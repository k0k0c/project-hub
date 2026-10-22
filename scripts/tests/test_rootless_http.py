"""Standalone browser routes must work without Codex or a code checkout."""
import http.client
from contextlib import closing
import json
import sqlite3
import subprocess
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_portal import PortalServer
from project_registry import ProjectRegistry
from project_settings import read_settings, update_settings


class RootlessHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = ProjectRegistry(Path(self.temp.name)/'data', standalone=True)
        self.server = PortalServer(('127.0.0.1', 0), registry=self.registry)
        self.worker = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .02}, daemon=True)
        self.worker.start()
        self.addCleanup(self.registry.close_connection_pool)
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.worker.join()
        self.wait_for_checkpoint_jobs()

    def wait_for_checkpoint_jobs(self):
        from completion_policy import _jobs, _jobs_lock
        with _jobs_lock:
            jobs = [job for (home, _), job in _jobs.items() if home == str(self.registry.home)]
        for job in jobs:
            job.join(5)
        self.assertTrue(all(not job.is_alive() for job in jobs), 'checkpoint job did not finish')

    def request(self, path, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            connection.request('GET' if body is None else 'POST', path,
                               None if body is None else json.dumps(body), {'Content-Type':'application/json'})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_fresh_home_empty_state_and_project_creation(self):
        status, state = self.request('/api/state')
        self.assertEqual(status, 200, state)
        self.assertTrue(state['projectRequired'])
        self.assertEqual(self.request('/api/v1/projects')[1]['projects'], [])
        status, created = self.request('/api/v1/projects', dict(action='create', name='Example', roots=[], requestId='a'*32))
        self.assertEqual(status, 200, created)
        project = created['project']
        self.assertEqual(project['roots'], [])
        status, summary = self.request('/api/tasks/summary?project='+project['id'])
        self.assertEqual(status, 200, summary)
        self.assertEqual(summary['project']['name'], 'Example')
        status, updated = self.request('/api/v1/projects', dict(action='update', project=project['id'], patch={'name':'Renamed'}, expected=1, requestId='b'*32))
        self.assertEqual(status, 200, updated)
        self.assertEqual(self.request('/api/tasks/summary?project='+project['id'])[1]['project']['name'], 'Renamed')

    def test_task_completion_records_unavailable_git_without_blocking_task(self):
        project = self.registry.create('No checkout', request_id='c'*32)['id']
        base = self.registry.base_store(project)
        self.assertEqual(self.request('/api/version-control?project='+project)[1]['status'], 'workspace_required')
        update_settings(base, {'git': {'autoCommit':True}}, read_settings(base)['revision'])
        revision = self.registry.store(project).snapshot()['revision']
        status, result = self.request('/api/v1/tasks/create?project='+project, dict(expected=revision, task={'title':'Independent task'}))
        self.assertEqual(status, 200, result)
        task = result['createdTask']
        status, closed = self.request('/api/v1/tasks/close?project='+project, dict(expected=result['revision'], task=task, mode='auto'))
        self.assertEqual(status, 200, closed)
        target = next(t for t in closed['tasks'] if t['id']==task)
        self.assertEqual(target['status'], 'done')
        self.assertEqual(target['gitCheckpoint']['reasonCode'], 'workspace_required')
        status, refused = self.request('/api/git/push?project='+project, {'confirm':True})
        self.assertEqual(status, 409, refused)
        self.assertEqual(refused['code'], 'workspace_required')

    def test_task_lifecycle_survives_missing_git_for_plain_workspace(self):
        workspace = Path(self.temp.name) / 'plain-workspace'
        workspace.mkdir()
        (workspace / '.svn').mkdir()
        project = self.registry.create('Plain workspace', roots=[str(workspace)], request_id='e'*32)['id']
        base = self.registry.base_store(project)
        update_settings(base, {'git': {'autoCommit': True}}, read_settings(base)['revision'])

        real_run = subprocess.run
        git_calls = []
        def missing_git(*args, **kwargs):
            command = args[0] if args else kwargs.get('args')
            executable = command[0] if isinstance(command, (list, tuple)) and command else str(command).split()[0]
            if Path(str(executable)).name.lower() in ('git', 'git.exe'):
                git_calls.append(command)
                raise FileNotFoundError('git unavailable for regression test')
            return real_run(*args, **kwargs)

        with mock.patch('subprocess.run', side_effect=missing_git):
            revision = self.registry.store(project).snapshot()['revision']
            status, created = self.request('/api/v1/tasks/create?project='+project,
                                           dict(expected=revision, task={'title':'Rootless lifecycle'}))
            self.assertEqual(status, 200, created)
            task = created['createdTask']
            status, edited = self.request('/api/v1/tasks/update?project='+project,
                                          dict(expected=created['revision'], task=task,
                                               patch={'summary':'Edited while Git is unavailable'}))
            self.assertEqual(status, 200, edited)
            status, closed = self.request('/api/v1/tasks/close?project='+project,
                                          dict(expected=edited['revision'], task=task, mode='auto'))
            self.assertEqual(status, 200, closed)
            self.wait_for_checkpoint_jobs()

            status, summary = self.request('/api/tasks/summary?project='+project)
            self.assertEqual(status, 200, summary)
            target = next(item for item in summary['tasks'] if item['id'] == task)
            self.assertEqual(target['status'], 'done')
            self.assertEqual(target['summary'], 'Edited while Git is unavailable')
            checkpoint = target['gitCheckpoint']
            self.assertEqual(checkpoint['status'], 'unavailable')
            self.assertEqual(checkpoint['reasonCode'], 'no_repository')
            self.assertFalse(checkpoint.get('sha'))
            self.assertFalse(checkpoint.get('commits'))

            status, history = self.request('/api/history?project='+project+'&task='+task)
            self.assertEqual(status, 200, history)
            self.assertTrue(any(event.get('taskId') == task for event in history['events']))
            self.assertEqual(git_calls, [], 'General task operations invoked Git for a plain folder')

    def test_work_begin_report_and_close_without_git_repository(self):
        from plugin_api import ServerHub
        from git_integration import decode_snapshot
        workspace = Path(self.temp.name) / 'source'
        workspace.mkdir()
        project = self.registry.create('Files only', roots=[str(workspace)], request_id='f'*32)['id']
        hub = ServerHub(self.registry)
        with mock.patch('subprocess.run', side_effect=AssertionError('Core work must not require Git')):
            hub.ensure_session('files-only', str(workspace))
            status, created = self.request('/api/v1/tasks/create?project='+project,
                dict(expected=self.registry.store(project).snapshot()['revision'], task={'title':'Files only'}))
            self.assertEqual(status, 200, created)
            task = created['createdTask']
            status, staged = self.request('/api/v1/stages/create?project='+project,
                dict(expected=created['revision'], task=task, stage={'title':'Edit source', 'remaining':['Edit']}))
            self.assertEqual(status, 200, staged)
            work = hub.begin('files-only', task=task, title='Edit source', resources=['file.py'], mode='write', stage=staged['createdStage'])
            (workspace / 'file.py').write_text('value = 1\n')
            with hub.connect() as connection:
                snapshot = decode_snapshot(connection.execute('SELECT git_snapshot FROM work WHERE id=?', (work['work'],)).fetchone()[0])
            self.assertFalse(snapshot['available'])
            completed = hub.report('files-only', work=work['work'], revision=work['revision'], result='Edited', status='done', stage_status='done')
            self.assertEqual(completed['status'], 'done')
            from hub_memory import Memory
            Memory(hub, 'files-only').flush_reports(work=work['work'])
            target = next(t for t in self.registry.store(project).snapshot()['tasks'] if t['id']==task)
            self.assertEqual(target['stages'][0]['status'], 'done')

    def test_first_coordination_read_creates_rootless_compatible_storage(self):
        project = self.registry.create('Independent workspace', request_id='d'*32)['id']
        database = self.registry.home / 'coordination' / 'coordination.sqlite3'
        self.assertFalse(database.exists())
        status, overview = self.request('/api/coordination?project='+project)
        self.assertEqual(status, 200, overview)
        with closing(sqlite3.connect(database)) as connection:
            self.assertEqual(connection.execute('SELECT version FROM meta').fetchone()[0], 2)
            projects = {row[1]:row for row in connection.execute('PRAGMA table_info(projects)')}
            sessions = {row[1]:row for row in connection.execute('PRAGMA table_info(sessions)')}
            self.assertFalse(projects['root'][3])
            self.assertFalse(sessions['workspace'][3])


if __name__ == '__main__':
    unittest.main()
