"""Rebuildable journal projections in the existing registry database.

Journals remain authoritative during the transition. A completed index names
the exact input digests; mismatches rebuild under the existing writer protocol.
Readers borrow no mutable projections and source access always joins current
ownership, including after a transfer in another process.
"""
import hashlib
import json
import uuid
import sqlite3
import threading
import time
import zlib
from contextlib import closing, nullcontext, contextmanager
from collections import OrderedDict

from request_metrics import measure, measured_lock, timed


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), sort_keys=True)


VIEW_BLOB = b'HubView1\x00'
VIEW_LIMIT = 64 * 1024 * 1024


def pack_view(value):
    """Reduce derived-page WAL writes; legacy/small TEXT stays readable."""
    raw = value.encode('utf-8')
    if len(raw) < 4096 or len(raw) > VIEW_LIMIT:
        return value
    compressed = VIEW_BLOB + zlib.compress(raw, 1)
    return compressed if len(compressed) < len(raw) * .9 else value


def unpack_view(value):
    if isinstance(value, str):
        return value
    if not isinstance(value, bytes) or not value.startswith(VIEW_BLOB):
        raise ValueError('Invalid prepared view encoding')
    decoder = zlib.decompressobj()
    try:
        raw = decoder.decompress(value[len(VIEW_BLOB):], VIEW_LIMIT + 1)
    except zlib.error as error:
        raise ValueError('Invalid prepared view compression') from error
    if len(raw) > VIEW_LIMIT or not decoder.eof or decoder.unused_data:
        raise ValueError('Invalid or oversized prepared view')
    return raw.decode('utf-8')


def sources(value, origin):
    """Retain historical registrations, with their original provenance."""
    found = set()
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if isinstance(item.get('path'), str):
                source = item.get('sourceProject', origin)
                if not isinstance(source, str):
                    raise ValueError('Invalid evidence source project')
                found.add((source, item['path']))
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return found


