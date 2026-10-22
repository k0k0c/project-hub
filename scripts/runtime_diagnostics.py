"""Small, failure-contained diagnostics for the local runtime supervisor."""
from collections import deque
from contextlib import contextmanager
from datetime import datetime, timezone
import faulthandler
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
import traceback
import uuid

MAX_LOG = 1024 * 1024
MAX_TAIL = 64 * 1024
MAX_REPORT_JSON = 128 * 1024
_lock = threading.RLock()
_state = {'pid': None, 'directory': None, 'component': None, 'fatal': None,
          'previous': {}, 'context': {}, 'active_children': set(),
          'child_exits': set(), 'console': None}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _safe(value, depth=0):
    if depth > 3:
        return '<depth-limit>'
    if isinstance(value, dict):
        hidden = ('secret', 'token', 'password', 'authorization', 'cookie', 'body')
        return {str(k): _safe(v, depth + 1) for k, v in value.items()
                if not any(part in str(k).lower() for part in hidden)}
    if isinstance(value, (list, tuple)):
        return [_safe(item, depth + 1) for item in value[:100]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if not isinstance(value, str) else value[:4000]
    return str(value)[:4000]


def resources():
    """Return cheap process resource evidence without adding a dependency."""
    result = {'cpuSeconds': time.process_time()}
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        result.update(maxRss=usage.ru_maxrss,
                      userSeconds=usage.ru_utime, systemSeconds=usage.ru_stime)
    except Exception:
        try:
            import ctypes
            class _Counters(ctypes.Structure):
                _fields_ = [('cb', ctypes.c_ulong), ('pageFaultCount', ctypes.c_ulong),
                            ('peakWorkingSetSize', ctypes.c_size_t), ('workingSetSize', ctypes.c_size_t),
                            ('quotaPeakPagedPoolUsage', ctypes.c_size_t), ('quotaPagedPoolUsage', ctypes.c_size_t),
                            ('quotaPeakNonPagedPoolUsage', ctypes.c_size_t), ('quotaNonPagedPoolUsage', ctypes.c_size_t),
                            ('pagefileUsage', ctypes.c_size_t), ('peakPagefileUsage', ctypes.c_size_t)]
            counters = _Counters(); counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            psapi = ctypes.WinDLL('psapi', use_last_error=True)
            kernel32.GetCurrentProcess.restype = ctypes.c_void_p
            psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Counters), ctypes.c_ulong]
            psapi.GetProcessMemoryInfo.restype = ctypes.c_bool
            handle = kernel32.GetCurrentProcess()
            if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                result.update(workingSet=counters.workingSetSize,
                              peakWorkingSet=counters.peakWorkingSetSize)
        except Exception:
            pass
    return result


def _process_alive(pid):
    """Return True/False when known, or None when process state is inaccessible."""
    if pid <= 0:
        return False
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_bool, ctypes.c_ulong]
            kernel32.OpenProcess.restype = ctypes.c_void_p
            kernel32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            kernel32.GetExitCodeProcess.restype = ctypes.c_bool
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.restype = ctypes.c_bool
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False if ctypes.get_last_error() == 87 else None  # PID does not exist; access denied is unknown.
            code = ctypes.c_ulong()
            try:
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return None
                return code.value == 259  # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return None
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return None
    except Exception:
        return None


