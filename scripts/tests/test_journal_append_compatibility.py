"""Compatibility coverage for recoverable journal append intents."""
import hashlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_registry import CodexProjects, ProjectRegistry
import journal_append

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_task_read_models as read_model_fixtures


class JournalAppendCompatibilityTests(unittest.TestCase):
    def setUp(self):
        read_model_fixtures.ReadModelTests.setUp(self)

    def _intent(self, project, event):
        with self.registry.connect() as connection:
            return dict(connection.execute(
                'SELECT * FROM journal_append_intents WHERE project=? AND event=?',
                (project, event)).fetchone())

    def test_new_intent_proof_and_legacy_complete_after_hash(self):
        self.view.memory_snapshot()
        event = dict(id='compat-proof', kind='note', taskId='task', title='Proof',
                     schemaVersion=1, seq=2, at='2026-01-01T00:00:00Z')
        before = self.view.journal.read_bytes()
        self.view._load()
        row = journal_append.prepare(self.view, event)
        self.assertEqual(b'', row['after_hash'])
        self.assertEqual(hashlib.sha256(before).digest(), row['before_hash'])
        self.assertEqual(len(before), row['before_size'])
        self.assertEqual(hashlib.sha256(before + row['suffix']).digest(),
                         journal_append.append(self.view, event, prepared=row))

        old_event = dict(id='compat-legacy-partial', kind='note', taskId='task', title='Legacy partial',
                         schemaVersion=1, seq=3, at='2026-01-01T00:00:01Z')
        prior = self.view.journal.read_bytes()
        self.view._load()
        old_row = journal_append.prepare(self.view, old_event)
        old_row['after_hash'] = hashlib.sha256(prior + old_row['suffix']).digest()
        partial = old_row['suffix'][:len(old_row['suffix']) // 2]
        self.view.journal.write_bytes(prior + partial)
        with self.registry.connect() as connection:
            connection.execute('INSERT INTO journal_append_intents VALUES(?,?,?,?,?,?,?)',
                               tuple(old_row.values()))
        self.assertEqual(old_row['after_hash'], journal_append.finish(self.view, old_row))

        complete_event = dict(id='compat-legacy-complete', kind='note', taskId='task', title='Legacy complete',
                              schemaVersion=1, seq=4, at='2026-01-01T00:00:02Z')
        prior = self.view.journal.read_bytes()
        self.view._load()
        complete_row = journal_append.prepare(self.view, complete_event)
        complete_row['after_hash'] = hashlib.sha256(prior + complete_row['suffix']).digest()
        self.view.journal.write_bytes(prior + complete_row['suffix'])
        with self.registry.connect() as connection:
            connection.execute('INSERT INTO journal_append_intents VALUES(?,?,?,?,?,?,?)',
                               tuple(complete_row.values()))
        self.assertEqual(complete_row['after_hash'], journal_append.finish(self.view, complete_row))

    def test_legacy_pending_intent_after_hash_is_repaired_exactly_once(self):
        self.view.memory_snapshot()
        event = dict(id='compat-pending', kind='note', taskId='task', title='Pending')
        self.view._load()
        before = self.view.journal.read_bytes()
        with patch('journal_append.checkpoint', side_effect=lambda point:
                   (_ for _ in ()).throw(RuntimeError('interrupted')) if point == 'after_intent' else None):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                self.view.record(event)
        intent = self._intent(self.view.project_id, event['id'])
        after_hash = hashlib.sha256(before + bytes(intent['suffix'])).digest()
        with self.registry.connect() as connection:
            connection.execute('UPDATE journal_append_intents SET after_hash=? WHERE project=? AND event=?',
                               (after_hash, self.view.project_id, event['id']))
        restarted = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
        view = restarted.store(self.view.project_id)
        self.assertEqual(1, sum(item['id'] == event['id'] for item in view.memory_snapshot()['allEvents']))
        self.assertEqual(1, sum(item['id'] == event['id'] for item in view.memory_snapshot()['allEvents']))
        with restarted.connect() as connection:
            self.assertEqual(0, connection.execute(
                'SELECT count(*) FROM journal_append_intents WHERE project=? AND event=?',
                (view.project_id, event['id'])).fetchone()[0])

    def test_same_size_restored_mtime_tamper_fails_closed_during_recovery(self):
        self.view.memory_snapshot()
        event = dict(id='compat-tamper', kind='note', taskId='task', title='Tamper')
        with patch('journal_append.checkpoint', side_effect=lambda point:
                   (_ for _ in ()).throw(RuntimeError('interrupted')) if point == 'after_intent' else None):
            with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                self.view.record(event)
        original = self.view.journal.read_bytes()
        stat = self.view.journal.stat()
        changed = bytearray(original)
        changed[0] = ord('X') if changed[0] != ord('X') else ord('Y')
        self.view.journal.write_bytes(changed)
        os.utime(self.view.journal, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        replacement = self.view.journal.read_bytes()
        restarted = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
        view = restarted.store(self.view.project_id)
        with self.assertRaisesRegex(ValueError, 'conflicts with pending'):
            view.memory_snapshot()
        self.assertEqual(replacement, view.journal.read_bytes())
        with restarted.connect() as connection:
            self.assertEqual(1, connection.execute(
                'SELECT count(*) FROM journal_append_intents WHERE project=? AND event=?',
                (view.project_id, event['id'])).fetchone()[0])
        with self.assertRaisesRegex(ValueError, 'conflicts with pending'):
            view.memory_snapshot()
        self.assertEqual(replacement, view.journal.read_bytes())


if __name__ == '__main__':
    unittest.main()
