"""Persistent local project spaces. Codex metadata is a read-only discovery adapter."""
from contextlib import closing
from copy import deepcopy
from dataclasses import dataclass
import json
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import time
import threading
import uuid

from project_portal import Store, atomic_write, require_external_data
from request_metrics import data_path, timed


def default_data_home():
    if os.environ.get('PROJECT_HUB_HOME'):
        return Path(os.environ['PROJECT_HUB_HOME']).expanduser().resolve()
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share'))
    return base / 'ProjectHub/data'


class CodexProjects:
    """Local desktop metadata format; errors preserve the last known registry.

    No writes to Codex, no transcript scanning, no claim of a stable public API.
    """
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(os.environ.get('CODEX_HOME', Path.home()/'.codex'))/'.codex-global-state.json'

    def read(self):
        try:
            # Read bytes on every lookup: timestamps (even size+mtime) cannot
            # establish freshness after an external edit or restore. Retain
            # only a private parsed projection of these exact bytes.
            content = self.path.read_bytes()
            cached = getattr(self, '_read_cache', None)
            if cached is not None and cached[0] == content:
                result = deepcopy(cached[1])
                # Root canonicalization also depends on current filesystem
                # aliases, which may change without changing catalog bytes.
                for project in result['projects']:
                    project['roots'] = [str(Path(root).resolve())
                                        for root in cached[2][project['codexId']]]
                return result
            state = json.loads(content.decode('utf-8-sig'))
            rows = state['local-projects']
            if not isinstance(rows, dict):
                raise ValueError('Unknown project catalog format')
            projects = []
            for key, row in rows.items():
                if key.startswith('g-p-'):
                    continue  # ChatGPT project mirror is not a saved local project.
                if not isinstance(row,dict) or row.get('id') != key:
                    raise ValueError('Invalid project catalog entry')
                roots = row.get('rootPaths')
                if not isinstance(roots,list) or not roots or not all(isinstance(p,str) and Path(p).is_absolute() for p in roots):
                    raise ValueError('Invalid project roots')
                if not isinstance(row.get('name'),str):
                    raise ValueError('Invalid project name')
                projects.append(dict(codexId=key,name=row['name'],roots=[str(Path(p).resolve()) for p in roots]))
            assignments = state.get('thread-project-assignments', {})
            if not isinstance(assignments, dict):
                raise ValueError('Invalid thread project assignments')
            for row in assignments.values():
                if not isinstance(row, dict) or not isinstance(row.get('projectId'), str) or not isinstance(row.get('projectKind'), str):
                    raise ValueError('Invalid thread project assignment')
            result = dict(available=True, projects=projects, assignments=assignments, source='codex-local-metadata')
            self._read_cache = content, deepcopy(result), {
                project['codexId']: rows[project['codexId']]['rootPaths'][:]
                for project in projects}
            return result
        except (OSError, ValueError, KeyError, TypeError) as error:
            self._read_cache = None
            return dict(available=False, projects=[], reason=str(error)[:240], source='codex-local-metadata')

    def assigned_project(self, session):
        """Optional explicit desktop assignment; never infer it from a title."""
        from project_resolution import assignment_for
        return assignment_for(self.read(), session)


class IndependentProjects:
    """A fresh Hub has no host catalog and does not discover projects itself."""
    def read(self):
        return dict(available=True, projects=[], assignments={}, source='hub-owned', authoritative=False)

    def assigned_project(self, session):
        return None


class ProjectRevisionConflict(ValueError):
    body = {'code': 'project_revision_conflict', 'message': 'Проект изменён. Обновите каталог и повторите изменение.'}


def start_operation(registry, body):
    """Opt-in durable management; legacy synchronous API remains compatible."""
    from storage_operations import Operations, normalize_origin
    action = body.get('action')
    required = {'action', 'name', 'roots', 'requestId'} if action == 'create' else \
               {'action', 'project', 'patch', 'expected', 'requestId'} if action == 'update' else set()
    operation = {key: value for key, value in body.items() if key not in ('background', 'origin')}
    if not required or set(operation) != required or body.get('background') is not True:
        raise ValueError('Use create or update with an explicit project operation and request ID')
    origin = normalize_origin(body.get('origin'), section='projects')
    if action == 'update':
        origin['project'] = operation['project']
        origin = normalize_origin(origin, section='projects')
    payload = dict(action='project-' + action, operation=operation,
                   requestId=operation['requestId'], origin=origin)

    def execute(payload, progress):
        request = payload['operation']
        progress({'phase': 'preparing'})
        if request['action'] == 'create':
            project = registry.create(request['name'], request['roots'], request_id=request['requestId'])
        else:
            project = registry.update(request['project'], request['patch'], expected=request['expected'],
                                      request_id=request['requestId'])
        return {'project': project}

    return {'operation': Operations(registry).start(payload, operation['requestId'], execute)}


