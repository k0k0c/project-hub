"""Lost write responses are reproduced only against disposable Hub storage."""
from contextlib import redirect_stderr
from http.client import IncompleteRead
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import threading
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_manual_editing import ManualApiCase
from plugin_api import ServerHub, compact_write_ack
from hub_core import HubError
from hub_http import Client
from hub_check import deliver, persist, post, validate_check
from check_runs import ingest
from project_portal import Handler
from hub_memory import Memory
from task_transfer import ProjectView


class WriteAcknowledgmentsTest(ManualApiCase):
    def setUp(self):
        super().setUp()
        self.client = Client('http://127.0.0.1:' + str(self.server.server_port))
        self.root = self.registry.store(self.pid).root

    def invoke(self, tool, **arguments):
        return self.client.call(self.root, 'ack-test', tool, arguments)

    def start(self):
        return dict(runId='ack-run', task=self.task(), status='running',
                    command=['runner'], startedAt='2026-09-20T00:00:00Z')

    def lose_response(self):
        original = self.client.opener.open
        def open_and_lose(*args, **kwargs):
            with original(*args, **kwargs) as response:
                response.read()
            raise TimeoutError('response lost after the server committed')
        return patch.object(self.client.opener, 'open', side_effect=open_and_lose)

    def test_report_lost_response_exact_replay_has_one_durable_report(self):
        task = self.invoke('hub_task', title='Report', scope=['test'], acceptance=['test'])['task']
        self.invoke('hub_plan', task=task, stage='test', title='Test')
        work = self.invoke('hub_begin', task=task, stage='test', title='Work', resources=['resource:test'])
        args = dict(work=work['work'], revision=work['revision'], result='Verified', status='done')
        with self.lose_response(), self.assertRaises(HubError) as caught:
            self.invoke('hub_report', **args)
        error = caught.exception.body
        self.assertEqual(error['error'], 'write_outcome_unknown')
        self.assertEqual(error['reason'], 'timeout')
        self.assertEqual(error['recovery'], dict(work=work['work'], revision=work['revision']))
        replay = self.invoke('hub_report', **args)
        self.assertEqual(replay['status'], 'done')
        with ServerHub(self.registry).connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE work=? AND kind='work.done'",
                                        (work['work'],)).fetchone()[0], 1)
        reports = [event for event in self.state()['allEvents'] if event.get('workId') == work['work']]
        self.assertEqual(len(reports), 1)
        with self.assertRaises(HubError) as conflict:
            self.invoke('hub_report', **dict(args, result='Changed'))
        self.assertEqual(conflict.exception.body['error'], 'revision_conflict')

    def test_check_lost_finish_flush_preserves_run_and_deduplicates(self):
        start = self.start()
        directory = self.root / '.local/checks' / start['runId']
        directory.mkdir(parents=True)
        persist(directory / 'start.json', dict(project=self.pid, payload=start))
        finish = dict(start, status='passed', exitCode=0, finishedAt='2026-09-20T00:00:01Z')
        persist(directory / 'finish.json', finish)
        post(self.client, self.pid, start)
        with self.lose_response(), self.assertRaises(HubError):
            post(self.client, self.pid, finish)
        self.assertFalse((directory / 'delivered.json').exists())
        self.assertTrue(deliver(self.client, self.pid, directory))
        self.assertTrue(deliver(self.client, self.pid, directory))
        events = [event for event in self.state()['allEvents'] if event.get('runId') == start['runId']]
        self.assertEqual([event['kind'] for event in events], ['check.started', 'check.passed'])
        self.assertTrue((directory / 'delivered.json').exists())

    def test_begin_lost_response_reuses_original_snapshot_without_git_recapture(self):
        (self.root / '.git').mkdir()
        task = self.invoke('hub_task', title='Begin retry', scope=['test'], acceptance=['test'])['task']
        self.invoke('hub_plan', task=task, stage='test', title='Test')
        args = dict(task=task, stage='test', title='Original work', resources=['feature.txt'])
        original_snapshot = dict(available=True, root=str(self.root), head='a' * 40,
                                 resources=['feature.txt'], dirty=[], allDirty=[])
        with patch('git_integration.work_snapshot', return_value=original_snapshot):
            with self.lose_response(), self.assertRaises(HubError) as caught:
                self.invoke('hub_begin', **args)
        self.assertTrue(caught.exception.body['retrySafe'])
        self.assertEqual(caught.exception.body['recovery'], dict(args, session='ack-test', mode='write'))
        (self.root / 'feature.txt').write_text('work after timeout', encoding='utf-8')
        with patch('git_integration.work_snapshot', side_effect=AssertionError('must retain first baseline')):
            replay = self.invoke('hub_begin', **args)
        with ServerHub(self.registry).connect() as db:
            rows = db.execute('SELECT id,git_snapshot FROM work WHERE task=?', (task,)).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['id'], replay['work'])
        self.assertEqual(json.loads(rows[0]['git_snapshot']), original_snapshot)
        hub = ServerHub(self.registry)
        with patch.object(hub, 'tasks', return_value=[]), self.assertRaises(HubError) as missing:
            hub.begin('ack-test', **args)
        self.assertEqual(missing.exception.body['error'], 'task_missing')

    def test_wrapper_retains_pending_and_explains_unknown_ack(self):
        start = self.start()
        directory = self.root / '.local/checks' / start['runId']
        directory.mkdir(parents=True)
        persist(directory / 'start.json', dict(project=self.pid, payload=start))
        output = StringIO()
        with self.lose_response(), redirect_stderr(output):
            self.assertFalse(deliver(self.client, self.pid, directory))
        self.assertIn('server may have saved', output.getvalue())
        self.assertFalse((directory / 'delivered.json').exists())
        self.assertEqual(json.loads((directory / 'start.json').read_text())['payload'], start)

    def test_real_socket_timeout_after_check_commit_is_unknown_and_recoverable(self):
        start = self.start()
        committed = threading.Event()
        release = threading.Event()
        replied = threading.Event()
        original = Handler.reply
        def delayed_reply(handler, status, body, *args, **kwargs):
            committed.set()
            release.wait(5)
            try:
                return original(handler, status, body, *args, **kwargs)
            except OSError:
                pass  # The client has closed its timed-out socket.
            finally:
                replied.set()
        self.client.timeout = .5
        try:
            with patch.object(Handler, 'reply', delayed_reply), self.assertRaises(HubError) as caught:
                post(self.client, self.pid, start)
            self.assertTrue(committed.is_set())
            self.assertEqual(caught.exception.body['reason'], 'timeout')
            self.assertEqual(caught.exception.body['writeOutcome'], 'unknown')
        finally:
            release.set()
            self.assertTrue(replied.wait(5))
        self.client.timeout = 15
        self.assertTrue(post(self.client, self.pid, start)['duplicate'])
        self.assertEqual(len([e for e in self.state()['allEvents'] if e.get('runId') == start['runId']]), 1)

    def test_check_response_amplification_and_compact_ack(self):
        start = self.start()
        start.update(command=['runner', 'x' * 1900, 'y' * 1900], summary='s' * 1600,
                     evidence=[dict(label='l' * 200, path=str(index) + 'p' * 200) for index in range(20)])
        self.assertLess(len(validate_check(start)), 15000)
        original = ingest(self.registry, self.pid, start)
        self.assertGreater(len(json.dumps(original).encode()), 16000)
        compact = compact_write_ack('hub_check', original)
        self.assertLess(len(json.dumps(compact).encode()), 2000)
        self.assertEqual(compact['run']['id'], original['run']['id'])
        self.assertEqual(compact['run']['status'], 'running')
        # Old servers echo the large run: the wrapper still accepts their receipt.
        with patch.object(self.client.opener, 'open', return_value=BytesIO(json.dumps(original).encode())):
            self.assertEqual(post(self.client, self.pid, start)['run']['runId'], start['runId'])
        replay = self.invoke('hub_check', **start)
        self.assertTrue(replay['duplicate'])
        self.assertNotIn('command', replay['run'])

    def test_oversized_malformed_truncated_and_timeout_are_distinct_unknowns(self):
        args = dict(work='work', revision=123, result='Saved')
        for raw, reason in ((b'x' * 256001, 'response_too_large'), (b'{', 'invalid_response'),
                            (b'[]', 'invalid_response')):
            with self.subTest(reason=reason), patch.object(self.client.opener, 'open', return_value=BytesIO(raw)):
                with self.assertRaises(HubError) as caught:
                    self.invoke('hub_report', **args)
                self.assertEqual(caught.exception.body['reason'], reason)
                self.assertEqual(caught.exception.body['writeOutcome'], 'unknown')
                self.assertTrue(caught.exception.body['retrySafe'])
        for failure in (IncompleteRead(b'{'), TimeoutError()):
            with patch.object(self.client.opener, 'open', side_effect=failure), self.assertRaises(HubError) as caught:
                self.invoke('hub_report', **args)
            self.assertEqual(caught.exception.body['error'], 'write_outcome_unknown')

    def test_non_idempotent_write_does_not_advise_blind_retry(self):
        with patch.object(self.client.opener, 'open', side_effect=TimeoutError()), self.assertRaises(HubError) as caught:
            self.invoke('hub_task', title='Task', scope=['test'], acceptance=['test'])
        self.assertFalse(caught.exception.body['retrySafe'])
        self.assertNotIn('recovery', caught.exception.body)
        with patch.object(self.client.opener, 'open', side_effect=TimeoutError()), self.assertRaises(HubError) as caught:
            self.invoke('hub_context')
        self.assertEqual(caught.exception.body['error'], 'server_unavailable')

    def test_structured_rejection_is_preserved_but_server_failure_is_unknown(self):
        rejection = dict(error='revision_conflict', message='Refresh', revision=9)
        for status in (409, 503):
            failure = HTTPError(self.client.url, status, 'Failed', {}, BytesIO(json.dumps(rejection).encode()))
            with patch.object(self.client.opener, 'open', side_effect=failure), self.assertRaises(HubError) as caught:
                self.invoke('hub_report', work='work', revision=1, result='Verified')
            if status == 409:
                self.assertEqual(caught.exception.body, rejection)
            else:
                self.assertEqual(caught.exception.body['writeOutcome'], 'unknown')

    def test_report_ack_preserves_publication_and_git_failure(self):
        receipt = dict(work='work', revision=2, status='done', planSync='pending', message='Retry delivery',
                       gitCheckpoint=dict(status='error', reason='Scope missing'), gitCommit=None)
        self.assertEqual(compact_write_ack('hub_report', dict(receipt, history=['x' * 256000])), receipt)

    def report_arguments(self):
        task = self.invoke('hub_task', title='Report delivery', scope=['test'], acceptance=['test'])['task']
        self.invoke('hub_plan', task=task, stage='test', title='Test')
        work = self.invoke('hub_begin', task=task, stage='test', title='Work', resources=['resource:test'])
        return task, dict(work=work['work'], revision=work['revision'], result='Verified', status='done')

    def test_report_own_delivery_bypasses_backlog_without_acknowledging_it(self):
        task, args = self.report_arguments()
        hub = ServerHub(self.registry)
        with hub.transaction() as db:
            for index in range(45):
                event = dict(id='backlog-' + str(index), taskId=task, kind='note', title='Earlier report')
                db.execute('INSERT INTO plan_outbox VALUES (?,?,?)',
                           (event['id'], self.pid, json.dumps(event)))
        with patch.object(Memory, 'progress', side_effect=AssertionError('Report must not take a progress snapshot')):
            result = self.invoke('hub_report', **args)
        self.assertEqual(result['planSync'], 'saved')
        self.assertTrue(result['progressHint']['deferred'])
        with hub.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM plan_outbox').fetchone()[0], 45)
        stage = self.state()['tasks'][0]['stages'][0]
        self.assertIn('Verified', stage['done'])
        # Other calls retain their bounded global delivery, including this backlog.
        self.invoke('hub_context')
        with hub.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM plan_outbox').fetchone()[0], 25)

    def test_postpersist_delivery_failure_and_exact_replay_recover_without_duplicates(self):
        task, args = self.report_arguments()
        original = ProjectView.record
        def save_then_fail(store, event, *values, **options):
            saved = original(store, event, *values, **options)
            if event['id'].startswith('work-report-'):
                raise OSError('Lost delivery acknowledgment after journal append')
            return saved
        with patch.object(ProjectView, 'record', save_then_fail):
            first = self.invoke('hub_report', **args)
        self.assertEqual(first['status'], 'done')
        self.assertEqual(first['planSync'], 'pending')
        with ServerHub(self.registry).connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM plan_outbox').fetchone()[0], 2)
        recovered = self.invoke('hub_report', **args)
        self.assertEqual(recovered['planSync'], 'saved')
        self.assertEqual(recovered['revision'], first['revision'])
        self.assertEqual(self.invoke('hub_report', **args)['planSync'], 'saved')
        state = self.state()
        events = [e for e in state['allEvents'] if e['id'].startswith(('work-report-', 'stage-report-'))]
        self.assertEqual(len(events), 2)
        self.assertEqual(state['tasks'][0]['stages'][0]['done'], ['Verified'])
        with ServerHub(self.registry).connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM plan_outbox').fetchone()[0], 0)

    def test_saved_requires_verified_removal_of_own_outbox_rows(self):
        task, args = self.report_arguments()
        hub = ServerHub(self.registry)
        with hub.connect() as db:
            db.execute('CREATE TRIGGER hold_delivery BEFORE DELETE ON plan_outbox BEGIN SELECT RAISE(IGNORE); END')
        try:
            self.assertEqual(self.invoke('hub_report', **args)['planSync'], 'pending')
        finally:
            with hub.connect() as db:
                db.execute('DROP TRIGGER hold_delivery')
        self.assertEqual(self.invoke('hub_report', **args)['planSync'], 'saved')
        self.assertEqual(self.state()['tasks'][0]['stages'][0]['done'], ['Verified'])

    def test_later_report_flushes_earlier_work_reports_in_order(self):
        task, args = self.report_arguments()
        with patch.object(Memory, 'flush_reports', side_effect=OSError('offline')):
            earlier = self.invoke('hub_report', **dict(args, status='active', stage_status='blocked', result='Blocked'))
        self.assertEqual(earlier['planSync'], 'pending')
        later = self.invoke('hub_report', **dict(args, revision=earlier['revision'], stage_status='done'))
        self.assertEqual(later['planSync'], 'saved')
        stage = self.state()['tasks'][0]['stages'][0]
        self.assertEqual(stage['status'], 'done')
        self.assertEqual(stage['done'], ['Verified'])
        with ServerHub(self.registry).connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM plan_outbox').fetchone()[0], 0)

    def test_large_own_backlog_returns_pending_until_exact_replay_drains_it(self):
        task, args = self.report_arguments()
        hub = ServerHub(self.registry)
        with hub.transaction() as db:
            for index in range(25):
                event = dict(id='work-report-' + args['work'] + '-' + str(1000 + index),
                             taskId=task, kind='note', title='Earlier report')
                db.execute('INSERT INTO plan_outbox VALUES (?,?,?)',
                           (event['id'], self.pid, json.dumps(event)))
        first = self.invoke('hub_report', **args)
        self.assertEqual(first['planSync'], 'pending')
        with hub.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM plan_outbox').fetchone()[0], 7)
        replay = self.invoke('hub_report', **args)
        self.assertEqual(replay['revision'], first['revision'])
        self.assertEqual(replay['planSync'], 'saved')
        self.assertEqual(self.state()['tasks'][0]['stages'][0]['done'], ['Verified'])
