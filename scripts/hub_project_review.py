"""Bounded fixed scopes and explicit review decisions over existing Hub stores."""
from datetime import datetime, timezone
import hashlib
import json
import math
import re
import sqlite3

from artifact_store import publish, resolve, parse, cas
from task_transfer import barrier

INTENTS = ('review', 'next-step', 'relevance', 'estimate', 'closure-review')
DECISIONS = ('current', 'done', 'superseded', 'duplicate', 'clarify')


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def text(value, limit):
    value = value if isinstance(value, str) else encoded(value).decode('utf-8')
    return value if len(value) <= limit else value[:limit - 1] + '…'


def basis(task, stage=None):
    keys = ('id', 'title', 'status', 'summary', 'scope', 'acceptance', 'deferred', 'parentTask', 'links', 'priority')
    result = {key: task.get(key) for key in keys}
    stages = [item for item in task.get('stages', []) if stage is None or item['id'] == stage]
    result['stages'] = [{key: item.get(key) for key in ('id', 'title', 'status', 'summary', 'remaining', 'done', 'dependsOn')}
                        for item in stages]
    return digest(result)


def scope(state, target='project', task=None, stage=None):
    if target not in ('project', 'task', 'stage') or (target == 'project' and (task or stage)):
        raise ValueError('Invalid fixed review target')
    if target != 'project' and not isinstance(task, str):
        raise ValueError('Task target is required')
    if (target == 'stage') != (stage is not None):
        raise ValueError('Stage target requires exactly one stage')
    if stage is not None and (not isinstance(stage, str) or not stage.strip()):
        raise ValueError('Stage ID must be nonempty')
    tasks = state['tasks'] if target == 'project' else [item for item in state['tasks'] if item['id'] == task]
    if target != 'project' and not tasks:
        raise ValueError('Task does not belong to this project')
    if target == 'project':
        tasks = [item for item in tasks if item.get('status') not in ('done', 'cancelled')]
    rows = []
    for item in tasks:
        stages = [s for s in item.get('stages', []) if s['id'] == stage] if stage else [
            s for s in item.get('stages', []) if s.get('status') != 'done']
        if stage and not stages:
            raise ValueError('Stage does not belong to this task')
        rows.append(dict(task=item['id'], stages=[s['id'] for s in stages]))
    return dict(target=target, task=task, stage=stage, tasks=rows)


