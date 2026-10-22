"""Installer maintenance transactions; never migrate or remove user storage.

Run from the installer's private temporary Python during replacement. A durable
external receipt and verified prior payload permit recovery after interruption.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid

from hub_launcher import (LauncherError, configure, default_base, external_path,
                          health, read_json, remembered_port, state_path, stop_hub,
                          validate_config)
from hub_lifecycle import atomic_json, file_lock

MANAGED = ('app', 'runtime', 'project-hub.cmd', 'brand.ico', 'distribution.json')
DESTINATION_NOT_EMPTY = 3


class DestinationNotEmpty(LauncherError):
    """A new installation would replace files not identified as Hub's program."""


def destination_conflicts(app):
    """Ignore only empty program directories and generated Python bytecode."""
    if not app.exists():
        return []
    checked_tree(app)
    conflicts = []
    for entry in sorted(app.iterdir()):
        if entry.name in ('app', 'runtime') and entry.is_dir():
            for path in sorted(entry.rglob('*')):
                if path.is_dir():
                    continue
                if path.is_file() and path.parent.name == '__pycache__' and \
                        re.fullmatch(r'[^.]+\.cpython-\d+(?:\.opt-\d+)?\.pyc', path.name):
                    continue
                conflicts.append(path.relative_to(app).as_posix())
                if len(conflicts) == 8:
                    return conflicts
        else:
            conflicts.append(entry.name)
            if len(conflicts) == 8:
                return conflicts
    return conflicts


def checked_path(value):
    path = Path(value)
    if not path.is_absolute():
        raise LauncherError('Maintenance requires absolute paths')
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            info = item.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise LauncherError('Maintenance paths cannot contain links or reparse points')
    return path.resolve()


def checked_tree(root):
    checked_path(root)
    for directory, names, files in os.walk(root, followlinks=False):
        for name in (*names, *files):
            checked_path(Path(directory) / name)


def checksum(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root):
    checked_tree(root)
    return {p.relative_to(root).as_posix():checksum(p) for p in sorted(root.rglob('*')) if p.is_file()}


def restore_runtime(source, target):
    """Keep identical loaded runtime files in place for existing MCP bridges."""
    old, current = inventory(source), inventory(target) if target.exists() else {}
    for relative in current.keys() - old.keys():
        checked_path(target / relative).unlink()
    for relative, expected in old.items():
        destination = checked_path(target / relative)
        if current.get(relative) == expected:
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination)
    for directory in sorted((p for p in target.rglob('*') if p.is_dir()), key=lambda p:len(p.parts), reverse=True):
        if not any(directory.iterdir()):
            directory.rmdir()


def paths(app, config):
    app = checked_path(app)
    if app.parent == app:
        raise LauncherError('Choose a dedicated application directory')
    if os.name == 'nt':
        # Depth does not identify a safe directory: a drive's direct child is
        # valid, but shared system/profile roots must never be program targets.
        protected = {Path(value).resolve() for name in (
            'SystemRoot', 'WINDIR', 'ProgramFiles', 'ProgramFiles(x86)',
            'ProgramW6432', 'ProgramData', 'USERPROFILE', 'PUBLIC',
            'LOCALAPPDATA', 'APPDATA') if (value := os.environ.get(name))}
        if profile := os.environ.get('USERPROFILE'):
            protected.add(Path(profile).resolve().parent)
        if app in protected:
            raise LauncherError('Choose a dedicated application directory, not a system or profile directory')
    config = external_path(config, application_home=app)
    return app, config, config.parent / 'updates' / 'current.json'


def read_transaction(app, config, receipt, *, completed_elsewhere=False):
    row = read_json(receipt)
    if not isinstance(row, dict) or row.get('schemaVersion') != 1 or \
            row.get('config') != str(config):
        raise LauncherError('Update receipt does not belong to this installation')
    if row.get('application') != str(app) and not (completed_elsewhere and
            isinstance(row.get('application'), str) and Path(row['application']).is_absolute() and
            row.get('status') in ('committed', 'rolled-back', 'first-install-failed')):
        raise LauncherError('Update receipt does not belong to this installation')
    identifier = row.get('id')
    if not isinstance(identifier, str) or len(identifier) != 32 or any(c not in '0123456789abcdef' for c in identifier):
        raise LauncherError('Invalid update receipt identifier')
    return row, checked_path(receipt.parent / identifier / 'previous')


def check_destination(app, config):
    """Read-only directory-page check; preparation owns recovery and shutdown."""
    app, config, receipt = paths(app, config)
    if receipt.exists():
        row, _ = read_transaction(app, config, receipt, completed_elsewhere=True)
        if row['application'] == str(app) and row['status'] in (
                'prepared', 'restoring', 'preparing', 'preparation-failed', 'first-install-failed'):
            return
    if (app / 'runtime/python.exe').is_file() and (app / 'app/scripts/hub_launcher.py').is_file():
        return
    conflicts = destination_conflicts(app)
    if conflicts:
        raise DestinationNotEmpty('The destination is not empty; unrecognized files remain: ' +
                                  ', '.join(conflicts) + '. Choose another directory.')


