"""Open the installed standalone Hub without writing to its application tree.

This launcher verifies the selected data home before opening a browser. Atomic
application activation and supervision are provided by hub_lifecycle.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser


APPLICATION_HOME = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8769
MAX_CONFIG_BYTES = 8192


class LauncherError(ValueError):
    pass


def default_base():
    if os.name == 'nt':
        local = os.environ.get('LOCALAPPDATA')
        if not local:
            raise LauncherError('LOCALAPPDATA is unavailable; specify an external --config path.')
        return Path(local) / 'ProjectHub'
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/ProjectHub'
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'ProjectHub'


def external_path(value, *, application_home=APPLICATION_HOME):
    path = Path(value)
    if not path.is_absolute():
        raise LauncherError('Configuration and data paths must be absolute.')
    # Check before resolve(): otherwise a symlink or Windows junction disappears
    # from the path and can redirect configuration writes.
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise LauncherError('Configuration and data paths cannot contain links or reparse points.')
    resolved = path.resolve()
    app = Path(application_home).resolve()
    if app.name == 'app' and (app.parent / 'runtime' / 'python.exe').is_file():
        app = app.parent
    if resolved == app or app in resolved.parents:
        raise LauncherError('Configuration and data must be outside the application directory.')
    return resolved


def read_json(path):
    with path.open('rb') as stream:
        raw = stream.read(MAX_CONFIG_BYTES + 1)
    if len(raw) > MAX_CONFIG_BYTES:
        raise LauncherError('Configuration exceeds the supported size; preserve it for recovery.')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise LauncherError('Configuration contains duplicate fields; preserve it for recovery.')
            value[key] = item
        return value
    try:
        return json.loads(raw, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as error:
        raise LauncherError('Configuration is unreadable; preserve it for recovery.') from error


def validate_config(value, *, application_home=APPLICATION_HOME):
    required = {'schemaVersion', 'dataHome', 'port', 'language'}
    if not isinstance(value, dict) or not required <= set(value) or set(value) - required - {'backupHome'}:
        raise LauncherError('Unsupported installation configuration; preserve it for recovery.')
    if type(value['schemaVersion']) is not int or value['schemaVersion'] != 1:
        raise LauncherError('Unsupported installation configuration version.')
    if type(value['port']) is not int or not 1 <= value['port'] <= 65535:
        raise LauncherError('The configured port must be between 1 and 65535.')
    if value['language'] not in ('ru', 'en') or not isinstance(value['dataHome'], str):
        raise LauncherError('The configuration requires language ru/en and an absolute data home.')
    external_path(value['dataHome'], application_home=application_home)
    if 'backupHome' in value:
        if not isinstance(value['backupHome'], str):
            raise LauncherError('The backup folder must be an absolute path.')
        home = external_path(value['dataHome'], application_home=application_home)
        backup = external_path(value['backupHome'], application_home=application_home)
        if home == backup or home in backup.parents or backup in home.parents:
            raise LauncherError('The data and backup folders must be separate and cannot contain each other.')
    return value


def backup_home(config):
    """Keep the established data-backups location for configurations without it."""
    home = Path(config['dataHome'])
    return Path(config.get('backupHome') or home.parent / (home.name + '-backups'))


def configure(path=None, *, language='ru', data_home=None, port=DEFAULT_PORT,
              application_home=APPLICATION_HOME):
    path = external_path(path or default_base() / 'installation.json', application_home=application_home)
    if path.exists():
        return validate_config(read_json(path), application_home=application_home)
    home = external_path(data_home or path.parent / 'data', application_home=application_home)
    value = validate_config(dict(schemaVersion=1, dataHome=str(home), port=port, language=language),
                            application_home=application_home)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation preserves another launcher's configuration. A failed
    # write is left visible for recovery, rather than silently replaced later.
    try:
        with path.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        return validate_config(read_json(external_path(path, application_home=application_home)),
                               application_home=application_home)
    return value


def health(port):
    """Read only the loopback health endpoint, without proxies or redirects."""
    from urllib.request import HTTPRedirectHandler
    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, request, fp, code, message, headers, newurl):
            return None
    try:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(f'http://127.0.0.1:{port}/api/health', timeout=.5) as response:
            if response.status != 200:
                return None
            raw = response.read(MAX_CONFIG_BYTES + 1)
            if len(raw) > MAX_CONFIG_BYTES:
                return None
            body = json.loads(raw)
            return body if isinstance(body, dict) else None
    except (OSError, URLError, HTTPError, ValueError, UnicodeError):
        return None


def matches_home(body, home):
    if not isinstance(body, dict) or body.get('service') != 'project-hub' or not isinstance(body.get('dataHome'), str):
        return False
    if body.get('supervised') is True and body.get('supervisorAlive') is not True:
        return False
    reported = Path(body['dataHome'])
    return reported.is_absolute() and os.path.normcase(str(reported.resolve())) == os.path.normcase(str(home.resolve()))


def matches_program(body, application_home):
    value = body.get('codeRoot') if isinstance(body, dict) else None
    return isinstance(value, str) and Path(value).is_absolute() and \
        os.path.normcase(str(Path(value).resolve())) == os.path.normcase(str(Path(application_home).resolve()))


def available_port(preferred):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if os.name == 'nt':
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind(('127.0.0.1', preferred))
        except OSError:
            probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


def state_path(config_path, application_home):
    return external_path(config_path.with_name('launcher-runtime.json'), application_home=application_home)


def remembered_port(path, home):
    try:
        value = read_json(path)
    except (OSError, LauncherError):
        return None
    if not isinstance(value, dict) or type(value.get('port')) is not int or not 1 <= value['port'] <= 65535:
        return None
    if not isinstance(value.get('dataHome'), str) or value['dataHome'] != str(home):
        return None
    return value['port']


def remember(path, port, home, *, control=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix='.hub-runtime-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            value = dict(port=port, dataHome=str(home), mode=os.environ.get('PROJECT_HUB_RUNTIME_MODE', 'installed'))
            if control is not None:
                value['control'] = str(control)
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def stop_child(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


def background_flags():
    """Keep an authorized desktop runtime independent of a caller's lifetime job.

    Windows must explicitly permit breakaway. Never try it from a restricted
    token or alter a job, token, sandbox policy, registry, or user configuration.
    """
    if os.name != 'nt':
        return 0
    from runtime_diagnostics import process_context, record
    context = process_context()
    job = context.get('windowsJob', {})
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    if job.get('killOnClose') and job.get('breakawayAllowed') and context.get('restrictedToken') is False:
        flags |= getattr(subprocess, 'CREATE_BREAKAWAY_FROM_JOB', 0)
    # A permitted inner job can still be nested in a non-breakaway outer job.
    # Only the child's recorded context establishes its remaining constraints.
    record('launcher.background_lifetime', process=context,
           breakawayRequested=bool(flags & getattr(subprocess, 'CREATE_BREAKAWAY_FROM_JOB', 0)))
    return flags


class DesktopSupervisor:
    """Correlate Explorer's launch with the actual supervisor, never a TCP PID."""
    def __init__(self, receipt, desktop_pid):
        self.receipt = receipt
        self.desktop_pid = desktop_pid
        self.pid = None

    def poll(self):
        from runtime_diagnostics import _process_alive
        try:
            row = read_json(self.receipt)
        except FileNotFoundError:
            row = None
        if row is not None:
            if not isinstance(row, dict) or not isinstance(row.get('process'), dict):
                raise LauncherError('Invalid independent source startup confirmation; see launcher diagnostics.')
            context = row.get('process', {})
            job = context.get('windowsJob', {})
            if not isinstance(job, dict):
                raise LauncherError('Invalid independent source process context; see launcher diagnostics.')
            if row.get('state') not in ('started', 'exited') or context.get('restrictedToken') is not False or \
                    context.get('parentPid') != self.desktop_pid or \
                    not (job.get('member') is False or job.get('killOnClose') is False) or \
                    type(context.get('pid')) is not int or context['pid'] <= 0 or \
                    (self.pid is not None and self.pid != context['pid']):
                raise LauncherError('Independent source startup could not be verified. See launcher diagnostics; no dependent server was accepted.')
            self.pid = context['pid']
            if row['state'] == 'exited':
                code = row.get('exitCode')
                if type(code) is not int or not 0 <= code <= 255:
                    raise LauncherError('Invalid independent source supervisor exit confirmation.')
                return code
        if self.pid is None:
            return None
        return 1 if _process_alive(self.pid) is False else None


