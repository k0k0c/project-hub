"""Local web adapter for the reusable backup format; bounded staged uploads."""
import base64
from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time
import uuid

from hub_backup import BackupError, MAX_BYTES, create_archive, digest, preview_archive, restore_copy, archive_summary

CHUNK_BYTES = 512 * 1024
REQUEST_LIMIT = 1024 * 1024


class Backups:
    def __init__(self, registry, runtime_version=None):
        self.registry = registry
        self.runtime_version = runtime_version
        from storage_operations import backup_directory
        self.home = backup_directory(registry)
        if self.home.is_symlink() or self.home.resolve() != self.home:
            raise BackupError('Папка резервных копий не должна быть ссылкой')
        self.home.mkdir(parents=True, exist_ok=True)
        self.jobs_home = self.home / 'jobs'
        if self.jobs_home.is_symlink() or self.jobs_home.resolve() != self.jobs_home:
            raise BackupError('Папка операций не должна быть ссылкой')
        self.jobs_home.mkdir(parents=True, exist_ok=True)

    def _id(self, value):
        if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
            raise BackupError('Неверный идентификатор архива')
        return value

    def _path(self, identifier, suffix):
        p = self.home / (self._id(identifier) + suffix)
        if p.is_symlink():
            raise BackupError('Ссылки в папке резервных копий не поддерживаются')
        return p

    def _job_path(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{32}', identifier):
            raise BackupError('Неверный идентификатор операции')
        path = self.jobs_home / (identifier + '.json')
        if path.is_symlink():
            raise BackupError('Ссылки в папке операций не поддерживаются')
        return path

    def _save_job(self, job):
        from project_portal import atomic_write
        atomic_write(self._job_path(job['id']), json.dumps(job, ensure_ascii=False))

    def _read_job(self, identifier):
        path = self._job_path(identifier)
        deadline = time.monotonic() + .25
        try:
            while True:
                try:
                    contents = path.read_text(encoding='utf-8')
                    break
                except PermissionError:
                    if os.name != 'nt' or time.monotonic() >= deadline:
                        raise
                    time.sleep(min(.05, max(0, deadline - time.monotonic())))
        except FileNotFoundError as error:
            raise BackupError('Операция не найдена') from error
        job = json.loads(contents)
        if not isinstance(job, dict) or job.get('id') != identifier:
            raise BackupError('Повреждены сведения об операции')
        queued_old = (job.get('status') == 'queued' and
                      job.get('createdEpoch') is not None and time.time() - job['createdEpoch'] > 30)
        if job.get('status') == 'running' or queued_old:
            from project_portal import Store
            try:
                with Store.lock_probe(self.jobs_home / (identifier + '.lock')).locked(timeout=0):
                    job.update(status='interrupted', finishedAt=datetime.now(timezone.utc).isoformat(),
                               error='Операция прервана после потери процесса')
                    self._save_job(job)
            except TimeoutError:
                pass  # A live worker retains the lease even during a long file.
        finished = job.get('finishedAt')
        # Older receipts did not persist a terminal timestamp.  Use their
        # creation time as a stable fallback instead of making elapsed time
        # grow on every status read.
        if job.get('status') in ('queued', 'running'):
            end = time.time()
        else:
            fallback = job.get('createdAt')
            end = (datetime.fromisoformat(finished).timestamp() if isinstance(finished, str)
                   else datetime.fromisoformat(fallback).timestamp() if isinstance(fallback, str)
                   else job.get('createdEpoch', time.time()))
        if job.get('createdEpoch') is not None:
            job['elapsed'] = max(0, end - job['createdEpoch'])
        return job

    def _read(self, identifier):
        p = self._path(identifier, '.json')
        try:
            value = json.loads(p.read_text(encoding='utf-8'))
        except FileNotFoundError as error:
            raise BackupError('Архив не найден') from error
        if not isinstance(value, dict) or value.get('id') != identifier:
            raise BackupError('Повреждены сведения об архиве')
        for key in ('archiveDeletion', 'copyDeletion'):
            receipts = value.get(key, {})
            if not isinstance(receipts, dict) or any(
                not isinstance(receipt, dict) or not isinstance(receipt.get('payload'), dict) or
                ('result' in receipt and not isinstance(receipt['result'], dict))
                for receipt in receipts.values()
            ):
                raise BackupError('Invalid deletion receipt metadata')
        if value.get('state') in ('restored', 'imported') and (
            not isinstance(value.get('restore'), dict) or
            not isinstance(value['restore'].get('path'), str)
        ):
            raise BackupError('Invalid copied storage metadata')
        return value

    def _save(self, row):
        from project_portal import atomic_write
        atomic_write(self._path(row['id'], '.json'), json.dumps(row, ensure_ascii=False))

    def _lock(self, timeout=10):
        from project_portal import Store
        return Store.lock_probe(self.home / 'writer.lock').locked(timeout=timeout)

    def _admission_lock(self, timeout=0):
        """Serialize short job registration without holding the archive lock."""
        from project_portal import Store
        return Store.lock_probe(self.jobs_home / 'admission.lock').locked(timeout=timeout)

    def catalog(self, *, page=None, page_size=20, history_page=1, sort='createdAt', direction='desc'):
        if page is not None and (type(page) is not int or page < 1 or page > 1000000 or
                type(history_page) is not int or not 1 <= history_page <= 1000000 or
                type(page_size) is not int or not 1 <= page_size <= 100 or
                sort not in ('createdAt', 'name', 'size') or direction not in ('asc', 'desc')):
            raise BackupError('Use valid backup pagination and sorting parameters')
        backups, copies, jobs = [], [], []
        for p in sorted(self.home.glob('*.json'), reverse=True):
            if not re.fullmatch('[0-9a-f]{32}', p.stem):
                continue
            row = self._read(p.stem)
            if row.get('state') in ('backup', 'preview', 'restored') and not row.get('archiveDeleted') and self._path(row['id'], '.zip').is_file():
                backups.append({k: row[k] for k in ('id', 'name', 'createdAt', 'size', 'sha256', 'projects')} |
                               {'verified': True, 'origin': row.get('origin', 'backup'),
                                'path': str(self._path(row['id'], '.zip'))})
            if row.get('state') in ('restored', 'imported') and not row.get('copyDeleted'):
                copies.append({'id': row['id'], **row['restore'], 'createdAt': row.get('restoredAt', row.get('createdAt')),
                               'origin': 'folder-import' if row['state'] == 'imported' else 'backup',
                               'active': Path(row['restore']['path']).resolve() == self.registry.home.resolve()})
        for p in sorted(self.jobs_home.glob('*.json'), reverse=True):
            if re.fullmatch('[0-9a-f]{32}', p.stem):
                try:
                    jobs.append(self._read_job(p.stem))
                except BackupError:
                    continue
        backups.sort(key=lambda row: (row.get(sort, 0 if sort == 'size' else ''), row['id']), reverse=direction == 'desc')
        jobs.sort(key=lambda row: (row.get('createdAt', ''), row['id']), reverse=True)
        copies.sort(key=lambda row: (row.get('createdAt', ''), row['id']), reverse=True)
        result = {'scope': 'all-projects', 'backupHome': str(self.home),
                  'backups': backups, 'restoreCopies': copies, 'jobs': jobs,
                  'capabilities': {'pagination': True, 'deleteArchive': True, 'deleteCopy': True}}
        if page is not None:
            active = [row for row in jobs if row.get('status') in ('queued', 'running')]
            history = [row for row in jobs if row not in active]
            def paginate(rows, number):
                pages = max(1, (len(rows) + page_size - 1) // page_size)
                number = min(number, pages)
                return rows[(number - 1) * page_size:number * page_size], {'page': number, 'pageSize': page_size, 'pages': pages, 'total': len(rows)}
            result['backups'], backup_page = paginate(backups, page)
            history, job_page = paginate(history, history_page)
            result.update(jobs=active + history, activeJobs=active, history=history,
                          pagination={'backups': backup_page, 'history': job_page, 'sort': sort, 'direction': direction})
        return result

    def _delete(self, body, progress=None):
        action = body['action']
        if set(body) != {'action', 'id', 'expected', 'confirmed', 'requestId'} or body['confirmed'] is not True:
            raise BackupError('Confirm deletion of the selected archive or inactive copy')
        self._id(body['requestId'])
        identifier = self._id(body['id'])
        row = self._read(identifier)
        receipt_key = 'archiveDeletion' if action == 'delete-archive' else 'copyDeletion'
        payload = {key: body[key] for key in ('id', 'expected', 'requestId')}
        receipts = row.setdefault(receipt_key, {})
        previous = receipts.get(body['requestId'])
        if previous and previous.get('payload') != payload:
            raise BackupError('A different deletion request is already recorded for this item')
        if previous and previous.get('result'):
            return previous['result']
        if any(not receipt.get('result') for key, receipt in receipts.items() if key != body['requestId']):
            raise BackupError('Complete the pending deletion request before starting another')
        if action == 'delete-archive':
            if row.get('archiveDeleted'):
                raise BackupError('The archive has already been deleted')
            if row.get('state') not in ('backup', 'preview', 'restored') or row.get('sha256') != body['expected']:
                raise BackupError('The archive changed after confirmation')
            target = self._path(identifier, '.zip')
            if not previous and (not target.is_file() or digest(target) != body['expected']):
                raise BackupError('The archive file changed after verification')
            receipts[body['requestId']] = {'payload': payload}
            self._save(row)
            target.unlink(missing_ok=True)
            row['archiveDeleted'] = True
        else:
            from hub_import import copied_home, inspect_home
            from hub_lifecycle import home_lease, control_directory, file_lock, read_job
            from hub_launcher import external_path
            target = copied_home(self, identifier)
            if target == self.registry.home or target.is_relative_to(self.registry.home) or self.registry.home.is_relative_to(target):
                raise BackupError('Active storage cannot be deleted')
            # Reject an administrative copy that has been repurposed as a code workspace.
            for project in self.registry.list(include_deleted=True)['projects']:
                for root in project.get('roots', []):
                    path = Path(root).resolve()
                    if path == target.parent or path.is_relative_to(target.parent) or target.parent.is_relative_to(path):
                        raise BackupError('The copied storage is referenced by a code workspace')
            control = control_directory()
            admission = file_lock(control.parent / 'activation-admission.lock', timeout=0) if control else nullcontext()
            with admission, home_lease(target):
                if control:
                    for job_file in (control.parent / 'activation-jobs').glob('*.json'):
                        job = read_job(job_file)
                        if job.get('status') in ('queued', 'running') and (job['payload'].get('copyId') == identifier or job['payload'].get('target') == str(target)):
                            raise BackupError('The copied storage is being activated')
                if not previous and inspect_home(target)['revision'] != body['expected']:
                    raise BackupError('The copied storage changed after inspection')
                # Every recursive target is exact, registered and checked before removal.
                # Refuse nested links/reparse points instead of traversing them.
                for directory, names, files in os.walk(target, followlinks=False):
                    for name in [*names, *files]:
                        external_path(Path(directory) / name)
                receipts[body['requestId']] = {'payload': payload}
                self._save(row)
                if progress:
                    progress({'phase': 'deleting'})
                if target.exists():
                    shutil.rmtree(target)
                row['copyDeleted'] = True
        result = {'id': identifier, 'deleted': True, 'action': action}
        receipts[body['requestId']] = {'payload': payload, 'result': result, 'deletedAt': datetime.now(timezone.utc).isoformat()}
        self._save(row)
        return result

    def download(self, identifier):
        row = self._read(identifier)
        if row.get('state') not in ('backup', 'preview', 'restored'):
            raise BackupError('Архив ещё не готов')
        path = self._path(identifier, '.zip')
        if not path.is_file() or path.stat().st_size != row['size']:
            raise BackupError('Файл архива отсутствует или изменился')
        return path, row['name']

    def upload_replay(self, body):
        if not isinstance(body, dict) or body.get('action') != 'upload-start' or not body.get('requestId'):
            return None
        if set(body) - {'action', 'name', 'size', 'requestId', 'origin'} or not {'name', 'size'} <= set(body):
            raise BackupError('Неизвестная операция или неверные поля запроса')
        self._id(body['requestId'])
        for metadata in self.home.glob('*.json'):
            if re.fullmatch('[0-9a-f]{32}', metadata.stem):
                existing = self._read(metadata.stem)
                if existing.get('uploadRequestId') == body['requestId']:
                    if existing['name'] != body['name'] or existing['size'] != body['size']:
                        raise BackupError('Идентификатор загрузки уже используется для другого архива')
                    return {'id': existing['id'], 'offset': existing.get('offset', 0),
                            'startedAt': existing.get('startedAt', existing.get('createdAt'))}
        return None

    def execute(self, body, progress=None, *, _lock_held=False, _snapshot_destination=None, _inspect_source=False):
        if not isinstance(body, dict):
            raise BackupError('Требуется объект запроса')
        action = body.get('action')
        upload_request = upload_origin = None
        if action == 'upload-start':
            replay = self.upload_replay(body)
            if replay is not None:
                return replay
            from storage_operations import normalize_origin
            upload_request = body.get('requestId')
            if upload_request is not None:
                self._id(upload_request)
            upload_origin = normalize_origin(body.get('origin'), section='backups')
            body = {key: value for key, value in body.items() if key not in ('origin', 'requestId')}
        if action in ('delete-archive', 'delete-copy'):
            with self._lock() if not _lock_held else nullcontext():
                return self._delete(body, progress)
        if action == 'upgrade-copy':
            if set(body) != {'action', 'id', 'expected', 'confirmed'}:
                raise BackupError('Use the copied storage ID and its exact preview revision')
            from hub_import import storage_action
            with self._lock() if not _lock_held else nullcontext():
                if progress:
                    progress({'phase': 'verifying'})
                return storage_action(self.registry, body)
        if action == 'import-folder':
            if set(body) != {'action','path','expected'}:
                raise BackupError('Use a folder path and its exact preview revision')
            from hub_import import copy_folder
            with self._lock() if not _lock_held else nullcontext():
                identifier = uuid.uuid4().hex
                target = self.home / 'prepared' / identifier
                result = copy_folder(body['path'], target, expected=body['expected'],
                                     active_home=self.registry.home, progress=progress,
                                     **({'inspect_and_copy':True} if _inspect_source else {}))
                source_preview = result.pop('sourcePreview', None)
                self._save({'id': identifier, 'state': 'imported', 'restore': result, 'origin': 'folder-import',
                            'sourcePath': str(Path(body['path']).resolve()), 'createdAt': datetime.now(timezone.utc).isoformat()})
                return dict(result, copyId=identifier, **({'sourcePreview':source_preview} if source_preview else {}))
        fields = {'create': {'action'}, 'upload-start': {'action', 'name', 'size'},
                  'upload-chunk': {'action', 'id', 'offset', 'data'},
                  'upload-complete': {'action', 'id'},
                  'upload-abort': {'action', 'id'},
                  'restore-copy': {'action', 'id', 'expectedSha256', 'confirmed'}}
        if action not in fields or set(body) != fields[action]:
            raise BackupError('Неизвестная операция или неверные поля запроса')
        with nullcontext() if _lock_held else self._lock():
            if action == 'create':
                identifier = uuid.uuid4().hex
                meta = create_archive(self.registry, self._path(identifier, '.zip'),
                                      {'application': 'Project Hub', 'runtimeVersion': self.runtime_version, 'backupWriter': '1.0'},
                                      **({'progress': progress} if progress else {}),
                                      **({'snapshot_destination': _snapshot_destination} if _snapshot_destination else {}))
                meta.update(id=identifier, name='project-hub-backup-' + identifier[:12] + '.zip', state='backup', origin='backup')
                self._save(meta)
                return {'backup': {k: v for k, v in meta.items() if k != 'state'}}
            if action == 'upload-start':
                size, name = body['size'], body['name']
                if type(size) is not int or not 0 < size <= MAX_BYTES:
                    raise BackupError('Недопустимый размер архива')
                if not isinstance(name, str) or not name or len(name) > 240 or any(c in name for c in '/\\\x00\r\n'):
                    raise BackupError('Недопустимое имя архива')
                pending = [json.loads(p.read_text(encoding='utf-8')) for p in self.home.glob('*.json')
                           if re.fullmatch('[0-9a-f]{32}', p.stem) and not p.is_symlink()]
                if sum(row.get('state') == 'uploading' for row in pending) >= 2:
                    raise BackupError('Уже загружаются два архива; завершите их загрузку')
                if upload_request:
                    for metadata in self.home.glob('*.json'):
                        if re.fullmatch('[0-9a-f]{32}', metadata.stem):
                            existing = self._read(metadata.stem)
                            if existing.get('uploadRequestId') == upload_request:
                                if existing['name'] != name or existing['size'] != size:
                                    raise BackupError('Идентификатор загрузки уже используется для другого архива')
                                return {'id': existing['id'], 'offset': existing.get('offset', 0),
                                        'startedAt': existing.get('startedAt', existing.get('createdAt'))}
                identifier = uuid.uuid4().hex
                self._path(identifier, '.partial').touch(exist_ok=False)
                started = datetime.now(timezone.utc).isoformat()
                self._save({'id': identifier, 'state': 'uploading', 'name': name, 'size': size, 'offset': 0,
                            'createdAt': started, 'startedAt': started,
                            'uploadRequestId': upload_request, 'uploadOrigin': upload_origin, 'uploadUpdated': time.time()})
                return {'id': identifier, 'offset': 0, 'startedAt': started}
            identifier = self._id(body['id'])
            row = self._read(identifier)
            if action == 'upload-abort':
                if row.get('state') not in ('uploading', 'rejected', 'cancelled', 'upload-interrupted'):
                    raise BackupError('Проверенный архив нельзя отменить как загрузку')
                self._path(identifier, '.partial').unlink(missing_ok=True)
                row['state'] = 'cancelled'
                row['finishedAt'] = datetime.now(timezone.utc).isoformat()
                self._save(row)
                return {'id': identifier, 'cancelled': True}
            if action == 'upload-chunk':
                if row.get('state') != 'uploading' or type(body['offset']) is not int or body['offset'] != row['offset']:
                    raise BackupError('Порядок загрузки изменился; повторите загрузку архива')
                if not isinstance(body['data'], str) or len(body['data']) > 4 * ((CHUNK_BYTES + 2) // 3):
                    raise BackupError('Слишком большой блок загрузки')
                try:
                    data = base64.b64decode(body['data'], validate=True)
                except (ValueError, UnicodeError) as error:
                    raise BackupError('Повреждён блок загрузки') from error
                if not data or len(data) > CHUNK_BYTES or row['offset'] + len(data) > row['size']:
                    raise BackupError('Блок превышает размер архива')
                with self._path(identifier, '.partial').open('r+b') as target:
                    target.truncate(row['offset'])  # A failed previous append never advances acknowledged state.
                    target.seek(row['offset'])
                    target.write(data)
                    target.flush()
                row['offset'] += len(data)
                row['uploadUpdated'] = time.time()
                if row['offset'] == row['size']:
                    row['uploadReceivedAt'] = datetime.now(timezone.utc).isoformat()
                self._save(row)
                return {'id': identifier, 'offset': row['offset']}
            if action == 'upload-complete':
                if row.get('state') in ('preview', 'restored'):
                    return {'id': identifier, 'name':row['name'], 'size':row['size'], 'sha256': row['sha256'], 'preview': row['preview'],
                            **({'copyId': identifier} if row['state'] == 'restored' and not row.get('copyDeleted') else {})}
                if row.get('state') != 'uploading' or row['offset'] != row['size']:
                    raise BackupError('Архив ещё не загружен полностью')
                path = self._path(identifier, '.partial')
                checksum = digest(path)
                target = self.home / 'prepared' / uuid.uuid4().hex
                try:
                    restored = restore_copy(path, target, checksum, progress=progress)
                    preview = archive_summary(json.loads((target / 'manifest.json').read_text(encoding='utf-8')))
                except Exception:
                    row['state'] = 'rejected'
                    row['finishedAt'] = datetime.now(timezone.utc).isoformat()
                    self._save(row)
                    raise
                path.rename(self._path(identifier, '.zip'))
                row.update(state='restored', restore=restored, restoredAt=datetime.now(timezone.utc).isoformat(),
                           sha256=checksum, preview=preview, projects=preview['projects'],
                           origin='upload', finishedAt=datetime.now(timezone.utc).isoformat())
                self._save(row)
                return {'id': identifier, 'name':row['name'], 'size':row['size'], 'sha256': checksum, 'preview': preview, 'copyId':identifier}
            if body['confirmed'] is not True or body['expectedSha256'] != row.get('sha256'):
                raise BackupError('Подтвердите восстановление проверенного архива')
            if row.get('state') == 'restored' and not row.get('copyDeleted'):
                return dict(row['restore'], copyId=identifier)
            if row.get('state') not in ('preview', 'backup', 'restored') or row.get('archiveDeleted'):
                raise BackupError('Сначала проверьте загруженный архив')
            target = self.home / 'prepared' / uuid.uuid4().hex
            result = restore_copy(self._path(identifier, '.zip'), target, row['sha256'], progress=progress)
            row.update(state='restored', restore=result, restoredAt=datetime.now(timezone.utc).isoformat())
            row.pop('copyDeleted', None)
            self._save(row)
            return dict(result, copyId=identifier)

    def job(self, identifier):
        if not self._job_path(identifier).is_file():
            from storage_operations import Operations
            operations = Operations(self.registry)
            if operations.path(identifier).is_file():
                return operations.read(identifier)
        return self._read_job(identifier)

    def start(self, body, requestId):
        if not isinstance(body, dict) or not isinstance(requestId, str) or not re.fullmatch('[0-9a-f]{32}', requestId):
            raise BackupError('Неверный идентификатор операции')
        action = body.get('action')
        from storage_operations import normalize_origin
        origin = normalize_origin(body.get('origin'), section='backups')
        body = {key: value for key, value in body.items() if key != 'origin'}
        if action not in ('create', 'upload-complete', 'restore-copy', 'import-folder', 'upgrade-copy', 'delete-archive', 'delete-copy'):
            raise BackupError('Эту операцию нельзя выполнить в фоне')
        fields = {'create': {'action'}, 'upload-complete': {'action', 'id'},
                  'restore-copy': {'action', 'id', 'expectedSha256', 'confirmed'},
                  'import-folder': {'action','path','expected'},
                  'upgrade-copy': {'action', 'id', 'expected', 'confirmed'},
                  'delete-archive': {'action', 'id', 'expected', 'confirmed', 'requestId'},
                  'delete-copy': {'action', 'id', 'expected', 'confirmed', 'requestId'}}
        if set(body) != fields[action]:
            raise BackupError('Неизвестная операция или неверные поля запроса')
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        try:
            with self._admission_lock(timeout=0):
                busy = False
                for path in self.jobs_home.glob('*.json'):
                    if not re.fullmatch('[0-9a-f]{32}', path.stem):
                        continue
                    try:
                        old = self._read_job(path.stem)
                    except BackupError:
                        continue
                    if old.get('requestId') == requestId:
                        if old.get('fingerprint') != fingerprint:
                            raise BackupError('Идентификатор операции уже используется для другого запроса')
                        return old
                    busy |= old.get('status') in ('queued', 'running')
                if busy:
                    raise BackupError('Дождитесь завершения текущей операции резервирования')
                from storage_operations import status
                state = status(self.registry)
                if any(row.get('status') in ('queued', 'running') or row.get('blocking')
                       for row in state['operations'] if not (action == 'upload-complete' and
                           row.get('action') == 'upload-start' and row.get('id') == body.get('id'))):
                    raise BackupError('Дождитесь завершения текущей операции с данными Hub')
                job = {'id': uuid.uuid4().hex, 'requestId': requestId, 'fingerprint': fingerprint,
                       'action': action, 'status': 'queued', 'phase': 'preparing',
                       'createdAt': datetime.now(timezone.utc).isoformat(), 'progress': {'completed': 0, 'total': 1}}
                if action == 'upload-complete':
                    job['workflowId'] = 'upload:' + body['id']
                job['origin'] = origin
                job['createdEpoch'] = time.time()
                self._save_job(job)
        except TimeoutError as error:
            raise BackupError('Операция уже регистрируется; повторите запрос') from error
        from hub_lifecycle import control_directory
        threading.Thread(target=self._run_job, args=(job['id'], body),
                         daemon=control_directory() is None).start()
        return job

    def _run_job(self, identifier, body):
        from project_portal import Store
        from storage_operations import internal, operation_directory
        from hub_lifecycle import file_lock
        with Store.lock_probe(self.jobs_home / (identifier + '.lock')).locked(), internal(self.registry), \
             file_lock(operation_directory(self.registry) / 'execution.lock', timeout=3600):
            self._run_leased_job(identifier, body)

    def _run_leased_job(self, identifier, body):
        from runtime_diagnostics import record, exception, resources
        job = self._read_job(identifier)
        if job.get('status') != 'queued':
            return  # A late thread never resurrects an interrupted request.
        job.update(status='running', startedAt=datetime.now(timezone.utc).isoformat(), leaseUntil=time.time() + 60)
        self._save_job(job)
        record('operation.started',operationId=identifier,action=body['action'],phase=job.get('phase'),resources=resources())
        last_report = [0, None]
        last_context = {}
        def report(value):
            if isinstance(value, dict):
                last_context.update(value)
            phase = value.get('phase') if isinstance(value, dict) else None
            if phase == last_report[1] and time.monotonic() - last_report[0] < .2:
                return
            last_report[:] = [time.monotonic(), phase]
            current = self._read_job(identifier)
            if current.get('status') != 'running':
                return
            current['progress'] = value if isinstance(value, dict) else {'completed': 0, 'total': 1}
            current['phase'] = current['progress'].get('phase', current.get('phase', 'preparing'))
            current['leaseUntil'] = time.time() + 60
            self._save_job(current)
            record('operation.progress',operationId=identifier,action=body['action'],phase=current['phase'],
                   progress=current['progress'],resources=resources())
        try:
            report({'phase': {'restore-copy': 'restoring', 'upload-complete': 'verifying'}.get(body['action'], 'preparing')})
            lock_deadline = time.monotonic() + 60
            while True:
                archive = ExitStack()
                try:
                    archive.enter_context(self._lock(timeout=0))
                except TimeoutError:
                    archive.close()
                    if time.monotonic() >= lock_deadline:
                        raise
                    report({'phase': 'waiting'})
                    time.sleep(.1)
                    continue
                try:
                    result = self.execute(body, progress=report, _lock_held=True)
                finally:
                    archive.close()
                break
            current = self._read_job(identifier)
            current.update(status='succeeded', phase='complete', finishedAt=datetime.now(timezone.utc).isoformat(),
                           leaseUntil=None, progress={'completed': 1, 'total': 1}, result=result)
            self._save_job(current)
            record('operation.finished',operationId=identifier,action=body['action'],status='succeeded',resources=resources())
        except BaseException as error:
            exception('operation.failed',error,operationId=identifier,action=body['action'],
                      phase=last_context.get('phase'),step=last_context.get('step'),
                      currentFile=last_context.get('currentFile'),resources=resources())
            current = self._read_job(identifier)
            current.update(status='failed', finishedAt=datetime.now(timezone.utc).isoformat(), leaseUntil=None,
                           error=str(error)[:400])
            self._save_job(current)
