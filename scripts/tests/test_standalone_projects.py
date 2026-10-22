"""Focused contracts for independent, rootless Hub projects.

These tests deliberately use a temporary external data home.  They describe
the standalone registry API and are expected to run after that API is wired
into ProjectRegistry.
"""
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from project_registry import ProjectRegistry


class FakeCatalog:
    """Read-only discovery fixture; it never writes or resurrects Hub rows."""

    def __init__(self, projects=None):
        self.projects = list(projects or [])

    def read(self):
        return {
            'available': True,
            'projects': list(self.projects),
            'assignments': {},
            'source': 'fixture',
        }

    def assigned_project(self, session):
        return None


class StandaloneProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / 'external-hub-data'
        self.catalog = FakeCatalog()
        self.registry = ProjectRegistry(self.home, catalog=self.catalog, standalone=True)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def request(seed):
        return f'{seed:032x}'

    def test_create_is_rootless_owned_and_idempotent(self):
        request_id = self.request(1)
        first = self.registry.create('Local Hub', roots=[], request_id=request_id)
        retry = self.registry.create('Local Hub', roots=[], request_id=request_id)

        self.assertEqual(first['id'], retry['id'])
        self.assertEqual(first['revision'], 1)
        self.assertEqual(first['ownership'], 'hub')
        self.assertEqual(first['roots'], [])
        self.assertEqual(first, retry)
        with self.assertRaises((ValueError, RuntimeError)):
            self.registry.create('Other name', roots=[], request_id=request_id)

    def test_update_uses_per_project_cas_and_preserves_winner(self):
        project = self.registry.create('Before', roots=[], request_id=self.request(2))
        updated = self.registry.update(project['id'], {'name': 'After'}, expected=1, request_id=self.request(3))
        self.assertEqual(updated['name'], 'After')
        self.assertEqual(updated['revision'], 2)

        with self.assertRaises((ValueError, RuntimeError)):
            self.registry.update(project['id'], {'name': 'Stale'}, expected=1, request_id=self.request(4))
        current = next(row for row in self.registry.list()['projects'] if row['id'] == project['id'])
        self.assertEqual(current['name'], 'After')
        self.assertEqual(current['revision'], 2)

    def test_soft_delete_recover_and_include_deleted(self):
        project = self.registry.create('Archive me', roots=[], request_id=self.request(5))
        deleted = self.registry.update(project['id'], {'deleted': True}, expected=1, request_id=self.request(6))
        self.assertTrue(deleted['deleted'])
        self.assertFalse(any(row['id'] == project['id'] for row in self.registry.list()['projects']))
        self.assertTrue(any(row['id'] == project['id'] for row in self.registry.list(include_deleted=True)['projects']))

        recovered = self.registry.update(project['id'], {'deleted': False}, expected=2, request_id=self.request(7))
        self.assertFalse(recovered['deleted'])
        self.assertTrue(any(row['id'] == project['id'] for row in self.registry.list()['projects']))

    def test_archive_flag_and_patch_validation(self):
        project = self.registry.create('Archive flag', roots=[], request_id=self.request(8))
        archived = self.registry.update(project['id'], {'archived': True}, expected=1, request_id=self.request(9))
        self.assertTrue(archived['archived'])
        with self.assertRaises((ValueError, RuntimeError)):
            self.registry.update(project['id'], {'roots': ['C:/unexpected']}, expected=2, request_id=self.request(10))

    def test_discovery_does_not_rename_or_resurrect_hub_projects(self):
        workspace = Path(self.temp.name) / 'legacy-workspace'
        workspace.mkdir()
        codex_id = 'external'
        catalog = FakeCatalog([dict(codexId=codex_id, name='External', roots=[str(workspace.resolve())])])
        legacy_home = Path(self.temp.name) / 'discovered-legacy-home'
        legacy = ProjectRegistry(legacy_home, catalog=catalog, standalone=False)
        legacy_projects = legacy.list()['projects']
        self.assertEqual(legacy_projects[0]['codex_id'], codex_id)
        legacy.close_connection_pool()

        standalone = ProjectRegistry(legacy_home, catalog=catalog, standalone=True)
        standalone.upgrade(confirmed=True)
        project = standalone.list(include_deleted=True)['projects'][0]
        renamed = standalone.update(project['id'], {'name': 'Hub name'},
                                    expected=project['revision'], request_id=self.request(11))
        standalone.update(renamed['id'], {'deleted': True}, expected=renamed['revision'],
                           request_id=self.request(12))

        catalog.projects = [dict(codexId=codex_id, name='External renamed',
                                 roots=[str(workspace.resolve())])]
        standalone.refresh()
        current = standalone.list(include_deleted=True)['projects'][0]
        self.assertEqual(current['name'], 'Hub name')
        self.assertTrue(current['deleted'])

    def test_legacy_schema_is_read_without_implicit_upgrade(self):
        legacy_home = Path(self.temp.name) / 'legacy-hub-data'
        legacy_home.mkdir()
        legacy = legacy_home / 'registry.sqlite3'
        with closing(sqlite3.connect(legacy)) as connection:
            connection.executescript('''
                CREATE TABLE registry_meta(version INTEGER NOT NULL);
                INSERT INTO registry_meta VALUES(1);
                CREATE TABLE spaces(id TEXT PRIMARY KEY,codex_id TEXT UNIQUE NOT NULL,name TEXT NOT NULL,
                                    roots TEXT NOT NULL,present INTEGER NOT NULL,updated REAL NOT NULL);
            ''')
        reread = ProjectRegistry(legacy_home, catalog=FakeCatalog(), standalone=True)
        self.assertEqual(reread.schema_version, 1)
        self.assertEqual(reread.list()['schemaVersion'], 1)
        self.assertEqual(reread.list()['projects'], [])
        with self.assertRaises((ValueError, RuntimeError)):
            reread.upgrade()

    def test_independent_catalog_preserves_saved_legacy_project_presence(self):
        workspace = Path(self.temp.name)/'saved-workspace'
        workspace.mkdir()
        home = Path(self.temp.name)/'saved-home'
        legacy = ProjectRegistry(home,catalog=FakeCatalog([
            dict(codexId='saved',name='Saved project',roots=[str(workspace.resolve())])]))
        before = legacy.list()['projects'][0]
        legacy.close_connection_pool()
        independent = ProjectRegistry(home,standalone=True)
        self.addCleanup(independent.close_connection_pool)
        after = independent.list()['projects'][0]
        for field in ('id','codex_id','name','roots','present','updated'):
            self.assertEqual(after[field],before[field])
        self.assertTrue(after['present'])
        self.assertEqual(independent.schema_version,1)
        independent.upgrade(confirmed=True)
        upgraded = independent.list()['projects'][0]
        self.assertTrue(upgraded['present'])
        self.assertEqual(upgraded['codex_id'],'saved')

    def test_upgrade_requires_confirmation_and_is_explicit(self):
        with self.assertRaises((ValueError, RuntimeError)):
            self.registry.upgrade()
        upgraded = self.registry.upgrade(confirmed=True)
        self.assertEqual(upgraded['schemaVersion'], 2)
        self.assertEqual(self.registry.schema_version, 2)

    def test_rootless_store_can_snapshot_and_record_history(self):
        project = self.registry.create('Rootless history', roots=[], request_id=self.request(13))
        store = self.registry.base_store(project['id'])
        self.assertIsNone(store.root)
        before = store.snapshot()
        self.assertEqual(before['project']['id'], project['id'])
        store.record({'taskId':'history-task', 'kind':'task.created', 'title':'History task', 'patch':{'title':'History task','status':'active'}})
        before = store.snapshot()
        event = store.record({'taskId':'history-task', 'kind': 'note', 'title': 'Rootless note', 'detail': 'Stored without a code workspace'}, expected_revision=before['revision'])
        self.assertEqual(event['kind'], 'note')
        after = store.snapshot()
        self.assertNotEqual(after['revision'], before['revision'])
        self.assertEqual(after['allEvents'][-1]['title'], 'Rootless note')

    def test_cas_conflict_does_not_drop_rootless_history(self):
        project = self.registry.create('Conflict history', roots=[], request_id=self.request(14))
        store = self.registry.base_store(project['id'])
        store.record({'taskId':'history-task', 'kind':'task.created', 'title':'History task', 'patch':{'title':'History task','status':'active'}})
        first = store.snapshot()
        store.record({'taskId':'history-task', 'kind': 'note', 'title': 'Winner'}, expected_revision=first['revision'])
        with self.assertRaises((ValueError, RuntimeError)):
            store.record({'taskId':'history-task', 'kind': 'note', 'title': 'Stale'}, expected_revision=first['revision'])
        current = store.snapshot()
        self.assertEqual([event['title'] for event in current['allEvents'] if event['kind'] == 'note'], ['Winner'])


if __name__ == '__main__':
    unittest.main()
