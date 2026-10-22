"""Manual editing over the existing ownership barrier and append-only journal."""
from contextlib import ExitStack, closing, nullcontext
import copy
import hashlib
import json
import sqlite3
import uuid

from project_portal import Store, atomic_write, now
from task_transfer import barrier, inventory


STAGE_FIELDS = {'title', 'status', 'summary', 'done', 'remaining', 'dependsOn', 'evidence', 'blocker', 'estimate'}
TASK_FIELDS = {'title', 'summary', 'status', 'scope', 'deferred', 'acceptance',
               'sources', 'type', 'priority', 'parentTask', 'weight', 'estimate', 'links', 'blocker'}
INVERSE = {'blocks': 'blocked-by', 'blocked-by': 'blocks', 'related': 'related',
           'duplicates': 'duplicated-by', 'duplicated-by': 'duplicates'}
STAGE_TITLES = {
    'create': "\u042d\u0442\u0430\u043f \u0441\u043e\u0437\u0434\u0430\u043d",
    'update': "\u042d\u0442\u0430\u043f \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d",
    'delete': "\u042d\u0442\u0430\u043f \u0443\u0434\u0430\u043b\u0451\u043d",
    'unlink': "\u042d\u0442\u0430\u043f \u043e\u0442\u0432\u044f\u0437\u0430\u043d",
    'transfer': "\u042d\u0442\u0430\u043f \u043f\u0435\u0440\u0435\u043d\u0435\u0441\u0451\u043d",
    'restore': "\u042d\u0442\u0430\u043f \u0432\u043e\u0441\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d",
}


def validate_links(registry, project, task, links):
    if not isinstance(links, list):
        raise ValueError('Links must be a list')
    with barrier(registry):
        _, owners, _ = inventory(registry)
        for link in links:
            if not isinstance(link, dict) or set(link) - {'type', 'target', 'project'} or link.get('type') not in INVERSE:
                raise ValueError('Invalid link')
            location = link.get('project', project)
            if not isinstance(location, str) or not location or not isinstance(link.get('target'), str):
                raise ValueError('Invalid linked task/project')
            if location == project and link['target'] == task:
                raise ValueError('A task cannot link to itself')
            if not any(o['task'] == link['target'] and location in (o['owner'], o['origin']) for o in owners):
                raise ValueError('Unknown linked task/project')


def project_operation(tasks, event):
    """Replay a single atomic lifecycle event; never rewrite earlier events."""
    if event['kind'] == 'stage.imported':
        tasks[event['taskId']]['stages'].extend(copy.deepcopy(event['importedStages']))
        return
    if event.get('stageIds'):
        for stage_id in event['stageIds']:
            item = {key: value for key, value in event.items() if key != 'stageIds'}
            item['stageId'] = stage_id
            item['history'] = [entry for entry in event.get('history', [])
                               if entry.get('stageId') == stage_id or stage_id in entry.get('stageIds', [])]
            project_operation(tasks, item)
        return
    source = tasks[event['taskId']]
    if event['kind'] == 'stage.restored':
        archived = next(s for s in reversed(source.get('archivedStages', []))
                        if s['id'] == event['stageId'] and s['lifecycle']['action'] in ('deleted', 'unlinked')
                        and not s['lifecycle'].get('restoredAt'))
        stage = copy.deepcopy(archived)
        stage.pop('lifecycle')
        source['stages'].append(stage)
        archived['lifecycle'].update(restoredAt=event['at'], restoredEventId=event['id'])
        return
    stage = next(item for item in source['stages'] if item['id'] == event['stageId'])
    source['stages'].remove(stage)
    archive = copy.deepcopy(stage)
    archive['lifecycle'] = {'action': 'transferred' if event['kind'] == 'stage.exported' else event['kind'].split('.')[1], 'at': event['at'],
                            'eventId': event['id'], 'reason': event.get('detail', '')}
    if event.get('targetTask'):
        archive['lifecycle']['targetTask'] = event['targetTask']
    if event.get('transactionId'):
        archive['lifecycle']['transactionId'] = event['transactionId']
    source.setdefault('archivedStages', []).append(archive)
    if event['kind'] == 'stage.transferred':
        target = tasks[event['targetTask']]
        history = stage.setdefault('history', [])
        known = {item['id'] for item in history}
        history.extend(copy.deepcopy(item) for item in event.get('history', []) if item['id'] not in known)
        stage.setdefault('transfers', []).append({'fromTask': source['id'], 'toTask': target['id'],
                                                 'at': event['at'], 'eventId': event['id']})
        target['stages'].append(stage)
        target['updatedAt'] = event['at']


