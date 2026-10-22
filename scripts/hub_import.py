"""Administrative import of whole Hub homes into new, inactive copies.

Input folders are never opened as ProjectRegistry: its initialization may write.
Logical data and owned instruction files are copied with verified content hashes.
SQLite writer reservations and existing journal locks coordinate legacy homes.
"""
from contextlib import ExitStack, closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import uuid

from hub_backup import BackupError, DATABASES, _files, _connect, digest, inventory
from hub_lifecycle import home_lease, file_lock
from hub_launcher import external_path


def inspect_home(path, *, progress=None):
    home = external_path(path)
    if not home.is_dir() or (home / 'INCOMPLETE').exists() or (home.parent / 'INCOMPLETE').exists():
        raise BackupError('Choose a complete Hub data folder')
    files = _files(home)
    projects, schemas = inventory(home, progress=progress)
    with _connect(home / 'registry.sqlite3') as db:
        pending = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='registry_upgrade'").fetchone()
        if pending and db.execute("SELECT 1 FROM registry_upgrade WHERE state='pending'").fetchone():
            raise BackupError('The copied storage upgrade is incomplete')
    proofs = {}
    def hash_file(file, name, completed):
        if not progress:
            return digest(file)
        h = hashlib.sha256()
        last = 0
        with file.open('rb') as stream:
            for chunk in iter(lambda: stream.read(1024**2), b''):
                h.update(chunk)
                now = time.monotonic()
                if now-last >= .5:
                    progress({'phase':'verifying','step':'hashing','currentFile':name,
                              'completed':completed-1,'total':len(files),'unit':'files'})
                    last = now
        return h.hexdigest()
    for completed, (name, file) in enumerate(sorted(files.items()), 1):
        proofs[name] = {'sha256': hash_file(file,name,completed), 'size': file.stat().st_size}
        if progress:
            progress({'phase': 'verifying', 'step':'hashing', 'currentFile':name,
                      'completed': completed, 'total': len(files), 'unit':'files'})
    # SQLite sidecar content is part of the logical snapshot. Include it in the
    # preview revision, though it is replaced with SQLite backups in the copy.
    for name in DATABASES:
        wal = home / (name + '-wal')
        if wal.is_file() and wal.stat().st_size:
            proofs[name + '-wal'] = {'sha256': digest(wal), 'size': wal.stat().st_size}
    revision = hashlib.sha256(json.dumps(proofs, sort_keys=True).encode()).hexdigest()
    return {'path': str(home), 'projects': projects, 'storageSchemas': schemas,
            'files': len(files), 'totalBytes': sum(p['size'] for p in proofs.values()), 'revision': revision}


def copy_folder(source, destination, *, expected, active_home, progress=None, inspect_and_copy=False):
    source = external_path(source)
    destination = external_path(destination)
    active_home = external_path(active_home)
    if source == active_home or source.is_relative_to(active_home) or active_home.is_relative_to(source):
        raise BackupError('Use a backup for the active Hub storage')
    if destination.exists() or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise BackupError('Import requires a new separate destination folder')
    if expected is None and not inspect_and_copy:
        raise BackupError('Use the inspected source revision')
    def report(phase, completed=0, total=0):
        if progress:
            progress({'phase': phase, 'completed': completed, 'total': total, 'unit':'files'})
    report('verifying')
    # Lifetime lease rejects another current runtime. Existing old-runtime locks
    # protect its journals and DB reservations protect its SQLite writers.
    with home_lease(source, create=False), ExitStack() as locks:
        for lock in [source / '.local/project-portal/writer.lock',
                     *sorted((source / 'projects').glob('*/writer.lock')),
                     source / 'instructions/edit.lock']:
            if lock.exists():
                locks.enter_context(file_lock(lock, timeout=2, create=False))
        for name in DATABASES:
            path = source / name
            if path.is_file():
                db = locks.enter_context(closing(sqlite3.connect(path, isolation_level=None, timeout=2)))
                db.execute('BEGIN IMMEDIATE')
        before = inspect_home(source, progress=progress)
        if expected is not None and before['revision'] != expected:
            raise BackupError('The source folder changed after preview; inspect it again')
        originals = _files(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='.hub-import-', dir=destination.parent) as temporary:
            stage = Path(temporary) / 'data'; stage.mkdir()
            proofs = {}
            for completed, (name, original) in enumerate(sorted(originals.items()), 1):
                target = stage / name; target.parent.mkdir(parents=True, exist_ok=True)
                if name in DATABASES:
                    with _connect(original) as db, closing(sqlite3.connect(target)) as copy:
                        db.backup(copy)
                else:
                    proof = digest(original); shutil.copyfile(original, target)
                    if digest(target) != proof or digest(original) != proof:
                        raise BackupError('A source file changed during import')
                    proofs[name] = proof
                report('snapshot', completed, len(originals))
            if set(_files(source)) != set(originals) or any(digest(originals[n]) != h for n, h in proofs.items()):
                raise BackupError('The source folder changed during import')
            _copy_instructions(stage, destination / 'data')
            projects, schemas = inventory(stage)
            destination.mkdir(exist_ok=False)
            (destination / 'INCOMPLETE').write_text('Import in progress', encoding='utf-8')
            stage.rename(destination / 'data')
            (destination / 'INCOMPLETE').unlink()
    return {'path': str(destination / 'data'), 'active': False, 'projectCount': len(projects),
            'projects': projects, 'storageSchemas': schemas,
            **({'sourcePreview':before} if inspect_and_copy else {})}


