"""Exact-content inventory reuse with isolated journals and ownership state."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_portal import Store
from project_registry import CodexProjects, ProjectRegistry
from task_transfer import barrier, inventory


class InventoryCacheTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        catalog = self.root / 'catalog.json'
        catalog.write_text(json.dumps({'local-projects': {
            name: {'id': name, 'name': name, 'rootPaths': [str(self.root / name)]}
            for name in ('first', 'second')}}), encoding='utf-8')
        self.registry = ProjectRegistry(self.root / 'data', CodexProjects(catalog))
        rows = self.registry.list()['projects']
        self.first, self.second = [next(row['id'] for row in rows if row['codex_id'] == name)
                                   for name in ('first', 'second')]
        self.store = self.registry.base_store(self.first)
        self.store.record({'taskId': 'task', 'kind': 'task.created', 'title': 'Create',
                           'patch': {'title': 'Original', 'status': 'planned', 'stages': []}})

    def read(self):
        with barrier(self.registry):
            return inventory(self.registry)

    def test_unchanged_inventory_skips_replay_and_returns_protected_copies(self):
        first, _, _ = self.read()
        first[self.first][0]['name'] = 'Caller altered seed'
        first[self.first][1][0]['title'] = 'Caller altered task'
        first[self.first][2][0]['patch']['title'] = 'Caller altered event'
        with patch.object(Store, '_load', side_effect=AssertionError('Unchanged input replayed')), \
                patch.object(Store, '_sync_git_commit_events', side_effect=AssertionError('Unchanged migration replayed')):
            second, _, _ = self.read()
        self.assertNotEqual('Caller altered seed', second[self.first][0]['name'])
        self.assertEqual('Original', second[self.first][1][0]['title'])
        self.assertEqual('Original', second[self.first][2][0]['patch']['title'])

    def test_same_size_journal_rewrite_with_restored_timestamp_is_not_stale(self):
        self.read()
        before = self.store.journal.stat()
        raw = self.store.journal.read_bytes()
        changed = raw.replace(b'Original', b'Modified')
        self.assertEqual(len(raw), len(changed))
        self.store.journal.write_bytes(changed)
        os.utime(self.store.journal, ns=(before.st_atime_ns, before.st_mtime_ns))
        self.assertEqual(before.st_mtime_ns, self.store.journal.stat().st_mtime_ns)
        snapshots, _, _ = self.read()
        self.assertEqual('Modified', snapshots[self.first][1][0]['title'])

    def test_seed_changes_are_invalidation_inputs(self):
        self.read()
        seed = self.store.data / 'project.json'
        content = json.loads(seed.read_text(encoding='utf-8'))
        content['name'] = 'New baseline name'
        seed.write_text(json.dumps(content), encoding='utf-8')
        self.assertEqual('New baseline name', self.read()[0][self.first][0]['name'])

    def test_writes_and_generated_history_are_not_hidden_by_warm_cache(self):
        self.read()
        self.store.record({'taskId': 'task', 'kind': 'task.updated', 'title': 'Start',
                           'patch': {'status': 'active'}}, expected_revision=1)
        snapshots, _, _ = self.read()
        self.assertEqual('active', snapshots[self.first][1][0]['status'])
        self.assertEqual(1, sum(event['kind'] == 'task.status_changed' for event in snapshots[self.first][2]))
        with patch.object(Store, '_load', side_effect=AssertionError('Completed migration replayed')):
            self.assertEqual(snapshots, self.read()[0])
        with self.assertRaises(ValueError):
            self.store.record({'taskId': 'task', 'kind': 'task.updated', 'title': 'Stale',
                               'patch': {'title': 'Rejected'}}, expected_revision=1)

    def test_ownership_is_always_read_fresh_even_with_cached_origins(self):
        self.read()
        with self.registry.connect() as connection:
            connection.execute('UPDATE task_owners SET owner=? WHERE origin=?', (self.second, self.first))
        _, owners, _ = self.read()
        self.assertEqual(self.second, next(row for row in owners if row['origin'] == self.first)['owner'])

    def test_corrupt_or_unreadable_inputs_do_not_fall_back_to_cached_success(self):
        self.read()
        original_read = Path.open

        def inaccessible(path, *args, **kwargs):
            if path == self.store.journal:
                raise PermissionError('Fixture journal unavailable')
            return original_read(path, *args, **kwargs)

        with patch.object(Path, 'open', inaccessible), self.assertRaises(PermissionError):
            self.read()
        journal_bytes = self.store.journal.read_bytes()
        self.store.journal.unlink()
        self.assertEqual([], self.read()[0][self.first][1])
        self.store.journal.write_bytes(journal_bytes)
        self.store.journal.write_text('{broken', encoding='utf-8')
        with self.assertRaises(ValueError):
            self.read()


if __name__ == '__main__':
    unittest.main()
