"""Checks ingestion uses real HTTP against disposable project catalogs."""
from concurrent.futures import ThreadPoolExecutor
from test_manual_editing import ManualApiCase
from check_runs import ingest, list_runs
from task_transfer import transfer


class ChecksHttpTest(ManualApiCase):
    def start(self, task=None, **fields):
        return dict(runId='run-one', task=task or self.task(), profile='custom-profile',
                    command=['test-runner', ''], scope=['src'], revision={'head': None, 'dirty': True},
                    startedAt='2026-09-19T10:00:00Z', status='running', **fields)

    def finish(self, start, **fields):
        return dict(start, **dict(status='passed', exitCode=0, durationMs=100,
                                 finishedAt='2026-09-19T10:00:01Z', **fields))

    def test_lifecycle_idempotence_and_projection(self):
        body = self.start(title='Verify publication lifecycle')
        body['stage'] = self.stage(body['task'])
        body['log'] = 'proof.txt'
        status, first = self.request('/api/v1/checks', body)
        self.assertEqual(status, 200, first)
        status, again = self.request('/api/v1/checks', body)
        self.assertTrue(again['duplicate'])
        end = self.finish(body)
        self.assertEqual(self.request('/api/v1/checks', end)[0], 200)
        self.assertTrue(self.request('/api/v1/checks', end)[1]['duplicate'])
        row = self.state()['checks'][0]
        self.assertEqual(row['status'], 'passed')
        self.assertEqual(row['profile'], 'custom-profile')
        self.assertEqual(row['title'], 'Verify publication lifecycle')
        self.assertEqual(row['stageId'], body['stage'])
        self.assertEqual(row['launchProject'], self.pid)
        self.assertEqual(self.state()['checkCount'], 1)
        self.assertEqual(row['evidence'][0]['path'], 'proof.txt')
        self.assertEqual(self.request('/api/v1/checks')[1]['runs'][0]['runId'], body['runId'])
        self.assertEqual(self.request('/api/v1/checks', dict(end, exitCode=3, status='failed'))[0], 409)
        self.assertEqual(self.request('/api/v1/checks', dict(body, profile='different'))[0], 409)
        self.assertEqual(self.request('/api/v1/checks', dict(body, title='Different purpose'))[0], 409)

    def test_invalid_atomic_and_requires_start(self):
        body = self.start()
        before = self.state()['revision']
        invalid = [self.finish(body), dict(body, extra=True), dict(body, command='shell string'),
                   dict(body, scope=['../escape']), dict(body, log='C:/secret'),
                   dict(body, log='..\\secret'), dict(body, evidence=[{'path':'proof.txt'}]),
                   dict(body, revision={'dirty':1}), dict(body, startedAt='2026-09-19'),
                   dict(body, counts={'passed': 1}), dict(body, runId='../bad'),
                   dict(body, finishedAt='2026-09-19T10:00:01Z'), dict(body, stage='missing')]
        for item in invalid:
            with self.subTest(item=item):
                self.assertEqual(self.request('/api/v1/checks', item)[0], 409)
                self.assertEqual(self.state()['revision'], before)
        ingest(self.registry, self.pid, body)
        for patch in ({'exitCode':None}, {'exitCode':True}, {'durationMs':-1},
                      {'finishedAt':'2026-09-18T10:00:01Z'}, {'counts':{'passed':-1}}):
            self.assertEqual(self.request('/api/v1/checks', dict(self.finish(body), **patch))[0], 409)

    def test_project_isolation_and_arbitrary_origin_owner(self):
        task = self.task()
        other = self.projects['b']
        transfer(self.registry, self.pid, other, task, self.state()['revision'], 'move-task')
        body = self.start(task=task, log='proof.txt', evidence=[{'label':'proof', 'path':'proof.txt'}])
        self.assertEqual(self.request('/api/v1/checks', body)[0], 409)
        first = ingest(self.registry, other, body)
        self.assertEqual(first['run']['originProject'], self.pid)
        self.assertEqual(first['run']['ownerProject'], other)
        self.assertEqual(first['run']['launchProject'], other)
        self.assertTrue(ingest(self.registry, other, body)['duplicate'])
        end = self.finish(body)
        ingest(self.registry, other, end)
        self.assertTrue(ingest(self.registry, other, end)['duplicate'])
        self.assertEqual(self.state()['checkCount'], 0)
        state = self.state(other)
        self.assertEqual(state['checks'][0]['evidence'][0]['path'], 'proof.txt')
        # Terminal receipt retry remains valid after moving the task back.
        transfer(self.registry, other, self.pid, task, state['revision'], 'return-task')
        self.assertTrue(ingest(self.registry, other, end)['duplicate'])
        row = self.state()['checks'][0]
        self.assertEqual(row['ownerProject'], self.pid)
        self.assertEqual(row['evidence'][0]['path'], 'hub-source/' + other + '/proof.txt')

    def test_running_checks_protect_task_and_stage(self):
        body = self.start()
        body['stage'] = self.stage(body['task'])
        ingest(self.registry, self.pid, body)
        with self.assertRaisesRegex(ValueError, 'unfinished check'):
            transfer(self.registry, self.pid, self.projects['b'], body['task'], self.state()['revision'], 'move')
        status, _ = self.request('/api/v1/stages/delete', {'task':body['task'], 'stage':body['stage'],
                                                           'expected':self.state()['revision']})
        self.assertEqual(status, 409)
        end = dict(body, status='unknown', finishedAt='2026-09-19T10:01:00Z', summary='Process lost')
        ingest(self.registry, self.pid, end)
        self.assertEqual(self.state()['checks'][0]['status'], 'unknown')
        transfer(self.registry, self.pid, self.projects['b'], body['task'], self.state()['revision'], 'move')

    def test_pagination_and_no_runid_reassignment(self):
        body = self.start()
        for index in range(33):
            ingest(self.registry, self.pid, dict(body, runId='run-' + str(index)))
        self.assertEqual(len(self.state()['checks']), 30)
        page = list_runs(self.registry.store(self.pid), 0, 20)
        self.assertEqual(page['total'], 33)
        self.assertEqual(page['next'], 20)
        self.assertEqual(len(list_runs(self.registry.store(self.pid), 20, 20)['runs']), 13)
        other_task = self.task(project=self.projects['b'])
        with self.assertRaisesRegex(ValueError, 'different launch'):
            ingest(self.registry, self.projects['b'], dict(body, runId='run-0', task=other_task))

    def test_concurrent_duplicate_delivery_is_serialized(self):
        body = self.start()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: ingest(self.registry, self.pid, body), range(2)))
        self.assertEqual(sorted(row['duplicate'] for row in results), [False, True])
        self.assertEqual(self.state()['checkCount'], 1)
        end = self.finish(body)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: ingest(self.registry, self.pid, end), range(2)))
        self.assertEqual(sorted(row['duplicate'] for row in results), [False, True])
        events = [e for e in self.state()['allEvents'] if e.get('runId') == body['runId']]
        self.assertEqual(len(events), 2)

    def test_failed_interrupted_and_restart_are_not_passed(self):
        from project_registry import ProjectRegistry
        body = self.start()
        ingest(self.registry, self.pid, body)
        end = dict(body, status='interrupted', exitCode=130, finishedAt='2026-09-19T10:01:00Z')
        ingest(self.registry, self.pid, end)
        restarted = ProjectRegistry(self.registry.home, self.registry.catalog)
        self.assertEqual(restarted.store(self.pid).snapshot()['checks'][0]['status'], 'interrupted')
        self.assertTrue(ingest(restarted, self.pid, end)['duplicate'])
        with self.assertRaisesRegex(ValueError, 'terminal result'):
            ingest(restarted, self.pid, self.finish(body))

    def test_mcp_bound_project_contract(self):
        from plugin_api import call
        body = self.start()
        root = str(self.registry.base_store(self.pid).root)
        request = dict(cwd=root, session='checks-test-session', tool='hub_check', arguments=body)
        result = call(self.registry, request)
        self.assertEqual(result['run']['ownerProject'], self.pid)
        self.assertTrue(call(self.registry, request)['duplicate'])