def _copy_instructions(stage, published):
    config = stage / 'instructions/location.json'
    if not config.is_file():
        return
    value = json.loads(config.read_text(encoding='utf-8'))
    root = external_path(value['root'])
    if not (root / 'SKILL.md').is_file() or not (root / '.project-hub-owned.json').is_file():
        raise BackupError('Owned instruction files are missing; use a compatible backup')
    target = stage / 'instructions/project-hub-user'
    files = _files(root, data_home=False)
    if target.exists():
        # Only this owned staging tree may be replaced, never the original root.
        shutil.rmtree(target)
    target.mkdir(parents=True)
    for name, original in files.items():
        out = target / name; out.parent.mkdir(parents=True, exist_ok=True)
        proof = digest(original); shutil.copyfile(original, out)
        if digest(out) != proof or digest(original) != proof:
            raise BackupError('Owned instructions changed during import')
    value['root'] = str(published / 'instructions/project-hub-user')
    value.pop('packageRoot', None)
    config.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def copied_home(backups, identifier):
    row = backups._read(identifier)
    if row.get('state') not in ('restored', 'imported') or row.get('copyDeleted') or not isinstance(row.get('restore'), dict):
        raise BackupError('Select a completed inactive copy')
    path = external_path(row['restore']['path'])
    parent = backups.registry.home.parent.resolve()
    # Copies belong to the server's administrative area, never arbitrary paths
    # submitted by the browser or a project's local source workspace.
    import re
    prepared = backups.home / 'prepared'
    current_area = path.name == 'data' and path.parent.parent == prepared and bool(re.fullmatch('[0-9a-f]{32}', path.parent.name))
    legacy_area = path.name == 'data' and path.parent.parent == parent and bool(re.fullmatch(re.escape(backups.registry.home.name) + r'-restored-[0-9a-f]{32}', path.parent.name))
    if not current_area and not legacy_area:
        raise BackupError('The copied storage is outside the registered import area')
    return path


def storage_catalog(registry):
    from backup_api import Backups
    from hub_lifecycle import catalog
    backups = Backups(registry).catalog()
    projects = registry.list(include_deleted=False)
    from storage_operations import backup_directory, configuration_path
    from hub_lifecycle import control_directory, supervisor_alive
    control = control_directory()
    return {'activeHome': str(registry.home), 'backupHome': str(backup_directory(registry)),
            'folderSettings': {'available': bool(configuration_path(registry) and control and supervisor_alive(control)),
                               'dataHome': str(registry.home), 'backupHome': str(backup_directory(registry))},
            'projects': projects['projects'], 'schemaVersion': projects.get('schemaVersion'),
            'projectCount': len(projects['projects']), 'copies': backups['restoreCopies'],
            'jobs': backups['jobs'], 'capabilities': backups['capabilities'], 'lifecycle': catalog()}


