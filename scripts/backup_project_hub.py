"""Versioned local migration backup. No credentials or Codex transcripts are copied."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone

from project_portal import Store


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(destination):
    destination = Path(destination).resolve()
    if (destination / 'INCOMPLETE').exists():
        raise ValueError('Incomplete backup')
    manifest = json.loads((destination / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['schemaVersion'] != 1:
        raise ValueError('Unsupported backup schema')
    for relative, expected in manifest['files'].items():
        path = (destination / relative).resolve()
        if not path.is_relative_to(destination) or digest(path) != expected:
            raise ValueError('Backup checksum mismatch: ' + relative)
    with closing(sqlite3.connect((destination / 'coordination.sqlite3').as_uri() + '?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed')
    return dict(files=len(manifest['files']), tasks=manifest['tasks'], revision=manifest['journalRevision'])


def backup(root, database, destination):
    root, database, destination = map(lambda p: Path(p).resolve(), (root, database, destination))
    if destination.exists():
        raise ValueError('Backup destination must be new; never overwrite a snapshot')
    if destination.is_relative_to(root):
        raise ValueError('Backups must be outside the source repository')
    destination.mkdir(parents=True)
    store = Store(root)
    try:
        # Journal lock prevents file replacement during copying. SQLite backup includes WAL.
        # Cross-store atomicity still requires pausing all writers at final cutover.
        with store.locked():
            seed, events = store._load()
            shutil.copytree(store.data, destination / 'project-data', ignore=shutil.ignore_patterns('__pycache__'))
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as source:
                with closing(sqlite3.connect(destination / 'coordination.sqlite3')) as target:
                    source.backup(target)
            tasks = store.project(seed, events)
        commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
        manifest = dict(schemaVersion=1, createdAt=datetime.now(timezone.utc).isoformat(),
                        sourceRoot=str(root), sourceDatabase=str(database), sourceCommit=commit,
                        journalRevision=len(events), tasks=[t['id'] for t in tasks],
                        consistency='Each store consistent; pause all writers for final cross-store cutover',
                        files={p.relative_to(destination).as_posix(): digest(p)
                               for p in destination.rglob('*') if p.is_file()})
        (destination / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return verify(destination)
    except Exception:
        # Retain failed snapshots for diagnosis but never label them complete.
        (destination / 'INCOMPLETE').write_text('Backup did not complete', encoding='utf-8')
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path)
    parser.add_argument('--database', type=Path)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    if not args.verify and (not args.root or not args.database):
        parser.error('--root and --database are required for backup')
    print(json.dumps(verify(args.destination) if args.verify else backup(args.root, args.database, args.destination)))
