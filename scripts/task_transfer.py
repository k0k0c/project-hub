"""Atomic task ownership overlay. Original journals and source paths stay intact."""
from contextlib import ExitStack, closing, contextmanager, nullcontext
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
import uuid

from project_portal import Store, now, user_history_events
from task_progress import project_progress
from request_metrics import measured_lock, timed


def setup(registry):
    with registry.connect() as c:
        c.executescript('''
            CREATE TABLE IF NOT EXISTS task_owners(
                uid TEXT PRIMARY KEY, origin TEXT NOT NULL, task TEXT NOT NULL, owner TEXT NOT NULL,
                UNIQUE(origin,task));
            CREATE TABLE IF NOT EXISTS task_transfers(
                request TEXT PRIMARY KEY, uid TEXT NOT NULL, source TEXT NOT NULL, target TEXT NOT NULL,
                at TEXT NOT NULL, actor TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS stage_transactions(
                id TEXT PRIMARY KEY, state TEXT NOT NULL CHECK(state IN ('pending','done')),
                at TEXT NOT NULL, body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS completion_checkpoints(
                id TEXT PRIMARY KEY, project TEXT NOT NULL, origin TEXT NOT NULL,
                task TEXT NOT NULL, stage TEXT, event TEXT NOT NULL,
                at TEXT NOT NULL, body TEXT NOT NULL, result TEXT NOT NULL);
        ''')


@contextmanager
def barrier(registry):
    if not getattr(registry.transfer_local, 'depth', 0):
        from storage_operations import ensure_writable
        ensure_writable(registry)
        from backup_session import active, BackupBusy
        from hub_lifecycle import draining
        if draining():
            raise BackupBusy('The server is switching storage; retry after it reconnects')
        if active(registry) is not None:
            raise BackupBusy('A backup snapshot is being copied; retry the change shortly')
    with measured_lock(registry.transfer_lock, 'ownership'):
        depth=getattr(registry.transfer_local,'depth',0)
        with ExitStack() as stack:
            if not depth:
                # The barrier owns only a data-home lock, not project/evidence
                # authority. Avoid constructing and resolving a full Store.
                stack.enter_context(Store.lock_probe(registry.home / '.local/project-portal/writer.lock').locked())
                # Admission can close while an earlier writer finishes. Recheck
                # only after taking its lock, before opening a write transaction.
                from storage_operations import ensure_writable
                ensure_writable(registry)
            registry.transfer_local.depth=depth+1
            try:
                if not depth:
                    from journal_append import recover
                    recover(registry)
                    from stage_operations import recover_stage_transfers
                    recover_stage_transfers(registry)
                yield
            finally:registry.transfer_local.depth=depth


def inventory(registry, *, copy_inputs=True, compact_events=False):
    """Caller holds barrier. Source journals are authoritative for task contents."""
    if getattr(registry, 'read_models', None) is not None:
        return registry.read_models.inventory(compact_events=compact_events)
    with registry.connect() as c:
        spaces=[r['id'] for r in c.execute('SELECT id FROM spaces')]
        known = {(row['origin'], row['task']) for row in c.execute('SELECT origin,task FROM task_owners')}
        snapshots={}
        for pid in spaces:
            store=registry.base_store(pid)
            seed,tasks,events = _origin_projection(registry, pid, store, copy_inputs=copy_inputs)
            snapshots[pid]=(seed,tasks,events)
            for task in tasks:
                if (pid, task['id']) in known:
                    continue
                uid=str(uuid.uuid5(uuid.NAMESPACE_URL, 'project-hub:'+pid+':'+task['id']))
                c.execute('INSERT OR IGNORE INTO task_owners VALUES(?,?,?,?)',(uid,pid,task['id'],pid))
        owners=[dict(r) for r in c.execute('SELECT * FROM task_owners')]
        transfers=[dict(r) for r in c.execute('SELECT rowid AS seq,* FROM task_transfers ORDER BY rowid')]
    return snapshots,owners,transfers


def _origin_signature(store, *, proven=None):
    """Content identity, also valid for write callers and restored timestamps."""
    models = getattr(getattr(store, 'registry', None), 'read_models', None)
    if models is not None:
        seed_proof,journal_proof = models.file_proofs(store.project_id) if proven is None else proven
        return (models.file_digests.digest(store.data / 'project.json',proven=seed_proof),
                models.file_digests.digest(store.journal,missing=True,proven=journal_proof))
    seed = hashlib.sha256((store.data / 'project.json').read_bytes()).digest()
    try:
        journal = hashlib.sha256(store.journal.read_bytes()).digest()
    except FileNotFoundError:
        journal = None
    return seed, journal


