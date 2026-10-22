from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_session_catalog import SessionCatalog, merge_sessions, workspace_key


class CatalogTest(unittest.TestCase):
    def test_normalizes_windows_extended_paths(self):
        self.assertEqual(workspace_key('\\\\?\\C:\\Project\\'), workspace_key('c:/project'))

    def test_only_matching_nonarchived_metadata_is_read(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'state.sqlite'
            c = sqlite3.connect(db)
            c.execute("CREATE TABLE threads(id TEXT,name TEXT,cwd TEXT,updated_at INTEGER,archived INTEGER,source TEXT DEFAULT 'vscode')")
            c.executemany('INSERT INTO threads(id,name,cwd,updated_at,archived) VALUES (?,?,?,?,?)', [
                ('a', 'Title A', '\\\\?\\C:\\project', 1, 0), ('b', 'Title B', 'C:/project/sub', 2, 0),
                ('c', 'Other', 'C:/project-other', 3, 0), ('d', 'Archived', 'C:/project', 4, 1)])
            c.execute("INSERT INTO threads VALUES ('sub','Internal','C:/project',5,0,'subagent')")
            c.commit(); c.close()
            before = db.read_bytes()
            result = SessionCatalog(db, ttl=0).read('c:/project')
            self.assertEqual([r['id'] for r in result['sessions']], ['b', 'a'])
            self.assertEqual(db.read_bytes(), before)

    def test_discovery_does_not_fabricate_connection_or_liveness(self):
        rows = merge_sessions([dict(id='a', name='Discovered', cwd='c:/p', updated_at=2)], [], {}, set(), {})
        self.assertEqual(rows[0]['integration'], 'discovered')
        self.assertIsNone(rows[0]['seen'])
        self.assertEqual(rows[0]['state'], 'unknown')

    def test_registration_merges_without_duplicate_and_preserves_evidence(self):
        rows = merge_sessions([dict(id='a', name='Old', cwd='c:/p', updated_at=2)],
                              [dict(id='a', state='idle', seen=3)], {'a': 'Codex name'}, {'a'}, {'a': 2})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['title'], 'Codex name')
        self.assertEqual(rows[0]['integration'], 'hooks')
        self.assertEqual(rows[0]['activeWork'], 2)

    def test_missing_database_is_not_created(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / 'missing.sqlite'
            self.assertFalse(SessionCatalog(db).read('c:/p')['available'])
            self.assertFalse(db.exists())
