"""Shared MCP, hook and check entry point for the prepared HTTP-only package."""
import json
import os
from pathlib import Path
import sys
sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'


def main():
    is_notice = sys.argv[1:] == ['notice-hook']
    is_hook = sys.argv[1:] == ['hook'] or is_notice
    if is_hook:
        try:
            raw = json.load(sys.stdin)
            if not isinstance(raw, dict):
                raise ValueError('Expected hook object')
        except (OSError, ValueError):
            print('{}')
            return
        # Only explicit edits with supplied identity are candidates for observation.
        # Missing metadata and opaque/read-only tools do not need transport.
        if (raw.get('hook_event_name') in ('PreToolUse', 'PostToolUse')
                and (raw.get('tool_name') not in ('apply_patch', 'Edit', 'Write')
                     or not raw.get('session_id') or not raw.get('cwd'))):
            print('{}')
            return
    scripts = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts))
    if sys.argv[1:2] == ['git-batch']:
        from hub_git_batch import main as run_batch
        raise SystemExit(run_batch(sys.argv[2:]))
    from hub_http import Client
    try:
        config = json.loads((scripts.parent / 'connection.json').read_text(encoding='utf-8'))
        if not isinstance(config, dict):
            raise ValueError('Expected a connection object')
        url = os.environ.get('PROJECT_HUB_URL', config['url'])
        Client(url)  # Fail before entering a legacy CLI path, even with an empty override.
    except (OSError, ValueError, KeyError) as error:
        if is_hook:
            print('{}')
            return
        raise SystemExit('Project Hub connection configuration is invalid') from error
    if is_hook:
        try:
            if is_notice:
                from hub_watch import run as watch
                config['url']=url
                watch(raw,config,lambda value: print(json.dumps(value),flush=True))
                return
            print(json.dumps(Client(url, timeout=1.5).hook(raw)))
        except Exception:
            # Optional observations cannot fail a Codex hook or demand approval.
            print('{}')
        return
    os.environ['PROJECT_HUB_URL'] = url
    if sys.argv[1:2] == ['mcp'] and config.get('instructionsDataHome') and config.get('userSkillRoot'):
        try:
            from hub_instructions import Instructions
            Instructions(config['instructionsDataHome']).initialize(config['userSkillRoot'])
        except (OSError, ValueError):
            # Optional local preferences never prevent the MCP connection.
            print('Project Hub local user skill requires repair; MCP remains available.', file=sys.stderr)
    if sys.argv[1:2] == ['check']:
        from hub_check import main as run_check
        raise SystemExit(run_check(sys.argv[2:], default_url=url))
    from hub_plugin import main as run
    run()


if __name__ == '__main__':
    try:
        main()
    except Exception:
        if sys.argv[1:] not in (['hook'],['notice-hook']):
            raise
        print('{}')