def project_links(registry, project, state, *, serialized=True):
    """Add reciprocal read projection, leaving the journal's outgoing links alone."""
    with barrier(registry) if serialized else nullcontext():
        snapshots, owners, _ = registry.read_models.inventory(include_events=False)
        by_location = {(row['origin'], row['task']): row for row in owners}
        current = {(row['owner'], row['task']): row for row in owners}
        visible = {task['id']: task for task in state['tasks']}
        for task in visible.values():
            task['relations'] = []
        seen = set()
        for entry in owners:
            task = next(t for t in snapshots[entry['origin']][1] if t['id'] == entry['task'])
            for link in task.get('links', []):
                location = link.get('project') or entry['origin']
                target = by_location.get((location, link['target'])) or current.get((location, link['target']))
                if not target and not link.get('project'):
                    target = current.get((entry['owner'], link['target']))
                if not target:
                    continue
                endpoints = ((entry, target, link['type'], 'outgoing'),
                             (target, entry, INVERSE[link['type']], 'incoming'))
                for source, other, kind, direction in endpoints:
                    key = (source['uid'], other['uid'], kind)
                    if source['owner'] != project or source['task'] not in visible or key in seen:
                        continue
                    seen.add(key)
                    visible[source['task']]['relations'].append({
                        'type': kind, 'target': other['task'], 'project': other['owner'],
                        'direction': direction, 'sourceTask': entry['task'],
                        'sourceProject': entry['owner']})
        state['relationsRevision'] = hashlib.sha256(json.dumps(
            [(task['id'], task['relations']) for task in state['tasks']], sort_keys=True).encode()).hexdigest()[:20]
    return state


def _digest(data):
    return hashlib.sha256(data).hexdigest()


def _journal_bytes(store):
    return store.journal.read_bytes() if store.journal.exists() else b''


def _append_event(data, event):
    prefix = data.decode('utf-8')
    if prefix and not prefix.endswith('\n'):
        prefix += '\n'
    return prefix + json.dumps(event, ensure_ascii=False) + '\n'


def _transfer_checkpoint(point):
    """Fault-injection boundary; production execution needs no side effect."""


def _apply_stage_transaction(registry, transaction, stores):
    """Caller holds the global barrier and both journal locks, in stable order."""
    writes = []
    for item in transaction['journals']:
        store = stores[item['project']]
        data = _journal_bytes(store)
        if _digest((store.data / 'project.json').read_bytes()) != item['seedHash']:
            raise ValueError('Stage transfer recovery conflict: baseline changed; no divergent data overwritten')
        digest = _digest(data)
        if digest == item['afterHash']:
            writes.append((store, None))
        elif digest == item['beforeHash'] and store.journal.exists() == item['beforeExists']:
            text = _append_event(data, item['event'])
            if _digest(text.encode('utf-8')) != item['afterHash']:
                raise ValueError('Invalid stage transfer recovery payload')
            seed, events = store._load()
            if len(events) != item['beforeRevision']:
                raise ValueError('Stage transfer recovery revision conflict')
            store.project(seed, [*events, item['event']], hierarchy=False)
            writes.append((store, text))
        else:
            raise ValueError('Stage transfer recovery conflict: journal diverged; no divergent data overwritten')
    # Validate every participant before replacing any file. After durable intent,
    # failures leave redo work, not an invitation to roll either journal back.
    for index, (store, text) in enumerate(writes):
        if text is not None:
            atomic_write(store.journal, text)
        _transfer_checkpoint('after_first_write' if index == 0 else 'after_second_write')
    with registry.connect() as connection:
        connection.execute('BEGIN IMMEDIATE')
        try:
            connection.execute("UPDATE stage_transactions SET state='done' WHERE id=? AND state='pending'",
                               (transaction['id'],))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def recover_stage_transfers(registry):
    """Redo pending intents before coordinated observations or new mutations."""
    with registry.connect() as connection:
        pending = [json.loads(row['body']) for row in connection.execute(
            "SELECT body FROM stage_transactions WHERE state='pending' ORDER BY rowid")]
    for transaction in pending:
        stores = {item['project']: registry.base_store(item['project']) for item in transaction['journals']}
        with ExitStack() as locks:
            for project in sorted(stores):
                locks.enter_context(stores[project].locked())
            _apply_stage_transaction(registry, transaction, stores)


