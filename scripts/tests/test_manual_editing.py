"""Manual API contract tests use disposable catalogs, roots and journals."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_portal import PortalServer
from project_registry import CodexProjects, ProjectRegistry


class ManualApiCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        catalog = root / 'catalog.json'
        catalog.write_text(json.dumps({'local-projects': {
            key: {'id': key, 'name': key, 'rootPaths': [str(root / key)]} for key in ('a', 'b')}}))
        self.registry = ProjectRegistry(root / 'data', CodexProjects(catalog))
        self.projects = {p['codex_id']: p['id'] for p in self.registry.list()['projects']}
        self.pid = self.projects['a']
        for pid in self.projects.values():
            store = self.registry.store(pid)
            store.root.mkdir()
            (store.root / 'proof.txt').write_text('evidence')
        self.server = PortalServer(('127.0.0.1', 0), registry=self.registry)
        # Keep per-test servers/data, but avoid the default half-second shutdown poll.
        self.worker = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': .05}, daemon=True)
        self.worker.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()

    def state(self, project=None):
        return self.registry.store(project or self.pid).snapshot()

    def request(self, route, body=None, project=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        try:
            connection.request('POST' if body is not None else 'GET', route + '?project=' + (project or self.pid),
                               json.dumps(body) if body is not None else None,
                               {'Content-Type': 'application/json'})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def mutate(self, route, body, project=None, expected_status=200):
        status, result = self.request('/api/v1/' + route,
                                      {'expected': self.state(project)['revision'], **body}, project)
        self.assertEqual(status, expected_status, result)
        return result

    def task(self, title='Task', project=None):
        return self.mutate('tasks/create', {'task': {'title': title}}, project)['createdTask']

    def stage(self, task, **fields):
        return self.mutate('stages/create', {'task': task, 'stage': {'title': 'Stage', **fields}})['createdStage']


class ManualEditingTest(ManualApiCase):
    def test_create_update_estimate_and_close(self):
        task = self.task()
        estimate = {'percentLow': 20, 'percentHigh': 40, 'hoursLow': 1, 'hoursHigh': 3,
                    'confidence': 'low', 'note': 'Remaining implementation'}
        state = self.mutate('tasks/update', {'task': task, 'patch': {'estimate': estimate, 'summary': 'Edited'}})
        self.assertEqual(state['tasks'][0]['estimate']['hoursHigh'], 3)
        self.mutate('tasks/update', {'task': task, 'patch': {'estimate': {'percentLow': 50, 'percentHigh': 20}}}, expected_status=409)
        self.mutate('tasks/update', {'task': task, 'patch': {'status': 'done'}}, expected_status=409)
        closed = self.mutate('tasks/close', {'task': task, 'mode': 'auto'})
        self.assertEqual(closed['tasks'][0]['status'], 'done')
        self.mutate('tasks/update', {'task': task, 'patch': {'status': 'done', 'title': 'Closed, edited'}})
        self.mutate('tasks/update', {'task': task, 'patch': {'status': 'active'}}, expected_status=409)
        self.assertEqual(self.mutate('tasks/reopen', {'task': task})['tasks'][0]['status'], 'active')

    def test_create_requires_current_revision_and_valid_task(self):
        before = self.state()['revision']
        self.task()
        status, _ = self.request('/api/v1/tasks/create', {'task': {'title': 'Stale'}, 'expected': before})
        self.assertEqual(status, 409)
        for fields in ({'title': ' '}, {'title': 'Bad', 'weight': True}, {'title': 'Bad', 'status': 'done'},
                       {'title': 'Bad', 'summary': []}, {'title': 'Bad', 'unknown': 1}):
            self.mutate('tasks/create', {'task': fields}, expected_status=409)
        self.assertEqual(len(self.state()['tasks']), 1)

    def test_stage_validation_is_atomic(self):
        task = self.task()
        stage = self.stage(task, id='stable')
        self.assertEqual(stage, 'stable')
        self.mutate('stages/update', {'task': task, 'stage': stage, 'patch': {'title': 'Renamed', 'remaining': ['Test']}})
        revision = self.state()['revision']
        for patch in ({'title': ' '}, {'dependsOn': ['missing']}, {'dependsOn': ['stable']},
                      {'done': 'text'}, {'summary': 1}, {'evidence': [{'path': '../escape'}]}):
            self.mutate('stages/update', {'task': task, 'stage': stage, 'patch': patch}, expected_status=409)
            self.assertEqual(self.state()['revision'], revision)
        self.mutate('stages/create', {'task': task, 'stage': {'id': 'stable', 'title': 'Duplicate'}}, expected_status=409)


if __name__ == '__main__':
    unittest.main()
