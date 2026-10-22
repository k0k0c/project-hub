"""Desktop delegation and source-supervisor identity contracts."""
import json
import itertools
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hub_launcher as launcher
import windows_desktop as desktop


class DesktopLaunchTest(unittest.TestCase):
    def test_missing_or_dead_controller_fails_before_the_general_operation_timeout(self):
        for dead in (False,True):
            with self.subTest(dead=dead), tempfile.TemporaryDirectory(prefix='hub-source-control-test-') as directory:
                root=Path(directory)
                def dispatch(argv,cwd):
                    if dead:
                        (root/'started.json').write_text('{"pid":1234}',encoding='utf-8')
                with patch.object(desktop, 'os', SimpleNamespace(name='nt')), \
                        patch('runtime_diagnostics.process_context',return_value={'restrictedToken':False}), \
                        patch('runtime_diagnostics._process_alive',return_value=False), \
                        patch.object(desktop, 'physical_directory',return_value=root), \
                        patch.object(Path,'is_file',return_value=True), \
                        patch.object(desktop,'launch',side_effect=dispatch), \
                        patch.object(desktop.time,'sleep'), \
                        patch.object(desktop.time,'monotonic',side_effect=itertools.count()):
                    with self.assertRaisesRegex(desktop.DesktopLaunchError,'exited before' if dead else 'did not start'):
                        desktop.run_controller(['--source','--stop'],root/'instances')

    def test_source_controller_uses_shared_physical_receipt_without_parent_appdata_writes(self):
        with tempfile.TemporaryDirectory(prefix='hub-source-control-test-') as directory:
            root = Path(directory)
            def dispatch(argv, cwd):
                receipt = Path(argv[argv.index('--desktop-entry')+1])
                self.assertEqual(root/'result.json', receipt)
                self.assertEqual(Path(desktop.__file__).resolve().parent, cwd)
                receipt.write_text(json.dumps(dict(exitCode=0, url='http://127.0.0.1:8769')), encoding='utf-8')
            with patch.object(desktop, 'os', SimpleNamespace(name='nt')), \
                    patch('runtime_diagnostics.process_context', return_value={'restrictedToken':False}), \
                    patch.object(desktop, 'physical_directory', return_value=root), \
                    patch.object(Path, 'is_file', return_value=True), \
                    patch.object(desktop, 'launch', side_effect=dispatch) as launch:
                result = desktop.run_controller(['--source','--stop','--config','C:/Data/config.json'], root/'instances')
            self.assertEqual(0, result['exitCode'])
            argv=launch.call_args.args[0]
            self.assertEqual(['--source','--stop','--config','C:/Data/config.json'],argv[3:7])
            self.assertEqual(str(root/'instances'), argv[-1])

    def test_restricted_unknown_and_non_windows_callers_are_not_delegated(self):
        for platform, restricted in [('nt', True), ('nt', None), ('posix', False)]:
            with self.subTest(platform=platform, restricted=restricted), \
                    patch.object(desktop, 'os', SimpleNamespace(name=platform)), \
                    patch('runtime_diagnostics.process_context', return_value={'restrictedToken': restricted}), \
                    patch.object(desktop.subprocess, 'run') as run:
                with self.assertRaises(desktop.DesktopLaunchError):
                    desktop.launch(['pythonw.exe'], '.')
                run.assert_not_called()

    def test_bounded_helper_preserves_argument_boundaries_and_desktop_identity(self):
        command = ['C:/Source Python/pythonw.exe', '-B', 'C:/Source Hub/launcher.py', '--config', 'C:/User Data/a.json']
        with patch.object(desktop, 'os', SimpleNamespace(name='nt')), \
                patch('runtime_diagnostics.process_context', return_value={'restrictedToken': False}), \
                patch.object(desktop.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=b'{"desktopPid":42}')) as run:
            self.assertEqual({'desktopPid': 42}, desktop.launch(command, 'C:/User Data'))
        self.assertEqual(command, run.call_args.args[0][-len(command):])
        self.assertEqual('C:/User Data', run.call_args.args[0][-len(command)-1])
        self.assertEqual(15, run.call_args.kwargs['timeout'])
        self.assertNotIn('shell', run.call_args.kwargs)

    def test_helper_failure_timeout_and_invalid_confirmation_are_distinct_failures(self):
        for result in [SimpleNamespace(returncode=1, stderr=b'COM error'),
                       SimpleNamespace(returncode=0, stdout=b'not json'),
                       SimpleNamespace(returncode=0, stdout=b'{"desktopPid":true}'),
                       SimpleNamespace(returncode=0, stdout=b'[]'),
                       subprocess.TimeoutExpired(['helper'], 15)]:
            with self.subTest(result=result), patch.object(desktop, 'os', SimpleNamespace(name='nt')), \
                    patch('runtime_diagnostics.process_context', return_value={'restrictedToken': False}), \
                    patch.object(desktop.subprocess, 'run') as run:
                if isinstance(result, Exception):
                    run.side_effect = result
                else:
                    run.return_value = result
                with self.assertRaises(desktop.DesktopLaunchError):
                    desktop.launch(['pythonw.exe'], '.')

    def test_windowed_caller_uses_console_helper_with_hidden_window_and_real_pipes(self):
        with patch.object(desktop, 'os', SimpleNamespace(name='nt')), \
                patch('runtime_diagnostics.process_context', return_value={'restrictedToken': False}), \
                patch.object(desktop.sys, 'executable', 'C:/Python/pythonw.exe'), \
                patch.object(desktop.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout=b'{"desktopPid":42}')) as run:
            desktop.launch(['C:/Python/pythonw.exe'], 'C:/Data')
        self.assertEqual(str(Path('C:/Python/python.exe')), run.call_args.args[0][0])
        self.assertEqual(subprocess.PIPE, run.call_args.kwargs['stdout'])


class SupervisorReceiptTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='hub-desktop-receipt-')
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / 'receipt.json'
        self.context = dict(pid=1234, parentPid=42, restrictedToken=False,
                            windowsJob=dict(member=True, killOnClose=False))

    def write(self, context, state='started'):
        self.path.write_text(json.dumps(dict(process=context, state=state)), encoding='utf-8')

    def test_missing_receipt_is_pending_and_valid_receipt_follows_actual_pid(self):
        process = launcher.DesktopSupervisor(self.path, 42)
        self.assertIsNone(process.poll())
        self.assertIsNone(process.pid)
        self.write(self.context)
        with patch('runtime_diagnostics._process_alive', return_value=True) as alive:
            self.assertIsNone(process.poll())
            alive.assert_called_once_with(1234)
        with patch('runtime_diagnostics._process_alive', return_value=False):
            self.assertEqual(1, process.poll())

    def test_failed_coupled_restricted_unknown_or_different_parent_is_rejected(self):
        cases = [dict(self.context, parentPid=99), dict(self.context, restrictedToken=True),
                 dict(self.context, restrictedToken=None), dict(self.context, pid=True),
                 dict(self.context, windowsJob={'member':True, 'killOnClose':True}),
                 dict(self.context, windowsJob={})]
        for context in cases:
            with self.subTest(context=context):
                self.write(context)
                with self.assertRaises(launcher.LauncherError):
                    launcher.DesktopSupervisor(self.path, 42).poll()
        self.write(self.context, state='failed')
        with self.assertRaises(launcher.LauncherError):
            launcher.DesktopSupervisor(self.path, 42).poll()

    def test_existing_owner_normal_exit_is_preserved_after_initial_receipt(self):
        process = launcher.DesktopSupervisor(self.path, 42)
        self.write(self.context)
        with patch('runtime_diagnostics._process_alive', return_value=True):
            self.assertIsNone(process.poll())
        for code in (0, 1):
            self.path.write_text(json.dumps(dict(state='exited', exitCode=code, process=self.context)), encoding='utf-8')
            with patch('runtime_diagnostics._process_alive', return_value=False):
                self.assertEqual(code, process.poll())

    def test_source_broker_uses_owned_pythonw_and_explicit_runtime_configuration(self):
        config = self.path.with_name('installation.json')
        command = [str(Path(sys.executable)), '-B', str(self.path.with_name('hub_launcher.py')), '--supervise', '--config', str(config)]
        with patch.object(launcher, 'os', SimpleNamespace(name='nt')), \
                patch.object(Path, 'is_file', return_value=True), \
                patch('hub_instance.directory', return_value=self.path.parent / 'instances'), \
                patch.object(desktop, 'launch', return_value={'desktopPid':42}) as launch, \
                patch.object(launcher.subprocess, 'Popen') as popen:
            process = launcher.start_supervisor(command, config, {'PRIVATE_PARENT_VALUE':'not-forwarded'}, source=True, development=True)
        popen.assert_not_called()
        argv = launch.call_args.args[0]
        self.assertEqual(str(Path(sys.executable).with_name('pythonw.exe')), argv[0])
        self.assertEqual(command[1:], argv[1:len(command)])
        self.assertEqual(['--source', '--mode', 'development'], argv[len(command):len(command)+3])
        self.assertEqual(str(self.path.parent/'instances'), argv[-1])
        self.assertEqual(config.parent, launch.call_args.args[1])
        self.assertIsInstance(process, launcher.DesktopSupervisor)
        self.assertEqual(42, process.desktop_pid)


if __name__ == '__main__':
    unittest.main()
