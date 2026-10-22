"""Installed runtime supervision; state lives beside installation.json.

The server owns the data-home lease, including while its request workers run.
A supervisor serializes installation launches and switches only verified copies.
No network-facing operation accepts executable commands or a caller-chosen port.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
import uuid


class LifecycleError(ValueError):
    pass


@contextmanager
def file_lock(path, *, timeout=0, create=True):
    path = Path(path)
    if path.is_symlink() or path.resolve() != path.absolute():
        raise LifecycleError('Runtime locks cannot contain links or reparse points')
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b' if create else 'r+b') as stream:
        if not stream.seek(0, 2):
            if not create:
                raise LifecycleError('An existing runtime lock is empty')
            stream.write(b'0'); stream.flush()
        deadline = time.monotonic() + timeout
        while True:
            try:
                stream.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as error:
                if time.monotonic() >= deadline:
                    raise TimeoutError('A Hub process is using this data home or installation') from error
                time.sleep(.05)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


@contextmanager
def home_lease(home, *, create=True):
    from hub_launcher import external_path
    home = external_path(home)
    fingerprint = hashlib.sha256(os.path.normcase(str(home)).encode()).hexdigest()[:24]
    path = home.parent / ('.project-hub-home-' + fingerprint + '.lock')
    if not create and not path.exists():
        yield
        return
    with file_lock(path, create=create):
        yield


def atomic_json(path, value):
    from hub_launcher import external_path
    path = external_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix='.hub-state-', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as output:
            json.dump(value, output, ensure_ascii=False); output.write('\n')
            output.flush(); os.fsync(output.fileno())
        deadline = time.monotonic() + .5
        while True:
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if os.name != 'nt' or time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
    finally:
        Path(temporary).unlink(missing_ok=True)


def control_directory():
    value = os.environ.get('PROJECT_HUB_CONTROL')
    if not value:
        return None
    from hub_launcher import external_path
    return external_path(value)


def supervisor_alive(control):
    path = control.parent.parent / 'supervisor.lock'
    if not path.is_file():
        return False
    try:
        with file_lock(path, create=False):
            return False
    except TimeoutError:
        return True


def draining():
    control = control_directory()
    return bool(control and ((control / 'stop.json').is_file() or
                (control / 'switch.json').is_file() and supervisor_alive(control)))


def _publication_diagnostic_fields(row):
    """Return bounded lifecycle context for publication failures."""
    publication = row.get('publication') or {}
    fields = {key: publication.get(key) for key in
              ('source', 'target', 'candidate', 'rollback', 'normalization',
               'brokerRequired', 'brokerPaths', 'brokerPid', 'brokerPending', 'brokerError', 'brokerTraceback')
              if publication.get(key) is not None}
    fields.update(operationId=row.get('id'), requestId=row.get('requestId'),
                  action=row.get('action'), phase=publication.get('phase') or row.get('phase'),
                  publicationState=publication.get('state'),
                  drainStarted=bool(publication.get('drainStarted')))
    return fields


def shutdown_monitor(stop, *, interval=.2):
    """Call the native server shutdown path; let its workers finish accepted work."""
    control = control_directory()
    if control is None:
        return None
    def watch():
        while not (control / 'stop.json').is_file() and supervisor_alive(control):
            time.sleep(interval)
        from runtime_diagnostics import record
        record('server.shutdown_requested', reason='stop_request' if (control / 'stop.json').is_file() else 'supervisor_lost', control=str(control))
        stop()
    thread = threading.Thread(target=watch, name='hub-shutdown', daemon=True)
    thread.start()
    return thread


def catalog():
    control = control_directory()
    if control is None:
        return {'available': False, 'reason': 'supervisor_required', 'operations': []}
    if not supervisor_alive(control):
        return {'available': False, 'reason': 'supervisor_stopped', 'operations': []}
    from hub_launcher import external_path
    jobs = external_path(control.parent / 'activation-jobs')
    rows = []
    if jobs.is_dir() and not jobs.is_symlink():
        for path in sorted(jobs.glob('*.json'))[-20:]:
            if re.fullmatch('[0-9a-f]{32}', path.stem) and not path.is_symlink():
                rows.append(read_job(path))
    return {'available': True, 'operations': rows}


def activation_receipt(request_id, *, expected, copy_id=None, target=None):
    if not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id):
        raise LifecycleError('Use a unique 32-character hexadecimal request ID')
    control = control_directory()
    if control is None:
        return None
    from hub_launcher import external_path
    path = external_path(control.parent / 'activation-jobs' / (request_id + '.json'))
    if not path.is_file():
        return None
    if path.is_symlink():
        raise LifecycleError('Activation receipt cannot be a link')
    row = read_job(path)
    payload = row.get('payload', {})
    if payload.get('expected') != expected or payload.get('copyId') != copy_id or target is not None and payload.get('target') != str(target):
        raise LifecycleError('Request ID was reused for different storage changes')
    return row


def read_job(path):
    from hub_launcher import external_path
    path = external_path(path)
    with path.open('rb') as stream:
        raw = stream.read(32_001)
    if len(raw) > 32_000:
        raise LifecycleError('Activation receipt exceeds the supported size')
    row = json.loads(raw)
    if not isinstance(row, dict) or row.get('id') != path.stem or not isinstance(row.get('payload'), dict):
        raise LifecycleError('Activation receipt is invalid; preserve it for recovery')
    return row


def request_activation(home, *, current_home, request_id, expected, copy_id=None):
    control = control_directory()
    if control is None:
        raise LifecycleError('Start Hub from its installed launcher to activate a storage copy')
    if not supervisor_alive(control):
        raise LifecycleError('The runtime supervisor stopped; reopen the installed application')
    if not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id):
        raise LifecycleError('Use a unique 32-character hexadecimal request ID')
    prior = activation_receipt(request_id, expected=expected, copy_id=copy_id, target=home)
    if prior is not None:
        return prior
    from hub_import import inspect_home
    inspected = inspect_home(home)
    if inspected['revision'] != expected:
        raise LifecycleError('The copied storage changed; inspect it again before activation')
    from hub_launcher import external_path
    home = external_path(home)
    current_home = external_path(current_home)
    if home == current_home:
        raise LifecycleError('The selected storage is already active')
    payload = {'target': str(home), 'source': str(current_home), 'expected': expected, 'copyId':copy_id}
    jobs = external_path(control.parent / 'activation-jobs')
    with file_lock(control.parent / 'activation-admission.lock', timeout=1):
        jobs.mkdir(exist_ok=True)
        path = jobs / (request_id + '.json')
        if path.is_file():
            existing = read_job(path)
            if existing.get('payload') != payload:
                raise LifecycleError('Request ID was reused for different storage changes')
            return existing
        for candidate in jobs.glob('*.json'):
            row = read_job(candidate)
            if row.get('status') in ('queued', 'running'):
                raise LifecycleError('A storage activation is already pending')
        row = {'id': request_id, 'status': 'queued', 'payload': payload, 'createdAt': time.time()}
        atomic_json(path, row)
        atomic_json(control / 'switch.json', {'id': request_id})
        return row


def _start(config, application_home, port, control, *, expected=None):
    from hub_launcher import backup_home
    import runtime_diagnostics as diagnostics
    home = Path(config['dataHome'])
    environment = os.environ.copy()
    environment.update(PYTHONDONTWRITEBYTECODE='1', PROJECT_HUB_UI_LANGUAGE=config['language'],
                       PROJECT_HUB_CONTROL=str(control), PROJECT_HUB_CONFIGURED_HOME=str(home),
                       PROJECT_HUB_OPERATION_HOME=str(control.parent.parent / 'operations'),
                        PROJECT_HUB_BACKUP_HOME=str(backup_home(config)),
                        PROJECT_HUB_DIAGNOSTICS_HOME=str(control.parent.parent / 'diagnostics'),
                        PYTHONUNBUFFERED='1')
    environment.pop('PYTHONFAULTHANDLER', None)
    environment.pop('PROJECT_HUB_ASGI_CATALOG', None)
    environment.pop('PROJECT_HUB_ACTIVATION_EXPECTED', None)
    if expected is not None:
        environment['PROJECT_HUB_ACTIVATION_EXPECTED'] = expected
    command = [sys.executable, '-B', str(Path(application_home) / 'scripts/project_portal.py'),
               '--projects-home', str(home), '--standalone', 'serve', '--port', str(port), '--transport', 'auto']
    home.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(command, cwd=home, env=environment, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
    if type(getattr(process, 'pid', None)) is int:
        capture = diagnostics.capture_child(process, 'server', {'control':str(control),'codeRoot':str(application_home),'port':port})
        process._hub_diagnostics = capture
        def exited():
            process.wait()
            diagnostics.child_exit(process, 'server', expected=getattr(process, '_hub_expected_exit', False),
                                   control=str(control), codeRoot=str(application_home), port=port, thread=capture.get('thread'))
        watcher = threading.Thread(target=exited, name='hub-server-exit', daemon=True)
        process._hub_exit_watcher = watcher
        watcher.start()
    return process


def _ready(process, home, port, *, timeout=20):
    from hub_launcher import health, matches_home
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LifecycleError('The selected Hub runtime exited during startup')
        body = health(port)
        if matches_home(body, Path(home)):
            return
        if body is not None:
            raise LifecycleError('The runtime port belongs to another service or data home')
        time.sleep(.1)
    raise LifecycleError('The selected Hub runtime did not become ready')


def _stop(process, control, *, timeout=60):
    if process.poll() is not None:
        return
    process._hub_expected_exit = True
    from runtime_diagnostics import record
    record('server.stop_requested', childPid=getattr(process,'pid',None), control=str(control))
    atomic_json(control / 'stop.json', {'requestedAt': time.time()})
    try:
        process.wait(timeout=timeout)
        watcher = getattr(process,'_hub_exit_watcher',None)
        if isinstance(watcher,threading.Thread):
            watcher.join(2)
    except subprocess.TimeoutExpired as error:
        # Do not kill a writer or start another data home after an uncertain drain.
        raise LifecycleError('The previous runtime is still stopping; activation was not performed') from error


def supervise(config_path, *, application_home):
    import runtime_diagnostics as diagnostics
    diagnostics.configure('supervisor', directory=Path(config_path).parent / 'diagnostics',
                          codeRoot=str(application_home), config=str(config_path),
                          mode=os.environ.get('PROJECT_HUB_RUNTIME_MODE','source'))
    diagnostics.record('supervisor.started')
    previous_directory = Path.cwd()
    try:
        from hub_launcher import external_path
        # A custom caller may have pinned the swappable data directory as CWD.
        os.chdir(external_path(config_path, application_home=application_home).parent)
        return _supervise(config_path, application_home=application_home)
    except TimeoutError:
        raise  # Another owned supervisor is a normal launch race.
    except BaseException as error:
        diagnostics.exception('supervisor.failed',error,config=str(config_path),codeRoot=str(application_home))
        raise
    finally:
        if previous_directory.is_dir():
            os.chdir(previous_directory)
        diagnostics.record('supervisor.exited')
        diagnostics.cleanup()


def _supervise(config_path, *, application_home):
    from hub_launcher import configure, available_port, remember, remembered_port, state_path, validate_config, external_path
    from hub_instance import main_lease, publish
    from runtime_diagnostics import lifetime
    record_port = remember
    def remember(path, port, home, *, control=None):
        record_port(path, port, home, control=control)
        publish(config_path, application_home, home, port)
    config_path = external_path(config_path, application_home=application_home)
    with main_lease(), file_lock(config_path.with_name('supervisor.lock')), \
            lifetime(config_path.with_name('supervisor-lifetime.json')) as heartbeat:
        os.environ['PROJECT_HUB_INSTALLATION_CONFIG'] = str(config_path)
        config = configure(config_path, application_home=application_home)
        from storage_application import recover
        if (config_path.parent / 'operations/jobs').is_dir():
            config = recover(config_path, keep_paused=True)
        from storage_preparation import prepare
        from storage_operations import internal
        from types import SimpleNamespace
        heartbeat(force=True, phase='preparing')
        with home_lease(config['dataHome']), internal(SimpleNamespace(home=Path(config['dataHome']))):
            prepare(config['dataHome'])
        established = remembered_port(state_path(config_path, application_home), Path(config['dataHome']))
        port = available_port(established or config['port'])
        if established is not None and port != established:
            raise LifecycleError(f'The saved Hub endpoint port {established} is occupied; stop the other service and reopen Hub. The endpoint was not changed.')
        root = external_path(config_path.parent / 'lifecycle', application_home=application_home)
        root.mkdir(exist_ok=True)
        (root / 'shutdown.json').unlink(missing_ok=True)
        control = root / ('runtime-' + uuid.uuid4().hex)
        control.mkdir()
        jobs = external_path(root / 'activation-jobs', application_home=application_home)
        heartbeat(force=True, phase='starting', port=port)
        process = _start(config, application_home, port, control)
        _ready(process, config['dataHome'], port)
        heartbeat(force=True, phase='serving', port=port, serverPid=getattr(process, 'pid', None))
        remember(state_path(config_path, application_home), port, Path(config['dataHome']), control=control)
        from storage_application import complete_recovery
        recovery_pending = False
        try:
            complete_recovery(config_path)
        except (OSError, ValueError) as error:
            from runtime_diagnostics import exception
            exception('supervisor.recovery_receipt_failed',error)
            recovery_pending = True  # Keep recovery's write barrier until confirmation is durable.
        from hub_desktop import start_tray
        try:
            start_tray(config_path, application_home=application_home)
        except (OSError, ValueError) as error:
            from runtime_diagnostics import exception
            exception('supervisor.tray_start_failed', error)
        # A job interrupted by supervisor loss remains visible and never replays a
        # possibly accepted switch automatically. The user can inspect both homes.
        activation_readable = True
        if jobs.is_dir():
            try:
                pending = [(path, read_job(path)) for path in jobs.glob('*.json')]
                for path, row in pending:
                    if row.get('status') in ('queued', 'running'):
                        row.update(status='interrupted', error='Supervisor stopped before confirming activation')
                        atomic_json(path, row)
            except (OSError, ValueError) as error:
                # Preserve uncertain receipts and the current lifetime lease.
                # Activation admission remains blocked by the unreadable receipt.
                from runtime_diagnostics import exception
                exception('supervisor.activation_catalog_failed', error)
                activation_readable = False
        waiting_drain = None
        waiting_storage = None
        desktop_check = time.monotonic()
        while process.poll() is None or waiting_drain is not None or waiting_storage is not None:
            time.sleep(.25)
            heartbeat(phase='applying' if waiting_drain or waiting_storage else 'serving',
                      port=port, serverPid=getattr(process, 'pid', None))
            if (root / 'shutdown.json').is_file():
                _stop(process, control)
                return process.returncode
            if time.monotonic() - desktop_check > 3:
                # Recover a crashed tray adapter while the owned server is live.
                # The desktop lease prevents a second icon during slow startup.
                try:
                    start_tray(config_path, application_home=application_home)
                except (OSError, ValueError) as error:
                    from runtime_diagnostics import exception
                    exception('supervisor.tray_check_failed',error)
                desktop_check = time.monotonic()
            from types import SimpleNamespace
            from storage_operations import Operations, timestamp
            operations = Operations(SimpleNamespace(home=Path(config['dataHome'])))
            try:
                operation_rows = operations.catalog()
            except (OSError, ValueError) as error:
                # Metadata publication/read errors must not release the lifetime
                # lease of a healthy server. Admission still fails closed on the
                # same unknown receipts; no mutation/recovery is replayed here.
                from runtime_diagnostics import exception
                exception('supervisor.operation_catalog_failed',error)
                continue
            if recovery_pending:
                try:
                    complete_recovery(config_path)
                    recovery_pending = False
                except (OSError, ValueError) as error:
                    from runtime_diagnostics import exception
                    exception('supervisor.recovery_receipt_failed',error)
                    continue
            if waiting_storage is not None:
                if process.poll() is None:
                    continue
                row = next((row for row in operation_rows if row['id'] == waiting_storage['id']), waiting_storage)
                from windows_storage_broker import is_active
                if is_active(row):
                    continue
                from storage_application import rollback
                try:
                    rollback(row, operations, config_path, keep_paused=True)
                    config = row['publication']['originalConfig']
                    control = root / ('runtime-' + uuid.uuid4().hex); control.mkdir()
                    process = _start(config, application_home, port, control)
                    _ready(process, config['dataHome'], port)
                    remember(state_path(config_path, application_home), port, Path(config['dataHome']), control=control)
                    from storage_application import finish_rollback
                    finish_rollback(row, operations)
                except Exception as recovery_error:
                    if getattr(recovery_error, 'pending', False):
                        waiting_storage = row
                        continue
                    from runtime_diagnostics import exception
                    exception('supervisor.storage_recovery_failed', recovery_error,
                              operationId=row.get('id'), requestId=row.get('requestId'),
                              action=row.get('action'), phase=row.get('phase'),
                              publicationState=(row.get('publication') or {}).get('state'),
                              drainStarted=bool((row.get('publication') or {}).get('drainStarted')))
                    row.update(status='interrupted', blocking=True, rollback='failed', error=str(recovery_error))
                    operations.save(row)
                    raise
                waiting_storage = None
                continue
            maintenance = next((row for row in operation_rows if row.get('supervised') and
                                row.get('status') == 'running' and row.get('publication')), None)
            if maintenance is not None:
                from backup_api import Backups
                try:
                    backup_rows=Backups(SimpleNamespace(home=Path(config['dataHome']))).catalog()['jobs']
                except (OSError, ValueError) as error:
                    from runtime_diagnostics import exception
                    exception('supervisor.backup_catalog_failed',error)
                    continue
                if any(row.get('status') in ('queued', 'running') for row in backup_rows):
                    continue  # Let accepted non-daemon workers release their leases before drain.
                if any(row.get('status') in ('queued', 'running') and not row.get('supervised')
                        for row in operation_rows):
                    continue
                try:
                    execution = file_lock(operations.home / 'execution.lock')
                    execution.__enter__()
                except TimeoutError:
                    continue
                owned = [process, control]
                try:
                    from storage_application import publish as publish_storage
                    config, process, control = publish_storage(maintenance, operations, config_path, config,
                        process, control, application_home, port, root, owned=owned)
                    remember(state_path(config_path, application_home), port, Path(config['dataHome']), control=control)
                    from storage_application import complete
                    complete(maintenance, operations, execution_locked=True)
                except Exception as error:
                    from runtime_diagnostics import exception
                    exception('storage.publication_failed', error,
                              **_publication_diagnostic_fields(maintenance))
                    if getattr(error, 'pending', False):
                        waiting_storage = maintenance
                        continue
                    maintenance.update(error=str(error)[:1000])
                    if not maintenance['publication'].get('drainStarted'):
                        # A stale prepared request never owns the current runtime
                        # or configuration. Reject it without stopping or reverting
                        # a later, successfully published configuration.
                        maintenance.update(status='failed', blocking=False, finishedAt=timestamp())
                        operations.save(maintenance)
                        continue
                    process, control = owned
                    if process.poll() is None:
                        try:
                            _stop(process, control)
                        except LifecycleError:
                            maintenance.update(phase='waiting-for-drain', blocking=True)
                            operations.save(maintenance)
                            waiting_storage = maintenance
                            continue
                    from storage_application import rollback
                    try:
                        rollback(maintenance, operations, config_path, keep_paused=True)
                        config = maintenance['publication']['originalConfig']
                        control = root / ('runtime-' + uuid.uuid4().hex); control.mkdir()
                        process = _start(config, application_home, port, control)
                        _ready(process, config['dataHome'], port)
                        remember(state_path(config_path, application_home), port, Path(config['dataHome']), control=control)
                        from storage_application import finish_rollback
                        finish_rollback(maintenance, operations)
                    except Exception as recovery_error:
                        if getattr(recovery_error, 'pending', False):
                            waiting_storage = maintenance
                            continue
                        from runtime_diagnostics import exception
                        exception('supervisor.storage_recovery_failed', recovery_error,
                                  operationId=maintenance.get('id'), requestId=maintenance.get('requestId'),
                                  action=maintenance.get('action'), phase=maintenance.get('phase'),
                                  publicationState=(maintenance.get('publication') or {}).get('state'),
                                  drainStarted=bool((maintenance.get('publication') or {}).get('drainStarted')))
                        maintenance.update(status='interrupted', blocking=True, rollback='failed',
                                           rollbackError=str(recovery_error), finishedAt=timestamp())
                        operations.save(maintenance)
                        raise
                finally:
                    execution.__exit__(None, None, None)
                continue
            if waiting_drain is not None:
                if process.poll() is None:
                    continue
                path, row, original = waiting_drain
                try:
                    control = root / ('runtime-' + uuid.uuid4().hex); control.mkdir()
                    process = _start(original, application_home, port, control)
                    _ready(process, original['dataHome'], port)
                    config = original
                    remember(state_path(config_path, application_home), port, Path(original['dataHome']))
                    row.update(status='failed', rollback='succeeded', activeHome=original['dataHome'])
                except Exception as recovery_error:
                    from runtime_diagnostics import exception
                    exception('supervisor.storage_recovery_failed', recovery_error,
                              operationId=row.get('id'), requestId=row.get('requestId'),
                              action=row.get('action'), phase=row.get('phase'),
                              rollback=row.get('rollback'))
                    row.update(status='failed', rollback='failed', rollbackError=str(recovery_error))
                    row['finishedAt'] = time.time(); atomic_json(path, row)
                    raise
                row['finishedAt'] = time.time(); atomic_json(path, row)
                waiting_drain = None
                continue
            if not activation_readable or not jobs.is_dir():
                continue
            try:
                activation_rows = [(path, read_job(path)) for path in sorted(jobs.glob('*.json'))]
            except (OSError, ValueError) as error:
                from runtime_diagnostics import exception
                exception('supervisor.activation_catalog_failed', error)
                continue
            for path, row in activation_rows:
                if row.get('status') != 'queued':
                    continue
                row.update(status='running', phase='checking'); atomic_json(path, row)
                original = dict(config)
                stopped = False
                try:
                    payload = row['payload']
                    if payload['source'] != config['dataHome']:
                        raise LifecycleError('The active storage changed before the request was processed')
                    from backup_api import Backups
                    from types import SimpleNamespace
                    if any(job.get('status') in ('queued', 'running') for job in
                           Backups(SimpleNamespace(home=Path(config['dataHome']))).catalog()['jobs']):
                        raise LifecycleError('A backup or import is still running; activate after it finishes')
                    from hub_import import inspect_home
                    target = payload['target']
                    with home_lease(target):
                        inspected = inspect_home(target)
                        if inspected['revision'] != payload['expected']:
                            raise LifecycleError('Copied storage changed before activation')
                    # New runtime obtains its own lifetime lease before opening DBs.
                    row.update(phase='stopping'); atomic_json(path, row)
                    _stop(process, control); stopped = True
                    next_config = validate_config({**config, 'dataHome': target}, application_home=application_home)
                    control = root / ('runtime-' + uuid.uuid4().hex); control.mkdir()
                    process = _start(next_config, application_home, port, control, expected=payload['expected'])
                    _ready(process, target, port)
                    # Commit the installation pointer only after the selected
                    # runtime answers health for the exact copied data home.
                    atomic_json(config_path, next_config)
                    config = next_config
                    remember(state_path(config_path, application_home), port, Path(target))
                    row.update(status='succeeded', phase='ready', activeHome=target)
                except Exception as error:
                    row.update(status='failed', error=str(error))
                    if not stopped:
                        (control / 'switch.json').unlink(missing_ok=True)
                        if (control / 'stop.json').exists():
                            # Keep supervising the original runtime until every
                            # accepted writer finishes, then reopen its data home.
                            row.update(status='running', phase='waiting-for-drain')
                            atomic_json(path, row)
                            waiting_drain = (path, row, original)
                            break
                    if stopped:
                        # If the new process is alive, drain it before rollback.
                        atomic_json(config_path, original)
                        try:
                            _stop(process, control)
                        except Exception as drain_error:
                            from runtime_diagnostics import exception
                            exception('supervisor.storage_drain_failed', drain_error,
                                      operationId=row.get('id'), requestId=row.get('requestId'),
                                      action=row.get('action'), phase=row.get('phase'),
                                      rollback=row.get('rollback'))
                            row.update(rollback='failed', rollbackError=str(drain_error), finishedAt=time.time())
                            atomic_json(path, row)
                            raise
                        try:
                            control = root / ('runtime-' + uuid.uuid4().hex); control.mkdir()
                            process = _start(original, application_home, port, control)
                            _ready(process, original['dataHome'], port)
                            config = original
                            remember(state_path(config_path, application_home), port, Path(original['dataHome']))
                            row.update(rollback='succeeded', activeHome=original['dataHome'])
                        except Exception as recovery_error:
                            from runtime_diagnostics import exception
                            exception('supervisor.storage_recovery_failed', recovery_error,
                                      operationId=row.get('id'), requestId=row.get('requestId'),
                                      action=row.get('action'), phase=row.get('phase'),
                                      rollback=row.get('rollback'))
                            row.update(rollback='failed', rollbackError=str(recovery_error), finishedAt=time.time())
                            atomic_json(path, row)
                            raise
                row['finishedAt'] = time.time(); atomic_json(path, row)
        from runtime_diagnostics import child_exit
        watcher = getattr(process,'_hub_exit_watcher',None)
        if isinstance(watcher,threading.Thread):
            watcher.join(2)
        child_exit(process,'server',expected=getattr(process,'_hub_expected_exit',False),control=str(control),port=port)
        return process.returncode