def process_context():
    """Record lifetime constraints without changing Windows jobs or permissions."""
    result = {'pid': os.getpid(), 'parentPid': os.getppid()}
    if os.name != 'nt':
        return result
    try:
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [('processTime', ctypes.c_int64), ('jobTime', ctypes.c_int64),
                        ('flags', wintypes.DWORD), ('minWorkingSet', ctypes.c_size_t),
                        ('maxWorkingSet', ctypes.c_size_t), ('activeProcesses', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class Extended(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', ctypes.c_uint64 * 6),
                        ('processMemory', ctypes.c_size_t), ('jobMemory', ctypes.c_size_t),
                        ('peakProcessMemory', ctypes.c_size_t), ('peakJobMemory', ctypes.c_size_t)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        advapi.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        advapi.IsTokenRestricted.argtypes = [wintypes.HANDLE]
        token = wintypes.HANDLE()
        if advapi.OpenProcessToken(kernel.GetCurrentProcess(), 0x8, ctypes.byref(token)):
            try:
                result['restrictedToken'] = bool(advapi.IsTokenRestricted(token))
            finally:
                kernel.CloseHandle(token)
        kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        inside = wintypes.BOOL()
        if kernel.IsProcessInJob(kernel.GetCurrentProcess(), None, ctypes.byref(inside)):
            result['windowsJob'] = {'member': bool(inside.value)}
            if inside.value:
                kernel.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                                              wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
                limits = Extended(); size = wintypes.DWORD()
                if kernel.QueryInformationJobObject(None, 9, ctypes.byref(limits), ctypes.sizeof(limits), ctypes.byref(size)):
                    flags = limits.basic.flags
                    result['windowsJob'].update(killOnClose=bool(flags & 0x2000),
                                                breakawayAllowed=bool(flags & 0x800),
                                                silentBreakaway=bool(flags & 0x1000))
                else:
                    result['windowsJob']['queryError'] = ctypes.get_last_error()
    except Exception:
        pass
    return result


@contextmanager
def lifetime(path, *, interval=5):
    """Durable heartbeat under the caller's lifetime lease; never infer an exit cause.

    A killed supervisor cannot flush its own exit record. The next lease owner
    detects that gap. This is evidence of an unrecorded exit, not proof of a crash,
    OOM, VPN issue, or termination by the parent application.
    """
    path = Path(path)
    previous = None
    try:
        previous = _read_json(path)
    except FileNotFoundError:
        pass
    except Exception as error:
        exception('supervisor.lifetime_read_failed', error)
    if isinstance(previous, dict) and previous.get('state') == 'running':
        fields = dict(previous=previous, cause='unknown', reason='missing_shutdown_record')
        record('supervisor.previous_run_interrupted', **fields)
        _incident('supervisor.previous_run_interrupted', fields=fields)
    row = dict(schemaVersion=1, runId=uuid.uuid4().hex, state='running', startedAt=_now(),
               heartbeatAt=_now(), process=process_context())
    def save():
        try:
            _atomic(path, row)
        except Exception as error:
            exception('supervisor.lifetime_write_failed', error)
    last_saved = time.monotonic()
    def pulse(*, force=False, **fields):
        nonlocal last_saved
        row.update(_safe(fields))
        now = time.monotonic()
        if force or now - last_saved >= interval:
            row['heartbeatAt'] = _now()
            save()
            last_saved = now
    save()
    failed = False
    try:
        yield pulse
    except BaseException:
        failed = True
        raise
    finally:
        row.update(state='failed' if failed else 'stopped', finishedAt=_now())
        save()


def _atomic(path, value):
    temporary = path.with_name(path.name + '.tmp-' + str(os.getpid()))
    temporary.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True), encoding='utf-8')
    os.replace(temporary, path)


def _read_json(path, limit=MAX_REPORT_JSON):
    data = path.read_bytes()[:limit]
    return json.loads(data.decode('utf-8'))


def _error_metadata(error):
    """Extract bounded, diagnostic-only metadata from structured exceptions."""
    try:
        body = getattr(error, 'body', None)
        if not isinstance(body, dict):
            body = {}
        result = {}
        code = getattr(error, 'code', None) or body.get('errorCode') or body.get('error')
        status = getattr(error, 'status', None) or body.get('status')
        if isinstance(code, (str, int, float, bool)):
            result['errorCode'] = str(code)[:128]
        if isinstance(status, int) and not isinstance(status, bool):
            result['status'] = status
        conflicts = body.get('conflicts')
        if isinstance(conflicts, (list, tuple)):
            result['conflictCount'] = len(conflicts)
            allowed = {'type', 'message', 'area', 'path', 'database', 'table', 'project',
                       'projects', 'requiredProjects', 'modes', 'resolutions'}
            sample = []
            for conflict in conflicts[:8]:
                if isinstance(conflict, dict):
                    item = {}
                    for key in allowed:
                        value = conflict.get(key)
                        if isinstance(value, str):
                            item[key] = value[:512]
                        elif isinstance(value, (int, float, bool)) or value is None:
                            item[key] = value
                        elif isinstance(value, (list, tuple)):
                            item[key] = [str(entry)[:128] for entry in value[:20]
                                         if isinstance(entry, (str, int, float, bool))]
                    sample.append(item)
            if sample:
                result['conflictSample'] = sample
        return result
    except Exception:
        return {}


def _incident(event, error=None, fields=None):
    if not _enabled():
        return
    try:
        target = _paths()[3]
        value = {'time': _now(), 'pid': os.getpid(), 'component': _state['component'],
                 'event': event, **_safe(fields or {})}
        if error is not None:
            value.update(errorType=type(error).__name__, errorMessage=str(error)[:4000],
                         traceback=''.join(traceback.format_exception(type(error), error, error.__traceback__))[-12000:])
            value.update(_error_metadata(error))
        _atomic(target, value)
    except Exception:
        pass


def _enabled():
    return _state['directory'] is not None


def _paths():
    directory = _state['directory']
    component = _state['component'] or 'runtime'
    pid = _state['pid'] or os.getpid()
    return (directory / f'{component}-{pid}.jsonl',
            directory / f'{component}-{pid}.fatal.log',
            directory / f'{component}-{pid}-context.json',
            directory / 'last-incident.json')


def _rotate(path):
    if not path.exists() or path.stat().st_size <= MAX_LOG:
        return
    for index in range(3, 0, -1):
        source = path.with_name(path.name + f'.{index}')
        target = path.with_name(path.name + f'.{index + 1}')
        if source.exists():
            if index == 3:
                source.unlink(missing_ok=True)
            else:
                os.replace(source, target)
    os.replace(path, path.with_name(path.name + '.1'))


class _BoundedStream:
    """Small file-like stream for None stdout/stderr and faulthandler."""
    def __init__(self, path):
        self.path = path
        self._stream = path.open('ab')
        self._lock = threading.RLock()

    def write(self, value):
        try:
            data = value.encode('utf-8', 'replace') if isinstance(value, str) else bytes(value)
            with self._lock:
                self._stream.write(data)
                self._stream.flush()
                if self.path.stat().st_size > MAX_LOG:
                    self._stream.close()
                    _rotate(self.path)
                    self._stream = self.path.open('ab')
            return len(value)
        except Exception:
            return 0

    def flush(self):
        try:
            with self._lock:
                self._stream.flush()
        except Exception:
            pass

    def fileno(self):
        return self._stream.fileno()

    def close(self):
        try:
            with self._lock:
                self._stream.close()
        except Exception:
            pass


def _retain(component):
    """Keep at most 40 closed process bundles, preserving the active process."""
    if not _enabled():
        return
    try:
        pattern = re.compile(r'^' + re.escape(component) + r'-(\d+)(?:-|\.|$)')
        bundles = {}
        for path in _state['directory'].iterdir():
            match = pattern.match(path.name)
            if match:
                pid = int(match.group(1))
                bundles.setdefault(pid, []).append(path)
        active = {os.getpid(), *(_state.get('active_children') or set())}
        closed = sorted(((max(p.stat().st_mtime for p in paths), pid, paths)
                         for pid, paths in bundles.items()
                         if pid not in active and _process_alive(pid) is False), reverse=True)
        for _, _, paths in closed[40:]:
            for path in paths:
                try:
                    path.unlink(missing_ok=True)
                except Exception:
                    pass
    except Exception:
        pass


def _write(event, fields):
    if not _enabled():
        return None
    path, _, context_path, _ = _paths()
    _rotate(path)
    entry = {'time': _now(), 'pid': os.getpid(), 'component': _state['component'],
             'event': event, **_safe(fields)}
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + '\n')
    if fields:
        _state['context'] = {**_state.get('context', {}), **_safe(fields)}
        _atomic(context_path, {'time': entry['time'], 'pid': entry['pid'],
                               'component': _state['component'], **_state['context']})
    return entry


