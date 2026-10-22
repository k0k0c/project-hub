"""Source and installed work launches share settings; development stays isolated."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hub_launcher as launcher
import hub_source as source


class SourceModeTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hub-source-mode-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.base = self.root / 'user'
        self.app = self.root / 'checkout'
        for target, attribute, value in ((source, 'APPLICATION_HOME', self.app),
                                         (source, 'default_base', lambda: self.base),
                                         (launcher, 'default_base', lambda: self.base)):
            replacement = patch.object(target, attribute, value)
            replacement.start(); self.addCleanup(replacement.stop)
        environment = patch.dict(os.environ, PROJECT_HUB_INSTANCE_HOME=str(self.root / 'runtime'))
        environment.start(); self.addCleanup(environment.stop)

    def run_source(self, arguments):
        with patch.object(source, 'launch', side_effect=launcher.main), \
             patch.object(launcher, 'source_desktop_controller_required', return_value=False), \
             patch.object(launcher, 'open_hub', return_value='http://127.0.0.1:19876') as opened, \
             patch.object(launcher, 'report_error') as error, patch.object(sys, 'stdout', io.StringIO()):
            result = source.main(arguments)
        return result, opened, error

    def test_default_work_launch_reads_installed_preferences_without_overwriting_them(self):
        config = self.base / 'installation.json'
        home = self.root / 'working-data'
        launcher.configure(data_home=home, port=19876, language='en')
        before = config.read_bytes()
        result, opened, error = self.run_source(['--data-home', str(self.root / 'unused'), '--no-browser'])
        self.assertEqual(0, result)
        error.assert_not_called()
        self.assertEqual(before, config.read_bytes())
        opened.assert_called_once_with(config, browser=False, development=False, switch=False, source=True)
        self.assertFalse((self.root / 'unused').exists())
        self.assertEqual(config, source.default_config('work'))

    def test_development_default_is_a_separate_persistent_profile(self):
        working = self.base / 'installation.json'
        launcher.configure(data_home=self.root / 'working-data')
        before = working.read_bytes()
        result, opened, error = self.run_source(['--mode', 'development', '--no-browser'])
        self.assertEqual(0, result)
        error.assert_not_called()
        config = source.default_config('development')
        self.assertTrue(config.is_relative_to(self.base / 'development' / 'sources'))
        self.assertEqual(str(config.parent / 'data'), json.loads(config.read_text(encoding='utf-8'))['dataHome'])
        opened.assert_called_once_with(config, browser=False, development=True, switch=False, source=True)
        profile_before = config.read_bytes()
        self.assertEqual(0, self.run_source(['--development', '--port', '19777'])[0])
        self.assertEqual(profile_before, config.read_bytes())
        self.assertEqual(before, working.read_bytes())

    def test_development_profiles_follow_checkout_while_work_config_is_common(self):
        work = source.default_config('work'); development = source.default_config('development')
        with patch.object(source, 'APPLICATION_HOME', self.root / 'other-checkout'):
            self.assertEqual(work, source.default_config('work'))
            self.assertNotEqual(development, source.default_config('development'))

    def test_development_refuses_working_home_even_when_work_server_is_stopped(self):
        home = self.root / 'working-data'
        launcher.configure(data_home=home)
        before = (self.base / 'installation.json').read_bytes()
        result, opened, error = self.run_source(['--mode', 'development', '--data-home', str(home)])
        self.assertEqual(1, result)
        opened.assert_not_called()
        self.assertIn('primary home', str(error.call_args.args[0]))
        self.assertEqual(before, (self.base / 'installation.json').read_bytes())
        self.assertFalse(home.exists())

    def test_source_work_configuration_is_protected_before_server_start(self):
        home = self.root / 'custom-working-data'
        config = self.root / 'custom-work/installation.json'
        self.assertEqual(0, launcher.main(['--source', '--mode', 'work', '--configure',
                                          '--config', str(config), '--data-home', str(home)]))
        result, opened, error = self.run_source(['--mode', 'development', '--data-home', str(home)])
        self.assertEqual(1, result)
        opened.assert_not_called()
        self.assertIn('primary home', str(error.call_args.args[0]))
        self.assertFalse(home.exists())

    def test_stop_preserves_selected_mode_and_does_not_configure_or_open(self):
        for mode in ('work', 'development'):
            with self.subTest(mode=mode), patch.object(source, 'launch', return_value=0) as launch:
                self.assertEqual(0, source.main(['--mode', mode, '--stop']))
                launch.assert_called_once_with(['--config', str(source.default_config(mode)),
                                                '--source', '--mode', mode, '--stop'])

    def test_development_stop_cannot_stop_working_configuration(self):
        launcher.configure(data_home=self.root / 'working-data')
        with patch.object(launcher, 'stop_hub') as stopped:
            result, opened, error = self.run_source(['--mode', 'development', '--stop',
                                                   '--config', str(self.base / 'installation.json')])
        self.assertEqual(1, result)
        stopped.assert_not_called(); opened.assert_not_called()
        self.assertIn('own configuration', str(error.call_args.args[0]))

    def test_development_cannot_switch_main_runtime(self):
        with patch.object(sys, 'stderr', io.StringIO()), patch.object(source, 'launch') as launch:
            with self.assertRaises(SystemExit):
                source.main(['--mode', 'development', '--switch'])
        launch.assert_not_called()

    def test_common_launcher_requires_explicit_development_configuration(self):
        with patch.object(launcher, 'report_error') as error, patch.object(launcher, 'configure') as configure:
            self.assertEqual(1, launcher.main(['--mode', 'development', '--configure']))
        configure.assert_not_called()
        self.assertIn('explicit external --config', str(error.call_args.args[0]))


class WindowedSourceTest(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt' and Path(sys.executable).with_name('pythonw.exe').is_file(), 'Windows Pythonw is required')
    def test_windowed_source_spawn_workers_start_with_file_diagnostics(self):
        import ctypes
        from ctypes import wintypes
        import socket
        import subprocess
        import time
        app=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix='hub-windowed-source-') as temporary:
            root=Path(temporary);config=root/'installation.json'
            with socket.socket() as listener:
                listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
            environment=os.environ.copy()
            environment['PROJECT_HUB_INSTANCE_HOME']=str(root/'instances')
            # The launcher must remove this inherited flag for Windows spawn.
            environment['PYTHONFAULTHANDLER']='1'
            windowed=str(Path(sys.executable).with_name('pythonw.exe'))
            command=[windowed,'-B',str(app/'scripts/hub_source.py'),'--mode','development',
                     '--config',str(config),'--data-home',str(root/'data'),'--port',str(port),'--no-browser']
            # A disposable caller is placed in a kill-on-close job which does
            # NOT permit breakaway, just like an enclosing application job.
            class Basic(ctypes.Structure):
                _fields_=[('processTime',ctypes.c_int64),('jobTime',ctypes.c_int64),('flags',wintypes.DWORD),
                          ('minimum',ctypes.c_size_t),('maximum',ctypes.c_size_t),('active',wintypes.DWORD),
                          ('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
            class Extended(ctypes.Structure):
                _fields_=[('basic',Basic),('io',ctypes.c_uint64*6),('processMemory',ctypes.c_size_t),
                          ('jobMemory',ctypes.c_size_t),('peakProcessMemory',ctypes.c_size_t),('peakJobMemory',ctypes.c_size_t)]
            kernel=ctypes.WinDLL('kernel32',use_last_error=True)
            kernel.CreateJobObjectW.restype=wintypes.HANDLE
            kernel.SetInformationJobObject.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
            kernel.AssignProcessToJobObject.argtypes=[wintypes.HANDLE,wintypes.HANDLE]
            kernel.CloseHandle.argtypes=[wintypes.HANDLE]
            job=kernel.CreateJobObjectW(None,None)
            limits=Extended();limits.basic.flags=0x2000
            self.assertTrue(kernel.SetInformationJobObject(job,9,ctypes.byref(limits),ctypes.sizeof(limits)))
            wrapper=root/'caller.py';done=root/'done.json';go=root/'go'
            wrapper.write_text('import json,pathlib,subprocess,time\n'
                f'go=pathlib.Path({str(go)!r})\n'
                'while not go.exists():time.sleep(.01)\n'
                f'p=subprocess.run({command!r},stdout=subprocess.PIPE,stderr=subprocess.STDOUT)\n'
                f'pathlib.Path({str(done)!r}).write_text(json.dumps(dict(code=p.returncode,output=p.stdout.decode(errors="replace"))))\n'
                'time.sleep(120)\n',encoding='utf-8')
            caller=None
            try:
                caller=subprocess.Popen([windowed,'-B',str(wrapper)],env=environment,
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                self.assertTrue(kernel.AssignProcessToJobObject(job,int(caller._handle)),ctypes.get_last_error())
                go.touch()
                deadline=time.monotonic()+40
                while not done.exists() and time.monotonic()<deadline:time.sleep(.1)
                diagnostic=root/'diagnostics'
                self.assertTrue(done.exists(), 'Source caller did not finish; '+ '\n'.join(p.read_text(encoding='utf-8') for p in diagnostic.glob('*.jsonl')))
                result=json.loads(done.read_text())
                self.assertEqual(result['code'],0,result['output']+'\n'+ '\n'.join(p.read_text(encoding='utf-8') for p in diagnostic.glob('*.jsonl')))
                body=launcher.health(port)
                self.assertTrue(launcher.matches_home(body,root/'data'),body)
                self.assertTrue(body['supervisorAlive'])
                lifetime=json.loads((root/'supervisor-lifetime.json').read_text())
                self.assertFalse(lifetime['process']['windowsJob'].get('killOnClose',False),lifetime)
                pid=body['pid']
                kernel.CloseHandle(job);job=None
                caller.wait(timeout=5)
                time.sleep(.3)
                after=launcher.health(port)
                self.assertIsNotNone(after, 'Source server died with its caller job')
                self.assertEqual(pid,after['pid'])
                self.assertTrue(after['supervisorAlive'])
                contexts=[json.loads(p.read_text(encoding='utf-8')) for p in diagnostic.glob('request-worker-*-context.json')]
                if body['transport']=='asgi':
                    self.assertTrue(contexts)
                else:
                    self.assertTrue(list(diagnostic.glob('server-*-context.json')))
                self.assertTrue(all(p['component']=='request-worker' for p in contexts))
            finally:
                if job:kernel.CloseHandle(job)
                if caller is not None and caller.poll() is None:
                    caller.terminate();caller.wait(timeout=5)
                subprocess.run([sys.executable,'-B',str(app/'scripts/hub_source.py'),'--mode','development',
                                '--config',str(config),'--stop'],env=environment,timeout=75,
                               stdout=subprocess.PIPE,stderr=subprocess.PIPE)


if __name__ == '__main__':
    unittest.main()