def start_supervisor(command, config_path, environment, *, source, development):
    if os.name != 'nt' or not source:
        return subprocess.Popen(command, cwd=str(config_path.parent), env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=background_flags())
    from windows_desktop import launch
    from hub_instance import directory
    request = uuid.uuid4().hex
    receipt = config_path.parent / 'diagnostics' / f'desktop-launch-{request}.json'
    windowed = Path(command[0]).with_name('pythonw.exe')
    if not windowed.is_file():
        raise LauncherError('Independent source startup requires pythonw.exe beside the source Python interpreter.')
    identity = launch([str(windowed), *command[1:], '--source', '--mode',
        'development' if development else 'work', '--desktop-launch-id', request,
        '--instance-home', str(directory())], config_path.parent)
    return DesktopSupervisor(receipt, identity['desktopPid'])


def stop_hub(config_path=None, *, application_home=APPLICATION_HOME, timeout=60, close_desktop=True):
    """Drain only this installation; never terminate an unknown/source runtime."""
    from hub_lifecycle import atomic_json, file_lock
    path = external_path(config_path or default_base() / 'installation.json', application_home=application_home)
    def closed():
        if close_desktop and (Path(application_home) / 'scripts/hub_desktop.py').is_file():
            from hub_desktop import close_tray
            close_tray(path, application_home=application_home)
    lock = path.with_name('supervisor.lock')
    if not lock.exists():
        closed()
        return
    try:
        with file_lock(lock, create=False):
            closed()
            return
    except TimeoutError:
        pass
    config = validate_config(read_json(path), application_home=application_home)
    home = Path(config['dataHome'])
    port = remembered_port(state_path(path, application_home), home) or config['port']
    body = health(port)
    if not matches_home(body, home) or body.get('supervised') is not True or not matches_program(body, application_home):
        raise LauncherError('Cannot verify the running installation; no process was stopped.')
    root = external_path(path.parent / 'lifecycle', application_home=application_home)
    with file_lock(root / 'activation-admission.lock'):
        # The stable marker handles current supervisors. Owned runtime markers
        # also allow a safe upgrade from earlier supervisors without --stop.
        atomic_json(root / 'shutdown.json', {'requestedAt':time.time()})
        for control in root.glob('runtime-*'):
            if len(control.name) == 40 and all(c in '0123456789abcdef' for c in control.name[8:]):
                control = external_path(control, application_home=application_home)
                if control.is_dir():
                    atomic_json(control / 'stop.json', {'requestedAt':time.time()})
        deadline = time.monotonic() + timeout
        while True:
            try:
                with file_lock(lock, create=False):
                    closed()
                    return
            except TimeoutError:
                if time.monotonic() >= deadline:
                    raise LauncherError('Hub is still draining accepted work; installation was not changed.')
                time.sleep(.1)


