import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_registry import ProjectRegistry, CodexProjects
from portal_asgi import PortalASGI


class ASGIContracts(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        catalog = self.root / 'catalog.json'
        catalog.write_text(json.dumps({'local-projects': {'fixture': {'id':'fixture','name':'Fixture','rootPaths':[str(self.root)]}}}))
        self.registry = ProjectRegistry(self.root / 'data', CodexProjects(catalog))
        self.project = self.registry.list()['projects'][0]['id']
        self.view = self.registry.store(self.project)
        (self.root / 'proof.txt').write_text('proof')
        self.view.record(dict(kind='task.created',taskId='task',title='Task',patch={
            'title':'Task','status':'active','stages':[],'sources':[{'path':'proof.txt'}]}))
        self.app = PortalASGI(self.registry, 18769, threads=2, pending=4)

    async def asyncTearDown(self):
        self.app.service.stopping.set()
        await asyncio.to_thread(self.app.executor.shutdown, wait=True, cancel_futures=True)
        await asyncio.to_thread(self.app.service.server_close)
        self.directory.cleanup()

    def scope(self, path, *, method='GET', headers=None):
        route, _, query = path.partition('?')
        return dict(type='http',method=method,path=route,raw_path=route.encode(),query_string=query.encode(),
                    http_version='1.1',headers=headers or [(b'host',b'127.0.0.1:18769')],client=('127.0.0.1',1))

    async def request(self, path, *, method='GET', body=b'', headers=None):
        sent = []
        async def receive():
            return {'type':'http.request','body':body,'more_body':False}
        async def send(event):
            sent.append(event)
        await self.app(self.scope(path,method=method,headers=headers), receive, send)
        return sent[0]['status'], dict(sent[0]['headers']), b''.join(e.get('body',b'') for e in sent[1:])

    async def test_shared_dispatch_headers_state_files_and_current_ownership(self):
        status, headers, data = await self.request('/api/tasks/summary?project=' + self.project)
        self.assertEqual(200,status)
        self.assertIn(b'server-timing',headers)
        state = json.loads(data)
        self.assertFalse(state['tasks'][0]['detailLoaded'])
        status, _, detail = await self.request('/api/tasks/detail?task=task&project=' + self.project)
        self.assertEqual(state['revision'],json.loads(detail)['revision'])
        status, _, data = await self.request('/api/evidence?path=proof.txt&project=' + self.project)
        self.assertEqual((200,b'proof'),(status,data))
        status, _, _ = await self.request('/api/evidence?path=outside.txt&project=' + self.project)
        self.assertEqual(400,status)

    async def test_spawn_dispatch_survives_a_worker_exit_without_replaying_request(self):
        await asyncio.to_thread(self.app.executor.shutdown, wait=True, cancel_futures=True)
        await asyncio.to_thread(self.app.service.server_close)
        self.app = PortalASGI(self.registry, 18769, processes=2)
        status, headers, data = await self.request('/api/evidence?path=proof.txt&project=' + self.project)
        self.assertEqual((200,b'proof'),(status,data))
        previous = self.app.executor
        worker = next(iter(previous._processes.values()))
        worker.terminate()
        await asyncio.to_thread(worker.join, 5)
        status, _, data = await self.request('/api/tasks/summary?project=' + self.project)
        self.assertEqual(503,status)
        self.assertIn(b'refresh before retrying',data)
        self.assertIsNot(previous,self.app.executor)
        status, _, data = await self.request('/api/tasks/detail?task=task&project=' + self.project)
        self.assertEqual(200,status)
        self.assertEqual('task',json.loads(data)['task']['id'])

    async def test_http_state_and_git_load_only_bounded_history(self):
        models = self.registry.read_models
        self.view.record(dict(kind='git.push',taskId='__project__',title='Push receipt',git={'branch':'main'}))
        models.snapshot(self.view,observations=False,summary=True)
        history = models.history
        def bounded(*args,**kwargs):
            if kwargs.get('limit',40) > 100:
                raise AssertionError('HTTP read requested complete journal')
            return history(*args,**kwargs)
        with patch.object(models,'history',side_effect=bounded), \
                patch('project_portal.cached_read_projection',return_value=({'available':True,'changedFiles':[]},[])):
            status, _, body = await self.request('/api/state?view=portal&project=' + self.project)
            self.assertEqual(200,status,body)
            self.assertNotIn('allEvents',json.loads(body))
            status, _, body = await self.request('/api/git?project=' + self.project)
            self.assertEqual(200,status,body)
            self.assertEqual('Push receipt',json.loads(body)['pushes'][0]['title'])

    async def test_internal_task_presentation_filter_is_limited_to_portal_state_and_summary(self):
        from unittest.mock import patch
        calls = []
        def observe(registry, project, snapshot):
            calls.append((registry, project))
            return snapshot
        with patch('internal_operations.filter_portal_internal_tasks', side_effect=observe):
            status, _, _ = await self.request('/api/state?view=portal&project=' + self.project)
            self.assertEqual(status, 200)
            self.assertEqual(len(calls), 1)
            status, _, _ = await self.request('/api/state?project=' + self.project)
            self.assertEqual(status, 200)
            self.assertEqual(len(calls), 1)
            status, _, _ = await self.request('/api/tasks/summary?project=' + self.project)
            self.assertEqual(status, 200)
            self.assertEqual(len(calls), 2)
            status, _, _ = await self.request('/api/tasks/detail?task=task&project=' + self.project)
            self.assertEqual(status, 200)
            self.assertEqual(len(calls), 2)

    async def test_host_body_limits_and_bounded_queue_are_enforced(self):
        self.assertEqual(403,(await self.request('/api/health',headers=[(b'host',b'outside.example')]))[0])
        self.assertEqual(400,(await self.request('/api/health',headers=[(b'host',b'localhost:18769'),
            (b'content-length',b'1'),(b'content-length',b'1')]))[0])
        self.app.active = self.app.pending
        self.assertEqual(503,(await self.request('/api/health'))[0])
        self.app.active = 0

    async def test_parallel_mcp_calls_do_not_use_large_upload_slots(self):
        entered, release = asyncio.Event(), asyncio.Event()
        count = 0
        async def receive():
            nonlocal count
            count += 1
            if count == 4:
                entered.set()
            await release.wait()
            return {'type':'http.request','body':b'{}'}
        async def invoke():
            sent=[]
            async def send(event): sent.append(event)
            await self.app(self.scope('/mcp',method='POST'),receive,send)
            return sent[0]['status']
        # A route can accept large uploads without every small body reserving
        # their memory. Also cover two genuinely large uploads already active.
        self.app.large_bodies = 2
        tasks=[asyncio.create_task(invoke()) for _ in range(4)]
        try:
            await asyncio.wait_for(entered.wait(),1)
            self.assertEqual(self.app.active,4)
            release.set()
            statuses=await asyncio.gather(*tasks)
            self.assertNotIn(503,statuses)
            self.assertEqual(self.app.large_bodies,2)
        finally:
            release.set()
            await asyncio.gather(*tasks,return_exceptions=True)
            self.app.large_bodies = 0

    async def test_chunked_upload_reserves_memory_before_dispatch_and_releases_on_disconnect(self):
        queues=[asyncio.Queue() for _ in range(2)]
        sent=[[],[]]
        async def hold(index):
            async def send(event): sent[index].append(event)
            await self.app(self.scope('/mcp',method='POST'),queues[index].get,send)
        tasks=[asyncio.create_task(hold(i)) for i in range(2)]
        try:
            for queue in queues:
                queue.put_nowait({'type':'http.request','body':b'x'*16_001,'more_body':True})
            for _ in range(30):
                if self.app.large_bodies == 2: break
                await asyncio.sleep(.01)
            self.assertEqual(self.app.large_bodies,2)
            status,_,_=await self.request('/mcp',method='POST',body=b'x'*16_001)
            self.assertEqual(status,503)
            # Small MCP calls still reach authentication rather than overload.
            self.assertNotEqual((await self.request('/mcp',method='POST',body=b'{}'))[0],503)
        finally:
            for queue in queues: queue.put_nowait({'type':'http.disconnect'})
            await asyncio.gather(*tasks)
        self.assertEqual((self.app.active,self.app.large_bodies),(0,0))

    async def test_compact_mutation_validates_revision_without_full_journal_response(self):
        revision = self.view.task_context('task')['revision']
        from task_transfer import ProjectView
        with patch.object(ProjectView, 'snapshot', side_effect=AssertionError('full journal snapshot')):
            status, _, payload = await self.request('/api/v1/tasks/update?project=' + self.project + '&view=summary',
                method='POST', headers=[(b'host',b'localhost:18769'),(b'content-type',b'application/json')],
                body=json.dumps({'task':'task','expected':revision,'patch':{'summary':'new'}}).encode())
        self.assertEqual(200, status, payload)
        state = json.loads(payload)
        self.assertNotIn('allEvents', state)
        self.assertNotEqual(revision, state['revision'])
        self.assertFalse(state['tasks'][0]['detailLoaded'])
        self.assertEqual('new', self.view.task_context('task')['tasks'][0]['summary'])
        status, _, _ = await self.request('/api/v1/tasks/update?project=' + self.project + '&view=summary',
            method='POST', headers=[(b'host',b'localhost:18769'),(b'content-type',b'application/json')],
            body=json.dumps({'task':'task','expected':revision,'patch':{'summary':'stale'}}).encode())
        self.assertEqual(409, status)

    async def test_write_ack_is_durable_and_does_not_prepare_a_display_page(self):
        models = self.registry.read_models
        revision = models.domain_key(self.project)
        path = '/api/v1/tasks/update?project=' + self.project + '&view=ack'
        headers = [(b'host',b'localhost:18769'),(b'content-type',b'application/json')]
        with patch.object(models,'prepare_view',side_effect=AssertionError('display rebuild in write acknowledgement')):
            status, _, payload = await self.request(path, method='POST',headers=headers,
                body=json.dumps({'task':'task','expected':revision,'patch':{'summary':'acknowledged'}}).encode())
        self.assertEqual(200,status,payload)
        acknowledgement = json.loads(payload)
        self.assertTrue(acknowledgement['accepted'])
        self.assertNotEqual(revision,acknowledgement['revision'])
        self.assertLess(len(payload),256)
        self.assertEqual('acknowledged',self.view.task_context('task')['tasks'][0]['summary'])
        status, _, _ = await self.request(path,method='POST',headers=headers,
            body=json.dumps({'task':'task','expected':revision,'patch':{'summary':'stale'}}).encode())
        self.assertEqual(409,status)

    async def test_route_limits_slow_bodies_and_subscriber_admission_release_resources(self):
        self.assertEqual(413, (await self.request('/api/health', body=b'x'))[0])
        self.assertEqual(413, (await self.request('/api/v1/plugin/call', method='POST',
            headers=[(b'host', b'localhost:18769'), (b'content-length', b'16001')]))[0])
        self.app.subscribers = self.app.subscriber_limit
        self.assertEqual(503, (await self.request('/api/events?project=' + self.project))[0])
        self.app.subscribers = 0
        self.app.body_timeout = .01
        sent = []
        async def slow():
            await asyncio.sleep(1)
        async def send(event): sent.append(event)
        await self.app(self.scope('/api/v1/plugin/call', method='POST'), slow, send)
        self.assertEqual(408, sent[0]['status'])
        self.assertEqual((0,0), (self.app.active,self.app.large_bodies))

    async def test_one_hundred_sse_subscribers_do_not_occupy_dispatch_workers(self):
        queues, tasks, ready = [], [], []
        for _ in range(100):
            queue = asyncio.Queue()
            queue.put_nowait({'type':'http.request','body':b''})
            marker = asyncio.Event()
            async def send(event, marker=marker):
                if b'event: revision' in event.get('body',b''):
                    marker.set()
            queues.append(queue)
            ready.append(marker.wait())
            tasks.append(asyncio.create_task(self.app(self.scope('/api/events?project=' + self.project), queue.get, send)))
        try:
            with patch.object(self.app.executor,'submit', wraps=self.app.executor.submit) as submit:
                await asyncio.wait_for(asyncio.gather(*ready), timeout=8)
                self.assertEqual(0,submit.call_count)
                self.assertEqual(200,(await self.request('/api/health'))[0])
                self.assertEqual(0,submit.call_count)
        finally:
            for queue in queues:
                queue.put_nowait({'type':'http.disconnect'})
            await asyncio.wait_for(asyncio.gather(*tasks),timeout=4)
            self.assertEqual(0, self.app.subscribers)

    async def test_health_uses_serving_process_with_process_workers(self):
        await asyncio.to_thread(self.app.executor.shutdown, wait=True, cancel_futures=True)
        await asyncio.to_thread(self.app.service.server_close)
        self.app = PortalASGI(self.registry, 18769, processes=2)
        with patch.object(self.app.executor, 'submit', side_effect=AssertionError('health must not use request workers')):
            first = await self.request('/api/health')
            second = await self.request('/api/health')
        self.assertEqual(200, first[0]); self.assertEqual(200, second[0])
        for name, value in ((b'content-type', b'application/json; charset=utf-8'), (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff')):
            self.assertEqual(value, first[1][name]); self.assertEqual(value, second[1][name])
        self.assertEqual(os.getpid(), json.loads(first[2])['pid'])
        self.assertEqual(os.getpid(), json.loads(second[2])['pid'])
    async def test_unhandled_dispatch_error_is_logged_and_health_remains_available(self):
        import runtime_diagnostics as diagnostics
        diagnostics.configure('fixture', self.root/'diagnostics')
        try:
            with patch.object(self.app,'dispatch',side_effect=RuntimeError('fixture request failure')):
                status,_,data=await self.request('/api/tasks/summary?project='+self.project)
            self.assertEqual(status,500)
            self.assertEqual(json.loads(data)['code'],'request_failed')
            self.assertEqual((await self.request('/api/health'))[0],200)
            incident=diagnostics.report()['incident']
            self.assertEqual(incident['route'],'/api/tasks/summary')
            self.assertNotIn('query_string',incident)
            status,_,data=await self.request('/api/runtime/diagnostics')
            self.assertEqual(status,200)
            self.assertEqual(json.loads(data)['incident']['errorType'],'RuntimeError')
        finally:
            diagnostics.cleanup()
