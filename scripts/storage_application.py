"""Prepare imports off-line, then publish through the owned runtime supervisor."""
from contextlib import ExitStack, nullcontext
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from hub_backup import BackupError
from hub_import import prepared_import, stage_progress
from hub_launcher import external_path, read_json, validate_config, backup_home
from storage_operations import Operations, configuration_path, backup_directory, timestamp


def folder_preview(registry, body):
    if set(body) - {'action', 'dataHome', 'backupHome', 'confirmed', 'requestId', 'origin', 'background'} or \
            not {'dataHome', 'backupHome', 'confirmed'} <= set(body):
        raise BackupError('Choose both the data and backup folders')
    data = external_path(body['dataHome'])
    backup = external_path(body['backupHome'])
    if data == backup or data in backup.parents or backup in data.parents:
        raise BackupError('Папки данных и резервных копий не должны совпадать или находиться одна внутри другой')
    old = registry.home.resolve()
    from project_portal import ROOT
    for path in (data, backup):
        if path == ROOT or path in ROOT.parents or ROOT in path.parents:
            raise BackupError('Папки данных и копий должны находиться отдельно от программы')
    for project in registry.list(include_deleted=True)['projects']:
        for root in project.get('roots', []):
            code = Path(root).resolve()
            for path in (data, backup):
                if path == code or path in code.parents or code in path.parents:
                    raise BackupError('Папки данных и копий должны находиться отдельно от папок кода проектов')
    for path in (data, backup):
        if path.exists() and not path.is_dir():
            raise BackupError('Выберите папку, а не файл')
        parent = path
        while not parent.exists():
            parent = parent.parent
        if not os.access(parent, os.W_OK):
            raise BackupError('Нет доступа на запись к выбранной папке')
    if data != old:
        if data in old.parents or old in data.parents:
            raise BackupError('Новая папка данных не должна находиться внутри текущей или содержать её')
        if data.exists() and next(data.iterdir(), None) is not None:
            raise BackupError('Новая папка данных не пуста. Выберите пустую папку; для добавления данных используйте импорт')
    path = configuration_path(registry)
    if not path:
        raise BackupError('Откройте Hub через ярлык, чтобы изменять общие папки этой установки')
    return dict(dataHome=str(data), backupHome=str(backup), oldDataHome=str(old),
                oldBackupHome=str(backup_directory(registry)), archives='remain', restartRequired=True)


def _portable_instructions(home, destination):
    path = home / 'instructions/location.json'
    if path.is_file():
        value = json.loads(path.read_text(encoding='utf-8'))
        owned = home / 'instructions/project-hub-user'
        if (owned / 'SKILL.md').is_file():
            value['root'] = str(destination / 'instructions/project-hub-user')
            value.pop('packageRoot', None)
            path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')


def start(registry, body):
    from hub_lifecycle import control_directory, supervisor_alive
    control = control_directory()
    if control is None or not supervisor_alive(control):
        raise BackupError('Откройте Hub через ярлык: применение данных требует управляемого перезапуска сервера')
    action = body.get('action')
    if action == 'change-folders':
        preview = folder_preview(registry, body)
        if body['confirmed'] is not True:
            return {'preview': preview}
    elif action == 'apply-import':
        allowed = {'action', 'id', 'expected', 'mode', 'projects', 'resolutions',
                   'includeGlobals', 'confirmed', 'requestId', 'origin', 'background', 'expectedActive'}
        if set(body) - allowed or not {'id', 'expected', 'mode', 'confirmed', 'requestId'} <= set(body):
            raise BackupError('Use the inspected copy, import mode and request ID')
        if body['confirmed'] is not True:
            raise BackupError('Подтвердите импорт после проверки проектов и конфликтов')
        if body['mode'] not in ('add', 'replace-all') or type(body.get('includeGlobals', False)) is not bool:
            raise BackupError('Select add or replace-all and an explicit global-settings choice')
    else:
        raise BackupError('Unsupported active-storage operation')
    operations = Operations(registry)
    request = body.get('requestId')
    def execute(payload, progress):
        return prepare(registry, payload, operations, progress)
    return {'operation': operations.start(body, request, execute)}


