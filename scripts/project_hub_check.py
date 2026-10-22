"""Independent local checks. No service, plugin transport or coordination imports."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fnmatch
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import time
import uuid

sys.dont_write_bytecode = True
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')

try:
    from check_paths import output_home
except ModuleNotFoundError:  # imported from the repository test harness
    from scripts.check_paths import output_home


PROFILES = ('auto', 'full', 'release', 'css', 'javascript', 'portal', 'core', 'package',
            'docs', 'documentation-ui', 'html-documents', 'plugin-docs', 'runner', 'artifacts', 'changesets')
CONFIG = '.project-hub/testing.json'
UNITTEST_RUNNER = 'scripts/project_hub_unittest.py'
AUTO_TEST_PROFILE = 'test-files'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':')).encode()


def git(root, *args):
    # Preserve GIT_INDEX_FILE here: a hook may be checking an alternate index.
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def collect(root, staged=False):
    """Read exact index blobs or tracked + nonignored working files, never .git."""
    entries = {}
    for row in git(root, 'ls-files', '--stage', '-z').split(b'\0'):
        if not row:
            continue
        meta, raw = row.split(b'\t', 1)
        mode, oid, stage = meta.decode().split()
        name = os.fsdecode(raw)
        if stage != '0' or mode not in ('100644', '100755'):
            raise ValueError(f'Unsupported conflicted index, symlink or submodule: {name}')
        entries[name] = (mode, oid)
    if not staged:
        for raw in git(root, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0'):
            if raw:
                entries.setdefault(os.fsdecode(raw), ('100644', None))
    files = {}
    for name, (mode, oid) in sorted(entries.items()):
        path = root / name
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise ValueError(f'Unsafe input path: {name}')
        if staged:
            data = git(root, 'cat-file', 'blob', oid)
        else:
            if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
                raise ValueError(f'Symlink input is not isolated: {name}')
            if not path.exists():
                continue
            data = path.read_bytes()
            if os.name != 'nt':
                mode = '100755' if path.stat().st_mode & 0o111 else '100644'
        files[name] = (mode, data)
    return files


def tree_key(files):
    return digest(canonical([(name, mode, digest(data)) for name, (mode, data) in sorted(files.items())]))


def input_manifest(files, origins=None):
    """The exact bytes available to validation, independent of evidence roles."""
    return [dict({'path': name, 'mode': mode, 'sha256': digest(data), 'size': len(data)},
                 **({'source': origins[name]} if origins and name in origins else {}))
            for name, (mode, data) in sorted(files.items())]


def validation_path(value, pattern=False):
    if (not isinstance(value, str) or not value or len(value) > 512 or '\\' in value or ':' in value
            or any(ord(c) < 32 for c in value) or value.startswith('/')
            or any(p in ('', '.', '..') for p in value.split('/'))
            or value.split('/')[0] in ('.git', '.local')
            or any(any(c in p for c in '<>"|') or p.rstrip(' .') != p
                   or p.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                                                *('COM' + str(i) for i in range(1, 10)),
                                                *('LPT' + str(i) for i in range(1, 10))} for p in value.split('/'))
            or (not pattern and any(c in value for c in '*?[]'))):
        raise ValueError('Validation inputs require safe relative paths')
    return value


def validation_policy(config):
    """The project owns its input/build graph; every checkout byte stays included."""
    policy = config.get('validationInputs', {'version': 1, 'artifacts': [], 'files': [], 'builds': [], 'profileDependencies': {}})
    if (not isinstance(policy, dict) or type(policy.get('version')) is not int or policy['version'] != 1
            or set(policy) - {'version', 'artifacts', 'files', 'builds', 'profileDependencies'}):
        raise ValueError('Unsupported validation input policy')
    for key in ('artifacts', 'files', 'builds'):
        if not isinstance(policy.get(key, []), list) or len(policy.get(key, [])) > 100:
            raise ValueError('Validation input declarations must be bounded lists')
    dependencies = policy.get('profileDependencies', {})
    if (not isinstance(dependencies, dict) or any(name not in config['profiles'] for name in dependencies)
            or any(not isinstance(values, list) or any(name not in config['profiles'] for name in values)
                   for values in dependencies.values())):
        raise ValueError('Unknown validation profile dependency')
    def visit(name, pending):
        if name in pending:
            raise ValueError('Validation profile dependencies must be acyclic')
        for target in dependencies.get(name, []):
            visit(target, pending | {name})
    for name in dependencies:
        visit(name, set())
    ids = set()
    for build in policy.get('builds', []):
        if (not isinstance(build, dict) or set(build) != {'id', 'argv', 'inputs', 'profiles'}
                or not isinstance(build['id'], str) or not re.fullmatch(r'[a-z0-9-]{1,80}', build['id'])
                or build['id'] in ids or not isinstance(build['argv'], list) or not 1 <= len(build['argv']) <= 100
                or any(not isinstance(arg, str) or not arg or '\0' in arg or len(arg) > 4000 for arg in build['argv'])
                or not isinstance(build['inputs'], list) or not 1 <= len(build['inputs']) <= 100
                or not isinstance(build['profiles'], list) or not build['profiles']
                or any(name not in config['profiles'] for name in build['profiles'])):
            raise ValueError('Invalid declared build dependency')
        ids.add(build['id'])
        for value in build['inputs']:
            validation_path(value, pattern=True)
    return policy


def resolve_validation_inputs(root, config, checkout, bindings=None):
    """Read pinned external bytes once; tests only receive their isolated copies.

    Locators are host bindings, never mutable Hub classification. Both descriptor
    and content hashes are checked. Roles describe the bytes and cannot omit them.
    """
    policy = validation_policy(config)
    files, origins = dict(checkout), {}
    bindings = os.environ if bindings is None else bindings
    total = 0
    def location(environment):
        if not isinstance(environment, str) or not re.fullmatch(r'PROJECT_HUB_INPUT_[A-Z0-9_]{1,100}', environment):
            raise ValueError('External inputs require a declared PROJECT_HUB_INPUT_ binding')
        value = bindings.get(environment)
        if not value or not Path(value).is_absolute():
            raise ValueError('Missing absolute external validation input binding: ' + environment)
        path = Path(value)
        if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in [path, *path.parents]):
            raise ValueError('External validation inputs cannot traverse links')
        if path.resolve().is_relative_to(Path(root).resolve()):
            raise ValueError('External validation inputs must be outside the checkout')
        return path
    def blob(directory, identifier, maximum):
        if not isinstance(identifier, str) or not re.fullmatch(r'[a-f0-9]{64}', identifier):
            raise ValueError('External input requires a SHA-256 identity')
        path = directory / 'blobs' / identifier[:2] / identifier
        if any(p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()) for p in (path, path.parent, path.parent.parent)):
            raise ValueError('Validation CAS cannot traverse links')
        if not path.is_file() or path.stat().st_size > maximum:
            raise ValueError('External validation blob missing or too large')
        data = path.read_bytes()
        if digest(data) != identifier:
            raise ValueError('External validation blob hash mismatch')
        return data
    for kind in ('files', 'artifacts'):
        for entry in policy.get(kind, []):
            fields = {'environment', 'path', 'sha256', 'mode'} if kind == 'files' else {'environment', 'path', 'ref'}
            if not isinstance(entry, dict) or set(entry) != fields:
                raise ValueError('Invalid external validation input declaration')
            target = validation_path(entry['path'])
            if any(name.casefold() == target.casefold() or name.casefold().startswith(target.casefold() + '/')
                   or target.casefold().startswith(name.casefold() + '/') for name in files):
                raise ValueError('External input collides with a snapshot path: ' + target)
            source = location(entry['environment'])
            if kind == 'files':
                if not source.is_file() or source.stat().st_size > 20 * 1024 * 1024 or entry['mode'] not in ('100644', '100755'):
                    raise ValueError('External validation input must be a bounded ordinary file')
                data, mode = source.read_bytes(), entry['mode']
                if not isinstance(entry['sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', entry['sha256']) or digest(data) != entry['sha256']:
                    raise ValueError('External validation input hash mismatch')
                origin = {'kind': 'dependency', 'binding': entry['environment'], 'sha256': entry['sha256']}
            else:
                parts = entry['ref'].split('/') if isinstance(entry['ref'], str) else []
                if len(parts) != 3 or parts[0] != 'hub-artifact' or '/' in parts[2] or validation_path('artifact/' + parts[2]) != 'artifact/' + parts[2]:
                    raise ValueError('Validation artifact requires an immutable hub-artifact reference')
                descriptor_bytes = blob(source, parts[1], 16000)
                descriptor = json.loads(descriptor_bytes)
                if (not isinstance(descriptor, dict) or type(descriptor.get('schemaVersion')) is not int or descriptor['schemaVersion'] != 1
                        or descriptor.get('kind') != 'artifact-descriptor' or descriptor.get('name') != parts[2]
                        or descriptor.get('version') != descriptor.get('contentHash') or type(descriptor.get('size')) is not int
                        or not 0 <= descriptor['size'] <= 20 * 1024 * 1024
                        or not isinstance(descriptor.get('artifactId'), str) or not 1 <= len(descriptor['artifactId']) <= 160
                        or any(ord(c) < 32 for c in descriptor['artifactId'])
                        or not isinstance(descriptor.get('provenance'), str) or not 1 <= len(descriptor['provenance']) <= 1000
                        or (descriptor.get('previous') is not None and (not isinstance(descriptor['previous'], str)
                            or not re.fullmatch(r'[a-f0-9]{64}', descriptor['previous'])))
                        or not isinstance(descriptor.get('roles'), list)
                        or any(role not in ('evidence', 'deliverable', 'product-input', 'test-fixture') for role in descriptor['roles'])):
                    raise ValueError('Invalid validation artifact descriptor')
                data, mode = blob(source, descriptor['contentHash'], 20 * 1024 * 1024), '100644'
                if len(data) != descriptor['size']:
                    raise ValueError('Validation artifact size mismatch')
                origin = {'kind': 'artifact', 'binding': entry['environment'], 'ref': entry['ref'],
                          'descriptorSha256': digest(descriptor_bytes), 'roles': descriptor['roles']}
            total += len(data)
            if total > 100 * 1024 * 1024:
                raise ValueError('External validation inputs exceed 100 MiB')
            files[target], origins[target] = (mode, data), origin
    for build in policy.get('builds', []):
        for pattern in build['inputs']:
            if not any(fnmatch.fnmatchcase(path, pattern) for path in files):
                raise ValueError('Declared build input is unavailable: ' + pattern)
    return files, origins, policy


def validation_profiles(policy, paths, profiles, reasons):
    selected = set(profiles)
    for build in policy.get('builds', []):
        if any(fnmatch.fnmatchcase(path, pattern) for path in paths for pattern in build['inputs']):
            selected.update(build['profiles'])
            reasons.append('build ' + build['id'] + ': ' + ', '.join(build['profiles']))
    pending = list(selected)
    while pending:
        for dependency in policy.get('profileDependencies', {}).get(pending.pop(), []):
            if dependency not in selected:
                selected.add(dependency)
                pending.append(dependency)
                reasons.append('declared profile dependency: ' + dependency)
    return ['full'] if 'full' in selected else sorted(selected)


def validation_commands(policy, profiles):
    return [build['argv'] for build in policy.get('builds', [])
            if 'full' in profiles or set(profiles).intersection(build['profiles'])]


def changed_paths(root, staged=False):
    args = ['diff', '--name-only', '--no-renames', '-z']
    if staged:
        args.append('--cached')
    else:
        # Unborn repositories have no HEAD; every input must be considered.
        try:
            git(root, 'rev-parse', '--verify', 'HEAD')
        except subprocess.CalledProcessError:
            return sorted(collect(root))
        args.append('HEAD')
    paths = {os.fsdecode(p) for p in git(root, *args).split(b'\0') if p}
    if not staged:
        paths.update(os.fsdecode(p) for p in git(root, 'ls-files', '--others', '--exclude-standard', '-z').split(b'\0') if p)
    return sorted(paths)


def diff_checks(root, staged):
    if staged:
        return [['git', 'diff', '--check', '--cached']]
    try:
        git(root, 'rev-parse', '--verify', 'HEAD')
    except subprocess.CalledProcessError:
        return [['git', 'diff', '--check', '--cached'], ['git', 'diff', '--check']]
    return [['git', 'diff', '--check', 'HEAD']]


def is_test_file(path):
    if not isinstance(path, str):
        return False
    directory, _, name = path.rpartition('/')
    return directory in ('scripts/tests', 'tests') and name.startswith('test_') and name.endswith('.py')


def source_test_policy(config):
    mapping = config.get('sourceTests', {})
    if not isinstance(mapping, dict):
        raise ValueError('sourceTests must map source files to explicit test files')
    for source, tests in mapping.items():
        validation_path(source)
        if not isinstance(tests, list) or not tests or any(not is_test_file(p) for p in tests):
            raise ValueError('sourceTests must name nonempty test file lists')
        for path in tests:
            validation_path(path)
    return mapping


def selected_test_paths(config, paths, profiles):
    if AUTO_TEST_PROFILE not in profiles:
        return []
    mapping = source_test_policy(config)
    return sorted({test for path in paths for test in
                   ([path] if is_test_file(path)
                    else mapping.get(path, []))})


def select_profiles(config, paths, requested):
    source_tests = source_test_policy(config)
    if requested == 'release':
        return ['full'], ['release alias: full validation']
    if requested != 'auto':
        if requested not in config['profiles']:
            raise ValueError(f'Unknown test profile: {requested}')
        return [requested], [f'explicit {requested} profile']
    selected, reasons = set(), []
    rules = list(config['rules']) + [dict(paths=build['inputs'], profiles=build['profiles'])
                                    for build in validation_policy(config).get('builds', [])]
    for path in paths:
        if is_test_file(path):
            # A test edit needs that test file, not every product profile which
            # happens to include it. Source edits still add their dependencies.
            selected.add(AUTO_TEST_PROFILE)
            reasons.append(f'{path}: exact changed test file')
            continue
        if path in source_tests:
            selected.add(AUTO_TEST_PROFILE)
            reasons.append(f'{path}: ' + ', '.join(source_tests[path]))
            continue
        matches = [rule for rule in rules
                   if any(fnmatch.fnmatchcase(path, p) for p in rule['paths'])
                   and not any(fnmatch.fnmatchcase(path, p) for p in rule.get('exclude', []))]
        if not matches:
            selected.add('full')
            reasons.append(f'{path}: unknown dependency coverage -> full')
        for rule in matches:
            selected.update(rule['profiles'])
            reasons.append(f"{path}: {', '.join(rule['profiles'])}")
    if not selected:
        return (['docs'], ['no changed paths: diff validation only']) if 'docs' in config['profiles'] else (['full'], ['no changed paths: full validation'])
    return (['full'] if 'full' in selected else sorted(selected)), reasons


def commands_for(config, profiles, files, changed_tests=()):
    patterns = [p for profile in profiles if profile != AUTO_TEST_PROFILE for p in config['profiles'][profile]]
    if AUTO_TEST_PROFILE in profiles:
        exact = sorted({path for path in changed_tests if is_test_file(path)})
        if not exact or any(path not in files for path in exact):
            raise ValueError('Changed test file is absent; select coverage for its deletion explicitly')
        patterns += exact
    tests = sorted(name for name in files if name.startswith(('scripts/tests/test_', 'tests/test_')) and
                   name.endswith('.py') and any(fnmatch.fnmatchcase(name if '/' in p else Path(name).name, p) for p in patterns))
    if not tests and patterns:
        raise ValueError('Selected profile contains no tests')
    commands = []
    for directory in ('scripts/tests', 'tests'):
        names = [Path(p).name for p in tests if str(Path(p).parent).replace('\\', '/') == directory]
        if not names:
            continue
        if UNITTEST_RUNNER in files:
            command = ['python', '-S', UNITTEST_RUNNER, '--directory', directory]
            if 'full' not in profiles:
                for name in names:
                    command += ['--pattern', name]
            commands.append(command)
        elif 'full' in profiles:
            commands.append(['python', '-S', '-m', 'unittest', 'discover', '-s', directory])
        else:
            commands += [['python', '-S', '-m', 'unittest', 'discover', '-s', directory, '-p', name] for name in names]
    syntax_profiles = config.get('javascriptProfiles', ['css', 'javascript', 'documentation-ui', 'html-documents', 'artifacts', 'full'])
    if (not isinstance(syntax_profiles, list) or any(not isinstance(p, str) for p in syntax_profiles)
            or ('javascriptProfiles' in config and any(p not in config['profiles'] and p != AUTO_TEST_PROFILE for p in syntax_profiles))):
        raise ValueError('javascriptProfiles must name configured profiles')
    if any(p in profiles for p in syntax_profiles):
        commands += [['node', '--check', p] for p in sorted(files) if p.startswith('tools/project-portal/web/') and p.endswith('.js')]
    return commands


def selection_scope(paths, scopes, staged, profile):
    if not scopes:
        return paths
    if staged or profile in ('full', 'release'):
        raise ValueError('--scope is only for worktree feedback; staged/full/release coverage cannot be narrowed')
    normalized = []
    for value in scopes:
        value = value.replace('\\', '/').rstrip('/')
        if not value or value.startswith('/') or ':' in value or any(p in ('', '.', '..') for p in value.split('/')):
            raise ValueError(f'Unsafe scope: {value}')
        normalized.append(value)
    selected = [p for p in paths if any(p == s or p.startswith(s + '/') for s in normalized)]
    if not selected:
        raise ValueError('--scope does not match any changed paths')
    return selected


def native_windows_environment(env, inherited_home=None):
    """Apply one native launch environment, including inside Git for Windows.

    Only shell-added variables, HOME/bin and Git installation PATH entries are replaced.
    All other variables/paths remain effective inputs, with their real hashes.
    """
    executable = shutil.which('git', path=env.get('PATH', ''))
    installation = None
    if executable:
        for candidate in list(Path(executable).resolve().parents)[:5]:
            if (candidate / 'cmd/git.exe').is_file() and (candidate / 'usr/bin/sh.exe').is_file():
                installation = candidate
                break
    if installation is None:
        raise ValueError('Native Windows validation requires a recognized Git for Windows installation')
    for key in ('MSYS', 'MSYS2_PATH_TYPE', 'EXEPATH', 'PLINK_PROTOCOL', 'CHERE_INVOKING',
                'MSYSTEM', 'MSYSTEM_CARCH', 'MSYSTEM_CHOST', 'MSYSTEM_PREFIX',
                'MINGW_PREFIX', 'MINGW_CHOST', 'MINGW_PACKAGE_PREFIX', 'SHELL',
                'SHLVL', '_', 'PWD', 'OLDPWD', 'TERM', 'COLORTERM'):
        env.pop(key, None)
    paths = [str(installation / 'cmd'), str(installation / 'usr/bin')]
    home_bin = (Path(inherited_home) / 'bin').resolve() if inherited_home else None
    for entry in env.get('PATH', '').split(os.pathsep):
        if not entry:
            continue
        value = Path(os.path.expandvars(entry.strip('"')))
        if not value.is_absolute():
            raise ValueError('Native Windows validation PATH requires absolute entries')
        value = value.resolve()
        # Git's shell inserts HOME/bin. HOME is replaced by a private empty
        # directory at launch, so its ambient executable directory cannot be
        # part of the isolated command search path.
        if not value.is_relative_to(installation) and value != home_bin:
            paths.append(str(value))
    unique = {}
    for path in paths:
        unique.setdefault(path.casefold(), path)
    env['PATH'] = os.pathsep.join(unique.values())
    return env


def base_environment(config=None):
    env = dict(os.environ)
    inherited_home = env.get('HOME') or env.get('USERPROFILE')
    for key in list(env):
        if key.startswith(('GIT_', 'PROJECT_HUB_', 'CODEX_', 'PYTHON', 'NODE_')) or key in ('PLUGIN_ROOT', 'VIRTUAL_ENV'):
            env.pop(key)
    env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', PYTHONHASHSEED='0',
               PYTHONIOENCODING='utf-8', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               PROJECT_HUB_URL='http://127.0.0.1:1', PROJECT_HUB_RUNTIME_MODE='development',
               GIT_CEILING_DIRECTORIES='<private>')
    # Replaced by private directories when executing; use stable placeholders in keys.
    for key in ('HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'CODEX_HOME', 'PROJECT_HUB_HOME', 'TMP', 'TEMP', 'TMPDIR'):
        env[key] = '<private>/' + key
    policy = (config or {}).get('executionEnvironment', {'version': 1, 'mode': 'captured'})
    if (not isinstance(policy, dict) or policy.get('version') != 1
            or set(policy) != {'version', 'mode'} or policy.get('mode') not in ('captured', 'native')):
        raise ValueError('Unsupported validation execution environment policy')
    if policy['mode'] == 'native' and os.name == 'nt':
        native_windows_environment(env, inherited_home)
    return env


def toolchain(env):
    result = {'platform': platform.platform(), 'python': sys.version}
    for name in ('python', 'node', 'git', 'powershell', 'pwsh', 'sh'):
        executable = sys.executable if name == 'python' else shutil.which(name, path=env.get('PATH', ''))
        if executable:
            path = Path(executable).resolve()
            result[name] = {'path': str(path), 'sha256': digest(path.read_bytes())}
        elif name in ('python', 'node', 'git'):
            raise ValueError(f'Required tool missing: {name}')
    # Include search paths and the entire effective environment without storing secrets.
    result['environment'] = digest(canonical(env))
    result['pythonPaths'] = sys.path
    # Tests use only stdlib and snapshot modules (-S excludes site startup and
    # installed packages). Hash runtime modules too: executable versions alone
    # miss patched standard libraries and native extensions.
    runtime = {}
    library = Path(sysconfig.get_path('stdlib'))
    for folder, directories, names in os.walk(library):
        directories[:] = sorted(d for d in directories if d not in ('site-packages', '__pycache__'))
        for name in sorted(names):
            path = Path(folder) / name
            if path.suffix in ('.py', '.pyd', '.dll', '.so', '.zip'):
                runtime[str(path)] = digest(path.read_bytes())
    for folder in (Path(sys.base_prefix), Path(sys.base_prefix) / 'DLLs'):
        if folder.is_dir():
            for path in sorted(folder.iterdir()):
                if path.is_file() and path.suffix in ('.dll', '.pyd', '.zip'):
                    runtime[str(path)] = digest(path.read_bytes())
    result['pythonRuntime'] = digest(canonical(runtime))
    return result


def resolve_commands(commands, env):
    """Resolve once against the environment that the launcher will actually use."""
    result = []
    for command in commands:
        executable = sys.executable if command[0] == 'python' else shutil.which(command[0], path=env.get('PATH', ''))
        if not executable:
            raise ValueError(f'Required tool missing: {command[0]}')
        path = Path(executable).resolve(strict=True)
        if not path.is_file():
            raise ValueError(f'Executable is not a file: {path}')
        result.append([str(path), *command[1:]])
    return result


def execution_spec(commands, files, env, timeout, origins=None):
    """Public, secret-free contract; env itself is retained only for execution."""
    argv = resolve_commands(commands, env)
    for index, command in enumerate(commands):
        if len(command) > 2 and command[2] == UNITTEST_RUNNER:
            argv[index] += ['--timings', f'<private>/timings-{index}.json']
    return {'schemaVersion': 1, 'argv': argv,
            'environmentSha256': digest(canonical(env)), 'runtime': toolchain(env),
            'inputManifestSha256': digest(canonical(input_manifest(files, origins))),
            'configSha256': digest(files[CONFIG][1]),
            'runnerSha256': digest(Path(__file__).read_bytes()), 'timeoutSeconds': timeout}


def preflight_spec(commands, env):
    argv = resolve_commands(commands, env)
    return {'argv': argv, 'environmentSha256': digest(canonical(env)),
            'executables': {command[0]: digest(Path(command[0]).read_bytes()) for command in argv},
            'timeoutSeconds': 60}


@contextmanager
def receipt_lock(path, timeout=600):
    """OS-owned lock, automatically released on exit/crash; no PID-file claims."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as stream:
        stream.seek(0, 2)
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        start = time.monotonic()
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
            except OSError:
                if time.monotonic() - start >= timeout:
                    raise TimeoutError(f'Timed out waiting for receipt lock: {path}')
                time.sleep(0.1)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def read_receipt(path, key, commands, spec, manifest):
    try:
        receipt = json.loads(path.read_text(encoding='utf-8'))
        if (receipt.get('key') == key and receipt.get('commands') == commands
                and receipt.get('executionSpec') == spec and receipt.get('inputManifest') == manifest
                and receipt.get('exitCode') == 0):
            result = Path(receipt['result'])
            log = Path(receipt['log'])
            if digest(result.read_bytes()) == receipt['resultHash'] and digest(log.read_bytes()) == receipt['logHash']:
                return receipt
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def reuse_diagnostic(output, inputs, commands, fresh=False):
    """Explain a miss without weakening receipt validation or recording env values."""
    if fresh:
        return {'reason': 'fresh_requested'}
    for path in sorted(output.glob('*.json'), reverse=True):
        try:
            previous = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(previous, dict) or previous.get('exitCode') != 0 or previous.get('commands') != commands:
            continue
        old = previous.get('receiptInputs', {'tree': previous.get('tree')})
        if not isinstance(old, dict):
            continue
        changed = [name for name, value in inputs.items() if name in old and old[name] != value]
        return {'reason': 'inputs_changed' if changed else 'no_verified_receipt',
                'comparedResult': str(path), 'changed': changed,
                'unrecorded': sorted(set(inputs) - set(old))}
    return {'reason': 'no_matching_successful_run'}


