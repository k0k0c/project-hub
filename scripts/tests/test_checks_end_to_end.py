"""Real wrapper subprocesses publish only to disposable Hub servers."""
import json
from pathlib import Path
import subprocess
import sys
from test_manual_editing import ManualApiCase

WRAPPER = Path(__file__).resolve().parents[2] / 'tools/project-portal/plugins/project-hub/scripts/hub_check.py'


class CheckEndToEndTest(ManualApiCase):
    def launch(self, project, task, profile, command):
        root = self.registry.base_store(project).root
        result = subprocess.run([sys.executable, str(WRAPPER), 'exec',
            '--url', 'http://127.0.0.1:' + str(self.server.server_port), '--project', project,
            '--task', task, '--profile', profile, '--cwd', str(root), '--', *command],
            capture_output=True, text=True, encoding='utf-8', timeout=30)
        return result

    def test_two_project_runners_and_readable_logs(self):
        first = self.task()
        second_project = self.projects['b']
        second = self.task(project=second_project)
        good = self.launch(self.pid, first, 'custom-python', [sys.executable, '-c', "print('first runner')"])
        self.assertEqual(good.returncode, 0, good.stderr)
        bad = self.launch(second_project, second, 'custom-node', ['node', '-e', "console.log('second runner');process.exit(7)"])
        self.assertEqual(bad.returncode, 7, bad.stderr)
        for project, task, profile, status, message in [
                (self.pid, first, 'custom-python', 'passed', 'first runner'),
                (second_project, second, 'custom-node', 'failed', 'second runner')]:
            store = self.registry.store(project)
            rows = store.snapshot()['checks']
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]['taskId'], rows[0]['profile'], rows[0]['status']), (task, profile, status))
            self.assertIn(message.encode(), store.evidence(rows[0]['evidence'][0]['path']))

    def test_actual_mcp_and_http_share_validator(self):
        from plugin_api import call
        body = {'runId':'shared-contract', 'task':self.task(), 'command':[sys.executable, ''],
                'startedAt':'2026-09-19T12:00:00Z', 'status':'running', 'revision':{'head':None,'dirty':False}}
        request = dict(cwd=str(self.registry.base_store(self.pid).root), session='checks-e2e',
                       tool='hub_check', arguments=body)
        first = call(self.registry, request)
        self.assertFalse(first['duplicate'])
        status, repeated = self.request('/api/v1/checks', body)
        self.assertEqual(status, 200)
        self.assertTrue(repeated['duplicate'])