def prepare(registry, body, operations, progress):
    from backup_api import Backups
    from storage_merge import revision, build_candidate, verified_source
    from storage_preparation import prepare as migrate
    from hub_lifecycle import control_directory, supervisor_alive
    config_path = configuration_path(registry)
    if config_path is None:
        raise BackupError('The saved configuration no longer matches this server; reopen Hub')
    original = validate_config(read_json(config_path))
    incoming_record = None
    incoming_snapshot = None
    if body['action'] == 'apply-import':
        incoming_record = prepared_import(registry, body['id'], expected=body['expected'])
        progress({'phase':'verifying','step':'prepared-source','reused':True})
        incoming_snapshot = verified_source(incoming_record['path'], incoming_record['normalizedRevision'])
    if body.get('expectedActive') and revision(registry.home) != body['expectedActive']:
        raise BackupError('Рабочие данные изменились после предварительного просмотра. Проверьте результат импорта ещё раз.')
    # Locate this receipt by its idempotent request, never by a caller's path.
    row = next(row for row in operations.catalog() if row['requestId'] == body['requestId'])
    identifier = row['id']
    work = external_path(operations.home / 'work' / identifier)
    work.mkdir(parents=True, exist_ok=False)
    backups = Backups(registry)
    progress({'phase': 'snapshot', 'step':'current-backup'})
    current = work / 'current'
    backup = backups.execute({'action': 'create'}, progress=stage_progress(progress, 'snapshot', 'current-backup'),
                             _snapshot_destination=current)['backup']
    backup_row = backups._read(backup['id'])
    backup_row.update(origin='before-import' if body['action'] == 'apply-import' else 'before-move', operationId=identifier)
    backups._save(backup_row)
    current_row = operations.read(identifier)
    current_row['safetyBackupId'] = backup['id']
    operations.save(current_row)
    progress({'phase':'verifying','step':'current-format'})
    migrate(current)
    current_revision = revision(current)
    if body.get('expectedActive') and current_revision != body['expectedActive']:
        raise BackupError('Рабочие данные изменились во время подготовки. Откройте предварительный просмотр ещё раз.')
    destination = registry.home.resolve()
    next_config = dict(original)
    next_config['backupHome'] = str(backup_directory(registry))
    if body['action'] == 'apply-import':
        incoming = Path(incoming_record['path'])
        progress({'phase':'verifying','step':'prepared-source', 'reused':True})
        candidate = destination.parent / ('.' + destination.name + '-publish-' + identifier)
        progress({'phase':'comparing','step':'import-compatibility'})
        from hub_lifecycle import home_lease
        with home_lease(incoming, create=False):
            result = build_candidate(current, incoming, candidate, mode=body['mode'],
                                     projects=body.get('projects'), resolutions=body.get('resolutions'),
                                     import_globals=body.get('includeGlobals', False),
                                     expected_active=current_revision, expected_incoming=incoming_record['normalizedRevision'],
                                     published_home=destination,
                                     incoming_snapshot=incoming_snapshot,
                                     progress=progress)
    else:
        preview = folder_preview(registry, body)
        destination = Path(preview['dataHome'])
        next_config.update(dataHome=str(destination), backupHome=preview['backupHome'])
        candidate = destination.parent / ('.' + destination.name + '-publish-' + identifier)
        shutil.copytree(current, candidate)
        result = {'path': str(destination), 'copied': destination != registry.home}
    progress({'phase':'verifying','step':'current-revision'})
    if revision(registry.home) != current_revision:
        raise BackupError('Текущие данные изменились во время подготовки. Импорт не применён; повторите проверку')
    # A destination-side staging directory makes the final rename atomic even
    # when the chosen data folder is on a different disk.
    stage = external_path(destination.parent / ('.' + destination.name + '-publish-' + identifier))
    # The candidate was already built on the destination device. Publication
    # only renames it; a second candidate-to-staging copy is unnecessary.
    _portable_instructions(stage, destination)
    progress({'phase':'verifying','step':'prepared-candidate'})
    candidate_revision = result['candidateRevision'] if body['action'] == 'apply-import' else revision(stage)
    if body['action'] == 'change-folders' and candidate_revision != current_revision:
        raise BackupError('Проверка подготовленных файлов не пройдена. Рабочие данные не изменены')
    control = control_directory()
    if not control or not supervisor_alive(control):
        raise BackupError('Supervisor stopped before publication; prepared data were not applied')
    publication = dict(source=str(registry.home), target=str(destination), candidate=str(candidate),
                       rollback=str(destination.parent / ('.' + destination.name + '-before-' + identifier)),
                       expectedActive=current_revision, expectedCandidate=candidate_revision,
                       originalConfig=original, nextConfig=validate_config(next_config),
                       backupId=backup['id'], safetyBackupHome=str(backups.home), state='prepared', result=result)
    return {'deferred': True, 'publication': publication}


