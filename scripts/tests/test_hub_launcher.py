import importlib.util
import io
import itertools
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


SOURCE = Path(__file__).resolve().parents[1] / 'hub_launcher.py'
SPEC = importlib.util.spec_from_file_location('hub_launcher', SOURCE)
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hub-launcher-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.app = self.base / 'application'
        (self.app / 'scripts').mkdir(parents=True)
        (self.app / 'scripts/project_portal.py').write_text('# mock installed portal\n', encoding='utf-8')
        (self.app / 'scripts/hub_launcher.py').write_text('# mock installed supervisor\n', encoding='utf-8')
        self.config = self.base / 'user/installation.json'
        self.home = self.base / 'user/data'
        isolated = patch.dict(os.environ, {'PROJECT_HUB_INSTANCE_HOME':str(self.base / 'main-runtime')})
        isolated.start(); self.addCleanup(isolated.stop)

    def configure(self, **kwargs):
        return launcher.configure(self.config, application_home=self.app, **kwargs)

    def open(self, **kwargs):
        return launcher.open_hub(self.config, application_home=self.app, **kwargs)

    def healthy(self, home=None):
        return dict(service='project-hub', dataHome=str(home or self.home), multiProject=True,
                    codeRoot=str(self.app), supervised=True, supervisorAlive=True)

    def test_first_configuration_and_existing_choices(self):
        initial = self.configure(language='en')
        self.assertEqual(initial, dict(schemaVersion=1, dataHome=str(self.home), port=8769, language='en'))
        before = self.config.read_bytes()
        self.assertEqual(self.configure(language='ru', data_home=self.base / 'different', port=9999), initial)
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse(self.home.exists(), 'configuration must not initialize a data store')
        self.assertEqual(sorted(self.app.rglob('*')), sorted([self.app / 'scripts', self.app / 'scripts/project_portal.py',
                                                              self.app / 'scripts/hub_launcher.py']))

    def test_defaults_use_external_platform_data_home(self):
        variable = 'LOCALAPPDATA' if os.name == 'nt' else 'XDG_DATA_HOME'
        with patch.dict(os.environ, {variable: str(self.base / 'local')}):
            self.assertEqual(launcher.default_base(), self.base / 'local/ProjectHub')
            default = launcher.configure(language='en', application_home=self.app)
        self.assertEqual(default['dataHome'], str(self.base / 'local/ProjectHub/data'))
        self.assertTrue((self.base / 'local/ProjectHub/installation.json').is_file())

    def test_config_corruption_is_not_overwritten(self):
        self.config.parent.mkdir(parents=True)
        initial = dict(schemaVersion=1, dataHome=str(self.home), port=8769, language='en')
        cases = ['not JSON', '[]', '{"language":"en","language":"ru"}', 'x' * 8193]
        for field, value in [('schemaVersion', True), ('schemaVersion', 2), ('port', True), ('port', 0),
                             ('port', 65536), ('language', 'fr'), ('dataHome', 'relative')]:
            cases.append(json.dumps({**initial, field:value}))
        cases.append(json.dumps({**initial, 'extra':True}))
        for raw in cases:
            with self.subTest(raw=raw[:80]):
                self.config.write_text(raw, encoding='utf-8')
                before = self.config.read_bytes()
                with self.assertRaises(launcher.LauncherError):
                    self.configure()
                self.assertEqual(before, self.config.read_bytes())

    def test_config_and_data_cannot_be_in_application_tree(self):
        for kwargs in [dict(path=self.app / 'installation.json'), dict(data_home=self.app / 'data')]:
            with self.subTest(kwargs=kwargs), self.assertRaises(launcher.LauncherError):
                launcher.configure(application_home=self.app, **kwargs)
        self.assertFalse((self.app / 'installation.json').exists())
        self.assertFalse((self.app / 'data').exists())

    def test_links_and_reparse_points_rejected(self):
        original = Path.lstat
        for target, attrs, mode in [(self.config, 0, stat.S_IFLNK),
                                    (self.config, 0x400, stat.S_IFREG),
                                    (self.config.parent, 0x400, stat.S_IFDIR)]:
            def fake_lstat(path, *args, **kwargs):
                if path == target:
                    return SimpleNamespace(st_mode=mode, st_file_attributes=attrs)
                return original(path, *args, **kwargs)
            with self.subTest(target=target, attrs=attrs), patch.object(Path, 'lstat', fake_lstat):
                with self.assertRaises(launcher.LauncherError):
                    self.configure()
        self.assertFalse(self.config.exists())

    def test_correct_running_home_reused_without_starting_process(self):
        self.configure()
        with patch.object(launcher, 'health', return_value=self.healthy()), \
             patch.object(launcher.subprocess, 'Popen') as start, \
             patch.object(launcher.webbrowser, 'open', return_value=True) as browser:
            self.assertEqual(self.open(), 'http://127.0.0.1:8769')
        start.assert_not_called()
        browser.assert_called_once_with('http://127.0.0.1:8769')

    def test_unmanaged_server_requires_graceful_stop_before_launcher_adoption(self):
        self.configure()
        with patch.object(launcher, 'health', return_value={**self.healthy(), 'supervised':False}), \
             patch.object(launcher.subprocess, 'Popen') as start:
            with self.assertRaisesRegex(launcher.LauncherError, 'without the shared launcher'):
                self.open()
        start.assert_not_called()

    def test_no_browser_mode_returns_ready_url_without_opening_browser(self):
        self.configure()
        with patch.object(launcher, 'health', return_value=self.healthy()), \
             patch.object(launcher.webbrowser, 'open') as browser:
            self.assertEqual(self.open(browser=False), 'http://127.0.0.1:8769')
        browser.assert_not_called()

    def test_occupied_other_home_starts_on_free_port_and_remembers_it(self):
        self.configure(language='en')
        before = self.config.read_bytes()
        process = Mock()
        process.poll.return_value = None
        other = self.healthy(self.base / 'unrelated-data')
        health_calls = []
        def occupied_health(port):
            health_calls.append(port)
            if port == 8769:
                return other
            return None if health_calls.count(49123) == 1 else self.healthy()
        with patch.object(launcher, 'health', side_effect=occupied_health) as health, \
             patch.object(launcher, 'remembered_port', return_value=49123), \
             patch.object(launcher.subprocess, 'Popen', return_value=process) as start, \
             patch.object(launcher.time, 'sleep'), \
             patch.object(launcher.webbrowser, 'open', return_value=True) as browser, \
             patch.dict(os.environ, {'PROJECT_HUB_ASGI_CATALOG':'unrelated-catalog'}):
            self.assertEqual(self.open(), 'http://127.0.0.1:49123')
        browser.assert_called_once_with('http://127.0.0.1:49123')
        command = start.call_args.args[0]
        self.assertEqual(command, [sys.executable, '-B', str(self.app / 'scripts/hub_launcher.py'),
                                   '--supervise', '--config', str(self.config)])
        options = start.call_args.kwargs
        self.assertEqual(options['cwd'], str(self.config.parent))
        self.assertEqual(options['env']['PROJECT_HUB_UI_LANGUAGE'], 'en')
        self.assertEqual(options['env']['PYTHONDONTWRITEBYTECODE'], '1')
        self.assertNotIn('PROJECT_HUB_ASGI_CATALOG', options['env'])
        for channel in ['stdin', 'stdout', 'stderr']:
            self.assertEqual(options[channel], subprocess.DEVNULL)
        if os.name == 'nt':
            self.assertTrue(options['creationflags'] & subprocess.CREATE_NO_WINDOW)
        self.assertEqual(self.config.read_bytes(), before, 'free port must not replace user port preference')
        process.terminate.assert_not_called()
        self.assertEqual(health.call_args_list[-1].args, (49123,))
        with patch.object(launcher, 'health', side_effect=[other, self.healthy()]), \
             patch.object(launcher, 'remembered_port', return_value=49123), \
             patch.object(launcher.subprocess, 'Popen', return_value=process) as start, \
             patch.object(launcher.webbrowser, 'open', return_value=True):
            self.assertEqual(self.open(), 'http://127.0.0.1:49123')
        start.assert_not_called()

    def test_wrong_service_never_opens_browser_after_spawn(self):
        self.configure()
        for body in [self.healthy(self.base / 'wrong-home'), dict(service='another-service', dataHome=str(self.home))]:
            process = Mock()
            process.poll.return_value = None
            with self.subTest(body=body), \
                 patch.object(launcher, 'health', return_value=body), \
                 patch.object(launcher, 'available_port', return_value=49123), \
                 patch.object(launcher.subprocess, 'Popen', return_value=process), \
                 patch.object(launcher.time, 'monotonic', side_effect=itertools.count(0, 1)), \
                 patch.object(launcher.time, 'sleep'), \
                 patch.object(launcher.webbrowser, 'open') as browser:
                with self.assertRaises(launcher.LauncherError):
                    self.open(timeout=5)
            browser.assert_not_called()
            process.terminate.assert_not_called()

    def test_first_start_allows_verified_backup_before_the_server_listens(self):
        self.configure()
        process = Mock()
        process.poll.return_value = None
        with patch.object(launcher, 'health', side_effect=[None, None, None, self.healthy()]), \
             patch.object(launcher.subprocess, 'Popen', return_value=process), \
             patch.object(launcher.time, 'monotonic', side_effect=itertools.count(0, 100)), \
             patch.object(launcher.time, 'sleep'), \
             patch.object(launcher.webbrowser, 'open') as browser:
            self.assertEqual(self.open(), 'http://127.0.0.1:8769')
        browser.assert_called_once_with('http://127.0.0.1:8769')
        process.terminate.assert_not_called()

    def test_startup_timeout_and_early_exit_are_bounded(self):
        self.configure()
        process = Mock()
        process.poll.return_value = None
        with patch.object(launcher, 'health', return_value=None), \
             patch.object(launcher, 'available_port', return_value=49123), \
             patch.object(launcher.subprocess, 'Popen', return_value=process), \
             patch.object(launcher.time, 'monotonic', side_effect=itertools.count(0, 20)), \
             patch.object(launcher.time, 'sleep'), \
             patch.object(launcher.webbrowser, 'open') as browser:
            with self.assertRaisesRegex(launcher.LauncherError, 'in time'):
                self.open(timeout=15)
        browser.assert_not_called()
        process.terminate.assert_not_called()
        exited = Mock()
        exited.poll.return_value = 7
        with patch.object(launcher, 'health', return_value=None), \
             patch.object(launcher, 'available_port', return_value=49123), \
             patch.object(launcher.subprocess, 'Popen', return_value=exited), \
             patch.object(launcher.webbrowser, 'open') as browser:
            with self.assertRaisesRegex(launcher.LauncherError, 'exit 7'):
                self.open()
        browser.assert_not_called()
        exited.terminate.assert_not_called()

    def test_bind_probes_loopback_and_falls_back_when_port_busy(self):
        probe = Mock()
        probe.bind.side_effect = [OSError('busy'), None]
        probe.getsockname.return_value = ('127.0.0.1', 49123)
        probe.__enter__ = Mock(return_value=probe)
        probe.__exit__ = Mock(return_value=False)
        with patch.object(launcher.socket, 'socket', return_value=probe):
            self.assertEqual(launcher.available_port(8769), 49123)
        self.assertEqual([call.args[0] for call in probe.bind.call_args_list],
                         [('127.0.0.1', 8769), ('127.0.0.1', 0)])

    @unittest.skipUnless(os.name == 'nt', 'Windows job lifetime contract')
    def test_background_lifetime_respects_job_and_restricted_token_boundaries(self):
        import runtime_diagnostics
        cases = [
            (dict(member=False), False, False),
            (dict(member=True,killOnClose=True,breakawayAllowed=True), False, True),
            (dict(member=True,killOnClose=True,breakawayAllowed=False), False, False),
            (dict(member=True,killOnClose=True,breakawayAllowed=True), True, False),
            (dict(member=True,killOnClose=True,breakawayAllowed=True), None, False),
        ]
        for job,restricted,independent in cases:
            with self.subTest(job=job,restricted=restricted), \
                 patch.object(runtime_diagnostics,'process_context',return_value=dict(windowsJob=job,restrictedToken=restricted)):
                flags=launcher.background_flags()
            self.assertTrue(flags & subprocess.CREATE_NO_WINDOW)
            self.assertEqual(bool(flags & subprocess.CREATE_BREAKAWAY_FROM_JOB),independent)

    def test_health_is_bounded_local_and_does_not_follow_redirects(self):
        response = Mock()
        response.status = 200
        response.read.return_value = json.dumps(self.healthy()).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = response
        with patch.object(launcher, 'build_opener', return_value=opener) as build:
            self.assertEqual(launcher.health(8769), self.healthy())
        opener.open.assert_called_once_with('http://127.0.0.1:8769/api/health', timeout=.5)
        redirect = build.call_args.args[1]
        self.assertIsNone(redirect.redirect_request(None, None, 302, '', {}, 'http://elsewhere'))

    def test_launcher_reports_errors_and_pythonw_has_no_console_dependency(self):
        with patch.object(launcher, 'configure', side_effect=launcher.LauncherError('invalid configuration')), \
             patch.object(launcher, 'report_error') as report:
            self.assertEqual(launcher.main(['--configure', '--language=en']), 1)
        self.assertEqual(str(report.call_args.args[0]), 'invalid configuration')
        with patch.object(launcher.sys, 'stderr', io.StringIO()) as stream:
            launcher.report_error(launcher.LauncherError('test error'))
            self.assertIn('test error', stream.getvalue())
        with patch.object(launcher.sys, 'stderr', None), \
             patch.object(launcher, 'default_base', return_value=self.base / 'windowed'), \
             patch.object(launcher.webbrowser, 'open') as browser:
            launcher.report_error(launcher.LauncherError('windowed <error>'))
        browser.assert_called_once_with((self.base / 'windowed/launch-error.html').as_uri())
        self.assertIn('&lt;error&gt;', (self.base / 'windowed/launch-error.html').read_text())


if __name__ == '__main__':
    unittest.main()
