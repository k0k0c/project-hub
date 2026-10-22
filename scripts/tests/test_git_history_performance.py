"""Git history batching contracts using disposable repositories only."""
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/project-portal/plugins/project-hub/scripts'))
import git_integration as adapter


class GitHistoryPerformanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'fixture@example.test')
        self.git('config', 'user.name', 'Fixture')
        self.shas = [self.commit('initial.txt', 'Initial')]

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.PIPE).decode().strip()

    def commit(self, name, title):
        (self.root / name).write_text(title, encoding='utf-8')
        self.git('add', '--', name)
        self.git('commit', '-q', '-m', title)
        return self.git('rev-parse', 'HEAD')

    def upstream(self, sha):
        self.git('update-ref', 'refs/heads/upstream-fixture', sha)
        self.git('branch', '--set-upstream-to=upstream-fixture')

    def test_cold_history_batches_files_and_ancestry_and_reuses_repository_projection(self):
        for number in range(6):
            self.shas.append(self.commit(f'file {number}.txt', f'Commit {number}'))
        self.upstream(self.shas[3])
        actual_run = subprocess.run
        with patch.object(adapter, 'repository', wraps=adapter.repository) as repository, \
                patch.object(adapter.subprocess, 'run', wraps=actual_run) as processes:
            history = adapter.git_history(self.root)
        repository.assert_called_once_with(self.root)
        commands = [call.args[0] for call in processes.call_args_list]
        self.assertEqual(1, sum('diff-tree' in command for command in commands))
        self.assertFalse(any('merge-base' in command for command in commands))
        self.assertEqual(1, sum('rev-list' in command and '--stdin' in command for command in commands))
        by_sha = {item['sha']: item for item in history}
        self.assertEqual(set(self.shas), set(by_sha))
        for index, sha in enumerate(self.shas):
            self.assertEqual(adapter._commit_files(self.root, sha), by_sha[sha]['files'])
            self.assertEqual(index <= 3, by_sha[sha]['pushed'])

    def test_divergence_and_upstream_rewrite_refresh_ancestry(self):
        local = self.commit('local.txt', 'Local only')
        self.git('checkout', '-q', '-b', 'other', self.shas[0])
        remote = self.commit('remote.txt', 'Remote only')
        self.git('checkout', '-q', '-')
        self.upstream(remote)
        first = {item['sha']: item for item in adapter.git_history(self.root)}
        self.assertTrue(first[self.shas[0]]['pushed'])
        self.assertFalse(first[local]['pushed'])
        self.upstream(local)
        self.assertTrue(next(item for item in adapter.git_history(self.root) if item['sha'] == local)['pushed'])
        self.upstream(remote)
        self.assertFalse(next(item for item in adapter.git_history(self.root) if item['sha'] == local)['pushed'])

    def test_full_range_is_not_limited_and_path_tokens_remain_unambiguous(self):
        for number, name in enumerate((self.shas[0], 'space name.txt', 'unicode-имя.txt', 'last.txt')):
            self.shas.append(self.commit(name, f'Commit {number}'))
        full = adapter.history(self.root, limit=None, range_spec=f'{self.shas[0]}..HEAD')
        self.assertEqual(4, len(full))
        self.assertEqual(2, len(adapter.history(self.root, limit=2)))
        for commit in full:
            self.assertEqual(adapter._commit_files(self.root, commit['sha']), commit['files'])
            self.assertIsNone(commit['pushed'])

    def test_merge_file_semantics_match_single_commit_projection(self):
        self.commit('main.txt', 'Main')
        self.git('checkout', '-q', '-b', 'side', self.shas[0])
        self.commit('side.txt', 'Side')
        self.git('checkout', '-q', '-')
        self.git('merge', '--no-ff', '-m', 'Merge side', 'side')
        for commit in adapter.git_history(self.root):
            self.assertEqual(adapter._commit_files(self.root, commit['sha']), commit['files'])

    def test_explicit_upstream_commit_check_avoids_repository_status(self):
        with patch.object(adapter, 'repository', side_effect=AssertionError('Unnecessary status scan')):
            self.assertTrue(adapter.commit_pushed(self.root, self.shas[0], 'HEAD'))

    def test_read_cache_reuses_history_but_refreshes_worktree_index_and_head(self):
        adapter.cached_read_projection(self.root)
        with patch.object(adapter, 'history', wraps=adapter.history) as history, \
                patch.object(adapter.subprocess, 'run', wraps=subprocess.run) as processes:
            info, commits = adapter.cached_read_projection(self.root)
        history.assert_not_called()
        self.assertEqual(len(processes.call_args_list), 4)
        commits[0]['files'].append('caller mutation')
        self.assertNotIn('caller mutation', adapter.cached_read_projection(self.root)[1][0]['files'])
        (self.root / 'untracked.txt').write_text('new')
        self.assertIn('untracked.txt', adapter.cached_read_repository(self.root)['changedFiles'])
        self.git('add', 'untracked.txt')
        self.assertTrue(adapter.cached_read_repository(self.root)['dirty'])
        self.git('commit', '-qm', 'New tracked file')
        refreshed, history = adapter.cached_read_projection(self.root)
        self.assertFalse(refreshed['dirty'])
        self.assertNotEqual(info['head'], refreshed['head'])
        self.assertEqual(len(history), 2)

    def test_read_cache_invalidates_upstream_config_and_detached_head(self):
        local = self.commit('local.txt', 'Local')
        self.upstream(self.shas[0])
        first, history = adapter.cached_read_projection(self.root)
        self.assertEqual(first['ahead'], 1)
        self.assertFalse(next(item for item in history if item['sha'] == local)['pushed'])
        self.upstream(local)
        second, history = adapter.cached_read_projection(self.root)
        self.assertEqual(second['ahead'], 0)
        self.assertTrue(next(item for item in history if item['sha'] == local)['pushed'])
        included = self.root / 'included-config'
        included.write_text('[remote "origin"]\n\turl = https://github.com/example/one.git\n')
        self.git('config', 'include.path', str(included))
        self.assertEqual(adapter.cached_read_repository(self.root)['githubUrl'], 'https://github.com/example/one')
        included.write_text('[remote "origin"]\n\turl = https://github.com/example/two.git\n')
        self.assertEqual(next(item for item in adapter.cached_read_projection(self.root)[1]
                              if item['sha'] == local)['githubUrl'],
                         'https://github.com/example/two/commit/' + local)
        self.git('checkout', '--detach', '-q', self.shas[0])
        detached, history = adapter.cached_read_projection(self.root)
        self.assertEqual(detached['branch'], '(detached HEAD)')
        self.assertEqual(len(history), 1)

    def test_parallel_readers_share_validation_and_write_paths_bypass_cache(self):
        adapter.cached_read_projection(self.root)
        scanning, release, second_entered = threading.Event(), threading.Event(), threading.Event()
        original_status, original_entry = adapter._status_rows, adapter._read_entry
        def status(root):
            scanning.set()
            self.assertTrue(release.wait(5))
            return original_status(root)
        def entry(root):
            result = original_entry(root)
            if scanning.is_set():
                second_entered.set()
            return result
        with patch.object(adapter, '_status_rows', side_effect=status) as scans, \
                patch.object(adapter, '_read_entry', side_effect=entry):
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(adapter.cached_read_repository, self.root)
                self.assertTrue(scanning.wait(5))
                second = pool.submit(adapter.cached_read_projection, self.root)
                try:
                    self.assertTrue(second_entered.wait(5))
                finally:
                    release.set()
                self.assertTrue(first.result()['available'])
                self.assertTrue(second.result()[0]['available'])
            self.assertEqual(scans.call_count, 1)
        with patch.object(adapter, '_cached_read', side_effect=AssertionError('write preflight used cache')):
            snapshot = adapter.work_snapshot(self.root, ['initial.txt'])
            (self.root / 'initial.txt').write_text('changed')
            result = adapter.commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Fresh preflight')
        self.assertEqual(result['status'], 'committed')

    def test_cached_read_never_treats_status_failure_as_clean(self):
        adapter.cached_read_projection(self.root)
        with patch.object(adapter, '_status_rows', side_effect=adapter.GitIntegrationError('status failed')):
            self.assertFalse(adapter.cached_read_repository(self.root)['available'])
        with patch.object(adapter, 'history', side_effect=adapter.GitIntegrationError('history failed')):
            with self.assertRaisesRegex(adapter.GitIntegrationError, 'history failed'):
                adapter.cached_read_projection(self.root, limit=7)

    def test_read_cache_keeps_linked_worktree_index_and_head_independent(self):
        linked = self.root.parent / (self.root.name + '-linked')
        self.git('worktree', 'add', '-q', '-b', 'linked-fixture', str(linked))
        self.addCleanup(lambda: self.git('worktree', 'remove', '--force', str(linked)))
        main, _ = adapter.cached_read_projection(self.root)
        branch, _ = adapter.cached_read_projection(linked)
        self.assertNotEqual(main['root'], branch['root'])
        self.assertEqual(main['common'], branch['common'])
        (linked / 'linked-only.txt').write_text('linked change')
        self.assertTrue(adapter.cached_read_repository(linked)['dirty'])
        self.assertFalse(adapter.cached_read_repository(self.root)['dirty'])
        subprocess.run(['git','-C',str(linked),'add','linked-only.txt'], check=True, capture_output=True)
        subprocess.run(['git','-C',str(linked),'commit','-qm','Linked commit'], check=True, capture_output=True)
        self.assertEqual(len(adapter.cached_read_projection(linked)[1]), 2)
        self.assertEqual(len(adapter.cached_read_projection(self.root)[1]), 1)


if __name__ == '__main__':
    unittest.main()
