"""One revision producer per process; subscribers consume immutable hints.

Cross-process journal/index/ownership changes are observed by the producer.
Subscribers never copy task bodies or run SQL, regardless of their tab count.
"""
import threading
import time
import copy
import hashlib
import json
import math
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path


OBSERVATION_TTL = 10


class EventBroker:
    def __init__(self, server):
        self.server = server
        self.condition = threading.Condition()
        self.projects = {}
        self.thread = None
        self.observers = ThreadPoolExecutor(max_workers=2, thread_name_prefix='hub-observation')
        self.observations = set()
        self.idle_seconds = 30

    def coordination_revision(self, store):
        home = getattr(store, 'coordination_home', None)
        if home is None or not hasattr(store, 'project_id'):
            return None
        path = home / 'coordination.sqlite3'
        if not path.is_file():
            return 0
        # This producer must retain its short read-only probe timeout even
        # though ordinary API/view queries use reusable coordination leases.
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.05)) as c:
            row = c.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE project=?', (store.project_id,)).fetchone()
            return row[0]

    def observe(self, entry):
        registry = getattr(entry['store'], 'registry', None)
        if registry is not None:
            from backup_session import active
            if active(registry) is not None:
                return  # Retain observations; do not publish host cache writes.
        future = entry.get('observation')
        if future is not None and future.done():
            self.observations.discard(future)
            with self.condition:
                try:
                    diagnostics = future.result()
                finally:
                    # A failed future must not permanently occupy the slot.
                    # The caller still receives the exception so run() records
                    # the observation error until a later retry succeeds.
                    if entry.get('observation') is future:
                        entry['observation'] = None
                entry['diagnostics'] = diagnostics
                entry['observed'] = time.monotonic()
        revision = self.coordination_revision(entry['store'])
        due = (time.monotonic() - entry.get('observed', float('-inf')) >= 10 or
               revision is not None and revision != entry.get('diagnostics', {}).get('revision', 0))
        if due and entry.get('observation') is None and len(self.observations) < 2:
            future = self.observers.submit(self._shared_diagnostics, entry['store'])
            entry['observation'] = future
            self.observations.add(future)

    def _observation_identity(self, store, coordination_revision):
        registry = getattr(store, 'registry', None)
        if registry is None:
            return None
        try:
            from codex_session_catalog import CATALOG
            catalog_database = getattr(CATALOG, 'database', None)
        except (ImportError, AttributeError):
            catalog_database = None
        from project_portal import SESSION_TITLES
        catalog_path = getattr(getattr(registry, 'catalog', None), 'path', None)
        installation_root = getattr(store, 'installation_root', '')
        values = {
            'project': str(getattr(store, 'project_id', '')),
            'registryCatalog': str(Path(catalog_path).resolve()) if catalog_path else '',
            'catalogDatabase': str(Path(catalog_database).resolve()) if catalog_database else '',
            'sessionTitles': str(Path(SESSION_TITLES.path).resolve()),
            'installationRoot': str(Path(installation_root).resolve()) if installation_root else '',
            'coordinationRevision': coordination_revision,
        }
        host_values = dict(values)
        host_values.pop('coordinationRevision')
        host_encoded = json.dumps(host_values, sort_keys=True, separators=(',', ':'))
        encoded = json.dumps(values, sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256((values['project'] + '\0' + encoded).encode()).hexdigest()
        host_digest = hashlib.sha256((values['project'] + '\0' + host_encoded).encode()).hexdigest()
        return digest, host_digest

    @staticmethod
    def _valid_cached(row, now):
        if row is None:
            return None
        try:
            age = now - float(row['observed_wall'])
        except (TypeError, ValueError, OverflowError):
            return None
        if not math.isfinite(age) or age < 0 or age >= OBSERVATION_TTL:
            return None
        try:
            body = json.loads(row['body'])
        except (TypeError, ValueError):
            return None
        return body if isinstance(body, dict) else None

    def _read_cached_diagnostics(self, registry, project, input_key, now):
        try:
            with registry.connect() as connection:
                connection.execute('''CREATE TABLE IF NOT EXISTS observation_cache(
                    project TEXT NOT NULL,
                    input_key TEXT NOT NULL,
                    observed_wall REAL NOT NULL,
                    body TEXT NOT NULL,
                    PRIMARY KEY(project, input_key))''')
                row = connection.execute(
                    'SELECT observed_wall,body FROM observation_cache WHERE project=? AND input_key=?',
                    (project, input_key)).fetchone()
        except sqlite3.Error:
            return None
        return self._valid_cached(row, now)

    def _write_cached_diagnostics(self, registry, project, input_key, observed_wall, body):
        try:
            encoded = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            if not isinstance(body, dict):
                return
            with registry.connect() as connection:
                try:
                    connection.execute('BEGIN IMMEDIATE')
                    connection.execute('''CREATE TABLE IF NOT EXISTS observation_cache(
                        project TEXT NOT NULL,
                        input_key TEXT NOT NULL,
                        observed_wall REAL NOT NULL,
                        body TEXT NOT NULL,
                        PRIMARY KEY(project, input_key))''')
                    connection.execute('DELETE FROM observation_cache WHERE project=? AND input_key<>?',
                                       (project, input_key))
                    connection.execute('''INSERT INTO observation_cache(project,input_key,observed_wall,body)
                        VALUES(?,?,?,?) ON CONFLICT(project,input_key) DO UPDATE SET
                        observed_wall=excluded.observed_wall, body=excluded.body''',
                        (project, input_key, observed_wall, encoded))
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
        except sqlite3.Error:
            return

    def _shared_diagnostics(self, store):
        registry = getattr(store, 'registry', None)
        if registry is None:
            return store.diagnostics()
        project = str(getattr(store, 'project_id', ''))
        coordination_revision = self.coordination_revision(store)
        identity = self._observation_identity(store, coordination_revision)
        if identity is None:
            return store.diagnostics()
        input_key, host_key = identity
        cached = self._read_cached_diagnostics(registry, project, input_key, time.time())
        if cached is not None:
            return cached
        from project_portal import Store
        lock_key = host_key
        lock_store = Store(registry.home,
                           data_dir=Path(registry.home) / 'observation-locks' / lock_key,
                           installation_root=getattr(store, 'installation_root', registry.home),
                           coordination_home=getattr(store, 'coordination_home', None))
        with lock_store.locked(label='host_observation', poll_interval=.005):
            coordination_revision = self.coordination_revision(store)
            identity = self._observation_identity(store, coordination_revision)
            if identity is None:
                return store.diagnostics()
            input_key, _ = identity
            cached = self._read_cached_diagnostics(registry, project, input_key, time.time())
            if cached is not None:
                return cached
            result = store.diagnostics()
            if not isinstance(result, dict):
                return {'available': False, 'reason': 'Observation returned an invalid result'}
            # A coordination write during discovery makes this result stale;
            # leave it uncached so the next producer observes the new key.
            final_coordination = self.coordination_revision(store)
            if (final_coordination != coordination_revision or
                    (final_coordination is not None and
                     result.get('revision') is not None and
                     result.get('revision') != final_coordination)):
                return result
            self._write_cached_diagnostics(registry, project, input_key, time.time(), result)
            return result

    def state(self, store):
        key = getattr(store, 'project_id', str(store.data))
        with self.condition:
            entry = self.projects.setdefault(key, dict(store=store, hint=None, error=None))
            entry['last_used'] = time.monotonic()
            if self.thread is None:
                self.thread = threading.Thread(target=self.run, name='hub-revision-producer', daemon=True)
                self.thread.start()
            if entry['error'] is not None:
                raise ValueError('Revision producer failed; reconnect for a fresh view') from entry['error']
            return entry['hint']

    def run(self):
        while not self.server.stopping.is_set():
            with self.condition:
                # Each connected stream calls state regularly. Stop polling
                # projects after the last tab/API observer has gone idle.
                instant = time.monotonic()
                retained = {key:entry for key,entry in self.projects.items()
                            if instant-entry['last_used'] < self.idle_seconds}
                if len(retained) != len(self.projects):
                    self.projects = retained
                    self.condition.notify_all()
                entries = list(self.projects.values())
                self.observations = {future for future in self.observations if not future.done()}
            for entry in entries:
                try:
                    store = entry['store']
                    if getattr(store, 'registry', None) is None:
                        state = self.server.read_snapshot(store)
                        settings_revision = state.get('settings', {}).get('revision')
                        relations_revision = state.get('relationsRevision')
                    else:
                        state = store.registry.read_models.hint(store)
                        if state is None:
                            state = store.registry.read_models.snapshot(store, observations=False, summary=True)
                        settings_revision = state.get('settingsRevision', state.get('settings', {}).get('revision'))
                        relations_revision = state.get('relationsRevision')
                    # Host discovery is refreshed once per project, never by
                    # each SSE connection. It stays outside task revision hashes.
                    self.observe(entry)
                    diagnostics = entry.get('diagnostics', {})
                    hint = dict(revision=state['revision'], coordinationRevision=diagnostics.get('revision', 0),
                                titlesRevision=diagnostics.get('titlesRevision', ''),
                                settingsRevision=settings_revision,
                                relationsRevision=relations_revision, knowledgeRevision=0)
                    registry = getattr(store, 'registry', None)
                    if registry:
                        with registry.connect() as c:
                            if c.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_meta'").fetchone():
                                row = c.execute('SELECT revision FROM knowledge_meta WHERE project=?', (store.project_id,)).fetchone()
                                hint['knowledgeRevision'] = row[0] if row else 0
                    before = entry['hint'] or {}
                    sections = {'revision': 'tasks', 'coordinationRevision': 'coordination',
                                'titlesRevision': 'coordination', 'settingsRevision': 'settings',
                                'relationsRevision': 'relations', 'knowledgeRevision': 'knowledge'}
                    changed = sorted({section for field, section in sections.items() if hint[field] != before.get(field)})
                    hint['changedSections'] = changed
                    with self.condition:
                        if changed:
                            entry['hint'] = hint
                        entry.update(error=None, checked=time.monotonic())
                        self.condition.notify_all()
                except (OSError, ValueError, KeyError, TimeoutError, sqlite3.Error) as error:
                    with self.condition:
                        entry['error'] = error
                        self.condition.notify_all()
            self.server.stopping.wait(.4)

    def diagnostics(self, store):
        self.state(store)
        key = getattr(store, 'project_id', str(store.data))
        with self.condition:
            return copy.deepcopy(self.projects[key].get('diagnostics', {'available': False, 'reason': 'Observation is being prepared'}))

    def checked(self, store):
        key = getattr(store, 'project_id', str(store.data))
        with self.condition:
            return self.projects.get(key, {}).get('checked', 0)

    def subscribe(self, store):
        joined = time.monotonic()
        self.state(store)
        with self.condition:
            self.condition.wait_for(lambda: self.checked(store) >= joined or self.server.stopping.is_set(), timeout=10)

    def close(self):
        with self.condition:
            self.condition.notify_all()
        if self.thread is not None:
            self.thread.join(timeout=2)
        self.observers.shutdown(wait=True, cancel_futures=True)
