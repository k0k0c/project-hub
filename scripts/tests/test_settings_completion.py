"""Completion policy across real temporary Git repositories and public routes."""
import subprocess
import threading
import time
from unittest.mock import patch

from test_manual_editing import ManualApiCase
from test_project_hub_plugin_api import Client, HubError
from completion_policy import retry_checkpoint
import completion_policy
from git_integration import GitIntegrationError
from project_settings import read_settings, update_settings


class SettingsCompletionTest(ManualApiCase):
    def setUp(self):
        super().setUp()
        self.store = self.registry.store(self.pid)
        self.root = self.store.root
        self.git('init', '-q')
        self.git('config', 'user.email', 'completion@example.test')
        self.git('config', 'user.name', 'Completion Test')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'commit.gpgsign', 'false')
        for name in ('feature.txt', 'unrelated.txt', 'staged.txt'):
            (self.root / name).write_text('before\n', encoding='utf-8')
        self.git('add', '.')
        self.git('commit', '-qm', 'Initial')
        self.client = Client('http://127.0.0.1:' + str(self.server.server_port))

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def invoke(self, tool, **args):
        return self.client.call(self.root, 'settings-completion-fixture', tool, args)

    def enable(self, mode='stage-and-task'):
        base = self.registry.base_store(self.pid)
        return update_settings(base, {'git': {'autoCommit': True, 'commitOn': mode}},
                               read_settings(base)['revision'])

    def target(self, task, stage=None):
        row = next(t for t in self.state()['tasks'] if t['id'] == task)
        return next(s for s in row['stages'] if s['id'] == stage) if stage else row

    def outcome(self, task, stage, status):
        deadline = time.monotonic() + 10
        while True:
            row = self.target(task, stage)
            checkpoint = row.get('gitCheckpoint', {})
            if checkpoint.get('status') != 'pending' and checkpoint:
                break
            if time.monotonic() >= deadline:
                self.fail('Checkpoint did not settle within 10s: ' + repr(row))
            time.sleep(.05)
        self.assertEqual(row['status'], 'done', row)
        self.assertEqual(checkpoint['status'], status, checkpoint)
        self.assertTrue(checkpoint['id'])
        self.assertIn('settingsRevision', checkpoint)
        if status == 'committed':
            self.assertEqual(row['gitCommit']['sha'], self.git('rev-parse', 'HEAD'))
        return checkpoint

    def reservation(self, change=True):
        task = self.task('Settings completion')
        stage = self.stage(task)
        work = self.invoke('hub_begin', task=task, stage=stage, title='Scoped edit',
                           resources=['feature.txt'], mode='write')
        if change:
            (self.root / 'feature.txt').write_text(task + '\n', encoding='utf-8')
        return task, stage, work

    def release(self, work):
        return self.invoke('hub_report', work=work['work'], revision=work['revision'],
                           result='Verified scoped edit', status='done')

    def complete_stage(self, route, task, stage, work):
        if route == 'report':
            return self.invoke('hub_report', work=work['work'], revision=work['revision'],
                               result='Verified scoped edit', status='done', stage_status='done')
        self.release(work)
        if route == 'record':
            return self.store.record(dict(id='complete-' + task, taskId=task, stageId=stage,
                kind='stage.updated', title='Complete', patch={'status': 'done'}),
                expected_revision=self.state()['revision'])
        if route == 'http':
            return self.mutate('stages/update', dict(task=task, stage=stage, patch={'status': 'done'}))
        return self.invoke('hub_plan', task=task, stage=stage, title='Stage', status='done',
                           expected=self.state()['revision'])

    def assert_stage_commit(self, route):
        self.enable('stage')
        task, stage, work = self.reservation()
        self.complete_stage(route, task, stage, work)
        receipt = self.outcome(task, stage, 'committed')
        self.assertEqual(receipt['verification'], 'exact-content-and-ancestry')
        self.assertEqual(receipt['changesets'][0]['coverage']['commit'], receipt['sha'])
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')
        self.assertEqual(self.git('show', '--format=', '--name-only', 'HEAD'), 'feature.txt')
        self.assertIn('Project-Hub-Task: ' + task, self.git('log', '-1', '--format=%B'))
        self.assertEqual(receipt['settingsRevision'], read_settings(self.registry.base_store(self.pid))['revision'])

    def test_default_off_through_all_completion_routes(self):
        self.assertFalse(read_settings(self.registry.base_store(self.pid))['settings']['git']['autoCommit'])
        initial = self.git('rev-parse', 'HEAD')
        for route in ('record', 'http', 'report', 'plan'):
            with self.subTest(route=route):
                task, stage, work = self.reservation()
                self.complete_stage(route, task, stage, work)
                self.outcome(task, stage, 'disabled')
                self.mutate('tasks/close', dict(task=task, mode='auto'))
                self.outcome(task, None, 'disabled')
                self.assertEqual(self.git('rev-parse', 'HEAD'), initial)

    def test_project_view_record_commits(self):
        self.assert_stage_commit('record')

    def test_administrative_blocker_repair_preserves_optional_git_policy(self):
        for enabled in (False, True):
            with self.subTest(autoCommit=enabled):
                if enabled:
                    self.enable('stage-and-task')
                task, stage, work = self.reservation()
                blocker = dict(kind='administrative', reason='Incorrect receipt metadata',
                               action='Repair receipt preserving audit history')
                self.invoke('hub_plan', task=task, stage=stage, title='Stage', status='blocked',
                            blocker=blocker, expected=self.state()['revision'])
                self.assertEqual(self.target(task, stage)['blocker'], blocker)
                self.release(work)
                self.invoke('hub_plan', task=task, stage=stage, title='Stage', status='done',
                            blocker=None, expected=self.state()['revision'])
                self.assertIsNone(self.target(task, stage)['blocker'])
                self.outcome(task, stage, 'committed' if enabled else 'disabled')
                self.mutate('tasks/close', dict(task=task, mode='auto'))
                self.outcome(task, None, 'committed' if enabled else 'disabled')
                if not enabled:
                    self.git('add', 'feature.txt')
                    self.git('commit', '-qm', 'Isolated fixture baseline after disabled policy')

    def test_manual_http_stage_update_commits(self):
        self.assert_stage_commit('http')

    def test_mcp_report_commits(self):
        self.assert_stage_commit('report')

    def test_mcp_plan_commits(self):
        self.assert_stage_commit('plan')

    def check_mode(self, mode):
        self.enable(mode)
        task, stage, work = self.reservation()
        self.complete_stage('http', task, stage, work)
        stage_receipt = self.outcome(task, stage, 'disabled' if mode == 'task' else 'committed')
        stage_head = self.git('rev-parse', 'HEAD')
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1' if mode == 'task' else '2')
        self.mutate('tasks/close', dict(task=task, mode='auto'))
        task_receipt = self.outcome(task, None, 'disabled' if mode == 'stage' else 'committed')
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')
        if mode == 'stage-and-task':
            self.assertTrue(task_receipt['reused'])
            self.assertEqual(task_receipt['sha'], stage_receipt['sha'])
            self.assertEqual(self.target(task)['gitCommit']['sha'], stage_receipt['sha'])
            self.assertEqual(self.git('rev-parse', 'HEAD'), stage_head)

    def test_stage_mode_skips_task_checkpoint(self):
        self.check_mode('stage')

    def test_task_mode_commits_on_manual_http_close(self):
        self.check_mode('task')

    def test_both_mode_does_not_duplicate_stage_commit_at_task_close(self):
        self.check_mode('stage-and-task')

    def test_task_links_multiple_covered_commits_without_new_commit(self):
        self.enable()
        task, stage, work = self.reservation()
        self.complete_stage('report', task, stage, work)
        first = self.outcome(task, stage, 'committed')['sha']
        second_stage = self.stage(task)
        second_work = self.invoke('hub_begin', task=task, stage=second_stage,
                                 title='Second scoped edit', resources=['feature.txt'], mode='write')
        (self.root / 'feature.txt').write_text('second stage\n', encoding='utf-8')
        self.complete_stage('report', task, second_stage, second_work)
        second = self.outcome(task, second_stage, 'committed')['sha']
        self.assertNotEqual(first, second)
        count = self.git('rev-list', '--count', 'HEAD')
        self.assertEqual(count, '3')
        self.mutate('tasks/close', dict(task=task, mode='auto'))
        receipt = self.outcome(task, None, 'no_changes')
        self.assertEqual({commit['sha'] for commit in receipt['commits']}, {first, second})
        self.assertEqual(self.git('rev-parse', 'HEAD'), second)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), count)

    def test_no_changes_does_not_create_empty_commit(self):
        self.enable()
        task, stage, work = self.reservation(change=False)
        self.complete_stage('record', task, stage, work)
        self.outcome(task, stage, 'no_changes')
        self.mutate('tasks/close', dict(task=task, mode='auto'))
        self.outcome(task, None, 'no_changes')
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1')

    def test_committed_stage_transfer_preserves_sha_without_new_commit(self):
        self.enable('stage')
        source, stage, work = self.reservation()
        self.complete_stage('report', source, stage, work)
        receipt = self.outcome(source, stage, 'committed')
        head = self.git('rev-parse', 'HEAD')
        count = self.git('rev-list', '--count', 'HEAD')
        destination = self.task('Destination task')
        self.mutate('stages/transfer', dict(task=source, stage=stage, target=destination))
        self.assertFalse(any(s['id'] == stage for s in self.target(source)['stages']))
        moved = self.target(destination, stage)
        self.assertEqual(moved['status'], 'done')
        self.assertEqual(moved['gitCheckpoint']['id'], receipt['id'])
        self.assertEqual(moved['gitCheckpoint']['status'], 'committed')
        self.assertEqual(moved['gitCheckpoint']['sha'], receipt['sha'])
        self.assertEqual(moved['gitCommit']['sha'], receipt['sha'])
        # Replay the durable journal independently of the registry receipt projection.
        replay = self.registry.base_store(self.pid).snapshot()
        replay_task = next(t for t in replay['tasks'] if t['id'] == destination)
        replay_stage = next(s for s in replay_task['stages'] if s['id'] == stage)
        self.assertEqual(replay_stage['gitCommit']['sha'], receipt['sha'])
        self.assertEqual(replay_stage['gitCheckpoint']['id'], receipt['id'])
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), count)

    def test_repeated_record_and_retry_do_not_duplicate_commit(self):
        self.enable()
        task, stage, work = self.reservation()
        self.complete_stage('record', task, stage, work)
        first = self.outcome(task, stage, 'committed')
        head = self.git('rev-parse', 'HEAD')
        self.store.record(dict(id='complete-' + task, taskId=task, stageId=stage,
            kind='stage.updated', title='Complete', patch={'status': 'done'}))
        retry_checkpoint(self.registry, self.pid, task, self.state()['revision'], stage=stage)
        self.assertEqual(self.outcome(task, stage, 'committed')['id'], first['id'])
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')

    def test_unrelated_dirty_files_and_preexisting_index_are_preserved(self):
        self.enable()
        (self.root / 'unrelated.txt').write_text('unrelated dirty\n', encoding='utf-8')
        (self.root / 'staged.txt').write_text('preexisting staged\n', encoding='utf-8')
        self.git('add', 'staged.txt')
        index = self.git('ls-files', '--stage')
        staged = self.git('diff', '--cached', '--binary')
        head = self.git('rev-parse', 'HEAD')
        task, stage, work = self.reservation()
        self.complete_stage('report', task, stage, work)
        receipt = self.outcome(task, stage, 'error')
        self.assertTrue(receipt.get('reason'))
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.git('ls-files', '--stage'), index)
        self.assertEqual(self.git('diff', '--cached', '--binary'), staged)
        self.assertEqual((self.root / 'unrelated.txt').read_text(), 'unrelated dirty\n')
        self.assertEqual((self.root / 'staged.txt').read_text(), 'preexisting staged\n')
        self.git('reset', 'HEAD', '--', 'staged.txt')
        retry_checkpoint(self.registry, self.pid, task, self.state()['revision'], stage=stage)
        self.assertEqual(self.outcome(task, stage, 'committed')['id'], receipt['id'])
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')
        self.assertEqual(self.git('diff', '--cached', '--binary'), '')
        self.assertEqual((self.root / 'unrelated.txt').read_text(), 'unrelated dirty\n')
        self.assertEqual((self.root / 'staged.txt').read_text(), 'preexisting staged\n')
        self.assertEqual(self.git('show', '--format=', '--name-only', 'HEAD'), 'feature.txt')

    def test_dirty_reserved_file_is_error_without_status_loss_or_scope_expansion(self):
        self.enable()
        (self.root / 'feature.txt').write_text('preexisting\n', encoding='utf-8')
        self.git('add', 'feature.txt')
        index = self.git('ls-files', '--stage')
        task, stage, work = self.reservation()
        content = (self.root / 'feature.txt').read_bytes()
        self.complete_stage('http', task, stage, work)
        self.assertTrue(self.outcome(task, stage, 'error').get('reason'))
        retry_checkpoint(self.registry, self.pid, task, self.state()['revision'], stage=stage)
        self.outcome(task, stage, 'error')
        self.assertEqual(self.git('ls-files', '--stage'), index)
        self.assertEqual((self.root / 'feature.txt').read_bytes(), content)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1')
        self.mutate('tasks/close', dict(task=task, mode='auto'))
        self.outcome(task, None, 'error')
        self.assertEqual(self.target(task, stage)['status'], 'done')
        self.assertEqual(self.target(task, None)['status'], 'done')
        self.assertEqual(self.outcome(task, stage, 'error')['id'], self.target(task, stage)['gitCheckpoint']['id'])
        self.assertEqual(self.git('ls-files', '--stage'), index)

    def test_readonly_audit_on_dirty_repo_needs_no_coding_commit(self):
        self.enable()
        (self.root / 'feature.txt').write_text('preexisting dirty\n', encoding='utf-8')
        (self.root / 'staged.txt').write_text('preexisting staged\n', encoding='utf-8')
        self.git('add', 'staged.txt')
        head = self.git('rev-parse', 'HEAD')
        index = self.git('ls-files', '--stage')
        status = self.git('status', '--porcelain')
        contents = {name: (self.root / name).read_bytes()
                    for name in ('feature.txt', 'staged.txt', 'unrelated.txt')}
        task = self.task('Read-only audit')
        stage = self.stage(task)
        work = self.invoke('hub_begin', task=task, stage=stage, title='Inspect dirty files',
                           resources=['feature.txt', 'staged.txt'], mode='read')
        self.invoke('hub_report', work=work['work'], revision=work['revision'],
                    result='Audit complete; no coding changes', status='done', stage_status='done')
        self.outcome(task, stage, 'no_changes')
        self.mutate('tasks/close', dict(task=task, mode='auto'))
        self.outcome(task, None, 'no_changes')
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1')
        self.assertEqual(self.git('ls-files', '--stage'), index)
        self.assertEqual(self.git('status', '--porcelain'), status)
        for name, content in contents.items():
            self.assertEqual((self.root / name).read_bytes(), content)

    def test_missing_safe_scope_remains_visible_after_task_close(self):
        self.enable('task')
        task = self.task()
        (self.root / 'feature.txt').write_text('unreserved\n', encoding='utf-8')
        self.mutate('tasks/close', dict(task=task, mode='auto'))
        self.assertTrue(self.outcome(task, None, 'error').get('reason'))
        retry_checkpoint(self.registry, self.pid, task, self.state()['revision'])
        self.outcome(task, None, 'error')
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1')

    def test_scoped_head_move_records_error_without_reopening_stage(self):
        self.enable('stage')
        task, stage, work = self.reservation()
        self.git('add', 'feature.txt')
        self.git('commit', '-qm', 'Concurrent scoped commit')
        head = self.git('rev-parse', 'HEAD')
        self.complete_stage('report', task, stage, work)
        receipt = self.outcome(task, stage, 'error')
        self.assertIn('Reserved files were committed', receipt['reason'])
        self.assertEqual(self.target(task, stage)['status'], 'done')
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)

    def test_overlapping_active_reservation_does_not_block_task_status(self):
        self.enable('task')
        task, stage, work = self.reservation()
        self.complete_stage('report', task, stage, work)
        self.outcome(task, stage, 'disabled')
        other = self.task('Other active task')
        other_stage = self.stage(other)
        active = self.invoke('hub_begin', task=other, stage=other_stage,
                             title='Concurrent edit', resources=['feature.txt'], mode='write')
        head = self.git('rev-parse', 'HEAD')
        try:
            self.mutate('tasks/close', dict(task=task, mode='auto'))
            receipt = self.outcome(task, None, 'error')
            self.assertIn('Another active work reservation overlaps', receipt['reason'])
            self.assertEqual(self.target(task)['status'], 'done')
            self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        finally:
            self.invoke('hub_report', work=active['work'], revision=active['revision'],
                        result='Concurrent work remains separate', status='done')

    def test_git_failure_is_visible_and_retry_uses_original_scope(self):
        self.enable()
        task, stage, work = self.reservation()
        with patch('completion_policy.commit_work', side_effect=GitIntegrationError('fixture Git failure')):
            self.complete_stage('record', task, stage, work)
            receipt = self.outcome(task, stage, 'error')
        self.assertIn('fixture Git failure', receipt['reason'])
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1')
        stale = self.state()['revision']
        self.store.record(dict(taskId=task, kind='note', title='Change before retry'))
        with self.assertRaises(ValueError):
            retry_checkpoint(self.registry, self.pid, task, stale, stage=stage)
        self.outcome(task, stage, 'error')
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1')
        (self.root / 'unrelated.txt').write_text('later unrelated\n', encoding='utf-8')
        retry_checkpoint(self.registry, self.pid, task, self.state()['revision'], stage=stage)
        self.assertEqual(self.outcome(task, stage, 'committed')['id'], receipt['id'])
        self.assertEqual(self.git('show', '--format=', '--name-only', 'HEAD'), 'feature.txt')
        self.assertEqual((self.root / 'unrelated.txt').read_text(), 'later unrelated\n')

    def test_stale_completion_and_retry_cannot_commit(self):
        self.enable()
        task, stage, work = self.reservation()
        with self.assertRaises(HubError):
            self.invoke('hub_report', work=work['work'], revision=work['revision'] - 1,
                        result='Stale', status='done', stage_status='done')
        self.release(work)
        stale = self.state()['revision']
        self.store.record(dict(taskId=task, kind='note', title='Concurrent edit'))
        with self.assertRaises(ValueError):
            self.store.record(dict(taskId=task, stageId=stage, kind='stage.updated',
                                  title='Stale', patch={'status': 'done'}), expected_revision=stale)
        for route, body in (('stages/update', dict(task=task, stage=stage, patch={'status': 'done'})),
                            ('tasks/close', dict(task=task, mode='manual'))):
            status, _ = self.request('/api/v1/' + route, dict(body, expected=stale))
            self.assertEqual(status, 409)
        with self.assertRaises(HubError):
            self.invoke('hub_plan', task=task, stage=stage, title='Stage', status='done', expected=stale)
        with self.assertRaises(ValueError):
            retry_checkpoint(self.registry, self.pid, task, stale, stage=stage)
        self.assertNotEqual(self.target(task, stage)['status'], 'done')
        self.assertNotEqual(self.target(task)['status'], 'done')
        self.assertNotIn('gitCheckpoint', self.target(task, stage))
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '1')

    def test_retry_recovers_commit_after_result_is_lost(self):
        self.enable()
        task, stage, work = self.reservation()
        original = completion_policy.commit_work

        def commit_then_lose_result(*args, **kwargs):
            original(*args, **kwargs)
            raise GitIntegrationError('fixture lost commit acknowledgement')

        with patch('completion_policy.commit_work', side_effect=commit_then_lose_result):
            self.complete_stage('plan', task, stage, work)
            failed = self.outcome(task, stage, 'error')
        head = self.git('rev-parse', 'HEAD')
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')
        self.assertIn('Project-Hub-Checkpoint: ' + failed['id'], self.git('log', '-1', '--format=%B'))
        retry_checkpoint(self.registry, self.pid, task, self.state()['revision'], stage=stage)
        recovered = self.outcome(task, stage, 'committed')
        self.assertEqual(recovered['id'], failed['id'])
        self.assertEqual(recovered['sha'], head)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')

    def test_slow_background_git_does_not_block_settings_read_or_write(self):
        self.enable()
        task, stage, work = self.reservation()
        self.release(work)
        entered, release = threading.Event(), threading.Event()
        original = completion_policy.commit_work

        def slow_commit(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise GitIntegrationError('fixture timed out waiting to release Git')
            return original(*args, **kwargs)

        completed = threading.Event()
        results = {}

        def access_settings():
            try:
                results['read'] = self.invoke('hub_settings')
                results['write'] = self.invoke('hub_settings',
                    patch={'viewer': {'wrapLines': not results['read']['settings']['viewer']['wrapLines']}},
                    expected=results['read']['revision'])
            except Exception as error:
                results['error'] = error
            finally:
                completed.set()

        worker = None
        with patch('completion_policy.commit_work', side_effect=slow_commit):
            try:
                started = time.monotonic()
                self.invoke('hub_plan', task=task, stage=stage, title='Stage', status='done',
                            expected=self.state()['revision'])
                self.assertLess(time.monotonic() - started, 5, 'Completion waited for slow Git')
                self.assertTrue(entered.wait(3), 'Background Git did not start')
                row = self.target(task, stage)
                self.assertEqual(row['status'], 'done')
                self.assertEqual(row['gitCheckpoint']['status'], 'pending')
                worker = threading.Thread(target=access_settings, daemon=True)
                worker.start()
                self.assertTrue(completed.wait(3), 'Settings blocked behind background Git')
                self.assertNotIn('error', results, results)
                self.assertNotEqual(results['read']['revision'], results['write']['revision'])
                self.assertNotEqual(results['read']['settings']['viewer']['wrapLines'],
                                    results['write']['settings']['viewer']['wrapLines'])
            finally:
                release.set()
                if worker is not None:
                    worker.join(10)
                self.outcome(task, stage, 'committed')