def stop_runtime(config_path=None, *, application_home=APPLICATION_HOME, development=False, timeout=60):
    """Stop the verified owner of a shared work configuration, or an isolated dev runtime."""
    from hub_instance import active, directory, same_path, check_development_home
    from hub_lifecycle import file_lock
    path = external_path(config_path or default_base() / 'installation.json', application_home=application_home)
    if development and config_path is None:
        raise LauncherError('Development mode requires its own configuration and data folder.')
    with file_lock(directory() / 'launch.lock', timeout=timeout):
        if development:
            if path.exists():
                config = validate_config(read_json(path), application_home=application_home)
                check_development_home(config['dataHome'], path, application_home)
        else:
            current = active()
            if current is not None:
                if not current['config'] or not same_path(current['config'], path):
                    raise LauncherError('Another main Hub configuration is active. Use its configuration to stop it.')
                application_home = Path(current['applicationHome'])
        stop_hub(path, application_home=application_home, timeout=timeout)


def report_error(error):
    if sys.stderr is not None:
        print(str(error), file=sys.stderr)
    else:
        # Windowed launchers have no console. Use the same browser presentation
        # on every desktop instead of depending on a native Windows dialog.
        import html
        from hub_lifecycle import atomic_json
        root = default_base()
        atomic_json(root / 'launch-error.json', {'message':str(error), 'at':time.time()})
        page = root / 'launch-error.html'
        page.write_text('<!doctype html><meta charset="utf-8"><title>Project Hub</title>'
                        '<h1>Project Hub</h1><p>' + html.escape(str(error)) + '</p>', encoding='utf-8')
        webbrowser.open(page.as_uri())