def configure(component, directory=None, **context):
    """Enable diagnostics only for an explicit directory or configured home."""
    try:
        with _lock:
            requested = directory or os.environ.get('PROJECT_HUB_DIAGNOSTICS_HOME')
            if not isinstance(component, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', component):
                cleanup(); return False
            if requested is None:
                cleanup(); return False
            target = Path(requested)
            if target.name in ('', '.', '..'):
                cleanup(); return False
            if _state['pid'] == os.getpid() and _state['directory'] == target and _state['component'] == component:
                if context: record('configured', **context)
                return True
            cleanup()
            target.mkdir(parents=True, exist_ok=True)
            _state.update(pid=os.getpid(), directory=target, component=component, context={})
            _, fatal, context_path, _ = _paths()
            # Keep the faulthandler descriptor stable for the process lifetime.
            # Console streams use a separate bounded file because rollover would
            # otherwise invalidate faulthandler's registered descriptor.
            fatal_stream = fatal.open('a', encoding='utf-8')
            _state['fatal'] = fatal_stream
            _state['previous'] = {'excepthook': sys.excepthook,
                                  'threading': getattr(threading, 'excepthook', None),
                                  'stderr': sys.stderr, 'stdout': sys.stdout}
            sys.excepthook = _uncaught
            if hasattr(threading, 'excepthook'):
                threading.excepthook = _uncaught_thread
            console = _BoundedStream(target / f'{component}-{os.getpid()}.console.log')
            _state['console'] = console
            if sys.stderr is None: sys.stderr = console
            if sys.stdout is None: sys.stdout = console
            faulthandler.enable(file=fatal_stream, all_threads=True)
            _atomic(context_path, {'time': _now(), 'pid': os.getpid(), 'component': component,
                                   'process': process_context(), **_safe(context)})
            record('configured', **context)
            _retain(component)
            return True
    except Exception:
        cleanup()
        return False


def record(event, **fields):
    try:
        with _lock:
            return _write(str(event), fields)
    except Exception:
        return None


def exception(event, error=None, **fields):
    try:
        if error is not None:
            fields['error'] = ''.join(traceback.format_exception(type(error), error, error.__traceback__))[-12000:]
            fields.update(_error_metadata(error))
            _incident(event, error, fields)
        return record(event, **fields)
    except Exception:
        return None


def _uncaught(exc_type, value, tb):
    exception('uncaught_exception', value, traceback=''.join(traceback.format_exception(exc_type, value, tb))[-12000:])
    previous = _state.get('previous', {}).get('excepthook')
    if previous:
        try:
            previous(exc_type, value, tb)
        except Exception:
            pass


def _uncaught_thread(args):
    _uncaught(args.exc_type, args.exc_value, args.exc_traceback)


def capture_child(process, component, context=None):
    """Drain a stdout=PIPE/stderr=STDOUT child into a bounded raw tail log."""
    try:
        directory = _state['directory']
        if directory is None:
            return {'enabled': False}
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f'{component}-{process.pid}.child.log'
        path.touch(exist_ok=True)
        def drain():
            stream = None
            try:
                tail = deque(maxlen=MAX_LOG)
                output = process.stdout
                if output is None:
                    return
                reader = getattr(output, 'read1', None) or output.read
                stream = path.open('ab')
                while True:
                    chunk = reader(8192)
                    if not chunk:
                        break
                    if isinstance(chunk, str):
                        chunk = chunk.encode('utf-8', 'replace')
                    tail.extend(chunk)
                    stream.write(chunk)
                    stream.flush()
                    if path.stat().st_size > MAX_LOG:
                        stream.close()
                        path.write_bytes(bytes(tail))
                        stream = path.open('ab')
            except Exception:
                pass
            finally:
                if stream is not None:
                    try:
                        stream.close()
                    except Exception:
                        pass
        thread = threading.Thread(target=drain, name=f'{component}-output', daemon=True)
        _state.setdefault('active_children', set()).add(process.pid)
        thread.start()
        _retain(component)
        if context:
            try:
                _atomic(directory / f'{component}-{process.pid}-context.json',
                        {'time': _now(), 'pid': process.pid, 'component': component, **_safe(context)})
            except Exception:
                pass
        record('child_started', component=component, childPid=process.pid, **(context or {}))
        return {'enabled': True, 'path': str(path), 'thread': thread.name,
                'threadObject': thread, 'childPid': process.pid}
    except Exception:
        return {'enabled': False}


def child_exit(process, component, **context):
    try:
        poll = getattr(process,'poll',None)
        code = poll() if callable(poll) else process.exitcode
        child_pid = getattr(process, 'pid', None)
        key = (component, child_pid)
        with _lock:
            if code is not None and key in _state.get('child_exits', set()):
                return None
            if code is not None:
                _state.setdefault('child_exits', set()).add(key)
            _state.get('active_children', set()).discard(child_pid)
        thread_name = context.pop('thread', None)
        thread_obj = context.pop('threadObject', None)
        if thread_obj is not None:
            thread_obj.join(.5)
        for thread in threading.enumerate():
            if thread is thread_name or thread.name == thread_name:
                thread.join(.5)
                break
        if _enabled():
            context_path = _state['directory'] / f'{component}-{child_pid}-context.json'
            try:
                context = {**json.loads(context_path.read_text(encoding='utf-8')), **context}
            except Exception:
                pass
            child_path = _state['directory'] / f'{component}-{child_pid}.child.log'
            try:
                with child_path.open('rb') as stream:
                    stream.seek(max(0, child_path.stat().st_size - MAX_TAIL))
                    context['outputTail'] = stream.read(MAX_TAIL).decode('utf-8', 'replace')
            except Exception:
                pass
        for reserved in ('time','pid','event','component'):
            context.pop(reserved,None)
        payload = dict(context, component=component, childPid=child_pid, exitCode=code,
                       exitHex=hex(code & 0xffffffff) if isinstance(code, int) and code < 0 else None)
        if code not in (0, None) or context.get('expected') is False:
            payload['incident'] = True
            result = record('child_exit', **payload)
            previous_incident = {}
            if _enabled():
                try:
                    previous_incident = _read_json(_paths()[3])
                except Exception:
                    pass
            if previous_incident and any(k in previous_incident for k in ('errorType', 'traceback', 'errorMessage')):
                payload['previousIncident'] = previous_incident
            _incident('child_exit', fields=payload)
            _retain(component)
            return result
        result = record('child_exit', **payload)
        _retain(component)
        return result
    except Exception:
        return None


def cleanup():
    with _lock:
        try:
            if _state.get('fatal'):
                faulthandler.disable()
                _state['fatal'].close()
        except Exception:
            pass
        try:
            if _state.get('console'):
                _state['console'].close()
        except Exception:
            pass
        previous = _state.get('previous', {})
        if previous.get('excepthook'):
            __import__('sys').excepthook = previous['excepthook']
        if previous.get('threading') and hasattr(threading, 'excepthook'):
            threading.excepthook = previous['threading']
        if 'stderr' in previous:
            sys.stderr = previous['stderr']
        if 'stdout' in previous:
            sys.stdout = previous['stdout']
        _state.update(pid=None, directory=None, component=None, fatal=None, previous={}, context={},
                      active_children=set(), child_exits=set(), console=None)


def report(directory=None, include_tail=False):
    try:
        root = Path(directory) if directory else _state.get('directory')
        if root is None or not root.is_dir():
            return {'enabled': False}
        incident = {}
        incident_path = root / 'last-incident.json'
        if incident_path.exists():
            incident = _read_json(incident_path)
        metadata = []
        for path in sorted(root.glob('*'), key=lambda item: item.stat().st_mtime, reverse=True)[:100]:
            if path.is_file() and path.name != 'last-incident.json':
                metadata.append({'name': path.name, 'size': path.stat().st_size})
        contexts = []
        context_paths = sorted(root.glob('*-context.json'), key=lambda item: item.stat().st_mtime,
                               reverse=True)[:20]
        for path in context_paths:
            try:
                contexts.append(_read_json(path))
            except Exception:
                continue
        result = {'enabled': True, 'directory': str(root), 'incident': incident,
                  'contexts': contexts, 'files': metadata}
        lifetime_path = root.parent / 'supervisor-lifetime.json'
        if lifetime_path.is_file():
            try:
                lifetime_row = _read_json(lifetime_path)
                process = lifetime_row.get('process', {})
                alive = _process_alive(process.get('pid', 0))
                result['lifetime'] = dict(lifetime_row, processAlive=alive)
                if lifetime_row.get('state') == 'running' and alive is False:
                    result['lifetime'].update(state='interrupted', cause='unknown', reason='missing_shutdown_record')
            except Exception:
                result['lifetime'] = {'state': 'unknown'}
        if include_tail:
            tails = []
            tail_paths = sorted(list(root.glob('*.fatal.log')) + list(root.glob('*.child.log')),
                                key=lambda item: item.stat().st_mtime, reverse=True)[:4]
            for path in tail_paths:
                with path.open('rb') as stream:
                    stream.seek(0, 2)
                    stream.seek(max(0, stream.tell() - MAX_TAIL))
                    tails.append(stream.read(MAX_TAIL))
            result['tail'] = b'\n'.join(tails)[-MAX_TAIL:].decode('utf-8', 'replace')
        return result
    except Exception:
        return {'enabled': False}
