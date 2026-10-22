"""HTTP isolation uses request-local stores, including overlapping requests."""
import concurrent.futures
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_registry import CodexProjects, ProjectRegistry
from project_portal import PortalServer


class MultiHttpTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name)
        self.catalog=self.base/'catalog.json'
        self.catalog.write_text(json.dumps({'local-projects':{key:dict(id=key,name=key,rootPaths=[str(self.base/key)]) for key in ('a','b')}}))
        self.registry=ProjectRegistry(self.base/'data',CodexProjects(self.catalog))
        self.projects={p['codex_id']:p['id'] for p in self.registry.list()['projects']}
        for name,pid in self.projects.items():
            store=self.registry.store(pid); store.root.mkdir()
            (store.root/'result.log').write_text(name+'-only')
            store.record(dict(kind='task.created',taskId='same-id',title=name,
                              patch=dict(title=name,status='planned',stages=[],sources=[dict(path='result.log',label='Result')])) )
        self.server=PortalServer(('127.0.0.1',0),registry=self.registry)
        self.worker=threading.Thread(target=self.server.serve_forever,daemon=True);self.worker.start()

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.worker.join();self.tmp.cleanup()

    def get(self,path):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        try:
            c.request('GET',path);r=c.getresponse();return r.status,r.read()
        finally:c.close()

    def post(self,path,payload):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        try:
            body=json.dumps(payload).encode()
            c.request('POST',path,body,{'Content-Type':'application/json'})
            r=c.getresponse();return r.status,r.read()
        finally:c.close()

    def test_requests_never_use_implicit_or_other_project(self):
        self.assertEqual(self.get('/api/state')[0],400)
        self.assertEqual(self.get('/api/state?project=unknown')[0],400)
        self.assertEqual(self.get('/api/state?project=a&project=b')[0],400)
        def read(name):
            pid=self.projects[name]
            status,body=self.get('/api/v1/state?project='+pid)
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)['tasks'][0]['title'],name)
            self.assertEqual(self.get('/api/evidence?project='+pid+'&path=result.log'),(200,(name+'-only').encode()))
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(read,['a','b']*5))
        self.assertEqual(self.get('/')[0],200)

    def test_git_endpoint_returns_bounded_projection(self):
        pid = self.projects['a']
        status, body = self.get('/api/git?project=' + pid)
        self.assertEqual(status, 200)
        projection = json.loads(body)
        self.assertEqual(set(projection), {'repository', 'summary', 'tasks', 'commits', 'pushes', 'unassigned'})
        self.assertFalse(projection['repository']['available'])
        self.assertEqual(projection['tasks'], [])

    def test_new_project_appears_without_restarting(self):
        rows=json.loads(self.catalog.read_text())
        rows['local-projects']['c']=dict(id='c',name='C',rootPaths=[str(self.base/'c')])
        self.catalog.write_text(json.dumps(rows))
        status,body=self.get('/api/v1/projects')
        self.assertEqual(status,200)
        pid=next(p['id'] for p in json.loads(body)['projects'] if p['codex_id']=='c')
        self.assertEqual(json.loads(self.get('/api/state?project='+pid)[1])['tasks'],[])

    def test_closed_task_can_be_reopened_through_http_contract(self):
        pid=self.projects['a']
        store=self.registry.store(pid)
        store.record(dict(taskId='same-id',kind='task.updated',title='Закрытие',
                          patch={'status':'done','closedManually':True}))
        state=store.snapshot()
        status,body=self.post('/api/v1/tasks/reopen?project='+pid,
                              {'task':'same-id','expected':state['revision']})
        self.assertEqual(status,200)
        reopened=json.loads(body)
        self.assertEqual(reopened['tasks'][0]['status'],'active')
        self.assertEqual(reopened['events'][0]['title'],'Задача переоткрыта')

    def test_task_mutations_reject_stale_revision_without_changing_state(self):
        pid = self.projects['a']
        store = self.registry.store(pid)
        store.record(dict(kind='task.created', taskId='target', title='Target',
                          patch={'title': 'Target', 'status': 'active', 'stages': []}))
        for route, fields in (
                ('update', {'patch': {'summary': 'stale'}}),
                ('close', {'mode': 'auto'}),
                ('reopen', {}),
                ('link', {'target': 'target', 'type': 'related'})):
            with self.subTest(route=route):
                store.record(dict(taskId='same-id', kind='task.updated', title='Prepare',
                                  patch={'status': 'done' if route == 'reopen' else 'active'}))
                stale = store.snapshot()['revision']
                store.record(dict(taskId='same-id', kind='task.updated', title='Newer edit',
                                  patch={'summary': 'newer'}))
                before = store.snapshot()
                status, body = self.post('/api/v1/tasks/' + route + '?project=' + pid,
                                         {'task': 'same-id', 'expected': stale, **fields})
                self.assertEqual(status, 409, body.decode())
                self.assertEqual(store.snapshot()['revision'], before['revision'])
                status, body = self.post('/api/v1/tasks/' + route + '?project=' + pid,
                                         {'task': 'same-id', 'expected': before['revision'], **fields})
                self.assertEqual(status, 200, body.decode())

    def test_stale_close_does_not_attempt_git_checkpoint(self):
        pid = self.projects['a']
        store = self.registry.store(pid)
        store.record(dict(taskId='same-id', kind='stage.created', stageId='only', title='Done',
                          patch={'title': 'Done', 'status': 'done'}))
        stale = store.snapshot()['revision']
        store.record(dict(taskId='same-id', kind='note', title='Concurrent change'))
        with patch('hub_core.Hub._commit_single_stage') as commit:
            status, body = self.post('/api/v1/tasks/close?project=' + pid,
                                     {'task': 'same-id', 'expected': stale, 'mode': 'auto'})
            self.assertEqual(status, 409, body.decode())
            commit.assert_not_called()
        self.assertEqual(store.snapshot()['tasks'][0]['status'], 'planned')

    def test_concurrent_updates_have_only_one_winner(self):
        pid = self.projects['a']
        store = self.registry.store(pid)
        revision = store.snapshot()['revision']
        def update(value):
            return self.post('/api/v1/tasks/update?project=' + pid,
                             {'task': 'same-id', 'expected': revision,
                              'patch': {'summary': value}})[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(update, ['first', 'second']))
        self.assertEqual(sorted(statuses), [200, 409])

    def test_push_reports_journal_failure_without_claiming_push_failed(self):
        pid = self.projects['a']
        with patch('project_portal.push_repository', return_value={'branch': 'main', 'commits': []}), \
                patch('task_transfer.ProjectView.record', side_effect=OSError('journal unavailable')):
            status, body = self.post('/api/git/push?project=' + pid, {'confirm': True})
        self.assertEqual(status, 200)
        result = json.loads(body)
        self.assertFalse(result['eventRecorded'])
        self.assertIn('journal unavailable', result['eventWarning'])
