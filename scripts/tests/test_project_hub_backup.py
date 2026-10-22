"""WAL backup preserves committed data and detects corrupt archives."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backup_project_hub import backup, verify


class BackupTest(unittest.TestCase):
    def test_wal_snapshot_and_tamper_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'project'
            data = root / 'docs/project-portal'
            data.mkdir(parents=True)
            (data / 'project.json').write_text(json.dumps(dict(schemaVersion=1, id='fixture', name='Fixture', tasks=[])))
            database = Path(temp) / 'live.sqlite3'
            destination = Path(temp) / 'snapshot'
            with closing(sqlite3.connect(database)) as live:
                live.execute('PRAGMA journal_mode=WAL')
                live.execute('CREATE TABLE sample(value TEXT)')
                live.execute("INSERT INTO sample VALUES('preserved')")
                live.commit()
                with patch('backup_project_hub.subprocess.check_output', return_value='test-commit'):
                    result = backup(root, database, destination)
                self.assertEqual(result['tasks'], [])
                with closing(sqlite3.connect(destination / 'coordination.sqlite3')) as copied:
                    self.assertEqual(copied.execute('SELECT value FROM sample').fetchone()[0], 'preserved')
            with self.assertRaises(ValueError):
                backup(root, database, destination)
            (destination / 'project-data/project.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                verify(destination)

    def test_refuses_repository_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, 'outside'):
                backup(temp, Path(temp) / 'db', Path(temp) / 'snapshot')
