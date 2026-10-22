import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import runtime_diagnostics as diagnostics


class RuntimeDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        diagnostics.cleanup()
        self.directory = tempfile.TemporaryDirectory()
        self.assertTrue(diagnostics.configure('fixture', self.directory.name, requestId='hidden', safe='ok'))

    def tearDown(self):
        diagnostics.cleanup()
        self.directory.cleanup()

    def test_rotation_and_secret_omission(self):
        for _ in range(300):
            diagnostics.record('large', token='omit', value='x' * 5000)
        files = list(Path(self.directory.name).glob('fixture-*.jsonl*'))
        self.assertLessEqual(len(files), 4)
        self.assertTrue(all(path.stat().st_size <= 2 * 1024 * 1024 for path in files))
        contents = ''.join(path.read_text(encoding='utf-8') for path in files)
        self.assertNotIn('omit', contents)

    def test_lifetime_records_unclean_predecessor_and_clean_shutdown(self):
        path = Path(self.directory.name) / 'lifetime.json'
        predecessor = dict(state='running', runId='previous', heartbeatAt='2026-01-01T00:00:00Z',
                           process=dict(pid=123, parentPid=456), phase='serving', port=8769)
        path.write_text(json.dumps(predecessor), encoding='utf-8')
        with diagnostics.lifetime(path) as heartbeat:
            current = json.loads(path.read_text())
            self.assertEqual('running', current['state'])
            self.assertNotEqual('previous', current['runId'])
            heartbeat(force=True, phase='serving', port=8769)
            incident = diagnostics.report()['incident']
            self.assertEqual('supervisor.previous_run_interrupted', incident['event'])
            self.assertEqual('unknown', incident['cause'])
            self.assertEqual('previous', incident['previous']['runId'])
        self.assertEqual('stopped', json.loads(path.read_text())['state'])
        with patch.object(diagnostics, '_incident') as incident:
            with diagnostics.lifetime(path):
                pass
            incident.assert_not_called()

    def test_lifetime_failure_is_recorded_without_hiding_original_error(self):
        path = Path(self.directory.name) / 'lifetime.json'
        with self.assertRaisesRegex(RuntimeError, 'fixture failure'):
            with diagnostics.lifetime(path):
                raise RuntimeError('fixture failure')
        self.assertEqual('failed', json.loads(path.read_text())['state'])
        with patch.object(diagnostics, '_atomic', side_effect=OSError('disk unavailable')):
            with diagnostics.lifetime(path):
                pass  # Diagnostics must not take down the application.

    def test_report_detects_dead_lifetime_without_claiming_a_cause(self):
        path = Path(self.directory.name).parent / 'supervisor-lifetime.json'
        # Keep this fixture within its own isolated parent.
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            logs = parent / 'diagnostics'; logs.mkdir()
            (parent / path.name).write_text(json.dumps(dict(state='running',process=dict(pid=123))),encoding='utf-8')
            with patch.object(diagnostics, '_process_alive', return_value=False):
                result = diagnostics.report(logs)
            self.assertEqual('interrupted', result['lifetime']['state'])
            self.assertEqual('unknown', result['lifetime']['cause'])

    def test_thread_hook_and_pythonw_safe_exception(self):
        failed = []
        def crash():
            raise RuntimeError('thread failure')
        thread = threading.Thread(target=crash)
        thread.start(); thread.join()
        log = next(Path(self.directory.name).glob('fixture-*.jsonl'))
        self.assertIn('uncaught_exception', log.read_text(encoding='utf-8'))
        diagnostics.exception('explicit', RuntimeError('recorded'))

    def test_child_tail_exit_incident_and_report(self):
        child = subprocess.Popen([sys.executable, '-c', "import sys; print('child output'); sys.exit(7)"],
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        capture = diagnostics.capture_child(child, 'worker', {'operation': 'fixture'})
        child.wait()
        capture['threadObject'].join(2)
        diagnostics.child_exit(child, 'worker', thread=capture['threadObject'], expected=False, operation='fixture')
        report = diagnostics.report(include_tail=True)
        self.assertIn('child output', report['tail'])
        self.assertEqual(7, report['incident']['exitCode'])
        self.assertIn('worker', json.dumps(report))

    def test_child_stream_keeps_output_written_before_eof(self):
        child = subprocess.Popen(
            [sys.executable, '-c',
             "import sys; print('first', flush=True); sys.stdin.readline(); print('last', flush=True)"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        capture = diagnostics.capture_child(child, 'stream', {'operation': 'fixture'})
        deadline = time.time() + 2
        while time.time() < deadline and 'first' not in Path(capture['path']).read_text(encoding='utf-8'):
            time.sleep(.01)
        self.assertIn('first', Path(capture['path']).read_text(encoding='utf-8'))
        self.assertIsNone(child.poll())
        child.stdin.write(b'\n'); child.stdin.close()
        child.wait(timeout=5)
        capture['threadObject'].join(2)
        diagnostics.child_exit(child, 'stream', thread=capture['threadObject'], expected=True)
        tail = Path(capture['path']).read_text(encoding='utf-8')
        self.assertIn('first', tail)
        self.assertIn('last', tail)

    def test_expected_and_unexpected_zero_exit_classification(self):
        expected = subprocess.Popen([sys.executable, '-c', 'pass'], stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT)
        expected.wait(timeout=5)
        diagnostics.child_exit(expected, 'expected', expected=True)
        self.assertFalse(diagnostics.report()['incident'])

        unexpected = subprocess.Popen([sys.executable, '-c', 'pass'], stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT)
        unexpected.wait(timeout=5)
        diagnostics.child_exit(unexpected, 'unexpected', expected=False)
        self.assertTrue(diagnostics.report()['incident']['incident'])

    def test_child_exit_preserves_prior_exception_evidence(self):
        diagnostics.exception('before_child', RuntimeError('prior evidence'))
        child = subprocess.Popen([sys.executable, '-c', 'pass'], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT)
        child.wait(timeout=5)
        diagnostics.child_exit(child, 'traceback', expected=False)
        incident = diagnostics.report()['incident']
        self.assertIn('previousIncident', incident)
        self.assertIn('prior evidence', json.dumps(incident))

    def test_report_tail_is_opt_in_and_invalid_configuration_is_safe(self):
        diagnostics.record('marker', value='ok')
        compact = diagnostics.report()
        self.assertIn('directory', compact)
        self.assertNotIn('tail', compact)
        self.assertIn('tail', diagnostics.report(include_tail=True))

        invalid = Path(self.directory.name) / 'file'
        invalid.write_text('x', encoding='utf-8')
        diagnostics.cleanup()
        self.assertFalse(diagnostics.configure('fixture', invalid))

    def test_none_streams_are_replaced_with_bounded_streams(self):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        try:
            diagnostics.cleanup()
            sys.stdout = None
            sys.stderr = None
            self.assertTrue(diagnostics.configure('none-stream', self.directory.name))
            sys.stdout.write('bounded output')
            sys.stderr.write('bounded error')
            sys.stdout.flush(); sys.stderr.flush()
        finally:
            diagnostics.cleanup()
            sys.stdout, sys.stderr = old_stdout, old_stderr

    def test_disabled_mode_never_writes(self):
        diagnostics.cleanup()
        self.assertFalse(diagnostics.configure('disabled'))
        self.assertIsNone(diagnostics.record('ignored'))

    def test_structured_exception_metadata_is_whitelisted(self):
        class MergeError(Exception):
            code = 'storage_import_conflict'
            status = 409
            body = {
                'error': 'conflict', 'message': 'merge required', 'secret': 'omit',
                'conflicts': [{'type': 'ambiguous-global-data', 'path': 'ui-preferences.json',
                               'modes': ['add'], 'projects': ['one', 'two'],
                               'rowValues': {'token': 'omit'}, 'payload': 'omit'}]
            }
        diagnostics.exception('merge', MergeError('merge failed'), phase='selected',
                              projects=['one', 'two'])
        incident = diagnostics.report()['incident']
        self.assertEqual('storage_import_conflict', incident['errorCode'])
        self.assertEqual(409, incident['status'])
        self.assertEqual(1, incident['conflictCount'])
        encoded = json.dumps(incident)
        self.assertIn('ambiguous-global-data', encoded)
        self.assertNotIn('rowValues', encoded)
        self.assertNotIn('omit', encoded)

    def test_structured_exception_conflicts_are_counted_and_sample_bounded(self):
        class BulkError(Exception):
            code = 'bulk_conflict'
            body = {'conflicts': [{'type': 'duplicate', 'path': str(index)} for index in range(100)]}
        diagnostics.exception('bulk', BulkError('many conflicts'))
        incident = diagnostics.report()['incident']
        self.assertEqual(100, incident['conflictCount'])
        self.assertLessEqual(len(incident['conflictSample']), 8)

    def test_structured_exception_large_fields_remain_reportable(self):
        class HugeError(Exception):
            code = 'huge_conflict'
            body = {'conflicts': [
                {'type': 'x' * 10000, 'message': 'm' * 10000,
                 'projects': ['p' * 10000 for _ in range(100)]}
                for _ in range(100)
            ]}
        diagnostics.exception('huge', HugeError('bounded'))
        report = diagnostics.report()
        self.assertTrue(report['enabled'])
        self.assertEqual(100, report['incident']['conflictCount'])
        self.assertLessEqual(len(json.dumps(report['incident'])), diagnostics.MAX_REPORT_JSON)

    def test_generic_exception_metadata_remains_compatible(self):
        diagnostics.exception('generic', RuntimeError('plain failure'))
        incident = diagnostics.report()['incident']
        self.assertEqual('RuntimeError', incident['errorType'])
        self.assertIn('plain failure', incident['errorMessage'])

    def test_retention_preserves_other_live_processes_and_bounds_closed_groups(self):
        folder=Path(self.directory.name)
        live_pid=900001
        for index in range(45):
            path=folder/f'fixture-{900000+index}.jsonl'
            path.write_text('old',encoding='utf-8')
            __import__('os').utime(path,(index,index))
        with patch.object(diagnostics,'_process_alive',side_effect=lambda pid:pid==live_pid):
            diagnostics._retain('fixture')
        self.assertTrue((folder/f'fixture-{live_pid}.jsonl').is_file())
        self.assertEqual(len(list(folder.glob('fixture-*.jsonl'))),42)
        self.assertFalse((folder/'fixture-900000.jsonl').exists())


if __name__ == '__main__':
    unittest.main()
