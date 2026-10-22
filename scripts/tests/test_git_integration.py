import subprocess
import tempfile
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/project-portal/plugins/project-hub/scripts'))
import git_integration as git_adapter
from git_integration import GitIntegrationError, commit_work, git_history, push_repository, repository, work_snapshot


class GitIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'hub@example.test')
        self.git('config', 'user.name', 'Project Hub Test')
        (self.root / 'feature.txt').write_text('before\n', encoding='utf-8')
        self.git('add', 'feature.txt')
        self.git('commit', '-q', '-m', 'Initial')

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], check=True, capture_output=True, text=True)

    def test_repository_projection_and_github_remote(self):
        self.git('remote', 'add', 'origin', 'git@github.com:k0k0c/project-hub.git')
        info = repository(self.root)
        self.assertTrue(info['available'])
        self.assertEqual(info['githubUrl'], 'https://github.com/k0k0c/project-hub')
        self.assertEqual(info['github']['branch'], 'https://github.com/k0k0c/project-hub/tree/master')
        self.assertEqual(info['github']['issues'], 'https://github.com/k0k0c/project-hub/issues')
        self.assertEqual(info['github']['pulls'], 'https://github.com/k0k0c/project-hub/pulls')
        self.assertEqual(info['github']['actions'], 'https://github.com/k0k0c/project-hub/actions')
        self.assertEqual(info['github']['compare'], 'https://github.com/k0k0c/project-hub/compare/master?expand=1')
        self.assertFalse(info['dirty'])

    def test_scoped_commit_keeps_metadata_and_files(self):
        snapshot = work_snapshot(self.root, ['feature.txt'])
        (self.root / 'feature.txt').write_text('after\n', encoding='utf-8')
        commit = commit_work(self.root, snapshot, 'hub-task', 'implementation', 'work-1', 'Implement feature')
        self.assertEqual(commit['status'], 'committed')
        self.assertEqual(len(commit['files']), 1)
        message = self.git('log', '-1', '--format=%B').stdout
        self.assertIn('Project-Hub-Task: hub-task', message)
        self.assertIn('Project-Hub-Stage: implementation', message)

    def test_preexisting_changes_are_not_captured(self):
        (self.root / 'feature.txt').write_text('already dirty\n', encoding='utf-8')
        snapshot = work_snapshot(self.root, ['feature.txt'])
        (self.root / 'feature.txt').write_text('changed again\n', encoding='utf-8')
        with self.assertRaisesRegex(GitIntegrationError, 'уже были изменения'):
            commit_work(self.root, snapshot, 'hub-task', 'implementation', 'work-1', 'Implement feature')

    def test_git_lock_error_keeps_primary_diagnostic_and_lock(self):
        snapshot = work_snapshot(self.root, ['feature.txt'])
        (self.root / 'feature.txt').write_text('agent change\n', encoding='utf-8')
        lock = self.root / '.git' / 'index.lock'
        lock.write_text('another process owns this lock', encoding='utf-8')
        try:
            with self.assertRaises(GitIntegrationError) as caught:
                commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Checkpoint')
            self.assertIn('index.lock', str(caught.exception))
            self.assertIn('Unable to create', str(caught.exception))
            self.assertEqual(lock.read_text(encoding='utf-8'), 'another process owns this lock')
            self.assertEqual(self.git('rev-parse', 'HEAD').stdout.strip(), snapshot['head'])
        finally:
            lock.unlink()

    def test_failed_commit_does_not_reset_concurrent_index_change(self):
        snapshot = work_snapshot(self.root, ['feature.txt'])
        (self.root / 'feature.txt').write_text('agent change\n', encoding='utf-8')
        original = git_adapter._run

        def run(root, *args, **kwargs):
            if 'commit' in args[:2]:
                (self.root / 'feature.txt').write_text('concurrent user change\n', encoding='utf-8')
                self.git('add', 'feature.txt')
                raise GitIntegrationError('hook failed')
            return original(root, *args, **kwargs)

        with patch.object(git_adapter, '_run', side_effect=run):
            with self.assertRaisesRegex(GitIntegrationError, 'index or HEAD changed'):
                commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Checkpoint')
        self.assertIn('+concurrent user change', self.git('diff', '--cached', '--', 'feature.txt').stdout)
        self.assertEqual(self.git('rev-parse', 'HEAD').stdout.strip(), snapshot['head'])

    def test_failed_commit_reports_index_cleanup_blocked_by_lock(self):
        snapshot = work_snapshot(self.root, ['feature.txt'])
        (self.root / 'feature.txt').write_text('agent change\n', encoding='utf-8')
        lock = self.root / '.git' / 'index.lock'
        original = git_adapter._run

        def run(root, *args, **kwargs):
            if 'commit' in args[:2]:
                lock.write_text('another process owns this lock', encoding='utf-8')
                raise GitIntegrationError('commit hook failed')
            return original(root, *args, **kwargs)

        try:
            with patch.object(git_adapter, '_run', side_effect=run):
                with self.assertRaises(GitIntegrationError) as caught:
                    commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Checkpoint')
            self.assertIn('commit hook failed', str(caught.exception))
            self.assertIn('Checkpoint-staged files remain in the index', str(caught.exception))
            self.assertTrue(lock.exists())
            self.assertEqual(git_adapter._staged_paths(self.root), ['feature.txt'])
        finally:
            lock.unlink(missing_ok=True)

    def test_frozen_index_excludes_late_staged_foreign_file(self):
        snapshot = work_snapshot(self.root, ['feature.txt'])
        (self.root / 'feature.txt').write_text('agent change\n', encoding='utf-8')
        (self.root / 'outside.txt').write_text('foreign staged change\n', encoding='utf-8')
        original = git_adapter._run

        def run(root, *args, **kwargs):
            if 'commit' in args[:2]:
                self.git('add', 'outside.txt')
            return original(root, *args, **kwargs)

        with patch.object(git_adapter, '_run', side_effect=run):
            receipt = commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Checkpoint')
        self.assertEqual(receipt['files'], ['feature.txt'])
        self.assertEqual(git_adapter._staged_paths(self.root), ['outside.txt'])
        self.assertEqual(self.git('show', '--format=', '--name-only', 'HEAD').stdout.strip(), 'feature.txt')

    def test_frozen_index_excludes_late_worktree_edit_of_reserved_file(self):
        snapshot = work_snapshot(self.root, ['feature.txt'])
        (self.root / 'feature.txt').write_text('agent change\n', encoding='utf-8')
        original = git_adapter._run

        def run(root, *args, **kwargs):
            if 'commit' in args[:2]:
                (self.root / 'feature.txt').write_text('late foreign edit\n', encoding='utf-8')
            return original(root, *args, **kwargs)

        with patch.object(git_adapter, '_run', side_effect=run):
            receipt = commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Checkpoint')
        self.assertEqual(receipt['files'], ['feature.txt'])
        self.assertEqual(self.git('show', 'HEAD:feature.txt').stdout, 'agent change\n')
        self.assertEqual((self.root / 'feature.txt').read_text(encoding='utf-8'), 'late foreign edit\n')
        self.assertEqual(git_adapter._staged_paths(self.root), [])

    def test_snapshot_does_not_compute_remote_projection_or_repeat_status(self):
        (self.root / 'unrelated.txt').write_text('user change', encoding='utf-8')
        with patch.object(git_adapter, 'repository', side_effect=AssertionError('UI projection')):
            with patch.object(git_adapter, '_run', wraps=git_adapter._run) as run:
                snapshot = work_snapshot(self.root, ['feature.txt'])
        self.assertTrue(snapshot['available'])
        self.assertEqual(snapshot['dirty'], [])
        self.assertEqual(snapshot['allDirty'], [dict(code='??', path='unrelated.txt')])
        self.assertEqual([call.args[1:] for call in run.call_args_list], [
            ('rev-parse', '--show-toplevel'), ('rev-parse', 'HEAD'),
            ('status', '--porcelain=v1', '-z', '--untracked-files=all')])

    def test_snapshot_status_failure_never_becomes_clean_boundary(self):
        with patch.object(git_adapter, '_status_rows', side_effect=GitIntegrationError('status timed out')):
            snapshot = work_snapshot(self.root, ['feature.txt'])
        self.assertFalse(snapshot['available'])
        (self.root / 'feature.txt').write_text('after', encoding='utf-8')
        self.assertEqual(commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Title')['status'], 'unavailable')

    def test_push_requires_explicit_confirmation(self):
        with self.assertRaisesRegex(GitIntegrationError, 'явного подтверждения'):
            push_repository(self.root)

    def test_unicode_and_untracked_snapshot_preserves_user_changes(self):
        for tracked in (True, False):
            with self.subTest(tracked=tracked):
                name = '\u043e\u0442\u0447\u0451\u0442.txt' if tracked else '\u043d\u043e\u0432\u044b\u0439.txt'
                path = self.root / name
                path.write_text('baseline', encoding='utf-8')
                if tracked:
                    self.git('add', '--', name)
                    self.git('commit', '-qm', 'Unicode baseline')
                path.write_text('user change', encoding='utf-8')
                snapshot = work_snapshot(self.root, [name])
                before = self.git('rev-parse', 'HEAD').stdout
                self.assertEqual(snapshot['dirty'][0]['path'], name)
                with self.assertRaises(GitIntegrationError):
                    commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Rejected')
                self.assertEqual(self.git('rev-parse', 'HEAD').stdout, before)
                self.assertEqual(path.read_text(encoding='utf-8'), 'user change')
                self.assertEqual(git_adapter._staged_paths(self.root), [])

    def test_snapshot_tracks_both_rename_endpoints(self):
        self.git('mv', 'feature.txt', '\u043d\u043e\u0432\u044b\u0439.txt')
        for resource in ('feature.txt', '\u043d\u043e\u0432\u044b\u0439.txt'):
            snapshot = work_snapshot(self.root, [resource])
            self.assertEqual(snapshot['dirty'][0]['originalPath'], 'feature.txt')
            with self.assertRaises(GitIntegrationError):
                commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Rejected')
        self.assertEqual(len(git_adapter._staged_paths(self.root)), 2)

    def test_directory_snapshot_rejects_preexisting_unicode_file(self):
        folder = self.root / 'docs'
        folder.mkdir()
        name = '\u043e\u0442\u0447\u0451\u0442.txt'
        (folder / name).write_text('baseline', encoding='utf-8')
        self.git('add', 'docs')
        self.git('commit', '-qm', 'Docs baseline')
        (folder / name).write_text('user edit', encoding='utf-8')
        snapshot = work_snapshot(self.root, ['docs'])
        (folder / 'plain.txt').write_text('agent edit', encoding='utf-8')
        with self.assertRaises(GitIntegrationError):
            commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Rejected')
        self.assertEqual(git_adapter._staged_paths(self.root), [])
        self.assertEqual((folder / name).read_text(encoding='utf-8'), 'user edit')

    def test_push_receipt_exceeds_history_display_limit(self):
        with tempfile.TemporaryDirectory() as remote:
            self.git('init', '--bare', remote)
            self.git('remote', 'add', 'origin', remote)
            self.git('push', '-u', 'origin', 'HEAD')
            parent = self.git('rev-parse', 'HEAD').stdout.strip()
            tree = self.git('rev-parse', 'HEAD^{tree}').stdout.strip()
            sent = set()
            for index in range(201):
                parent = self.git('commit-tree', tree, '-p', parent, '-m', f'Outgoing {index}').stdout.strip()
                sent.add(parent)
            self.git('update-ref', 'HEAD', parent)
            result = push_repository(self.root, confirmed=True)
            self.assertEqual({row['sha'] for row in result['commits']}, sent)

    def test_literal_untracked_filename_is_committed_without_unrelated_changes(self):
        name = '[feature] \u043e\u0442\u0447\u0451\u0442.txt'
        (self.root / 'feature.txt').write_text('preexisting', encoding='utf-8')
        snapshot = work_snapshot(self.root, [name])
        (self.root / name).write_text('new', encoding='utf-8')
        result = commit_work(self.root, snapshot, 'task', 'stage', 'work', 'New file')
        self.assertEqual(result['files'], [name])
        self.assertEqual(repository(self.root)['changedFiles'], ['feature.txt'])

    def test_status_nul_parser_keeps_arrow_and_newline_names(self):
        with patch.object(git_adapter, '_run', return_value=' M line\n -> name\0R  target\0old -> source\0'):
            self.assertEqual(git_adapter._status_rows(self.root), [
                {'code': ' M', 'path': 'line\n -> name'},
                {'code': 'R ', 'path': 'target', 'originalPath': 'old -> source'}])

    def test_staging_validation_rejects_unrelated_file_and_preserves_it(self):
        snapshot = work_snapshot(self.root, ['feature.txt'])
        (self.root / 'feature.txt').write_text('agent', encoding='utf-8')
        (self.root / 'outside.txt').write_text('user', encoding='utf-8')
        original = git_adapter._run
        def run(root, *args, **kwargs):
            result = original(root, *args, **kwargs)
            if args[:2] == ('--literal-pathspecs', 'add'):
                self.git('add', 'outside.txt')
            return result
        before = self.git('rev-parse', 'HEAD').stdout
        with patch.object(git_adapter, '_run', side_effect=run):
            with self.assertRaises(GitIntegrationError):
                commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Rejected')
        self.assertEqual(self.git('rev-parse', 'HEAD').stdout, before)
        self.assertEqual(git_adapter._staged_paths(self.root), ['outside.txt'])
        self.assertEqual((self.root / 'feature.txt').read_text(), 'agent')

    def test_push_receipt_uses_pinned_head_and_pre_push_upstream(self):
        with tempfile.TemporaryDirectory() as remote:
            self.git('init', '--bare', remote)
            self.git('remote', 'add', 'origin', remote)
            self.git('push', '-u', 'origin', 'HEAD')
            sent = []
            for index in range(3):
                self.git('commit', '--allow-empty', '-qm', f'Outgoing {index}')
                sent.append(self.git('rev-parse', 'HEAD').stdout.strip())
            original = git_adapter._run
            def run(root, *args, **kwargs):
                if args[0] == 'push':
                    self.git('commit', '--allow-empty', '-qm', 'Concurrent local commit')
                return original(root, *args, **kwargs)
            with patch.object(git_adapter, '_run', side_effect=run):
                result = push_repository(self.root, confirmed=True)
            self.assertEqual({row['sha'] for row in result['commits']}, set(sent))
            self.assertTrue(all(row['pushed'] for row in result['commits']))
            self.assertEqual(self.git('rev-parse', '@{u}').stdout.strip(), sent[-1])
            self.assertEqual(result['ahead'], 1)
            push_repository(self.root, confirmed=True)
            self.assertEqual(push_repository(self.root, confirmed=True)['commits'], [])

    def test_commit_receipt_rejects_index_change_during_commit(self):
        snapshot = work_snapshot(self.root, ['feature.txt'])
        (self.root / 'feature.txt').write_text('agent change', encoding='utf-8')
        original = git_adapter._run
        def run(root, *args, **kwargs):
            if 'commit' in args[:2]:
                self.git('reset', 'HEAD', '--', 'feature.txt')
                self.git('commit', '--allow-empty', '-qm', 'Concurrent index change')
                return ''
            return original(root, *args, **kwargs)
        with patch.object(git_adapter, '_run', side_effect=run):
            with self.assertRaisesRegex(GitIntegrationError, 'состав файлов изменился'):
                commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Checkpoint')
        self.assertEqual((self.root / 'feature.txt').read_text(), 'agent change')
        self.assertEqual(git_adapter._staged_paths(self.root), [])

    def test_history_normalizes_author_timezone_and_sorts_instants(self):
        self.git('commit', '--allow-empty', '-qm', 'Later instant', '--date=2026-09-15T01:00:00Z')
        self.git('commit', '--allow-empty', '-qm', 'Earlier instant', '--date=2026-09-15T03:00:00+03:00')
        rows = [row for row in git_history(self.root) if row['message'].endswith('instant')]
        self.assertEqual([row['message'] for row in rows], ['Later instant', 'Earlier instant'])
        self.assertEqual(rows[1]['at'], '2026-09-15T00:00:00Z')

    def test_history_reads_project_hub_trailers_without_guessing(self):
        (self.root / 'feature.txt').write_text('tracked\n', encoding='utf-8')
        self.git('add', 'feature.txt')
        self.git('commit', '-q', '-m', 'Tracked change\n\nProject-Hub-Task: hub-task\nProject-Hub-Stage: stage-1\nProject-Hub-Work: work-1')
        rows = git_history(self.root, 10)
        tracked = next(row for row in rows if row['message'] == 'Tracked change')
        self.assertEqual(tracked['taskId'], 'hub-task')
        self.assertEqual(tracked['stageId'], 'stage-1')
        self.assertEqual(tracked['workId'], 'work-1')
        self.assertEqual(tracked['fileCount'], 1)
        self.assertFalse(any(row.get('taskId') for row in rows if row['message'] == 'Initial'))


if __name__ == '__main__':
    unittest.main()