def prepare(app, config):
    app, config, receipt = paths(app, config)
    if receipt.exists():
        interrupted, _ = read_transaction(app, config, receipt, completed_elsewhere=True)
        if interrupted['status'] in ('prepared', 'restoring'):
            rollback(app, config)
    with file_lock(receipt.parent / 'maintenance.lock'):
        repairing_first = False
        if receipt.exists():
            previous, _ = read_transaction(app, config, receipt, completed_elsewhere=True)
            repairing_first = previous['application'] == str(app) and previous['status'] == 'first-install-failed'
            if previous['status'] in ('preparing', 'preparation-failed'):
                # Files are replaced only after the prepared receipt. An
                # interrupted snapshot leaves the original program in place.
                if previous['installed']:
                    verify_and_start(app, config)
                previous['status'] = 'rolled-back'
                atomic_json(receipt, previous)
            if previous['status'] not in ('committed', 'rolled-back', 'first-install-failed'):
                raise LauncherError('An interrupted update requires recovery before another installation')
        installed = not repairing_first and (app / 'runtime/python.exe').is_file() and (app / 'app/scripts/hub_launcher.py').is_file()
        if not installed and not repairing_first:
            conflicts = destination_conflicts(app)
            if conflicts:
                raise DestinationNotEmpty('The destination is not empty; unrecognized files remain: ' +
                                          ', '.join(conflicts) + '. Choose another directory.')
        if config.exists():
            validate_config(read_json(config), application_home=app)
        stop_hub(config, application_home=app / 'app')
        row = dict(schemaVersion=1, id=uuid.uuid4().hex, application=str(app), config=str(config),
                   status='preparing', installed=installed,
                   configSha256=checksum(config) if config.exists() else None)
        try:
            atomic_json(receipt, row)
            prior = checked_path(receipt.parent / row['id'] / 'previous')
            prior.mkdir(parents=True)
            if installed:
                for name in MANAGED:
                    source = app / name
                    if not source.exists():
                        continue
                    checked_tree(source)
                    if source.is_dir():
                        shutil.copytree(source, prior / name)
                    else:
                        shutil.copy2(source, prior / name)
                files = inventory(prior)
                if files != {p.relative_to(app).as_posix():checksum(p)
                             for name in MANAGED for p in ((app/name).rglob('*') if (app/name).is_dir() else [app/name])
                             if p.is_file()}:
                    raise LauncherError('Previous program changed during snapshot')
                atomic_json(prior.parent / 'files.json', files)
        except (ValueError, OSError) as error:
            row['status'] = 'preparation-failed'
            try:
                atomic_json(receipt, row)
            except OSError:
                pass  # A full disk must not prevent restarting the unchanged program.
            if installed:
                try:
                    verify_and_start(app, config)
                except Exception as recovery:
                    raise LauncherError(f'Snapshot failed: {error}. Restart the unchanged program: {recovery}') from error
            raise
        row['status'] = 'prepared'
        atomic_json(receipt, row)
        return row


