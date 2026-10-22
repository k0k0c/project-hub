"""Source checkout entry point using the same launcher as the installed Hub."""
import argparse
import hashlib
from pathlib import Path
import sys

from hub_launcher import APPLICATION_HOME, default_base, main as launch


def default_config(mode):
    base = default_base()
    if mode == 'work':
        return base / 'installation.json'
    key = hashlib.sha256(str(APPLICATION_HOME.resolve()).casefold().encode()).hexdigest()[:16]
    return base / 'development' / 'sources' / key / 'installation.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='Override the selected mode configuration with an absolute external path')
    parser.add_argument('--data-home', type=Path, help='Initial external data home or an existing preserved Hub home')
    parser.add_argument('--port', type=int, default=8769)
    parser.add_argument('--language', choices=('ru','en'), default='ru')
    parser.add_argument('--no-browser', action='store_true')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--mode', choices=('work', 'development'), default='work',
                      help='Work shares installed settings; development uses an isolated source profile')
    mode.add_argument('--development', dest='mode', action='store_const', const='development',
                      help='Alias for --mode development')
    parser.add_argument('--switch', action='store_true')
    parser.add_argument('--stop', action='store_true')
    args = parser.parse_args(argv)
    if args.mode == 'development' and args.switch:
        parser.error('--switch is only available in work mode')
    config = args.config or default_config(args.mode)
    command = ['--config', str(config), '--source', '--mode', args.mode]
    if args.stop:
        return launch([*command, '--stop'])
    command += ['--configure', '--open', '--port', str(args.port), '--language', args.language]
    if args.data_home is not None:
        command += ['--data-home', str(args.data_home)]
    for flag in ('no_browser','switch'):
        if getattr(args, flag):
            command.append('--' + flag.replace('_','-'))
    return launch(command)


if __name__ == '__main__':
    sys.exit(main())
