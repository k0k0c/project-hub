"""Atomic storage-upgrade contracts using disposable external homes."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hub_storage_schema import upgrade_coordination, upgrade_registry
from project_registry import ProjectRegistry


class EmptyCatalog:
    def read(self):
        return {'available': True, 'projects': [], 'assignments': {}, 'source': 'fixture'}

    def assigned_project(self, session):
        return None


def registry_v1(path, *, child=False, broken=False):
    with closing(sqlite3.connect(path)) as db:
        db.executescript('''
            PRAGMA foreign_keys=OFF;
            CREATE TABLE registry_meta(version INTEGER NOT NULL);
            INSERT INTO registry_meta VALUES(1);
            CREATE TABLE spaces(id TEXT PRIMARY KEY, codex_id TEXT UNIQUE NOT NULL,
                                name TEXT NOT NULL, roots TEXT NOT NULL,
                                present INTEGER NOT NULL, updated REAL NOT NULL);
            INSERT INTO spaces VALUES('p1','codex-p1','Fixture','[]',1,1.0);
        ''')
        if child:
            db.executescript('''
                CREATE TABLE space_notes(id TEXT PRIMARY KEY, space TEXT NOT NULL REFERENCES spaces(id), body TEXT);
                INSERT INTO space_notes VALUES('n1','p1','kept');
                CREATE TABLE space_audit(id INTEGER PRIMARY KEY, space TEXT);
                CREATE INDEX spaces_name_idx ON spaces(name);
                CREATE TRIGGER spaces_audit AFTER UPDATE OF name ON spaces
                BEGIN INSERT INTO space_audit(space) VALUES(NEW.id); END;
            ''')
        if broken:
            db.execute("INSERT INTO space_notes VALUES('bad','missing','broken')")
        db.commit()


def coordination_v1(path, *, child=False, extra_session=False, broken=False):
    with closing(sqlite3.connect(path)) as db:
        db.executescript('''
            PRAGMA foreign_keys=OFF;
            CREATE TABLE meta(version INTEGER NOT NULL);
            INSERT INTO meta VALUES(1);
            CREATE TABLE projects(id TEXT PRIMARY KEY, root TEXT UNIQUE, git_common TEXT);
            CREATE TABLE sessions(id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id),
                workspace TEXT, state TEXT NOT NULL, seen REAL NOT NULL, turn TEXT,
                checkpoint TEXT NOT NULL DEFAULT '', task TEXT, last_cursor INTEGER NOT NULL DEFAULT 0);
            INSERT INTO projects VALUES('p1','/fixture','/fixture/.git');
            INSERT INTO sessions(id,project,workspace,state,seen,turn,checkpoint,task,last_cursor)
                VALUES('s1','p1','/fixture','idle',1.0,NULL,'',NULL,0);
        ''')
        if extra_session:
            db.execute('ALTER TABLE sessions ADD COLUMN unknown_column TEXT')
        if child:
            db.executescript('''
                CREATE TABLE work(id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id),
                    session TEXT NOT NULL REFERENCES sessions(id), task TEXT NOT NULL, title TEXT NOT NULL,
                    status TEXT NOT NULL, revision INTEGER NOT NULL, created REAL NOT NULL,
                    updated REAL NOT NULL, result TEXT NOT NULL DEFAULT '', checkpoint TEXT NOT NULL DEFAULT '',
                    evidence TEXT NOT NULL DEFAULT '[]');
                CREATE TABLE claims(work TEXT NOT NULL REFERENCES work(id), name TEXT NOT NULL,
                                    mode TEXT NOT NULL, PRIMARY KEY(work,name));
                INSERT INTO work VALUES('w1','p1','s1','task','Work','active',1,1,1,'','','[]');
                INSERT INTO claims VALUES('w1','file','exclusive');
                CREATE INDEX sessions_state_idx ON sessions(state);
                CREATE TABLE session_audit(id INTEGER PRIMARY KEY, session TEXT);
                CREATE TRIGGER sessions_audit AFTER UPDATE OF state ON sessions
                BEGIN INSERT INTO session_audit(session) VALUES(NEW.id); END;
            ''')
        if broken:
            db.execute("INSERT INTO work VALUES('bad','missing','s1','task','Bad','active',1,1,1,'','','[]')")
        db.commit()


class StorageUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / 'external-hub-data'
        self.home.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_registry_upgrade_preserves_child_foreign_keys_indexes_and_triggers(self):
        database = self.home / 'registry.sqlite3'
        registry_v1(database, child=True)
        with closing(sqlite3.connect(database)) as db:
            upgrade_registry(db)
            self.assertEqual(db.execute('SELECT version FROM registry_meta').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT id FROM spaces').fetchone()[0], 'p1')
            self.assertEqual(db.execute('SELECT space,body FROM space_notes').fetchone(), ('p1', 'kept'))
            self.assertEqual(db.execute('PRAGMA foreign_key_list(space_notes)').fetchone()[2], 'spaces')
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type IN ('index','trigger')")}
            self.assertIn('spaces_name_idx', names)
            self.assertIn('spaces_audit', names)
            self.assertFalse(any('_v2' in name for name in names))

    def test_coordination_upgrade_preserves_work_claims_and_child_objects(self):
        database = self.home / 'coordination.sqlite3'
        coordination_v1(database, child=True)
        with closing(sqlite3.connect(database)) as db:
            upgrade_coordination(database)
        with closing(sqlite3.connect(database)) as db:
            self.assertEqual(db.execute('SELECT version FROM meta').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT id,project FROM sessions').fetchone()[:], ('s1', 'p1'))
            self.assertEqual(db.execute('SELECT work,name FROM claims').fetchone()[:], ('w1', 'file'))
            names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type IN ('table','index','trigger')")}
            self.assertIn('sessions_state_idx', names)
            self.assertNotIn('projects_v2', names)
            self.assertNotIn('sessions_v2', names)

    def test_invalid_registry_or_coordination_upgrade_rolls_back_version_and_rows(self):
        registry_db = self.home / 'registry.sqlite3'
        registry_v1(registry_db, child=True, broken=True)
        with closing(sqlite3.connect(registry_db)) as db, self.assertRaises(ValueError):
            upgrade_registry(db)
        with closing(sqlite3.connect(registry_db)) as db:
            self.assertEqual(db.execute('SELECT version FROM registry_meta').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT id FROM spaces').fetchone()[0], 'p1')

        coordination_db = self.home / 'coordination.sqlite3'
        coordination_v1(coordination_db, extra_session=True)
        with self.assertRaises(ValueError):
            upgrade_coordination(coordination_db)
        with closing(sqlite3.connect(coordination_db)) as db:
            self.assertEqual(db.execute('SELECT version FROM meta').fetchone()[0], 1)
            self.assertIsNotNone(db.execute("SELECT 1 FROM pragma_table_info('sessions') WHERE name='unknown_column'").fetchone())

    def test_registry_upgrade_failure_stays_pending_until_coordination_is_fixed(self):
        registry_v1(self.home / 'registry.sqlite3')
        coordination = self.home / 'coordination'
        coordination.mkdir()
        coordination_db = coordination / 'coordination.sqlite3'
        coordination_v1(coordination_db, extra_session=True)
        registry = ProjectRegistry(self.home, catalog=EmptyCatalog(), standalone=True)
        self.addCleanup(registry.close_connection_pool)
        with self.assertRaises(ValueError):
            registry.upgrade(confirmed=True)
        with self.assertRaises(ValueError):
            registry.require_ready()
        with self.assertRaises(ValueError):
            registry._management()
        for access in (registry.store, registry.base_store, registry.origin_files):
            with self.assertRaises(ValueError):
                access('p1')
        self.assertFalse((self.home/'projects/p1/project.json').exists())
        with closing(sqlite3.connect(self.home / 'registry.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT version FROM registry_meta').fetchone()[0], 2)
            self.assertEqual(db.execute('SELECT state FROM registry_upgrade').fetchone()[0], 'pending')

        with closing(sqlite3.connect(coordination_db)) as db:
            db.execute('ALTER TABLE sessions RENAME TO sessions_bad')
            db.execute('''CREATE TABLE sessions(id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id),
                workspace TEXT, state TEXT NOT NULL, seen REAL NOT NULL, turn TEXT,
                checkpoint TEXT NOT NULL DEFAULT '', task TEXT, last_cursor INTEGER NOT NULL DEFAULT 0)''')
            db.execute('''INSERT INTO sessions SELECT id,project,workspace,state,seen,turn,checkpoint,task,last_cursor FROM sessions_bad''')
            db.execute('DROP TABLE sessions_bad')
            db.commit()
        registry.upgrade(confirmed=True)
        registry.require_ready()
        self.assertEqual(registry.schema_version, 2)

    def test_create_receipt_replays_registered_id_after_post_commit_store_failure(self):
        registry = ProjectRegistry(self.home / 'registry', catalog=EmptyCatalog(), standalone=True)
        self.addCleanup(registry.close_connection_pool)
        request_id = 'a' * 32
        original = registry.base_store
        with patch.object(registry, 'base_store', side_effect=OSError('baseline unavailable')):
            with self.assertRaises(OSError):
                registry.create('Retryable', roots=[], request_id=request_id)
        with patch.object(registry, 'base_store', original):
            replay = registry.create('Retryable', roots=[], request_id=request_id)
        rows = registry.list()['projects']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], replay['id'])
        self.assertEqual(replay['name'], 'Retryable')


if __name__ == '__main__':
    unittest.main()