def verify_and_start(app, config):
    executable = app / 'runtime/python.exe'
    launcher = app / 'app/scripts/hub_launcher.py'
    if not executable.is_file() or not launcher.is_file():
        raise LauncherError('Installed runtime is incomplete')
    manifest = app / 'distribution.json'
    if manifest.is_file():
        metadata = json.loads(manifest.read_text(encoding='utf-8'))
        files = metadata.get('files') if isinstance(metadata, dict) else None
        if not isinstance(metadata, dict) or metadata.get('schemaVersion') != 1 or not isinstance(files, dict) or not files:
            raise LauncherError('Invalid installed program manifest')
        for relative, expected in files.items():
            target = checked_path(app / relative)
            if not target.is_relative_to(app) or not target.is_file() or checksum(target) != expected:
                raise LauncherError(f'Installed program failed file verification: {relative}')
    from hub_instance import active, same_path, register_primary
    register_primary(config,app)
    current = active()
    if current is not None and (not current['config'] or not same_path(current['config'], config) or
                                not same_path(current['applicationHome'], app / 'app')):
        # An explicit source/main launch owns the machine. Verify the new runtime
        # without acquiring its production data or silently switching versions.
        subprocess.run([str(executable), '-B', '-c',
            'import project_portal, agent_api, mcp_transport, hub_launcher, hub_lifecycle, hub_tray'],
            check=True, timeout=30, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return False
    subprocess.run([str(executable), '-B', str(launcher), '--open', '--no-browser', '--config', str(config)],
                   check=True, timeout=45, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    value = validate_config(read_json(config), application_home=app)
    home = Path(value['dataHome'])
    port = remembered_port(state_path(config, app), home) or value['port']
    body = health(port)
    from hub_launcher import matches_home, matches_program
    if not matches_home(body, home) or body.get('supervised') is not True or \
            not matches_program(body, app / 'app'):
        raise LauncherError('The installed runtime did not confirm its storage and identity')
    if not (app / 'app/scripts/agent_api.py').is_file() or not (app / 'app/scripts/mcp_transport.py').is_file():
        raise LauncherError('The HTTP agent connection runtime is missing')
    return True


def rollback(app, config):
    app, config, receipt = paths(app, config)
    with file_lock(receipt.parent / 'maintenance.lock'):
        row, prior = read_transaction(app, config, receipt)
        if row['status'] in ('rolled-back', 'first-install-failed'):
            return row
        if row['status'] == 'committed':
            raise LauncherError('A committed update cannot be rolled back by an old request')
        if not row['installed']:
            stop_hub(config, application_home=app / 'app')
            row['status'] = 'first-install-failed'
            atomic_json(receipt, row)
            return row
        manifest = checked_path(prior.parent / 'files.json')
        if not manifest.is_file() or inventory(prior) != json.loads(manifest.read_text(encoding='utf-8')):
            raise LauncherError('The previous program snapshot failed verification; no files were removed')
        if Path(sys.executable).resolve().is_relative_to(app):
            raise LauncherError('Run recovery from a compatible Python runtime outside the application being restored')
        stop_hub(config, application_home=app / 'app')
        # Each removal target is fixed and confirmed within the application root.
        for name in MANAGED:
            target = checked_path(app / name)
            if not target.is_relative_to(app) or target == app:
                raise LauncherError('Unsafe program replacement target')
            checked_tree(target)
        row['status'] = 'restoring'
        atomic_json(receipt, row)
        for name in MANAGED:
            target, source = app / name, prior / name
            if name == 'runtime' and source.is_dir():
                restore_runtime(source, target)
                continue
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
            if source.is_dir():
                shutil.copytree(source, target)
            elif source.is_file():
                shutil.copy2(source, target)
        verify_and_start(app, config)
        row['status'] = 'rolled-back'
        atomic_json(receipt, row)
        return row


def finish(app, config, *, language='en'):
    app, config, receipt = paths(app, config)
    try:
        with file_lock(receipt.parent / 'maintenance.lock'):
            row, _ = read_transaction(app, config, receipt)
            if row['status'] == 'committed':
                return row
            if row['status'] != 'prepared':
                raise LauncherError('Program replacement was not prepared')
            configure(config, language=language, application_home=app)
            if row['configSha256'] and checksum(config) != row['configSha256']:
                raise LauncherError('Installation settings changed during replacement')
            started = verify_and_start(app, config)
            row['launchDeferred'] = started is False
            row['status'] = 'committed'
            atomic_json(receipt, row)
            return row
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        try:
            restored = rollback(app, config)
        except Exception as recovery:
            raise LauncherError(f'Update failed: {error}. Recovery required: {recovery}') from error
        outcome = 'Previous program restored.' if restored['status'] == 'rolled-back' else 'Repair the first installation; user data was preserved.'
        raise LauncherError(f'Update failed: {error}. {outcome}') from error


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check-destination','prepare','finish','rollback','stop'))
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=default_base() / 'installation.json')
    parser.add_argument('--language', choices=('en','ru'), default='en')
    parser.add_argument('--installer', type=Path, help='Record this verified local installer for future maintenance')
    args = parser.parse_args(argv)
    try:
        if args.action == 'check-destination':
            check_destination(args.app, args.config)
        elif args.action == 'stop':
            app, config, _ = paths(args.app, args.config)
            stop_hub(config, application_home=app / 'app')
        else:
            result = finish(args.app, args.config, language=args.language) if args.action == 'finish' else \
                globals()[args.action](args.app, args.config)
            if args.action == 'finish' and args.installer is not None:
                installer = checked_path(args.installer)
                if not installer.is_file() or installer.suffix.lower() != '.exe':
                    raise LauncherError('Use an existing installer executable')
                atomic_json(args.config.with_name('maintenance-installer.json'),
                            {'schemaVersion':1, 'path':str(installer), 'sha256':checksum(installer)})
            if sys.stdout is not None:
                print(json.dumps(result))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        try:
            # Diagnose a rejected application path without validating it again.
            # A rejected drive/share root is not an application directory; its
            # external configuration may still hold the maintenance diagnostic.
            config = external_path(args.config)
            if args.app.is_absolute() and args.app.parent != args.app:
                config = external_path(config, application_home=args.app)
            diagnostic = checked_path(config.parent / 'updates' / 'last-error.txt')
            diagnostic.parent.mkdir(parents=True, exist_ok=True)
            diagnostic.write_text(str(error) + '\n', encoding='utf-8')
        except (ValueError, OSError):
            pass
        if sys.stderr is not None:
            print(str(error), file=sys.stderr)
        return DESTINATION_NOT_EMPTY if isinstance(error, DestinationNotEmpty) else 1


if __name__ == '__main__':
    sys.exit(main())