def summary_from(state, selected=None):
    selected = selected or scope(state)
    by_id = {item['id']: item for item in state['tasks']}
    decisions = {}
    for event in state.get('allEvents', state.get('events', [])):
        if event.get('kind') == 'decision':
            decisions[event['taskId']] = text(event.get('detail', event.get('title', '')), 180)
    rows = []
    sessions = {'active': set(), 'waiting': set(), 'unknown': set()}
    unknown_tasks = 0
    for selected_task in selected['tasks']:
        task = by_id.get(selected_task['task'])
        if task is None:
            raise ValueError('Fixed task moved; refresh the scope')
        stage_ids = selected_task['stages']
        stages = [item for item in task.get('stages', []) if item['id'] in stage_ids]
        if len(stages) != len(stage_ids):
            raise ValueError('Fixed stage moved; refresh the scope')
        selected_stage = next((s for s in stages if s['id'] == selected.get('stage')), None)
        activity = (selected_stage or task).get('agentActivity', {}).get('state', 'unknown')
        for kind in sessions:
            sessions[kind].update((selected_stage or task).get('agentSessions', {}).get(kind, []))
        if activity == 'unknown':
            unknown_tasks += 1
        for work in task.get('currentWorks', []):
            if selected_stage and selected_stage['id'] not in work.get('stageIds', [work.get('stageId')]):
                continue
            if work.get('session'):
                sessions['active'].add(work['session'])
        remaining = [(item['id'], point) for item in stages for point in item.get('remaining', [])]
        rows.append(dict(id=task['id'], title=text(task['title'], 180), status=task['status'],
            type=task.get('type', 'task'), priority=task.get('priority'), parentTask=task.get('parentTask'),
            goal=text(task.get('scope', task.get('summary', '')), 300), acceptance=text(task.get('acceptance', []), 350),
            remaining=[dict(stage=identity, text=text(point, 160)) for identity, point in remaining[:3]],
            remainingCount=len(remaining), stages=[dict(id=item['id'], status=item['status'],
                dependsOn=item.get('dependsOn', []), expectedState=basis(task, item['id'])) for item in stages],
            expectedState=basis(task, selected.get('stage')),
            estimate=(selected_stage or task).get('estimate'), activity=activity,
            lastDecision=decisions.get(task['id']), refs=[text(ref, 220) for ref in task.get('sources', [])[:3]],
            refsCount=len(task.get('sources', [])), creator=task.get('createdBy')))
    ids = {row['id'] for row in rows}
    # Parent totals can include child work. Retain unknown parent-only effort
    # explicitly instead of treating an excluded epic's own requirements as zero.
    parents = {row['parentTask'] for row in rows if row.get('parentTask') in ids}
    candidates = [row for row in rows if row['id'] not in parents]
    groups = {row['id']: row['id'] for row in candidates}
    def root(identity):
        while groups[identity] != identity:
            identity = groups[identity]
        return identity
    for row in candidates:
        task = by_id[row['id']]
        for link in task.get('links', []):
            other = link.get('target')
            if link.get('type') in ('duplicates', 'duplicated-by') and other in groups and link.get('project', state['project']['id']) == state['project']['id']:
                left, right = sorted((root(row['id']), root(other)))
                groups[right] = left
    estimate_groups = {}
    for row in candidates:
        estimate_groups.setdefault(root(row['id']), []).append(row)
    low = high = 0
    known = 0
    for members in estimate_groups.values():
        estimates = [member.get('estimate') or {} for member in members]
        valid = [e for e in estimates if all(isinstance(e.get(key), (int, float)) and not isinstance(e.get(key), bool)
                 and math.isfinite(e[key]) for key in ('hoursLow', 'hoursHigh')) and 0 <= e['hoursLow'] <= e['hoursHigh']]
        if valid:
            low += max(e['hoursLow'] for e in valid)
            high += max(e['hoursHigh'] for e in valid)
            known += 1
    unknown = len(estimate_groups) - known
    sessions['unknown'] -= sessions['active']
    sessions['waiting'] -= sessions['active'] | sessions['unknown']
    return dict(project=state['project']['id'], revision=state['revision'], scope=selected, rows=rows,
        total=len(rows), activity=dict(state='active' if sessions['active'] else 'unknown' if unknown_tasks else
            'waiting' if any(row['activity'] == 'waiting' for row in rows) else 'idle',
            activeChats=len(sessions['active']), unknownChats=len(sessions['unknown']), waitingChats=len(sessions['waiting']), unknownTasks=unknown_tasks,
            waitingTasks=sum(row['activity'] == 'waiting' for row in rows)),
        estimate=dict(hoursLow=low if known else None, hoursHigh=high if known else None,
            knownGroups=known, unknownGroups=unknown, parentEffortUnallocated=sorted(parents),
            complete=bool(known) and not unknown and not parents, confidence='low',
            basis='Sequential active agent time; waiting, queues and pauses excluded. Parent/duplicate work is not added twice.'))


def page(summary, offset=0, budget=11500):
    if isinstance(budget, bool) or not isinstance(budget, int) or not 8000 <= budget <= 12000:
        raise ValueError('Summary budget must be 8000–12000 UTF-8 bytes')
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= len(summary['rows']):
        raise ValueError('Invalid summary offset')
    result = {key: value for key, value in summary.items() if key not in ('rows', 'scope')}
    result.update(target=summary['scope']['target'], task=summary['scope']['task'], stage=summary['scope']['stage'],
                  offset=offset, rows=[], next=None, coverage='all fixed tasks, paged')
    parents = result['estimate'].get('parentEffortUnallocated', [])
    result['estimate'] = dict(result['estimate'], parentEffortUnallocated=parents[:10],
                              parentEffortUnallocatedCount=len(parents))
    if len(encoded(result)) > budget:
        raise ValueError('Summary metadata exceeds its bounded budget')
    for row in summary['rows'][offset:]:
        if len(encoded(row)) > budget - len(encoded(result)):
            row = dict(row, stages=[], stageCount=len(row['stages']), stageDetailsOmitted=True,
                       stageIndexRef='task:' + row['id'])
        result['rows'].append(row)
        if len(encoded(result)) > budget:
            result['rows'].pop()
            break
    if offset < len(summary['rows']) and not result['rows']:
        raise ValueError('One task exceeds the bounded summary; use its task reference')
    end = offset + len(result['rows'])
    result['next'] = end if end < len(summary['rows']) else None
    return result


