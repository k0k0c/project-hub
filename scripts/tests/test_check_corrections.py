"""Explicit check corrections preserve journal receipts in disposable catalogs."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from unittest.mock import Mock

from test_manual_editing import ManualApiCase
from check_runs import IMMUTABLE, ingest, list_runs
from task_transfer import transfer


class CheckCorrectionsTest(ManualApiCase):
    def launch(self):
        task = self.task()
        body = dict(runId='correctable-run', task=task, stage=self.stage(task),
                    title='Correction regression', profile='focused', profileVersion='v1',
                    command=['runner', '--test'], scope=['src'],
                    revision={'head': 'abc', 'dirty': True, 'fingerprint': 'original'},
                    startedAt='2026-09-19T10:00:00Z', status='running', log='proof.txt')
        ingest(self.registry, self.pid, body)
        return body

    def finish(self, body):
        end = dict(body, status='failed', exitCode=1, durationMs=1000,
                   finishedAt='2026-09-19T10:00:01Z', counts={'failed': 1})
        result = ingest(self.registry, self.pid, end)
        return end, result['run']['id']

    def corrected(self, end, event, **patch):
        return dict(end, **dict(status='passed', exitCode=0, counts={'passed': 1},
                               correction={'reason': 'Original exit code was misreported',
                                           'expectedEvent': event}, **patch))

    def events(self):
        return [e for e in self.state()['allEvents'] if e.get('runId') == 'correctable-run']

    def test_http_projection_audit_and_deterministic_retries(self):
        start = self.launch()
        end, event = self.finish(start)
        original = deepcopy(self.events())
        correction = self.corrected(end, event)
        status, result = self.request('/api/v1/checks', correction)
        self.assertEqual(status, 200, result)
        self.assertFalse(result['duplicate'])
        row = self.state()['checks'][0]
        self.assertEqual(result['run']['id'], row['id'])
        self.assertEqual(result['run']['status'], 'passed')
        self.assertEqual(result['run']['correction'], correction['correction'])
        self.assertEqual(row['status'], 'passed')
        self.assertEqual(row['kind'], 'check.corrected')
        self.assertEqual(row['correction'], correction['correction'])
        self.assertEqual(row['detail'], correction['correction']['reason'])
        self.assertEqual(self.events()[:2], original)
        for key in IMMUTABLE:
            self.assertEqual(row.get(key), start.get(key))
        before = self.state()['revision']
        retry = dict(reversed(list(correction.items())))
        again = ingest(self.registry, self.pid, retry)
        self.assertTrue(again['duplicate'])
        self.assertEqual(again['run']['id'], row['id'])
        self.assertEqual(self.state()['revision'], before)
        self.assertEqual(list_runs(self.registry.store(self.pid))['runs'][0]['id'], row['id'])
        from project_registry import ProjectRegistry
        restarted = ProjectRegistry(self.registry.home, self.registry.catalog)
        self.assertEqual(restarted.store(self.pid).snapshot()['checks'][0]['id'], row['id'])

    def test_chain_stale_conflicts_and_old_replays(self):
        start = self.launch()
        end, event = self.finish(start)
        first = self.corrected(end, event)
        current = ingest(self.registry, self.pid, first)['run']
        stale = self.corrected(end, event, summary='Concurrent different correction')
        with self.assertRaisesRegex(ValueError, 'result changed'):
            ingest(self.registry, self.pid, stale)
        second = dict(end, correction={'reason': 'Later evidence confirms failure',
                                      'expectedEvent': current['id']})
        latest = ingest(self.registry, self.pid, second)['run']
        for payload in (start, end, first, second):
            self.assertTrue(ingest(self.registry, self.pid, payload)['duplicate'])
        self.assertEqual(len(self.events()), 4)
        self.assertEqual(self.state()['checks'][0]['id'], latest['id'])
        ordinary = self.corrected(end, event)
        ordinary.pop('correction')
        with self.assertRaisesRegex(ValueError, 'terminal result'):
            ingest(self.registry, self.pid, ordinary)
        with self.assertRaisesRegex(ValueError, 'different content'):
            ingest(self.registry, self.pid, dict(end, summary='Silent mutation'))

    def test_documented_failure_correction_does_not_invent_exit_code(self):
        start = self.launch()
        ingest(self.registry, self.pid, start)
        end = dict(start, status='passed', exitCode=0, finishedAt='2026-09-19T10:00:01Z')
        event = ingest(self.registry, self.pid, end)['run']['id']
        corrected = dict(end, status='failed', exitCode=None, log='proof.txt',
                         summary='Build log confirms failure; original process exit code was not retained.',
                         correction=dict(reason='Incorrect passed result', expectedEvent=event))
        for invalid in (dict(corrected, exitCode=0), dict(corrected, summary=''),
                        {k: v for k, v in corrected.items() if k != 'log'}):
            with self.assertRaises(ValueError):
                ingest(self.registry, self.pid, invalid)
        result = ingest(self.registry, self.pid, corrected)
        self.assertEqual(result['run']['status'], 'failed')
        self.assertIsNone(result['run']['exitCode'])
        self.assertTrue(ingest(self.registry, self.pid, corrected)['duplicate'])
        self.assertEqual(self.events()[1]['check']['exitCode'], 0)

    def test_validation_and_immutable_identity_are_atomic(self):
        start = self.launch()
        correction = self.corrected(dict(start, finishedAt='2026-09-19T10:00:01Z'), 'missing')
        with self.assertRaisesRegex(ValueError, 'result changed'):
            ingest(self.registry, self.pid, correction)
        end, event = self.finish(start)
        good = self.corrected(end, event)
        invalid = [dict(good, correction=value) for value in
                   ({}, None, {'reason': ' ', 'expectedEvent': event},
                    {'reason': 'x' * 1201, 'expectedEvent': event},
                    {'reason': 'Fix', 'expectedEvent': ''},
                    {'reason': 'Fix', 'expectedEvent': event, 'extra': True})]
        invalid += [dict(start, correction=good['correction']), dict(good, exitCode=1),
                    dict(good, log='../escape'), dict(good, launchProject=self.pid)]
        for key, value in dict(runId='unknown-run', task='another-task', stage='another-stage',
                               title='Changed', profile='other', profileVersion='v2',
                               command=['other'], scope=[], revision={}).items():
            invalid.append(dict(good, **{key: value}))
        before = self.state()['revision']
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(self.request('/api/v1/checks', payload)[0], 409)
                self.assertEqual(self.state()['revision'], before)
        with self.assertRaisesRegex(ValueError, 'another project'):
            ingest(self.registry, self.projects['b'], good)
        self.assertEqual(self.state()['revision'], before)

    def test_bad_future_start_can_be_marked_unknown_without_rerunning(self):
        start = self.launch()
        original = deepcopy(self.events())
        event = original[0]['id']
        fixed = dict(start, startedAt=None, status='passed', exitCode=0,
                     finishedAt='2026-09-19T09:51:41Z',
                     summary='Original start was entered incorrectly; log confirms exit 0 and finish, start is unknown.',
                     correction=dict(reason='Repair mistaken future start', expectedEvent=event))
        status, result = self.request('/api/v1/checks', fixed)
        self.assertEqual(status, 200, result)
        row = self.state()['checks'][0]
        self.assertEqual(result['run']['id'], row['id'])
        self.assertIsNone(row['startedAt'])
        self.assertEqual(row['finishedAt'], fixed['finishedAt'])
        self.assertEqual(self.events()[:1], original)
        self.assertEqual(len(self.events()), 2)
        self.assertEqual(self.state()['checks'][0]['status'], 'passed')
        for payload in (start, fixed):
            self.assertTrue(ingest(self.registry, self.pid, payload)['duplicate'])
        stale = dict(fixed, summary='Competing recovery')
        with self.assertRaisesRegex(ValueError, 'result changed'):
            ingest(self.registry, self.pid, stale)

    def test_known_start_correction_preserves_identity_and_chronology(self):
        start = self.launch()
        end, event = self.finish(start)
        fixed = self.corrected(end, event, startedAt='2026-09-19T09:59:59Z',
                               summary='Execution log supplies the real launch timestamp')
        result = ingest(self.registry, self.pid, fixed)['run']
        self.assertEqual(result['startedAt'], fixed['startedAt'])
        second = dict(fixed, startedAt=None, correction=dict(
            reason='Timestamp source was unreliable', expectedEvent=result['id']))
        latest = ingest(self.registry, self.pid, second)['run']
        for payload in (start, end, fixed, second):
            self.assertTrue(ingest(self.registry, self.pid, payload)['duplicate'])
        self.assertEqual(self.state()['checks'][0]['id'], latest['id'])
        before = self.state()['revision']
        invalid = [dict(second, correction=dict(reason='Bad', expectedEvent=latest['id']),
                        startedAt='2026-09-19T11:00:00Z'),
                   dict(fixed, summary=''),
                   {k: v for k, v in second.items() if k != 'log'},
                   dict(second, command=['different-command']),
                   dict(start, startedAt=None),
                   dict(start, startedAt='2026-09-19T09:59:59Z')]
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                ingest(self.registry, self.pid, payload)
            self.assertEqual(self.state()['revision'], before)

    def test_running_start_change_requires_documented_correction(self):
        start = self.launch()
        event = self.events()[0]['id']
        finish = dict(start, startedAt='2026-09-19T09:59:59Z', status='passed',
                      finishedAt='2026-09-19T10:00:01Z', exitCode=0)
        with self.assertRaisesRegex(ValueError, 'different launch metadata'):
            ingest(self.registry, self.pid, finish)
        fixed = dict(finish, correction=dict(reason='Incorrect start', expectedEvent=event))
        with self.assertRaisesRegex(ValueError, 'evidence and summary'):
            ingest(self.registry, self.pid, fixed)
        fixed['summary'] = 'The execution log records the actual launch time.'
        self.assertEqual(ingest(self.registry, self.pid, fixed)['run']['status'], 'passed')

    def test_concurrent_correction_compare_and_swap(self):
        end, event = self.finish(self.launch())
        good = self.corrected(end, event)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: ingest(self.registry, self.pid, good), range(2)))
        self.assertEqual(sorted(row['duplicate'] for row in results), [False, True])
        current = results[0]['run']['id']
        def submit(reason):
            try:
                return ingest(self.registry, self.pid, dict(end, correction={
                    'reason': reason, 'expectedEvent': current}))
            except ValueError as error:
                return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, ['Evidence A', 'Evidence B']))
        self.assertEqual(sum(isinstance(row, dict) for row in results), 1)
        self.assertTrue(any(isinstance(row, str) and 'result changed' in row for row in results))
        self.assertEqual(len(self.events()), 4)

    def test_transfer_retains_launch_project_and_evidence(self):
        end, event = self.finish(self.launch())
        other = self.projects['b']
        transfer(self.registry, self.pid, other, end['task'], self.state()['revision'], 'move')
        good = self.corrected(end, event)
        result = ingest(self.registry, other, good)
        self.assertEqual(result['run']['launchProject'], self.pid)
        self.assertEqual(result['run']['ownerProject'], other)
        self.assertTrue(ingest(self.registry, self.pid, good)['duplicate'])
        row = self.state(other)['checks'][0]
        self.assertEqual(row['status'], 'passed')
        self.assertEqual(row['evidence'][0]['path'], 'hub-source/' + self.pid + '/proof.txt')
        self.assertEqual(self.state()['checkCount'], 0)

    def test_mcp_schema_validation_and_bound_dispatch(self):
        from hub_plugin import Mcp
        from hub_core import HubError
        from plugin_api import call
        end, event = self.finish(self.launch())
        good = self.corrected(end, event)
        client = Mock()
        mcp = Mcp(None, cwd=str(self.registry.base_store(self.pid).root),
                  session='correction-test-session', client=client)
        mcp.call('hub_check', good)
        self.assertEqual(client.call.call_args.args[-1], good)
        with self.assertRaises(HubError):
            mcp.call('hub_check', dict(good, correction={'reason': 'Missing expected event'}))
        self.assertEqual(client.call.call_count, 1)
        result = call(self.registry, dict(cwd=str(self.registry.base_store(self.pid).root),
                      session='correction-test-session', tool='hub_check', arguments=good))
        self.assertEqual(result['run']['status'], 'passed')
