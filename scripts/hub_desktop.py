"""Common desktop lifecycle for source and packaged runtimes.

The supervisor owns the lifecycle. The tray is a view and asynchronous control
surface; it has no hide preference and never opens project databases.
"""
import argparse
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import time


class DesktopError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def dependencies(application_home):
    bundled = Path(application_home) / '.local/server-deps'
    if bundled.is_dir() and str(bundled) not in sys.path:
        sys.path.insert(0, str(bundled))


def tray_supported(application_home):
    dependencies(application_home)
    return (Path(application_home) / 'scripts/hub_tray.py').is_file() and \
        importlib.util.find_spec('pystray') is not None and importlib.util.find_spec('PIL') is not None


def python_windowed(executable=None):
    executable = Path(executable or sys.executable)
    if not executable.is_absolute() or not executable.is_file():
        raise DesktopError('The owned Python runtime is unavailable. Repair the application.')
    candidate = executable.with_name('pythonw.exe')
    return str(candidate if candidate.is_file() else executable)


def tray_state(config_path, *, application_home):
    from hub_launcher import external_path, read_json
    try:
        state = read_json(external_path(Path(config_path).with_name('desktop-tray-state.json'),
                                        application_home=application_home))
        if state.get('applicationHome') == str(Path(application_home).resolve()) and \
                state.get('visible') is True and 0 <= time.time() - state.get('at', 0) < 5:
            return state
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return None


def start_tray(config_path, *, application_home, wait=False, python_executable=None):
    from hub_launcher import external_path, read_json, background_flags
    config_path = external_path(config_path, application_home=application_home)
    marker = config_path.with_name('desktop-tray-exit.json')
    if marker.exists():
        from hub_lifecycle import file_lock
        lock = config_path.with_name('desktop-tray.lock')
        try:
            if lock.exists():
                with file_lock(lock, create=False):
                    marker.unlink(missing_ok=True)
            else:
                marker.unlink(missing_ok=True)
        except TimeoutError:
            return False  # The previous controller must observe its exit request.
    if tray_state(config_path, application_home=application_home) is not None:
        return True
    # The visible owner and a supplied owner interpreter are independent of the
    # caller's packages. A new local tray still needs its local dependencies.
    if python_executable is None and not tray_supported(application_home):
        return False
    error_path = config_path.with_name('desktop-tray-error.json')
    error_path.unlink(missing_ok=True)
    command = [python_windowed(python_executable), '-B', str(Path(application_home) / 'scripts/hub_tray.py'),
               '--config', str(config_path), '--application-home', str(Path(application_home).resolve())]
    environment = os.environ.copy()
    environment['PROJECT_HUB_DIAGNOSTICS_HOME']=str(config_path.parent / 'diagnostics')
    try:
        state = read_json(config_path.with_name('launcher-runtime.json'))
        if state.get('mode') in ('source','installed','development'):
            environment['PROJECT_HUB_RUNTIME_MODE'] = state['mode']
    except (OSError, ValueError, AttributeError):
        pass
    subprocess.Popen(command, cwd=str(config_path.parent), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     env=environment, creationflags=background_flags())
    if wait:
        wait_for_tray(config_path,application_home=application_home)
    return True


def wait_for_tray(config_path, *, application_home, timeout=8):
    from hub_launcher import read_json
    deadline = time.monotonic() + timeout
    while True:
        if tray_state(config_path,application_home=application_home) is not None:
            return True
        try:
            error = read_json(Path(config_path).with_name('desktop-tray-error.json'))
        except FileNotFoundError:
            error = None
        if error is not None:
            raise DesktopError(str(error.get('message','The required server tray failed to start.')))
        if time.monotonic() >= deadline:
            raise DesktopError('The server tray did not become visible. Check the desktop backend and reopen Hub.')
        time.sleep(.1)


def close_tray(config_path, *, application_home, timeout=5):
    from hub_launcher import external_path
    from hub_lifecycle import atomic_json, file_lock
    path = external_path(config_path, application_home=application_home)
    atomic_json(path.with_name('desktop-tray-exit.json'), {'requestedAt':time.time()})
    lock = path.with_name('desktop-tray.lock')
    if lock.exists():
        try:
            with file_lock(lock, timeout=timeout, create=False):
                pass
        except TimeoutError as error:
            raise DesktopError('The previous tray controller is still closing. Retry before switching launchers.') from error


def runtime_status(server):
    from hub_lifecycle import control_directory
    control = control_directory()
    app = Path(__file__).resolve().parents[1]
    config = os.environ.get('PROJECT_HUB_INSTALLATION_CONFIG')
    port = server.server_port
    from runtime_diagnostics import report
    diagnostics=report(include_tail=False)
    return dict(diagnostics={key:diagnostics[key] for key in ('enabled','directory','incident','contexts') if key in diagnostics},
        mode=os.environ.get('PROJECT_HUB_RUNTIME_MODE') or ('installed' if control else 'source'),
        running=True, port=port, url=f'http://127.0.0.1:{port}', programPath=str(app),
        dataHome=str(server.registry.home) if server.registry else str(server.store.data),
        backupHome=str(__import__('storage_operations').backup_directory(server.registry)) if server.registry else None,
        pid=os.getpid(),
        platform=sys.platform, supervised=control is not None,
        tray=dict(supported=tray_supported(app), required=True,
                  visible=bool(config and tray_state(config, application_home=app))))


def update_runtime(server, body):
    raise DesktopError('The server icon is always shown while Hub runs. Tray visibility settings were removed.', 410)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('start', 'stop', 'restart'))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--source', action='store_true')
    parser.add_argument('--development', action='store_true')
    args = parser.parse_args(argv)
    from hub_launcher import APPLICATION_HOME, open_hub, stop_hub, report_error
    try:
        if args.action in ('stop', 'restart'):
            stop_hub(args.config, application_home=APPLICATION_HOME, close_desktop=args.action == 'stop')
        if args.action in ('start', 'restart'):
            open_hub(args.config, application_home=APPLICATION_HOME, browser=False,
                     source=args.source, development=args.development)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        report_error(error)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
