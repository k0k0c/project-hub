"""Reviewed batches prove contributions without modifying original boundaries."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from test_git_changesets import ChangesetTest
from git_changesets import (at_commit, capture, create, compose_batch, verify_batch_coverage,
                            canonical, digest, ChangesetError)


class BatchTest(ChangesetTest):
    # Reuse only fixture helpers, not the inherited contract test methods.
    def change(self, before, data, task, path='a.txt', root=None):
        root = root or self.root
        (root / path).write_bytes(data)
        after = capture(root, before['scope'], self.put)
        return create(before, after, [{'task': task}], actor='agent', confirmation='Explicit test attribution')

    def batch(self, before, changes):
        parent = at_commit(self.root, before['head'], before, self.put)
        return compose_batch(parent, changes, self.blobs.__getitem__, self.put,
                             actor='reviewer', confirmation='Reviewed the selected contributions')

    def test_batch_sequential_dirty_start_has_complete_reviewed_chain(self):
        before = capture(self.root, ['a.txt'], self.put)
        first = self.change(before, b'changed\nsecond\n', 'first')
        dirty = capture(self.root, ['a.txt'], self.put)
        second = self.change(dirty, b'changed\nfinished\n', 'second')
        batch = self.batch(before, [second, first])
        frozen = copy.deepcopy(dirty)
        sha = self.commit('shared commit without trailers')
        result = verify_batch_coverage(self.root, batch, sha, self.blobs.__getitem__, self.put)
        self.assertEqual(set(result['changesets']), {first['id'], second['id']})
        self.assertEqual(dirty, frozen)
        self.assertEqual(self.blobs[dirty['sourceFiles']['a.txt']['blob']], b'changed\nsecond\n')
        with self.assertRaises(ChangesetError) as raised:
            self.batch(before, [second])
        self.assertEqual(raised.exception.reason_code, 'batch_baseline_unknown')

    def test_batch_disjoint_hunks_from_linked_worktrees(self):
        before = capture(self.root, ['a.txt'], self.put)
        linked = self.root.parent / (self.root.name + '-batch')
        self.git('worktree', 'add', '--detach', str(linked), 'HEAD')
        self.addCleanup(lambda: self.git('worktree', 'remove', '--force', str(linked)))
        other = capture(linked, ['a.txt'], self.put)
        first = self.change(before, b'changed\nsecond\n', 'first')
        second = self.change(other, b'first\nfinished\n', 'second', root=linked)
        batch = self.batch(before, [second, first])
        self.assertEqual(batch, self.batch(before, [first, second]))
        final = json.loads(self.blobs[batch['afterBlob']])
        self.assertEqual(self.blobs[final['files']['a.txt']['blob']], b'changed\nfinished\n')
        self.assertEqual(batch['steps'][0]['method'], 'reviewed-disjoint-text-hunks')
        (self.root / 'a.txt').write_bytes(b'changed\nfinished\n')
        sha = self.commit('integrated hunks')
        result = verify_batch_coverage(self.root, batch, sha, self.blobs.__getitem__, self.put)
        self.assertEqual(len(result['associations']), 2)
        self.assertNotEqual(first['worktreeId'], second['worktreeId'])
        self.assertEqual((linked / 'a.txt').read_bytes(), b'first\nfinished\n')

    def test_batch_overlapping_hunks_and_distinct_binary_versions_refuse(self):
        before = capture(self.root, ['a.txt', 'b.bin'], self.put)
        first = self.change(before, b'changed\nsecond\n', 'first')
        second = self.change(before, b'conflicting\nsecond\n', 'second')
        with self.assertRaises(ChangesetError) as raised:
            self.batch(before, [first, second])
        self.assertEqual(raised.exception.reason_code, 'batch_conflict')
        (self.root / 'a.txt').write_bytes(b'first\nsecond\n')
        first = self.change(before, b'\0a', 'first', path='b.bin')
        second = self.change(before, b'\0b', 'second', path='b.bin')
        with self.assertRaises(ChangesetError) as raised:
            self.batch(before, [first, second])
        self.assertEqual(raised.exception.reason_code, 'batch_conflict')

    def test_batch_shared_identical_binary_and_deletion_preserve_members(self):
        before = capture(self.root, ['a.txt', 'b.bin'], self.put)
        first = self.change(before, b'\0shared', 'first', path='b.bin')
        second = self.change(before, b'\0shared', 'second', path='b.bin')
        dirty = capture(self.root, before['scope'], self.put)
        (self.root / 'a.txt').unlink()
        deletion = create(dirty, capture(self.root, before['scope'], self.put), [{'task': 'deletion'}],
                          actor='agent', confirmation='Reviewed deletion')
        batch = self.batch(before, [first, second, deletion])
        sha = self.commit('binary plus deletion')
        coverage = verify_batch_coverage(self.root, batch, sha, self.blobs.__getitem__, self.put)
        self.assertEqual(len(coverage['changesets']), 3)
        self.assertEqual(len(next(step for step in batch['steps'] if step['path'] == 'b.bin')['members']), 2)

    def test_batch_candidate_and_parent_are_verified_read_only(self):
        before = capture(self.root, ['a.txt'], self.put)
        change = self.change(before, b'intended\nsecond\n', 'first')
        batch = self.batch(before, [change])
        (self.root / 'a.txt').write_bytes(b'other\nsecond\n')
        sha = self.commit('wrong bytes')
        index = self.git('ls-files', '--stage')
        with self.assertRaises(ChangesetError) as raised:
            verify_batch_coverage(self.root, batch, sha, self.blobs.__getitem__, self.put)
        self.assertEqual(raised.exception.reason_code, 'coverage_mismatch')
        self.assertEqual(index, self.git('ls-files', '--stage'))
        (self.root / 'a.txt').write_bytes(b'intended\nsecond\n')
        late = self.commit('right bytes in wrong parent')
        with self.assertRaises(ChangesetError) as raised:
            verify_batch_coverage(self.root, batch, late, self.blobs.__getitem__, self.put)
        self.assertEqual(raised.exception.reason_code, 'batch_parent_changed')

    def test_batch_self_consistent_forged_hunk_proof_is_rebuilt(self):
        before = capture(self.root, ['a.txt'], self.put)
        change = self.change(before, b'changed\nsecond\n', 'first')
        batch = self.batch(before, [change])
        sha = self.commit('change')
        batch['steps'][0]['members'][0]['hunks'] = [{'start': 500, 'end': 501, 'replacementSha256': '0' * 64}]
        batch['id'] = digest(canonical({key: value for key, value in batch.items() if key != 'id'}))
        with self.assertRaises(ChangesetError) as raised:
            verify_batch_coverage(self.root, batch, sha, self.blobs.__getitem__, self.put)
        self.assertEqual(raised.exception.reason_code, 'batch_changed')

    def test_batch_native_writer_runs_hooks_and_preserves_unrelated_bytes(self):
        from git_integration import commit_reviewed_batch
        before = capture(self.root, ['a.txt'], self.put)
        first = self.change(before, b'changed\nsecond\n', 'first')
        dirty = capture(self.root, ['a.txt'], self.put)
        second = self.change(dirty, b'changed\nfinished\n', 'second')
        batch = self.batch(before, [first, second])
        (self.root / 'b.bin').write_bytes(b'\0unrelated')
        hook = self.root / '.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\ngit diff --cached --name-only > hook-ran.txt\n', encoding='utf-8')
        hook.chmod(0o755)
        result = commit_reviewed_batch(self.root, batch, self.blobs.__getitem__, self.put,
                                       confirmed=batch['id'], title='Reviewed batch')
        self.assertEqual(result['verification'], 'reviewed-batch-content-and-ancestry')
        self.assertEqual((self.root / 'hook-ran.txt').read_text().strip(), 'a.txt')
        self.assertEqual((self.root / 'b.bin').read_bytes(), b'\0unrelated')
        self.assertEqual(self.git('diff', '--cached', '--name-only'), '')
        self.assertEqual(result['files'], ['a.txt'])

    def test_batch_native_writer_rejects_preexisting_index_and_stale_review(self):
        from git_integration import commit_reviewed_batch, GitIntegrationError
        before = capture(self.root, ['a.txt'], self.put)
        change = self.change(before, b'changed\nsecond\n', 'first')
        batch = self.batch(before, [change])
        (self.root / 'b.bin').write_bytes(b'\0staged')
        self.git('add', 'b.bin')
        index = self.git('ls-files', '--stage')
        with self.assertRaises(GitIntegrationError) as raised:
            commit_reviewed_batch(self.root, batch, self.blobs.__getitem__, self.put, confirmed=batch['id'], title='Batch')
        self.assertEqual(raised.exception.reason_code, 'index_preexisting')
        self.assertEqual(self.git('ls-files', '--stage'), index)
        self.git('reset', 'HEAD', '--', 'b.bin')
        with self.assertRaises(ChangesetError) as raised:
            commit_reviewed_batch(self.root, batch, self.blobs.__getitem__, self.put, confirmed='0' * 64, title='Batch')
        self.assertEqual(raised.exception.reason_code, 'batch_preview_changed')
        (self.root / 'a.txt').write_bytes(b'late\nsecond\n')
        with self.assertRaises(ChangesetError) as raised:
            commit_reviewed_batch(self.root, batch, self.blobs.__getitem__, self.put, confirmed=batch['id'], title='Batch')
        self.assertEqual(raised.exception.reason_code, 'completed_bytes_changed')
        self.assertEqual(self.git('rev-parse', 'HEAD'), before['head'])

    def test_batch_native_cli_consumes_existing_cas_without_database_writes(self):
        before = capture(self.root, ['a.txt'], self.put)
        change = self.change(before, b'changed\nsecond\n', 'first')
        batch = self.batch(before, [change])
        blob = self.put(canonical(batch))
        with tempfile.TemporaryDirectory() as directory:
            location = Path(directory)
            for identifier, data in self.blobs.items():
                path = location / 'blobs' / identifier[:2] / identifier
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            baseline = sorted(str(path.relative_to(location)) for path in location.rglob('*') if path.is_file())
            entry = Path(__file__).resolve().parents[2] / 'tools/project-portal/plugins/project-hub/scripts/client_entry.py'
            result = subprocess.run([sys.executable, '-S', str(entry), 'git-batch', '--root', str(self.root),
                '--cas', directory, '--batch-blob', blob, '--confirmed', batch['id'], '--title', 'Native CLI batch'],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt['batchId'], batch['id'])
            self.assertEqual(receipt['sha'], self.git('rev-parse', 'HEAD'))
            self.assertEqual(baseline, sorted(str(path.relative_to(location)) for path in location.rglob('*') if path.is_file()))


# unittest does not duplicate the imported fixture contract suite here.
def load_tests(loader, tests, pattern):
    import unittest
    names = [name for name in BatchTest.__dict__ if name.startswith('test_batch_')]
    return unittest.TestSuite(BatchTest(name) for name in names)
