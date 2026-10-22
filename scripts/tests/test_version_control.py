"""Optional Git capability contracts, using only disposable workspaces."""
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import project_portal  # Adds the packaged core modules to sys.path.
from git_integration import cached_read_projection, decode_snapshot, repository
from version_control import (capture_work, common_directory, inspect_workspace,
                             source_revision, workspace_status)
from hub_core import resolve_project


class OptionalVersionControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'workspace'
        self.root.mkdir()

    def test_plain_folder_and_other_vcs_marker_need_no_git_process(self):
        (self.root / '.svn').mkdir()
        with patch('subprocess.run', side_effect=AssertionError('Git is optional')):
            self.assertEqual(workspace_status(None)['status'], 'workspace_required')
            self.assertEqual(inspect_workspace(self.root)['status'], 'no_repository')
            self.assertIsNone(common_directory(self.root))
            self.assertIsNone(source_revision(self.root))
            self.assertEqual(capture_work(self.root, ['file.txt'])['reasonCode'], 'no_repository')
            self.assertEqual(capture_work(self.root, ['file.txt'], 'read')['reasonCode'], 'source_write_not_requested')
            self.assertFalse(repository(self.root)['available'])
            self.assertEqual(cached_read_projection(self.root)[1], [])

    def test_missing_workspace_does_not_masquerade_as_missing_repository(self):
        self.assertEqual(inspect_workspace(self.root / 'missing')['status'], 'workspace_unavailable')

    def test_missing_client_keeps_detected_repository_and_core_routing(self):
        (self.root / '.git').mkdir()
        projects = [dict(id='project', codex_id='native', present=True, roots=[str(self.root)])]
        with patch('version_control.shutil.which', return_value=None), \
                patch('subprocess.run', side_effect=AssertionError('No Git executable')):
            info = inspect_workspace(self.root)
            self.assertEqual(info['provider'], 'git')
            self.assertEqual(info['status'], 'client_unavailable')
            self.assertEqual(info['operations'], [])
            self.assertEqual(resolve_project(projects, self.root)[0]['id'], 'project')
            self.assertFalse(capture_work(self.root, ['file.txt'])['available'])

    @unittest.skipUnless(shutil.which('git'), 'Git is needed for its provider contracts')
    def test_real_repository_subfolder_and_read_work(self):
        subprocess.run(['git', '-C', str(self.root), 'init', '-q'], check=True, capture_output=True)
        nested = self.root / 'src'
        nested.mkdir()
        state = inspect_workspace(nested)
        self.assertTrue(state['available'])
        self.assertEqual(state['status'], 'ready')
        self.assertEqual(Path(state['repositoryRoot']), self.root)
        self.assertIn('checkpoint', state['operations'])
        with patch('subprocess.run', side_effect=AssertionError('Read work must not scan Git')):
            self.assertFalse(capture_work(nested, ['file.py'], 'read')['available'])
            self.assertFalse(capture_work(nested, ['resource:catalog'], 'write')['available'])
        self.assertTrue(capture_work(nested, ['file.py'])['available'])

    def test_git_failure_and_timeout_are_explicit_but_not_core_failures(self):
        (self.root / '.git').write_text('gitdir: missing')
        with patch('version_control.shutil.which', return_value='git'):
            for error, expected in ((FileNotFoundError(), 'client_unavailable'),
                                    (subprocess.TimeoutExpired(['git'], 3), 'repository_unavailable')):
                with self.subTest(error=error), patch('subprocess.run', side_effect=error):
                    info = inspect_workspace(self.root)
                    self.assertFalse(info['available'])
                    self.assertEqual(info['status'], expected)
                    self.assertIsNone(source_revision(self.root))
                    self.assertFalse(capture_work(self.root, ['file.py'])['available'])


if __name__ == '__main__':
    unittest.main()
