"""Exact-content cache and unchanged-read work regressions on isolated data."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_registry import CodexProjects, ProjectRegistry
from project_portal import Store
from task_transfer import barrier, inventory


class PerformanceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.catalog = self.base / 'catalog.json'
        self.catalog.write_text(json.dumps({'local-projects': {'a': dict(
            id='a', name='First', rootPaths=[str(self.base / 'project')])}}))
        self.registry = ProjectRegistry(self.base / 'data', CodexProjects(self.catalog))
        self.pid = self.registry.list()['projects'][0]['id']
        self.store = self.registry.base_store(self.pid)
        self.store.record(dict(kind='task.created', taskId='task', title='Created',
            patch=dict(title='Task', status='planned', stages=[])))

    def tearDown(self):
        self.temp.cleanup()

    def test_catalog_avoids_reparse_but_same_size_restored_timestamp_change_invalidates(self):
        catalog = self.registry.catalog
        catalog.read()
        with patch('project_registry.json.loads', wraps=json.loads) as loads:
            one = catalog.read()
            one['projects'][0]['name'] = 'Caller mutation'
            self.assertEqual(catalog.read()['projects'][0]['name'], 'First')
            self.assertEqual(loads.call_count, 0)
            stamp = self.catalog.stat()
            self.catalog.write_bytes(self.catalog.read_bytes().replace(b'First', b'Other'))
            os.utime(self.catalog, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            self.assertEqual(catalog.read()['projects'][0]['name'], 'Other')
            self.assertEqual(loads.call_count, 1)
        self.catalog.write_text('{broken')
        self.assertFalse(catalog.read()['available'])

    def test_hot_inventory_skips_reprojection_and_ownership_writes(self):
        statements = []
        original_connect = self.registry.connect
        from contextlib import contextmanager
        @contextmanager
        def traced_connect():
            with original_connect() as connection:
                connection.set_trace_callback(statements.append)
                yield connection
        with barrier(self.registry):
            inventory(self.registry)
            inventory(self.registry)
            with patch.object(Store, 'project', wraps=Store.project) as project:
                with patch.object(self.registry, 'connect', traced_connect):
                    snapshots, _, _ = inventory(self.registry)
                self.assertEqual(project.call_count, 0)
            snapshots[self.pid][1][0]['title'] = 'Caller mutation'
            self.assertEqual(inventory(self.registry)[0][self.pid][1][0]['title'], 'Task')
        self.assertFalse(any('INSERT' in sql.upper() or 'BEGIN IMMEDIATE' in sql.upper()
                             for sql in statements), statements)

    def test_cached_catalog_rechecks_root_alias_resolution(self):
        self.registry.catalog.read()
        retargeted = self.base / 'retargeted'
        with patch('project_registry.Path.resolve', return_value=retargeted) as resolve:
            result = self.registry.catalog.read()
        self.assertEqual(result['projects'][0]['roots'], [str(retargeted)])
        self.assertEqual(resolve.call_count, 1)

    def test_memory_snapshot_borrows_inputs_without_exposing_cached_values(self):
        seed_path = self.store.data / 'project.json'
        seed = json.loads(seed_path.read_text(encoding='utf-8-sig'))
        seed['metadata'] = dict(labels=['original'])
        seed_path.write_text(json.dumps(seed), encoding='utf-8')
        self.store.record(dict(kind='note', taskId='task', title='Evidence',
                               detail='Original detail', evidence=[dict(path='README.md')]))
        view = self.registry.store(self.pid)
        with patch.object(Store, 'diagnostics', side_effect=AssertionError('Optional discovery')):
            first = view.memory_snapshot()
            view.memory_snapshot()  # populate the exact-content cache after migrations
            first['project']['metadata']['labels'].append('caller mutation')
            first['tasks'][0]['title'] = 'Caller mutation'
            first['allEvents'][-1]['detail'] = 'Caller mutation'
            first['allEvents'][-1]['evidence'][0]['path'] = 'changed.md'
            fresh = view.memory_snapshot()
        self.assertEqual(fresh['revision'], first['revision'])
        self.assertEqual(fresh['project']['metadata']['labels'], ['original'])
        self.assertEqual(fresh['tasks'][0]['title'], 'Task')
        self.assertEqual(fresh['allEvents'][-1]['detail'], 'Original detail')
        self.assertEqual(fresh['allEvents'][-1]['evidence'][0]['path'], 'README.md')

    def test_server_plan_keeps_task_contract_without_optional_discovery(self):
        from plugin_api import call
        with patch.object(Store, 'diagnostics', side_effect=AssertionError('Optional discovery')):
            result = call(self.registry, dict(cwd=str(self.store.root), session='isolated-reader',
                          tool='hub_plan', arguments=dict(task='task')))
            updated = call(self.registry, dict(cwd=str(self.store.root), session='isolated-reader',
                           tool='hub_task_update', arguments=dict(task='task', expected=result['revision'],
                                                                 patch=dict(title='Renamed task'))))
        self.assertEqual(result['task']['id'], 'task')
        self.assertIsInstance(result['revision'], str)
        self.assertNotEqual(updated['revision'], result['revision'])
        self.assertEqual(self.registry.store(self.pid).memory_snapshot()['tasks'][0]['title'], 'Renamed task')

    def test_external_journal_change_updates_revision_with_restored_timestamp(self):
        view = self.registry.store(self.pid)
        initial = view.snapshot()
        view.snapshot()
        stamp = self.store.journal.stat()
        # An independent store represents a writer outside this registry cache.
        external = Store(self.store.root, data_dir=self.store.data,
                         coordination_home=self.store.coordination_home)
        external.record(dict(kind='note', taskId='task', title='External observation'))
        os.utime(self.store.journal, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        changed = view.snapshot()
        self.assertNotEqual(initial['revision'], changed['revision'])
        self.assertTrue(any(event['title'] == 'External observation' for event in changed['events']))
        stamp = self.store.journal.stat()
        self.store.journal.write_bytes(self.store.journal.read_bytes().replace(
            b'External observation', b'Restored observation'))
        os.utime(self.store.journal, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
        restored = view.snapshot()
        self.assertNotEqual(changed['revision'], restored['revision'])
        self.assertTrue(any(event['title'] == 'Restored observation' for event in restored['events']))

    def test_registry_refresh_stays_fresh_without_unchanged_write_transaction(self):
        self.registry.refresh()
        statements = []
        original_connect = self.registry.connect
        from contextlib import contextmanager
        @contextmanager
        def traced_connect():
            with original_connect() as connection:
                connection.set_trace_callback(statements.append)
                yield connection
        with patch.object(self.registry, 'connect', traced_connect):
            self.registry.refresh()
            self.registry.base_store(self.pid)
        self.assertFalse(any('BEGIN IMMEDIATE' in sql.upper() for sql in statements), statements)
        # Direct database edits are seen on the next refresh, never hidden by a
        # registry-level memo of the discovery response.
        with self.registry.connect() as connection:
            connection.execute('UPDATE spaces SET name=? WHERE id=?', ('External', self.pid))
        self.assertEqual(self.registry.list()['projects'][0]['name'], 'First')


if __name__ == '__main__':
    unittest.main()
