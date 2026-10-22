"""Existing-commit adoption uses public routes and disposable Git repositories."""
import json
import subprocess
import time
from unittest.mock import patch

from test_manual_editing import ManualApiCase
from test_project_hub_plugin_api import Client
from project_settings import read_settings, update_settings


class CheckpointReconciliationTest(ManualApiCase):
    def setUp(self):
        super().setUp()
        self.root = self.registry.store(self.pid).root
        self.git('init', '-q')
        self.git('config', 'user.email', 'reconciliation@example.test')
        self.git('config', 'user.name', 'Checkpoint Test')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'commit.gpgsign', 'false')
        (self.root / 'feature.txt').write_text('before\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'Initial')
        self.base = self.git('rev-parse', 'HEAD')
        store = self.registry.base_store(self.pid)
        update_settings(store, {'git': {'autoCommit': True}}, read_settings(store)['revision'])
        self.client = Client('http://127.0.0.1:' + str(self.server.server_port))

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def invoke(self, tool, **args):
        return self.client.call(self.root, 'reconciliation-fixture', tool, args)

    def reserve(self, dirty=False, legacy=False):
        task = self.task('Reconciliation')
        stage = self.stage(task)
        if dirty:
            (self.root / 'feature.txt').write_text('preexisting\n')
        work = self.invoke('hub_begin', task=task, stage=stage, title='Edit', mode='write', resources=['feature.txt'])
        if legacy:
            # Emulate a persisted pre-contract reservation, only in this private
            # fixture. Original journals/checkpoint IDs are never rewritten.
            from plugin_api import ServerHub
            hub = ServerHub(self.registry)
            with hub.transaction() as c:
                snapshot = json.loads(c.execute('SELECT git_snapshot FROM work WHERE id=?', (work['work'],)).fetchone()[0])
                snapshot.pop('contentBoundary', None)
                c.execute('UPDATE work SET git_snapshot=? WHERE id=?', (json.dumps(snapshot), work['work']))
        return task, stage, work

    def commit(self, task, value='after', extra=''):
        (self.root / 'feature.txt').write_text(value + '\n')
        self.git('add', 'feature.txt')
        self.git('commit', '-qm', 'Manual integration\n\nProject-Hub-Task: ' + task + '\nProject-Hub-Stage: integration\n' + extra)
        return self.git('rev-parse', 'HEAD')

    def close_stage(self, task, stage, work):
        self.invoke('hub_report', work=work['work'], revision=work['revision'], result='Test result', status='done', stage_status='done')
        return self.settled(task, stage)

    def target(self, task, stage=None):
        target = next(t for t in self.state()['tasks'] if t['id'] == task)
        return next(s for s in target['stages'] if s['id'] == stage) if stage else target

    def settled(self, task, stage=None):
        for _ in range(200):
            result = self.target(task, stage).get('gitCheckpoint', {})
            if result and result['status'] != 'pending':
                # The worker removes its reservation immediately after publication.
                import completion_policy
                with completion_policy._jobs_lock:
                    running = (str(self.registry.home), result['id']) in completion_policy._jobs
                if not running:
                    return result
            time.sleep(.05)
        self.fail('Checkpoint did not settle')

    def adopt(self, task, stage, commits, reason='Explicit integration review', expected_status=200):
        return self.mutate('checkpoints/retry', dict(task=task, stage=stage, commits=commits, reason=reason), expected_status=expected_status)

    def test_recovered_commit_uses_prepared_subset_after_previous_stage_checkpoint(self):
        task, stage, first = self.reserve()
        (self.root / 'feature.txt').write_text('first completed\n')
        initial = self.close_stage(task, stage, first)
        self.assertEqual(initial['status'], 'committed')
        self.mutate('stages/update', dict(task=task, stage=stage, patch={'status': 'active'}))
        work = self.invoke('hub_begin', task=task, stage=stage, title='Second scope', mode='write', resources=['followup.txt'])
        (self.root / 'followup.txt').write_text('second completed\n')
        from git_changesets import ChangesetError
        with patch('completion_policy._exact_coverage', side_effect=ChangesetError('fixture_interruption', 'Post-commit verification interrupted')):
            interrupted = self.close_stage(task, stage, work)
        self.assertEqual(interrupted['status'], 'error')
        self.assertEqual(interrupted['preparedWorkIds'], [work['work']])
        sha = interrupted['gitOutcome']['sha']
        with patch('completion_policy.commit_work', side_effect=AssertionError('Existing commit must not repeat')):
            self.mutate('checkpoints/retry', dict(task=task, stage=stage))
            recovered = self.settled(task, stage)
        self.assertEqual(recovered['status'], 'committed')
        self.assertEqual(recovered['sha'], sha)
        self.assertTrue(recovered['recovered'])
        self.assertEqual(recovered['scopedFiles'], ['followup.txt'])
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '3')

    def test_historical_adoption_preserves_snapshots_errors_index_and_later_changes(self):
        task, stage, work = self.reserve(dirty=True, legacy=True)
        sha = self.commit(task)
        self.git('commit', '--amend', '-qm', 'Legacy integration\n\nProject-Hub-Task: ' + task
                 + '\n\nProject-Hub-Stage: integration\n\nProject-Hub-Work: legacy')
        sha = self.git('rev-parse', 'HEAD')
        old = self.close_stage(task, stage, work)
        self.assertEqual(old['status'], 'error')
        with self.registry.connect() as c:
            original = c.execute('SELECT body FROM completion_checkpoints WHERE id=?', (old['id'],)).fetchone()['body']
        later = self.commit('another-task', 'later')
        (self.root / 'proof.txt').write_text('unrelated staged')
        self.git('add', 'proof.txt')
        (self.root / 'feature.txt').write_text('new uncommitted')
        before_index = self.git('diff', '--cached', '--binary')
        result = self.adopt(task, stage, [sha.upper()])['checkpoint']
        self.assertEqual(result['sha'], sha)
        self.assertTrue(result['reconciled'])
        self.assertEqual(result['reconciliation']['previousResult']['status'], 'error')
        self.assertEqual(result['reconciliation']['scopedFiles'], ['feature.txt'])
        self.assertEqual(self.git('rev-parse', 'HEAD'), later)
        self.assertEqual(self.git('diff', '--cached', '--binary'), before_index)
        self.assertEqual((self.root / 'feature.txt').read_text(), 'new uncommitted')
        with self.registry.connect() as c:
            self.assertEqual(c.execute('SELECT body FROM completion_checkpoints WHERE id=?', (old['id'],)).fetchone()['body'], original)
        with self.registry.base_store(self.pid).locked():
            _, events = self.registry.base_store(self.pid)._load()
        self.assertTrue(any(e.get('patch', {}).get('gitCheckpoint', {}).get('status') == 'error' for e in events))
        revision = self.state()['revision']
        self.assertEqual(self.adopt(task, stage, [sha])['revision'], revision)
        self.adopt(task, stage, [sha], reason='Different approval', expected_status=409)

    def test_multi_commit_mcp_and_task_reuse(self):
        task, stage, work = self.reserve()
        first = self.commit(task, 'first')
        second = self.commit(task, 'second')
        self.assertEqual(self.close_stage(task, stage, work)['status'], 'error')
        self.adopt(task, stage, [second], expected_status=409)
        self.adopt(task, stage, [second, first], expected_status=409)
        result = self.invoke('hub_checkpoint', task=task, stage=stage, expected=self.state()['revision'],
                             commits=[first, second], reason='Reviewed both commits')
        self.assertEqual(result['checkpoint']['sha'], second)
        self.mutate('tasks/close', dict(task=task, mode='auto'))
        self.assertEqual(self.settled(task)['sha'], second)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '3')

    def test_shared_work_two_stages_keeps_both_immutable_links_and_commits_once(self):
        task=self.task('Shared work')
        first=self.stage(task,id='first');second=self.stage(task,id='second')
        work=self.invoke('hub_begin',task=task,stages=[first,second],phase='implementation',
                         title='Shared implementation',mode='write',resources=['feature.txt'])
        (self.root/'feature.txt').write_text('shared completed\n')
        self.invoke('hub_report',work=work['work'],revision=work['revision'],result='Both stages implemented',
                    status='done',stage=first,stage_status='done')
        one=self.settled(task,first)
        self.assertEqual(one['status'],'committed',one)
        self.mutate('stages/update',dict(task=task,stage=second,patch={'status':'done','remaining':[]}))
        two=self.settled(task,second)
        self.assertEqual(two['status'],'committed',two);self.assertEqual(two['sha'],one['sha'])
        self.assertTrue(two['reused']);self.assertEqual(self.git('rev-list','--count','HEAD'),'2')
        from knowledge_store import KnowledgeStore
        for result in (one,two):
            change=result['changesets'][0]
            body=json.loads(KnowledgeStore(self.registry,change['project']).read_blob(change['blob']))
            self.assertEqual({link['stage'] for link in body['associations']},{first,second})

    def test_shared_commit_covers_two_tasks_with_exact_frozen_content(self):
        (self.root / 'second.bin').write_bytes(b'\x00before')
        self.git('add', 'second.bin'); self.git('commit', '-qm', 'Second fixture')
        first_task, first_stage, first_work = self.reserve()
        second_task = self.task('Second contribution'); second_stage = self.stage(second_task)
        second_work = self.invoke('hub_begin', task=second_task, stage=second_stage, title='Binary change',
                                  mode='write', resources=['second.bin'])
        (self.root / 'feature.txt').write_text('first contribution\n')
        (self.root / 'second.bin').write_bytes(b'\x00second contribution\xff')
        self.git('add', 'feature.txt', 'second.bin'); self.git('commit', '-qm', 'Reviewed shared commit\n\nProject-Hub-Task: integration-only')
        sha = self.git('rev-parse', 'HEAD')
        self.assertEqual(self.close_stage(first_task, first_stage, first_work)['status'], 'error')
        self.assertEqual(self.close_stage(second_task, second_stage, second_work)['status'], 'error')
        index = self.git('ls-files', '--stage')
        first = self.adopt(first_task, first_stage, [sha])['checkpoint']
        second = self.adopt(second_task, second_stage, [sha])['checkpoint']
        self.assertEqual(first['verification'], 'exact-content-and-ancestry')
        self.assertEqual(first['batchId'], second['batchId'])
        self.assertNotEqual(first['changesets'][0]['id'], second['changesets'][0]['id'])
        self.assertEqual(first['scopedFiles'], ['feature.txt'])
        self.assertEqual(second['scopedFiles'], ['second.bin'])
        self.assertEqual(self.git('ls-files', '--stage'), index)
        self.assertEqual(self.git('rev-parse', 'HEAD'), sha)

    def test_exact_dirty_baseline_cannot_be_adopted_by_filename_or_trailer(self):
        task, stage, work = self.reserve(dirty=True)
        original_bytes = (self.root / 'feature.txt').read_bytes()
        sha = self.commit(task, 'preexisting and own change')
        self.close_stage(task, stage, work)
        result = self.adopt(task, stage, [sha], expected_status=409)
        self.assertIn('Dirty or intervening', result['error'])
        context = self.invoke('hub_context', work=work['work'])['work'][0]
        snapshot = json.loads(context['git_snapshot'])
        from knowledge_store import KnowledgeStore
        store = KnowledgeStore(self.registry, self.pid)
        before = json.loads(store.read_blob(snapshot['contentBoundary']['blob']))
        self.assertEqual(store.read_blob(before['sourceFiles']['feature.txt']['blob']), original_bytes)
        self.assertEqual(self.git('rev-parse', 'HEAD'), sha)

    def test_commit_bytes_must_match_frozen_completed_result(self):
        task, stage, work = self.reserve()
        sha = self.commit(task, 'intended')
        self.close_stage(task, stage, work)
        self.commit(task, 'different later bytes')
        other = self.git('rev-parse', 'HEAD')
        result = self.adopt(task, stage, [sha, other], expected_status=409)
        self.assertIn('immutable completed work bytes', result['error'])
        self.assertEqual(self.adopt(task, stage, [sha])['checkpoint']['sha'], sha)

    def test_large_commit_has_bounded_receipt_and_complete_paginated_details(self):
        task = self.task('Large evidence commit')
        stage = self.stage(task)
        work = self.invoke('hub_begin', task=task, stage=stage, title='Evidence', mode='write', resources=['evidence'])
        directory = self.root / 'evidence'
        directory.mkdir()
        files = []
        for number in range(260):
            path = directory / (str(number).zfill(4) + '-' + 'long-evidence-name-' * 6 + '.txt')
            path.write_text('verified\n')
            files.append(path.relative_to(self.root).as_posix())
        self.git('add', 'evidence')
        self.git('commit', '-qm', 'Evidence\n\nProject-Hub-Task: ' + task)
        sha = self.git('rev-parse', 'HEAD')
        old = self.close_stage(task, stage, work)
        with self.registry.connect() as c:
            snapshot = c.execute('SELECT body FROM completion_checkpoints WHERE id=?', (old['id'],)).fetchone()['body']
        result = self.adopt(task, stage, [sha])['checkpoint']
        self.assertEqual(result['status'], 'committed')
        self.assertEqual(result['filesCount'], len(files))
        self.assertTrue(result['detailsAvailable'])
        self.assertLess(len(json.dumps(result)), 12000)
        with self.registry.connect() as c:
            row = c.execute('SELECT body,result FROM completion_checkpoints WHERE id=?', (old['id'],)).fetchone()
        self.assertEqual(row['body'], snapshot)
        self.assertEqual(json.loads(row['result'])['files'], files)
        collected, offset = [], 0
        from completion_policy import checkpoint_details
        while offset is not None:
            page = checkpoint_details(self.registry, self.pid, old['id'], offset=offset, limit=100)
            collected.extend(page['items'])
            offset = page['next']
        self.assertEqual(collected, files)
        import http.client
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        try:
            connection.request('GET', '/api/v1/checkpoints/detail?project=' + self.pid + '&checkpoint=' + old['id'] + '&limit=10')
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            self.assertEqual(json.loads(response.read())['items'], files[:10])
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, 'selected project'):
            checkpoint_details(self.registry, self.projects['b'], old['id'])
        revision = self.state()['revision']
        self.assertEqual(self.adopt(task, stage, [sha])['revision'], revision)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')

    def test_lost_journal_ack_retries_only_metadata_without_duplicate_event(self):
        task, stage, work = self.reserve()
        sha = self.commit(task)
        old = self.close_stage(task, stage, work)
        from project_portal import Store
        original = Store.record
        def lost_ack(store, event, *args, **kwargs):
            saved = original(store, event, *args, **kwargs)
            if event.get('title') == 'Git checkpoint: committed':
                raise OSError('Lost journal acknowledgment')
            return saved
        with patch.object(Store, 'record', lost_ack):
            result = self.adopt(task, stage, [sha])['checkpoint']
        self.assertEqual(result['sha'], sha)
        self.assertEqual(result['publication']['status'], 'pending')
        self.assertIn('acknowledgment', result['publication']['reason'])
        with patch('completion_policy._run', side_effect=AssertionError('Git must not run again')):
            result = self.adopt(task, stage, [sha])['checkpoint']
        self.assertNotIn('publication', result)
        events = self.state()['allEvents']
        committed = [e for e in events if e.get('patch', {}).get('gitCheckpoint', {}).get('id') == old['id']
                     and e.get('patch', {}).get('gitCheckpoint', {}).get('status') == 'committed']
        self.assertEqual(len(committed), 1)
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')

    def test_metadata_publication_failure_is_retried_without_git_access(self):
        task, stage, work = self.reserve()
        sha = self.commit(task)
        self.close_stage(task, stage, work)
        from project_portal import Store
        from completion_policy import retry_checkpoint
        with patch.object(Store, 'record', side_effect=OSError('Journal unavailable')):
            result = self.adopt(task, stage, [sha])['checkpoint']
        self.assertEqual(result['status'], 'committed')
        self.assertEqual(result['publication']['status'], 'pending')
        self.mutate('stages/update', dict(task=task, stage=stage, patch={'status': 'active'}))
        self.adopt(task, stage, [sha], reason='Different adoption after reopen', expected_status=409)
        with patch('completion_policy._run', side_effect=AssertionError('Git must not run again')), \
                patch('completion_policy.repository', side_effect=AssertionError('No Git status on publication retry')):
            retry_checkpoint(self.registry, self.pid, task, self.state()['revision'], stage=stage)
            for _ in range(100):
                result = self.target(task, stage)['gitCheckpoint']
                if not result.get('publication'):
                    break
                time.sleep(.02)
        self.assertNotIn('publication', result)
        self.assertEqual(result['sha'], sha)
        self.assertEqual(self.target(task, stage)['status'], 'active')
        self.assertEqual(self.git('rev-list', '--count', 'HEAD'), '2')

    def test_read_only_adoption_preserves_overlapping_foreign_work_and_index(self):
        task, stage, work = self.reserve()
        sha = self.commit(task)
        self.close_stage(task, stage, work)
        other = self.task('Foreign work')
        other_stage = self.stage(other)
        foreign = self.client.call(self.root, 'foreign-agent', 'hub_begin',
            dict(task=other, stage=other_stage, title='Foreign edit', mode='write', resources=['feature.txt']))
        (self.root / 'feature.txt').write_text('foreign staged\n')
        self.git('add', 'feature.txt')
        (self.root / 'feature.txt').write_text('foreign unstaged\n')
        before = self.git('diff', '--cached', '--binary')
        self.assertEqual(self.adopt(task, stage, [sha])['checkpoint']['sha'], sha)
        self.assertEqual(self.git('diff', '--cached', '--binary'), before)
        self.assertEqual((self.root / 'feature.txt').read_text(), 'foreign unstaged\n')
        context = self.client.call(self.root, 'foreign-agent', 'hub_context', dict(work=foreign['work']))
        self.assertEqual(context['work'][0]['status'], 'active')

    def test_wrong_task_and_duplicate_trailers_rejected(self):
        for extra, foreign in [('', True), ('Project-Hub-Task: duplicate\n', False)]:
            with self.subTest(extra=extra, foreign=foreign):
                task, stage, work = self.reserve(legacy=True)
                sha = self.commit('foreign' if foreign else task, task, extra)
                self.close_stage(task, stage, work)
                before = self.state()['revision']
                self.adopt(task, stage, [sha], expected_status=409)
                self.assertEqual(self.state()['revision'], before)

    def test_missing_scope_coverage_stale_revision_and_bad_inputs(self):
        task, stage, work = self.reserve()
        sha = self.commit(task)
        self.close_stage(task, stage, work)
        revision = self.state()['revision']
        for commits, reason in [([], 'why'), ([sha[:10]], 'why'), ([sha, sha.upper()], 'why'), ([sha], ' '), ([sha], 'x' * 1201), (None, 'why')]:
            with self.subTest(commits=commits, reason=reason[:10]):
                self.adopt(task, stage, commits, reason, expected_status=409)
        status, _ = self.request('/api/v1/checkpoints/retry', dict(task=task, stage=stage, expected='stale', commits=[sha], reason='why'))
        self.assertEqual(status, 409)
        self.assertEqual(self.state()['revision'], revision)
        self.adopt(task, stage, [self.base], expected_status=409)

    def test_foreign_branch_and_tag_rejected(self):
        task, stage, work = self.reserve()
        sha = self.commit(task)
        self.close_stage(task, stage, work)
        branch = self.git('branch', '--show-current')
        self.git('checkout', '-qb', 'other', self.base)
        other = self.commit(task, 'other')
        self.git('checkout', '-q', branch)
        self.adopt(task, stage, [other], expected_status=409)
        self.git('tag', '-a', 'annotated', '-m', 'Tag', sha)
        self.adopt(task, stage, [self.git('rev-parse', 'annotated')], expected_status=409)

    def test_active_original_work_is_rejected(self):
        task, stage, work = self.reserve()
        sha = self.commit(task)
        self.mutate('stages/update', dict(task=task, stage=stage, patch={'status': 'done'}))
        self.assertEqual(self.settled(task, stage)['status'], 'error')
        self.adopt(task, stage, [sha], expected_status=409)
        self.invoke('hub_report', work=work['work'], revision=work['revision'], result='Done', status='done')
        self.assertEqual(self.adopt(task, stage, [sha])['checkpoint']['status'], 'committed')

    def test_pending_and_reopened_target_cannot_be_adopted(self):
        task, stage, work = self.reserve()
        sha = self.commit(task)
        store = self.registry.store(self.pid)
        models = self.registry.read_models
        with patch('completion_policy.schedule_checkpoint'):
            self.invoke('hub_report', work=work['work'], revision=work['revision'], result='Done', status='done', stage_status='done')
            self.adopt(task, stage, [sha], expected_status=409)
            # Materialize the pending checkpoint while its scheduler is
            # intentionally disabled.  The subsequent warm decode must resume
            # the persisted job without rebuilding the prepared view.
            with patch('read_models.time.time', return_value=1800000000):
                models.snapshot(store, observations=False, summary=True)
        with patch('read_models.time.time', return_value=1800000000), \
             patch.object(store, '_build_snapshot', side_effect=AssertionError('warm pending recovery rebuilt view')):
            models.snapshot(store, observations=False, summary=True)
        self.assertEqual(self.settled(task, stage)['status'], 'error')
        self.mutate('stages/update', dict(task=task, stage=stage, patch={'status': 'active'}))
        self.adopt(task, stage, [sha], expected_status=409)

    def test_dirty_changes_cannot_be_discarded_and_called_covered(self):
        task, stage, work = self.reserve(dirty=True)
        (self.root / 'feature.txt').write_text('before\n')
        (self.root / 'proof.txt').write_text('other change')
        self.git('add', '.')
        self.git('commit', '-qm', 'Other file\n\nProject-Hub-Task: ' + task)
        sha = self.git('rev-parse', 'HEAD')
        self.assertEqual(self.close_stage(task, stage, work)['status'], 'error')
        self.adopt(task, stage, [sha], expected_status=409)

    def test_merge_and_unselected_scoped_history_rejected(self):
        task, stage, work = self.reserve()
        branch = self.git('branch', '--show-current')
        self.git('checkout', '-qb', 'side')
        first = self.commit(task, 'side change')
        self.git('checkout', '-q', branch)
        (self.root / 'proof.txt').write_text('main change')
        self.git('add', '.')
        self.git('commit', '-qm', 'Unrelated main')
        self.git('merge', '--no-ff', 'side', '-m', 'Merge\n\nProject-Hub-Task: ' + task)
        merge = self.git('rev-parse', 'HEAD')
        self.close_stage(task, stage, work)
        self.adopt(task, stage, [first, merge], expected_status=409)