def _validate_publication(row):
    publication = row['publication']
    identifier = row['id']
    source = external_path(publication['source'])
    target = external_path(publication['target'])
    stage = external_path(publication['candidate'])
    rollback = external_path(publication['rollback'])
    # Authorize the saved logical siblings before comparing physical paths.
    # Windows can redirect a newly created sibling after prepare has saved its
    # path; resolve() of that sibling then has a different physical parent.
    logical_target = Path(publication['target'])
    if Path(publication['candidate']) != logical_target.parent / ('.' + logical_target.name + '-publish-' + identifier) or \
            Path(publication['rollback']) != logical_target.parent / ('.' + logical_target.name + '-before-' + identifier):
        raise BackupError('Не удалось подтвердить папки применения импорта. Рабочие данные сохранены; подробности доступны в диагностике.')
    validate_config(publication['originalConfig'])
    validate_config(publication['nextConfig'])
    if external_path(publication['originalConfig']['dataHome']) != source or external_path(publication['nextConfig']['dataHome']) != target:
        raise BackupError('Publication configuration does not match its storage paths')
    return source, target, stage, rollback


def _broker_paths(row, operations, config_path, source, target, stage):
    from windows_storage_broker import identity
    publication = row['publication']
    paths = dict(source=str(source), target=str(target), candidate=str(stage),
                 rollback=str(target.parent / ('.' + target.name + '-before-' + row['id'])),
                 failedTarget=str(target.parent / ('.' + target.name + '-failed-' + row['id'])))
    if source == target and stage.parent != target.parent:
        shadow = external_path(stage.parent / target.name)
        paths.update(shadowSource=str(shadow),
                     shadowRollback=str(stage.parent / ('.' + target.name + '-shadow-before-' + row['id'])))
        if shadow.exists():
            publication['shadowIdentity'] = identity(shadow)
    publication.update(brokerPaths=paths, sourceIdentity=identity(source), candidateIdentity=identity(stage),
                       physicalReceiptPath=str(operations.path(row['id']).resolve()),
                       physicalConfigPath=str(config_path.resolve()))
    operations.save(row)


def _run_broker(action, row, config_path, *, application_home=None):
    from windows_storage_broker import run, BrokerError
    try:
        latest = run(action, row, config_path, application_home=application_home)
    except BrokerError as error:
        if error.row is not None and error.row is not row:
            row.clear(); row.update(error.row)
        raise
    if latest is not row:
        row.clear(); row.update(latest)


def rollback(row, operations, config_path, *, keep_paused=False):
    """Called only after the supervisor has drained every owned server."""
    from hub_lifecycle import atomic_json, home_lease
    source, target, stage, retained = _validate_publication(row)
    publication = row['publication']
    if publication.get('brokerRequired'):
        from windows_storage_broker import is_active, BrokerPendingError
        if is_active(row):
            raise BrokerPendingError('Переключение папки ещё выполняется. Дождитесь завершения.', row=row)
    if read_json(config_path) not in (publication['originalConfig'], publication['nextConfig']):
        raise BackupError('Конфигурация изменена извне. Данные сохранены; требуется проверить путь хранилища перед возвратом')
    with ExitStack() as leases:
        leases.enter_context(home_lease(source))
        if target != source:
            leases.enter_context(home_lease(target))
        if publication.get('brokerRequired') and not publication.get('brokerPaths'):
            from storage_merge import revision
            if not source.is_dir() or revision(source) != publication['expectedActive']:
                raise BackupError('Не удалось подтвердить прежнее хранилище. Данные сохранены для восстановления.')
        elif publication.get('brokerRequired') and publication.get('brokerPaths'):
            _run_broker('rollback', row, config_path)
            publication = row['publication']
        elif source == target and retained.is_dir():
            if source.exists():
                failed = external_path(source.parent / ('.' + source.name + '-failed-' + row['id']))
                source.rename(failed)
            retained.rename(source)
        elif source == target and publication['state'] in ('publishing', 'published'):
            from storage_merge import revision
            if not source.is_dir() or revision(source) != publication['expectedActive']:
                raise BackupError('Сохранённая прежняя папка отсутствует. Рабочие файлы не изменены; используйте проверенную резервную копию для восстановления.')
        elif source != target and not stage.exists() and publication['state'] != 'prepared' and target.exists():
            failed = external_path(target.parent / ('.' + target.name + '-failed-' + row['id']))
            target.rename(failed)
        if not source.is_dir():
            raise BackupError('Previous data folder is missing; manual recovery is required')
        if not publication.get('brokerRequired'):
            atomic_json(config_path, publication['originalConfig'])
        row.update(status='running' if keep_paused else 'failed', phase='starting' if keep_paused else 'ready',
                   blocking=keep_paused, rollback='succeeded', activeHome=str(source))
        if not keep_paused:
            row['finishedAt'] = timestamp()
        operations.save(row)


