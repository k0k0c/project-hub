"""Repository-local bridge; the independent runner has no Hub dependency."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')

try:
    from check_paths import output_home
except ModuleNotFoundError:  # imported from the repository test harness
    from scripts.check_paths import output_home

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'scripts/project_hub_check.py'
WRAPPER = ROOT / 'tools/project-portal/plugins/project-hub/scripts/hub_check.py'


def execute_core(arguments):
    result = subprocess.run([sys.executable, str(RUNNER), *arguments], cwd=ROOT,
                            capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(result.stdout, end='')
    print(result.stderr, end='', file=sys.stderr)
    # The runner owns unique log names; publish its actual output, not just a path.
    for line in result.stdout.splitlines():
        if '; result: ' not in line:
            continue
        path = Path(line.rsplit('; result: ', 1)[1]).resolve()
        output = output_home(ROOT)
        if not path.is_relative_to(output):
            continue
        try:
            record = json.loads(path.read_text(encoding='utf-8'))
            log = Path(record['log']).resolve()
            if log.is_relative_to(output):
                print(log.read_text(encoding='utf-8', errors='replace'), end='')
        except (OSError, ValueError, KeyError):
            print('Check log could not be included; inspect the runner result.', file=sys.stderr)
    return result.returncode


def main(arguments=None):
    arguments = list(sys.argv[1:] if arguments is None else arguments)
    if '--execute-core' in arguments:
        arguments.remove('--execute-core')
        return execute_core(arguments)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--title', default=os.environ.get('PROJECT_HUB_CHECK_TITLE'))
    options, arguments = parser.parse_known_args(arguments)
    if '--explain' in arguments:
        return subprocess.call([sys.executable, str(RUNNER), *arguments], cwd=ROOT)
    context = {key: os.environ.get('PROJECT_HUB_CHECK_' + key.upper()) for key in ('task', 'project', 'stage', 'url')}
    if not all(context[key] for key in ('task', 'project', 'url')):
        print('Checks run locally: Hub task/project/url context missing; publication is not registered.', file=sys.stderr)
        return execute_core(arguments)
    explanation = subprocess.run([sys.executable, str(RUNNER), *arguments, '--explain'],
                                 cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
    if explanation.returncode:
        print(explanation.stderr, end='', file=sys.stderr)
        return explanation.returncode
    description = json.loads(explanation.stdout)
    head = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    dirty = subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'])
    command = [sys.executable, str(WRAPPER), 'exec', '--url', context['url'],
               '--project', context['project'], '--task', context['task'], '--cwd', str(ROOT),
               '--title', options.title or ('Pre-commit validation' if '--staged' in arguments else 'Project validation'),
               '--profile', '+'.join(description['profiles']),
               '--profile-version', description['profileVersion'],
               '--revision', json.dumps(dict(head=head.stdout.strip() if head.returncode == 0 else None,
                                             dirty=bool(dirty), fingerprint=description['tree']))]
    if context['stage']:
        command += ['--stage', context['stage']]
    for path in description.get('scope', [])[:100]:
        command += ['--scope', path]
    command += ['--', sys.executable, str(Path(__file__).resolve()), '--execute-core', *arguments]
    return subprocess.call(command, cwd=ROOT)


if __name__ == '__main__':
    raise SystemExit(main())