def _origin_projection(registry, project, store, *, copy_inputs=True, with_signature=False):
    # The existing ownership barrier serializes this registry-local LRU. Do not
    # retain caller-owned lists. Ordinary callers receive copies; the private
    # snapshot builder borrows inputs under the barrier and copies outputs.
    cache = getattr(registry, '_inventory_cache', None)
    if cache is None:
        cache = registry._inventory_cache = OrderedDict()
    with store.locked():
        before = _origin_signature(store)
        cached = cache.get(project)
        if cached is not None and cached[0] == before:
            cache.move_to_end(project)
            result = deepcopy(cached[1]) if copy_inputs else cached[1]
            return (*result, cached[0]) if with_signature else result
    # These methods acquire their own journal locks; never nest those locks.
    store._sync_git_commit_events(discover=False)
    store._sync_task_change_events()
    with store.locked():
        seed, events = store._load()
        loaded = store._loaded_signature
        tasks = store.project(seed, events, hierarchy=False)
        after = _origin_signature(store)
    result = seed, tasks, events
    cache.pop(project, None)
    # A migration or intervening writer changed input. Return the fresh result,
    # but let the next read run migrations over that exact content before caching.
    if before == after == loaded:
        cache[project] = loaded, deepcopy(result)
        while len(cache) > 16:
            cache.popitem(last=False)
    return (*result, loaded) if with_signature else result


def rewrite_sources(value, origin, owner):
    if isinstance(value,list):return [rewrite_sources(v,origin,owner) for v in value]
    if not isinstance(value,dict):return value
    result={k:rewrite_sources(v,origin,owner) for k,v in value.items()}
    origin=result.get('sourceProject',origin) if isinstance(result.get('path'),str) else origin
    if origin!=owner and isinstance(result.get('path'),str):
        result['path']='hub-source/'+origin+'/'+result['path']
    return result


def normalize_owner_graph(tasks, owners):
    """Decorate private owner inputs without changing origin journal rows."""
    current_ids = {task['id'] for task in tasks}
    locations = {(entry['origin'],entry['task']): entry['owner'] for entry in owners}
    for task in tasks:
        # Older moves can leave a parent in another owner's origin history.
        if task.get('parentTask') not in current_ids:
            task['parentTask'] = None
        for link in task.get('links', []):
            if link['target'] not in current_ids and not link.get('project'):
                target = locations.get((task['originProject'],link['target']))
                if target is not None:
                    link['project'] = target


def event_order(event):
    """Order instants consistently across both projections, retaining stable ties."""
    try:
        instant = datetime.fromisoformat(event['at'].replace('Z', '+00:00'))
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        instant = instant.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError, OverflowError):
        instant = datetime.min.replace(tzinfo=timezone.utc)
    return instant, event.get('originProject', '~'), event.get('seq', 0), event['id']


