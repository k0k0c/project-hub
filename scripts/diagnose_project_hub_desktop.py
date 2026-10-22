"""Compare a desktop task's plugin references with the installed personal package.

Read-only diagnostic: inspects only supplied developer-context lines relevant to
the plugin, never assistant reasoning or user messages. No models or trust changes.
"""
import argparse
import json
from pathlib import Path
import re
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--thread', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    home = Path.home() / '.codex'
    manifest = json.loads((Path.home() / 'plugins/project-hub/.codex-plugin/plugin.json').read_text(encoding='utf-8'))
    connection = sqlite3.connect((home / 'state_5.sqlite').as_uri() + '?mode=ro', uri=True)
    try:
        row = connection.execute('SELECT rollout_path FROM threads WHERE id=?', (args.thread,)).fetchone()
    finally:
        connection.close()
    if row is None:
        raise ValueError('Requested thread not found')
    references, startup = set(), False
    with Path(row[0]).open(encoding='utf-8') as source:
        for line in source:
            item = json.loads(line)
            payload = item.get('payload', {})
            if item.get('type') != 'response_item' or payload.get('type') != 'message' or payload.get('role') != 'developer':
                continue
            for block in payload.get('content', []):
                text = block.get('text', '')
                references.update(re.findall(r'project-hub/([^/\s]+)/skills/project-hub/SKILL\.md', text))
                startup |= 'Project Hub is connected.' in text or 'Project Hub startup context is available.' in text
    versions = sorted(references)
    result = dict(thread=args.thread, installedVersion=manifest['version'], developerContextVersions=versions,
                  startupContextPresent=startup,
                  referencedCacheExists={version: (home / 'plugins/cache/personal/project-hub' / version / 'skills/project-hub/SKILL.md').is_file() for version in versions},
                  mismatch=any(version != manifest['version'] for version in versions),
                  note='Historical developer-context references; repeat with a fresh task after desktop refresh to verify recovery.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