class ReadModels:
    VERSION = 4
    # Page compatibility is independent of the journal/event index. Older
    # summaries omit pending-stage IDs and must be prepared once on upgrade.
    VIEW_VERSION = 5

    @staticmethod
    def event_metadata(event):
        if event['kind'].startswith('check.') or event['kind'] == 'git.push':
            return event
        result = {key: event[key] for key in ('id','kind','taskId','stageId','at','seq','schemaVersion') if key in event}
        if event.get('patch'):
            result['patch'] = {key: value if key in ('primary','status') else None
                               for key, value in event['patch'].items()}
        result['_compactEvent'] = True
        return result

    def __init__(self, registry):
        self.registry = registry
        self.lock = threading.RLock()
        self.views = OrderedDict()
        self.append_pages = OrderedDict()
        self.domain_keys = OrderedDict()
        self.build_locks = {}
        self.process_build_locks = {}
        self.projection_local = threading.local()
        self.history_pages = OrderedDict()
        self.history_locks = [threading.Lock() for _ in range(64)]
        from file_freshness import FileDigests
        self.file_digests = FileDigests()
        from backup_session import active
        if active(registry) is not None:
            return
        from journal_append import setup
        setup(registry)
        with registry.connect() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS read_model_heads(
                    project TEXT PRIMARY KEY, version INTEGER NOT NULL,
                    seed_hash BLOB NOT NULL, journal_hash BLOB,
                    journal_seq INTEGER NOT NULL, project_body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS read_model_file_proofs(
                    project TEXT PRIMARY KEY,seed_hash BLOB NOT NULL,seed_token TEXT,
                    journal_hash BLOB,journal_token TEXT);
                CREATE TABLE IF NOT EXISTS read_model_tasks(
                    project TEXT NOT NULL, task TEXT NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(project,task));
                CREATE TABLE IF NOT EXISTS read_model_task_graph(
                    project TEXT NOT NULL, task TEXT NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(project,task));
                CREATE TABLE IF NOT EXISTS read_model_events(
                    project TEXT NOT NULL, seq INTEGER NOT NULL, id TEXT NOT NULL,
                    task TEXT NOT NULL, kind TEXT NOT NULL, instant TEXT NOT NULL,
                    visible INTEGER NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(project,seq), UNIQUE(project,id));
                CREATE INDEX IF NOT EXISTS read_events_task
                    ON read_model_events(project,task,seq);
                CREATE INDEX IF NOT EXISTS read_events_id ON read_model_events(id,project);
                CREATE INDEX IF NOT EXISTS read_events_history
                    ON read_model_events(project,instant,seq,id,task,kind,visible);
                CREATE INDEX IF NOT EXISTS read_events_owner
                    ON read_model_events(project,task,instant,seq,id,kind,visible);
                CREATE INDEX IF NOT EXISTS read_owners_current ON task_owners(owner,origin,task);
                CREATE INDEX IF NOT EXISTS read_owners_origin ON task_owners(origin,task,owner);
                CREATE TABLE IF NOT EXISTS read_model_event_metadata(
                    project TEXT NOT NULL, seq INTEGER NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(project,seq));
                CREATE TABLE IF NOT EXISTS read_model_sources(
                    origin TEXT NOT NULL, task TEXT NOT NULL, source TEXT NOT NULL,
                    path TEXT NOT NULL, PRIMARY KEY(origin,task,source,path));
                CREATE INDEX IF NOT EXISTS read_sources_path
                    ON read_model_sources(source,path,origin,task);
                CREATE TABLE IF NOT EXISTS read_model_views(
                    project TEXT PRIMARY KEY, input_key TEXT NOT NULL,
                    body TEXT NOT NULL, summary TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS read_model_hints(
                    project TEXT PRIMARY KEY, input_key TEXT NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS read_model_details(
                    project TEXT NOT NULL, task TEXT NOT NULL, body TEXT NOT NULL,
                    PRIMARY KEY(project,task));
                CREATE TABLE IF NOT EXISTS read_model_view_cursors(
                    project TEXT PRIMARY KEY,input_key TEXT NOT NULL,latest TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS read_model_changes(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL,
                    journal_seq INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS read_model_generation(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    generation INTEGER NOT NULL);
                INSERT OR IGNORE INTO read_model_generation VALUES(1,0);
            ''')
            # Every dependency mutation invalidates readers in other processes,
            # including direct SQL and recovery. The increment rolls back with
            # its mutation; cache keys never depend on an in-memory notifier.
            for table in ('read_model_heads', 'task_owners', 'task_transfers',
                          'completion_checkpoints'):
                for action in ('INSERT', 'UPDATE', 'DELETE'):
                    c.execute(f'''CREATE TRIGGER IF NOT EXISTS read_generation_{table}_{action}
                        AFTER {action} ON {table} BEGIN
                        UPDATE read_model_generation SET generation=generation+1 WHERE singleton=1;
                        END''')

    def ensure_origin(self, project):
        if not getattr(self.registry.transfer_local, 'depth', 0):
            from backup_session import active
            if active(self.registry) is not None:
                return
        from task_transfer import barrier, _origin_projection, _origin_signature
        store = self.registry.origin_files(project)
        captured = None
        if not getattr(self.registry.transfer_local, 'depth', 0):
            stage_pending, pending, visibility, row, proof = self.pending_visibility(project, store, capture=True)
            if visibility is True:
                return
            if stage_pending or pending is not None:
                with barrier(self.registry):
                    pass  # Recover a committed intent before lending a prepared view.
            else:
                captured = row, self.head_proofs(row, proof)
        else:
            # Already serialized writers need no intent visibility probe. Read
            # the head and its file proofs from one SQLite snapshot instead of
            # repeatedly leasing connections for the same freshness check.
            with self.registry.connect() as c:
                c.execute('BEGIN')
                row = c.execute('SELECT * FROM read_model_heads WHERE project=?', (project,)).fetchone()
                proof = c.execute('SELECT * FROM read_model_file_proofs WHERE project=?', (project,)).fetchone()
                c.commit()
            captured = row, self.head_proofs(row, proof)
        with measure('index_freshness'):
            if captured is not None:
                row, proven = captured
                if not getattr(self.registry.transfer_local, 'depth', 0):
                    # File tokens can overtake the SQL snapshot during an
                    # ordinary append. A changed token is not yet an unmanaged
                    # edit: recheck its publication before hashing the journal.
                    seed = self.file_digests.reuse(store.data / 'project.json', proven=proven[0])
                    journal = self.file_digests.reuse(store.journal, missing=True, proven=proven[1])
                    signature = (seed[1], journal[1]) if seed[0] and journal[0] else None
                else:
                    signature = _origin_signature(store, proven=proven)
            else:
                signature = _origin_signature(store)
                with self.registry.connect() as c:
                    row = c.execute('SELECT * FROM read_model_heads WHERE project=?', (project,)).fetchone()
            if (row is not None and row['version'] == self.VERSION and
                    (row['seed_hash'], row['journal_hash']) == signature):
                return
        if not getattr(self.registry.transfer_local, 'depth', 0):
            # A writer can create its intent after the first SQL snapshot and
            # before the file opens above. Recheck that visibility point before
            # joining recovery; otherwise ordinary reads queue as writers.
            import errno
            probe = store.writer_probe()
            deadline = time.monotonic() + .25
            while True:
                stage_pending, pending, visibility = self.pending_visibility(project, store)
                if visibility is True:
                    return
                if stage_pending or pending is not None:
                    break
                # A completed publisher may have overtaken the file read. A
                # short origin lock makes this final comparison linearizable
                # without moving normal readers into the global writer queue.
                try:
                    with probe.locked(label='fresh_head', timeout=0):
                        with measure('index_freshness'):
                            signature = _origin_signature(store)
                            with self.registry.connect() as c:
                                row = c.execute('SELECT * FROM read_model_heads WHERE project=?', (project,)).fetchone()
                            if (row is not None and row['version'] == self.VERSION and
                                    (row['seed_hash'], row['journal_hash']) == signature):
                                return
                        break  # Unmanaged change or missing head needs recovery.
                except TimeoutError as error:
                    cause = error.__cause__
                    if not isinstance(cause, OSError) or cause.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                if time.monotonic() >= deadline:
                    break
                with measure('append_proof_wait'):
                    time.sleep(.005)
        with barrier(self.registry):
            # A competing reader may already have published the new head.
            signature = _origin_signature(store)
            with self.registry.connect() as c:
                row = c.execute('SELECT * FROM read_model_heads WHERE project=?', (project,)).fetchone()
            if (row is not None and row['version'] == self.VERSION and
                    (row['seed_hash'], row['journal_hash']) == signature):
                return
            with measure('index_rebuild'):
                for attempt in range(3):
                    seed, tasks, events, loaded = _origin_projection(
                        self.registry, project, self.registry.base_store(project),
                        copy_inputs=False, with_signature=True)
                    if loaded == _origin_signature(store):
                        self.publish(project, seed, tasks, events, loaded)
                        return
            raise ValueError('Journal changed during index rebuild; retry the read')

    def pending_visibility(self, project, store, *, capture=False):
        deadline = time.monotonic() + .25
        retries = 0
        while True:
            head = proof = appended = None
            with measure('append_visibility'):
                with self.registry.connect() as c:
                    c.execute('BEGIN')
                    stage_pending = c.execute("SELECT 1 FROM stage_transactions WHERE state='pending' LIMIT 1").fetchone()
                    pending = c.execute('SELECT * FROM journal_append_intents WHERE project=?',(project,)).fetchone()
                    if capture or (pending is not None and not stage_pending):
                        head = c.execute('SELECT * FROM read_model_heads WHERE project=?',(project,)).fetchone()
                        proof = c.execute('SELECT * FROM read_model_file_proofs WHERE project=?',(project,)).fetchone()
                    if pending is not None and not stage_pending:
                        appended = c.execute('SELECT * FROM journal_append_proofs WHERE project=?',(project,)).fetchone()
                    c.commit()
                visibility = (self._committed_append_read(store,pending,head,proof,appended)
                              if not stage_pending and pending is not None else False)
            if pending is not None and not stage_pending and visibility is False and retries < 2:
                # The writer can finish between the SQL snapshot and the lock
                # probe. A stale intent must not turn that completed publication
                # into a recovery writer. Recheck the durable marker, rather
                # than assuming a free lock proves the old snapshot is current.
                with self.registry.connect() as c:
                    current = c.execute('SELECT event FROM journal_append_intents WHERE project=?', (project,)).fetchone()
                if current is None or current['event'] != pending['event']:
                    retries += 1
                    continue
            if visibility is not None or time.monotonic() >= deadline:
                result = stage_pending, pending, visibility
                return (*result, head, proof) if capture else result
            # Wait only for an active writer's proof, outside ownership. Exact
            # pre/post file proofs still govern lending the completed SQL head.
            with measure('append_proof_wait'):
                time.sleep(.005)

    def _committed_append_read(self, store, pending, head, proof, appended):
        """Lend the completed SQL version while its managed successor is written.

        A busy origin writer lock and verified file tokens name the visibility point.
        A crashed writer has no lock and must recover before lending a view.
        Transfers use their separate pending protocol and never take this path.
        """
        if (head is None or head['version'] != self.VERSION or
                (head['seed_hash'],head['journal_hash']) != (pending['seed_hash'],pending['before_hash'])):
            return False
        from file_freshness import token
        import errno
        # A fresh Store has an independent uncontended thread lock and no
        # registry outer barrier; probe only this origin's operating-system lock.
        probe = store.writer_probe()
        try:
            with probe.locked(label='writer_probe',timeout=0):
                return False
        except TimeoutError as error:
            cause = error.__cause__
            if not isinstance(cause,OSError) or cause.errno not in (errno.EACCES,errno.EAGAIN):
                raise
        if (proof is None or (proof['seed_hash'],proof['journal_hash']) !=
                (head['seed_hash'],head['journal_hash'])):
            return False
        seed_proof = (json.loads(proof['seed_token']),proof['seed_hash']) if proof['seed_token'] is not None else None
        if self.file_digests.digest(store.data/'project.json',proven=seed_proof) != pending['seed_hash']:
            return False
        try:
            with store.journal.open('rb') as stream:
                current = token(stream)
            with store.journal.open('rb') as stream:
                if current is None:
                    return False
                if current != token(stream):
                    # The active managed writer can still be closing/fsyncing
                    # its suffix. Await its exact proof; never lend changing
                    # bytes and never promote this observation to recovery yet.
                    return None
        except FileNotFoundError:
            return pending['before_hash'] is None
        prior_token = json.loads(proof['journal_token']) if proof['journal_token'] is not None else None
        if prior_token is not None and tuple(prior_token) == current:
            return True
        if appended is None and prior_token is not None:
            return None  # Active origin writer has not published its proof yet.
        return (appended is not None and appended['event'] == pending['event'] and
                appended['journal_token'] is not None and
                tuple(json.loads(appended['journal_token'])) == current and
                (not pending['after_hash'] or appended['after_hash'] == pending['after_hash']))

    @staticmethod
    def head_proofs(head, proof):
        if (head is None or proof is None or
                (proof['seed_hash'], proof['journal_hash']) != (head['seed_hash'], head['journal_hash'])):
            return None, None
        return tuple((json.loads(proof[name+'_token']),proof[name+'_hash']) if proof[name+'_token'] is not None else None
                     for name in ('seed','journal'))

    def file_proofs(self, project):
        with self.registry.connect() as c:
            row = c.execute('SELECT p.* FROM read_model_file_proofs p JOIN read_model_heads h USING(project) '
                            'WHERE p.project=? AND p.seed_hash=h.seed_hash AND p.journal_hash IS h.journal_hash',
                            (project,)).fetchone()
        if row is None:
            return None,None
        return tuple((json.loads(row[name+'_token']),row[name+'_hash']) if row[name+'_token'] is not None else None
                     for name in ('seed','journal'))

    def captured_file_proofs(self, project, signature):
        store = self.registry.origin_files(project)
        paths = store.data/'project.json',store.journal
        with self.file_digests.lock:
            known = [self.file_digests.entries.get(path) for path in paths]
            if all(proof is not None and proof[1] == value for proof,value in zip(known,signature)):
                # These exact digests/tokens were checked by the caller's fresh
                # file validation. SQL fallback is only needed after eviction
                # or restart; do not repeatedly read the prior head's proof.
                return project,signature[0],encode(known[0][0]),signature[1],encode(known[1][0])
        persisted = self.file_proofs(project)
        proofs = []
        with self.file_digests.lock:
            for path,value,old in zip(paths,signature,persisted):
                known = self.file_digests.entries.get(path) or old
                proofs.append(encode(known[0]) if known is not None and known[1] == value else None)
        return project,signature[0],proofs[0],signature[1],proofs[1]

    def ensure(self, owner):
        if getattr(self.projection_local,'revision',None) is not None:
            return
        self.ensure_origin(owner)
        with self.registry.connect() as c:
            origins = [r[0] for r in c.execute(
                'SELECT DISTINCT origin FROM task_owners WHERE owner=? AND origin<>?', (owner, owner))]
        for origin in origins:
            self.ensure_origin(origin)

    def publish(self, project, seed, tasks, events, signature, *, consume_intent=None,
                require_migrations=False):
        from project_portal import user_history_events
        from task_transfer import event_order
        registrations = set()
        for source, path in sources({k: v for k, v in seed.items() if k != 'tasks'}, project):
            registrations.add((project, '', source, path))
        for task in tasks:
            for source, path in sources(task, project):
                registrations.add((project, task['id'], source, path))
        for event in events:
            for source, path in sources(event, project):
                registrations.add((project, event['taskId'], source, path))
        event_rows = [(project, event['seq'], event['id'], event['taskId'], event['kind'],
                       event_order(event)[0].isoformat(timespec='microseconds'),
                       int(bool(user_history_events([event]))), encode(event)) for event in events]
        file_proofs = self.captured_file_proofs(project,signature)
        with self.registry.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                for table, column in (('read_model_tasks', 'project'), ('read_model_task_graph', 'project'), ('read_model_events', 'project'),
                                      ('read_model_event_metadata', 'project'),
                                      ('read_model_sources', 'origin')):
                    c.execute(f'DELETE FROM {table} WHERE {column}=?', (project,))
                c.executemany('INSERT INTO read_model_tasks VALUES(?,?,?)',
                              [(project, t['id'], encode(t)) for t in tasks])
                c.executemany('INSERT INTO read_model_task_graph VALUES(?,?,?)',
                              [(project, t['id'], encode(self.task_graph(t))) for t in tasks])
                c.executemany('INSERT INTO read_model_events VALUES(?,?,?,?,?,?,?,?)', event_rows)
                c.executemany('INSERT INTO read_model_event_metadata VALUES(?,?,?)',
                              [(project, e['seq'], encode(self.event_metadata(e))) for e in events])
                c.executemany('INSERT INTO read_model_sources VALUES(?,?,?,?)', sorted(registrations))
                c.executemany('INSERT OR IGNORE INTO task_owners VALUES(?,?,?,?)',
                              [(str(uuid.uuid5(uuid.NAMESPACE_URL, 'project-hub:' + project + ':' + t['id'])),
                                project, t['id'], project) for t in tasks])
                c.execute('''INSERT INTO read_model_heads VALUES(?,?,?,?,?,?) ON CONFLICT(project)
                             DO UPDATE SET version=excluded.version,seed_hash=excluded.seed_hash,
                             journal_hash=excluded.journal_hash,journal_seq=excluded.journal_seq,
                             project_body=excluded.project_body''',
                          (project, 0 if require_migrations else self.VERSION, *signature, len(events),
                           encode({k: v for k, v in seed.items() if k != 'tasks'})))
                c.execute('DELETE FROM read_model_changes WHERE project=?', (project,))
                c.execute('INSERT INTO read_model_changes(project,journal_seq) VALUES(?,?)',
                          (project, len(events)))
                c.execute('INSERT OR REPLACE INTO read_model_file_proofs VALUES(?,?,?,?,?)',file_proofs)
                if consume_intent is not None:
                    c.execute('DELETE FROM journal_append_intents WHERE project=? AND event=?',
                              (project, consume_intent))
                    c.execute('DELETE FROM journal_append_proofs WHERE project=? AND event=?',
                              (project, consume_intent))
                c.commit()
            except BaseException:
                c.rollback()
                raise
        prepared = getattr(self.registry, 'prepared_sources', None)
        if prepared is not None:
            for _, _, source, path in registrations:
                prepared.schedule(source, path)

    def evidence_origin(self, owner, relative):
        from backup_session import active, connection
        session = active(self.registry)
        if session is None:
            self.ensure(owner)
        candidates = [(owner, relative)]
        if relative.startswith('hub-source/'):
            parts = relative.split('/', 2)
            if len(parts) == 3:
                candidates.append((parts[1], parts[2]))
        allowed = set()
        with connection(self.registry, session) if session else self.registry.connect() as c:
            for source, path in candidates:
                rows = c.execute('''SELECT DISTINCT s.source,s.path FROM read_model_sources s
                    LEFT JOIN task_owners o ON o.origin=s.origin AND o.task=s.task
                    WHERE s.source=? AND s.path=? AND
                    ((s.task='' AND s.origin=?) OR o.owner=?)''', (source, path, owner, owner))
                for row in rows:
                    visible = row['path'] if row['source'] == owner else 'hub-source/' + row['source'] + '/' + row['path']
                    if visible == relative:
                        allowed.add((row['source'], row['path']))
        if not allowed:
            raise ValueError('File is not evidence of this project')
        if len(allowed) != 1:
            raise ValueError('Ambiguous evidence reference')
        source, path = allowed.pop()
        return self.registry.base_store(source), path

    def raw_tasks(self, owner, *, task=None, graph_task=None):
        self.ensure(owner)
        with self.registry.connect() as c:
            body = 't.body'
            parameters = ()
            if graph_task is not None:
                # Validate the complete owner graph without decoding unrelated
                # stages, evidence and text. The changed task retains its full
                # original body; callers requesting ordinary inputs are unchanged.
                body = 'CASE WHEN t.task=? THEN t.body ELSE coalesce(g.body,t.body) END'
                parameters = (graph_task,)
            query = f'''SELECT {body} AS body,o.uid,o.origin,h.journal_seq
                FROM task_owners o JOIN read_model_tasks t ON t.project=o.origin AND t.task=o.task
                LEFT JOIN read_model_task_graph g ON g.project=t.project AND g.task=t.task
                JOIN read_model_heads h ON h.project=o.origin WHERE o.owner=?'''
            parameters += (owner,)
            if task is not None:
                query += ' AND o.task=?'
                parameters += (task,)
            rows = c.execute(query + ' ORDER BY o.rowid', parameters).fetchall()
        from task_transfer import rewrite_sources
        result = []
        for row in rows:
            task = json.loads(row['body'])
            # json.loads already provides private write inputs. Local sources
            # need no owner path rewriting unless explicit foreign provenance
            # appears; avoid recursively copying every unchanged local task.
            if row['origin'] != owner or '"sourceProject"' in row['body']:
                task = rewrite_sources(task, row['origin'], owner)
            task.update(uid=row['uid'], originProject=row['origin'], _sourceRevision=row['journal_seq'])
            result.append(task)
        return result

    def ensure_all(self):
        if getattr(self.projection_local,'revision',None) is not None:
            return
        with self.registry.connect() as c:
            projects = [r[0] for r in c.execute('SELECT id FROM spaces ORDER BY rowid')]
        for project in projects:
            self.ensure_origin(project)

    def inventory(self, *, include_events=True, compact_events=False):
        """Compatibility replay inputs, decoded only when a view is rebuilt."""
        self.ensure_all()
        with self.registry.connect() as c:
            c.execute('BEGIN')
            heads = c.execute('SELECT * FROM read_model_heads ORDER BY rowid').fetchall()
            snapshots = {}
            for head in heads:
                project = head['project']
                tasks = [json.loads(r[0]) for r in c.execute(
                    'SELECT body FROM read_model_tasks WHERE project=? ORDER BY rowid', (project,))]
                table = 'read_model_event_metadata' if compact_events else 'read_model_events'
                relevant = (" AND (json_type(body,'$.patch.primary') IS NOT NULL"
                            " OR json_type(body,'$.patch.status') IS NOT NULL"
                            " OR json_type(body,'$.patch.estimate') IS NOT NULL"
                            " OR json_extract(body,'$.kind') LIKE 'check.%'"
                            " OR json_extract(body,'$.kind')='git.push')") if compact_events else ''
                events = [json.loads(r[0]) for r in c.execute(
                    f'SELECT body FROM {table} WHERE project=?{relevant} ORDER BY seq', (project,))] if include_events else []
                snapshots[project] = (dict(json.loads(head['project_body']), tasks=tasks), tasks, events)
            owners = [dict(r) for r in c.execute('SELECT * FROM task_owners ORDER BY rowid')]
            transfers = [dict(r) for r in c.execute('SELECT rowid AS seq,* FROM task_transfers ORDER BY rowid')]
            c.commit()
        return snapshots, owners, transfers

    def hydrate_events(self, events, owner):
        """Load only the visible page bodies while preserving original numbering."""
        from task_transfer import rewrite_sources
        with self.registry.connect() as c:
            for event in events:
                if not event.get('_compactEvent'):
                    continue
                origin, sequence = event['originProject'], event['seq']
                row = c.execute('SELECT body FROM read_model_events WHERE project=? AND seq=?', (origin, sequence)).fetchone()
                if row is None:
                    raise ValueError('Event changed during prepared view construction')
                event.clear()
                event.update(rewrite_sources(json.loads(row[0]), origin, owner), originProject=origin)

    def domain_key(self, owner):
        """Content revisions exclude host observations and running read jobs."""
        captured = getattr(self.projection_local,'revision',None)
        if captured is not None and captured[0] == owner:
            return captured[2]
        self.ensure_all()
        return self.cached_domain_keys(owner)[1]

    def input_domain_key(self, owner):
        """All dependencies of a prepared view, including incoming relations."""
        captured = getattr(self.projection_local,'revision',None)
        if captured is not None and captured[0] == owner:
            return captured[1]
        self.ensure_all()
        return self.cached_domain_keys(owner)[0]

    def cached_domain_keys(self, owner):
        """Hash unchanged dependencies once per committed SQL generation.

        Generation and inputs belong to one read transaction. A concurrent
        writer can only make this result an older coherent snapshot, exactly as
        an uncached domain_inputs read. Producer publication still compares
        complete fresh inputs under its SQL writer reservation.
        """
        database = self.registry.database
        def identity():
            stat = database.stat()
            return stat.st_dev, stat.st_ino
        database_identity = identity()
        with self.registry.connect() as c:
            c.execute('BEGIN')
            try:
                generation = c.execute(
                    'SELECT generation FROM read_model_generation WHERE singleton=1').fetchone()[0]
                with self.lock:
                    entry = self.domain_keys.get(owner)
                    if entry is not None and entry[:2] == (database_identity, generation):
                        self.domain_keys.move_to_end(owner)
                if entry is None or entry[:2] != (database_identity, generation):
                    inputs = self.domain_inputs(owner, connection=c)
                    entry = (database_identity, generation, self.domain_digest(inputs),
                             self.content_digest(owner, inputs))
                c.commit()
            except BaseException:
                c.rollback()
                raise
        if identity() != database_identity:
            raise ValueError('Registry changed during domain revision; retry the read')
        with self.lock:
            current = self.domain_keys.get(owner)
            if current is None or current[0] != database_identity or current[1] <= generation:
                self.domain_keys[owner] = entry
                self.domain_keys.move_to_end(owner)
                while len(self.domain_keys) > 64:
                    self.domain_keys.popitem(last=False)
        return entry[2], entry[3]

    @classmethod
    def content_digest(cls, owner, inputs):
        heads, owners, moves, checkpoints = inputs
        seen = {move[1] for move in moves if owner in (move[2], move[3])}
        relevant_owners = [row for row in owners
                           if row[1] == owner or row[3] == owner or row[0] in seen]
        identifiers = {row[0] for row in relevant_owners}
        origins = {owner, *(row[1] for row in owners if row[3] == owner)}
        return cls.domain_digest([
            [head for head in heads if head[0] in origins], relevant_owners,
            [move for move in moves if move[1] in identifiers], checkpoints])

    @staticmethod
    def domain_digest(inputs):
        return hashlib.sha256(encode(inputs).encode()).hexdigest()[:20]

    @timed('domain_inputs')
    def domain_inputs(self, owner, *, connection=None):
        with self.registry.connect() if connection is None else nullcontext(connection) as c:
            if connection is None:
                c.execute('BEGIN')
            heads = [(r['project'], bytes(r['seed_hash']).hex(),
                      bytes(r['journal_hash']).hex() if r['journal_hash'] is not None else None)
                     for r in c.execute('SELECT * FROM read_model_heads ORDER BY project')]
            owners = [tuple(r) for r in c.execute('SELECT * FROM task_owners ORDER BY uid')]
            moves = [tuple(r) for r in c.execute('SELECT * FROM task_transfers ORDER BY rowid')]
            checkpoints = [tuple(r) for r in c.execute(
                'SELECT c.id,c.result FROM completion_checkpoints c '
                'JOIN task_owners o ON o.origin=c.origin AND o.task=c.task '
                'WHERE o.owner=? ORDER BY c.rowid', (owner,))]
            if connection is None:
                c.commit()
        return [heads, owners, moves, checkpoints]

    @timed('view_capture')
    def capture_append_view(self, project, event):
        """Capture a proven prepared page before an ordinary journal append.

        Only changes whose display dependencies are local qualify. Structural,
        progress, checkpoint and source changes use the complete projection.
        The caller holds the writer barrier; external file changes are still
        checked again before publishing the advanced page.
        """
        kind, patch = event['kind'], event.get('patch', {})
        if not (kind in ('note', 'finding', 'decision') or
                (kind == 'task.updated' and set(patch) <= {'summary'})):
            return None
        with self.registry.connect() as c:
            owner = c.execute('SELECT owner FROM task_owners WHERE origin=? AND task=?',
                              (project,event['taskId'])).fetchone()
            if owner is None:
                return None
            owner = owner[0]
            row = c.execute('SELECT * FROM read_model_views WHERE project=?', (owner,)).fetchone()
        if row is None:
            return None
        try:
            previous = dict(row)
            with self.lock:
                cached = self.append_pages.get(owner)
            if (cached is not None and len(cached) > 5 and
                    cached[0][0] == row['input_key'] and cached[5] == (row['body'], row['summary'])):
                previous['body'], previous['summary'] = cached[0][1:]
            else:
                previous['body'], previous['summary'] = unpack_view(row['body']), unpack_view(row['summary'])
        except ValueError:
            return None  # A disposable damaged page must not reject a write.
        key = self.view_key(owner)
        if key != row['input_key']:
            return None
        with self.registry.connect() as c:
            cursor = c.execute('SELECT latest FROM read_model_view_cursors WHERE project=? AND input_key=?',
                               (owner,key)).fetchone()
        if cursor is not None:
            latest = json.loads(cursor[0])
        else:
            with self.projection_inputs(key,owner):
                page = self._history_uncached(owner,limit=1,visible=False)['events']
            latest = page[0] if page else None
        return owner, previous, self.domain_inputs(owner), latest

    def prepare_append_view(self, captured, project, event):
        if captured is None:
            return None
        from task_transfer import rewrite_sources, event_order
        owner, previous, inputs, latest = captured
        visible_event = dict(rewrite_sources(event,project,owner),originProject=project)
        prior_order = dict(latest,seq=latest['originSeq']) if latest else None
        if prior_order and event_order(visible_event) <= event_order(prior_order):
            return None  # Restored/future-dated history needs full renumbering.
        # This only prepares private bytes. The post-durability validation below
        # freshly checks every dependency and the final SQL update compares the
        # exact previous key; another full input scan here proves no publication.
        with measure('view_advance'):
            page = self.append_page(owner,previous)
            state, compact = dict(page[1]), dict(page[2])
            state['tasks'], compact['tasks'] = list(state['tasks']), list(compact['tasks'])
            body_parts, summary_parts = list(page[3]), list(page[4])
            revisions = dict(state.get('_originRevisions') or
                             {task['originProject']:task['_sourceRevision'] for task in state['tasks']})
            revisions[project] = event['seq']
            state['_originRevisions'] = revisions
            changed = None
            for index, task in enumerate(state['tasks']):
                if task['originProject'] == project and task['id'] == event['taskId']:
                    from copy import deepcopy
                    task = deepcopy(task)
                    task['_sourceRevision'] = event['seq']
                    task['updatedAt'] = event['at']
                    if event['kind'] == 'task.updated':
                        task.update(event.get('patch', {}))
                    changed = task
                    state['tasks'][index] = task
                    body_parts[index] = encode(task)
                    changed_body = body_parts[index]
                    break
            if changed is None:
                return None
            visible_event.update(originSeq=event['seq'],seq=latest['seq']+1 if latest else 1)
            state['events'] = [visible_event,*state['events']][:24]
            state['eventCount'] += 1
            state['lastEventAt'] = event['at']
            compact.update({name: value for name, value in state.items() if name != 'tasks'})
            for index, task in enumerate(compact['tasks']):
                if task['originProject'] == project and task['id'] == event['taskId']:
                    compact['tasks'][index] = self.task_summary(changed)
                    summary_parts[index] = encode(compact['tasks'][index])
                    break
            return dict(owner=owner,old_key=previous['input_key'],state=state,compact=compact,
                        changed=changed_body,
                        latest=encode(visible_event),inputs=inputs,body_parts=body_parts,summary_parts=summary_parts)

    def append_page(self, owner, previous):
        identity = previous['input_key'], previous['body'], previous['summary']
        with self.lock:
            page = self.append_pages.get(owner)
            if page is not None and page[0] == identity:
                return page
        state, compact = json.loads(previous['body']), json.loads(previous['summary'])
        return identity,state,compact,[encode(t) for t in state['tasks']],[encode(t) for t in compact['tasks']]

    def remember_append_page(self, prepared):
        page = ((prepared['key'],prepared['body'],prepared['summary']),prepared['state'],prepared['compact'],
                prepared['body_parts'],prepared['summary_parts'],
                (prepared['stored_body'], prepared['stored_summary']))
        with self.lock:
            self.append_pages[prepared['owner']] = page
            self.append_pages.move_to_end(prepared['owner'])
            while len(self.append_pages)>4 or sum(len(p[0][1])+len(p[0][2])+
                    (sum(len(v) for v in p[5]) if len(p)>5 else 0)
                    for p in self.append_pages.values())>16*1024*1024:
                self.append_pages.popitem(last=False)

    @staticmethod
    def page_body(state, parts):
        # Encoded task fragments stay private and immutable. The origin sequence
        # belongs to this page header, so an append need not re-encode every task.
        header = encode({name:value for name,value in state.items() if name != 'tasks'})
        return header[:-1]+',"tasks":['+','.join(parts)+']}'

    @timed('view_validate')
    def validate_append_view(self, prepared, project, after_hash):
        """Verify all file inputs after durability, before the atomic SQL publish."""
        if prepared is None:
            return None
        from task_transfer import _origin_signature
        owner = prepared['owner']
        if self.domain_inputs(owner) != prepared['inputs']:
            return None
        inputs = prepared['inputs']
        expected = [list(inputs[0]),*inputs[1:]]
        expected[0] = [(pid,seed,after_hash.hex() if pid == project else journal)
                       for pid,seed,journal in expected[0]]
        parts = json.loads(prepared['old_key'])
        parts[0] = self.domain_digest(expected)
        key = encode(parts)
        for pid,seed,journal in expected[0]:
            signature = _origin_signature(self.registry.origin_files(pid))
            expected_signature = (bytes.fromhex(seed),bytes.fromhex(journal) if journal is not None else None)
            if signature != expected_signature:
                return None
        with self.projection_inputs(key,owner,inputs=expected):
            if self.view_key(owner) != key:
                return None
        prepared['key'] = key
        prepared['state']['revision'] = prepared['compact']['revision'] = self.content_digest(owner, expected)
        prepared['body'] = self.page_body(prepared['state'],prepared['body_parts'])
        prepared['summary'] = self.page_body(prepared['compact'],prepared['summary_parts'])
        prepared['stored_body'],prepared['stored_summary'] = pack_view(prepared['body']),pack_view(prepared['summary'])
        return prepared

    @contextmanager
    def projection_inputs(self,key,owner,*,inputs=None):
        """Reuse the initial proof only inside an unpublished projection.

        SQL reads still capture their own immutable inputs. The final fresh
        key check rejects a racing change before any result is published.
        Intermediate pages bypass caches to avoid polluting an older key.
        """
        previous = getattr(self.projection_local,'revision',None)
        inputs = self.domain_inputs(owner) if inputs is None else inputs
        self.projection_local.revision = (owner,json.loads(key)[0],self.content_digest(owner,inputs))
        try:
            yield
        finally:
            self.projection_local.revision = previous

    @timed('view_key')
    def view_key(self, owner, *, bucket=None):
        domain = self.input_domain_key(owner)
        database = self.registry.home / 'coordination/coordination.sqlite3'
        coordination = [False, 0]
        if database.exists():
            coordination[0] = True
            with self.registry.coordination_connect() as c:
                if c.execute("SELECT 1 FROM sqlite_master WHERE name='events'").fetchone():
                    coordination[1] = c.execute('SELECT coalesce(max(seq),0) FROM events WHERE project=?', (owner,)).fetchone()[0]
        store = self.registry.origin_files(owner)
        try:
            settings = hashlib.sha256((store.data / 'project-settings.json').read_bytes()).hexdigest()
        except FileNotFoundError:
            settings = None
        # Progress has explicit time-dependent boundaries. Recompute at most once
        # per ten seconds per project, independently of the number of clients.
        return encode([domain, coordination, settings, int(time.time() / 10) if bucket is None else bucket, store.display_name, self.VIEW_VERSION])

    @staticmethod
    def _hint_body(state):
        settings = state.get('settings') if isinstance(state, dict) else None
        return {'revision': state.get('revision'),
                'settings': {'revision': settings.get('revision')} if isinstance(settings, dict) else {'revision': None},
                'relationsRevision': state.get('relationsRevision')}

    def _publish_hint(self, connection, project, input_key, state):
        connection.execute('INSERT OR REPLACE INTO read_model_hints VALUES(?,?,?)',
                           (project, input_key, encode(self._hint_body(state))))

    def hint(self, store):
        """Return the small persisted display hint for the current view key."""
        frozen = self.backup_view(store.project_id)
        if frozen is not None:
            return self._hint_body(json.loads(frozen[2]))
        owner = store.project_id
        bucket = int(time.time() / 10)
        key = self.view_key(owner, bucket=bucket)
        with self.registry.connect() as c:
            row = c.execute('SELECT input_key,body FROM read_model_hints WHERE project=? AND input_key=?',
                            (owner, key)).fetchone()
            if row is not None:
                try:
                    value = json.loads(row['body'])
                except (TypeError, ValueError):
                    value = None
                if isinstance(value, dict):
                    return value
            # Existing views from before the hint table are a cold/missing-hint
            # path. Decode only their compact summary once and persist the hint.
            view = c.execute('SELECT input_key,summary FROM read_model_views WHERE project=? AND input_key=?',
                             (owner, key)).fetchone()
            if view is None:
                return None
            try:
                state = json.loads(unpack_view(view['summary']))
            except ValueError:
                return None
            self._publish_hint(c, owner, key, state)
            return self._hint_body(state)

    def snapshot(self, store, *, observations=True, summary=False, task=None, tasks_only=False, complete_history=True):
        owner = store.project_id
        frozen = self.backup_view(owner, complete_history=complete_history and not summary and task is None and not tasks_only)
        if frozen is not None:
            return self.decode_view(store, frozen, observations=False, summary=summary, task=task,
                                    tasks_only=tasks_only, complete_history=complete_history, frozen=True)
        # Clock progression selects a new view, but cannot invalidate a stable
        # domain while that view is being prepared under contention.
        bucket = int(time.time() / 10)
        key = self.view_key(owner, bucket=bucket)
        with self.lock:
            entry = self.views.get(owner)
        if entry is None or entry[0] != key:
            # Other writers/processes publish immutable serialized rows. Loading
            # an already matching SQL view is not a build and must not queue
            # behind the per-worker cold-view producer.
            entry = self.published_view(owner, key)
        if entry is not None and entry[0] == key:
            self.remember_view(owner, entry)
        else:
            with self.lock:
                producer = self.build_locks.setdefault(owner, threading.Lock())
            # A writer already holding the barrier must never wait for a reader
            # whose producer lock precedes that barrier. It can publish directly.
            gate = nullcontext() if getattr(self.registry.transfer_local, 'depth', 0) else measured_lock(producer, 'view_producer')
            with gate:
                # Waiters must compare against current inputs, not the key they
                # captured before waiting. A write may already have published
                # that view while the producer was serving another request.
                bucket = int(time.time() / 10)
                key = self.view_key(owner,bucket=bucket)
                with self.lock:
                    entry = self.views.get(owner)
                if entry is None or entry[0] != key:
                    entry = self.prepare_view(store, key, bucket)
                self.remember_view(owner, entry)
        return self.decode_view(store, entry, observations=observations, summary=summary, task=task,
                                tasks_only=tasks_only, complete_history=complete_history)

    def backup_view(self, owner, *, complete_history=False):
        from backup_session import current, connection, SessionEnded
        session = current(self.registry)
        if session is None or owner not in session['views']:
            return None
        try:
            with connection(self.registry, session) as db:
                row = db.execute('SELECT * FROM read_model_views WHERE project=? AND input_key=?',
                                 (owner, session['views'][owner])).fetchone()
                result = self.stored_view(session['views'][owner], row)
                if result is None:
                    raise ValueError('The prepared backup view is unavailable')
                if complete_history:
                    history = self._history_uncached(owner, limit=2**31-1, visible=False, connection=db)
                    result += (list(reversed(history['events'])),)
                return result
        except SessionEnded:
            return None

    def remember_view(self, owner, entry):
        with self.lock:
            self.views[owner] = entry
            self.views.move_to_end(owner)
            while len(self.views) > 8 or sum(len(v[1])+len(v[2]) for v in self.views.values()) > 64*1024*1024:
                self.views.popitem(last=False)

    def published_view(self, owner, key):
        with self.registry.connect() as c:
            row = c.execute('SELECT * FROM read_model_views WHERE project=? AND input_key=?', (owner,key)).fetchone()
        return self.stored_view(key, row)

    @staticmethod
    def stored_view(key, row):
        if row is not None:
            try:
                return key, unpack_view(row['body']), unpack_view(row['summary'])
            except ValueError:
                pass  # Derived corruption rebuilds from authoritative inputs.
        return None

    def prepare_view(self, store, key, bucket):
        owner = store.project_id
        published = self.published_view(owner, key)
        if published is not None:
            return published
        # Share a single producer across dispatch processes as well as threads.
        # This is a derived-view lock, independent of the journal writer lock.
        # A writer already holding the barrier must bypass it to avoid inversion.
        if getattr(self.registry.transfer_local,'depth',0):
            return self._prepare_view(store,key,bucket)
        with self.lock:
            producer = self.process_build_locks.get(owner)
            if producer is None:
                from project_portal import Store
                lock_name = hashlib.sha256(owner.encode()).hexdigest()[:32]
                producer = Store(self.registry.home,data_dir=self.registry.home / 'view-locks' / lock_name)
                self.process_build_locks[owner] = producer
        with producer.locked(label='view_process',poll_interval=.005):
            return self._prepare_view(store,key,bucket)

    def _prepare_view(self, store, key, bucket):
        from task_transfer import barrier
        from stage_operations import project_links
        owner = store.project_id
        with measure('view_prepare'):
            for attempt in range(2):
                # Compute optimistic immutable inputs without blocking writers.
                # A racing mutation falls back to one serialized build, keeping
                # reads bounded even when revisions change continuously.
                serialized = bool(attempt)
                with barrier(self.registry) if serialized else nullcontext():
                    key = self.view_key(owner, bucket=bucket)
                    with self.registry.connect() as c:
                        row = c.execute('SELECT * FROM read_model_views WHERE project=?', (owner,)).fetchone()
                    published = self.stored_view(key, row) if row is not None and row['input_key'] == key else None
                    if published is not None:
                        return published
                    with self.projection_inputs(key,owner):
                        state = self.refresh_clock_view(store, key, row)
                        if state is None:
                            state = store._build_snapshot(observations=False, compact_events=True, serialized=serialized)
                            project_links(self.registry, owner, state, serialized=serialized)
                    state.pop('allEvents', None)
                    compact = dict(state)
                    compact['tasks'] = [self.task_summary(t) for t in state['tasks']]
                    body, overview = encode(state), encode(compact)
                    stored_body, stored_overview = pack_view(body), pack_view(overview)
                    details = [(owner,t['id'],encode(t)) for t in state['tasks']]
                    # Current domain/coordination/clock keys must name every
                    # input used above. Never publish a mixed revision.
                    # File/coordination freshness can invoke recovery; never
                    # perform it while holding a SQL writer reservation. The
                    # final SQL compare-and-publish uses one exact snapshot,
                    # without making a prepared-page producer a journal writer.
                    if key != self.view_key(owner, bucket=bucket):
                        continue
                    with self.registry.connect() as c:
                        with measure('view_publish'):
                            try:
                                c.execute('BEGIN IMMEDIATE')
                                pending = c.execute("SELECT 1 FROM stage_transactions WHERE state='pending' LIMIT 1").fetchone()
                                if (pending is not None or json.loads(key)[0] !=
                                        self.domain_digest(self.domain_inputs(owner,connection=c))):
                                    c.rollback()
                                    continue
                                row = c.execute('SELECT * FROM read_model_views WHERE project=? AND input_key=?', (owner,key)).fetchone()
                                published = self.stored_view(key, row)
                                if published is not None:
                                    c.commit()
                                    return published
                                c.execute('INSERT OR REPLACE INTO read_model_views VALUES(?,?,?,?)', (owner,key,stored_body,stored_overview))
                                self._publish_hint(c, owner, key, compact)
                                c.execute('DELETE FROM read_model_details WHERE project=?', (owner,))
                                c.executemany('INSERT INTO read_model_details VALUES(?,?,?)',details)
                                c.commit()
                            except sqlite3.OperationalError as error:
                                c.rollback()
                                if (not serialized and getattr(error,'sqlite_errorcode',0) & 255
                                        in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED)):
                                    continue
                                raise
                            except BaseException:
                                c.rollback()
                                raise
                    return key,body,overview
            raise ValueError('Project changed during view preparation; retry the read')

    @staticmethod
    def progress_inputs(events, primary, legacy=None):
        """Retain only static journal facts consumed by the clock projection."""
        def record(event):
            result = {name:event[name] for name in ('id','kind','taskId','at','seq','originProject') if name in event}
            result['patch'] = {name:value for name,value in event.get('patch',{}).items()
                               if name in ('estimate','primary','status')}
            return result
        return dict(legacy={} if legacy is None else legacy,
                    events=[record(e) for e in events if 'estimate' in e.get('patch',{}) or
                            (e['kind'] in ('stage.updated','stage.created') and e.get('patch',{}).get('status') == 'done')],
                    primary=[record(e) for e in primary if isinstance(e.get('patch',{}).get('primary'),dict) or
                             (e['kind'] == 'task.updated' and e.get('patch',{}).get('status') in ('done','cancelled')) or
                             e['kind'] == 'task.transferred'])

    def refresh_clock_view(self, store, key, row):
        """Refresh time-dependent display over the exact unchanged static view.

        Both content/relations, coordination sequence, settings, name and format
        must match. The ordinary final fresh check and SQL CAS still publish it.
        Older derived pages without compiled inputs use the complete builder.
        """
        if row is None:
            return None
        try:
            previous, current = json.loads(row['input_key']), json.loads(key)
        except (ValueError,TypeError):
            return None
        if (not isinstance(previous,list) or not isinstance(current,list) or
                len(previous) != 6 or len(current) != 6 or previous[3] == current[3] or
                previous[:3] != current[:3] or previous[4:] != current[4:]):
            return None
        try:
            state = json.loads(unpack_view(row['body']))
        except (ValueError,TypeError):
            return None
        if not isinstance(state,dict) or not isinstance(state.get('tasks'),list):
            return None
        inputs = state.get('_progressInputs')
        if (not isinstance(inputs,dict) or not isinstance(inputs.get('events'),list) or
                not isinstance(inputs.get('primary'),list) or not isinstance(inputs.get('legacy'),dict)):
            return None
        from task_progress import project_progress
        from project_portal import now
        from copy import deepcopy
        with measure('clock_projection'):
            self.decorate_detail_revisions(state['tasks'],state)
            # Start from journal work, never from an earlier coordination badge.
            for task in state['tasks']:
                if task['id'] in inputs['legacy']:
                    task['currentWork'] = deepcopy(inputs['legacy'][task['id']])
                else:
                    task.pop('currentWork',None)
            state['mainTask'] = project_progress(state['tasks'],inputs['events'],store.project_id,
                                                self.registry.home/'coordination/coordination.sqlite3',inputs['primary'])
            state['serverTime'] = now()
        return state

    def decode_view(self, store, entry, *, observations, summary, task, tasks_only, complete_history=True, frozen=False):
        owner = store.project_id
        if tasks_only or task is not None:
            metadata = json.loads(entry[2])
            with self.registry.connect() as c:
                c.execute('BEGIN')
                current = c.execute('SELECT input_key FROM read_model_views WHERE project=?', (owner,)).fetchone()
                same = not frozen and current is not None and current[0] == entry[0]
                if same and tasks_only:
                    rows = c.execute('SELECT body FROM read_model_details WHERE project=? ORDER BY rowid', (owner,)).fetchall()
                elif same:
                    row = c.execute('SELECT body FROM read_model_details WHERE project=? AND task=?', (owner, task)).fetchone()
                c.commit()
            if tasks_only:
                tasks = [json.loads(r[0]) for r in rows] if same else json.loads(entry[1])['tasks']
                self.decorate_detail_revisions(tasks, metadata)
                result = dict(revision=metadata['revision'], tasks=tasks, allEvents=[], mainTask=metadata['mainTask'], redirects=metadata.get('redirects', {}))
            else:
                found = json.loads(row['body']) if same and row is not None else (
                    next((t for t in json.loads(entry[1])['tasks'] if t['id']==task), None) if not same else None)
                if found is None:
                    raise KeyError('Task moved or was not found')
                self.decorate_detail_revisions([found], metadata)
                result = dict(revision=metadata['revision'],task=found,mainTask=metadata['mainTask'])
        else:
            with measure('view_decode'):
                result = json.loads(entry[2] if summary else entry[1])
                self.decorate_detail_revisions(result['tasks'],result)
                result.pop('_originRevisions',None)
                result.pop('_progressInputs',None)
            if frozen and complete_history and not summary:
                result['allEvents'] = entry[3]
            if not summary and complete_history and not frozen:
                # Only legacy full-state consumers request complete history.
                # Hold ownership stable so tasks and events name one revision;
                # a concurrent write after the cache lookup falls back to a
                # fresh legacy snapshot instead of mixing revisions.
                from task_transfer import barrier
                with barrier(self.registry):
                    if json.loads(entry[0])[0] != self.input_domain_key(owner):
                        result = store._build_snapshot(observations=False)
                    else:
                        result['allEvents'] = list(reversed(self.history(owner, limit=2**31-1, visible=False)['events']))
        if not frozen:
            from completion_policy import resume_pending_checkpoints
            resume_pending_checkpoints(self.registry, result.get('tasks', [result['task']] if 'task' in result else []))
        if observations:
            result['coordination'] = store.diagnostics()
        result['serverTime'] = __import__('project_portal').now()
        return result

    @staticmethod
    def decorate_detail_revisions(tasks, metadata):
        # Detail bodies are immutable until that task changes. An append's
        # origin sequence belongs to the captured view, not each task body.
        # Use its exact compact projection, including when a newer head has
        # already been published; never borrow a sequence from a different key.
        origins = metadata.get('_originRevisions')
        if origins is not None:
            for task in tasks:
                task['_sourceRevision'] = origins[task['originProject']]
            return
        revisions = {(task['id'], task['originProject']): task['_sourceRevision']
                     for task in metadata['tasks']}
        for task in tasks:
            task['_sourceRevision'] = revisions[(task['id'], task['originProject'])]

    @staticmethod
    def task_graph(task):
        return dict(id=task['id'], type=task.get('type','task'),
                    parentTask=task.get('parentTask'), links=task.get('links',[]))

    @staticmethod
    def task_summary(task):
        omitted = {'sources', 'scope', 'deferred', 'acceptance', 'stages'}
        result = {k: v for k, v in task.items() if k not in omitted}
        result['stages'] = [{k: v for k, v in stage.items() if k in
                            ('id', 'title', 'status', 'estimate', 'agentActivity', 'blocker')}
                           for stage in task.get('stages', [])]
        # A summary is also a recovery read. Keep only the identifiers needed
        # to wake pending jobs; complete Git receipts remain in task detail.
        for stage, compact in zip(task.get('stages', []), result['stages']):
            checkpoint = stage.get('gitCheckpoint')
            if isinstance(checkpoint, dict) and checkpoint.get('status') == 'pending' and checkpoint.get('id'):
                compact['gitCheckpoint'] = {k: checkpoint[k] for k in ('id', 'status')}
        result['detailLoaded'] = False
        fields = [task.get(k) for k in ('id','title','summary','status','type','priority','parentTask','scope','acceptance','deferred')]
        fields.extend([stage.get(k) for stage in task.get('stages', []) for k in ('id','title','summary','done','remaining')])
        fields.extend([source.get(k) for source in task.get('sources', []) for k in ('label','path')])
        def words(value):
            if isinstance(value, list):
                return ' '.join(words(v) for v in value)
            if isinstance(value, dict):
                return ' '.join(words(v) for v in value.values())
            return '' if value is None else str(value)
        result['searchText'] = words(fields).lower()
        return result

    def history(self, owner, task=None, before=None, limit=40, kind=None, *, visible=True):
        from backup_session import active, connection, SessionEnded
        session = active(self.registry)
        if session is not None:
            try:
                with connection(self.registry, session) as db:
                    return self._history_uncached(owner, task, before, limit, kind, visible=visible, connection=db)
            except SessionEnded:
                pass
        # Complete legacy snapshots already own their decoded result. Avoid an
        # extra encoding and decoding of the full journal for the page cache.
        if limit > 100 or getattr(self.projection_local,'revision',None) is not None:
            return self._history_uncached(owner,task,before,limit,kind,visible=visible)
        domain = self.domain_key(owner)
        key = (owner,domain,task,before,limit,kind,visible)
        with self.lock:
            body = self.history_pages.get(key)
            if body is not None:
                self.history_pages.move_to_end(key)
        if body is None:
            gate = nullcontext() if getattr(self.registry.transfer_local, 'depth', 0) else self.history_locks[hash(key) % 64]
            with gate:
                with self.lock:
                    body = self.history_pages.get(key)
                if body is None:
                    result = self._history_uncached(owner,task,before,limit,kind,visible=visible)
                    body = encode(result)
                    if len(body) <= 8*1024*1024 and domain == self.domain_key(owner):
                        with self.lock:
                            self.history_pages[key] = body
                            while len(self.history_pages)>64 or sum(len(v) for v in self.history_pages.values())>8*1024*1024:
                                self.history_pages.popitem(last=False)
        return json.loads(body)

    def history_count(self, owner):
        self.ensure(owner)
        with self.registry.connect() as c:
            events = c.execute('''SELECT sum(amount) FROM (
                SELECT count(*) AS amount FROM task_owners o JOIN read_model_events e
                    ON e.project=o.origin AND e.task=o.task WHERE o.owner=:owner AND e.visible=1
                UNION ALL SELECT count(*) FROM read_model_events e
                    WHERE e.project=:owner AND e.task='__project__' AND e.kind='git.push' AND e.visible=1
                    AND NOT EXISTS (SELECT 1 FROM task_owners o WHERE o.origin=e.project
                                    AND o.task=e.task AND o.owner=:owner))''', {'owner':owner}).fetchone()[0]
            moves = c.execute('''SELECT count(*) FROM task_transfers tr
                JOIN task_owners o ON o.uid=tr.uid WHERE ? IN (tr.source,tr.target,o.owner)''', (owner,)).fetchone()[0]
        return events + moves

    def _history_uncached(self, owner, task=None, before=None, limit=40, kind=None, *, visible=True, connection=None):
        """Number the complete owner history before applying a bounded filter."""
        from task_transfer import event_order, rewrite_sources
        if connection is None:
            self.ensure(owner)
        with self.registry.connect() if connection is None else nullcontext(connection) as c:
            c.create_function('hub_instant', 1, lambda at: event_order({'at': at, 'id': ''})[0].isoformat(timespec='microseconds'))
            if connection is None:
                c.execute('BEGIN')
            rows = c.execute('''WITH owner_events AS (
                SELECT NULL AS body,e.project,e.id,e.kind,e.task,e.instant,e.visible,e.seq AS origin_seq,e.project AS sort_project
                FROM task_owners o JOIN read_model_events e ON e.project=o.origin AND e.task=o.task
                WHERE o.owner=:owner
                UNION ALL
                SELECT NULL,e.project,e.id,e.kind,e.task,e.instant,e.visible,e.seq,e.project
                FROM read_model_events e WHERE e.project=:owner AND e.task='__project__' AND e.kind='git.push'
                    AND NOT EXISTS (SELECT 1 FROM task_owners o WHERE o.origin=e.project
                                    AND o.task=e.task AND o.owner=:owner)
                UNION ALL
                SELECT json_object('id',tr.request,'kind','task.transferred','taskId',o.task,'at',tr.at,
                    'title','Задача перенесена','detail',a.name || ' → ' || b.name,
                    'sourceProject',tr.source,'targetProject',tr.target,'actor',tr.actor,'schemaVersion',1,'seq',tr.rowid),
                    NULL,tr.request,'task.transferred',o.task,hub_instant(tr.at),1,tr.rowid,'~'
                FROM task_transfers tr JOIN task_owners o ON o.uid=tr.uid
                JOIN spaces a ON a.id=tr.source JOIN spaces b ON b.id=tr.target
                WHERE :owner IN (tr.source,tr.target,o.owner)
                ), numbered AS (
                    SELECT *,row_number() OVER (ORDER BY instant,sort_project,origin_seq,id) AS view_seq FROM owner_events),
                selected AS (SELECT * FROM numbered WHERE (:visible=0 OR visible=1)
                    AND (:task IS NULL OR task=:task) AND (:before IS NULL OR view_seq<:before)
                    AND (:kind IS NULL OR substr(kind,1,length(:kind))=:kind)
                    ORDER BY view_seq DESC LIMIT :limit)
                SELECT p.*,coalesce(p.body,e.body) AS resolved_body FROM selected p
                LEFT JOIN read_model_events e ON e.project=p.project AND e.seq=p.origin_seq
                ORDER BY p.view_seq DESC''',
                             dict(owner=owner, visible=int(visible), task=task, before=before, kind=kind, limit=limit+1)).fetchall()
            rows = [dict(row) for row in rows]
            if connection is None:
                c.commit()
        page = []
        for row in rows[:limit]:
            event = json.loads(row['resolved_body'])
            if row['project'] is not None:
                event = dict(rewrite_sources(event, row['project'], owner), originProject=row['project'])
            event.update(originSeq=row['origin_seq'], seq=row['view_seq'])
            page.append(event)
        return dict(events=page, next=page[-1]['seq'] if len(rows)>limit else None)

    def events(self, owner, *, task=None):
        self.ensure(owner)
        with self.registry.connect() as c:
            rows = c.execute('''SELECT e.body,e.project FROM read_model_events e
                LEFT JOIN task_owners o ON o.origin=e.project AND o.task=e.task
                WHERE (o.owner=? OR (e.project=? AND e.task='__project__' AND e.kind='git.push'))
                AND (? IS NULL OR e.task=?) ORDER BY e.instant,e.project,e.seq,e.id''',
                             (owner, owner, task, task)).fetchall()
        from task_transfer import rewrite_sources
        return [dict(rewrite_sources(json.loads(r['body']), r['project'], owner), originProject=r['project'])
                for r in rows]

    def event_exists(self, owner, identifier):
        self.ensure(owner)
        with self.registry.connect() as c:
            return c.execute('''SELECT 1 FROM read_model_events e
                LEFT JOIN task_owners o ON o.origin=e.project AND o.task=e.task
                WHERE e.id=? AND (o.owner=? OR (e.project=? AND e.task='__project__')) LIMIT 1''',
                             (identifier, owner, owner)).fetchone() is not None

    def head(self, project):
        self.ensure_origin(project)
        with self.registry.connect() as c:
            return dict(c.execute('SELECT * FROM read_model_heads WHERE project=?', (project,)).fetchone())

    def origin_tasks(self, project, signature, *, task=None):
        """Borrow no objects: an incremental writer gets its own decoded rows."""
        with self.registry.connect() as c:
            row = c.execute('SELECT * FROM read_model_heads WHERE project=?', (project,)).fetchone()
            if row is None or row['version'] != self.VERSION or (row['seed_hash'],row['journal_hash']) != signature:
                return None
            query = 'SELECT body FROM read_model_tasks WHERE project=?'
            parameters = (project,)
            if task is not None:
                query += ' AND task=?'
                parameters += (task,)
            return [json.loads(r[0]) for r in c.execute(query + ' ORDER BY rowid', parameters)]

    def origin_event(self, project, identifier):
        with self.registry.connect() as c:
            row = c.execute('SELECT body FROM read_model_events WHERE project=? AND id=?', (project, identifier)).fetchone()
        return json.loads(row[0]) if row is not None else None

    @timed('index_append')
    def appended(self, project, before, after_hash, tasks, event, *, prepared_view=None):
        from project_portal import user_history_events, SEMANTIC_TASK_FIELDS
        from task_transfer import event_order
        patch = event.get('patch', {})
        summary_only = event['kind'] == 'task.updated' and set(patch) <= {'summary'}
        if ((event['kind'] == 'task.updated' and set(patch) & SEMANTIC_TASK_FIELDS) or
                (event['kind'] in ('task.updated','stage.updated') and 'gitCommit' in patch)):
            # Existing deterministic history migrations remain authoritative.
            # These transitions rebuild once before the next prepared read.
            with self.registry.connect() as c:
                c.execute('DELETE FROM journal_append_intents WHERE project=? AND event=?',(project,event['id']))
                c.execute('DELETE FROM journal_append_proofs WHERE project=? AND event=?',(project,event['id']))
            return
        prepared_view = self.validate_append_view(prepared_view,project,after_hash)
        file_proofs = self.captured_file_proofs(project,(before[0],after_hash))
        receipt = None
        with self.registry.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                head = c.execute('SELECT * FROM read_model_heads WHERE project=?', (project,)).fetchone()
                if head is None or (head['seed_hash'],head['journal_hash']) != before or head['journal_seq']+1 != event['seq']:
                    c.rollback()
                    c.execute('DELETE FROM journal_append_intents WHERE project=? AND event=?',(project,event['id']))
                    c.execute('DELETE FROM journal_append_proofs WHERE project=? AND event=?',(project,event['id']))
                    return  # A cold/restored journal rebuilds from authoritative bytes.
                c.executemany('''INSERT INTO read_model_tasks VALUES(?,?,?) ON CONFLICT(project,task)
                    DO UPDATE SET body=excluded.body WHERE body<>excluded.body''',
                              [(project,t['id'],encode(t)) for t in tasks])
                if not summary_only:
                    c.executemany('''INSERT INTO read_model_task_graph VALUES(?,?,?) ON CONFLICT(project,task)
                        DO UPDATE SET body=excluded.body WHERE body<>excluded.body''',
                                  [(project,t['id'],encode(self.task_graph(t))) for t in tasks])
                c.execute('INSERT INTO read_model_events VALUES(?,?,?,?,?,?,?,?)',
                          (project,event['seq'],event['id'],event['taskId'],event['kind'],
                           event_order(event)[0].isoformat(timespec='microseconds'),int(bool(user_history_events([event]))),encode(event)))
                c.execute('INSERT INTO read_model_event_metadata VALUES(?,?,?)',
                          (project,event['seq'],encode(self.event_metadata(event))))
                registrations = (set() if summary_only else
                                 {(project,t['id'],source,path) for t in tasks for source,path in sources(t,project)})
                registrations.update((project,event['taskId'],source,path) for source,path in sources(event,project))
                c.executemany('INSERT OR IGNORE INTO read_model_sources VALUES(?,?,?,?)', sorted(registrations))
                c.executemany('INSERT OR IGNORE INTO task_owners VALUES(?,?,?,?)',
                              [(str(uuid.uuid5(uuid.NAMESPACE_URL,'project-hub:'+project+':'+t['id'])),project,t['id'],project) for t in tasks])
                c.execute('UPDATE read_model_heads SET journal_hash=?,journal_seq=? WHERE project=?', (after_hash,event['seq'],project))
                c.execute('DELETE FROM read_model_changes WHERE project=?', (project,))
                c.execute('INSERT INTO read_model_changes(project,journal_seq) VALUES(?,?)', (project,event['seq']))
                c.execute('INSERT OR REPLACE INTO read_model_file_proofs VALUES(?,?,?,?,?)',file_proofs)
                if prepared_view is not None:
                    owner = prepared_view['owner']
                    updated = c.execute('UPDATE read_model_views SET input_key=?,body=?,summary=? '
                                        'WHERE project=? AND input_key=?',
                                        (prepared_view['key'],prepared_view['stored_body'],prepared_view['stored_summary'],
                                         owner,prepared_view['old_key'])).rowcount
                    if updated:
                        self._publish_hint(c, owner, prepared_view['key'], prepared_view['compact'])
                        c.execute('UPDATE read_model_details SET body=? WHERE project=? AND task=?',
                                  (prepared_view['changed'],owner,event['taskId']))
                        c.execute('INSERT OR REPLACE INTO read_model_view_cursors VALUES(?,?,?)',
                                  (owner,prepared_view['key'],prepared_view['latest']))
                        receipt = dict(project=owner, revision=prepared_view['state']['revision'])
                # Clear the durability marker atomically with this exact head.
                # A restart before publication still recovers from the journal.
                c.execute('DELETE FROM journal_append_intents WHERE project=? AND event=?',(project,event['id']))
                c.execute('DELETE FROM journal_append_proofs WHERE project=? AND event=?',(project,event['id']))
                c.commit()
            except BaseException:
                c.rollback()
                raise
        prepared = getattr(self.registry,'prepared_sources',None)
        if receipt is not None:
            self.remember_append_page(prepared_view)
        if prepared:
            for source,path in sources(event,project):
                prepared.schedule(source,path)
        # This names the exact committed publication, rather than a later
        # readback that might already observe another writer's version.
        return receipt