def commit_stage_transfer(registry, entries, transaction_id):
    """Commit a fully validated intent; entries' journal locks are already held."""
    transaction = {'id': transaction_id, 'journals': []}
    stores = {}
    for store, events, event in entries:
        data = _journal_bytes(store)
        after = _append_event(data, event)
        stores[store.project_id] = store
        transaction['journals'].append({
            'project': store.project_id, 'seedHash': _digest((store.data / 'project.json').read_bytes()),
            'beforeHash': _digest(data), 'beforeExists': store.journal.exists(), 'beforeRevision': len(events),
            'afterHash': _digest(after.encode('utf-8')), 'event': event})
    with registry.connect() as connection:
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('BEGIN IMMEDIATE')
        try:
            connection.execute('INSERT INTO stage_transactions VALUES(?,?,?,?)',
                               (transaction_id, 'pending', now(), json.dumps(transaction, ensure_ascii=False)))
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
    _transfer_checkpoint('after_intent')
    _apply_stage_transaction(registry, transaction, stores)


def _bind_provenance(value, origin):
    if isinstance(value, list):
        return [_bind_provenance(item, origin) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: _bind_provenance(item, origin) for key, item in value.items()}
    if isinstance(result.get('path'), str):
        source = result.get('sourceProject', origin)
        result['sourceProject'] = source
    return result


def _validate_destination(stages, target):
    selected = {stage['id']: stage for stage in stages}
    if any(stage['id'] in selected for stage in target['stages']):
        raise ValueError('Destination already contains this stage ID')
    for archived in target.get('archivedStages', []):
        moving = selected.get(archived['id'])
        if moving is None:
            continue
        lifecycle = archived.get('lifecycle', {})
        ancestry = {entry['eventId'] for entry in moving.get('transfers', [])
                    if entry.get('fromTask') == target['id']}
        if lifecycle.get('action') != 'transferred' or \
                lifecycle.get('transactionId', lifecycle.get('eventId')) not in ancestry:
            raise ValueError('Destination stage ID is reserved by unrelated archive history')


