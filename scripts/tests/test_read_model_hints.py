"""Persisted lightweight hints avoid decoding full prepared views in SSE polls."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_task_read_models as read_model_fixtures
from project_registry import CodexProjects, ProjectRegistry
from task_transfer import transfer


class ReadModelHintTests(unittest.TestCase):
    def setUp(self):
        # Warm-hit contracts require the same clock bucket across preparation
        # and hint reads. The explicit clock-change test overrides this pin.
        clock = patch('read_models.time.time', return_value=1800000000)
        clock.start()
        self.addCleanup(clock.stop)
        read_model_fixtures.ReadModelTests.setUp(self)

    def test_hint_matches_persisted_summary(self):
        models = self.registry.read_models
        summary = models.snapshot(self.view, observations=False, summary=True)
        hint = models.hint(self.view)
        self.assertEqual(summary['revision'], hint['revision'])
        self.assertEqual(summary['settings']['revision'], hint['settings']['revision'])
        self.assertEqual(summary['relationsRevision'], hint['relationsRevision'])

    def test_warm_hint_does_not_decode_summary_or_build(self):
        models = self.registry.read_models
        # Keep preparation and the guarded read in one view-key bucket.  The
        # full suite can otherwise cross the ten-second freshness boundary
        # between these two operations and turn a warm-hint assertion into a
        # legitimate cold miss.
        with patch('read_models.time.time', return_value=1800000000):
            models.snapshot(self.view, observations=False, summary=True)
            with self.registry.connect() as connection:
                summary = connection.execute('SELECT summary FROM read_model_views WHERE project=?',
                                             (self.view.project_id,)).fetchone()['summary']
            original = json.loads
            def guarded(value, *args, **kwargs):
                if value == summary:
                    raise AssertionError('warm hint decoded the full summary')
                return original(value, *args, **kwargs)
            with patch.object(self.view, '_build_snapshot', side_effect=AssertionError('warm hint rebuilt view')), \
                 patch('read_models.json.loads', side_effect=guarded):
                hint = models.hint(self.view)
        self.assertIsInstance(hint, dict)

    def test_hint_survives_a_second_registry_instance(self):
        models = self.registry.read_models
        models.snapshot(self.view, observations=False, summary=True)
        restarted = ProjectRegistry(self.registry.home, CodexProjects(self.catalog))
        view = restarted.store(self.ids['one'])
        with patch.object(view, '_build_snapshot', side_effect=AssertionError('restart rebuilt view')):
            self.assertEqual(models.hint(self.view), restarted.read_models.hint(view))

    def test_append_transfer_and_settings_advance_hint_key(self):
        models = self.registry.read_models
        models.snapshot(self.view, observations=False, summary=True)
        before = models.hint(self.view)
        self.view.record(dict(kind='note', taskId='task', title='Hint append'))
        after = models.hint(self.view)
        self.assertNotEqual(after['revision'], before['revision'])

        preview = transfer(self.registry, self.ids['one'], self.ids['two'], 'task', preview=True)
        transfer(self.registry, self.ids['one'], self.ids['two'], 'task',
                 expected=preview['revision'], request='hint-transfer')
        target = self.registry.store(self.ids['two'])
        models.snapshot(target, observations=False, summary=True)
        self.assertIsNotNone(models.hint(target))

        plugin_scripts = Path(__file__).resolve().parents[2] / 'tools/project-portal/plugins/project-hub/scripts'
        sys.path.insert(0, str(plugin_scripts))
        from project_settings import read_settings, update_settings
        settings = read_settings(target)
        update_settings(target, {'git': {'autoCommit': True}}, settings['revision'])
        self.assertIsNone(models.hint(target))

    def test_clock_bucket_changes_view_key_without_changing_domain(self):
        models = self.registry.read_models
        with patch('read_models.time.time', return_value=1800000000):
            models.snapshot(self.view, observations=False, summary=True)
            self.assertIsNotNone(models.hint(self.view))
        with patch('read_models.time.time', return_value=1800000011):
            self.assertIsNone(models.hint(self.view))


if __name__ == '__main__':
    unittest.main()
