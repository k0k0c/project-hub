"""Install and run a transferred Project Hub bundle on this machine."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent
MARKER = '.project-hub-install.json'
MARKETPLACE = 'project-hub-local'


def default_install_root():
    base = Path(os.environ.get('LOCALAPPDATA', Path.home() / '.local/share'))
    return base / 'ProjectHub/app'


def default_data_home():
    if os.environ.get('PROJECT_HUB_HOME'):
        return Path(os.environ['PROJECT_HUB_HOME']).expanduser().resolve()
    return default_install_root().parent / 'data'


def verify_bundle(source=ROOT):
    source = Path(source).resolve()
    manifest = json.loads((source / 'distribution.json').read_text(encoding='utf-8'))
    if not isinstance(manifest, dict):
        raise ValueError('Invalid Project Hub distribution manifest')
    files = manifest.get('files')
    if manifest.get('schemaVersion') != 1 or manifest.get('name') != 'project-hub' or not isinstance(files, dict) or not 1 <= len(files) <= 5000:
        raise ValueError('Invalid Project Hub distribution manifest')
    required = {'setup_project_hub.py', 'scripts/project_portal.py', 'scripts/prepare_project_hub_plugin.py',
                'tools/project-portal/plugins/project-hub/plugin.json'}
    if not required <= files.keys():
        raise ValueError('Distribution is missing required runtime files')
    if not isinstance(manifest.get('version'), str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?', manifest['version']):
        raise ValueError('Invalid distribution version')
    for name, digest in files.items():
        if (not isinstance(name, str) or '\\' in name or ':' in name
                or name.startswith('/') or any(p in ('', '.', '..') for p in name.split('/'))
                or any(p in ('.git', '.codex', '.agents', '.local', '__pycache__') for p in name.split('/'))
                or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise ValueError('Invalid distribution file reference')
        path = source.joinpath(*PurePosixPath(name).parts)
        if (path.is_symlink() or not path.resolve().is_relative_to(source)
                or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest):
            raise ValueError('Distribution integrity check failed: ' + name)
    tree = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if tree != manifest.get('sourceTreeSha256'):
        raise ValueError('Distribution tree hash does not match')
    return manifest


def installed_config(app):
    config = json.loads((app / MARKER).read_text(encoding='utf-8'))
    if config.get('schemaVersion') != 1 or config.get('kind') != 'project-hub-local-installation':
        raise ValueError('Destination is not an owned Project Hub installation')
    return config


def separate_data(app, data):
    if data.is_relative_to(app) or app.is_relative_to(data):
        raise ValueError('Runtime and writable data must use separate directories')


def codex_command(executable, *args):
    result = subprocess.run([executable, 'plugin', *args], capture_output=True, text=True,
                            encoding='utf-8', errors='replace', timeout=120)
    if result.returncode:
        raise RuntimeError('Codex plugin command failed: ' + (result.stderr or result.stdout).strip()[:1500])
    return json.loads(result.stdout)


def inspect_codex(executable):
    snapshot = codex_command(executable, 'list', '--json')
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('installed'), list):
        raise ValueError('Unknown Codex plugin list format')
    for plugin in snapshot['installed']:
        if not isinstance(plugin, dict):
            raise ValueError('Unknown Codex plugin entry')
        if plugin.get('name') == 'project-hub' and plugin.get('marketplaceName') != MARKETPLACE:
            raise ValueError('Another marketplace owns project-hub; inspect the existing installation first')


def install(source=ROOT, install_root=None, data_home=None, port=None, skip_codex_registration=False,
            user_skill_root=None):
    source = Path(source).resolve()
    manifest = verify_bundle(source)
    app = Path(install_root or default_install_root()).expanduser().resolve()
    previous = None
    if app.exists():
        if not (app / MARKER).is_file():
            raise ValueError('Refusing to overwrite an unowned installation directory')
        previous = installed_config(app)
    if app.is_relative_to(source) or source.is_relative_to(app):
        raise ValueError('Install destination must be separate from the extracted bundle')
    data = Path(data_home or (previous or {}).get('dataHome') or default_data_home()).expanduser().resolve()
    separate_data(app, data)
    skill_root = Path(user_skill_root or (previous or {}).get('userSkillRoot') or
                     (data / 'instructions/project-hub-user' if skip_codex_registration else
                      Path.home() / '.agents/skills/project-hub-user')).expanduser().absolute()
    if skill_root.name != 'project-hub-user' or skill_root.resolve() != skill_root:
        raise ValueError('Use a separate project-hub-user skill directory')
    if skill_root.is_relative_to(app) or app.is_relative_to(skill_root):
        raise ValueError('User instructions and installed runtime must be separate')
    port = port if port is not None else (previous or {}).get('port', 8769)
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError('Use a TCP port from 1 to 65535')
    if sys.version_info < (3, 10):
        raise ValueError('Python 3.10 or newer is required')
    if not shutil.which('git'):
        raise ValueError('Install Git and make it available on PATH')
    codex = None if skip_codex_registration else shutil.which('codex')
    if not skip_codex_registration:
        if not codex:
            raise ValueError('Install Codex CLI and make codex available on PATH')
        inspect_codex(codex)
    app.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + app.name + '-install-', dir=app.parent)).resolve()
    backup = None
    try:
        for name in ['distribution.json', *manifest['files']]:
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)
        spec = importlib.util.spec_from_file_location('prepare_local_' + uuid.uuid4().hex,
                                                     stage / 'scripts/prepare_project_hub_plugin.py')
        prepare_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prepare_module)
        package = stage / 'plugins/project-hub'
        prepare_module.prepare(package, 'http://127.0.0.1:' + str(port), runtime_root=app / 'plugins/project-hub',
                               user_skill_root=skill_root, data_home=data)
        # Load defaults from this verified bundle, even if another version's module
        # is already imported in the process (e.g. an update or receiver fixture).
        instruction_spec = importlib.util.spec_from_file_location('hub_initializer_' + uuid.uuid4().hex,
                                                                  package / 'scripts/hub_instructions.py')
        instruction_module = importlib.util.module_from_spec(instruction_spec)
        instruction_spec.loader.exec_module(instruction_module)
        instruction_module.Instructions(data).initialize(skill_root, package_root=app / 'plugins/project-hub')
        cache_version = manifest['version'].split('+', 1)[0] + '+local.' + uuid.uuid4().hex[:12]
        for relative in ('plugin.json', '.codex-plugin/plugin.json'):
            path = package / relative
            metadata = json.loads(path.read_text(encoding='utf-8'))
            metadata['version'] = cache_version
            path.write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        marketplace = stage / '.agents/plugins/marketplace.json'
        marketplace.parent.mkdir(parents=True)
        marketplace.write_text(json.dumps(dict(name=MARKETPLACE, interface=dict(displayName='Project Hub local'),
            plugins=[dict(name='project-hub', source=dict(source='local', path='./plugins/project-hub'),
                          policy=dict(installation='AVAILABLE', authentication='ON_INSTALL'), category='Productivity')]), indent=2) + '\n', encoding='utf-8')
        config = dict(schemaVersion=1, kind='project-hub-local-installation', dataHome=str(data), port=port,
                      userSkillRoot=str(skill_root),
                      installationId=uuid.uuid4().hex,
                      sourceRevision=manifest.get('sourceRevision'), sourceTreeSha256=manifest['sourceTreeSha256'],
                      codexRegistered=False)
        (stage / MARKER).write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
        if app.exists():
            if previous is None or installed_config(app) != previous:
                raise ValueError('Installation destination changed; retry after inspecting it')
            backup = app.with_name(app.name + '-previous-' + uuid.uuid4().hex[:12])
            app.rename(backup)
        try:
            stage.rename(app)
        except OSError:
            if backup and not app.exists():
                backup.rename(app)
            raise
    finally:
        if stage.exists():
            if stage.parent != app.parent or not stage.name.startswith('.' + app.name + '-install-'):
                raise ValueError('Unexpected staging directory; cleanup stopped')
            shutil.rmtree(stage)
    if codex:
        codex_command(codex, 'marketplace', 'add', str(app), '--json')
        codex_command(codex, 'add', 'project-hub@' + MARKETPLACE, '--json')
        config['codexRegistered'] = True
        (app / MARKER).write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    return dict(installation=str(app), dataHome=str(data), url='http://127.0.0.1:' + str(port),
                userSkillRoot=str(skill_root),
                backup=str(backup) if backup else None, codexRegistered=bool(codex),
                hookTrust='Review the installed hook definition in Codex; trust is unchanged')


def serve(install_root=None):
    app = Path(install_root or default_install_root()).expanduser().resolve()
    config = installed_config(app)
    data = Path(config['dataHome']).resolve()
    separate_data(app, data)
    return subprocess.call([sys.executable, '-B', str(app / 'scripts/project_portal.py'),
        '--projects-home', str(data), 'serve', '--port', str(config['port'])], cwd=app)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('verify', help='Verify every bundled file before installation')
    for name in ('install', 'run', 'serve'):
        command = commands.add_parser(name)
        command.add_argument('--install-root', type=Path)
        if name != 'serve':
            command.add_argument('--data-home', type=Path)
            command.add_argument('--port', type=int)
            command.add_argument('--skip-codex-registration', action='store_true')
            command.add_argument('--user-skill-root', type=Path)
    args = parser.parse_args()
    if args.command == 'verify':
        manifest = verify_bundle()
        print(json.dumps(dict(verified=True, version=manifest['version'], files=len(manifest['files']))))
        return 0
    app = Path(args.install_root or default_install_root()).expanduser().resolve()
    if args.command == 'install' or (args.command == 'run' and (
            not (app / MARKER).is_file() or args.data_home is not None or args.port is not None or
            args.user_skill_root is not None)):
        print(json.dumps(install(install_root=app, data_home=args.data_home, port=args.port,
                                skip_codex_registration=args.skip_codex_registration,
                                user_skill_root=args.user_skill_root), indent=2), flush=True)
    if args.command in ('run', 'serve'):
        return serve(app)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