def summary(registry, project, target='project', task=None, stage=None, offset=0, expected=None):
    store = registry.store(project)
    state = getattr(store, 'memory_snapshot', store.snapshot)()
    if expected is not None and expected != state['revision']:
        raise ValueError('Summary changed; refresh before reading another page')
    return page(summary_from(state, scope(state, target, task, stage)), offset)


def freeze_scope(registry, project, action_id, state, target, task, stage):
    if not isinstance(action_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', action_id):
        raise ValueError('Invalid action ID')
    value = summary_from(state, scope(state, target, task, stage))
    value.update(schemaVersion=1, kind='agent-action-scope', actionId=action_id)
    artifact = publish(registry.store(project), 'scope-' + action_id + '.json', encoded(value),
                       roles=['evidence'], provenance='explicit-agent-action:' + action_id)
    return value, artifact['source']['path']


def read_scope(registry, project, reference, action_id=None):
    store = registry.store(project)
    descriptor, content = registered_artifact(store, reference)
    value = json.loads(content)
    if (not isinstance(value, dict) or value.get('kind') != 'agent-action-scope' or value.get('project') != project
            or value.get('schemaVersion') != 1 or (action_id is not None and value.get('actionId') != action_id)):
        raise ValueError('Scope artifact belongs to another action/project')
    if descriptor['provenance'] != 'explicit-agent-action:' + value.get('actionId',''):
        raise ValueError('Scope has no explicit action provenance')
    selected = value.get('scope')
    if not isinstance(selected, dict) or selected.get('target') not in ('project', 'task', 'stage') or not isinstance(selected.get('tasks'), list):
        raise ValueError('Invalid captured scope')
    seen = set()
    for item in selected['tasks']:
        if (not isinstance(item, dict) or set(item) != {'task','stages'} or not isinstance(item['task'], str)
                or item['task'] in seen or not isinstance(item['stages'], list) or
                any(not isinstance(identity, str) or not identity.strip() for identity in item['stages']) or
                len(set(item['stages'])) != len(item['stages'])):
            raise ValueError('Invalid fixed task/stage membership')
        seen.add(item['task'])
    if selected['target'] != 'project' and (len(selected['tasks']) != 1 or selected['tasks'][0]['task'] != selected.get('task')):
        raise ValueError('Captured task target is inconsistent')
    if selected['target'] == 'stage' and (not selected.get('stage') or selected['tasks'][0]['stages'] != [selected['stage']]):
        raise ValueError('Captured stage target is inconsistent')
    return value


def registered_artifact(store, reference):
    identifier,_ = parse(reference)
    marker=cas(store).data / 'artifact-descriptors' / identifier
    if not marker.is_file() or marker.is_symlink() or marker.read_bytes() != (identifier+'\n').encode('ascii'):
        raise ValueError('Artifact is not registered in this project')
    return resolve(store,reference)


def immutable_evidence(store, reference):
    if not isinstance(reference, str) or len(reference) > 300:
        raise ValueError('Use bounded immutable evidence references')
    if reference.startswith('hub-artifact/'):
        registered_artifact(store, reference)
    elif reference.startswith('hub-source/'):
        origin, relative = store.evidence_origin(reference)
        resolve(origin, relative)
    elif re.fullmatch(r'knowledge/revision/[0-9]+/document/.+', reference):
        from knowledge_store import KnowledgeStore
        _, _, revision, _, identifier = reference.split('/', 4)
        KnowledgeStore(store.registry, store.project_id).read(identifier, int(revision))
    elif re.fullmatch(r'git:(?:[0-9a-f]{40}|[0-9a-f]{64})', reference):
        from git_integration import _run
        if _run(store.root, 'cat-file', '-t', reference[4:]) != 'commit':
            raise ValueError('Evidence commit is unavailable')
    else:
        raise ValueError('Completion requires immutable artifact, Knowledge revision or Git commit evidence')


def publish_review(registry, project, session, action_id, work, expected, proposals):
    """Publish authored proposals; only later explicit local-user apply changes status."""
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= 20:
        raise ValueError('Publish 1–20 bounded proposals')
    with barrier(registry):
        with registry.connect() as c:
            action = c.execute('SELECT * FROM codex_chat_actions WHERE project=? AND action_id=?', (project, action_id)).fetchone()
        if not action or action['thread_id'] != session:
            raise ValueError('Review publication requires the action-owning verified native chat')
        response = json.loads(action['response'])
        if response.get('intent') not in INTENTS:
            raise ValueError('This action did not request a service review')
        from plugin_api import ServerHub
        hub = ServerHub(registry)
        with hub.connect() as c:
            owned = c.execute('SELECT * FROM work WHERE id=? AND session=? AND project=?', (work, session, project)).fetchone()
        if not owned or owned['phase'] not in ('review', 'research', 'planning') or owned['status'] != 'active':
            raise ValueError('Register your own active review/research work before publishing')
        frozen = read_scope(registry, project, response['scopeRef'], action_id)
        with hub.connect() as c:
            if c.execute("SELECT 1 FROM claims WHERE work=? AND mode='write'", (work,)).fetchone():
                raise ValueError('Service review requires read claims')
        if owned['task'] not in {item['task'] for item in frozen['scope']['tasks']}:
            raise ValueError('Review work must belong to an existing task in this action scope')
        if response.get('reviewRef'):
            prior = read_review(registry, project, response['reviewRef'])
            if prior['work'] == work and prior['reviewedRevision'] == expected and [
                    {k:v for k,v in p.items() if k != 'id'} for p in prior['proposals']] == proposals:
                return dict(source=dict(path=response['reviewRef']), proposals=prior['proposals'],
                            revision=registry.store(project).memory_snapshot()['revision'], replayed=True)
            raise ValueError('This action already published different proposals; start a fresh explicit review')
        store = registry.store(project)
        state = store.memory_snapshot()
        if expected != state['revision']:
            raise ValueError('Project changed; retrieve fresh scoped context before publishing')
        by_id = {item['id']: item for item in state['tasks']}
        allowed = {item['task']: set(item['stages']) for item in frozen['scope']['tasks']}
        reviewed = []
        targets = set()
        for value in proposals:
            validate_proposal(value)
            value = dict(value)
            task, stage = value.get('task'), value.get('stage')
            if task not in allowed or (stage is not None and stage not in allowed[task]):
                raise ValueError('Proposal lies outside the fixed action scope')
            if frozen['scope']['target'] == 'stage' and stage != frozen['scope']['stage']:
                raise ValueError('A stage review may not change its whole task')
            if (task, stage) in targets:
                raise ValueError('Use one reviewed decision per task/stage target')
            targets.add((task, stage))
            if any(t == task and s != stage and (s is None or stage is None) for t,s in targets):
                raise ValueError('Choose whole-task or stage proposals for a task without overlapping them')
            target = by_id.get(task)
            if target is None or value.get('expectedState') != basis(target, stage):
                raise ValueError('Proposal target changed; retrieve fresh target context')
            if value.get('decision') not in DECISIONS or any(not isinstance(value.get(key), str) or not value[key].strip()
                    or len(value[key]) > limit for key, limit in (('reason', 1200), ('confidence', 160))):
                raise ValueError('Decision, reason and confidence are required')
            evidence = value.get('evidence', [])
            if not isinstance(evidence, list) or not 1 <= len(evidence) <= 6:
                raise ValueError('Every proposal requires evidence')
            if value['decision'] == 'done':
                required = by_id[task].get('acceptance', []) if stage is None else []
                selected = target['stages'] if stage is None else [s for s in target['stages'] if s['id'] == stage]
                required = set(required) | {point for s in selected if s['status'] != 'done' for point in s.get('remaining', [])}
                criteria = value.get('criteria', [])
                if (not required or not isinstance(criteria, list) or any(not isinstance(entry, dict) or set(entry) != {'requirement','evidence'} or
                        not isinstance(entry['requirement'], str) or not isinstance(entry['evidence'], str) for entry in criteria)
                        or {entry.get('requirement') for entry in criteria} != required):
                    raise ValueError('Completion must account for every acceptance/remaining criterion')
                for entry in criteria:
                    if set(entry) != {'requirement', 'evidence'} or entry['evidence'] not in evidence:
                        raise ValueError('Every fulfilled criterion requires listed immutable evidence')
            elif any(not isinstance(reference, str) or not reference.strip() or len(reference) > 300 for reference in evidence):
                raise ValueError('Invalid proposal evidence')
            for reference in evidence:
                immutable_evidence(store, reference)
            if value['decision'] in ('superseded', 'duplicate'):
                replacement = value.get('replacement')
                if (not isinstance(replacement, dict) or set(replacement) != {'task','stage','expectedState'} or replacement['task'] == task
                        or replacement['task'] not in by_id or not any(s['id'] == replacement['stage'] for s in by_id[replacement['task']]['stages'])):
                    raise ValueError('Replacement requires a different task and an existing destination stage')
                requirements = value.get('requirements')
                if not isinstance(requirements, list) or len(requirements) > 20 or any(not isinstance(point, str) or not point.strip() or len(point) > 400 for point in requirements):
                    raise ValueError('Declare reviewed requirements to preserve in the destination stage')
                original = set(target.get('acceptance', [])) if stage is None else set()
                original.update(point for item in target['stages'] if (stage is None or item['id'] == stage)
                                and item['status'] != 'done' for point in item.get('remaining', []))
                if not original <= set(requirements) or replacement['expectedState'] != basis(by_id[replacement['task']], replacement['stage']):
                    raise ValueError('Preserve every unresolved requirement and verify the destination state')
            value['id'] = digest([action_id, value])[:24]
            reviewed.append(value)
        body = dict(schemaVersion=1, kind='project-review', project=project, actionId=action_id,
                    scopeRef=response['scopeRef'], intent=response['intent'], actor=session, work=work,
                    reviewedRevision=expected, proposals=reviewed)
        artifact = publish(store, 'review-' + action_id + '.json', encoded(body), roles=['evidence','deliverable'],
                           provenance='verified-review-session:' + session)
        source = dict(artifact['source'], label='Ревизия задач: предложения')
        hub.attach_artifact(session, owned['task'], source['path'], state['revision'], stage=None,
                            label=source['label'], roles=['evidence','deliverable'])
        with registry.connect() as c:
            row = c.execute('SELECT response FROM codex_chat_actions WHERE action_id=?', (action_id,)).fetchone()
            latest = json.loads(row[0]); latest['reviewRef'] = source['path']
            c.execute('UPDATE codex_chat_actions SET response=? WHERE action_id=?', (encoded(latest).decode('utf-8'), action_id))
        return dict(source=source, proposals=reviewed, revision=store.memory_snapshot()['revision'], writes='review evidence only')


def publish_estimates(registry, project, session, action_id, work, expected, estimates):
    """Explicit estimate intent authorizes estimate metadata, never scope/status edits."""
    from plugin_api import ServerHub
    from project_portal import validate_estimate
    if not isinstance(estimates, list) or not 1 <= len(estimates) <= 20:
        raise ValueError('Publish 1–20 bounded estimates')
    with barrier(registry):
        with registry.connect() as c:
            action = c.execute('SELECT * FROM codex_chat_actions WHERE project=? AND action_id=?', (project, action_id)).fetchone()
        if not action or action['thread_id'] != session:
            raise ValueError('Estimate requires the action-owning verified chat')
        response = json.loads(action['response'])
        if response.get('intent') != 'estimate':
            raise ValueError('Only an explicit estimate action may publish metadata')
        frozen = read_scope(registry, project, response['scopeRef'], action_id)
        allowed = {row['task']: set(row['stages']) for row in frozen['scope']['tasks']}
        hub = ServerHub(registry)
        with hub.connect() as c:
            owned = c.execute('SELECT * FROM work WHERE id=? AND project=? AND session=?', (work, project, session)).fetchone()
            write = c.execute("SELECT 1 FROM claims WHERE work=? AND mode='write'", (work,)).fetchone()
        if not owned or owned['status'] != 'active' or owned['phase'] not in ('planning','research','review') or write or owned['task'] not in allowed:
            raise ValueError('Register your own scoped service work with read claims')
        store = registry.store(project); state = store.memory_snapshot()
        prefix = 'review-estimate-' + digest([action_id, work, estimates])[:24] + '-'
        done = {event['id'] for event in state['allEvents']}
        if all(prefix + str(index) in done for index in range(len(estimates))):
            return dict(replayed=True, revision=state['revision'])
        if expected != state['revision']:
            raise ValueError('Project changed; refresh before publishing estimates')
        seen = set(); events = []
        by_id = {item['id']:item for item in state['tasks']}
        for index, entry in enumerate(estimates):
            if not isinstance(entry, dict) or set(entry) != {'task','stage','expectedState','estimate'}:
                raise ValueError('Estimate requires task, stage (or null), expectedState and estimate')
            task, stage = entry['task'], entry['stage']
            if not isinstance(task,str) or (stage is not None and not isinstance(stage,str)):
                raise ValueError('Estimate task/stage must be stable string IDs')
            if task not in allowed or (stage is not None and stage not in allowed[task]) or (task,stage) in seen:
                raise ValueError('Estimate lies outside the unique fixed scope')
            if frozen['scope']['target'] == 'stage' and stage != frozen['scope']['stage']:
                raise ValueError('Stage estimate may not update its task')
            seen.add((task,stage))
            if task not in by_id or entry['expectedState'] != basis(by_id[task], stage):
                raise ValueError('Estimate target changed')
            estimate = entry['estimate']
            if (not isinstance(estimate, dict) or set(estimate) - {'hoursLow','hoursHigh','percentLow','percentHigh','confidence','note'} or
                    not {'confidence','note'} <= set(estimate) or
                    any(not isinstance(estimate.get(key), str) or not estimate[key].strip() or len(estimate[key]) > limit
                        for key,limit in (('confidence',160),('note',1200)))):
                raise ValueError('Estimate needs confidence and basis note; omit both hours when unknown')
            validate_estimate(estimate)
            patch = dict(estimate=dict(estimate, updatedBy=session))
            event = dict(id=prefix+str(index), taskId=task, kind='stage.updated' if stage else 'task.updated',
                         title='Оценка оставшегося времени агента', detail='Явный запрос оценки: '+action_id, patch=patch)
            if stage: event['stageId'] = stage
            events.append(event)
        applied=[]
        try:
            for event in events:
                if event['id'] not in done:
                    store.record(event, expected_revision=state['revision'])
                    state = store.memory_snapshot()
                applied.append(event['id'])
        except (ValueError,OSError,sqlite3.Error) as error:
            return dict(status='partial' if applied else 'rejected', applied=applied, revision=store.memory_snapshot()['revision'], error=str(error))
        result = dict(status='published', applied=applied, revision=state['revision'], writes='estimate metadata only')
        with registry.connect() as c:
            current = c.execute('SELECT response FROM codex_chat_actions WHERE action_id=?', (action_id,)).fetchone()
            latest=json.loads(current[0]); latest['estimateResult']=result
            c.execute('UPDATE codex_chat_actions SET response=? WHERE action_id=?', (encoded(latest).decode(), action_id))
        return result


def validate_proposal(value, published=False):
    allowed={'task','stage','decision','reason','confidence','evidence','criteria','replacement','requirements','expectedState','priority'}
    if published: allowed.add('id')
    if (not isinstance(value,dict) or set(value)-allowed or not {'task','decision','reason','confidence','evidence','expectedState'}<=set(value)
            or any(not isinstance(value.get(key),str) for key in ('task','reason','confidence','expectedState'))
            or (value.get('stage') is not None and not isinstance(value['stage'],str))
            or value['decision'] not in DECISIONS or not re.fullmatch(r'[a-f0-9]{64}',value['expectedState'])
            or not isinstance(value['evidence'],list) or not 1<=len(value['evidence'])<=6
            or any(not isinstance(ref,str) or not ref.strip() or len(ref)>300 for ref in value['evidence'])):
        raise ValueError('Invalid proposal structure')
    if 'priority' in value:
        from project_portal import PRIORITIES
        if (value.get('stage') is not None or value['decision'] != 'current' or
                (value['priority'] is not None and (not isinstance(value['priority'], str) or value['priority'] not in PRIORITIES))):
            raise ValueError('Priority proposals require a whole-task current decision and a supported priority or null')
    if value['decision']=='done':
        criteria=value.get('criteria')
        if not isinstance(criteria,list) or not criteria or len(criteria)>100 or any(not isinstance(entry,dict) or
            set(entry)!={'requirement','evidence'} or not isinstance(entry['requirement'],str) or not isinstance(entry['evidence'],str)
            for entry in criteria):
            raise ValueError('Invalid completion criteria')
    if value['decision'] in ('superseded','duplicate'):
        replacement=value.get('replacement'); requirements=value.get('requirements')
        if (not isinstance(replacement,dict) or set(replacement)!={'task','stage','expectedState'} or
                any(not isinstance(replacement[key],str) or not replacement[key] for key in replacement) or
                not re.fullmatch(r'[a-f0-9]{64}',replacement['expectedState']) or not isinstance(requirements,list) or len(requirements)>20 or
                any(not isinstance(point,str) or not point.strip() or len(point)>400 for point in requirements)):
            raise ValueError('Invalid reviewed replacement')


def read_review(registry, project, reference):
    store = registry.store(project)
    origin, relative = store.evidence_origin(reference)
    descriptor, content = resolve(origin, relative)
    review = json.loads(content)
    if (not isinstance(review, dict) or review.get('kind') != 'project-review' or review.get('project') != project
            or review.get('schemaVersion') != 1 or not isinstance(review.get('actor'), str)
            or descriptor['provenance'] != 'verified-review-session:' + review['actor']
            or not isinstance(review.get('proposals'), list) or not 1 <= len(review['proposals']) <= 20
            or any(not isinstance(value, dict) or not re.fullmatch(r'[a-f0-9]{24}', value.get('id', ''))
                   or value.get('decision') not in DECISIONS for value in review['proposals'])
            or len({value['id'] for value in review['proposals']}) != len(review['proposals'])):
        raise ValueError('Review belongs to another project')
    if (any(not isinstance(review.get(key),str) or not review[key] for key in ('scopeRef','actionId','actor','work')) or
            not isinstance(review.get('reviewedRevision'),(str,int)) or isinstance(review['reviewedRevision'],bool)):
        raise ValueError('Invalid immutable review metadata')
    read_scope(registry,project,review['scopeRef'],review['actionId'])
    for value in review['proposals']:
        validate_proposal(value,published=True)
    return review


def apply_review(registry, project, reference, selected, expected):
    if (not isinstance(selected, list) or not 1 <= len(selected) <= 20 or
            any(not isinstance(identity,str) or not re.fullmatch(r'[a-f0-9]{24}',identity) for identity in selected) or len(set(selected)) != len(selected)):
        raise ValueError('Select 1–20 unique proposal IDs')
    review = read_review(registry, project, reference)
    proposals = {value['id']: value for value in review['proposals']}
    if any(identity not in proposals for identity in selected):
        raise ValueError('Unknown reviewed proposal')
    applied = []
    with barrier(registry):
        store = registry.store(project)
        state = store.memory_snapshot()
        prefix = 'review-apply-' + digest(review)[:20] + '-'
        events = {event['id'] for event in state['allEvents']}
        pending = [identity for identity in selected if prefix + identity + '-final' not in events]
        applied = [identity for identity in selected if identity not in pending]
        if not pending:
            return dict(status='applied', applied=applied, revision=state['revision'], replay=True)
        if expected != state['revision']:
            raise ValueError('Project changed; refresh before applying the reviewed decisions')
        by_id = {task['id']: task for task in state['tasks']}
        for identity in pending:
            value = proposals[identity]
            if value['task'] not in by_id or basis(by_id[value['task']], value.get('stage')) != value['expectedState']:
                raise ValueError('Reviewed target changed; review the new state before applying')
            destination = value.get('replacement')
            if destination and (destination['task'] not in by_id or basis(by_id[destination['task']], destination['stage']) != destination['expectedState']):
                raise ValueError('Replacement destination changed; review it before applying')
            if value['decision'] in ('done', 'superseded', 'duplicate') or 'priority' in value:
                from completion_policy import _work_boundary
                if any(work['write'] and work['status'] in ('active','waiting') for work in
                       _work_boundary(registry, project, value['task'], value.get('stage'))):
                    raise ValueError('Implementation work remains open; reconcile it before applying reviewed changes')
        try:
            for identity in pending:
                value = proposals[identity]
                state = store.memory_snapshot(); by_id = {task['id']: task for task in state['tasks']}
                source = by_id[value['task']]; stage = value.get('stage'); decision = value['decision']
                if decision in ('superseded', 'duplicate'):
                    destination = value['replacement']; target = by_id[destination['task']]
                    target_stage = next(s for s in target['stages'] if s['id'] == destination['stage'])
                    if target['status'] in ('done', 'cancelled') or target_stage['status'] in ('done', 'cancelled'):
                        raise ValueError('Replacement destination must remain open')
                    requirements = list(dict.fromkeys(target_stage.get('remaining', []) + value['requirements']))
                    proof = {'path': reference, 'label': 'Ревизия: перенос требований'}
                    original_sources = [dict(item) for item in source.get('sources', []) if isinstance(item, dict) and item.get('path')]
                    original_sources += [dict(item) for source_stage in source['stages'] if stage is None or source_stage['id'] == stage
                                         for item in source_stage.get('evidence', []) if isinstance(item, dict) and item.get('path')]
                    evidence = list(target_stage.get('evidence', []))
                    for item in original_sources + [proof]:
                        if item.get('path') not in {existing.get('path') for existing in evidence}:
                            evidence.append(item)
                    store.record(dict(id=prefix+identity+'-requirements', taskId=target['id'], stageId=target_stage['id'],
                        kind='stage.updated', title='Требования сохранены по ревизии', detail=value['reason'],
                        patch=dict(remaining=requirements, evidence=evidence)), expected_revision=state['revision'])
                    state = store.memory_snapshot()
                    links = source.get('links', []) + [dict(type='duplicates' if decision == 'duplicate' else 'related', target=target['id'])]
                    from stage_operations import validate_links
                    validate_links(registry, project, source['id'], links)
                    if stage is not None:
                        store.record(dict(id=prefix+identity+'-backlink', taskId=source['id'], kind='task.updated',
                            title='Связь с заменяющей задачей', patch=dict(links=links)), expected_revision=state['revision'])
                        state = store.memory_snapshot()
                    patch = dict(status='cancelled', closeReason=value['reason'], links=links) if stage is None else dict(status='cancelled')
                elif decision == 'done':
                    if stage is None and source.get('completion', {}).get('incompleteChildren'):
                        raise ValueError('Complete or explicitly resolve unfinished children before closing a task')
                    patch = dict(status='done', closeReason=value['reason'], closedManually=True) if stage is None else dict(status='done', remaining=[])
                else:
                    patch = dict(priority=value['priority']) if 'priority' in value else None
                event = dict(id=prefix+identity+'-final', taskId=source['id'], title='Ревизия: '+decision,
                             detail=value['reason']+'\nАвтор предложения: '+review['actor']+'; применено пользователем.',
                             evidence=[dict(path=reference, label='Просмотренное предложение')])
                if patch is None:
                    event['kind'] = 'decision'
                else:
                    event.update(kind='stage.updated' if stage else 'task.updated', patch=patch)
                    if stage:
                        event['stageId'] = stage
                store.record(event, expected_revision=state['revision'])
                applied.append(identity)
        except (ValueError, OSError, sqlite3.Error) as error:
            return dict(status='partial' if applied else 'rejected', applied=applied,
                        remaining=[identity for identity in selected if identity not in applied],
                        revision=store.memory_snapshot()['revision'], error=str(error))
        return dict(status='applied', applied=applied, revision=store.memory_snapshot()['revision'])