class ProjectView(Store):
    def __init__(self, registry, project):
        base=registry.base_store(project)
        # base_store just resolved these paths for this new request view.
        # Copy its fresh static context instead of canonicalizing it twice.
        self.__dict__.update(base.__dict__)
        self.registry,self.project_id=registry,project
        self.display_name=base.display_name

    def memory_snapshot(self):
        """Fresh task contracts without optional host/session discovery."""
        return self.snapshot(observations=False)

    def memory_tasks(self):
        return self.registry.read_models.snapshot(self, observations=False, tasks_only=True)

    @timed('write_inputs')
    def write_context(self, *, task=None):
        """Current validation inputs, independent of prepared display pages."""
        with barrier(self.registry):
            tasks = self.registry.read_models.raw_tasks(self.project_id, graph_task=task)
            with self.registry.connect() as c:
                owners = [dict(r) for r in c.execute('SELECT * FROM task_owners')]
                moved = c.execute('''SELECT o.task,o.owner,o.uid FROM task_owners o
                    WHERE o.owner<>? AND (o.origin=? OR EXISTS (
                        SELECT 1 FROM task_transfers tr WHERE tr.uid=o.uid AND tr.source=?))''',
                                  (self.project_id,self.project_id,self.project_id)).fetchall()
            normalize_owner_graph(tasks,owners)
            # Indexed tasks already carry validated defaults. Write callers
            # need raw owner inputs; record validates the resulting graph.
            return dict(tasks=tasks, revision=self.registry.read_models.domain_key(self.project_id),
                        redirects={r['task']: dict(project=r['owner'],task=r['task'],uid=r['uid']) for r in moved})

    def event_exists(self, identifier):
        return self.registry.read_models.event_exists(self.project_id, identifier)

    def task_context(self, task):
        try:
            detail = self.registry.read_models.snapshot(self, observations=False, task=task)
        except KeyError:
            state = self.registry.read_models.snapshot(self, observations=False, summary=True)
            return dict(revision=state['revision'], tasks=[], allEvents=[], mainTask=state['mainTask'])
        return dict(revision=detail['revision'], tasks=[detail['task']], allEvents=[], mainTask=detail['mainTask'])

    def snapshot(self, *, observations=True):
        return self.registry.read_models.snapshot(self, observations=observations)

    def _build_snapshot(self, *, observations=True, compact_events=False, serialized=True):
        with barrier(self.registry) if serialized else nullcontext():
            # Borrow cache inputs only under the barrier. Every exposed task,
            # event and project value below is copied before decoration.
            snapshots,owners,transfers=inventory(self.registry, copy_inputs=False, compact_events=compact_events)
            if compact_events:
                with self.registry.connect() as c:
                    source_revisions = dict(c.execute('SELECT project,journal_seq FROM read_model_heads'))
            source_tasks_by_id = {pid: {task['id']: task for task in source_tasks}
                                  for pid, (_, source_tasks, _) in snapshots.items()}
            source_events_by_task = {}
            for pid, (_, _, source_events) in snapshots.items():
                grouped = source_events_by_task[pid] = {}
                for event in source_events:
                    grouped.setdefault(event['taskId'], []).append(event)
            tasks,events=[],[]
            for entry in owners:
                if entry['owner']!=self.project_id:continue
                source_events=snapshots[entry['origin']][2]
                if entry['task'] not in source_tasks_by_id[entry['origin']]:
                    continue  # A restored origin can predate this durable UID.
                task=source_tasks_by_id[entry['origin']][entry['task']]
                task=rewrite_sources(task,entry['origin'],self.project_id)
                task['uid']=entry['uid'];task['originProject']=entry['origin']
                task['_sourceRevision']=source_revisions[entry['origin']] if compact_events else len(source_events)
                tasks.append(task)
                events.extend(dict(rewrite_sources(e,entry['origin'],self.project_id),originProject=entry['origin'])
                              for e in source_events_by_task[entry['origin']].get(entry['task'], []))
            normalize_owner_graph(tasks,owners)
            tasks = Store.project({'tasks': tasks}, [])
            events.extend(dict(event, originProject=self.project_id)
                          for event in snapshots[self.project_id][2]
                          if event['taskId'] == '__project__' and event['kind'] == 'git.push')
            for transfer in transfers:
                entry=next(o for o in owners if o['uid']==transfer['uid'])
                if self.project_id not in (transfer['source'],transfer['target'],entry['owner']):continue
                events.append(dict(id=transfer['request'],kind='task.transferred',taskId=entry['task'],at=transfer['at'],
                    title='Задача перенесена',detail=self.registry.base_store(transfer['source']).display_name+' → '+self.registry.base_store(transfer['target']).display_name,
                    sourceProject=transfer['source'],targetProject=transfer['target'],actor=transfer['actor'],schemaVersion=1,seq=transfer['seq']))
            events.sort(key=event_order)
            visible_events = user_history_events(events)
            for task in tasks:
                task['participatingSessions'] = []
            database=self.registry.home/'coordination/coordination.sqlite3'
            if database.exists():
                with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)) as c:
                    for task in tasks:
                        locations={task['originProject'],self.project_id}
                        for move in transfers:
                            if move['uid']==task['uid']:locations.update((move['source'],move['target']))
                        slots=','.join('?' for _ in locations)
                        task['participatingSessions']=[r[0] for r in c.execute(
                            f'SELECT DISTINCT session FROM work WHERE project IN ({slots}) AND task=? ORDER BY session',
                            (*sorted(locations),task['id']))]
            for index,event in enumerate(events,1):
                event['originSeq']=event.get('seq');event['seq']=index
            seed=snapshots[self.project_id][0]
            project=deepcopy({k:v for k,v in seed.items() if k!='tasks'})
            project['name']=self.display_name
            redirects={}
            for entry in owners:
                seen=entry['origin']==self.project_id or any(t['uid']==entry['uid'] and t['source']==self.project_id for t in transfers)
                if seen and entry['owner']!=self.project_id:
                    redirects[entry['task']]=dict(project=entry['owner'],task=entry['task'],uid=entry['uid'])
            from completion_policy import project_checkpoints
            from project_settings import read_settings
            project_checkpoints(self.registry, self.project_id, tasks, events)
            revision=self.registry.read_models.domain_key(self.project_id)
            primary_events = [dict(e, originProject=pid) for pid, (_, _, source_events) in snapshots.items() for e in source_events]
            for move in transfers:
                entry = next(o for o in owners if o['uid'] == move['uid'])
                primary_events.append(dict(kind='task.transferred',taskId=entry['task'],originProject=entry['origin'],
                                           at=move['at'],seq=move['seq'],id=move['request']))
            legacy_work = {task['id']:deepcopy(task['currentWork']) for task in tasks if 'currentWork' in task}
            main_task = project_progress(tasks, events, self.project_id, database, primary_events)
            from check_runs import project_runs
            runs = project_runs(events, self.project_id)
            result = dict(project=project,tasks=tasks,revision=revision,mainTask=main_task,events=list(reversed(visible_events[-24:])),
                        allEvents=events,eventCount=len(visible_events),lastEventAt=events[-1]['at'] if events else None,
                        checks=runs[:30],checkCount=len(runs),serverTime=now(),
                        redirects=redirects,
                        settings=read_settings(self.registry.base_store(self.project_id)))
            if compact_events:
                models = self.registry.read_models
                result['_progressInputs'] = models.progress_inputs(events, primary_events, legacy_work)
                result['events'] = models.history(self.project_id, limit=24)['events']
                result['eventCount'] = models.history_count(self.project_id)
                latest = models.history(self.project_id, limit=1, visible=False)['events']
                result['lastEventAt'] = latest[0]['at'] if latest else None
        # Optional host discovery can spawn Git for unrelated worktrees. It is
        # observational, and must never hold the task ownership/write barrier.
        if observations:
            result['coordination'] = self.diagnostics()
        return result

    def history(self, task_id=None, before=None, limit=40, kind=None):
        return self.registry.read_models.history(self.project_id, task_id, before, limit, kind)

    def _legacy_history(self, task_id=None, before=None, limit=40, kind=None):
        # History does not need the full snapshot projection.  In particular,
        # diagnostics and project progress can be expensive on a cold read,
        # while the event list only needs ownership and source-journal data.
        with barrier(self.registry):
            snapshots, owners, transfers = inventory(self.registry)
            events=[]
            for entry in owners:
                if entry['owner'] != self.project_id:
                    continue
                _, _, source_events = snapshots[entry['origin']]
                events.extend(
                    dict(rewrite_sources(event, entry['origin'], self.project_id),
                         originProject=entry['origin'])
                    for event in source_events
                    if event['taskId'] == entry['task']
                )
            events.extend(dict(event, originProject=self.project_id)
                          for event in snapshots[self.project_id][2]
                          if event['taskId'] == '__project__' and event['kind'] == 'git.push')
            for transfer in transfers:
                entry = next(o for o in owners if o['uid'] == transfer['uid'])
                if self.project_id not in (transfer['source'], transfer['target'], entry['owner']):
                    continue
                events.append(dict(
                    id=transfer['request'], kind='task.transferred', taskId=entry['task'],
                    at=transfer['at'], title='Задача перенесена',
                    detail=self.registry.base_store(transfer['source']).display_name +
                          ' → ' + self.registry.base_store(transfer['target']).display_name,
                    sourceProject=transfer['source'], targetProject=transfer['target'],
                    actor=transfer['actor'], schemaVersion=1, seq=transfer['seq']))
            events.sort(key=event_order)
            for index, event in enumerate(events, 1):
                event['originSeq'] = event.get('seq')
                event['seq'] = index
        events=[e for e in reversed(user_history_events(events)) if (not task_id or e['taskId']==task_id)
                and (before is None or e['seq']<before) and (not kind or e['kind'].startswith(kind))]
        page=events[:limit]
        return dict(events=page,next=page[-1]['seq'] if len(events)>limit else None)

    def evidence_origin(self, relative):
        models = getattr(self.registry, 'read_models', None)
        if models is not None:
            return models.evidence_origin(self.project_id, relative)
        allowed={}
        def collect(v,origin):
            if isinstance(v,dict):
                if isinstance(v.get('path'),str):
                    path=v['path']
                    source=v.get('sourceProject',origin)
                    visible=path if source==self.project_id else 'hub-source/'+source+'/'+path
                    target=(source,path)
                    if visible in allowed and allowed[visible]!=target:raise ValueError('Ambiguous evidence reference')
                    allowed[visible]=target
                for value in v.values():collect(value,origin)
            elif isinstance(v,list):
                for value in v:collect(value,origin)
        with barrier(self.registry):
            snapshots,owners,_=inventory(self.registry)
            collect({k:v for k,v in snapshots[self.project_id][0].items() if k!='tasks'},self.project_id)
            for entry in owners:
                if entry['owner']!=self.project_id:continue
                _,tasks,events=snapshots[entry['origin']]
                collect([t for t in tasks if t['id']==entry['task']],entry['origin'])
                collect([e for e in events if e['taskId']==entry['task']],entry['origin'])
        if relative not in allowed:raise ValueError('File is not evidence of this project')
        origin,path=allowed[relative]
        store=self.registry.base_store(origin)
        store.project_id=origin
        return store,path

    @timed('owner_record')
    def record(self, payload, expected_revision=None):
        self.write_receipt = None
        # Used by the forthcoming server write API. Legacy direct writers are not enrolled.
        with barrier(self.registry):
            primary = payload.get('patch', {}).get('primary')
            if isinstance(primary, dict) and primary.get('project') != self.project_id:
                raise ValueError('Primary selection must belong to current project')
            state=self.write_context(task=payload['taskId'])
            retry=payload.get('id') and self.event_exists(payload['id'])
            if not retry and expected_revision is not None and state['revision']!=expected_revision:
                raise ValueError('Task changed; refresh before writing')
            if payload['taskId'] == '__project__' and payload['kind'] == 'git.push':
                return self.registry.base_store(self.project_id).record(
                    payload, hierarchy_tasks=state['tasks'])
            task=next((t for t in state['tasks'] if t['id']==payload['taskId']),None)
            if not task:
                if payload['kind']!='task.created' or payload['taskId'] in state['redirects']:
                    raise ValueError('Task moved or does not belong to this project')
                origin=self.project_id
            else:origin=task['originProject']
            def bind_sources(value):
                if isinstance(value,list):return [bind_sources(v) for v in value]
                if not isinstance(value,dict):return value
                result={k:(v if k == 'check' else bind_sources(v)) for k,v in value.items()}
                if isinstance(result.get('path'),str):
                    source=result.get('sourceProject',self.project_id)
                    if (not isinstance(source, str) or not source or source != source.strip() or
                            len(source)>128 or any(ord(char)<32 for char in source)):
                        raise ValueError('Invalid evidence source project')
                    if result['path'].startswith('hub-source/'):
                        evidence_store, relative = self.evidence_origin(result['path'])
                        if 'sourceProject' in result and source != evidence_store.project_id:
                            raise ValueError('Evidence source conflicts with its projected path')
                        source, result['path'] = evidence_store.project_id, relative
                    if source not in (origin,self.project_id):
                        self.evidence_origin('hub-source/' + source + '/' + result['path'])
                    if result['path'].startswith('knowledge/'):
                        from knowledge_store import KnowledgeStore
                        import re
                        match=re.fullmatch(r'knowledge/(?:(?:revision/([0-9]+)/))?document/(.+)',result['path'])
                        if not match: raise ValueError('Invalid knowledge document source')
                        document=KnowledgeStore(self.registry,source).read(match[2],int(match[1]) if match[1] else None)
                        if document['kind']!='document': raise ValueError('Knowledge source must reference a document')
                    else:
                        self.registry.base_store(source).resolve_path(result['path'])
                    if source != origin or 'sourceProject' in result or origin != self.project_id:
                        result['sourceProject']=source
                return result
            # Notes with explicit provenance need the same ownership check.
            # Keep legacy literal relative paths as originally recorded.
            if (origin != self.project_id or
                    payload['kind'] in ('task.created', 'task.updated', 'stage.created', 'stage.updated') or
                    any(isinstance(value, dict) and 'sourceProject' in value
                        for value in payload.get('evidence', []))):
                payload=bind_sources(payload)
            from completion_policy import prepare_checkpoint, schedule_checkpoint
            payload = dict(payload)
            payload.setdefault('id', 'hub-event-' + uuid.uuid4().hex)
            checkpoint = prepare_checkpoint(self.registry, self.project_id, origin, task, payload, retry)
            origin_store = self.registry.base_store(origin)
            result = origin_store.record(payload, hierarchy_tasks=state['tasks'])
            if checkpoint:
                schedule_checkpoint(self.registry, checkpoint)
            elif origin_store.write_receipt is not None and origin_store.write_receipt['project'] == self.project_id:
                self.write_receipt = origin_store.write_receipt
            return result


