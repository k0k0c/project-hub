"""Generic runner tests use temporary roots and a disposable loopback receiver."""
from contextlib import redirect_stdout, redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

PLUGIN = Path(__file__).resolve().parents[2] / 'tools/project-portal/plugins/project-hub'
sys.path.insert(0, str(PLUGIN / 'scripts'))
import hub_check


class CheckWrapperTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output_temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.output_temp.cleanup)
        environment = patch.dict(os.environ, {'PROJECT_HUB_CHECK_OUTPUT_HOME': self.output_temp.name})
        environment.start(); self.addCleanup(environment.stop)
        self.events = []
        self.reject = False
        self.delay = 0
        owner = self
        class Receiver(BaseHTTPRequestHandler):
            def do_POST(self):
                value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if '/artifacts/upload?' not in self.path:
                    owner.events.append((self.path, value))
                time.sleep(owner.delay)
                self.send_response(503 if owner.reject else 200)
                self.end_headers()
                self.wfile.write(b'{"source":{"path":"hub-artifact/fixture/check.log"}}' if '/artifacts/upload?' in self.path else b'{"ok":true}')
            def log_message(self, *args):
                pass
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Receiver)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.url = 'http://127.0.0.1:' + str(self.server.server_port)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def run_wrapper(self, code, extra=None, command=None):
        argv = ['exec', '--url', self.url, '--project', 'temporary', '--task', 'task',
                '--title', 'Verify check publication', '--stage', 'stage', '--profile', 'opaque-profile', '--profile-version', 'opaque-v1',
                '--cwd', str(self.root)] + (extra or [])
        argv += ['--'] + (command or [sys.executable, '-c', code])
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(io.StringIO()):
            result = hub_check.main(argv)
        self.output = json.loads(output.getvalue())
        return result

    def flush(self, *extra):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return hub_check.main(['flush', '--url', self.url, '--project', 'temporary',
                                   '--cwd', str(self.root), *extra])

    def runs(self):
        return list(hub_check.check_directory(self.root, None)[1].glob('*/start.json'))

    def test_success_literal_argv_and_immutable_metadata(self):
        literal = 'space & | ; $(never) "quoted"'
        result = self.run_wrapper('', command=[sys.executable, '-c', 'import sys; print(sys.argv[1])', literal],
                                  extra=['--scope', 'src', '--revision', '{"head":"abc","dirty":true}'])
        self.assertEqual(result, 0)
        self.assertEqual(self.output['publication'], 'delivered')
        start, finish = self.events[0][1], self.events[-1][1]
        self.assertEqual(self.events[0][0], '/api/v1/checks?project=temporary')
        self.assertEqual(start['status'], 'running')
        self.assertEqual(start['title'], 'Verify check publication')
        self.assertEqual(finish['status'], 'passed')
        self.assertEqual(finish['exitCode'], 0)
        for key, value in start.items():
            if key != 'status':
                self.assertEqual(finish[key], value)
        self.assertNotIn('log', start)
        self.assertTrue(finish['log'].startswith('hub-artifact/'))
        self.assertIn(literal, Path(self.output['localLog']).read_text())
        self.assertFalse((self.root / '.local').exists())
        self.assertTrue((self.runs()[0].parent / 'delivered.json').exists())

    def test_nonzero_and_launch_failure_never_pass(self):
        self.assertEqual(self.run_wrapper('raise SystemExit(7)'), 7)
        self.assertEqual(self.events[-1][1]['status'], 'failed')
        self.assertEqual(self.events[-1][1]['exitCode'], 7)
        self.assertEqual(self.run_wrapper('', command=[str(self.root / 'missing-runner')]), 127)
        self.assertEqual(self.events[-1][1]['status'], 'unknown')
        self.assertNotIn('exitCode', self.events[-1][1])
        self.assertEqual(len(self.runs()), 2)

    def test_slow_acknowledgement_is_delivered(self):
        self.delay = .6
        self.assertEqual(self.run_wrapper('pass'), 0)
        self.assertTrue((self.runs()[0].parent / 'delivered.json').exists())

    def test_offline_command_runs_and_explicit_retry_orders_both_events(self):
        self.reject = True
        self.assertEqual(self.run_wrapper('print("ran offline")'), 0)
        self.assertEqual((self.output['status'], self.output['publication']), ('passed', 'pending'))
        run = self.runs()[0].parent
        self.assertTrue((run / 'finish.json').exists())
        self.assertFalse((run / 'delivered.json').exists())
        self.reject = False
        self.events.clear()
        self.assertEqual(self.flush(), 0)
        self.assertEqual([event['status'] for _, event in self.events], ['running', 'passed'])
        self.assertEqual(len({event['runId'] for _, event in self.events}), 1)
        self.assertEqual(self.flush(), 0)
        self.assertEqual(len(self.events), 2)

    def test_start_without_finish_requires_explicit_abandonment(self):
        self.reject = True
        self.run_wrapper('pass')
        run = self.runs()[0].parent
        (run / 'finish.json').unlink()
        self.reject = False
        self.events.clear()
        self.assertEqual(self.flush(), 1)
        self.assertEqual(self.events[-1][1]['status'], 'running')
        self.assertEqual(self.flush('--abandon-run', run.name), 0)
        self.assertEqual(self.events[-1][1]['status'], 'unknown')
        self.assertNotIn('exitCode', self.events[-1][1])

    def test_transport_and_log_root_restrictions(self):
        for url in ['https://127.0.0.1', 'http://example.com', 'http://user:secret@localhost', 'http://localhost/path']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                hub_check.Client(url)
        with self.assertRaises(ValueError):
            hub_check.check_directory(self.root, '../elsewhere')

    def test_oversized_log_keeps_terminal_result_and_retry_payload(self):
        self.reject = True
        self.assertEqual(self.run_wrapper('import sys; sys.stdout.write("x" * (21 * 1024**2))'), 0)
        run = self.runs()[0].parent
        self.reject = False
        self.events.clear()
        self.assertEqual(self.flush(), 0)
        self.assertEqual(['running', 'passed'], [value['status'] for _, value in self.events])
        finish = self.events[-1][1]
        self.assertNotIn('log', finish)
        self.assertIn('retained in external local check storage', finish['summary'])
        self.assertGreater((run / 'output.log').stat().st_size, 20 * 1024**2)
        (run / 'delivered.json').unlink()
        self.assertEqual(self.flush(), 0)
        self.assertEqual(finish, self.events[-1][1])

    def test_storage_failure_does_not_block_command(self):
        with patch.object(hub_check, 'persist', side_effect=OSError('disk unavailable')):
            self.assertEqual(self.run_wrapper('raise SystemExit(6)'), 6)
        self.assertEqual((self.output['status'], self.output['publication']), ('failed', 'unavailable'))
        self.assertEqual(self.events, [])

    def test_interruption_cleans_up_and_reports_interrupted(self):
        child = MagicMock()
        child.wait.side_effect = [KeyboardInterrupt(), -2]
        child.returncode = -2
        with patch.object(hub_check.subprocess, 'Popen', return_value=child), patch.object(hub_check, 'stop_child') as stop:
            self.assertEqual(self.run_wrapper('pass'), 130)
        stop.assert_called_once_with(child)
        self.assertEqual(self.events[-1][1]['status'], 'interrupted')

    def test_installer_copies_new_script(self):
        sys.path.insert(0, str(PLUGIN.parents[3] / 'scripts'))
        from prepare_project_hub_plugin import prepare
        destination = self.root / 'package/project-hub'
        prepare(destination, self.url)
        self.assertEqual((destination / 'scripts/hub_check.py').read_bytes(),
                         (PLUGIN / 'scripts/hub_check.py').read_bytes())

    @unittest.skipUnless(os.name == 'nt', 'Windows native process-tree cleanup')
    def test_windows_interruption_terminates_real_child_tree(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        marker = self.root / 'descendant.pid'
        code = ('import subprocess,sys,time,pathlib; '
                'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
                'pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(30)')
        real_popen = subprocess.Popen
        handles = []
        children = []
        def launch(command, **kwargs):
            child = real_popen(command, **kwargs)
            if command[0] == sys.executable:
                children.append(child)
                real_wait = child.wait
                first = True
                def wait(*args, **options):
                    nonlocal first
                    if first:
                        first = False
                        deadline = time.monotonic() + 5
                        descendant_pid = None
                        while descendant_pid is None and time.monotonic() < deadline:
                            try:
                                candidate = int(marker.read_text().strip())
                            except (OSError, ValueError):
                                candidate = 0
                            if candidate > 0:
                                descendant_pid = candidate
                            else:
                                time.sleep(.01)
                        self.assertIsNotNone(descendant_pid, 'Runner did not start descendant')
                        handle = kernel.OpenProcess(0x100000, False, descendant_pid)
                        self.assertTrue(handle)
                        handles.append(handle)
                        raise KeyboardInterrupt
                    return real_wait(*args, **options)
                child.wait = wait
            return child
        try:
            with patch.object(hub_check.subprocess, 'Popen', side_effect=launch):
                self.assertEqual(self.run_wrapper('', command=[sys.executable, '-c', code, str(marker)]), 130)
            self.assertIsNotNone(children[0].poll())
            self.assertEqual(kernel.WaitForSingleObject(handles[0], 2000), 0)
            self.assertEqual(self.events[-1][1]['status'], 'interrupted')
        finally:
            for child in children:
                if child.poll() is None:
                    hub_check.stop_child(child)
            for handle in handles:
                kernel.CloseHandle(handle)


if __name__ == '__main__':
    unittest.main()
