"""Native folder adapter boundaries and exact argv; no real desktop launches."""
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_files


class LocalFilesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hub-local-files-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.registry = types.SimpleNamespace(home=self.root / 'data')
        self.registry.home.mkdir()
        self.program = self.root / 'program'; self.program.mkdir()

    def test_rejects_arbitrary_open_path_and_relative_input(self):
        with self.assertRaises(local_files.LocalFileError):
            local_files.execute(self.registry, {'action': 'open-folder', 'kind': 'data', 'path': str(self.program)}, application_home=self.program)
        with self.assertRaises(local_files.LocalFileError):
            local_files.local_path('relative/path')
        with self.assertRaises(local_files.LocalFileError):
            local_files.execute(self.registry, {'action': 'open-folder', 'kind': 'data', 'command': 'anything'}, application_home=self.program)

    def test_picker_returns_server_path_and_cancel_without_upload(self):
        with patch.object(local_files, 'choose_folder', return_value=str(self.root)):
            result = local_files.execute(self.registry, {'action': 'choose-folder', 'kind': 'import'}, application_home=self.program)
        self.assertEqual(result, {'path': str(self.root), 'cancelled': False})
        with patch.object(local_files, 'choose_folder', return_value=None):
            self.assertTrue(local_files.execute(self.registry, {'action': 'choose-folder', 'kind': 'data'}, application_home=self.program)['cancelled'])

    def test_revealing_archive_never_executes_the_file(self):
        backups = self.root / 'data-backups'; backups.mkdir()
        archive = backups / 'example.zip'; archive.write_bytes(b'example')
        with patch.object(local_files, 'open_folder', return_value={'opened': True}) as opened:
            local_files.execute(self.registry, {'action': 'open-folder', 'kind': 'backups', 'path': str(archive), 'reveal': True}, application_home=self.program)
        opened.assert_called_once_with(archive, reveal=True)
        with self.assertRaises(local_files.LocalFileError):
            local_files.open_folder(archive)

    def test_macos_reveal_uses_finder_argv_without_shell(self):
        archive = self.root / 'example $(never-run).zip'; archive.write_bytes(b'x')
        with patch.object(local_files.os, 'name', 'posix'), patch.object(local_files.sys, 'platform', 'darwin'), \
             patch.object(local_files, '_run', return_value=types.SimpleNamespace(returncode=0)) as run:
            # Preserve the platform's concrete Path class while testing the adapter.
            with patch.object(local_files, 'local_path', return_value=archive):
                local_files.open_folder(str(archive), reveal=True)
        run.assert_called_once_with(['/usr/bin/open', '-R', str(archive)])


if __name__ == '__main__':
    unittest.main()
