"""Durable local operation receipts and a shared admission barrier.

Receipts live outside the data being replaced. An interrupted publication keeps
the barrier closed until the supervisor has recovered its filesystem journal.
Only trusted worker code can borrow the barrier; HTTP/MCP payloads cannot.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid
from functools import wraps

from hub_lifecycle import atomic_json, file_lock
from hub_launcher import external_path, read_json, backup_home
from hub_backup import BackupError

_local = threading.local()
PENDING = ('queued', 'running')


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def _timestamp_epoch(value, fallback=None):
    """Parse persisted upload timestamps without making reads mutate time."""
    for candidate in (value, fallback):
        if isinstance(candidate, str):
            try:
                return datetime.fromisoformat(candidate).timestamp()
            except ValueError:
                continue
        if isinstance(candidate, (int, float)):
            return candidate
    return time.time()


def configuration_path(registry):
    value = os.environ.get('PROJECT_HUB_INSTALLATION_CONFIG')
    if not value:
        return None
    path = external_path(value)
    try:
        config = read_json(path)
    except (OSError, ValueError):
        return None
    try:
        if external_path(config.get('dataHome', '')) != registry.home.resolve():
            return None
    except ValueError:
        return None
    return path


def backup_directory(registry):
    configured = os.environ.get('PROJECT_HUB_CONFIGURED_HOME')
    explicit = os.environ.get('PROJECT_HUB_BACKUP_HOME')
    if configured and explicit and external_path(configured) == registry.home.resolve():
        return external_path(explicit)
    path = configuration_path(registry)
    if path:
        return external_path(backup_home(read_json(path)))
    return external_path(registry.home.parent / (registry.home.name + '-backups'))


def operation_directory(registry):
    configured = os.environ.get('PROJECT_HUB_CONFIGURED_HOME')
    explicit = os.environ.get('PROJECT_HUB_OPERATION_HOME')
    if configured and explicit and external_path(configured) == registry.home.resolve():
        return external_path(explicit)
    path = configuration_path(registry)
    return external_path(path.parent / 'operations' if path else
                         registry.home.parent / (registry.home.name + '-operations'))


def normalize_origin(value=None, *, section='data'):
    if value is None:
        return {'section': section}
    if not isinstance(value, dict) or set(value) - {'section', 'project'}:
        raise BackupError('Invalid operation origin')
    if value.get('section') not in ('data', 'backups', 'settings', 'projects'):
        raise BackupError('Invalid operation section')
    project = value.get('project')
    if project is not None and (not isinstance(project, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', project)):
        raise BackupError('Invalid origin project')
    return dict(value)


@contextmanager
def internal(registry):
    homes = getattr(_local, 'homes', set())
    previous = homes.copy()
    _local.homes = homes | {str(registry.home.resolve())}
    try:
        yield
    finally:
        _local.homes = previous


def trusted(registry):
    return str(registry.home.resolve()) in getattr(_local, 'homes', set())


class Operations:
    def __init__(self, registry):
        self.registry = registry
        self.home = operation_directory(registry)
        self.jobs = self.home / 'jobs'

    def path(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch('[0-9a-f]{32}', identifier):
            raise BackupError('Invalid operation identifier')
        return external_path(self.jobs / (identifier + '.json'))

    def save(self, row):
        atomic_json(self.path(row['id']), row)

    def read(self, identifier):
        path = self.path(identifier)
        # Windows can briefly deny opening a file while its atomic replacement
        # is completing. Readers must not turn that sharing race into HTTP 500.
        deadline = time.monotonic() + .5
        while True:
            try:
                with path.open('rb') as stream:
                    raw = stream.read(4_000_001)
                break
            except PermissionError:
                if os.name != 'nt' or time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
        if len(raw) > 4_000_000:
            raise BackupError('Operation receipt is too large')
        row = json.loads(raw)
        if not isinstance(row, dict) or row.get('id') != identifier:
            raise BackupError('Invalid operation receipt')
        if row.get('status') in PENDING and not row.get('supervised'):
            old = time.time() - row.get('createdEpoch', time.time()) > 30
            if row['status'] == 'running' or old:
                try:
                    with file_lock(self.jobs / (identifier + '.lock')):
                        row.update(status='interrupted', finishedAt=timestamp(),
                                   error='Operation interrupted after worker process loss')
                        self.save(row)
                except TimeoutError:
                    pass
        finished = row.get('finishedAt')
        end = datetime.fromisoformat(finished).timestamp() if isinstance(finished, str) else finished if isinstance(finished, (int, float)) else time.time()
        row['elapsed'] = max(0, end - row.get('createdEpoch', time.time()))
        return row

    def catalog(self):
        if not self.jobs.is_dir():
            return []
        rows = []
        for path in self.jobs.glob('*.json'):
            if re.fullmatch('[0-9a-f]{32}', path.stem):
                rows.append(self.read(path.stem))
        return sorted(rows, key=lambda row: row.get('createdEpoch', 0), reverse=True)

    def register(self, body, request_id, *, supervised=False, section='data'):
        if not isinstance(body, dict) or not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id):
            raise BackupError('Use a unique 32-character hexadecimal request ID')
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        origin = normalize_origin(body.get('origin'), section=section)
        self.jobs.mkdir(parents=True, exist_ok=True)
        with file_lock(self.home / 'admission.lock', timeout=2):
            existing = self.catalog()
            for prior in existing:
                if prior.get('requestId') == request_id:
                    if prior.get('fingerprint') != fingerprint:
                        raise BackupError('Request ID was reused for different storage changes')
                    return prior, False
            if any(prior.get('status') in PENDING or prior.get('blocking') for prior in existing):
                raise BackupError('Дождитесь завершения текущей операции с данными перед запуском следующей')
            if status(self.registry)['writesPaused']:
                from backup_session import BackupBusy
                raise BackupBusy('Дождитесь завершения текущей операции с данными перед запуском следующей')
            row = dict(id=uuid.uuid4().hex, requestId=request_id, fingerprint=fingerprint,
                       action=body['action'], status='queued', phase='waiting',
                       createdAt=timestamp(), createdEpoch=time.time(), origin=origin,
                       dataHome=str(self.registry.home), supervised=supervised,
                       payload=body, progress={})
            self.save(row)
            return row, True

    def start(self, body, request_id, execute):
        row, created = self.register(body, request_id)
        if created:
            from hub_lifecycle import control_directory
            worker = threading.Thread(target=self.run, args=(row['id'], execute),
                                      daemon=control_directory() is None, name='hub-storage-operation')
            worker.start()
        return row

    def run(self, identifier, execute):
        self.jobs.mkdir(parents=True, exist_ok=True)
        with file_lock(self.jobs / (identifier + '.lock')):
            row = self.read(identifier)
            if row['status'] != 'queued':
                return
            from runtime_diagnostics import record, exception, resources
            last_progress = [None, None, 0.0]
            last_context = {}
            def report(value):
                if value.get('phase') != last_context.get('phase'):
                    last_context.clear()
                last_context.update(value)
                now=time.monotonic()
                phase=value.get('phase')
                complete=value.get('completed')
                total=value.get('total')
                final=type(complete) in (int,float) and type(total) in (int,float) and total>0 and complete>=total
                if phase==last_progress[0] and value.get('step')==last_progress[1] and now-last_progress[2]<.25 and not final:
                    return
                last_progress[:]=[phase,value.get('step'),now]
                current = self.read(identifier)
                current.update(phase=value.get('phase', current['phase']), progress=value)
                self.save(current)
                record('operation.progress',operationId=identifier,action=current['action'],phase=current['phase'],
                       progress={key:value[key] for key in ('completed','total','unit','step','currentFile',
                                'detailPhase','detailStep','reused') if key in value},resources=resources())
            try:
                # Queued workers retain their own OS lease while waiting.
                with file_lock(self.home / 'execution.lock', timeout=3600):
                    row.update(status='running', phase='preparing', startedAt=timestamp())
                    self.save(row)
                    payload = row['payload']
                    choices = {key:payload[key] for key in ('id','mode','includeGlobals','expected','path') if key in payload}
                    if isinstance(payload.get('projects'),list):
                        choices['projects'] = [project for project in payload['projects'][:100] if isinstance(project,str)]
                        choices['projectCount'] = len(payload['projects'])
                    if isinstance(payload.get('resolutions'),dict):
                        choices['resolutions'] = {key:value for key,value in list(payload['resolutions'].items())[:100]
                                                  if isinstance(key,str) and isinstance(value,str)}
                    record('operation.started',operationId=identifier,requestId=row['requestId'],action=row['action'],
                           phase=row['phase'],choices=choices,resources=resources())
                    with internal(self.registry):
                        result = execute(row['payload'], report)
                    row = self.read(identifier)
                    if isinstance(result, dict) and result.get('deferred'):
                        row.update(status='running', phase='waiting-for-restart', supervised=True,
                                   blocking=True, publication=result['publication'])
                        self.save(row)
                        record('operation.deferred',operationId=identifier,action=row['action'],phase=row['phase'])
                        return
                    row.update(status='succeeded', phase='ready', result=result)
            except BaseException as error:
                exception('operation.failed',error,operationId=identifier,action=row.get('action'),phase=last_context.get('phase') or row.get('phase'),
                          step=last_context.get('step'),currentFile=last_context.get('currentFile'),resources=resources())
                row = self.read(identifier)
                row.update(status='failed', error=str(error)[:1000],
                           phase=last_context.get('phase',row.get('phase')),
                           progress=dict(last_context) if last_context else row.get('progress',{}))
                if isinstance(getattr(error, 'body', None), dict):
                    row['errorBody'] = error.body
            row['finishedAt'] = timestamp()
            self.save(row)
            record('operation.finished',operationId=identifier,action=row['action'],status=row['status'],phase=row['phase'],resources=resources())


def status(registry):
    from backup_session import active
    from hub_lifecycle import catalog
    rows = Operations(registry).catalog()
    # Old receipts are still visible, but cannot redirect active storage.
    lifecycle = catalog()
    known = {row['id'] for row in rows}
    rows += [row for row in lifecycle['operations'] if row['id'] not in known]
    from backup_api import Backups
    backups = Backups(registry)
    for path in backups.jobs_home.glob('*.json'):
        if re.fullmatch('[0-9a-f]{32}', path.stem) and path.stem not in known:
            rows.append(backups.job(path.stem))
    for path in backups.home.glob('*.json'):
        if not re.fullmatch('[0-9a-f]{32}', path.stem):
            continue
        upload = backups._read(path.stem)
        if not upload.get('uploadRequestId'):
            continue
        uploading = upload.get('state') == 'uploading'
        if uploading and time.time() - upload.get('uploadUpdated', time.time()) > 900:
            upload['state'] = 'upload-interrupted'
            upload['finishedAt'] = timestamp()
            backups._save(upload)
            uploading = False
        terminal = not uploading
        started = upload.get('startedAt') or upload.get('createdAt')
        finished = upload.get('finishedAt')
        if upload.get('state') in ('preview', 'rejected') and upload.get('uploadReceivedAt'):
            finished = upload['uploadReceivedAt']
        # Legacy upload metadata has no finishedAt.  Its last durable update
        # is the closest terminal boundary; never use the current read time.
        if terminal and not finished:
            finished = upload.get('uploadUpdated') or upload.get('createdAt')
        started_epoch = _timestamp_epoch(started, upload.get('createdAt'))
        finished_epoch = _timestamp_epoch(finished, started) if terminal else None
        state = upload.get('state')
        rows.append(dict(id=upload['id'], requestId=upload['uploadRequestId'], action='upload-start',
                         status='running' if uploading else 'interrupted' if state == 'upload-interrupted' else
                         'failed' if state in ('aborted', 'rejected', 'cancelled') else 'succeeded',
                         phase='upload' if uploading else 'complete', workflowId='upload:' + upload['id'],
                         origin=upload.get('uploadOrigin', {'section': 'backups'}),
                         createdAt=upload['createdAt'], startedAt=started,
                         **({'finishedAt': finished} if terminal else {}),
                         elapsed=max(0, (finished_epoch if terminal else time.time()) - started_epoch),
                         payload={'id': upload['id']},
                         progress={'completed': upload.get('offset', 0), 'total': upload['size'], 'unit': 'bytes'}))
    paused = any(row.get('status') in PENDING or row.get('blocking') for row in rows)
    snapshot = active(registry) is not None if hasattr(registry, 'database') else False
    return {'writesPaused': paused or snapshot, 'reason': 'storage_operation' if paused else
            'backup_snapshot' if snapshot else None, 'operations': rows}


def ensure_writable(registry):
    if trusted(registry):
        return
    from backup_session import BackupBusy
    if status(registry)['writesPaused']:
        raise BackupBusy('A storage operation is in progress; viewing is available, retry changes after completion')


def read_handler(function):
    """GET can maintain derived read caches, but never admits a user mutation."""
    @wraps(function)
    def wrapped(handler, *args, **kwargs):
        registry = getattr(handler.server, 'registry', None)
        if registry is None:
            return function(handler, *args, **kwargs)
        with internal(registry):
            return function(handler, *args, **kwargs)
    return wrapped
