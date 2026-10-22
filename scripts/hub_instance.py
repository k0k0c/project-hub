"""Local main-runtime ownership shared by source and packaged launchers.

The OS-held lease, not a PID file or a TCP port, determines ownership. Metadata
is only used after verifying that lease and the matching loopback health reply.
Explicit development runtimes skip the main lease, never the data-home lease.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import time


def directory():
    from hub_launcher import default_base, external_path
    return external_path(os.environ.get('PROJECT_HUB_INSTANCE_HOME') or default_base() / 'runtime')


def development():
    return os.environ.get('PROJECT_HUB_RUNTIME_MODE') == 'development'


@contextmanager
def main_lease():
    from hub_lifecycle import file_lock
    if development():
        yield
    else:
        with file_lock(directory() / 'main.lock'):
            yield


def publish(config, application_home, home, port):
    if development():
        return
    from hub_lifecycle import atomic_json
    atomic_json(directory() / 'main.json', dict(schemaVersion=1,
        config=str(config) if config is not None else None,
        applicationHome=str(Path(application_home).resolve()), dataHome=str(Path(home).resolve()),
        port=port, mode=os.environ.get('PROJECT_HUB_RUNTIME_MODE', 'source'),
        pythonExecutable=sys.executable,
        at=time.time(), pid=os.getpid()))


def register_primary(config, application_home):
    """Portable pointers to configured main storage, including inactive homes."""
    from hub_lifecycle import file_lock, atomic_json
    from hub_launcher import external_path, read_json, LauncherError
    config = str(external_path(config, application_home=application_home))
    path = directory() / 'configurations.json'
    with file_lock(path.with_suffix('.lock'), timeout=5):
        try:
            row = read_json(path)
        except FileNotFoundError:
            row = {'schemaVersion':1,'configs':[]}
        if (not isinstance(row,dict) or set(row) != {'schemaVersion','configs'} or row['schemaVersion'] != 1 or
                not isinstance(row['configs'],list) or any(not isinstance(p,str) for p in row['configs'])):
            raise LauncherError('Invalid main configuration pointers; preserve the runtime metadata for recovery.')
        if config not in row['configs']:
            row['configs'].append(config)
            import json
            if len(json.dumps(row).encode()) > 8000:
                raise LauncherError('Too many primary configuration pointers; preserve them for recovery.')
            atomic_json(path,row)


def active():
    """Return a verified owned runtime; never trust stale process metadata."""
    from hub_lifecycle import file_lock
    from hub_launcher import read_json, health, matches_home, matches_program, LauncherError
    root = directory()
    if not (root / 'main.lock').is_file():
        return None
    try:
        with file_lock(root / 'main.lock', create=False):
            return None
    except TimeoutError:
        pass
    try:
        row = read_json(root / 'main.json')
        if not isinstance(row, dict) or row.get('schemaVersion') != 1 or type(row.get('port')) is not int:
            raise ValueError('Invalid main runtime state')
        body = health(row['port'])
        if matches_home(body, Path(row['dataHome'])) and matches_program(body, row['applicationHome']):
            return row
    except (OSError, ValueError, KeyError, TypeError):
        pass
    # Do not turn a temporarily unavailable owner into permission for a duplicate.
    raise LauncherError('The main Hub runtime is starting or stopping. Retry after it finishes.')


def same_path(left, right):
    return os.path.normcase(str(Path(left).resolve())) == os.path.normcase(str(Path(right).resolve()))


def check_development_home(home, config, application_home):
    """Reject parallel runs against the active or configured primary storage."""
    from hub_launcher import default_base, read_json, external_path, LauncherError
    home = external_path(home, application_home=application_home)
    primary_config = default_base() / 'installation.json'
    configs = [primary_config]
    try:
        pointers = read_json(directory() / 'configurations.json')
    except FileNotFoundError:
        pointers = None
    if pointers is not None:
        if (not isinstance(pointers,dict) or pointers.get('schemaVersion') != 1 or
                not isinstance(pointers.get('configs'),list) or any(not isinstance(p,str) for p in pointers['configs'])):
            raise LauncherError('Invalid main configuration pointers; development launch was refused.')
        configs.extend(Path(p) for p in pointers['configs'])
    for primary_config in configs:
        if same_path(config, primary_config):
            raise LauncherError('Development mode requires its own configuration and data folder.')
        try:
            primary = read_json(external_path(primary_config, application_home=application_home))
        except FileNotFoundError:
            continue
        if isinstance(primary, dict) and isinstance(primary.get('dataHome'), str) and same_path(home, primary['dataHome']):
            raise LauncherError('Development mode cannot use the installed Hub data folder or another primary home. Use an inactive copy.')
    row = active()
    if row is not None and same_path(home, row['dataHome']):
        raise LauncherError('Development mode cannot use the main Hub data folder. Use an inactive copy.')
