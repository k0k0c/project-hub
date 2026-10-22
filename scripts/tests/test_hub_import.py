"""Focused inactive Hub storage import checks."""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
from hub_import import copy_folder, inspect_home
from hub_backup import BackupError


class HubImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hub-import-test-')
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'; self.source.mkdir()
        with closing(sqlite3.connect(self.source / 'registry.sqlite3')) as db:
            db.execute('CREATE TABLE registry_meta(version INTEGER NOT NULL)')
            db.execute('INSERT INTO registry_meta VALUES(2)')
            db.execute('CREATE TABLE spaces(id TEXT PRIMARY KEY, codex_id TEXT UNIQUE, name TEXT NOT NULL, roots TEXT NOT NULL, present INTEGER NOT NULL, updated REAL NOT NULL, revision INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0, ownership TEXT NOT NULL DEFAULT "hub")')
            db.commit()
        (self.source / 'coordination').mkdir()
        with closing(sqlite3.connect(self.source / 'coordination/coordination.sqlite3')) as db:
            db.execute('CREATE TABLE meta(version INTEGER NOT NULL)')
            db.execute('INSERT INTO meta VALUES(2)')
            db.commit()
        (self.source / 'projects').mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_inspect_includes_wal_in_revision(self):
        first = inspect_home(self.source)
        connection = sqlite3.connect(self.source / 'registry.sqlite3')
        try:
            connection.execute('PRAGMA journal_mode=WAL')
            connection.execute('CREATE TABLE IF NOT EXISTS wal_probe(value TEXT)')
            connection.execute("INSERT INTO wal_probe VALUES('pending')")
            connection.commit()
            second = inspect_home(self.source)
            self.assertNotEqual(first['revision'], second['revision'])
        finally:
            connection.close()

    def test_copy_rejects_active_or_nested_destination(self):
        with self.assertRaises(BackupError):
            copy_folder(self.source, self.source / 'nested', expected=inspect_home(self.source)['revision'],
                        active_home=self.root / 'other')
        with self.assertRaises(BackupError):
            copy_folder(self.source, self.root / 'copy', expected=inspect_home(self.source)['revision'],
                        active_home=self.source)

    def test_copy_preserves_source_and_returns_inactive_home(self):
        expected = inspect_home(self.source)['revision']
        source_bytes = (self.source / 'registry.sqlite3').read_bytes()
        destination = self.root / 'inactive'
        result = copy_folder(self.source, destination, expected=expected, active_home=self.root / 'active')
        self.assertFalse(result['active'])
        self.assertEqual((self.source / 'registry.sqlite3').read_bytes(), source_bytes)
        self.assertTrue((destination / 'data/registry.sqlite3').is_file())

    def test_automatic_copy_inspects_once_under_the_writer_reservation(self):
        with patch('hub_import.inspect_home', wraps=inspect_home) as inspection:
            result = copy_folder(self.source, self.root / 'automatic', expected=None,
                                 active_home=self.root / 'active', inspect_and_copy=True)
        self.assertEqual(inspection.call_count, 1)
        self.assertEqual(result['sourcePreview']['revision'], inspect_home(self.source)['revision'])
        self.assertTrue(Path(result['path']).is_dir())

    def test_unconfirmed_copy_still_requires_the_inspected_revision(self):
        destination = self.root / 'unconfirmed'
        with self.assertRaises(BackupError):
            copy_folder(self.source, destination, expected=None, active_home=self.root / 'active')
        self.assertFalse(destination.exists())

    def test_inspection_reports_validation_stage_and_current_file_with_same_revision(self):
        (self.source/'fixture.bin').write_bytes(b'x'*3*1024*1024)
        progress=[]
        expected=inspect_home(self.source)
        actual=inspect_home(self.source,progress=progress.append)
        self.assertEqual(actual,expected)
        self.assertTrue(any(p.get('step')=='database-integrity' and p.get('currentFile')=='registry.sqlite3' for p in progress))
        hashing=[p for p in progress if p.get('step')=='hashing']
        self.assertTrue(any(p.get('currentFile')=='fixture.bin' for p in hashing))
        self.assertEqual(hashing[-1]['completed'],hashing[-1]['total'])
        self.assertEqual(hashing[-1]['unit'],'files')


if __name__ == '__main__':
    unittest.main()
