"""Activation revision checks precede registry initialization under the home lease."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import hub_import
from hub_lifecycle import home_lease
import project_portal


class ActivationStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hub-activation-startup-')
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / 'data'
        self.home.mkdir()
        with closing(sqlite3.connect(self.home / 'registry.sqlite3')) as db:
            db.execute('CREATE TABLE registry_meta(version INTEGER NOT NULL)')
            db.execute('INSERT INTO registry_meta VALUES(2)')
            db.execute('CREATE TABLE spaces(id TEXT PRIMARY KEY, codex_id TEXT UNIQUE, name TEXT NOT NULL, roots TEXT NOT NULL, present INTEGER NOT NULL, updated REAL NOT NULL, revision INTEGER NOT NULL DEFAULT 1, archived INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0, ownership TEXT NOT NULL DEFAULT "hub")')
            db.commit()
        self.argv = ['--projects-home', str(self.home), '--standalone', 'serve', '--transport', 'threaded']

    def test_target_changed_after_supervisor_preview_never_initializes_registry(self):
        expected = hub_import.inspect_home(self.home)['revision']
        # A competing owner acquires the lease during the supervisor's drain.
        with home_lease(self.home), closing(sqlite3.connect(self.home / 'registry.sqlite3')) as db:
            db.execute('CREATE TABLE late_change(value TEXT)')
            db.execute("INSERT INTO late_change VALUES('accepted after early check')")
            db.commit()
        unchanged = (self.home / 'registry.sqlite3').read_bytes()
        with patch.dict(os.environ, {'PROJECT_HUB_ACTIVATION_EXPECTED': expected}), \
             patch.object(project_portal, 'serve_projects') as serve, \
             patch('project_registry.ProjectRegistry') as registry:
            with self.assertRaisesRegex(ValueError, 'changed before runtime activation'):
                project_portal.main(self.argv)
        serve.assert_not_called()
        registry.assert_not_called()
        self.assertEqual((self.home / 'registry.sqlite3').read_bytes(), unchanged)

    def test_matching_snapshot_is_checked_under_lifetime_lease(self):
        expected = hub_import.inspect_home(self.home)['revision']
        inspect = hub_import.inspect_home
        def inspect_locked(home):
            with self.assertRaises(TimeoutError):
                with home_lease(home):
                    pass
            return inspect(home)
        with patch.dict(os.environ, {'PROJECT_HUB_ACTIVATION_EXPECTED': expected}), \
             patch.object(hub_import, 'inspect_home', side_effect=inspect_locked), \
             patch.object(project_portal, 'serve_projects', return_value=7) as serve:
            self.assertEqual(project_portal.main(self.argv), 7)
        serve.assert_called_once()

    def test_matching_legacy_schema_is_rejected_before_initialization(self):
        with closing(sqlite3.connect(self.home / 'registry.sqlite3')) as db:
            db.execute('UPDATE registry_meta SET version=1')
            db.commit()
        expected = hub_import.inspect_home(self.home)['revision']
        unchanged = (self.home / 'registry.sqlite3').read_bytes()
        with patch.dict(os.environ, {'PROJECT_HUB_ACTIVATION_EXPECTED': expected}), \
             patch.object(project_portal, 'serve_projects') as serve:
            with self.assertRaisesRegex(ValueError, 'upgrade the inactive copy'):
                project_portal.main(self.argv)
        serve.assert_not_called()
        self.assertEqual((self.home / 'registry.sqlite3').read_bytes(), unchanged)

    def test_ordinary_start_has_no_activation_precondition(self):
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(hub_import, 'inspect_home', side_effect=AssertionError('ordinary launch must not inspect activation revision')), \
             patch.object(project_portal, 'serve_projects', return_value=0):
            # Raw test servers opt into the explicit isolated development path.
            self.assertEqual(project_portal.main(['--development', *self.argv]), 0)

    def test_main_server_requires_shared_launcher_before_opening_storage(self):
        from contextlib import redirect_stderr
        import io
        unchanged = (self.home / 'registry.sqlite3').read_bytes()
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(project_portal, 'serve_projects') as serve, \
             redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                project_portal.main(self.argv)
        self.assertEqual(error.exception.code, 2)
        serve.assert_not_called()
        self.assertEqual((self.home / 'registry.sqlite3').read_bytes(), unchanged)


if __name__ == '__main__':
    unittest.main()
