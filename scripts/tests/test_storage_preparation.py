"""Verified original backup and startup upgrade with disposable data only."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_storage_upgrade import registry_v1, coordination_v1
from storage_preparation import prepare, _files


class StoragePreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / 'data'
        self.home.mkdir()
        registry_v1(self.home / 'registry.sqlite3', child=True)
        (self.home / 'coordination').mkdir()
        coordination_v1(self.home / 'coordination/coordination.sqlite3', child=True)
        (self.home / 'projects/p1').mkdir(parents=True)
        (self.home / 'projects/p1/immutable-file.txt').write_text('Original uploaded data', encoding='utf-8')

    def test_upgrade_preserves_original_bytes_ids_and_foreign_keys(self):
        before = _files(self.home)
        result = prepare(self.home)
        self.assertTrue(result['changed'])
        self.assertEqual(_files(Path(result['backup'])), before)
        with closing(sqlite3.connect(self.home / 'registry.sqlite3')) as c:
            self.assertEqual(c.execute('SELECT id,codex_id,ownership FROM spaces').fetchone(), ('p1', 'codex-p1', 'hub'))
            self.assertEqual(c.execute('SELECT space,body FROM space_notes').fetchone(), ('p1', 'kept'))
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
        with closing(sqlite3.connect(self.home / 'coordination/coordination.sqlite3')) as c:
            self.assertEqual(c.execute('SELECT id,project,session,task FROM work').fetchone(), ('w1', 'p1', 's1', 'task'))
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertFalse(prepare(self.home)['changed'])
        self.assertEqual(json.loads(Path(result['receipt']).read_text())['state'], 'complete')

    def test_changed_or_corrupt_backup_blocks_upgrade_without_touching_original(self):
        before = _files(self.home)
        with patch('storage_preparation._verify_backup', side_effect=ValueError('bad copy')):
            with self.assertRaises(ValueError):
                prepare(self.home)
        self.assertEqual(_files(self.home), before)

    def test_wal_snapshot_is_verified_without_changing_the_original_backup(self):
        database = self.home / 'registry.sqlite3'
        with closing(sqlite3.connect(database)) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute("INSERT INTO spaces VALUES('p2','codex-p2','Unavailable','[]',0,2.0)")
            db.commit()
            self.assertTrue(database.with_name(database.name + '-wal').is_file())
            result = prepare(self.home)
            receipt = json.loads(Path(result['receipt']).read_text())
            self.assertEqual(_files(Path(result['backup'])), receipt['files'])
            with closing(sqlite3.connect(Path(result['backup']) / 'registry.sqlite3')) as copy:
                self.assertEqual(copy.execute("SELECT present FROM spaces WHERE id='p2'").fetchone(), (0,))
            with closing(sqlite3.connect(database)) as copy:
                self.assertEqual(copy.execute("SELECT present,ownership FROM spaces WHERE id='p2'").fetchone(), (0, 'hub'))

    def test_recovery_retains_first_backup_and_never_serves_a_pending_upgrade(self):
        with patch('project_registry.ProjectRegistry.upgrade', side_effect=ValueError('interrupted')):
            with self.assertRaises(ValueError):
                prepare(self.home)
        receipt_path = self.home.parent / 'data-schema-backups/preparation.json'
        receipt = json.loads(receipt_path.read_text())
        self.assertEqual(receipt['state'], 'pending')
        result = prepare(self.home)
        self.assertEqual(result['backup'], receipt['backup'])
        self.assertEqual(json.loads(receipt_path.read_text())['state'], 'complete')

    def test_unknown_schema_is_preserved_without_a_backup_or_initializer_write(self):
        with closing(sqlite3.connect(self.home / 'registry.sqlite3')) as c:
            c.execute('UPDATE registry_meta SET version=99'); c.commit()
        before = _files(self.home)
        with self.assertRaises(ValueError):
            prepare(self.home)
        self.assertEqual(_files(self.home), before)
        self.assertFalse((self.home.parent / 'data-schema-backups').exists())


if __name__ == '__main__':
    unittest.main()
