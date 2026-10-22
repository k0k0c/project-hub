"""Portable whole-data-home archives. No UI, source checkout or client dependency.

The live adapter supplies a snapshot guard; verification/restoration never open
the live databases and restoration only creates a new, inactive destination.
See docs/backup-format.md for the versioned public container contract.
"""
from contextlib import ExitStack, closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import stat
import tempfile
import time
import zipfile
import zlib

KIND = 'project-hub-backup'
VERSION = {'major': 1, 'minor': 0}
FEATURES = {'whole-data-home', 'sqlite-snapshot', 'portable-instructions', 'source-file-aliases'}
DATABASES = ('registry.sqlite3', 'coordination/coordination.sqlite3')
MAX_BYTES = 2 * 1024**3
MAX_FILES = 100_000
MAX_MANIFEST = 8 * 1024**2
BLOCK = 1024**2


class BackupError(ValueError):
    pass


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(BLOCK), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_name(name):
    if not isinstance(name, str) or not name or '\\' in name or '\x00' in name:
        raise BackupError('Недопустимый путь в архиве')
    parts = PurePosixPath(name).parts
    if name.startswith('/') or '/'.join(parts) != name or any(p in ('.', '..') for p in parts):
        raise BackupError('Недопустимый путь в архиве')
    for part in parts:
        if any(ord(c) < 32 or c in ':<>"|?*' for c in part) or part.endswith((' ', '.')):
            raise BackupError('Путь несовместим с Windows')
        if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part):
            raise BackupError('Зарезервированное имя Windows в архиве')
    return name


def _ephemeral(relative, data_home=True):
    path = PurePosixPath(relative)
    return (path.name in ('writer.lock', 'edit.lock') or '__pycache__' in path.parts
            or path.suffix == '.pyc'
            or (data_home and ('language-servers' in path.parts or path.parts[0] == 'runtime'
                or any(relative == db + ending for db in DATABASES for ending in ('-wal', '-shm', '-journal')))))


def _files(home, data_home=True):
    result = {}
    for directory, dirs, files in os.walk(home, followlinks=False):
        for name in list(dirs):
            p = Path(directory) / name
            relative = p.relative_to(home).as_posix()
            if p.is_symlink() or p.resolve() != p.absolute():
                raise BackupError('Ссылки внутри хранилища не поддерживаются')
            if _ephemeral(relative, data_home):
                dirs.remove(name)
        for name in files:
            p = Path(directory) / name
            relative = p.relative_to(home).as_posix()
            if _ephemeral(relative, data_home):
                continue
            if p.is_symlink() or p.resolve() != p.absolute() or not p.is_file():
                raise BackupError('В хранилище найден нестандартный файл')
            result[safe_name(relative)] = p
    if len(result) > MAX_FILES or sum(p.stat().st_size for p in result.values()) > MAX_BYTES:
        raise BackupError('Хранилище превышает поддерживаемый размер архива')
    return result


def _connect(path):
    return closing(sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True, timeout=10))