def run(root, profile='auto', staged=False, explain=False, fresh=False, scopes=None, timeout=None):
    root = Path(root).resolve()
    files = collect(root, staged)
    config = json.loads(files[CONFIG][1])
    if config.get('version') not in (1, 2):
        raise ValueError('Unsupported testing configuration version')
    files, origins, policy = resolve_validation_inputs(root, config, files)
    checkout_paths = changed_paths(root, staged)
    paths = selection_scope(checkout_paths, scopes, staged, profile)
    validation_paths = sorted(set(paths) | set(origins))
    profiles, reasons = select_profiles(config, validation_paths, profile)
    profiles = validation_profiles(policy, validation_paths, profiles, reasons)
    exact_tests = selected_test_paths(config, validation_paths, profiles)
    commands = validation_commands(policy, profiles) + commands_for(config, profiles, files, exact_tests)
    timeout = config.get('timeoutSeconds', 900) if timeout is None else timeout
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0 or timeout > 86400:
        raise ValueError('timeout must be positive and at most 86400 seconds')
    description = {'schemaVersion': 1, 'configVersion': config['version'],
                   'configDigest': digest(files[CONFIG][1]), 'validationScope': validation_paths,
                   'profileVersion': digest(files[CONFIG][1]), 'scope': paths,
                   'mode': 'staged' if staged else 'worktree', 'profiles': profiles,
                   'checkoutScope': checkout_paths, 'selectionScope': scopes or [],
                   'coverage': 'task-feedback' if scopes else 'checkout', 'timeoutSeconds': timeout,
                   'reasons': reasons, 'commands': commands, 'selectedTests': exact_tests, 'tree': tree_key(files),
                   'diffChecks': diff_checks(root, staged)}
    env = base_environment(config)
    manifest = input_manifest(files, origins)
    spec = execution_spec(commands, files, env, timeout, origins)
    description.update(inputManifest=manifest, inputManifestSha256=spec['inputManifestSha256'],
                       executionSpec=spec, externalInputs=list(origins),
                       buildDependencies=[build['id'] for build in policy.get('builds', [])
                                          if 'full' in profiles or set(profiles).intersection(build['profiles'])])
    if explain:
        print(json.dumps(description, indent=2))
        return 0
    if profile == 'auto' and not staged and profiles == ['full']:
        raise ValueError('auto would run the full suite. Inspect --explain, limit task feedback with --scope, '
                         'or select an appropriate focused profile. Use --profile full explicitly for '
                         'release verification or a justified cross-cutting integration check.')
    # Preflight always reruns against the caller's exact Git context (including
    # alternate index). It is separate from the isolated product-test receipt.
    diff_env = dict(os.environ)
    preflight = preflight_spec(description['diffChecks'], diff_env)
    diff_argv = preflight['argv']
    chain = spec['runtime']
    identity = {'tree': description['tree'], 'toolchain': chain,
                'runner': spec['runnerSha256'], 'timeout': timeout, 'schema': 3}
    inputs = {'tree': identity['tree'], 'runner': identity['runner'], 'timeout': timeout,
              'toolchain': digest(canonical(chain)), 'inputManifest': spec['inputManifestSha256'],
              'executionSpec': digest(canonical(spec))}
    key = digest(canonical(dict(identity, executionSpec=spec)))
    output = output_home(root)
    run_id = time.strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex
    log_path, result_path = output / (run_id + '.log'), output / (run_id + '.json')
    receipt_path = output / 'receipts' / (key + '.json')
    with receipt_lock(output / 'locks' / (key + '.lock')):
        receipt = None if fresh else read_receipt(receipt_path, key, commands, spec, manifest)
        if not fresh and not receipt and profiles != ['full']:
            full_commands = validation_commands(policy, ['full']) + commands_for(config, ['full'], files)
            full_spec = execution_spec(full_commands, files, env, timeout, origins)
            full_key = digest(canonical(dict(identity, executionSpec=full_spec)))
            receipt = read_receipt(output / 'receipts' / (full_key + '.json'), full_key, full_commands, full_spec, manifest)
        reuse = {'reason': 'verified_receipt'} if receipt else reuse_diagnostic(output, inputs, commands, fresh)
        code = 0
        observations = []
        failure_kind = None
        with log_path.open('w', encoding='utf-8') as log:
            log.write('Receipt reuse: ' + json.dumps(reuse) + '\n')
            for command in diff_argv:
                log.write(json.dumps(command) + '\n')
                log.flush()
                try:
                    check = subprocess.run(command, cwd=root, env=diff_env, stdout=log, stderr=subprocess.STDOUT, timeout=preflight['timeoutSeconds'])
                    code = code or check.returncode
                except (OSError, subprocess.TimeoutExpired) as exc:
                    log.write(f'Diff safety check execution failed: {exc}\n')
                    code = code or 1
                    failure_kind = 'timeout' if isinstance(exc, subprocess.TimeoutExpired) else 'launch'
                    break
            if code:
                failure_kind = failure_kind or 'diff'
                log.write('Diff safety check failed; tests not run.\n')
                receipt = None
            elif receipt:
                log.write('Reused verified receipt: ' + receipt['result'] + '\n')
            else:
                # Fixtures must not inherit the checkout's Git repository or
                # its staged index. A short external temp tree also preserves
                # Windows path headroom for long evidence filenames.
                temporary_parent = Path(tempfile.gettempdir()).resolve()
                if temporary_parent == root or temporary_parent.is_relative_to(root):
                    raise ValueError('Validation needs a temporary directory outside the checkout')
                with tempfile.TemporaryDirectory(prefix='project-check-', dir=temporary_parent) as temp:
                    snapshot = Path(temp) / 'source'
                    snapshot.mkdir()
                    for name, (mode, data) in files.items():
                        target = snapshot / name
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(data)
                        target.chmod(0o755 if mode == '100755' else 0o644)
                    execution_env = dict(env)
                    for name, value in env.items():
                        if value == '<private>':
                            execution_env[name] = str(Path(temp))
                        elif value.startswith('<private>/'):
                            directory = Path(temp) / name
                            directory.mkdir()
                            execution_env[name] = str(directory)
                    for command_index, command in enumerate(commands):
                        argv = list(spec['argv'][command_index])
                        timing_path = Path(temp) / f'timings-{command_index}.json'
                        argv = [str(timing_path) if arg == f'<private>/timings-{command_index}.json' else arg
                                for arg in argv]
                        log.write(json.dumps(argv) + '\n')
                        log.flush()
                        started = time.monotonic()
                        try:
                            completed = subprocess.run(argv, cwd=snapshot, env=execution_env,
                                                       stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
                            code = completed.returncode
                            if code:
                                failure_kind = 'tests'
                        except (OSError, subprocess.TimeoutExpired) as exc:
                            log.write(f'Check execution failed: {exc}\n')
                            code = 1
                            failure_kind = 'timeout' if isinstance(exc, subprocess.TimeoutExpired) else 'launch'
                        observed = {'command': command, 'seconds': round(time.monotonic() - started, 6), 'exitCode': code}
                        if timing_path.exists():
                            observed['unittest'] = json.loads(timing_path.read_text(encoding='utf-8'))
                        observations.append(observed)
                        if code:
                            break
                    if any(not (snapshot / name).is_file() or (snapshot / name).read_bytes() != data
                           for name, (_, data) in files.items()):
                        log.write('Tests modified source snapshot inputs; receipt refused.\n')
                        code = code or 1
                        failure_kind = failure_kind or 'snapshot_mutation'
        # Concurrent edits must never earn a receipt for the current checkout/index.
        try:
            current_files, current_origins, _ = resolve_validation_inputs(root, config, collect(root, staged))
            preflight_stable = preflight_spec(description['diffChecks'], dict(os.environ)) == preflight
            stable = (input_manifest(current_files, current_origins) == manifest and preflight_stable
                      and execution_spec(commands, current_files, base_environment(config), timeout, current_origins) == spec)
        except (OSError, ValueError, subprocess.SubprocessError):
            # A disappearing executable or source must keep a useful failed
            # result instead of escaping before diagnostics are published.
            stable = preflight_stable = False
        if not stable:
            code = code or 1
            failure_kind = failure_kind or 'inputs_changed'
        result = dict(description, key=key, exitCode=code, stable=stable, log=str(log_path),
                      reused=receipt['result'] if receipt else None, failureKind=failure_kind,
                      timings=observations,
                      receiptInputs=inputs, receiptReuse=reuse,
                      executionSpec=spec, inputManifest=manifest,
                      preflightSpec=preflight, preflightStable=preflight_stable)
        result_path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        if code == 0 and not receipt:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            record = dict(key=key, commands=commands, executionSpec=spec, inputManifest=manifest,
                          exitCode=0, result=str(result_path), log=str(log_path),
                          resultHash=digest(result_path.read_bytes()), logHash=digest(log_path.read_bytes()))
            temporary = receipt_path.with_suffix('.' + run_id + '.tmp')
            temporary.write_text(json.dumps(record), encoding='utf-8')
            temporary.replace(receipt_path)
        print(f"{'PASS' if code == 0 else 'FAIL'} {','.join(profiles)}; {'receipt reused; ' if receipt else ''}result: {result_path}")
        if not stable:
            print('Inputs changed during checks; rerun for the current tree.', file=sys.stderr)
        return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', default='auto', help='auto, release, or a profile in the snapshot configuration')
    parser.add_argument('--staged', action='store_true', help='test exact index blobs in a private snapshot')
    parser.add_argument('--explain', action='store_true', help='show selection and commands without running checks')
    parser.add_argument('--fresh', action='store_true', help='ignore successful receipts')
    parser.add_argument('--scope', action='append', help='changed relative file/directory for task feedback only (repeatable)')
    parser.add_argument('--timeout', type=float, help='per-command seconds; defaults to timeoutSeconds in the configuration')
    args = parser.parse_args(argv)
    try:
        return run(Path(__file__).resolve().parents[1], args.profile, args.staged, args.explain, args.fresh, args.scope, args.timeout)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(f'project checks failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
