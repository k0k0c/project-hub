"""Read-only chat history from existing work, task journals and Codex metadata."""
from collections import defaultdict
from datetime import datetime
import re
import sys

UUID = re.compile(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', re.I)
ACTOR = re.compile(r'[a-f0-9]{64}', re.I)


def event_session(event):
    """Only explicit chat identity is evidence; titles and prose are never parsed."""
    for field in ('session', 'actor'):
        value = event.get(field)
        if isinstance(value, dict):
            value = value.get('session')
        if isinstance(value, str) and (UUID.fullmatch(value) or ACTOR.fullmatch(value)):
            return value
    return None


def chat_history(store, task=None, offset=0, limit=25, query=''):
    state = getattr(store, 'memory_snapshot', store.snapshot)()
    project = getattr(store, 'project_id', state['project']['id'])
    tasks = {t['id']: t for t in state['tasks']}
    if task is not None and task not in tasks:
        raise ValueError('Unknown task')
    offset, limit = max(0, offset), max(1, min(100, limit))
    locations = {tid: {project, t.get('originProject', project)} for tid, t in tasks.items()}
    registry = getattr(store, 'registry', None)
    internal_actors = set()
    if registry is not None:
        from internal_operations import filter_portal_internal_tasks, research_actors
        visible = filter_portal_internal_tasks(registry, project, state)
        # Internal model operations have their own history, not user chat/task
        # entries. A direct task lookup still retains its historical record.
        if task is None:
            tasks = {t['id']: t for t in visible['tasks']}
            locations = {tid: places for tid, places in locations.items() if tid in tasks}
            internal_actors = research_actors(registry, project)
        by_uid = {t.get('uid'): tid for tid, t in tasks.items()}
        with registry.connect() as c:
            for row in c.execute('SELECT uid,source,target FROM task_transfers'):
                if row['uid'] in by_uid:
                    locations[by_uid[row['uid']]].update((row['source'], row['target']))

    memberships = defaultdict(set)
    last_work = {}
    stage_links = defaultdict(dict)
    def stage_relation(sid, tid, stage, stamp):
        known = next((s for s in tasks[tid].get('stages', []) if s['id'] == stage), None)
        if known is not None:
            previous = stage_links[sid].get((tid, stage), {})
            stage_links[sid][(tid, stage)] = dict(task=tid, stage=stage, title=known.get('title', stage),
                lastRelatedAt=max(previous.get('lastRelatedAt', 0), stamp))
    registered, relations, warnings = [], {}, []
    plugin_scripts = store.installation_root / 'tools/project-portal/plugins/project-hub/scripts'
    if str(plugin_scripts) not in sys.path:
        sys.path.insert(0, str(plugin_scripts))
    from hub_core import Hub
    from codex_session_catalog import CATALOG, merge_sessions
    from project_portal import SESSION_TITLES
    hub = Hub(store.coordination_home) if store.coordination_home is not None else Hub()
    if hub.db.exists():
        try:
            with hub.connect() as c:
                registered = [dict(r) for r in c.execute('SELECT id,project,workspace,state,seen,task FROM sessions')]
                if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='session_agents'").fetchone():
                    relations = {r['session']: dict(r) for r in c.execute('SELECT * FROM session_agents')}
                places = sorted(set().union(*locations.values())) if locations else [project]
                marks = ','.join('?' for _ in places)
                for row in c.execute(f'''SELECT w.project,w.task,w.session,l.stage,MAX(w.updated) AS updated
                        FROM work w LEFT JOIN (SELECT work,stage FROM work_stage_links
                            UNION SELECT work,stage FROM work_stages) l ON l.work=w.id
                        WHERE w.project IN ({marks}) GROUP BY w.project,w.task,w.session,l.stage''', places):
                    if row['project'] in locations.get(row['task'], ()):
                        memberships[row['session']].add(row['task'])
                        last_work[row['session']] = max(last_work.get(row['session'], 0), row['updated'])
                        stage_relation(row['session'], row['task'], row['stage'], row['updated'])
        except Exception as error:
            warnings.append('История работ недоступна: ' + str(error)[:160])
    else:
        warnings.append('История работ Hub отсутствует; доступны только сохраненные события и каталог Codex.')
    for t in tasks.values():
        creator = t.get('createdBy') or {}
        if (isinstance(creator, dict) and creator.get('project') in locations[t['id']]
                and isinstance(creator.get('session'), str) and 0 < len(creator['session']) <= 150):
            memberships[creator['session']].add(t['id'])
        for sid in t.get('participatingSessions', []):
            memberships[sid].add(t['id'])
    for event in state.get('allEvents', state.get('events', [])):
        sid = event_session(event)
        if sid and event.get('taskId') in tasks:
            memberships[sid].add(event['taskId'])
            try:
                stamp = datetime.fromisoformat(event['at'].replace('Z', '+00:00')).timestamp()
                last_work[sid] = max(last_work.get(sid, 0), stamp)
                stage_relation(sid, event['taskId'], event.get('stageId'), stamp)
            except (KeyError, ValueError, TypeError):
                pass
    catalog = dict(CATALOG.read_project(registry, project, registered, {}, include_archived=True)
                   if registry is not None else CATALOG.read(store.root, include_archived=True))
    selected = catalog.pop('registered', [s for s in registered if s['project'] == project])
    # Work stays related to its task after the chat moves to another project.
    selected_ids = {s['id'] for s in selected}
    selected.extend(dict(s, historical=True) for s in registered
                    if s['id'] in memberships and s['id'] not in selected_ids)
    from native_chats import normalize, linked
    resources = []
    if registry is not None:
        for place in {project} | (set().union(*locations.values()) if locations else set()):
            for resource in linked(registry, place):
                tid = resource['task']
                if (tid is None and place == project or
                        tid in tasks and place in locations.get(tid, ())):
                    resources.append(resource)
    native_ids = {r['resource'].get('nativeId') for r in resources
                  if r['resource']['client'].casefold() in ('codex', 'codex-desktop')}
    names = SESSION_TITLES.get(list({s['id'] for s in selected + catalog['sessions']} | set(memberships) | (native_ids - {None})))
    # A Hub actor can look like a UUID without being a native Codex chat.
    # Only the actual Codex catalog/title database supplies legacy provenance.
    native_codex_ids = {s['id'] for s in catalog['sessions']} | {sid for sid, title in names.items() if title is not None}
    rows = {s['id']: s for s in merge_sessions(catalog['sessions'], selected, names, set(), {})}
    for sid in memberships:
        rows.setdefault(sid, dict(id=sid, title=names.get(sid), historical=True, state='unknown'))
    for sid in native_codex_ids:
        if sid in rows and UUID.fullmatch(sid):
            rows[sid]['nativeChat'] = normalize(dict(client='codex', nativeId=sid), provenance='codex-catalog')
    def identity(resource):
        client = resource['client'].casefold()
        return (client, resource.get('clientInstance'), resource.get('host'),
                resource.get('nativeId') or resource.get('openUri'))

    native_rows = {identity(row['nativeChat']): sid for sid, row in rows.items() if row.get('nativeChat')}
    actor_targets = defaultdict(set)
    for resource in sorted(resources, key=lambda r: r['updated'], reverse=True):
        native = resource['resource']
        key = identity(native)
        sid = native_rows.get(key)
        if sid is None:
            # A real native ID can join a discovered conversation; an opaque
            # Hub actor or a coincidentally equal ID in another client cannot.
            sid = 'native:' + resource['resourceId']
            native_rows[key] = sid
        row = rows.setdefault(sid, dict(id=sid, title=None, state='unknown'))
        if not row.get('nativeChat'):
            row['nativeChat'] = native
        if not row.get('title'):
            row['title'] = names.get(native.get('nativeId')) if key[0] in ('codex', 'codex-desktop') else None
            row['title'] = row.get('title') or native.get('title')
        row['source'] = native['client']
        row['updatedAt'] = max(row.get('updatedAt') or 0, resource['updated'])
        actor_targets[resource['actor']].add(sid)
        tid = resource['task']
        if tid is not None:
            memberships[sid].add(tid)
            stage_relation(sid, tid, resource['stage'], resource['updated'])
    # Catalog discovery can omit a parent that moved; the recorded relation is
    # still sufficient to show a context row and an accurately labelled link.
    for sid, row in list(rows.items()):
        relation = relations.get(sid, {})
        for key, column in [('parentSession', 'parent'), ('agentPath', 'agent_path'), ('agentNickname', 'nickname'), ('agentRole', 'role')]:
            if not row.get(key) and relation.get(column):
                row[key] = relation[column]
    aliases = {actor: next(iter(targets)) for actor, targets in actor_targets.items()
               if len(targets) == 1 and (not rows.get(actor, {}).get('nativeChat') or
                   identity(rows[actor]['nativeChat']) == identity(rows[next(iter(targets))]['nativeChat']))}
    for actor, sid in aliases.items():
        row = rows[sid]
        row['hubActors'] = sorted(set(row.get('hubActors', [])) | {actor})
        if actor == sid:
            continue
        participant = rows.pop(actor, {})
        for key, value in participant.items():
            if key != 'id' and not row.get(key):
                row[key] = value
        for key in ('seen', 'updatedAt'):
            if participant.get(key):
                row[key] = max(row.get(key) or 0, participant[key])
        memberships[sid].update(memberships.pop(actor, set()))
        last_work[sid] = max(last_work.get(sid, 0), last_work.pop(actor, 0))
        for key, link in stage_links.pop(actor, {}).items():
            if link['lastRelatedAt'] >= stage_links[sid].get(key, {}).get('lastRelatedAt', 0):
                stage_links[sid][key] = link
    for sid, row in list(rows.items()):
        if sid in internal_actors and not memberships[sid] and not row.get('nativeChat'):
            del rows[sid]
            continue
        parent = aliases.get(row.get('parentSession'), row.get('parentSession'))
        row['parentSession'] = parent if parent != sid else None
        row['taskLinks'] = [dict(id=tid, title=tasks[tid]['title'], project=project) for tid in sorted(memberships[sid])]
        row['lastRelatedAt'] = last_work.get(sid)
        row['stageLinks'] = [stage_links[sid][key] for key in sorted(stage_links[sid])]
        row['kind'] = 'subagent' if row.get('parentSession') else 'agent'
        row['historical'] = bool(row.get('historical') or row.get('archived') or row.get('state') == 'closed')
        row['chatIdentity'] = 'reported' if row.get('nativeChat') else 'unreported'
    wanted = {sid for sid in rows if task is None or task in memberships[sid]}
    direct = set(wanted)
    for sid in list(wanted):
        chain = {sid}
        current = sid
        while rows[current].get('parentSession'):
            parent = rows[current]['parentSession']
            if parent in chain or len(chain) >= 32:
                rows[current]['parentSession'] = None
                break
            chain.add(parent)
            rows.setdefault(parent, dict(id=parent, title=names.get(parent), historical=True,
                                         kind='agent', state='unknown', taskLinks=[]))
            relation = relations.get(parent, {})
            if relation.get('parent'):
                rows[parent].setdefault('parentSession', relation['parent'])
            wanted.add(parent)
            current = parent
    groups = defaultdict(list)
    for sid in wanted:
        current, seen = sid, set()
        while rows[current].get('parentSession') in wanted and current not in seen:
            seen.add(current)
            current = rows[current]['parentSession']
        row = dict(rows[sid], contextOnly=sid not in direct, openSession=current)
        groups[current].append(row)
    for root, members in groups.items():
        links = {t['id']: t for s in members for t in s.get('taskLinks', [])}
        root_row = next(s for s in members if s['id'] == root)
        root_row['taskLinks'] = [links[tid] for tid in sorted(links)]
        root_row['lastActivityAt'] = max(max(s.get('lastRelatedAt') or 0, s.get('seen') or 0,
                                            s.get('updatedAt') or 0) for s in members)
    needle = query.strip().casefold()
    groups = {root: members for root, members in groups.items() if not needle or any(
        needle in str(value or '').casefold() for s in members
        for value in [s['id'], s.get('title'), s.get('agentNickname'), s.get('agentPath'),
                      *[t['title'] for t in s.get('taskLinks', [])], *[t['id'] for t in s.get('taskLinks', [])]])}
    ordered = sorted(groups, key=lambda root: (max(max(s.get('lastRelatedAt') or 0, s.get('seen') or 0,
                        s.get('updatedAt') or 0) for s in groups[root]), root), reverse=True)
    page = ordered[offset:offset + limit]
    return dict(available=True, sessions=[s for root in page for s in sorted(groups[root], key=lambda s: s['id'])],
                total=len(ordered), offset=offset, next=offset + limit if offset + limit < len(ordered) else None,
                task=task, discovery={k: v for k, v in catalog.items() if k != 'sessions'}, warnings=warnings,
                coverage=dict(tasks=len(tasks), tasksWithChats=len(set().union(*memberships.values())) if memberships else 0,
                              source='Сохраненные работы и явные авторы событий; тексты переписки не анализируются.'))