def inventory(home, *, progress=None):
    """Read authoritative copied stores without initializing or repairing them."""
    home = Path(home)
    schemas = {'projectJournal': 1}
    from runtime_diagnostics import record
    def stage(step, current_file):
        record('storage.validation', step=step, currentFile=current_file)
        if progress:
            progress({'phase':'verifying', 'step':step, 'currentFile':current_file})
    for relative, table, key in ((DATABASES[0], 'registry_meta', 'registry'),
                                 (DATABASES[1], 'meta', 'coordination')):
        p = home / relative
        if not p.exists():
            if relative == DATABASES[0]:
                raise BackupError('Реестр проектов отсутствует')
            continue
        stage('database-integrity', relative)
        with _connect(p) as db:
            started = time.monotonic()
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise BackupError('Повреждена база данных: ' + relative)
            record('storage.database_checked',currentFile=relative,elapsedSeconds=round(time.monotonic()-started,3))
            stage('database-relations', relative)
            if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise BackupError('Нарушены связи в базе данных: ' + relative)
            versions = db.execute('SELECT version FROM ' + table).fetchall()
            if len(versions) != 1 or versions[0][0] not in (1, 2):
                raise BackupError('Неподдерживаемая версия схемы: ' + relative)
            schemas[key] = versions[0][0]
    projects = []
    with _connect(home / DATABASES[0]) as db:
        rows = db.execute('SELECT id,name FROM spaces ORDER BY id').fetchall()
    for pid, name in rows:
        safe_name(pid)
        if '/' in pid:
            raise BackupError('Недопустимый идентификатор проекта')
        data = home / 'projects' / pid
        stage('project-journal', 'projects/' + pid + '/events.jsonl')
        task_ids, events = set(), 0
        if (data / 'project.json').exists():
            seed = json.loads((data / 'project.json').read_text(encoding='utf-8-sig'))
            if (not isinstance(seed, dict) or seed.get('schemaVersion') != 1 or seed.get('id') != pid
                    or not isinstance(seed.get('tasks', []), list)):
                raise BackupError('Состояние проекта не соответствует реестру')
            for task in seed.get('tasks', []):
                if not isinstance(task, dict) or not isinstance(task.get('id'), str):
                    raise BackupError('Повреждена запись задачи')
                task_ids.add(task['id'])
        if (data / 'events.jsonl').exists():
            with (data / 'events.jsonl').open(encoding='utf-8-sig') as journal:
                for line in journal:
                    if line.strip():
                        event = json.loads(line)
                        if not isinstance(event, dict):
                            raise BackupError('Повреждён журнал проекта')
                        events += 1
                        if event.get('kind') == 'task.created':
                            if not isinstance(event.get('taskId'), str):
                                raise BackupError('В журнале отсутствует идентификатор задачи')
                            task_ids.add(event['taskId'])
        projects.append({'id': pid, 'name': name, 'tasks': len(task_ids), 'journalEvents': events})
    return projects, schemas


@contextmanager
def live_snapshot(registry):
    """Serialize journals/instructions and reserve both SQLite writers.

    Backup reads use separate read connections while the reservations remain
    open: sqlite3.backup on a connection's own write transaction would block.
    """
    from project_portal import Store
    from task_transfer import barrier
    _files(registry.home)  # Reject links before creating/acquiring any source lock.
    from knowledge_store import KnowledgeStore
    from backup_session import publish
    for attempt in range(3):
        # Preparation can be expensive on a cold catalog. Perform it before
        # taking the snapshot barrier, then validate briefly under reservations.
        views = {}
        with registry.connect() as db:
            catalog = [tuple(row) for row in db.execute('SELECT id,name,roots,present FROM spaces ORDER BY id')]
        for project, *_ in catalog:
            KnowledgeStore(registry, project)
            store = registry.store(project)
            key = registry.read_models.view_key(project)
            views[project] = registry.read_models.prepare_view(store, key, json.loads(key)[3])[0]
        with registry.connect() as db:
            generation = db.execute('SELECT generation FROM read_model_generation WHERE singleton=1').fetchone()[0]
        with barrier(registry), ExitStack() as stack:
            for directory in sorted((registry.home / 'projects').glob('*')):
                if directory.is_dir():
                    stack.enter_context(Store.lock_probe(directory / 'writer.lock').locked())
            instructions = None
            if (registry.home / 'instructions/location.json').exists():
                # The owned companion is a legacy deployment adapter, not a format dependency.
                import sys
                scripts = Path(__file__).resolve().parents[1] / 'tools/project-portal/plugins/project-hub/scripts'
                if str(scripts) not in sys.path:
                    sys.path.insert(0, str(scripts))
                from hub_instructions import Instructions, _lock
                instructions = Instructions(registry.home)
                stack.enter_context(_lock(instructions.home))
                instructions.read()
            for relative in DATABASES:
                path = registry.home / relative
                if path.exists():
                    db = stack.enter_context(closing(sqlite3.connect(path, isolation_level=None, timeout=10)))
                    db.execute('BEGIN IMMEDIATE')
            with registry.connect() as db:
                valid = (generation == db.execute('SELECT generation FROM read_model_generation WHERE singleton=1').fetchone()[0]
                         and catalog == [tuple(row) for row in db.execute('SELECT id,name,roots,present FROM spaces ORDER BY id')]
                         and all(db.execute('SELECT 1 FROM read_model_views WHERE project=? AND input_key=?',
                                            (project, key)).fetchone() for project, key in views.items()))
            for project, key in views.items():
                captured = json.loads(key)
                settings = registry.home / 'projects' / project / 'project-settings.json'
                settings_hash = digest(settings) if settings.is_file() else None
                valid = valid and captured[0] == registry.read_models.cached_domain_keys(project)[0] and captured[2] == settings_hash
                coordination = registry.home / DATABASES[1]
                current_coord = [coordination.is_file(), 0]
                if current_coord[0]:
                    with _connect(coordination) as db:
                        if db.execute("SELECT 1 FROM sqlite_master WHERE name='events'").fetchone():
                            current_coord[1] = db.execute('SELECT coalesce(max(seq),0) FROM events WHERE project=?', (project,)).fetchone()[0]
                valid = valid and captured[1] == current_coord
            if not valid:
                continue  # Release all reservations before preparing again.
            stack.enter_context(publish(registry, views, generation))
            yield instructions
            return
    raise BackupError('Данные изменились во время подготовки снимка; повторите резервирование')