def open_hub(config_path=None, *, application_home=APPLICATION_HOME, timeout=600, browser=True,
             development=False, switch=False, source=False):
    from hub_instance import directory
    from hub_lifecycle import file_lock
    # Serialize shortcut launches across source and installed configurations.
    # The supervisor owns a different lifetime lock after this short admission.
    with file_lock(directory() / 'launch.lock', timeout=timeout):
        return _open_hub(config_path, application_home=application_home, timeout=timeout,
                         browser=browser, development=development, switch=switch, source=source)


def _open_hub(config_path=None, *, application_home=APPLICATION_HOME, timeout=600, browser=True,
              development=False, switch=False, source=False):
    from hub_instance import active, same_path, check_development_home, register_primary
    if development and config_path is None:
        raise LauncherError('Development mode requires an explicit external --config and separate data folder.')
    config_path = external_path(config_path or default_base() / 'installation.json', application_home=application_home)
    config = configure(config_path, application_home=application_home)
    home = external_path(config['dataHome'], application_home=application_home)
    current = None
    if development:
        check_development_home(home, config_path, application_home)
    else:
        register_primary(config_path,application_home)
        current = active()
        if current is not None:
            same_runtime = current['config'] and same_path(current['config'], config_path) and \
                same_path(current['applicationHome'], application_home)
            if not switch or same_runtime:
                if current['config']:
                    from hub_desktop import start_tray
                    if not start_tray(current['config'], application_home=Path(current['applicationHome']),
                                      wait=True,python_executable=current.get('pythonExecutable')):
                        raise LauncherError('The main server tray is still closing. Reopen Hub after it finishes.')
                url = 'http://127.0.0.1:' + str(current['port'])
                if browser: webbrowser.open(url)
                return url
            if not current['config']:
                raise LauncherError('The main server was started directly. Stop it gracefully before switching launchers.')
    # Only a new runtime needs the caller's desktop dependencies. In particular,
    # verify a switch target before draining the healthy current owner.
    if not development and (Path(application_home) / 'scripts/hub_desktop.py').is_file():
        from hub_desktop import tray_supported
        if not tray_supported(application_home):
            raise LauncherError('Tray dependencies are unavailable. Repair the installation or install the source desktop requirements before starting Hub.')
    if current is not None:
        stop_hub(current['config'], application_home=Path(current['applicationHome']))
    runtime = state_path(config_path, application_home)
    remembered = remembered_port(runtime, home)
    def desktop():
        if (Path(application_home) / 'scripts/hub_desktop.py').is_file():
            from hub_desktop import start_tray
            try:
                shown = start_tray(config_path, application_home=application_home,wait=not development)
                if not shown and not development:
                    raise LauncherError('The required server tray could not start.')
            except (OSError, ValueError) as error:
                if not development:
                    stop_hub(config_path,application_home=application_home)
                    raise LauncherError(str(error)) from error
                report_error(error)
    for port in dict.fromkeys([config['port'], *([remembered] if remembered else [])]):
        body = health(port)
        if matches_home(body, home) and matches_program(body, application_home):
            if not development and body.get('supervised') is not True:
                raise LauncherError('This server was started without the shared launcher. Stop it gracefully, then reopen Hub through the source or installed shortcut.')
            url = f'http://127.0.0.1:{port}'
            desktop()
            if browser: webbrowser.open(url)
            return url
    portal = Path(application_home).resolve() / 'scripts' / 'project_portal.py'
    supervisor = Path(application_home).resolve() / 'scripts' / 'hub_launcher.py'
    if not portal.is_file() or not supervisor.is_file():
        raise LauncherError('The installed portal is missing; repair the application installation.')
    home.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment['PYTHONDONTWRITEBYTECODE'] = '1'
    environment['PROJECT_HUB_UI_LANGUAGE'] = config['language']
    environment['PROJECT_HUB_RUNTIME_MODE'] = 'development' if development else 'source' if source else 'installed'
    environment['PROJECT_HUB_DIAGNOSTICS_HOME'] = str(config_path.parent / 'diagnostics')
    # Windows spawn children can have no stderr until their worker entry point.
    # Enable faulthandler explicitly with the durable file after Python starts.
    environment.pop('PYTHONFAULTHANDLER', None)
    environment['PYTHONUNBUFFERED'] = '1'
    environment.pop('PROJECT_HUB_CODEX_ADAPTER', None)
    environment.pop('PROJECT_HUB_ASGI_CATALOG', None)
    command = [sys.executable, '-B', str(supervisor), '--supervise', '--config', str(config_path)]
    # Keep the supervisor outside the swappable data home. It survives the
    # server drain while publication renames that directory.
    process = start_supervisor(command, config_path, environment, source=source, development=development)
    # An existing data home may need its verified full backup before the first
    # upgraded server can listen. Ordinary ready homes still return immediately.
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline:
            code = process.poll()
            if code not in (None, 0):
                raise LauncherError(f'The portal exited before becoming ready (exit {code}).')
            port = remembered_port(runtime, home) or config['port']
            body = health(port)
            if matches_home(body, home) and matches_program(body, application_home):
                if isinstance(process, DesktopSupervisor) and process.pid is None:
                    time.sleep(.1)
                    continue
                url = f'http://127.0.0.1:{port}'
                if isinstance(process, DesktopSupervisor):
                    # The independent supervisor owns and repairs its tray.
                    # Never race it by creating a tray tied to this caller.
                    if not development:
                        from hub_desktop import wait_for_tray
                        wait_for_tray(config_path, application_home=application_home)
                else:
                    desktop()
                if browser: webbrowser.open(url)
                return url
            time.sleep(.1)
        raise LauncherError('The portal did not become ready in time; no browser was opened.')
    except BaseException:
        # A supervisor may already own a live server. Do not kill it after an
        # uncertain health read; another shortcut can reconnect to that instance.
        raise
    finally:
        if isinstance(process, DesktopSupervisor):
            process.receipt.unlink(missing_ok=True)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description='Configure or open the installed standalone Project Hub.')
    parser.add_argument('--configure', action='store_true')
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--supervise', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--stop', action='store_true', help='Gracefully stop the selected Hub runtime')
    parser.add_argument('--no-browser', action='store_true', help='Start or verify the portal without opening a browser')
    parser.add_argument('--language', choices=('ru', 'en'), default='ru')
    parser.add_argument('--config', type=Path, help='External installation configuration path')
    parser.add_argument('--data-home', type=Path, help='Initial external data home; existing choices are preserved')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT)
    parser.add_argument('--source', action='store_true', help='Launch the source runtime through the common lifecycle')
    parser.add_argument('--desktop-launch-id', help=argparse.SUPPRESS)
    parser.add_argument('--desktop-entry', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--instance-home', type=Path, help=argparse.SUPPRESS)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--mode', choices=('work', 'development'), default='work',
                      help='Work uses the shared main runtime; development requires isolated configuration and data')
    mode.add_argument('--development', dest='mode', action='store_const', const='development',
                      help='Alias for --mode development')
    parser.add_argument('--switch', action='store_true', help='Gracefully stop the verified main runtime and switch to this launcher')
    args = parser.parse_args(argv)
    args.development = args.mode == 'development'
    if not args.configure and not args.open and not args.supervise and not args.stop:
        parser.error('Choose --configure or --open.')
    if args.desktop_launch_id and (not args.supervise or not args.source or
            len(args.desktop_launch_id) != 32 or any(c not in '0123456789abcdef' for c in args.desktop_launch_id)):
        parser.error('Invalid desktop supervisor request.')
    if args.desktop_entry and (not args.source or args.supervise or not args.desktop_entry.is_absolute() or
            args.desktop_entry.name != 'result.json' or not args.desktop_entry.parent.name.startswith('hub-source-control-')):
        parser.error('Invalid desktop source controller request.')
    if args.instance_home is not None and not (args.desktop_launch_id or args.desktop_entry):
        parser.error('--instance-home is internal to a desktop supervisor request.')
    if source_desktop_controller_required(args):
        # A packaged caller can see a different AppData overlay. Delegate before
        # any diagnostics, locks, registration pointers or configuration writes.
        from windows_desktop import run_controller
        from hub_instance import directory
        try:
            response = run_controller(argv, directory())
            if response.get('url') and sys.stdout is not None:
                print(response['url'])
            if response['exitCode'] and sys.stderr is not None:
                print('Source Hub operation failed; inspect Hub launcher diagnostics.', file=sys.stderr)
            return response['exitCode']
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            report_error(error)
            return 1
    exit_code = 1
    controller_url = None
    try:
        if args.desktop_entry:
            from windows_desktop import desktop_identity
            from runtime_diagnostics import process_context
            from hub_lifecycle import atomic_json
            context = process_context()
            job = context.get('windowsJob', {})
            if context.get('restrictedToken') is not False or context.get('parentPid') != desktop_identity()['desktopPid'] or \
                    not (job.get('member') is False or job.get('killOnClose') is False):
                raise LauncherError('The source controller is not running in the independent Windows desktop context.')
            atomic_json(external_path(args.desktop_entry.with_name('started.json')), dict(pid=os.getpid()))
            if args.instance_home is not None:
                os.environ['PROJECT_HUB_INSTANCE_HOME'] = str(external_path(args.instance_home))
        import runtime_diagnostics as diagnostics
        diagnostic_config=external_path(args.config or default_base() / 'installation.json',application_home=APPLICATION_HOME)
        diagnostics.configure('supervisor' if args.supervise else 'launcher',directory=diagnostic_config.parent / 'diagnostics',
                              codeRoot=str(APPLICATION_HOME),config=str(diagnostic_config),mode=os.environ.get('PROJECT_HUB_RUNTIME_MODE','source' if args.source else 'installed'))
        if args.development and args.config is None:
            raise LauncherError('Development mode requires an explicit external --config and separate data folder.')
        if args.development and args.switch:
            raise LauncherError('Switching the main runtime is only available in work mode.')
        if args.stop:
            stop_runtime(args.config, development=args.development)
            exit_code = 0
            return 0
        if args.supervise:
            if args.source:
                os.environ['PROJECT_HUB_RUNTIME_MODE'] = 'development' if args.development else 'source'
            if args.desktop_launch_id:
                from hub_lifecycle import atomic_json
                context = diagnostics.process_context()
                job = context.get('windowsJob', {})
                independent = context.get('restrictedToken') is False and \
                    (job.get('member') is False or job.get('killOnClose') is False)
                receipt = diagnostic_config.parent / 'diagnostics' / f'desktop-launch-{args.desktop_launch_id}.json'
                atomic_json(receipt, dict(state='started' if independent else 'failed', process=context))
                diagnostics.record('supervisor.desktop_launch', independent=independent, process=context)
                if not independent:
                    raise LauncherError('The Windows desktop did not provide an independent supervisor. No server was started.')
                if args.instance_home is not None:
                    os.environ['PROJECT_HUB_INSTANCE_HOME'] = str(external_path(args.instance_home))
            from hub_lifecycle import supervise
            try:
                result = supervise(external_path(args.config or default_base() / 'installation.json'), application_home=APPLICATION_HOME)
            except TimeoutError:
                result = 0  # An existing supervisor owns this installation.
            if args.desktop_launch_id and receipt.exists():
                # The parent removes this short-lived receipt after readiness.
                # A losing launch race exits successfully and reconnects to the
                # verified existing runtime, just like the ordinary Popen path.
                atomic_json(receipt, dict(state='exited', exitCode=result, process=context))
            return result
        if args.configure:
            config = configure(args.config, language=args.language, data_home=args.data_home, port=args.port)
            if args.development:
                from hub_instance import check_development_home
                check_development_home(config['dataHome'], args.config, APPLICATION_HOME)
            if not args.development:
                from hub_instance import register_primary
                register_primary(args.config or default_base() / 'installation.json',APPLICATION_HOME)
        if args.open:
            url = open_hub(args.config, browser=not args.no_browser, development=args.development,
                           switch=args.switch, source=args.source)
            if sys.stdout is not None: print(url)
            controller_url = url
        exit_code = 0
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        diagnostics.exception('launcher.failed',error)
        report_error(error)
        return 1
    finally:
        if args.desktop_entry:
            from hub_lifecycle import atomic_json
            atomic_json(external_path(args.desktop_entry), dict(exitCode=exit_code, url=controller_url))
        if 'diagnostics' in locals():
            diagnostics.cleanup()


def source_desktop_controller_required(args):
    return os.name == 'nt' and args.source and not args.supervise and not args.desktop_entry


if __name__ == '__main__':
    sys.exit(main())
