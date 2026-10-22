"""Draft administration for optional code workspaces in existing schema v2.

Root references are positions in spaces.roots: never delete or compact them.
Transport authorization and enabled-root enforcement belong to the host API.
"""
import json
import hashlib
import os
from pathlib import Path
import shutil
import stat
import time
import uuid

from project_registry import ProjectRevisionConflict
from task_transfer import barrier


def installed_runtime_roots():
    app = Path(__file__).resolve().parents[1]
    return [app.parent] if app.name == 'app' and (app.parent / 'runtime/python.exe').is_file() else []


def local_access(registry, project, roots):
    """Fresh, read-only access state; never compact indexed source roots."""
    with registry.connect() as connection:
        row = connection.execute('SELECT roots FROM spaces WHERE id=?', (project,)).fetchone()
        current = json.loads(row['roots']) if row else []
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE name='project_workspaces' AND type='table'").fetchone()
        entries = Workspaces._rows(connection, project, current) if exists else []
    selected = {str(i) for i in range(len(current))}
    for item in entries:
        if item['kind'] == 'local' and not item['enabled']:
            selected.discard(item['descriptor']['rootRef'])
    protected = [registry.home.resolve(), *installed_runtime_roots()]
    available = set()
    if [str(root) for root in roots] == current:
        for ref in selected:
            root = Path(current[int(ref)])
            try:
                no_reparse(root)
                if not root.is_dir() or any(root.is_relative_to(path) or path.is_relative_to(root) for path in protected):
                    continue
                with os.scandir(root):
                    pass
                available.add(ref)
            except (OSError, WorkspaceError):
                continue
    signature = hashlib.sha256(json.dumps([current, sorted(selected), sorted(available)]).encode()).hexdigest()
    return dict(available=available, configured=selected, signature=signature)


class WorkspaceError(ValueError):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.body = dict(error=code, message=message)
        self.status = status