def finish_rollback(row, operations):
    row.update(status='failed', phase='ready', blocking=False, finishedAt=timestamp())
    operations.save(row)


def complete_recovery(config_path):
    from types import SimpleNamespace
    config = read_json(config_path)
    operations = Operations(SimpleNamespace(home=Path(config['dataHome'])))
    for row in operations.catalog():
        if row.get('rollback') == 'succeeded' and row.get('status') == 'running' and row.get('blocking'):
            finish_rollback(row, operations)


def recover(config_path, *, keep_paused=False):
    """Restore a known previous state before any DB is opened after a crash."""
    from types import SimpleNamespace
    from hub_lifecycle import atomic_json
    config = read_json(config_path)
    registry = SimpleNamespace(home=Path(config['dataHome']))
    operations = Operations(registry)
    for row in operations.catalog():
        if row.get('publication') and row.get('status') in ('running', 'interrupted'):
            try:
                if row['publication']['state'] == 'prepared' and not row['publication'].get('drainStarted'):
                    row.update(status='failed', blocking=False, finishedAt=timestamp(),
                               error='Подготовка прервана до применения. Рабочие данные не изменены.')
                    operations.save(row)
                else:
                    rollback(row, operations, config_path, keep_paused=keep_paused)
            except Exception as error:
                if getattr(error, 'pending', False):
                    # A live broker still owns the durable journal and renames.
                    # Never overwrite its state or race it with rollback.
                    raise
                row.update(status='interrupted', blocking=True, error=str(error))
                operations.save(row)
                raise BackupError('Storage recovery failed; data were preserved. ' + str(error)) from error
    return read_json(config_path)


def publish(row, operations, config_path, config, process, control, application_home, port, root, *, owned=None):
    """Drain, journal both renames, start and verify; caller handles failed drain."""
    from hub_lifecycle import _stop, _start, _ready, atomic_json, home_lease
    from storage_merge import revision
    source, target, stage, retained = _validate_publication(row)
    publication = row['publication']
    if source != external_path(config['dataHome']) or read_json(config_path) != publication['originalConfig']:
        raise BackupError('The active configuration changed before publication')
    publication['brokerRequired'] = os.name == 'nt' and stage.parent != target.parent
    with ExitStack() as leases:
        # Verify the large private candidate while the old HTTP runtime remains
        # available. Keep its lease through drain and publication.
        leases.enter_context(home_lease(stage))
        row.update(phase='verifying', blocking=True, supervised=True,
                   progress={'phase':'verifying','step':'prepared-candidate'})
        operations.save(row)
        if revision(stage) != publication['expectedCandidate']:
            raise BackupError('Подготовленные данные изменились. Рабочие данные не изменены; повторите предварительный просмотр.')
        row.update(phase='stopping', blocking=True, supervised=True)
        publication['drainStarted'] = True
        operations.save(row)
        atomic_json(control / 'switch.json', {'id': row['id']})
        _stop(process, control)
        # A failed drain never reaches any rename or configuration write.
        leases.enter_context(home_lease(source))
        if target != source:
            leases.enter_context(home_lease(target))
        if revision(source) != publication['expectedActive']:
            raise BackupError('Storage changed before publication; prepared data were not applied')
        if target != source and target.exists() and next(target.iterdir(), None) is not None:
            raise BackupError('Destination became nonempty; previous data were preserved')
        row['phase'] = 'publishing'
        if publication['brokerRequired']:
            _broker_paths(row, operations, config_path, source, target, stage)
            _run_broker('publish', row, config_path, application_home=application_home)
            publication = row['publication']
        else:
            _publish_direct(row, operations, config_path, source, target, stage, retained)
    next_control = root / ('runtime-' + uuid.uuid4().hex)
    next_control.mkdir()
    row['phase'] = 'starting'
    operations.save(row)
    next_process = _start(publication['nextConfig'], application_home, port, next_control)
    if owned is not None:
        owned[:] = [next_process, next_control]
    _ready(next_process, target, port)
    # Keep admission closed until the supervisor durably remembers the endpoint.
    row.update(phase='starting', activeHome=str(target))
    operations.save(row)
    return publication['nextConfig'], next_process, next_control


