"""Prepare an exclusively leased old data home before accepting requests.

Every original byte is copied and verified before using the existing atomic
schema upgrade. Recovery reuses that original backup rather than backing up a
partially upgraded home as if it were the original.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import uuid

from hub_lifecycle import atomic_json
from project_workspaces import no_reparse


def _database(path, meta):
    if not path.exists():
        return None, False
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as db:
        row = db.execute('SELECT version FROM ' + meta).fetchone()
        pending = (meta == 'registry_meta' and db.execute("SELECT 1 FROM sqlite_master WHERE name='registry_upgrade'").fetchone()
                   and db.execute("SELECT 1 FROM registry_upgrade WHERE state='pending'").fetchone())
    if not row or row[0] not in (1, 2):
        raise ValueError('Unsupported storage schema; original data was not modified')
    return row[0], bool(pending)


def _files(home):
    result = {}
    no_reparse(home)
    for path in sorted(home.rglob('*')):
        no_reparse(path)
        if path.is_file():
            # Hash streams; source snapshots and uploaded files need not fit RAM.
            with path.open('rb') as stream:
                result[path.relative_to(home).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    return result


def _verify_backup(home, files):
    if _files(home) != files:
        raise ValueError('Original storage backup verification failed; no migration can proceed')
    for name in files:
        if name.endswith(('.sqlite3', '.sqlite', '.db')):
            path = home / name
            with path.open('rb') as stream:
                if stream.read(16) != b'SQLite format 3\x00':
                    continue  # Uploaded files may use a database-like suffix.
            # Ordinary SQLite must include the copied WAL. Verify a scratch
            # copy so its SHM bookkeeping cannot alter the immutable original.
            with tempfile.TemporaryDirectory(prefix='hub-backup-integrity-') as temporary:
                target = Path(temporary) / path.name
                shutil.copy2(path, target)
                for suffix in ('-wal', '-shm'):
                    sidecar = path.with_name(path.name + suffix)
                    if sidecar.is_file():
                        shutil.copy2(sidecar, target.with_name(target.name + suffix))
                with closing(sqlite3.connect(target.as_uri() + '?mode=ro', uri=True)) as db:
                    if db.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                        raise ValueError('Storage backup database failed integrity verification')


def prepare(home):
    """Caller must hold home_lease(home); no serving process may be active."""
    home = Path(home).resolve()
    version, pending = _database(home / 'registry.sqlite3', 'registry_meta')
    coordination, _ = _database(home / 'coordination/coordination.sqlite3', 'meta')
    if version is None:
        return dict(changed=False, schemaVersion=2)
    no_reparse(home)
    parent = home.parent / (home.name + '-schema-backups')
    no_reparse(parent)
    receipt_path = parent / 'preparation.json'
    receipt = json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else None
    if version == 2 and coordination in (None, 2) and not pending and (receipt is None or receipt.get('state') == 'complete'):
        return dict(changed=False, schemaVersion=2)
    if receipt is not None:
        if receipt.get('home') != str(home) or receipt.get('version') != 1 or receipt.get('state') not in ('pending', 'complete'):
            raise ValueError('Storage preparation record requires manual recovery')
        backup = Path(receipt['backup']).resolve()
        if backup.parent != parent.resolve() or backup.name in ('', '.', '..'):
            raise ValueError('Storage preparation backup must remain inside its owned directory')
        _verify_backup(backup, receipt['files'])
    else:
        if pending:
            raise ValueError('An incomplete earlier upgrade has no original backup receipt; recover its inactive copy before starting')
        original = _files(home)
        backup = parent / uuid.uuid4().hex
        parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(home, backup, symlinks=False)
        _verify_backup(backup, original)
        if _files(home) != original:
            raise ValueError('Storage changed during backup; stop every writer before retrying startup')
        receipt = dict(version=1, home=str(home), backup=str(backup), state='pending',
                       files=original, createdAt=time.time(), fromSchema=version)
        atomic_json(receipt_path, receipt)
    from project_registry import ProjectRegistry
    registry = ProjectRegistry(home, standalone=True)
    try:
        registry.upgrade(confirmed=True)
        registry.require_ready()
        # The schema upgrade gives imported projects Hub ownership while
        # preserving their source IDs, availability and history exactly.
        with registry.connect() as db:
            db.execute("UPDATE spaces SET ownership='hub' WHERE ownership='codex'")
    finally:
        registry.close_connection_pool()
    if _database(home / 'registry.sqlite3', 'registry_meta') != (2, False) or _database(home / 'coordination/coordination.sqlite3', 'meta')[0] not in (None, 2):
        raise ValueError('Storage preparation is incomplete; serving remains disabled')
    receipt.update(state='complete', completedAt=time.time())
    atomic_json(receipt_path, receipt)
    return dict(changed=True, schemaVersion=2, backup=str(backup), receipt=str(receipt_path))