def no_reparse(path):
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if (stat.S_ISLNK(info.st_mode) or
                getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            raise WorkspaceError('unsafe_workspace', 'Select a folder without symbolic links or reparse points')


class Workspaces:
    def __init__(self, registry, *, runtime_roots=()):
        self.registry = registry
        # The host supplies installed runtime locations. Do not infer the public
        # Hub source checkout as a protected runtime installation.
        self.protected = [registry.home.resolve(), *(Path(value).resolve() for value in runtime_roots)]

    def local_root(self, value):
        if not isinstance(value, str) or not value or len(value)>2000 or any(ord(c)<32 for c in value):
            raise WorkspaceError('invalid_workspace', 'Use an absolute existing local folder')
        path = Path(value)
        if not path.is_absolute() or '..' in path.parts:
            raise WorkspaceError('invalid_workspace', 'Use an absolute existing local folder')
        try:
            no_reparse(path)
            path = path.resolve(strict=True)
            if not path.is_dir():
                raise WorkspaceError('workspace_missing', 'Select an existing local folder')
            # Opening the iterator probes directory access without enumerating
            # source files or running Git/LSP/project commands.
            with os.scandir(path):
                pass
        except OSError as error:
            raise WorkspaceError('workspace_missing', 'The local folder is missing or inaccessible') from error
        if any(path.is_relative_to(protected) or protected.is_relative_to(path) for protected in self.protected):
            raise WorkspaceError('protected_workspace', 'Select a code folder separate from Hub data and the installed runtime')
        return str(path)

    @staticmethod
    def _project(connection, project):
        row = connection.execute('SELECT * FROM spaces WHERE id=?', (project,)).fetchone()
        if row is None:
            raise WorkspaceError('unknown_project', 'Select a registered project', 404)
        if ('deleted' in row.keys() and row['deleted']) or not row['present']:
            raise WorkspaceError('project_unavailable', 'Select an available project', 409)
        return row, json.loads(row['roots'])

    @staticmethod
    def _rows(connection, project, roots):
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE name='project_workspaces' AND type='table'").fetchone()
        rows = connection.execute('SELECT * FROM project_workspaces WHERE project=? ORDER BY id LIMIT 65', (project,)).fetchall() if exists else []
        if len(rows)>64:
            raise WorkspaceError('workspace_limit', 'Workspace catalog exceeds its supported limit', 409)
        result = []
        used = set()
        for row in rows:
            item = dict(row)
            if len(item['descriptor'])>8000:
                raise WorkspaceError('workspace_mapping', 'Workspace metadata exceeds its supported limit', 409)
            item['descriptor'] = json.loads(item['descriptor'])
            if not isinstance(item['descriptor'], dict):
                raise WorkspaceError('workspace_mapping', 'Workspace metadata must be an object', 409)
            item['enabled'] = bool(item['enabled'])
            if item['kind'] == 'local':
                ref = item['descriptor'].get('rootRef')
                if ref is None:
                    root = item['descriptor'].get('root')
                    ref = str(roots.index(root)) if root in roots else None
                if (not isinstance(ref, str) or not ref.isdecimal() or len(ref)>4 or
                        ref != str(int(ref)) or int(ref)>=len(roots)):
                    raise WorkspaceError('workspace_mapping', 'Local workspace has no stable root reference', 409)
                if ref in used:
                    raise WorkspaceError('workspace_mapping', 'Local workspaces share a root reference', 409)
                used.add(ref)
                item['descriptor']['rootRef'] = ref
                # spaces.roots is the authoritative location, even on import.
                item['descriptor']['root'] = roots[int(ref)]
            result.append(item)
        for index, root in enumerate(roots):
            if str(index) not in used:
                result.append(dict(id='legacy-local-'+project+'-'+str(index), project=project, kind='local',
                                   descriptor=dict(root=root, rootRef=str(index)), enabled=True,
                                   revision=1, updated=0, legacy=True))
        if len(result)>64:
            raise WorkspaceError('workspace_limit', 'Workspace catalog exceeds its supported limit', 409)
        return result

    def catalog(self, project):
        self.registry.require_ready()
        with self.registry.connect() as connection:
            # Keep revision, roots and workspace metadata on one read snapshot.
            connection.execute('BEGIN')
            row, roots = self._project(connection, project)
            items = self._rows(connection, project, roots)
            connection.rollback()
        for item in items:
            if item['kind'] != 'local':
                item['availability'] = 'metadata-only'
                item['capabilities'] = dict(source=False, git=dict(state='metadata-only'), lsp=dict(state='metadata-only'))
                continue
            root = item['descriptor']['root']
            try:
                self.local_root(root)
                available = True
                item['availability'] = 'available'
            except WorkspaceError as error:
                available = False
                item['availability'] = error.body['error']
            usable = available and item['enabled']
            marker = Path(root) / '.git'
            try:
                if usable:
                    no_reparse(marker)
                repository = usable and marker.exists()
            except (OSError, WorkspaceError):
                repository = False
            item['capabilities'] = dict(
                source=usable,
                git=dict(repository=bool(repository), executable=bool(shutil.which('git')),
                         state='detected' if repository else 'unavailable'),
                lsp=dict(state='not-checked' if usable else 'unavailable', available=None if usable else False),
            )
        return dict(project=project, revision=row['revision'] if 'revision' in row.keys() else 0,
                    management=self.registry.schema_version==2,
                    rootRefs=[str(i) for i in range(len(roots))], items=items)

    def change(self, project, action, *, expected, request_id, workspace=None, root=None, enabled=None):
        """Admin-only CAS mutation. Exact replay precedes filesystem validation."""
        self.registry._management()
        if type(expected) is not int or expected<1:
            raise WorkspaceError('invalid_revision', 'Use the current project revision')
        if action not in ('add', 'relocate', 'enable'):
            raise WorkspaceError('invalid_workspace', 'Use add, relocate or enable')
        if action == 'add' and (workspace is not None or enabled is not None):
            raise WorkspaceError('invalid_workspace', 'Add accepts a local folder only')
        if action == 'relocate' and (not isinstance(workspace, str) or enabled is not None):
            raise WorkspaceError('invalid_workspace', 'Relocate requires a workspace ID and folder')
        if action == 'enable' and (not isinstance(workspace, str) or type(enabled) is not bool or root is not None):
            raise WorkspaceError('invalid_workspace', 'Enable requires a workspace ID and boolean flag')
        payload = dict(action='workspace.'+action, project=project, expected=expected,
                       workspace=workspace, root=root, enabled=enabled)
        with barrier(self.registry), self.registry.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            try:
                proof, prior = self.registry._request(connection, request_id, payload)
                if prior is not None:
                    connection.rollback()
                    return prior
                row, roots = self._project(connection, project)
                if row['revision'] != expected:
                    raise ProjectRevisionConflict('Project changed; refresh before editing workspaces')
                items = self._rows(connection, project, roots)
                changed = True
                at = time.time()
                if action == 'add':
                    if len(roots)>=8 or len(items)>=64:
                        raise WorkspaceError('workspace_limit', 'At most eight local folders are supported')
                    canonical = self.local_root(root)
                    if any(Path(canonical) == Path(value) for value in roots):
                        raise WorkspaceError('workspace_exists', 'This local folder is already registered', 409)
                    item = dict(id=uuid.uuid4().hex, project=project, kind='local',
                                descriptor=dict(root=canonical, rootRef=str(len(roots))),
                                enabled=True, revision=1, updated=at)
                    roots.append(canonical)
                else:
                    item = next((value for value in items if value['id'] == workspace), None)
                    if item is None:
                        raise WorkspaceError('unknown_workspace', 'Workspace does not exist', 404)
                    if action == 'relocate':
                        if item['kind'] != 'local':
                            raise WorkspaceError('invalid_workspace', 'Only local folders can be relocated')
                        canonical = self.local_root(root)
                        index = int(item['descriptor']['rootRef'])
                        if any(Path(canonical) == Path(value) for position,value in enumerate(roots) if position != index):
                            raise WorkspaceError('workspace_exists', 'This local folder is already registered', 409)
                        changed = canonical != roots[index]
                        roots[index] = canonical
                        item['descriptor']['root'] = canonical
                    else:
                        # Enabling an absent folder is rejected; disabling it is
                        # always possible, preserving its evidence namespace.
                        if enabled and item['kind'] == 'local':
                            self.local_root(item['descriptor']['root'])
                        changed = enabled != item['enabled']
                        item['enabled'] = enabled
                    if changed:
                        item['revision'] += 1
                        item['updated'] = at
                if changed or item.get('legacy'):
                    updated = connection.execute('''INSERT INTO project_workspaces VALUES(?,?,?,?,?,?,?)
                        ON CONFLICT(id) DO UPDATE SET descriptor=excluded.descriptor,
                        enabled=excluded.enabled, revision=excluded.revision, updated=excluded.updated
                        WHERE project_workspaces.project=excluded.project''',
                        (item['id'], project, item['kind'], json.dumps(item['descriptor']), int(item['enabled']), item['revision'], item['updated']))
                    if updated.rowcount != 1:
                        raise WorkspaceError('workspace_mapping', 'Workspace ID belongs to another project', 409)
                    connection.execute("UPDATE spaces SET roots=?,revision=revision+1,ownership='hub',updated=? WHERE id=?",
                                       (json.dumps(roots), at, project))
                result = dict(project=project, revision=expected+(1 if changed or item.get('legacy') else 0),
                              workspace={key: value for key,value in item.items() if key!='legacy'}, roots=roots)
                connection.execute('INSERT INTO project_requests VALUES(?,?,?)', (request_id, proof, json.dumps(result)))
                connection.commit()
                return result
            except BaseException:
                connection.rollback()
                raise