def storage_action(registry, body):
    if not isinstance(body, dict):
        raise BackupError('Use a storage operation object')
    action = body.get('action')
    if action in ('change-folders', 'apply-import'):
        from storage_application import start
        return start(registry, body)
    if action in ('inspect-folder', 'inspect-copy', 'preview-folder') and body.get('background') is True:
        from storage_operations import Operations
        required = {'action', 'background', 'requestId', 'path' if action != 'inspect-copy' else 'id'}
        if not required <= set(body) or set(body) - required - {'origin'}:
            raise BackupError('Use the source and a unique inspection request ID')
        return {'job': Operations(registry).start(body, body['requestId'],
                    lambda payload, progress: compare_source(registry, payload, progress))}
    if action == 'preview-folder' and set(body) == {'action', 'path'}:
        if external_path(body['path']) == registry.home:
            raise BackupError('Use a backup for the active Hub storage')
        with home_lease(body['path'], create=False):
            return {'preview': inspect_home(body['path'])}
    from backup_api import Backups
    backups = Backups(registry)
    if action == 'inspect-copy' and set(body) == {'action', 'id'}:
        path = copied_home(backups, body['id'])
        with home_lease(path):
            return {'preview': inspect_home(path)}
    if action == 'upgrade-copy' and set(body) == {'action', 'id', 'expected', 'confirmed'}:
        if body['confirmed'] is not True:
            raise BackupError('Confirm the copied storage upgrade')
        path = copied_home(backups, body['id'])
        with home_lease(path):
            preview = inspect_home(path)
            if preview['revision'] != body['expected']:
                raise BackupError('The copied storage changed after preview')
            from project_registry import ProjectRegistry
            copy = ProjectRegistry(path, standalone=True)
            try:
                copy.upgrade(confirmed=True)
            finally:
                copy.close_connection_pool()
            return {'preview': inspect_home(path)}
    if action == 'activate-copy':
        raise BackupError('Восстановление теперь применяется в текущую папку данных. Проверьте копию и выберите режим импорта')
    raise BackupError('Unsupported storage operation')


def compare_source(registry, body, progress):
    from backup_api import Backups
    from storage_operations import Operations
    from storage_merge import preview
    from hub_backup import live_snapshot
    backups = Backups(registry)
    identifier = body.get('id')
    if identifier is None:
        path = external_path(body['path'])
        if path == registry.home or path in registry.home.parents or registry.home in path.parents:
            raise BackupError('Используйте резервную копию для данных активного хранилища')
        copied = backups.execute(dict(action='import-folder', path=str(path), expected=None),
                                 progress=stage_progress(progress, 'copying', 'source-copy'),
                                 _inspect_source=True)
        identifier = copied['copyId']
    prepared = prepared_import(registry, identifier, progress=progress)
    inspected = dict(prepared['preview'])
    comparison_home = Path(prepared['path'])
    from local_files import remember_source
    row = backups._read(identifier)
    inspected['sourcePath'] = row.get('sourcePath') or str(backups._path(identifier, '.zip'))
    inspected['sourceKind'] = 'folder' if row.get('sourcePath') else 'zip'
    inspected['preparedSchemas'] = prepared['storageSchemas']
    inspected['converted'] = prepared['converted']
    remember_source(inspected['sourcePath'])
    from runtime_diagnostics import record
    record('import.source_inspected',files=inspected['files'],totalBytes=inspected['totalBytes'],schemas=inspected['storageSchemas'])
    progress({'phase': 'comparing', 'step': 'import-compatibility'})
    # Prepare and pin the current read-model baseline before recording its
    # revision. Later safety backup preparation must not silently change the
    # schema/default state relative to the preview the user approved.
    with live_snapshot(registry), home_lease(comparison_home, create=False):
        started=time.monotonic()
        record('import.comparison_started')
        comparison = preview(registry.home, comparison_home)
        record('import.comparison_finished',elapsedSeconds=round(time.monotonic()-started,3),projects=len(comparison['projects']))
    if prepared.get('normalizedRevision') and prepared['normalizedRevision'] != comparison['incomingRevision']:
        row.pop('preparedImport', None); backups._save(row)
        raise BackupError('Подготовленный источник изменился. Проверьте источник ещё раз.')
    prepared['normalizedRevision'] = comparison['incomingRevision']
    row['preparedImport'] = prepared
    backups._save(row)
    for project in comparison['projects']:
        project['exists'] = project['status'] != 'new'
        project['identical'] = project['status'] == 'identical'
    comparison['currentProjects'] = registry.list(include_deleted=True)['projects']
    return {'preview': inspected, 'comparison': comparison, 'copyId': identifier}


def stage_progress(progress, phase, step):
    """Keep the user stage stable while a nested helper reports its own work."""
    if progress is None:
        return None
    def report(value):
        progress({**value, 'phase': phase, 'step': step,
                  'detailPhase': value.get('phase'), 'detailStep': value.get('step')})
    return report