def transfer(registry, source, target, task_id, expected=None, request=None, actor='local-user', preview=False):
    if source==target:raise ValueError('Choose a different destination')
    if not isinstance(actor,str) or not actor.strip() or len(actor)>120:raise ValueError('Invalid actor')
    registry.base_store(target)  # Validate destination before beginning.
    with barrier(registry):
        with registry.connect() as c:
            if request:
                old=c.execute('SELECT * FROM task_transfers WHERE request=?',(request,)).fetchone()
                if old:
                    body=json.loads(old['body'])
                    if [source,target,task_id,expected,actor]!=body['input']:raise ValueError('Request ID reused with different input')
                    return body['result']
            state=registry.store(source).snapshot()
            task=next((t for t in state['tasks'] if t['id']==task_id),None)
            if not task:raise ValueError('Task moved or was not found')
            destination=registry.store(target).snapshot()
            alias=destination['redirects'].get(task_id)
            if any(t['id']==task_id for t in destination['tasks']) or (alias and alias['uid']!=task['uid']):
                raise ValueError('Destination already has a task or historical link with this ID')
            if expected is not None and state['revision']!=expected:raise ValueError('Task changed; preview again')
            if task.get('parentTask') or task.get('children'):
                raise ValueError('Unlink task parent and children before transferring')
            with ExitStack() as locks:
                # Source journal and coordination lock close races with existing local writers.
                base=registry.base_store(task['originProject'])
                locks.enter_context(base.locked())
                seed, origin_events = base._load()
                if len(origin_events)!=task['_sourceRevision']:
                    raise ValueError('Source changed; preview again')
                origin_tasks = base.project(seed, origin_events, hierarchy=False)
                original = next(item for item in origin_tasks if item['id'] == task_id)
                if original.get('parentTask') or any(item.get('parentTask') == task_id for item in origin_tasks):
                    raise ValueError('Unlink historical task parent and children before transferring')
                database=registry.home/'coordination/coordination.sqlite3'
                if database.exists():
                    coordination=locks.enter_context(closing(sqlite3.connect(database,timeout=5)))
                    coordination.execute('BEGIN IMMEDIATE')
                    for pending in coordination.execute('SELECT payload FROM plan_outbox WHERE project IN (?,?)',(source,task['originProject'])):
                        if json.loads(pending[0]).get('taskId')==task_id:
                            raise ValueError('Task has pending reports; finish journal delivery first')
                    if coordination.execute("SELECT 1 FROM work WHERE project IN (?,?) AND task=? AND status IN ('active','waiting') LIMIT 1",
                                            (source,task['originProject'],task_id)).fetchone():
                        raise ValueError('Task has active work or reservations; prepare a checkpoint first')
                if task.get('currentWork'):raise ValueError('Task has an unfinished work step')
                runs={}
                for e in state['allEvents']:
                    if e['taskId']==task_id and e['kind'].startswith('check.'):
                        runs[e.get('runId',e['id'])]=e['kind']
                if 'check.started' in runs.values():raise ValueError('Task has an unfinished check')
                result=dict(uid=task['uid'],task=task_id,source=source,target=target,revision=state['revision'],
                            title=task['title'],stages=len(task['stages']),events=sum(e['taskId']==task_id for e in state['allEvents']),
                            sourceFilesProject=task['originProject'],chatsMoved=False)
                if preview:return result
                if not isinstance(request,str) or not 1<=len(request)<=100 or expected is None:raise ValueError('Preview revision and request ID required')
                c.execute('BEGIN IMMEDIATE')
                try:
                    c.execute('UPDATE task_owners SET owner=? WHERE uid=? AND owner=?',(target,task['uid'],source))
                    c.execute('INSERT INTO task_transfers VALUES(?,?,?,?,?,?,?)',
                              (request,task['uid'],source,target,now(),actor,json.dumps(dict(input=[source,target,task_id,expected,actor],result=result))))
                    c.commit()
                except BaseException:c.rollback();raise
                return result