def _publish_direct(row, operations, config_path, source, target, stage, retained):
    from hub_lifecycle import atomic_json
    publication = row['publication']
    publication['state'] = 'retaining'
    operations.save(row)
    if source == target:
        source.rename(retained)
    elif target.exists():
        target.rmdir()  # Verified empty destination, never recursive deletion.
    publication['state'] = 'publishing'
    operations.save(row)
    stage.rename(target)
    publication['state'] = 'published'
    operations.save(row)
    atomic_json(config_path, publication['nextConfig'])


def complete(row, operations, *, execution_locked=False):
    publication = row['publication']
    target = publication['target']
    row.update(status='succeeded', phase='ready', blocking=False, finishedAt=timestamp(),
               activeHome=target, result=dict(publication['result'], path=target, activeHome=target,
                                             backupId=publication['backupId']))
    operations.save(row)
    cleanup_snapshot(row, operations, execution_locked=execution_locked)


def cleanup_snapshot(row, operations, *, execution_locked=False):
    """Remove only this successful operation's redundant current-data snapshot.

    The verified ZIP and retained previous active directory remain recovery
    sources. Cleanup failure cannot turn an already published import into an
    error or authorize deletion of another operation's files.
    """
    from hub_backup import digest
    from hub_lifecycle import file_lock
    from runtime_diagnostics import record, exception
    publication = row.get('publication', {})
    if (row.get('status') != 'succeeded' or row.get('phase') != 'ready' or
            publication.get('state') != 'published' or
            row.get('cleanup', {}).get('state') == 'complete'):
        return
    try:
        with nullcontext() if execution_locked else file_lock(operations.home / 'execution.lock', timeout=0):
            # path() validates the receipt ID before constructing any target.
            operations.path(row['id'])
            work = external_path(operations.home / 'work' / row['id'])
            snapshot = external_path(work / 'current')
            if snapshot.parent != work or work.parent != external_path(operations.home / 'work'):
                raise BackupError('Invalid snapshot cleanup path')
            protected = [external_path(publication[key]) for key in ('source', 'target', 'candidate', 'rollback')]
            if any(snapshot == path or path.is_relative_to(snapshot) or snapshot.is_relative_to(path)
                   for path in protected):
                raise BackupError('Snapshot cleanup overlaps publication data')
            archive_home = external_path(publication.get('safetyBackupHome') or backup_home(publication['originalConfig']))
            backup_id = publication['backupId']
            if not isinstance(backup_id, str) or not re.fullmatch('[0-9a-f]{32}', backup_id):
                raise BackupError('Invalid safety backup receipt ID')
            metadata_path = external_path(archive_home / (backup_id + '.json'))
            metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            archive = external_path(archive_home / (backup_id + '.zip'))
            if (metadata.get('id') != backup_id or metadata.get('operationId') != row['id'] or
                    metadata.get('origin') not in ('before-import', 'before-move') or
                    archive.stat().st_size != metadata.get('size') or digest(archive) != metadata.get('sha256')):
                raise BackupError('Preserve snapshot: safety backup proof is unavailable')
            if snapshot.exists():
                shutil.rmtree(snapshot)
            if work.is_dir() and not any(work.iterdir()):
                work.rmdir()
            row['cleanup'] = {'state':'complete', 'finishedAt':timestamp(), 'snapshot':str(snapshot)}
            operations.save(row)
            record('operation.snapshot_cleanup', operationId=row['id'], snapshot=str(snapshot))
    except TimeoutError:
        # Another operation may already own admission after durable completion.
        # Retaining a private snapshot is harmless and can be retried later.
        return
    except Exception as error:
        exception('operation.snapshot_cleanup_failed', error, operationId=row['id'])
