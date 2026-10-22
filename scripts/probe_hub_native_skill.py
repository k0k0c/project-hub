"""Verify native local-skill discovery on temporary files, without model generation."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from codex_adapter import CodexAdapter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools/project-portal/plugins/project-hub/scripts'))
from hub_instructions import Instructions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='hub-native-skill-') as temporary:
        base = Path(temporary)
        repository = base / 'repository'
        repository.mkdir()
        subprocess.run(['git', 'init', '-q', str(repository)], check=True, capture_output=True)
        location = repository / '.agents/skills/project-hub-user'
        initial = Instructions(base / 'private-data').initialize(location)
        adapter = CodexAdapter()
        try:
            handshake = adapter.probe()
            if not handshake['available']:
                raise RuntimeError(handshake.get('reason', 'Native handshake unavailable'))
            response = adapter.skills([str(repository)])
            found = []
            def visit(value):
                if isinstance(value, dict):
                    if value.get('name') == 'project-hub-user':
                        found.append(value)
                    for item in value.values():
                        visit(item)
                elif isinstance(value, list):
                    for item in value:
                        visit(item)
            visit(response)
            matches = [item for item in found if Path(item.get('path', '')).resolve() == (location / 'SKILL.md').resolve()]
            result = dict(verified=bool(matches), codexVersion=handshake['version'],
                skill='project-hub-user', scope='REPO', discoveredCount=len(matches),
                instructionDigest=hashlib.sha256((location / 'SKILL.md').read_bytes()).hexdigest(),
                modelCalls=0, newChats=0, temporaryFiles=True,
                note='Native discovery verifies format/path, not implicit skill selection or an existing chat reload. USER scope is documented; this disposable PoC uses REPO discovery.')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(result, ensure_ascii=False))
            if not result['verified']:
                raise SystemExit(1)
        finally:
            adapter.close()


if __name__ == '__main__':
    main()
