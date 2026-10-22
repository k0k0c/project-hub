"""Project-local publication adapter, without contacting any running Hub."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('check_publish', Path(__file__).resolve().parents[1] / 'project_hub_check_publish.py')
publish = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publish)


class CheckPublishTest(unittest.TestCase):
    def test_execute_core_reads_only_external_output_home(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            # Point the runner output at a disposable external location for this test.
            with patch.dict(os.environ, {'PROJECT_HUB_CHECK_OUTPUT_HOME': str(output)}):
                namespace = publish.output_home(publish.ROOT)
                result = namespace / 'result.json'; log = namespace / 'result.log'
                log.write_text('check log\n')
                result.write_text(json.dumps({'log': str(log)}))
                completed = subprocess.CompletedProcess([], 0, f'PASS; result: {result}\n', '')
                with patch.object(publish.subprocess, 'run', return_value=completed), contextlib.redirect_stdout(io.StringIO()) as stdout:
                    self.assertEqual(publish.execute_core(['--profile', 'css']), 0)
                self.assertIn('check log', stdout.getvalue())

    def test_missing_context_runs_without_fabricated_task(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(publish, 'execute_core', return_value=7) as run:
            with contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(publish.main(['--profile', 'css']), 7)
            run.assert_called_once_with(['--profile', 'css'])
            self.assertIn('not registered', output.getvalue())

    def test_concrete_profile_and_revision_passed_to_generic_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / '.project-hub').mkdir()
            (root / '.project-hub/testing.json').write_text('{}')
            responses = [subprocess.CompletedProcess([], 0, json.dumps({'profiles':['css','javascript'], 'tree':'content-sha', 'profileVersion':'config-sha', 'scope':['src']}), ''),
                         subprocess.CompletedProcess([], 0, 'commit-sha\n', '')]
            env = {'PROJECT_HUB_CHECK_TASK':'task-a', 'PROJECT_HUB_CHECK_PROJECT':'project-a',
                   'PROJECT_HUB_CHECK_STAGE':'stage-a', 'PROJECT_HUB_CHECK_URL':'http://127.0.0.1:9999'}
            with patch.dict(os.environ, env, clear=True), patch.object(publish, 'ROOT', root), \
                    patch.object(publish.subprocess, 'run', side_effect=responses), \
                    patch.object(publish.subprocess, 'check_output', return_value=b' M source'), \
                    patch.object(publish.subprocess, 'call', return_value=3) as call:
                self.assertEqual(publish.main(['--title','Verify layout','--profile','auto']), 3)
            argv = call.call_args.args[0]
            self.assertEqual(argv[argv.index('--profile')+1], 'css+javascript')
            self.assertEqual(argv[argv.index('--title')+1], 'Verify layout')
            self.assertNotIn('--title', argv[argv.index('--execute-core')+1:])
            self.assertEqual(argv[argv.index('--task')+1], 'task-a')
            self.assertEqual(argv[argv.index('--stage')+1], 'stage-a')
            revision = json.loads(argv[argv.index('--revision')+1])
            self.assertEqual(revision, {'head':'commit-sha', 'dirty':True, 'fingerprint':'content-sha'})
            self.assertIn('--execute-core', argv)

    def test_selection_failure_does_not_execute_or_claim_success(self):
        env = {'PROJECT_HUB_CHECK_TASK':'task-a', 'PROJECT_HUB_CHECK_PROJECT':'project-a',
               'PROJECT_HUB_CHECK_URL':'http://127.0.0.1:9999'}
        with patch.dict(os.environ, env, clear=True), \
                patch.object(publish.subprocess, 'run', return_value=subprocess.CompletedProcess([], 2, '', 'bad config')), \
                patch.object(publish.subprocess, 'call') as call, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(publish.main(['--profile','auto']), 2)
            call.assert_not_called()
