"""A leased, generation-checked read view during the backup writer barrier.

The marker grants no authority by itself. A live OS lease and an exact SQLite
generation are both required. Readers pin a read transaction before borrowing
prepared rows; after the lease ends ordinary freshness/recovery resumes.
"""
from contextlib import contextmanager, closing
import errno
import json
import sqlite3
import uuid


class SessionEnded(Exception):
    pass


class BackupBusy(ValueError):
    pass


def _paths(registry):
    directory = registry.home / 'runtime' / 'backup'
    return directory / 'read-session.json', directory / 'reader.lock'


def current(registry):
    marker, lock = _paths(registry)
    if not marker.is_file() or marker.is_symlink() or lock.is_symlink():
        return None
    from project_portal import Store
    try:
        with Store.lock_probe(lock).locked(timeout=0):
            return None  # A leftover marker never suppresses normal recovery.
    except TimeoutError as error:
        if not isinstance(error.__cause__, OSError) or error.__cause__.errno not in (errno.EACCES, errno.EAGAIN):
            raise
    try:
        value = json.loads(marker.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return None
    if (not isinstance(value, dict) or value.get('dataHome') != str(registry.home.resolve())
            or value.get('version') != 1 or not isinstance(value.get('views'), dict)
            or type(value.get('generation')) is not int):
        return None
    return value


@contextmanager
def connection(registry, session):
    """Pin the generation before reading authorization, history or view rows."""
    with closing(sqlite3.connect(registry.database.resolve().as_uri() + '?mode=ro', uri=True, timeout=.2)) as db:
        db.row_factory = sqlite3.Row
        db.execute('BEGIN')
        row = db.execute('SELECT generation FROM read_model_generation WHERE singleton=1').fetchone()
        if row is None or row[0] != session['generation']:
            raise SessionEnded()
        yield db


def active(registry):
    session = current(registry)
    if session is not None:
        try:
            with connection(registry, session):
                return session
        except SessionEnded:
            pass
    return None


@contextmanager
def publish(registry, views, generation):
    """Called only after project locks and both SQLite writer reservations."""
    from project_portal import Store, atomic_write
    marker, lock = _paths(registry)
    with Store.lock_probe(lock).locked():
        with registry.connect() as db:
            if generation != db.execute('SELECT generation FROM read_model_generation WHERE singleton=1').fetchone()[0]:
                raise SessionEnded('The prepared snapshot generation changed')
        value = dict(version=1, id=uuid.uuid4().hex, dataHome=str(registry.home.resolve()),
                     generation=generation, views=views, writesPaused=True)
        atomic_write(marker, json.dumps(value))
        try:
            yield value
        finally:
            marker.unlink(missing_ok=True)
