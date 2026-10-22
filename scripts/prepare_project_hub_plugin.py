"""Prepare the neutral HTTP-only package without changing the installed plugin."""
import argparse
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tools/project-portal/plugins/project-hub'


def prepare(destination, url, python=sys.executable, runtime_root=None, user_skill_root=None, data_home=None):
    # Use the same transport validation as the client before creating files.
    sys.path.insert(0, str(SOURCE / 'scripts'))
    from hub_http import Client
    Client(url)
    destination = Path(destination).resolve()
    runtime_root = Path(runtime_root).resolve() if runtime_root else destination
    if destination.name != 'project-hub':
        raise ValueError('Package directory must be named project-hub')
    if destination.exists():
        raise ValueError('Use a new destination; existing packages are not overwritten')
    if not Path(python).is_absolute():
        raise ValueError('Use an absolute Python executable path')
    shutil.copytree(SOURCE, destination, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    manifest_path = destination / '.codex-plugin/plugin.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    manifest['name'] = 'project-hub'
    manifest['version'] = '0.2.0'
    manifest['interface']['displayName'] = 'Project Hub for Codex'
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    # Both MCP and hooks start this entry point and read the same package config.
    connection = {'url': url.rstrip('/')}
    if user_skill_root is not None:
        connection['userSkillRoot'] = str(Path(user_skill_root).absolute())
        if data_home is not None:
            connection['instructionsDataHome'] = str(Path(data_home).absolute())
        skill = destination / 'skills/project-hub/SKILL.md'
        with skill.open('a', encoding='utf-8') as output:
            output.write('\n## Local user preferences\n\n'
                         'When applying Project Hub, also apply the native `project-hub-user` skill at '
                         + str(Path(user_skill_root).absolute() / 'SKILL.md') + '. Preserve its user text. '
                         'Native MCP connections still follow the verified local instruction manifest, '
                         'startup/compaction reads and changed-bundle refresh; this legacy companion does not replace them. '
                         'If absent, continue with the current verified workflow and report the missing local skill.\n')
    (destination / 'connection.json').write_text(json.dumps(connection) + '\n', encoding='utf-8')
    portable_path = destination / 'plugin.json'
    portable = json.loads(portable_path.read_text(encoding='utf-8'))
    portable['version'] = manifest['version']
    portable['extensions']['com.openai']['interface']['displayName'] = manifest['interface']['displayName']
    portable_path.write_text(json.dumps(portable, indent=2) + '\n', encoding='utf-8')
    mcp = {'mcpServers': {'project_hub': {'command': str(python),
            'args': [str(runtime_root / 'scripts/client_entry.py'), 'mcp'], 'startup_timeout_sec': 10}}}
    (destination / '.mcp.json').write_text(json.dumps(mcp, indent=2) + '\n', encoding='utf-8')
    (destination / 'mcp.json').write_text(json.dumps(dict(
        {'$schema': 'https://agent-plugins.org/schemas/1.0.0/mcp.schema.json'}, **mcp), indent=2) + '\n', encoding='utf-8')
    hooks_path = destination / 'hooks/hooks.json'
    hooks = json.loads(hooks_path.read_text(encoding='utf-8'))
    # Codex uses PowerShell on Windows: a quoted executable requires '&'.
    command_args = (' -c "import os,runpy,sys;'
               "p=os.path.join(os.environ['PLUGIN_ROOT'],'scripts');sys.path.insert(0,p);"
               "runpy.run_path(os.path.join(p,'client_entry.py'),run_name='__main__')\" hook")
    for groups in hooks['hooks'].values():
        for group in groups:
            for hook in group['hooks']:
                hook['command'] = '"' + str(python) + '"' + command_args
                hook['commandWindows'] = "& '" + str(python).replace("'", "''") + "'" + command_args
    hooks_path.write_text(json.dumps(hooks, indent=2) + '\n', encoding='utf-8')
    return {'package': str(destination), 'url': url.rstrip('/'), 'installed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--url', required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.destination, args.url)))


if __name__ == '__main__':
    main()
