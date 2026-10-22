"""Program replacement and recovery never consume real installation data."""
from contextlib import redirect_stderr
import io
import json
import os
from pathlib import Path, PureWindowsPath
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hub_update as update
import hub_launcher as launcher
import hub_lifecycle as lifecycle


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hub-maintenance-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.app = self.base / 'program'
        self.config = self.base / 'settings/installation.json'
        self.data = self.base / 'storage'
        self.data.mkdir()
        (self.data / 'knowledge.txt').write_text('user data', encoding='utf-8')
        self.private = self.config.parent / 'private/key.bin'
        self.private.parent.mkdir(parents=True)
        self.private.write_bytes(b'private key fixture')
        launcher.configure(self.config, data_home=self.data, language='ru', port=18888, application_home=self.app)
        self.before = self.config.read_bytes()

    def program(self, value='old'):
        for name in ('runtime/python.exe', 'app/scripts/hub_launcher.py', 'app/scripts/agent_api.py', 'app/scripts/mcp_transport.py', 'project-hub.cmd'):
            path = self.app / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding='utf-8')

    def preserved(self):
        self.assertEqual(self.before, self.config.read_bytes())
        self.assertEqual(b'private key fixture', self.private.read_bytes())
        self.assertEqual('user data', (self.data / 'knowledge.txt').read_text())

    def test_success_and_reinstall_keep_external_settings_and_previous_program(self):
        self.program()
        with patch.object(update, 'stop_hub'):
            row = update.prepare(self.app, self.config)
        self.program('new')
        with patch.object(update, 'verify_and_start') as start:
            result = update.finish(self.app, self.config, language='en')
        self.assertEqual('committed', result['status'])
        start.assert_called_once_with(self.app, self.config)
        prior = self.config.parent / 'updates' / row['id'] / 'previous/project-hub.cmd'
        self.assertEqual('old', prior.read_text())
        self.preserved()
        with patch.object(update, 'stop_hub'):
            self.assertEqual('prepared', update.prepare(self.app, self.config)['status'])

    def test_foreign_source_main_defers_launch_and_never_opens_installed_storage(self):
        self.program()
        current = dict(config=str(self.base/'source/config.json'),
                       applicationHome=str(self.base/'source/app'),dataHome=str(self.base/'source/data'),port=19542)
        with patch('hub_instance.active',return_value=current), patch.object(update.subprocess,'run') as run, \
             patch.object(update,'health') as health, patch.object(update,'stop_hub') as stop:
            self.assertFalse(update.verify_and_start(self.app,self.config))
        self.assertEqual(run.call_count,1)
        self.assertIn('-c',run.call_args.args[0])
        self.assertNotIn('--open',run.call_args.args[0])
        health.assert_not_called(); stop.assert_not_called()
        self.preserved()

    def test_finish_records_deferred_launch_as_successful_installation(self):
        self.program()
        with patch.object(update,'stop_hub'):
            update.prepare(self.app,self.config)
        self.program('new')
        with patch.object(update,'verify_and_start',return_value=False):
            result=update.finish(self.app,self.config)
        self.assertEqual(result['status'],'committed')
        self.assertTrue(result['launchDeferred'])
        self.preserved()

    def test_failed_new_runtime_restores_only_program_and_http_runtime(self):
        self.program()
        with patch.object(update, 'stop_hub'):
            update.prepare(self.app, self.config)
        self.program('new')
        (self.app / 'app/new-file.py').write_text('new')
        (self.app / 'unins000.exe').write_text('Inno-owned')
        with patch.object(update, 'stop_hub'), patch.object(update, 'verify_and_start', side_effect=[ValueError('unhealthy'), None]) as start:
            with self.assertRaisesRegex(ValueError, 'Previous program restored'):
                update.finish(self.app, self.config)
        self.assertEqual(2, start.call_count)
        self.assertEqual('old', (self.app / 'app/scripts/agent_api.py').read_text())
        self.assertEqual('old', (self.app / 'app/scripts/mcp_transport.py').read_text())
        self.assertFalse((self.app / 'app/new-file.py').exists())
        self.assertEqual('Inno-owned', (self.app / 'unins000.exe').read_text())
        self.preserved()

    def test_tampered_prior_and_config_rejected_without_removal(self):
        self.program()
        with patch.object(update, 'stop_hub'):
            row = update.prepare(self.app, self.config)
        prior = self.config.parent / 'updates' / row['id'] / 'previous/project-hub.cmd'
        prior.write_text('corrupt')
        self.program('new')
        with self.assertRaisesRegex(ValueError, 'failed verification'):
            update.rollback(self.app, self.config)
        self.assertEqual('new', (self.app / 'project-hub.cmd').read_text())
        self.preserved()

    def test_interrupted_update_recovers_and_old_receipt_cannot_undo_commit(self):
        self.program()
        with patch.object(update, 'stop_hub'), patch.object(update, 'verify_and_start'):
            update.prepare(self.app, self.config)
            self.assertEqual('prepared', update.prepare(self.app, self.config)['status'])
        self.program('new')
        with patch.object(update, 'stop_hub'), patch.object(update, 'verify_and_start'):
            update.rollback(self.app, self.config)
            update.prepare(self.app, self.config)
            update.finish(self.app, self.config)
        with self.assertRaisesRegex(ValueError, 'committed'):
            update.rollback(self.app, self.config)
        self.preserved()

    def test_prepare_failure_restarts_unchanged_program_and_retry_recovers(self):
        self.program()
        with patch.object(update, 'stop_hub'), patch.object(update.shutil, 'copytree', side_effect=OSError('copy failed')), \
                patch.object(update, 'verify_and_start') as restart:
            with self.assertRaisesRegex(OSError, 'copy failed'):
                update.prepare(self.app, self.config)
            restart.assert_called_once_with(self.app, self.config)
        self.assertEqual('old', (self.app / 'project-hub.cmd').read_text())
        with patch.object(update, 'stop_hub'), patch.object(update, 'verify_and_start'):
            self.assertEqual('prepared', update.prepare(self.app, self.config)['status'])
        self.preserved()

    def test_receipt_write_failure_restarts_unchanged_program(self):
        self.program()
        with patch.object(update, 'stop_hub'), patch.object(update, 'atomic_json', side_effect=OSError('disk full')), \
                patch.object(update, 'verify_and_start') as restart:
            with self.assertRaisesRegex(OSError, 'disk full'):
                update.prepare(self.app, self.config)
            restart.assert_called_once_with(self.app, self.config)
        self.assertEqual('old', (self.app / 'project-hub.cmd').read_text())
        self.preserved()

    def test_failed_first_install_can_be_repaired_without_losing_data(self):
        with patch.object(update, 'stop_hub'):
            update.prepare(self.app, self.config)
        self.program('first')
        with patch.object(update, 'stop_hub'), patch.object(update, 'verify_and_start', side_effect=ValueError('unhealthy')):
            with self.assertRaisesRegex(ValueError, 'Repair the first installation'):
                update.finish(self.app, self.config)
        with patch.object(update, 'stop_hub'), patch.object(update, 'verify_and_start'):
            self.assertFalse(update.prepare(self.app, self.config)['installed'])
            self.assertEqual('committed', update.finish(self.app, self.config)['status'])
        self.preserved()

    def test_unrecognized_destination_and_data_in_program_refused(self):
        (self.app / 'app').mkdir(parents=True)
        (self.app / 'app/user.txt').write_text('not a Hub installation')
        with self.assertRaisesRegex(ValueError, 'unrecognized'):
            update.prepare(self.app, self.config)
        self.assertEqual('not a Hub installation', (self.app / 'app/user.txt').read_text())
        with self.assertRaisesRegex(ValueError, 'outside'):
            update.paths(self.app, self.app / 'installation.json')

    def test_drive_children_and_unicode_paths_are_valid_application_directories(self):
        for value in ('D:/ProjectHub', 'D:/Hub folder/Программа', '//server/share/ProjectHub'):
            app = PureWindowsPath(value)
            with self.subTest(value=value), \
                    patch.object(update, 'checked_path', return_value=app), \
                    patch.object(update, 'external_path', return_value=self.config):
                self.assertEqual((app, self.config, self.config.parent / 'updates/current.json'),
                                 update.paths(app, self.config))

    @unittest.skipUnless(os.name == 'nt', 'Windows directory preflight')
    def test_drive_child_preflight_does_not_create_or_write_the_directory(self):
        app = Path(self.base.anchor) / ('Hub папка ' + self.base.name)
        self.assertFalse(app.exists())
        self.assertEqual(0, update.main(['check-destination', '--app', str(app), '--config', str(self.config)]))
        self.assertFalse(app.exists())
        self.preserved()

    def test_drive_and_share_roots_are_rejected_before_configuration_or_shutdown(self):
        for app in (Path(self.base.anchor), PureWindowsPath('D:/'), PureWindowsPath('//server/share/')):
            with self.subTest(app=str(app)), patch.object(update, 'checked_path', return_value=app), \
                    patch.object(update, 'external_path') as config, patch.object(update, 'stop_hub') as stop:
                with self.assertRaisesRegex(update.LauncherError, 'dedicated application directory'):
                    update.paths(app, self.config)
                config.assert_not_called()
                stop.assert_not_called()

    @unittest.skipUnless(os.name == 'nt', 'Windows system/profile directories')
    def test_system_and_profile_roots_remain_protected_but_dedicated_children_are_valid(self):
        protected = {key: str(self.base / key) for key in (
            'SystemRoot', 'WINDIR', 'ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432',
            'ProgramData', 'USERPROFILE', 'PUBLIC', 'LOCALAPPDATA', 'APPDATA')}
        protected['USERPROFILE'] = str(self.base / 'Users/person')
        with patch.dict(os.environ, protected):
            for value in (*protected.values(), str(self.base / 'Users')):
                with self.subTest(value=value):
                    with self.assertRaisesRegex(update.LauncherError, 'system or profile directory'):
                        update.paths(Path(value), self.config)
                    self.assertEqual(Path(value) / 'Hub', update.paths(Path(value) / 'Hub', self.config)[0])

    def test_relative_paths_and_reparse_points_are_still_rejected(self):
        with self.assertRaisesRegex(update.LauncherError, 'absolute paths'):
            update.paths(Path('relative-program'), self.config)
        attributes = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        with patch.object(Path, 'lstat', return_value=attributes):
            with self.assertRaisesRegex(update.LauncherError, 'links or reparse points'):
                update.paths(self.base, self.config)
        attributes = SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
        with patch.object(Path, 'lstat', return_value=attributes):
            with self.assertRaisesRegex(update.LauncherError, 'links or reparse points'):
                update.paths(self.base, self.config)

    def test_invalid_application_path_keeps_diagnostic_without_repeating_paths(self):
        with patch.object(update, 'paths', side_effect=update.LauncherError('Invalid application path')) as paths, \
                redirect_stderr(io.StringIO()) as output:
            self.assertEqual(1, update.main(['check-destination', '--app', str(self.app), '--config', str(self.config)]))
        paths.assert_called_once()
        self.assertIn('Invalid application path', output.getvalue())
        self.assertIn('Invalid application path', (self.config.parent / 'updates/last-error.txt').read_text())
        self.preserved()

    def test_rejected_drive_root_keeps_diagnostic_in_external_configuration(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(1, update.main(['check-destination', '--app', self.base.anchor, '--config', str(self.config)]))
        self.assertIn('dedicated application directory',
                      (self.config.parent / 'updates/last-error.txt').read_text())
        self.preserved()

    def test_permission_error_is_reported_even_when_persistent_log_is_unwritable(self):
        error = PermissionError(13, 'Access denied', str(self.app / 'Программа'))
        with patch.object(update, 'check_destination', side_effect=error), \
                patch.object(Path, 'write_text', side_effect=PermissionError('Log is unwritable')), \
                patch.object(update, 'stop_hub') as stop, redirect_stderr(io.StringIO()) as output:
            self.assertEqual(1, update.main(['check-destination', '--app', str(self.app), '--config', str(self.config)]))
        self.assertIn(str(error), output.getvalue())
        self.assertNotIn('Log is unwritable', output.getvalue())
        stop.assert_not_called()
        self.assertFalse(self.app.exists())
        self.preserved()

    def test_invalid_configuration_does_not_write_diagnostic_inside_application(self):
        config = self.app / 'installation.json'
        with redirect_stderr(io.StringIO()) as output:
            self.assertEqual(1, update.main(['check-destination', '--app', str(self.app), '--config', str(config)]))
        self.assertIn('outside the application', output.getvalue())
        self.assertFalse(self.app.exists())
        self.preserved()

    def test_reinstall_accepts_only_bytecode_remaining_after_uninstall(self):
        self.program()
        with patch.object(update, 'stop_hub'), patch.object(update, 'verify_and_start'):
            update.prepare(self.app, self.config)
            update.finish(self.app, self.config)
        update.shutil.rmtree(self.app)
        for relative in ('app/scripts/__pycache__/hub_launcher.cpython-313.pyc',
                         'runtime/Lib/site-packages/library/__pycache__/module.cpython-313.opt-2.pyc'):
            path = self.app / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'old cache')
        with patch.object(update, 'stop_hub'):
            row = update.prepare(self.app, self.config)
        self.assertEqual('prepared', row['status'])
        self.assertFalse(row['installed'])
        self.assertEqual(b'old cache', path.read_bytes())
        self.preserved()

    def test_noncache_files_are_preserved_and_block_first_install(self):
        for relative in ('notes.txt', 'app/scripts/__pycache__/user.txt',
                         'app/scripts/__pycache__/user.pyc'):
            with self.subTest(relative=relative):
                path = self.app / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'keep this file')
                with patch.object(update, 'stop_hub') as stop:
                    with self.assertRaises(update.DestinationNotEmpty):
                        update.prepare(self.app, self.config)
                stop.assert_not_called()
                self.assertEqual(b'keep this file', path.read_bytes())
                self.assertFalse((self.config.parent / 'updates/current.json').exists())
                path.unlink()
                self.preserved()

    def test_nonempty_destination_has_distinct_exit_code_and_diagnostic(self):
        path = self.app / 'notes.txt'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'keep this file')
        with patch.object(update, 'stop_hub') as stop, patch.object(update.sys, 'stderr'):
            result = update.main(['prepare', '--app', str(self.app), '--config', str(self.config)])
        self.assertEqual(3, result)
        stop.assert_not_called()
        self.assertIn('notes.txt', (self.config.parent / 'updates/last-error.txt').read_text())
        self.assertEqual(b'keep this file', path.read_bytes())
        self.preserved()

    def test_directory_preflight_checks_selected_path_without_preparing_or_stopping(self):
        path = self.app / 'notes.txt'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'keep this file')
        another = self.base / 'selected-program'
        with patch.object(update, 'stop_hub') as stop, patch.object(update, 'verify_and_start') as start, \
                patch.object(update.sys, 'stderr'):
            self.assertEqual(3, update.main(['check-destination', '--app', str(self.app), '--config', str(self.config)]))
            self.assertEqual(0, update.main(['check-destination', '--app', str(another), '--config', str(self.config)]))
        stop.assert_not_called()
        start.assert_not_called()
        self.assertFalse((self.config.parent / 'updates/current.json').exists())
        self.assertFalse(another.exists())
        self.assertEqual(b'keep this file', path.read_bytes())
        self.preserved()

    def test_directory_preflight_keeps_pending_recovery_unchanged(self):
        with patch.object(update, 'stop_hub'):
            row = update.prepare(self.app, self.config)
        (self.app / 'app').mkdir(parents=True)
        (self.app / 'app/partial.py').write_text('interrupted program')
        receipt = self.config.parent / 'updates/current.json'
        for status in ('prepared', 'restoring', 'preparing', 'preparation-failed', 'first-install-failed'):
            with self.subTest(status=status):
                lifecycle.atomic_json(receipt, {**row, 'status':status})
                before = receipt.read_bytes()
                with patch.object(update, 'stop_hub') as stop, patch.object(update, 'rollback') as rollback:
                    update.check_destination(self.app, self.config)
                stop.assert_not_called()
                rollback.assert_not_called()
                self.assertEqual(before, receipt.read_bytes())
                self.assertEqual('interrupted program', (self.app / 'app/partial.py').read_text())
                self.preserved()

    def test_another_directory_keeps_completed_program_and_external_data(self):
        self.program()
        with patch.object(update, 'stop_hub'):
            row = update.prepare(self.app, self.config)
        receipt = self.config.parent / 'updates/current.json'
        prior = receipt.parent / row['id'] / 'previous/project-hub.cmd'
        for status in ('committed', 'rolled-back', 'first-install-failed'):
            with self.subTest(status=status):
                lifecycle.atomic_json(receipt, {**row, 'status':status})
                another = self.base / ('another-' + status)
                with patch.object(update, 'stop_hub'):
                    result = update.prepare(another, self.config)
                self.assertEqual(str(another), result['application'])
                self.assertFalse(result['installed'])
                self.assertEqual('old', (self.app / 'project-hub.cmd').read_text())
                self.assertEqual('old', prior.read_text())
                self.preserved()

    def test_another_directory_cannot_discard_an_unfinished_update(self):
        self.program()
        with patch.object(update, 'stop_hub'):
            row = update.prepare(self.app, self.config)
        receipt = self.config.parent / 'updates/current.json'
        another = self.base / 'another-program'
        for status in ('prepared', 'preparing', 'preparation-failed', 'restoring'):
            with self.subTest(status=status):
                lifecycle.atomic_json(receipt, {**row, 'status':status})
                before = receipt.read_bytes()
                with patch.object(update, 'stop_hub') as stop:
                    with self.assertRaisesRegex(ValueError, 'does not belong'):
                        update.prepare(another, self.config)
                stop.assert_not_called()
                self.assertEqual(before, receipt.read_bytes())
                self.assertFalse(another.exists())
                self.assertEqual('old', (self.app / 'project-hub.cmd').read_text())
                self.preserved()

    def test_stop_verifies_exact_installed_owner_and_never_kills(self):
        self.program()
        lock = self.config.with_name('supervisor.lock')
        control = self.config.parent / ('lifecycle/runtime-' + 'a'*32)
        control.mkdir(parents=True)
        body = dict(service='project-hub', dataHome=str(self.data), supervised=True,
                    supervisorAlive=True, codeRoot=str(self.app / 'app'))
        with lifecycle.file_lock(lock), patch.object(launcher, 'health', return_value=body):
            with self.assertRaisesRegex(ValueError, 'still draining'):
                launcher.stop_hub(self.config, application_home=self.app / 'app', timeout=0)
        self.assertTrue((control / 'stop.json').is_file())
        with lifecycle.file_lock(lock), patch.object(launcher, 'health', return_value={**body, 'codeRoot':str(self.base / 'source')}):
            with self.assertRaisesRegex(ValueError, 'no process was stopped'):
                launcher.stop_hub(self.config, application_home=self.app / 'app', timeout=0)
        self.preserved()

    def test_recovery_refuses_its_own_runtime_before_replacing_files(self):
        self.program()
        with patch.object(update, 'stop_hub'):
            update.prepare(self.app, self.config)
        self.program('new')
        with patch.object(update.sys, 'executable', str(self.app / 'runtime/python.exe')):
            with self.assertRaisesRegex(ValueError, 'outside the application'):
                update.rollback(self.app, self.config)
        self.assertEqual('new', (self.app / 'app/scripts/hub_launcher.py').read_text())
        self.preserved()

    def test_runtime_restore_skips_identical_loaded_files(self):
        old = self.base / 'prior/runtime'; old.mkdir(parents=True)
        new = self.app / 'runtime'; new.mkdir(parents=True)
        for directory in (old, new):
            (directory / 'python.exe').write_bytes(b'same binary')
        (old / 'library.py').write_text('prior')
        (new / 'library.py').write_text('new')
        (new / 'new.py').write_text('new file')
        original = update.shutil.copy2
        def guarded_copy(source, destination):
            self.assertNotEqual('python.exe', Path(destination).name)
            return original(source, destination)
        with patch.object(update.shutil, 'copy2', side_effect=guarded_copy):
            update.restore_runtime(old, new)
        self.assertEqual(update.inventory(old), update.inventory(new))


if __name__ == '__main__':
    unittest.main()
