"""Install the neutral HTTP package during coordinated cutover.

Never edits Codex trust or grants permissions. Existing running chats are not restarted.
"""
import json
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from urllib.request import Request
from prepare_project_hub_plugin import prepare, SOURCE

ROOT = Path(__file__).resolve().parents[1]

def check_installed(snapshot):
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('installed'), list):
        raise ValueError('Unknown Codex plugin list format; installation stopped')
    for plugin in snapshot['installed']:
        if not isinstance(plugin, dict):
            raise ValueError('Unknown Codex plugin list format; installation stopped')
        if plugin.get('name') == 'project-hub' and plugin.get('marketplaceName') != 'personal':
            raise ValueError('A different marketplace owns project-hub; inspect before installing')


def read_marketplace(marketplace, target):
    """Accept the existing personal scaffold without depending on creator helpers."""
    if not marketplace.is_file():
        raise ValueError('Existing plugin has no personal marketplace entry; inspect before updating')
    entries = json.loads(marketplace.read_text(encoding='utf-8'))
    if not isinstance(entries, dict) or entries.get('name') != 'personal':
        raise ValueError('Expected the personal marketplace')
    plugins = entries.get('plugins')
    if not isinstance(plugins, list):
        raise ValueError('Invalid personal marketplace plugins list')
    names = set()
    selected = None
    for plugin in plugins:
        if not isinstance(plugin, dict) or not isinstance(plugin.get('name'), str) or not plugin['name']:
            raise ValueError('Invalid personal marketplace plugin entry')
        if plugin['name'] in names:
            raise ValueError('Duplicate personal marketplace plugin entry')
        names.add(plugin['name'])
        if plugin['name'] == 'project-hub':
            selected = plugin
    if selected is None:
        raise ValueError('Personal marketplace does not contain this plugin')
    source = selected.get('source')
    # This installer updates only the standard home-relative personal scaffold.
    # Do not guess how another marketplace resolves absolute or traversal paths.
    if not isinstance(source, dict) or source.get('source') != 'local' or source.get('path') != './plugins/project-hub':
        raise ValueError('Expected local project-hub source path ./plugins/project-hub')
    resolved_source = (marketplace.parents[2] / source['path']).resolve()
    if resolved_source != target.resolve():
        raise ValueError('Personal marketplace source does not resolve to the exact update destination')
    return entries['name']


def cache_version(package, previous_version=None):
    manifest_path = package / '.codex-plugin/plugin.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    base = manifest['version'].split('+', 1)[0]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    version = base + '+codex.' + now.strftime('%Y%m%d%H%M%S')
    if version == previous_version:
        version = base + '+codex.' + (now + timedelta(seconds=1)).strftime('%Y%m%d%H%M%S')
    manifest['version'] = version
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    portable_path = package / 'plugin.json'
    if portable_path.is_file():
        portable = json.loads(portable_path.read_text(encoding='utf-8'))
        portable['version'] = version
        portable_path.write_text(json.dumps(portable, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def install(url):
    sys.path.insert(0, str(SOURCE / 'scripts'))
    from hub_http import Client
    client = Client(url)
    health_request = Request(url.rstrip('/') + '/api/v1/health', headers={'Accept': 'application/json'})
    with client.opener.open(health_request, timeout=5) as response:
        raw = response.read(16001)
    if len(raw) > 16000:
        raise ValueError('Hub health response is too large')
    health = json.loads(raw)
    if (not isinstance(health, dict) or health.get('service') != 'project-hub'
            or health.get('multiProject') is not True):
        raise ValueError('Expected a healthy multi-project Project Hub service')
    data_path = health.get('dataHome')
    if not isinstance(data_path, str) or not data_path or '\0' in data_path or not Path(data_path).is_absolute():
        raise ValueError('Hub health must declare an absolute dataHome')
    data_home = Path(data_path).resolve()
    request = Request(url.rstrip('/') + '/api/v1/projects', headers={'Accept': 'application/json'})
    with client.opener.open(request, timeout=5) as response:
        raw = response.read(256001)
    if len(raw) > 256000:
        raise ValueError('Project catalog response is too large')
    catalog = json.loads(raw)
    if not isinstance(catalog, dict) or catalog.get('schemaVersion') != 1 or not isinstance(catalog.get('projects'), list):
        raise ValueError('Expected a version 1 multi-project Hub')
    # The desktop CLI may wait for the remote marketplace request before
    # returning local plugins. Give this read-only inspection enough time on
    # slow/offline connections; it still fails closed on an actual timeout.
    check_installed(json.loads(subprocess.check_output(['codex','plugin','list','--json'], text=True, encoding='utf-8', timeout=90)))
    user = Path.home()
    creator = user / '.codex/skills/.system/plugin-creator/scripts'
    target = user / 'plugins/project-hub'
    marketplace = user / '.agents/plugins/marketplace.json'
    previous_version = None
    if target.exists():
        manifest = json.loads((target / '.codex-plugin/plugin.json').read_text(encoding='utf-8'))
        if not isinstance(manifest, dict) or manifest.get('name') != 'project-hub':
            raise ValueError('Destination belongs to another plugin')
        previous_version = manifest.get('version')
    else:
        scaffold = creator / 'create_basic_plugin.py'
        if not scaffold.is_file():
            raise ValueError('First installation requires the official plugin-creator scaffold helper; unavailable')
        subprocess.run([sys.executable, str(scaffold), 'project-hub', '--with-marketplace'], check=True, timeout=30)
    read_marketplace(marketplace, target)
    from hub_instructions import Instructions
    instructions = Instructions(data_home)
    companion_root = (instructions.location() if instructions.config.exists()
                      else user / '.agents/skills/project-hub-user')
    instructions.initialize(companion_root, package_root=target)
    companion_root = instructions.location()
    backup_home = ROOT.parent / 'project-hub-backups'
    backup_home.mkdir(parents=True, exist_ok=True)
    backup = Path(tempfile.mkdtemp(prefix='plugin-before-update-', dir=backup_home))
    shutil.copytree(target, backup/'project-hub')
    with tempfile.TemporaryDirectory(prefix='project-hub-package-') as directory:
        package = Path(directory)/'project-hub'
        prepare(package, url, runtime_root=target, user_skill_root=companion_root, data_home=data_home)
        cache_version(package, previous_version)
        shutil.copytree(package, target, dirs_exist_ok=True)
    name = read_marketplace(marketplace, target)
    check_installed(json.loads(subprocess.check_output(['codex','plugin','list','--json'], text=True, encoding='utf-8', timeout=90)))
    subprocess.run(['codex', 'plugin', 'add', 'project-hub@' + name, '--json'], check=True, timeout=60)
    return {'plugin': str(target), 'marketplace': str(marketplace), 'backup': str(backup),
            'hookTrust': 'Not modified; verify new-session startup before resuming writes'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    args = parser.parse_args()
    print(json.dumps(install(args.url), ensure_ascii=False))


if __name__ == '__main__':
    main()
