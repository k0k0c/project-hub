"""Project authority survives app changes without impersonating work owners."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from agent_bindings import Connections
from agent_runtime import call, tools
from hub_core import HubError
from plugin_api import ServerHub
from project_registry import ProjectRegistry


class WorkReconciliationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.registry = ProjectRegistry(Path(temporary.name) / 'home', standalone=True)
        self.addCleanup(self.registry.close_connection_pool)
        self.connections = Connections(self.registry)
        self.project = self.registry.create('Example project')['id']
        self.first = self.enroll('a', 'editor-one')
        self.second = self.enroll('b', 'editor-two')
        self.task = self.invoke(self.first, 'hub_task', title='Shared task', scope=['Example'], acceptance=['Verified'])['task']
        self.invoke(self.first, 'hub_plan', task=self.task, stage='verify', title='Verify')

    def enroll(self, key, client, project=None):
        invitation = self.connections.invite(project or self.project, request_id=key * 32)
        return self.connections.enroll(invitation['token'], client, 'installation-' + key,
                                       workspace=str(self.workspace) if getattr(self, 'workspace', None) else None)

    def invoke(self, connection, tool, **arguments):
        if getattr(self, 'workspace', None):
            arguments.setdefault('workspace', str(self.workspace))
        return call(self.registry, connection['token'], tool, dict(session='same-native-chat', **arguments))

    def start(self, connection=None, title='Original work'):
        return self.invoke(connection or self.first, 'hub_begin', task=self.task, stage='verify', title=title,
                           resources=['resource:example'])

    def waiting(self, legacy=False):
        self.waiting_count = getattr(self, 'waiting_count', 0) + 1
        work = self.start(title='Original work ' + str(self.waiting_count))
        self.invoke(self.first, 'hub_report', **{k: work[k] for k in ('work', 'revision')},
                    result='Original verified result', checkpoint='Await acceptance', status='waiting', waiting_kind='user_confirmation')
        if legacy:
            # A persisted pre-MCP owner, on disposable data only.
            with ServerHub(self.registry).transaction() as c:
                owner = c.execute('SELECT session FROM work WHERE id=?', (work['work'],)).fetchone()[0]
                c.execute("INSERT INTO sessions(id,project,workspace,state,seen) SELECT 'same-native-chat',project,workspace,state,seen FROM sessions WHERE id=?", (owner,))
                c.execute("UPDATE work SET session='same-native-chat' WHERE id=?", (work['work'],))
        return self.read(work['work'])

    def read(self, work, connection=None):
        return self.invoke(connection or self.second, 'hub_context', work=work)['work'][0]

    def reconcile(self, work, connection=None, **overrides):
        arguments = dict(work=work['id'], revision=work['revision'], status='done', result='User accepted the verified result',
                         reconcile=dict(owner=work['session'], status=work['status'], reason='Explicit acceptance after reconnect'))
        arguments.update(overrides)
        return self.invoke(connection or self.second, 'hub_report', **arguments)

    def row(self, work):
        with self.registry.coordination_connect() as c:
            return dict(c.execute('SELECT * FROM work WHERE id=?', (work,)).fetchone())

    def test_raw_native_and_connection_scoped_owners_reconcile_without_transfer(self):
        for legacy in (False, True):
            with self.subTest(legacy=legacy):
                work = self.waiting(legacy)
                original = self.row(work['id'])
                with self.assertRaises(HubError) as caught:
                    self.invoke(self.second, 'hub_report', work=work['id'], revision=work['revision'], result='Ordinary foreign report', status='done')
                self.assertEqual(caught.exception.body['error'], 'not_owner')
                with patch.object(ServerHub, 'freeze_git_boundary', side_effect=AssertionError('Do not capture current bytes for historical work')):
                    result = self.reconcile(work)
                self.assertEqual(result['status'], 'done')
                self.assertEqual(result['planSync'], 'saved')
                current = self.row(work['id'])
                for field in ('id', 'session', 'project', 'task', 'git_snapshot', 'created'):
                    self.assertEqual(current[field], original[field])
                self.assertEqual(result['reconciliation']['owner'], original['session'])
                with self.registry.coordination_connect() as c:
                    audit = json.loads(c.execute('SELECT body FROM events WHERE seq=?', (result['revision'],)).fetchone()[0])['reconciliation']
                    self.assertEqual(audit['previousResult'], 'Original verified result')
                    self.assertEqual(audit['previousCheckpoint'], 'Await acceptance')
                    self.assertEqual(audit['actor'], result['reconciliation']['actor'])
                    self.assertEqual(c.execute('SELECT COUNT(*) FROM claims WHERE work=?', (work['id'],)).fetchone()[0], 1)
                self.assertEqual(self.reconcile(work), result)
                changed = dict(owner=work['session'], status=work['status'], reason='Different intent')
                with self.assertRaises(HubError):
                    self.reconcile(work, reconcile=changed)

    def test_task_created_in_one_app_continued_and_closed_in_another(self):
        work = self.waiting()
        plan = self.invoke(self.second, 'hub_plan', task=self.task)
        self.invoke(self.second, 'hub_task_update', task=self.task, expected=plan['revision'], patch=dict(title='Continued in another app'))
        own = self.start(self.second, title='Continue')
        deferred = self.invoke(self.second, 'hub_report', work=own['work'], revision=own['revision'], result='Verified continuation', status='done', stage_status='done')
        self.assertEqual(deferred['stageCompletionDeferred']['openWorkCount'], 1)
        self.reconcile(work, stage_status='done')
        plan = self.invoke(self.second, 'hub_plan', task=self.task)
        self.assertEqual(plan['task']['stages'][0]['status'], 'done')
        self.invoke(self.second, 'hub_task_close', task=self.task, expected=plan['revision'], mode='auto')
        self.assertEqual(self.invoke(self.first, 'hub_plan', task=self.task)['task']['status'], 'done')

    def test_active_work_requires_explicit_interruption_and_owner_race_is_guarded(self):
        started = self.start()
        work = self.read(started['work'])
        self.assertTrue(work['reconciliation']['activeConfirmationRequired'])
        with self.assertRaises(HubError) as caught:
            self.reconcile(work)
        self.assertEqual(caught.exception.body['error'], 'work_active')
        self.assertEqual(self.row(work['id'])['status'], 'active')
        self.invoke(self.first, 'hub_report', work=work['id'], revision=work['revision'], status='active', result='Still executing')
        active = dict(owner=work['session'], status='active', reason='User requested interruption')
        with self.assertRaises(HubError):
            self.reconcile(work, reconcile=dict(active, allowActive=True))
        with self.assertRaises(HubError) as caught:
            self.reconcile(work, reconcile=active)
        self.assertEqual(caught.exception.body['error'], 'revision_conflict')
        current = self.read(work['id'])
        from work_reconciliation_api import apply
        body = dict(work=current['id'], revision=current['revision'], owner=current['session'], observedStatus='active',
                    reason='User confirmed interruption in Hub', result='Cancelled after coordination', status='cancelled',
                    interruptActive=False, confirmed=current['id']+':'+str(current['revision']))
        with self.assertRaises(HubError):
            apply(self.registry, self.project, body)
        body['interruptActive'] = True
        result = apply(self.registry, self.project, body)
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(apply(self.registry, self.project, body), result)
        self.assertTrue(self.row(current['id'])['session'] == current['session'])
        with self.assertRaises(HubError):
            self.invoke(self.first, 'hub_report', work=current['id'], revision=current['revision'], result='Late owner', status='active')

    def test_foreign_project_rejected_and_does_not_read_or_freeze_work(self):
        work = self.waiting()
        other = self.enroll('c', 'other-app', self.registry.create('Other project')['id'])
        self.assertEqual(self.invoke(other, 'hub_context', work=work['id'])['work'], [])
        with patch.object(ServerHub, 'freeze_git_boundary', side_effect=AssertionError('No filesystem read')):
            with self.assertRaises(HubError) as caught:
                self.reconcile(work, other)
        self.assertEqual(caught.exception.body['error'], 'work_project_mismatch')
        self.assertEqual(self.row(work['id'])['revision'], work['revision'])

    def test_competing_reconciliation_and_lost_reply_are_atomic_and_idempotent(self):
        work = self.waiting()
        third = self.enroll('d', 'third-app')
        def attempt(connection):
            try:
                return self.reconcile(work, connection)
            except HubError as error:
                return error.body
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(attempt, [self.second, third]))
        self.assertEqual(sum(item.get('status') == 'done' for item in outcomes), 1)
        self.assertEqual(sum(item.get('error') == 'revision_conflict' for item in outcomes), 1)
        winner = self.second if outcomes[0].get('status') == 'done' else third
        result = self.reconcile(work, winner)
        with self.registry.coordination_connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM events WHERE work=? AND kind='work.done'", (work['id'],)).fetchone()[0], 1)
        self.assertEqual(result['revision'], self.row(work['id'])['revision'])

    def test_reconciliation_retains_archived_evidence_without_revalidation(self):
        work = self.waiting()
        with ServerHub(self.registry).transaction() as c:
            c.execute('UPDATE work SET evidence=? WHERE id=?', (json.dumps(['archived/original.txt']), work['id']))
        from artifact_store import publish
        evidence = publish(self.registry.store(self.project), 'acceptance.txt', b'Accepted', roles=['evidence'])['source']['path']
        revision = self.invoke(self.second, 'hub_plan', task=self.task)['revision']
        self.invoke(self.second, 'hub_artifact', task=self.task, path=evidence, expected=revision)
        result = self.reconcile(work, evidence=[evidence])
        self.assertEqual(result['planSync'], 'saved')
        self.assertEqual(json.loads(self.row(work['id'])['evidence']), ['archived/original.txt', evidence])
        plan = self.invoke(self.second, 'hub_plan', task=self.task)
        self.assertIn('User accepted the verified result', json.dumps(plan))
        self.assertIn(evidence, json.dumps(plan))
        self.assertNotIn('archived/original.txt', json.dumps(plan))

    def test_invalid_reconciliation_cannot_resume_or_change_phase(self):
        work = self.waiting()
        with self.assertRaises(HubError) as caught:
            self.reconcile(work, self.first)
        self.assertEqual(caught.exception.body['error'], 'reconciliation_not_required')
        for changed in (dict(status='active'), dict(phase='review'), dict(reconcile={}),
                        dict(reconcile=dict(owner=work['session'], status='waiting', reason=' ')),
                        dict(reconcile=dict(owner='different-owner', status='waiting', reason='Observed owner changed'))):
            with self.subTest(changed=changed), self.assertRaises(HubError):
                self.reconcile(work, **changed)
        self.assertEqual(self.row(work['id'])['revision'], work['revision'])

    def test_reconnected_connection_and_tool_schema_keep_explicit_contract(self):
        work = self.waiting()
        # A new enrollment to the same project, distinct from credential rotation.
        reconnected = self.enroll('e', 'editor-one')
        self.reconcile(work, reconnected)
        declaration = next(tool for tool in tools() if tool['name'] == 'hub_report')
        schema = declaration['inputSchema']['properties']['reconcile']
        self.assertEqual(schema['required'], ['owner', 'status', 'reason'])
        self.assertFalse(schema['additionalProperties'])

    def test_git_boundary_index_and_foreign_live_claims_remain_unchanged(self):
        self.workspace = self.registry.home.parent / 'workspace'
        self.workspace.mkdir()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.workspace), *args], stderr=subprocess.DEVNULL)
        git('init', '-q')
        git('config', 'user.name', 'Example')
        git('config', 'user.email', 'example@example.test')
        git('config', 'commit.gpgsign', 'false')
        (self.workspace / 'feature.txt').write_text('before\n')
        git('add', '.')
        git('commit', '-qm', 'Initial')
        self.project = self.registry.create('Workspace project', roots=[str(self.workspace)])['id']
        self.first = self.enroll('f', 'first-app')
        self.second = self.enroll('9', 'second-app')
        self.task = self.invoke(self.first, 'hub_task', title='Edit', scope=['feature.txt'], acceptance=['Accepted'])['task']
        self.invoke(self.first, 'hub_plan', task=self.task, stage='verify', title='Verify')
        started = self.invoke(self.first, 'hub_begin', task=self.task, stage='verify', title='Original edit', resources=['feature.txt'])
        (self.workspace / 'feature.txt').write_text('accepted\n')
        self.invoke(self.first, 'hub_report', work=started['work'], revision=started['revision'], result='Awaiting acceptance', status='waiting')
        work = self.read(started['work'])
        snapshot = self.row(work['id'])['git_snapshot']
        self.assertIn('contentBoundary', json.loads(snapshot))
        self.assertNotIn('contentAfter', json.loads(snapshot))
        live = self.invoke(self.second, 'hub_begin', task=self.task, stage='verify', title='Parallel edit', resources=['feature.txt'])
        (self.workspace / 'feature.txt').write_text('later unrelated edit\n')
        git('add', 'feature.txt')
        index = git('ls-files', '--stage')
        head = git('rev-parse', 'HEAD')
        self.reconcile(work)
        self.assertEqual(self.row(work['id'])['git_snapshot'], snapshot)
        self.assertEqual(git('ls-files', '--stage'), index)
        self.assertEqual(git('rev-parse', 'HEAD'), head)
        self.assertEqual((self.workspace / 'feature.txt').read_text(), 'later unrelated edit\n')
        self.assertEqual(self.row(live['work'])['status'], 'active')
        with self.registry.coordination_connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM claims WHERE work=?', (live['work'],)).fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