def manual_operation(registry, project, route, body):
    operation = route.rsplit('/', 1)[1]
    task_create = route == '/api/v1/tasks/create'
    if not isinstance(body, dict):
        raise ValueError('Invalid manual editing fields')
    body = copy.deepcopy(body)
    requested_id = None
    if task_create:
        if 'patch' in body:
            raise ValueError('Use task for task creation')
        body['patch'] = body.pop('task', None)
    elif operation == 'create':
        if 'patch' in body:
            raise ValueError('Use stage for stage creation')
        body['patch'] = body.pop('stage', None)
        if isinstance(body['patch'], dict):
            requested_id = body['patch'].pop('id', None)
            if requested_id is not None and (not isinstance(requested_id, str) or
                    not requested_id.strip() or len(requested_id) > 120):
                raise ValueError('Invalid stage ID')
    elif operation == 'transfer':
        if 'targetTask' in body:
            raise ValueError('Use target for stage transfer')
        body['targetTask'] = body.pop('target', None)
    allowed = {'expected', 'patch'} if task_create else {'task', 'expected'}
    if not task_create:
        allowed |= {'patch'} if operation == 'create' else {'stage'}
        if operation == 'update':
            allowed.add('patch')
        if operation in ('delete', 'unlink', 'transfer'):
            allowed.add('reason')
        if operation == 'transfer':
            allowed.update(('targetTask', 'includeDependencies'))
    if not isinstance(body, dict) or set(body) - allowed:
        raise ValueError('Invalid manual editing fields')
    if not isinstance(body.get('expected'), str) or not body['expected']:
        raise ValueError('Expected revision is required')
    if 'reason' in body and (not isinstance(body['reason'], str) or len(body['reason']) > 1600):
        raise ValueError('Invalid operation reason')
    if 'includeDependencies' in body and type(body['includeDependencies']) is not bool:
        raise ValueError('includeDependencies must be a boolean')
    for field in ('task', 'stage', 'targetTask'):
        if field in allowed and (not isinstance(body.get(field), str) or not body[field].strip()):
            raise ValueError('Missing ' + field)
    with barrier(registry):
        store = registry.store(project)
        state = store.snapshot()
        if body['expected'] != state['revision']:
            raise ValueError('Task changed; refresh before writing')
        if task_create or operation in ('create', 'update'):
            patch = body.get('patch')
            if not isinstance(patch, dict) or not patch or set(patch) - (TASK_FIELDS if task_create else STAGE_FIELDS):
                raise ValueError('Invalid manual patch')
            patch = copy.deepcopy(patch)
            if operation == 'create':
                patch.setdefault('status', 'planned')
            if task_create and patch.get('status') in ('done', 'cancelled'):
                raise ValueError('Create an unfinished task, then use its explicit lifecycle route')
            identity = requested_id or ('hub-' if task_create else 'stage-') + uuid.uuid4().hex[:16]
            task_id = identity if task_create else body['task']
            if task_create:
                patch['stages'] = []
                if 'links' in patch:
                    validate_links(registry, project, task_id, patch['links'])
            else:
                task = next((t for t in state['tasks'] if t['id'] == task_id), None)
                if task is None:
                    raise ValueError('Unknown task')
                if task['status'] in ('done', 'cancelled'):
                    raise ValueError('Reopen the task before editing stages')
                if operation == 'create' and any(s['id'] == identity for s in task.get('archivedStages', [])):
                    raise ValueError('Stage ID is reserved by audit history')
            event = dict(taskId=task_id, kind=('task.' if task_create else 'stage.') +
                         ('created' if operation == 'create' else 'updated'),
                         title="\u0417\u0430\u0434\u0430\u0447\u0430 \u0441\u043e\u0437\u0434\u0430\u043d\u0430" if task_create else STAGE_TITLES[operation], patch=patch)
            if not task_create:
                event['stageId'] = identity if operation == 'create' else body['stage']
            store.record(event, expected_revision=body['expected'])
            result = store.snapshot()
            if operation == 'create':
                result['createdTask' if task_create else 'createdStage'] = identity
            return project_links(registry, project, result)
        source = next((t for t in state['tasks'] if t['id'] == body['task']), None)
        if source is None:
            raise ValueError('Unknown source task')
        target = next((t for t in state['tasks'] if t['id'] == body.get('targetTask')), None)
        if operation == 'transfer':
            if not target or target['id'] == source['id']:
                raise ValueError('Choose a different destination task in this project')
        affected = [source] + ([target] if target else [])
        if any(s.get('gitCheckpoint', {}).get('status') == 'pending' for t in affected for s in t.get('stages', [])):
            raise ValueError('Git checkpoint is running; retry this stage operation when it finishes')
        if any(t['status'] in ('done', 'cancelled') for t in affected):
            raise ValueError('Reopen affected tasks before editing stages')
        bases = {task['originProject']: registry.base_store(task['originProject']) for task in affected}
        base = bases[source['originProject']]
        with ExitStack() as locks:
            for origin in sorted(bases):
                locks.enter_context(bases[origin].locked())
            loaded = {origin: origin_store._load() for origin, origin_store in bases.items()}
            for task in affected:
                if len(loaded[task['originProject']][1]) != task['_sourceRevision']:
                    raise ValueError('Task journal changed; refresh before writing')
            seed, events = loaded[source['originProject']]
            tasks = {t['id']: t for t in base.project(seed, events, hierarchy=False)}
            target_original = None
            if target:
                target_seed, target_events = loaded[target['originProject']]
                target_original = next(t for t in Store.project(target_seed, target_events, hierarchy=False)
                                       if t['id'] == target['id'])
            original = tasks[source['id']]
            if operation == 'restore':
                if any(s['id'] == body['stage'] for s in original['stages']):
                    raise ValueError('Stage is already active')
                stage = next((s for s in reversed(original.get('archivedStages', []))
                              if s['id'] == body['stage'] and s['lifecycle']['action'] in ('deleted', 'unlinked')
                              and not s['lifecycle'].get('restoredAt')), None)
            else:
                stage = next((s for s in original['stages'] if s['id'] == body['stage']), None)
            if stage is None:
                raise ValueError('Unknown stage for this operation')
            selected = {stage['id']}
            if operation == 'transfer' and body.get('includeDependencies'):
                # Take the undirected dependency component so neither task gains
                # a dangling edge, including reverse dependents and shared prerequisites.
                while True:
                    expanded = set(selected)
                    for item in original['stages']:
                        dependencies = set(item.get('dependsOn', []))
                        if item['id'] in selected or dependencies & selected:
                            expanded.update(dependencies | {item['id']})
                    if expanded == selected:
                        break
                    selected = expanded
            elif stage.get('dependsOn') or any(stage['id'] in s.get('dependsOn', []) for s in original['stages']):
                raise ValueError('Stage has dependencies; update dependencies before detaching or transferring')
            if target:
                _validate_destination([item for item in original['stages'] if item['id'] in selected], target_original)
            if any(t.get('currentWork') for t in affected):
                raise ValueError('Task has unfinished work; publish its checkpoint first')
            from check_runs import project_runs
            if any(run['kind'] == 'check.started' and run['taskId'] == source['id']
                   and (not run.get('stageId') or run['stageId'] in selected)
                   for run in project_runs(events)):
                raise ValueError('Stage has a running check; finish or reconcile it first')
            database = registry.home / 'coordination/coordination.sqlite3'
            if database.exists():
                connection = locks.enter_context(closing(sqlite3.connect(database, timeout=5)))
                connection.execute('BEGIN IMMEDIATE')
                for task in affected:
                    locations = (project, task['originProject'])
                    if connection.execute("SELECT 1 FROM work WHERE project IN (?,?) AND task=? AND status IN ('active','waiting') LIMIT 1",
                                          (*locations, task['id'])).fetchone():
                        raise ValueError('Task has active work; publish its checkpoint first')
                    for row in connection.execute('SELECT payload FROM plan_outbox WHERE project IN (?,?)', locations):
                        if json.loads(row[0]).get('taskId') == task['id']:
                            raise ValueError('Task has pending reports; deliver reports first')
            event = dict(id=uuid.uuid4().hex, taskId=source['id'], stageId=stage['id'],
                         kind='stage.' + {'delete': 'deleted', 'unlink': 'unlinked', 'transfer': 'transferred', 'restore': 'restored'}[operation],
                         title=STAGE_TITLES[operation], detail=body.get('reason', ''), actor='local-user',
                         at=now(), seq=len(events) + 1, schemaVersion=1)
            if target:
                event['targetTask'] = target['id']
                if len(selected) > 1:
                    event['stageIds'] = [s['id'] for s in original['stages'] if s['id'] in selected]
                event['history'] = [{key: copy.deepcopy(value) for key, value in e.items() if key != 'history'} for e in events
                                    if e['taskId'] == source['id'] and
                                    (e.get('stageId') in selected or selected.intersection(e.get('stageIds', [])))]
            if target and target['originProject'] != source['originProject']:
                transaction_id = event['id']
                imported = []
                for original_stage in original['stages']:
                    if original_stage['id'] not in selected:
                        continue
                    moved = _bind_provenance(copy.deepcopy(original_stage), source['originProject'])
                    history = moved.setdefault('history', [])
                    known = {item['id'] for item in history}
                    for item in event.get('history', []):
                        if item['id'] not in known and (item.get('stageId') == moved['id'] or moved['id'] in item.get('stageIds', [])):
                            history.append(_bind_provenance({key: value for key, value in item.items()
                                                            if key != 'importedStages'}, source['originProject']))
                            known.add(item['id'])
                    moved.setdefault('transfers', []).append({'fromTask': source['id'], 'toTask': target['id'],
                        'fromOrigin': source['originProject'], 'toOrigin': target['originProject'],
                        'at': event['at'], 'eventId': transaction_id})
                    imported.append(moved)
                exported = {key: value for key, value in event.items() if key != 'history'}
                exported.update(id=transaction_id + '-export', kind='stage.exported', transactionId=transaction_id)
                received = dict(id=transaction_id + '-import', kind='stage.imported', taskId=target['id'],
                                stageId=stage['id'], stageIds=[item['id'] for item in imported],
                                importedStages=imported, transactionId=transaction_id, sourceTask=source['id'],
                                sourceOrigin=source['originProject'], title=STAGE_TITLES['transfer'],
                                detail=body.get('reason', ''), actor='local-user', at=event['at'],
                                schemaVersion=1, seq=len(target_events) + 1)
                base.project(seed, [*events, exported], hierarchy=False)
                Store.project(target_seed, [*target_events, received], hierarchy=False)
                Store.project({'tasks': state['tasks']}, [exported, received])
                commit_stage_transfer(registry, [(base, events, exported),
                                      (bases[target['originProject']], target_events, received)], transaction_id)
            else:
                base.project(seed, [*events, event], hierarchy=False)
                Store.project({'tasks': state['tasks']}, [event])
                atomic_write(base.journal, ''.join(json.dumps(e, ensure_ascii=False) + '\n' for e in [*events, event]))
        return project_links(registry, project, store.snapshot())