def _normalization_token():
    proof = hashlib.sha256()
    for name in ('storage_preparation.py', 'hub_storage_schema.py', 'project_registry.py'):
        proof.update(Path(__file__).with_name(name).read_bytes())
    return proof.hexdigest()


def prepared_import(registry, identifier, *, progress=None, expected=None):
    """Retain the verified normalized source used by preview until apply.

    This cache belongs to the registered source, not to the live data home.
    Application still validates its logical revision while building a candidate.
    The original ZIP/folder and the registered raw copy are never migrated.
    """
    from backup_api import Backups
    from storage_operations import Operations
    from storage_preparation import prepare
    backups = Backups(registry)
    row = backups._read(identifier)
    raw = copied_home(backups, identifier)
    if row.get('sha256') and not row.get('archiveDeleted'):
        archive = backups._path(identifier, '.zip')
        if not archive.is_file() or digest(archive) != row['sha256']:
            raise BackupError('Исходный ZIP изменился после проверки. Выберите и проверьте архив ещё раз.')
    cached = row.get('preparedImport')
    token = _normalization_token()
    owned = external_path(Operations(registry).home / 'prepared-sources' / identifier)
    if isinstance(cached, dict) and cached.get('token') == token and cached.get('archiveSha256') == row.get('sha256') and cached.get('rawPath') == str(raw):
        path = external_path(cached['path'])
        if path != raw and not (path.name == 'data' and path.parent.parent == owned):
            # A different launcher can see another physical Windows namespace.
            # Never read or delete the foreign cached tree. Preview can rebuild
            # from the registered raw copy; an approved apply must be reviewed.
            if expected is not None:
                raise BackupError('Подготовка источника изменилась. Откройте предварительный просмотр ещё раз.')
            cached = None
        if cached is not None and path.is_dir() and not (path.parent / 'INCOMPLETE').exists():
            if expected is not None and (cached['preview']['revision'] != expected or not cached.get('normalizedRevision')):
                raise BackupError('Источник изменился после просмотра. Проверьте его ещё раз.')
            if cached.get('state') == 'normalizing':
                if progress:
                    progress({'phase':'migrating','step':'source-format'})
                with home_lease(path):
                    prepare(path)
                cached['state'] = 'ready'
                row['preparedImport'] = cached; backups._save(row)
            if progress:
                progress({'phase': 'verifying', 'step': 'prepared-source', 'reused': True})
            cached['converted'] = any(cached['preview']['storageSchemas'].get(key) == 1
                                      for key in ('registry', 'coordination'))
            cached['storageSchemas'] = {key:2 if key in ('registry', 'coordination') and version == 1 else version
                                       for key, version in cached['preview']['storageSchemas'].items()}
            return cached
    if expected is not None:
        raise BackupError('Сначала откройте предварительный просмотр источника импорта.')
    if progress:
        progress({'phase': 'verifying', 'step': 'source-validation'})
    # Schema discovery is cheap. A legacy source is inspected and copied under
    # one writer reservation, avoiding a redundant full pre-copy hash pass.
    with home_lease(raw, create=False):
        _, schemas = inventory(raw)
    normalized = raw
    converted = any(schemas.get(key) == 1 for key in ('registry', 'coordination'))
    if converted:
        outer = owned / uuid.uuid4().hex
        copied = copy_folder(raw, outer, expected=None, active_home=registry.home, inspect_and_copy=True,
                             progress=stage_progress(progress, 'copying', 'source-copy'))
        normalized = Path(copied['path'])
        inspected = copied['sourcePreview']
    else:
        with home_lease(raw, create=False):
            inspected = inspect_home(raw, progress=progress)
    prepared = dict(path=str(normalized.resolve()), rawPath=str(raw), preview=inspected, token=token,
                    archiveSha256=row.get('sha256'), converted=converted,
                    state='normalizing' if converted else 'ready',
                    storageSchemas={key:2 if key in ('registry', 'coordination') and version == 1 else version
                                    for key, version in inspected['storageSchemas'].items()})
    # Journal this owned image before migration so a failed preview can resume
    # its preparation rather than copying a large source yet again.
    row['preparedImport'] = prepared; backups._save(row)
    if converted:
        if progress:
            progress({'phase': 'migrating', 'step': 'source-format'})
        with home_lease(normalized):
            prepare(normalized)
        prepared['state'] = 'ready'
        row['preparedImport'] = prepared; backups._save(row)
    return prepared
