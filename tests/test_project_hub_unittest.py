"""Grouped discovery preserves counts, failures and disposable timing output."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('timed_unittest', SOURCE / 'scripts/project_hub_unittest.py')
timed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timed)


class TimedDiscoveryTests(unittest.TestCase):
    def exercise(self, failing=False, empty=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            # Unique names avoid shared unittest import caches across fixtures.
            name = 'test_' + root.name.replace('-', '_') + '.py'
            if not empty:
                (root / name).write_text('import unittest\nclass Case(unittest.TestCase):\n def test_case(self): '
                                         + ('self.fail("expected")' if failing else 'pass') + '\n')
            output = root / 'timings.json'
            with contextlib.redirect_stderr(io.StringIO()):
                code = timed.main(['--directory', str(root), '--pattern', name, '--pattern', 'test*.py', '--pattern', name,
                                   '--timings', str(output)])
            return code, json.loads(output.read_text())

    def test_successful_pattern_union_is_not_duplicated(self):
        code, result = self.exercise()
        self.assertEqual(0, code)
        self.assertEqual(1, result['testsRun'])
        self.assertEqual(1, len(result['tests']))
        self.assertGreaterEqual(result['tests'][0]['seconds'], 0)

    def test_phase_timings_cover_success_failures_cleanup_and_skip(self):
        class Success(unittest.TestCase):
            def setUp(self):
                self.addCleanup(lambda: None)
            def test_case(self):
                pass

        class SetupFailure(unittest.TestCase):
            def setUp(self):
                raise RuntimeError('setup')
            def test_case(self):
                self.fail('body must not run')

        class BodyFailure(unittest.TestCase):
            def test_case(self):
                self.fail('body')

        class CleanupFailure(unittest.TestCase):
            def setUp(self):
                self.addCleanup(lambda: (_ for _ in ()).throw(RuntimeError('cleanup')))
            def test_case(self):
                pass

        class Skipped(unittest.TestCase):
            def test_case(self):
                self.skipTest('skip')

        stream = io.StringIO()
        suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(case)
                                   for case in (Success, SetupFailure, BodyFailure, CleanupFailure, Skipped))
        result = timed.TimedResult(stream, True, 1)
        unittest.TestSuite(suite).run(result)
        self.assertEqual(5, result.testsRun)
        self.assertEqual(1, len(result.failures))
        self.assertEqual(2, len(result.errors))
        self.assertEqual(1, len(result.skipped))
        self.assertEqual(5, len(result.timings))
        for item in result.timings:
            self.assertEqual({'setup', 'body', 'teardown', 'cleanup'}, set(item['phases']))
            self.assertLessEqual(sum(item['phases'].values()), item['seconds'] + 0.002)
        for case in (Success, SetupFailure, BodyFailure, CleanupFailure, Skipped):
            self.assertTrue(any(f'.{case.__name__}.test_case' in item['test'] for item in result.timings))

    def test_failing_and_empty_discovery_cannot_pass(self):
        code, result = self.exercise(failing=True)
        self.assertEqual(1, code)
        self.assertEqual(1, result['failures'])
        code, result = self.exercise(empty=True)
        self.assertEqual(1, code)
        self.assertEqual(0, result['testsRun'])

    def test_failure_traceback_keeps_test_source_line(self):
        class Failing(unittest.TestCase):
            def test_actual_assertion(self):
                self.fail('traceback marker')

        stream = io.StringIO()
        result = timed.TimedResult(stream, True, 1)
        with contextlib.redirect_stderr(io.StringIO()) as diagnostics:
            unittest.defaultTestLoader.loadTestsFromTestCase(Failing).run(result)
        self.assertEqual(1, len(result.failures))
        failure = result.failures[0][1]
        self.assertIn('test_project_hub_unittest.py', failure)
        self.assertIn('traceback marker', failure)
        self.assertNotIn('timed_call', failure)
        self.assertIn('[FAIL]', diagnostics.getvalue())

    def test_script_launch_retains_project_namespace_imports(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts/tests').mkdir(parents=True)
            (root / 'scripts/fixture.py').write_text('VALUE = 42\n')
            (root / 'scripts/tests/test_namespace.py').write_text(
                'import unittest\nfrom scripts.fixture import VALUE\n'
                'class Case(unittest.TestCase):\n def test_value(self): self.assertEqual(42, VALUE)\n')
            result = subprocess.run([sys.executable, '-S', str(SOURCE / 'scripts/project_hub_unittest.py'),
                                     '--directory', 'scripts/tests'], cwd=root, capture_output=True, text=True)
            self.assertEqual(0, result.returncode, result.stderr)
