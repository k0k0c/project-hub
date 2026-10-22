"""Publish ticketed storage paths in the Windows host filesystem namespace.

The supervisor keeps its leases while a hidden normal host process performs the
physical renames. Both processes use the same durable recovery receipt.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

MAX_WAIT = 60


class BrokerError(RuntimeError):
    def __init__(self, message, *, row=None):
        super().__init__(message)
        self.row = row


class BrokerPendingError(BrokerError):
    pending = True


def _path(value):
    from hub_launcher import external_path
    if not isinstance(value, str) or not value:
        raise ValueError('Physical storage path is required')
    return external_path(value)


def identity(path):
    info = Path(path).stat()
    return [info.st_dev, info.st_ino]


def _write(path, value):
    from hub_lifecycle import atomic_json
    atomic_json(Path(path), value)


def _read_receipt(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(4_000_001)
    if len(raw) > 4_000_000:
        raise ValueError('Storage operation receipt is too large')
    return json.loads(raw)


def _journal(ticket, state):
    ticket['row']['publication']['state'] = state
    _write(ticket['receiptPath'], ticket['row'])


def _validate(ticket):
    from hub_launcher import read_json, validate_config
    row = ticket['row']
    if not re.fullmatch('[0-9a-f]{32}', row.get('id', '')):
        raise ValueError('Invalid storage operation identity')
    publication = row['publication']
    paths = publication['brokerPaths']
    original = publication['originalConfig']; next_config = publication['nextConfig']
    validate_config(original); validate_config(next_config)
    source, target, candidate, retained, failed = (
        _path(paths[key]) for key in ('source', 'target', 'candidate', 'rollback', 'failedTarget'))
    if source != _path(original['dataHome']) or target != _path(next_config['dataHome']):
        raise ValueError('Physical storage paths do not match the installation')
    for path, suffix in ((candidate, 'publish'), (retained, 'before'), (failed, 'failed')):
        if path.name != f'.{target.name}-{suffix}-{row["id"]}':
            raise ValueError('Physical storage path does not match the operation')
    if retained.parent != target.parent or failed.parent != target.parent:
        raise ValueError('Recovery paths must share the destination parent')
    if candidate in (source, target, retained):
        raise ValueError('Prepared storage must be a separate directory')
    shadow = paths.get('shadowSource'); shadow_retained = paths.get('shadowRollback')
    if bool(shadow) != bool(shadow_retained):
        raise ValueError('Incomplete shadow recovery paths')
    if shadow:
        shadow = _path(shadow); shadow_retained = _path(shadow_retained)
        if source != target or shadow != candidate.parent / target.name or \
                shadow_retained != candidate.parent / f'.{target.name}-shadow-before-{row["id"]}' or \
                shadow == source or shadow_retained == retained:
            raise ValueError('Invalid shadow recovery paths')
    config_path = _path(ticket['configPath']); receipt = _path(ticket['receiptPath'])
    if config_path != _path(publication['physicalConfigPath']) or \
            receipt != _path(publication['physicalReceiptPath']) or receipt.name != row['id'] + '.json':
        raise ValueError('Physical journal paths do not match the operation')
    if _read_receipt(receipt) != row:
        raise ValueError('Storage operation changed before the broker acquired it')
    current = read_json(config_path)
    if current not in (original, next_config) or (ticket['action'] == 'publish' and current != original):
        raise ValueError('Installation configuration changed before publication')
    if not publication.get('sourceIdentity') or not publication.get('candidateIdentity'):
        raise ValueError('Storage identities are required')
    return source, target, candidate, retained, failed, shadow, shadow_retained


def _check_identity(path, expected):
    if not path.is_dir() or identity(path) != expected:
        raise ValueError('Physical storage directory changed: ' + str(path))


def _check_original_source(publication, source, shadow):
    if source.is_dir() and identity(source) != publication['sourceIdentity']:
        # In an overlaid namespace stat(logical_source) can refer to the shadow
        # even when resolve(logical_source) returns the normal host path. Keep
        # both old trees, and record their distinct identities before renaming.
        if not shadow or publication.get('shadowIdentity') != publication['sourceIdentity']:
            raise ValueError('Physical storage directory changed: ' + str(source))
        _check_identity(shadow, publication['shadowIdentity'])
        publication['runtimeSourceIdentity'] = publication['sourceIdentity']
        publication['sourceIdentity'] = identity(source)
    _check_identity(source, publication['sourceIdentity'])


def _publish(ticket, paths):
    source, target, candidate, retained, failed, shadow, shadow_retained = paths
    publication = ticket['row']['publication']
    _check_original_source(publication, source, shadow)
    _check_identity(candidate, publication['candidateIdentity'])
    if candidate.stat().st_dev != target.parent.stat().st_dev:
        raise ValueError('Prepared storage must be on the destination device')
    if retained.exists() or failed.exists() or (shadow_retained and shadow_retained.exists()):
        raise ValueError('Recovery directory already exists')
    if source != target and target.exists() and (not target.is_dir() or next(target.iterdir(), None) is not None):
        raise ValueError('Destination must be empty before publication')
    if shadow and shadow.exists():
        _check_identity(shadow, publication.get('shadowIdentity'))
    _journal(ticket, 'retaining')
    if shadow and shadow.exists():
        shadow.rename(shadow_retained)
    if source == target:
        source.rename(retained)
    elif target.exists():
        target.rmdir()
    _journal(ticket, 'publishing')
    candidate.rename(target)
    _check_identity(target, publication['candidateIdentity'])
    _journal(ticket, 'published')
    _write(ticket['configPath'], publication['nextConfig'])


def _rollback(ticket, paths):
    source, target, candidate, retained, failed, shadow, shadow_retained = paths
    publication = ticket['row']['publication']
    if not retained.exists():
        _check_original_source(publication, source, shadow)
    old_identity = publication['sourceIdentity']; new_identity = publication['candidateIdentity']
    if source == target:
        if retained.exists():
            _check_identity(retained, old_identity)
            if target.exists():
                _check_identity(target, new_identity)
                if failed.exists():
                    raise ValueError('Failed publication directory already exists')
        else:
            _check_identity(source, old_identity)
    else:
        _check_identity(source, old_identity)
        if target.exists() and not candidate.exists():
            _check_identity(target, new_identity)
            if failed.exists():
                raise ValueError('Failed publication directory already exists')
    if shadow_retained and shadow_retained.exists():
        _check_identity(shadow_retained, publication.get('shadowIdentity'))
        if shadow.exists():
            raise ValueError('Shadow source unexpectedly exists')
    _journal(ticket, 'rollback')
    if source == target and retained.exists():
        if target.exists():
            target.rename(failed)
        retained.rename(source)
    elif source != target and target.exists() and not candidate.exists():
        target.rename(failed)
    if shadow_retained and shadow_retained.exists():
        shadow_retained.rename(shadow)
    _check_identity(source, old_identity)
    _write(ticket['configPath'], publication['originalConfig'])
    _journal(ticket, 'rolled-back')


def _perform(ticket):
    paths = _validate(ticket)
    if ticket['action'] not in ('publish', 'rollback'):
        raise ValueError('Unsupported physical storage action')
    publication = ticket['row']['publication']
    publication.update(brokerPid=os.getpid(), brokerPending=True)
    _write(ticket['receiptPath'], ticket['row'])
    if ticket['action'] == 'publish':
        _publish(ticket, paths)
    else:
        _rollback(ticket, paths)
    publication['brokerPending'] = False
    _write(ticket['receiptPath'], ticket['row'])
    return ticket['row']


def _helper(ticket_path):
    ticket = json.loads(Path(ticket_path).read_text(encoding='utf-8'))
    try:
        row = _perform(ticket)
        _write(ticket['resultPath'], {'ok': True, 'row': row})
    except Exception as error:
        # Never replace a more advanced recovery step with the original ticket.
        row = _read_receipt(ticket['receiptPath'])
        if row['publication'].get('brokerTicket') != ticket['row']['publication'].get('brokerTicket'):
            raise
        row['publication'].update(brokerPending=False, brokerError=str(error)[:2000],
                                  brokerTraceback=traceback.format_exc()[-12000:])
        _write(ticket['receiptPath'], row)
        _write(ticket['resultPath'], {'ok': False, 'error': str(error)[:2000], 'row': row})
        return 1
    return 0


def _launch(ticket_path, application_home=None):
    python = Path(sys.executable)
    if application_home:
        bundled = Path(application_home).parent / 'runtime/python.exe'
        if bundled.is_file():
            python = bundled
    command = subprocess.list2cmdline([str(python), '-B', str(Path(__file__).resolve()), '--ticket', str(ticket_path)])
    # WMI creates a normal host process, with no privilege or policy changes.
    script = ("$si=New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ShowWindow=[uint16]0}; "
              "$p=Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments "
              "@{CommandLine='%s';ProcessStartupInformation=$si}; "
              "if($p.ReturnValue -ne 0){exit [int]$p.ReturnValue}; Write-Output $p.ProcessId") % command.replace("'", "''")
    return subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                          capture_output=True, text=True, timeout=MAX_WAIT, check=False,
                          creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def run(action, row, config_path, *, application_home=None):
    if is_active(row):
        raise BrokerPendingError('Переключение папки ещё выполняется. Дождитесь завершения.', row=row)
    publication = row['publication']
    root = Path(tempfile.mkdtemp(prefix='hub-storage-broker-')).resolve()
    ticket_path = root / 'ticket.json'; result_path = root / 'result.json'
    publication.update(brokerPending=True, brokerTicket=str(ticket_path), brokerPid=None,
                       brokerDispatch=str(root / 'dispatch.json'))
    _write(publication['physicalReceiptPath'], row)
    ticket = dict(action=action, row=row, configPath=str(config_path),
                  receiptPath=publication['physicalReceiptPath'], resultPath=str(result_path))
    _write(ticket_path, ticket)
    dispatched = False
    try:
        completed = _launch(ticket_path, application_home=application_home)
        if completed.returncode:
            publication['brokerPending'] = False
            _write(ticket['receiptPath'], row)
            raise BrokerError('Не удалось запустить переключение папки данных.', row=row)
        dispatched = True
        try:
            pid = int(completed.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as error:
            raise BrokerPendingError('Не удалось подтвердить запуск переключения папки.', row=_read_receipt(ticket['receiptPath'])) from error
        _write(root / 'dispatch.json', {'pid': pid})
        deadline = time.monotonic() + MAX_WAIT
        while not result_path.is_file() and time.monotonic() < deadline:
            time.sleep(.1)
        if not result_path.is_file():
            latest = _read_receipt(ticket['receiptPath'])
            raise BrokerPendingError('Переключение папки ещё выполняется. Дождитесь завершения.', row=latest)
        result = json.loads(result_path.read_text(encoding='utf-8'))
        if not result['ok']:
            raise BrokerError('Не удалось применить данные. Выполняется возврат прежнего хранилища.', row=result['row'])
        return result['row']
    except subprocess.TimeoutExpired as error:
        raise BrokerPendingError('Не удалось подтвердить завершение переключения папки.', row=_read_receipt(ticket['receiptPath'])) from error
    except OSError as error:
        # Failure before WMI dispatch has no concurrent helper to wait for.
        if not dispatched:
            publication.update(brokerPending=False, brokerError=str(error)[:2000])
            _write(ticket['receiptPath'], row)
            raise BrokerError('Не удалось запустить переключение папки данных.', row=row) from error
        raise BrokerPendingError('Не удалось подтвердить завершение переключения папки.', row=_read_receipt(ticket['receiptPath'])) from error
    finally:
        if result_path.is_file():
            shutil.rmtree(root, ignore_errors=True)


def is_active(row):
    publication = row.get('publication') or {}
    if not publication.get('brokerPending'):
        return False
    pid = publication.get('brokerPid')
    if not isinstance(pid, int) and publication.get('brokerDispatch'):
        try:
            pid = json.loads(Path(publication['brokerDispatch']).read_text(encoding='utf-8'))['pid']
        except (OSError, ValueError, KeyError):
            pass
    if not isinstance(pid, int):
        return True  # Dispatch may have succeeded without a response.
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.get_last_error() != 87
    try:
        code = ctypes.c_ulong()
        return not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)) or code.value == 259
    finally:
        kernel32.CloseHandle(handle)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ticket', required=True)
    raise SystemExit(_helper(parser.parse_args().ticket))