def create_archive(registry, destination, created_by=None, *, progress=None, snapshot_destination=None):
    """Snapshot the full installation; destination must be outside data home."""
    home, destination = registry.home.resolve(), Path(destination).resolve()
    def report(phase, completed=0, total=0):
        if progress is not None:
            progress(dict(phase=phase, completed=completed, total=total))
    report('preparing')
    if destination.exists() or destination.is_relative_to(home):
        raise BackupError('Архив должен быть новым файлом вне рабочего хранилища')
    if snapshot_destination is not None:
        snapshot_destination = Path(snapshot_destination).absolute()
        if snapshot_destination.exists() or snapshot_destination == home or home in snapshot_destination.parents:
            raise BackupError('Снимок требует отдельной новой папки вне рабочих данных')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.backup-', dir=destination.parent) as temp:
        stage = Path(temp)
        payload = stage / 'home'
        payload.mkdir()
        with live_snapshot(registry) as instructions:
            originals = _files(home)
            proofs = {}
            report('snapshot', 0, len(originals))
            for completed, (relative, source) in enumerate(sorted(originals.items()), 1):
                target = payload / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if relative in DATABASES:
                    with _connect(source) as db, closing(sqlite3.connect(target)) as copied:
                        db.backup(copied)
                else:
                    before = digest(source)
                    shutil.copyfile(source, target)
                    if digest(target) != before or digest(source) != before:
                        raise BackupError('Файлы изменились во время резервирования; повторите операцию')
                    proofs[relative] = before
                report('snapshot', completed, len(originals))
            if set(_files(home)) != set(originals) or any(digest(originals[p]) != h for p, h in proofs.items()):
                raise BackupError('Хранилище изменилось во время резервирования; повторите операцию')
            required = ['whole-data-home', 'sqlite-snapshot']
            if any(PurePosixPath(name).name == 'source-file-aliases.json' for name in originals):
                required.append('source-file-aliases')
            if instructions is not None:
                root = instructions.location()
                portable = stage / 'portable-instructions'
                portable.mkdir()
                companions = _files(root, data_home=False)
                companion_proofs = {}
                for name, source in companions.items():
                    target = portable / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    before = digest(source)
                    shutil.copyfile(source, target)
                    if digest(target) != before or digest(source) != before:
                        raise BackupError('Инструкции изменились во время резервирования')
                    companion_proofs[name] = before
                if (set(_files(root, data_home=False)) != set(companions)
                        or any(digest(companions[name]) != proof for name, proof in companion_proofs.items())):
                    raise BackupError('Инструкции изменились во время резервирования')
                required.append('portable-instructions')
            projects, schemas = inventory(payload)
        report('compressing', 0, len(originals))
        files = {}
        for p in sorted(stage.rglob('*')):
            if p.is_file():
                files[p.relative_to(stage).as_posix()] = {'size': p.stat().st_size, 'sha256': digest(p)}
        manifest = {'kind': KIND, 'formatVersion': VERSION, 'scope': 'all-projects',
                    'createdAt': datetime.now(timezone.utc).isoformat(),
                    'createdBy': created_by or {'application': 'Project Hub', 'backupWriter': '1.0'},
                    'requiredFeatures': required, 'storageSchemas': schemas,
                    'projects': projects, 'files': files,
                    'excluded': ['OS locks', 'SQLite sidecars (included via snapshot)', 'generated language-server workspaces', 'transient runtime state and logs', 'Python bytecode'],
                    'extensions': {}}
        (stage / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        partial = stage / 'archive.partial'
        with zipfile.ZipFile(partial, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for completed, name in enumerate(['manifest.json', *files], 1):
                archive.write(stage / name, name)
                report('compressing', completed, len(files) + 1)
        report('verifying')
        preview_archive(partial)
        # Never replace an existing archive; a simultaneous creator fails closed.
        with destination.open('xb') as output, partial.open('rb') as source:
            shutil.copyfileobj(source, output, BLOCK)
            output.flush(); os.fsync(output.fileno())
        if snapshot_destination is not None:
            # Use the very same SQLite-consistent snapshot that produced the
            # safety ZIP. Do not decompress that ZIP into another work copy.
            if instructions is not None:
                bundled = payload / 'instructions/project-hub-user'
                if bundled.exists():
                    shutil.rmtree(bundled)
                shutil.copytree(stage / 'portable-instructions', bundled)
                location = payload / 'instructions/location.json'
                value = json.loads(location.read_text(encoding='utf-8'))
                value['root'] = str(snapshot_destination / 'instructions/project-hub-user')
                value.pop('packageRoot', None)
                location.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
            snapshot_destination.parent.mkdir(parents=True, exist_ok=True)
            if payload.stat().st_dev == snapshot_destination.parent.stat().st_dev:
                payload.rename(snapshot_destination)
            else:
                shutil.copytree(payload, snapshot_destination)
                before = {name: digest(path) for name, path in _files(payload).items()}
                after = {name: digest(path) for name, path in _files(snapshot_destination).items()}
                if before != after:
                    raise BackupError('Проверка рабочей копии на другом диске не пройдена')
    return {'name': destination.name, 'size': destination.stat().st_size,
            'sha256': digest(destination), 'createdAt': manifest['createdAt'], 'projects': projects}


def _manifest(archive):
    infos = archive.infolist()
    if len(infos) > MAX_FILES + 1:
        raise BackupError('В архиве слишком много файлов')
    names, folded, total = {}, set(), 0
    for info in infos:
        name = safe_name(info.filename)
        if name in names or name.casefold() in folded or info.is_dir():
            raise BackupError('Архив содержит повторяющиеся или неоднозначные пути')
        if stat.S_IFMT(info.external_attr >> 16) not in (0, stat.S_IFREG):
            raise BackupError('Ссылки и нестандартные файлы не поддерживаются')
        if info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise BackupError('Неподдерживаемое сжатие или шифрование архива')
        names[name] = info
        folded.add(name.casefold())
        total += info.file_size
    if total > MAX_BYTES or 'manifest.json' not in names or names['manifest.json'].file_size > MAX_MANIFEST:
        raise BackupError('Отсутствует manifest или превышен размер архива')
    manifest = json.loads(archive.read('manifest.json'))
    if not isinstance(manifest, dict):
        raise BackupError('Manifest должен быть объектом')
    if (not isinstance(manifest.get('createdAt'), str)
            or not isinstance(manifest.get('extensions', {}), dict)):
        raise BackupError('Неверные метаданные manifest')
    try:
        datetime.fromisoformat(manifest['createdAt'].replace('Z', '+00:00'))
    except ValueError as error:
        raise BackupError('Неверная дата создания архива') from error
    version = manifest.get('formatVersion', {})
    required = manifest.get('requiredFeatures')
    if (manifest.get('kind') != KIND or not isinstance(version, dict)
            or type(version.get('major')) is not int or version.get('major') != 1
            or type(version.get('minor')) is not int or version['minor'] < 0
            or manifest.get('scope') != 'all-projects' or not isinstance(required, list)
            or not all(isinstance(feature, str) for feature in required)
            or not {'whole-data-home', 'sqlite-snapshot'} <= set(required)
            or set(required) - FEATURES):
        raise BackupError('Неподдерживаемый формат или обязательные возможности архива')
    files = manifest.get('files')
    if not isinstance(files, dict) or set(names) != {'manifest.json', *files}:
        raise BackupError('Состав архива не соответствует manifest')
    for name, proof in files.items():
        safe_name(name)
        if not name.startswith(('home/', 'portable-instructions/')):
            raise BackupError('Неизвестная область данных архива')
        if (not isinstance(proof, dict) or type(proof.get('size')) is not int
                or proof['size'] != names[name].file_size
                or not isinstance(proof.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', proof['sha256'])):
            raise BackupError('Неверное описание файла в manifest')
    return manifest


def _extract_payload(path, stage, progress=None):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise BackupError('Архив превышает поддерживаемый размер')
    with zipfile.ZipFile(path) as archive:
        manifest = _manifest(archive)
        for completed, (name, proof) in enumerate(manifest['files'].items(), 1):
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256()
            count = 0
            with archive.open(name) as source, target.open('xb') as output:
                for chunk in iter(lambda: source.read(BLOCK), b''):
                    count += len(chunk)
                    if count > proof['size']:
                        raise BackupError('Превышен заявленный размер файла')
                    h.update(chunk)
                    output.write(chunk)
            if count != proof['size'] or h.hexdigest() != proof['sha256']:
                raise BackupError('Контрольная сумма файла не совпадает: ' + name)
            if progress:
                progress(dict(phase='restoring', step='archive-extraction', completed=completed,
                              total=len(manifest['files']), unit='files', currentFile=name))
    projects, schemas = inventory(stage / 'home')
    if projects != manifest.get('projects') or schemas != manifest.get('storageSchemas'):
        raise BackupError('Описание проектов или схем не соответствует данным')
    if 'portable-instructions' in manifest['requiredFeatures']:
        for name in ('SKILL.md', '.project-hub-owned.json'):
            if not (stage / 'portable-instructions' / name).is_file():
                raise BackupError('В архиве отсутствуют переносимые инструкции')
        config = json.loads((stage / 'home/instructions/location.json').read_text(encoding='utf-8'))
        marker = json.loads((stage / 'portable-instructions/.project-hub-owned.json').read_text(encoding='utf-8'))
        if (not isinstance(config, dict) or not isinstance(marker, dict)
                or config.get('kind') != 'project-hub-user-skill-v1' or marker.get('kind') != config['kind']):
            raise BackupError('Неверные сведения о владельце инструкций')
    return manifest


def _extract_verified(path, stage, progress=None):
    try:
        return _extract_payload(path, stage, progress=progress)
    except (zipfile.BadZipFile, sqlite3.DatabaseError, json.JSONDecodeError,
            KeyError, TypeError, UnicodeError, EOFError, zlib.error) as error:
        raise BackupError('Повреждён архив или его описание') from error


def preview_archive(path):
    with tempfile.TemporaryDirectory(prefix='hub-backup-verify-') as temp:
        manifest = _extract_verified(path, Path(temp))
    return archive_summary(manifest)


def archive_summary(manifest):
    return {k: manifest[k] for k in ('kind', 'formatVersion', 'scope', 'createdAt', 'projects', 'storageSchemas')} | {
        'files': len(manifest['files']), 'totalBytes': sum(p['size'] for p in manifest['files'].values())}


def restore_copy(path, destination, expected_sha256=None, *, progress=None):
    path, destination = Path(path).resolve(), Path(destination).absolute()
    if destination.exists() or destination.is_symlink() or destination.parent.resolve() != destination.parent:
        raise BackupError('Восстановление допускается только в новую папку без ссылок')
    if expected_sha256 is not None and digest(path) != expected_sha256:
        raise BackupError('Архив изменился после проверки')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.restore-', dir=destination.parent) as temp:
        stage = Path(temp)
        manifest = _extract_verified(path, stage, progress=progress)
        if expected_sha256 is not None and digest(path) != expected_sha256:
            raise BackupError('Архив изменился во время восстановления')
        portable = stage / 'portable-instructions'
        if 'portable-instructions' in manifest['requiredFeatures']:
            if not (portable / 'SKILL.md').is_file() or not (portable / '.project-hub-owned.json').is_file():
                raise BackupError('В архиве отсутствуют переносимые инструкции')
            new_root = stage / 'home/instructions/project-hub-user'
            if new_root.exists():
                if not new_root.resolve().is_relative_to(stage.resolve()):
                    raise BackupError('Некорректная папка инструкций')
                shutil.rmtree(new_root)
            shutil.copytree(portable, new_root)
            config = stage / 'home/instructions/location.json'
            value = json.loads(config.read_text(encoding='utf-8'))
            value['root'] = str(destination / 'data/instructions/project-hub-user')
            value.pop('packageRoot', None)
            config.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        # Exclusive outer reservation prevents even an empty pre-existing folder
        # from being overwritten on POSIX. Publish within our newly owned folder.
        destination.mkdir(exist_ok=False)
        (destination / 'INCOMPLETE').write_text('Restore in progress', encoding='utf-8')
        (stage / 'home').rename(destination / 'data')
        (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        (destination / 'INCOMPLETE').unlink()
    return {'path': str(destination / 'data'), 'projectCount': len(manifest['projects']), 'active': False}
