"""Explicit, repeatable upgrades of inactive Hub data homes.

Each SQLite upgrade is atomic. A partially upgraded copy remains readable by
the dual-version runtime and can be retried before activation. Opening an old
home never invokes these upgrades implicitly.
"""
from contextlib import closing
from pathlib import Path
import sqlite3


SPACES_V2 = '''CREATE TABLE {table}(
    id TEXT PRIMARY KEY, codex_id TEXT UNIQUE, name TEXT NOT NULL,
    roots TEXT NOT NULL, present INTEGER NOT NULL, updated REAL NOT NULL,
    revision INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0, ownership TEXT NOT NULL DEFAULT 'codex')'''


def extensions(connection):
    for statement in (
        '''CREATE TABLE IF NOT EXISTS project_requests(
            id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS registry_upgrade(
            id INTEGER PRIMARY KEY CHECK(id=1), state TEXT NOT NULL)''',
        '''CREATE TABLE IF NOT EXISTS client_bindings(
            id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES spaces(id),
            client TEXT NOT NULL, external_id TEXT NOT NULL, metadata TEXT NOT NULL,
            updated REAL NOT NULL, UNIQUE(client,external_id))''',
        '''CREATE TABLE IF NOT EXISTS project_workspaces(
            id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES spaces(id),
            kind TEXT NOT NULL, descriptor TEXT NOT NULL, enabled INTEGER NOT NULL,
            revision INTEGER NOT NULL, updated REAL NOT NULL)''',
    ):
        connection.execute(statement)


def initialize_registry(connection, standalone=False):
    exists = connection.execute("SELECT 1 FROM sqlite_master WHERE name='registry_meta' AND type='table'").fetchone()
    if exists:
        rows = connection.execute('SELECT version FROM registry_meta').fetchall()
        if len(rows) != 1 or rows[0][0] not in (1, 2):
            raise ValueError('Unsupported project registry version; not modified')
        return rows[0][0]
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('BEGIN IMMEDIATE')
    try:
        version = 2 if standalone else 1
        connection.execute('CREATE TABLE registry_meta(version INTEGER NOT NULL)')
        connection.execute('INSERT INTO registry_meta VALUES(?)', (version,))
        if version == 2:
            connection.execute(SPACES_V2.format(table='spaces'))
            extensions(connection)
        else:
            connection.execute('''CREATE TABLE spaces(
                id TEXT PRIMARY KEY, codex_id TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                roots TEXT NOT NULL, present INTEGER NOT NULL, updated REAL NOT NULL)''')
        connection.commit()
        return version
    except BaseException:
        connection.rollback()
        raise


def upgrade_registry(connection):
    """Keep IDs and all dependent tables; change the project row in one commit."""
    version = connection.execute('SELECT version FROM registry_meta').fetchone()[0]
    if version == 2:
        return
    if version != 1:
        raise ValueError('Unsupported project registry version; not modified')
    connection.execute('PRAGMA foreign_keys=OFF')
    connection.execute('BEGIN IMMEDIATE')
    try:
        connection.execute(SPACES_V2.format(table='spaces_v2'))
        connection.execute('''INSERT INTO spaces_v2(id,codex_id,name,roots,present,updated)
                              SELECT id,codex_id,name,roots,present,updated FROM spaces''')
        extras = [row[0] for row in connection.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name='spaces' AND type IN ('index','trigger') AND sql IS NOT NULL")]
        connection.execute('DROP TABLE spaces')
        connection.execute('ALTER TABLE spaces_v2 RENAME TO spaces')
        for sql in extras:
            connection.execute(sql)
        extensions(connection)
        if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
            raise ValueError('Registry foreign keys failed validation; upgrade rolled back')
        connection.execute('UPDATE registry_meta SET version=2')
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.execute('PRAGMA foreign_keys=ON')


def upgrade_coordination(path):
    """Allow projects and actors without local code; preserve every child FK."""
    path = Path(path)
    if not path.exists():
        return
    with closing(sqlite3.connect(path, timeout=5, isolation_level=None)) as c:
        rows = c.execute('SELECT version FROM meta').fetchall()
        if len(rows) != 1 or rows[0][0] not in (1, 2):
            raise ValueError('Unsupported coordination version; not modified')
        if rows[0][0] == 2:
            return
        c.execute('PRAGMA foreign_keys=OFF')
        c.execute('BEGIN IMMEDIATE')
        try:
            extras = [row[0] for row in c.execute("SELECT sql FROM sqlite_master WHERE tbl_name IN ('projects','sessions') AND type IN ('index','trigger') AND sql IS NOT NULL")]
            c.execute('CREATE TABLE projects_v2(id TEXT PRIMARY KEY, root TEXT UNIQUE, git_common TEXT)')
            c.execute('''CREATE TABLE sessions_v2(
                id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id), workspace TEXT,
                state TEXT NOT NULL, seen REAL NOT NULL, turn TEXT, checkpoint TEXT NOT NULL DEFAULT '',
                task TEXT, last_cursor INTEGER NOT NULL DEFAULT 0)''')
            expected = {'id','project','workspace','state','seen','turn','checkpoint','task','last_cursor'}
            if {row[1] for row in c.execute('PRAGMA table_info(sessions)')} != expected:
                raise ValueError('Unknown session columns; upgrade rolled back')
            c.execute('INSERT INTO projects_v2(id,root,git_common) SELECT id,root,git_common FROM projects')
            c.execute('''INSERT INTO sessions_v2(id,project,workspace,state,seen,turn,checkpoint,task,last_cursor)
                          SELECT id,project,workspace,state,seen,turn,checkpoint,task,last_cursor FROM sessions''')
            # Do not rename the old tables: SQLite would rewrite child FKs to
            # the obsolete names. Rebuild and rename replacements instead.
            c.execute('DROP TABLE sessions')
            c.execute('DROP TABLE projects')
            c.execute('ALTER TABLE projects_v2 RENAME TO projects')
            c.execute('ALTER TABLE sessions_v2 RENAME TO sessions')
            for sql in extras:
                c.execute(sql)
            if c.execute('PRAGMA foreign_key_check').fetchone() is not None:
                raise ValueError('Coordination foreign keys failed validation; upgrade rolled back')
            c.execute('UPDATE meta SET version=2')
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.execute('PRAGMA foreign_keys=ON')