@dataclass(frozen=True)
class OriginFiles:
    """Internal journal inputs; deliberately no source root or evidence API."""
    registry: object
    project_id: str
    display_name: str
    data: Path

    @property
    def journal(self):
        return self.data / 'events.jsonl'

    def writer_probe(self):
        return Store.lock_probe(self.data / 'writer.lock')


class ProjectRegistry:
    def __init__(self, directory=None, catalog=None, *, standalone=False):
        self.home = (Path(directory) if directory else default_data_home()).resolve()
        require_external_data(self.home)
        self.standalone = standalone
        self.catalog = catalog if catalog is not None else IndependentProjects() if standalone else CodexProjects()
        self.home.mkdir(parents=True,exist_ok=True)
        self.database = self.home/'registry.sqlite3'
        self._connection_pool = None
        self._coordination_pool = None
        self.transfer_lock=threading.RLock()
        self.hub_schema_lock=threading.RLock()
        self.transfer_local=threading.local()
        from backup_session import active
        if active(self) is not None:
            # A new read worker borrows the existing prepared schema without
            # replaying initializer INSERTs behind the snapshot reservation.
            from read_models import ReadModels
            with self.connect() as c:
                self.schema_version = c.execute('SELECT version FROM registry_meta').fetchone()[0]
                if self.schema_version not in (1, 2):
                    raise ValueError('Unsupported project registry version')
            self.read_models = ReadModels(self)
            return
        with self.connect() as c:
            from hub_storage_schema import initialize_registry
            self.schema_version = initialize_registry(c, standalone)
        from task_transfer import setup
        setup(self)
        from read_models import ReadModels
        self.read_models = ReadModels(self)

    def connect(self):
        if self._connection_pool is not None:
            return self._connection_pool.connect()
        c = sqlite3.connect(self.database,timeout=5,isolation_level=None)
        c.row_factory=sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        return closing(c)

    def enable_connection_pool(self):
        from sqlite_pool import SQLitePool
        with self.transfer_lock:
            if self._connection_pool is None:
                self._connection_pool = SQLitePool(self.database,foreign_keys=True)

    def close_connection_pool(self):
        if self._connection_pool is not None:
            self._connection_pool.close()
            self._connection_pool = None
        if self._coordination_pool is not None:
            self._coordination_pool.close()
            self._coordination_pool = None

    def coordination_connect(self):
        """Fresh coordination queries without reopening WAL for every lookup."""
        database = self.home/'coordination/coordination.sqlite3'
        if self._connection_pool is None:
            c = sqlite3.connect(database.as_uri()+'?mode=rw',uri=True,timeout=5,isolation_level=None)
            c.row_factory = sqlite3.Row
            c.execute('PRAGMA foreign_keys=ON')
            return closing(c)
        from sqlite_pool import SQLitePool
        with self.hub_schema_lock:
            if self._coordination_pool is None:
                self._coordination_pool = SQLitePool(database,foreign_keys=True,existing_only=True)
        return self._coordination_pool.connect()

    @timed('catalog_refresh')
    def refresh(self):
        from backup_session import active
        if active(self) is not None:
            return dict(available=True, source='backup-snapshot', projects=[])
        discovery = self.catalog.read()
        if not discovery['available'] or discovery.get('authoritative') is False:
            return discovery
        with self.connect() as c:
            # Compare against current SQLite rows rather than memoizing the
            # last catalog result: other registries/processes may change rows.
            rows = c.execute('SELECT * FROM spaces').fetchall()
            self.schema_version = c.execute('SELECT version FROM registry_meta').fetchone()[0]
            current = {row['codex_id']: row for row in rows if row['codex_id'] is not None}
            desired = {p['codexId']: p for p in discovery['projects']}
            unchanged = all(
                (self.schema_version == 2 and row['ownership'] == 'hub') or
                (row['present'] == (key in desired)
                and (key not in desired or (row['name'] == desired[key]['name']
                     and row['roots'] == json.dumps(desired[key]['roots']))))
                for key, row in current.items()) and desired.keys() <= current.keys()
            if unchanged:
                return discovery
            c.execute('BEGIN IMMEDIATE')
            try:
                discovered = {p['codexId'] for p in discovery['projects']}
                for row in rows:
                    if self.schema_version == 2 and row['ownership'] == 'hub':
                        continue
                    if row['present'] and row['codex_id'] not in discovered:
                        c.execute('UPDATE spaces SET present=0,updated=? WHERE codex_id=?', (time.time(), row['codex_id']))
                for project in discovery['projects']:
                    owned = current.get(project['codexId'])
                    if owned is not None and self.schema_version == 2 and owned['ownership'] == 'hub':
                        continue
                    existing = c.execute('SELECT id FROM spaces WHERE codex_id=?',(project['codexId'],)).fetchone()
                    pid = existing['id'] if existing else str(uuid.uuid4())
                    c.execute('''INSERT INTO spaces(id,codex_id,name,roots,present,updated) VALUES(?,?,?,?,1,?) ON CONFLICT(codex_id)
                                 DO UPDATE SET name=excluded.name,roots=excluded.roots,present=1,updated=excluded.updated
                                 WHERE spaces.name!=excluded.name OR spaces.roots!=excluded.roots OR spaces.present!=1''',
                              (pid,project['codexId'],project['name'],json.dumps(project['roots']),time.time()))
                c.commit()
            except BaseException:
                c.rollback(); raise
        return discovery

    @staticmethod
    def _project(row):
        project = dict(row)
        project['roots'] = json.loads(project['roots'])
        if 'revision' in project:
            for flag in ('archived', 'deleted'):
                project[flag] = bool(project[flag])
        return project

    def list(self, include_deleted=False):
        discovery=self.refresh()
        with self.connect() as c:
            self.schema_version = c.execute('SELECT version FROM registry_meta').fetchone()[0]
            where = ' WHERE deleted=0' if self.schema_version == 2 and not include_deleted else ''
            projects=[self._project(r) for r in c.execute('SELECT * FROM spaces'+where+' ORDER BY present DESC,name,id')]
        return dict(schemaVersion=self.schema_version,projects=projects,discovery={k:v for k,v in discovery.items() if k not in ('projects','assignments')})

    def upgrade(self, *, confirmed=False):
        """Explicit administrator operation for an inactive, imported copy."""
        if not self.standalone or confirmed is not True:
            raise ValueError('Explicit confirmation is required to upgrade an inactive copied data home')
        self.transfer_local.upgrading = True
        try:
            return self._upgrade_inactive()
        finally:
            self.transfer_local.upgrading = False

    def _upgrade_inactive(self):
        from task_transfer import barrier
        from hub_storage_schema import upgrade_registry, upgrade_coordination
        self.close_connection_pool()
        with barrier(self):
            with self.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                try:
                    c.execute('CREATE TABLE IF NOT EXISTS registry_upgrade(id INTEGER PRIMARY KEY CHECK(id=1),state TEXT NOT NULL)')
                    c.execute("INSERT INTO registry_upgrade VALUES(1,'pending') ON CONFLICT(id) DO UPDATE SET state='pending'")
                    c.commit()
                except BaseException:
                    c.rollback()
                    raise
                upgrade_registry(c)
            upgrade_coordination(self.home/'coordination/coordination.sqlite3')
            with self.connect() as c:
                c.execute("UPDATE registry_upgrade SET state='complete' WHERE id=1")
                self.schema_version = c.execute('SELECT version FROM registry_meta').fetchone()[0]
            self.__dict__.pop('_hub_schema_identity', None)
        return dict(schemaVersion=self.schema_version)

    def _management(self):
        self.require_ready()
        with self.connect() as c:
            version = c.execute('SELECT version FROM registry_meta').fetchone()[0]
        if version != 2:
            raise ValueError('Import and explicitly upgrade a copy before managing independent projects')

    def require_ready(self):
        """An incomplete copied home may be inspected/upgraded, not activated."""
        if getattr(self.transfer_local, 'upgrading', False):
            return
        with self.connect() as c:
            pending = (c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='registry_upgrade'").fetchone()
                       and c.execute("SELECT 1 FROM registry_upgrade WHERE state='pending'").fetchone())
        if pending:
            raise ValueError('Data-home upgrade is incomplete; retry it on the inactive copy before activation')

    @staticmethod
    def _name(name):
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 240 or any(ord(ch)<32 for ch in name):
            raise ValueError('Project name must contain 1–240 printable characters')
        return name.strip()

    @staticmethod
    def _request(connection, request_id, payload):
        if not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id):
            raise ValueError('Use a unique 32-character hexadecimal request ID')
        fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode()).hexdigest()
        old = connection.execute('SELECT fingerprint,result FROM project_requests WHERE id=?', (request_id,)).fetchone()
        if old is not None:
            if old['fingerprint'] != fingerprint:
                raise ValueError('Request ID was reused with different project changes')
            return fingerprint, json.loads(old['result'])
        return fingerprint, None

    def create(self, name, roots=None, *, request_id=None):
        self._management()
        name, roots = self._name(name), [] if roots is None else roots
        if not isinstance(roots, list) or len(roots)>8 or any(not isinstance(root,str) or not Path(root).is_absolute() for root in roots):
            raise ValueError('Workspaces must be a list of up to eight absolute local folders')
        request_id = request_id or uuid.uuid4().hex
        from task_transfer import barrier
        with barrier(self), self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                fingerprint, old = self._request(c, request_id, dict(action='create', name=name, roots=roots))
                if old is not None:
                    c.rollback()
                    self.base_store(old['id'])
                    return old
                canonical_roots = list(dict.fromkeys(str(Path(root).resolve()) for root in roots))
                if any(not Path(root).is_dir() for root in canonical_roots):
                    raise ValueError('A local code workspace must be an existing folder')
                project = uuid.uuid4().hex
                c.execute('''INSERT INTO spaces(id,codex_id,name,roots,present,updated,ownership)
                             VALUES(?,NULL,?,?,1,?,'hub')''', (project,name,json.dumps(canonical_roots),time.time()))
                for root in canonical_roots:
                    c.execute('INSERT INTO project_workspaces VALUES(?,?,?,?,1,1,?)',
                              (uuid.uuid4().hex,project,'local',json.dumps(dict(root=root)),time.time()))
                result = self._project(c.execute('SELECT * FROM spaces WHERE id=?',(project,)).fetchone())
                c.execute('INSERT INTO project_requests VALUES(?,?,?)', (request_id,fingerprint,json.dumps(result)))
                c.commit()
                # Commit the idempotency receipt first. A crash before baseline
                # initialization leaves the same registered ID for replay;
                # the existing lazy initializer rechecks under SQLite's writer
                # reservation instead of creating an unregistered directory.
                self.base_store(project)
                return result
            except BaseException:
                c.rollback()
                raise

    def update(self, project_id, patch, *, expected, request_id=None):
        self._management()
        if not isinstance(patch,dict) or not patch or set(patch)-{'name','archived','deleted'}:
            raise ValueError('Project changes may update name, archived or deleted')
        patch = dict(patch)
        if 'name' in patch:
            patch['name'] = self._name(patch['name'])
        if any(type(patch[key]) is not bool for key in ('archived','deleted') if key in patch):
            raise ValueError('Project archive and deletion flags must be boolean')
        if type(expected) is not int or expected<1:
            raise ValueError('Use the current project revision')
        request_id = request_id or uuid.uuid4().hex
        from task_transfer import barrier
        with barrier(self), self.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            try:
                fingerprint, old = self._request(c, request_id, dict(action='update',id=project_id,patch=patch,expected=expected))
                if old is not None:
                    c.rollback()
                    return old
                row = c.execute('SELECT * FROM spaces WHERE id=?',(project_id,)).fetchone()
                if row is None:
                    raise KeyError('Unknown project')
                if row['revision'] != expected:
                    raise ProjectRevisionConflict('Project changed; refresh before editing')
                if any(row[key] != value for key,value in patch.items()) or row['ownership'] != 'hub':
                    assignments = ','.join(key+'=?' for key in patch)
                    c.execute('UPDATE spaces SET '+assignments+",ownership='hub',revision=revision+1,updated=? WHERE id=?",
                              (*patch.values(),time.time(),project_id))
                result = self._project(c.execute('SELECT * FROM spaces WHERE id=?',(project_id,)).fetchone())
                c.execute('INSERT INTO project_requests VALUES(?,?,?)',(request_id,fingerprint,json.dumps(result)))
                c.commit()
                return result
            except BaseException:
                c.rollback()
                raise

    def store(self, project_id):
        self.require_ready()
        from task_transfer import ProjectView
        return ProjectView(self,project_id)

    @timed('origin_context')
    def origin_files(self, project_id):
        self.require_ready()
        with self.connect() as c:
            project = c.execute('SELECT id,name FROM spaces WHERE id=?',(project_id,)).fetchone()
        if project is None:
            raise KeyError('Unknown project')
        data = data_path(self.home / 'projects' / project['id'])
        if not (data / 'project.json').exists():
            # First initialization retains the ordinary canonical-root and
            # SQLite writer protocol. Warm metadata reads need no source root.
            self.base_store(project_id)
        return OriginFiles(self, project_id, project['name'], data)

    @timed('store_context')
    def base_store(self, project_id):
        self.require_ready()
        with self.connect() as c:
            project=c.execute('SELECT * FROM spaces WHERE id=?',(project_id,)).fetchone()
            if not project:
                raise KeyError('Unknown project')
            data=self.home/'projects'/project['id']
            baseline=data/'project.json'
            # Existing data needs no write reservation. Missing initialization
            # still rechecks under the same SQLite writer barrier as before.
            if not baseline.exists():
                c.execute('BEGIN IMMEDIATE')
                try:
                    if not baseline.exists():
                        atomic_write(baseline,json.dumps(dict(schemaVersion=1,id=project['id'],name=project['name'],tasks=[])))
                    c.commit()
                except BaseException:
                    c.rollback(); raise
        roots = json.loads(project['roots'])
        store = Store(roots[0] if roots else None,data_dir=data,coordination_home=self.home/'coordination')
        store.display_name = project['name']
        store.registry, store.project_id = self, project_id
        return store
