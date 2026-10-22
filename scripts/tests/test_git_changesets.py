"""Content coverage contracts using disposable Git repositories and CAS."""
import hashlib
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/project-portal/plugins/project-hub/scripts'))
from git_changesets import capture, create, verify_coverage, identity, canonical, digest, ChangesetError


class ChangesetTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.blobs = {}
        self.git('init', '-q')
        self.git('config', 'user.email', 'coverage@example.test')
        self.git('config', 'user.name', 'Coverage Test')
        self.git('config', 'core.autocrlf', 'false')
        self.git('config', 'commit.gpgsign', 'false')
        (self.root / 'a.txt').write_bytes(b'first\nsecond\n')
        (self.root / 'b.bin').write_bytes(b'\x00\x01')
        self.commit('initial')

    def git(self, *args):
        return subprocess.run(['git', '-C', str(self.root), *args], capture_output=True, check=True).stdout.decode().strip()

    def commit(self, title):
        self.git('add', '.')
        self.git('commit', '-qm', title)
        return self.git('rev-parse', 'HEAD')

    def put(self, content):
        key = hashlib.sha256(content).hexdigest()
        self.blobs[key] = content
        return key

    def test_frozen_candidate_must_match_completed_content_before_commit(self):
        from git_integration import commit_work, work_snapshot, GitIntegrationError
        snapshot = work_snapshot(self.root, ['a.txt'])
        (self.root / 'a.txt').write_bytes(b'completed intended bytes\n')
        completed = capture(self.root, ['a.txt'], self.put)
        (self.root / 'a.txt').write_bytes(b'late unreserved bytes\n')
        initial = self.git('rev-parse', 'HEAD')
        with self.assertRaises(GitIntegrationError) as raised:
            commit_work(self.root, snapshot, 'task', 'stage', 'work', 'Completed', expected_content=completed['files'])
        self.assertEqual(raised.exception.reason_code, 'candidate_content_changed')
        self.assertEqual(self.git('rev-parse', 'HEAD'), initial)
        self.assertEqual(self.git('diff', '--cached', '--name-only'), '')
        self.assertEqual((self.root / 'a.txt').read_bytes(), b'late unreserved bytes\n')

    def test_git_eol_projection_preserves_physical_originals_and_exact_commit_bytes(self):
        self.git('config', 'core.autocrlf', 'true')
        (self.root / 'a.txt').write_bytes(b'first\r\nsecond\r\n')
        before = capture(self.root, ['a.txt'], self.put)
        self.assertEqual(self.blobs[before['sourceFiles']['a.txt']['blob']], b'first\r\nsecond\r\n')
        self.assertEqual(self.blobs[before['files']['a.txt']['blob']], b'first\nsecond\n')
        (self.root / 'a.txt').write_bytes(b'changed\r\nsecond\r\n')
        after = capture(self.root, ['a.txt'], self.put)
        change = create(before, after, [{'task': 'eol'}], actor='agent', confirmation='Reviewed the built-in EOL projection')
        sha = self.commit('EOL change')
        self.assertEqual(verify_coverage(self.root, change, sha, self.blobs.__getitem__)['verification'], 'exact-content-and-ancestry')
        self.assertEqual((self.root / 'a.txt').read_bytes(), b'changed\r\nsecond\r\n')

    def test_one_commit_covers_two_tasks_and_binary_changes_without_trailers(self):
        first = capture(self.root, ['a.txt'], self.put)
        second = capture(self.root, ['b.bin'], self.put)
        (self.root / 'a.txt').write_bytes(b'changed\nsecond\n')
        (self.root / 'b.bin').write_bytes(b'\x00\xff')
        a = create(first, capture(self.root, ['a.txt'], self.put), [{'task': 'task-a', 'stage': 'implementation'}], actor='agent', confirmation='Reviewed the before/after bytes')
        b = create(second, capture(self.root, ['b.bin'], self.put), [{'task': 'task-b'}, {'task': 'task-a', 'stage': 'integration'}], actor='agent', confirmation='Reviewed binary bytes')
        sha = self.commit('shared batch')
        original_index = self.git('ls-files', '--stage')
        covered = [verify_coverage(self.root, change, sha, self.blobs.__getitem__) for change in (a, b)]
        self.assertEqual({row['commit'] for row in covered}, {sha})
        self.assertEqual(covered[1]['associations'], b['associations'])
        self.assertEqual(original_index, self.git('ls-files', '--stage'))

    def test_dirty_baseline_is_retained_and_never_automatically_attributed(self):
        (self.root / 'a.txt').write_bytes(b'preexisting dirty bytes\n')
        before = capture(self.root, ['a.txt'], self.put)
        (self.root / 'a.txt').write_bytes(b'preexisting dirty bytes\nown change\n')
        change = create(before, capture(self.root, ['a.txt'], self.put), [{'task': 'task'}], actor='agent', confirmation='Only the new change belongs to this task')
        self.assertTrue(before['dirty'])
        self.assertEqual(self.blobs[change['changes'][0]['before']['blob']], b'preexisting dirty bytes\n')
        sha = self.commit('mixed legacy commit')
        with self.assertRaises(ChangesetError) as raised:
            verify_coverage(self.root, change, sha, self.blobs.__getitem__)
        self.assertEqual(raised.exception.reason_code, 'baseline_not_in_commit_parent')

    def test_filenames_ancestry_and_modified_boundaries_do_not_prove_content(self):
        before = capture(self.root, ['a.txt'], self.put)
        (self.root / 'a.txt').write_bytes(b'intended')
        after = capture(self.root, ['a.txt'], self.put)
        change = create(before, after, [{'task': 'task'}], actor='agent', confirmation='Reviewed')
        (self.root / 'a.txt').write_bytes(b'different bytes in same filename')
        sha = self.commit('same path')
        with self.assertRaises(ChangesetError) as raised:
            verify_coverage(self.root, change, sha, self.blobs.__getitem__)
        self.assertEqual(raised.exception.reason_code, 'coverage_mismatch')
        before['head'] = sha
        with self.assertRaises(ChangesetError):
            create(before, after, [{'task': 'task'}], actor='agent', confirmation='Reviewed')

    def test_linked_worktree_has_distinct_identity_in_same_repository(self):
        linked = self.root / 'linked'
        self.git('worktree', 'add', '--detach', str(linked), 'HEAD')
        main, other = identity(self.root), identity(linked)
        self.assertEqual(main['repositoryId'], other['repositoryId'])
        self.assertNotEqual(main['worktreeId'], other['worktreeId'])

    def test_deletion_and_new_path_are_verified_in_integration_worktree(self):
        before = capture(self.root, ['a.txt', 'renamed.txt'], self.put)
        (self.root / 'a.txt').rename(self.root / 'renamed.txt')
        change = create(before, capture(self.root, ['a.txt', 'renamed.txt'], self.put), [{'task': 'task'}], actor='agent', confirmation='Reviewed rename bytes')
        sha = self.commit('rename')
        linked = self.root.parent / (self.root.name + '-integration')
        self.git('worktree', 'add', '--detach', str(linked), 'HEAD')
        self.addCleanup(lambda: self.git('worktree', 'remove', '--force', str(linked)))
        result = verify_coverage(linked, change, sha, self.blobs.__getitem__)
        self.assertEqual(result['changeset'], change['id'])
        self.assertEqual(change['worktreeId'], before['worktreeId'])

    def test_tracked_executable_mode_is_preserved(self):
        self.git('update-index', '--chmod=+x', 'a.txt')
        if os.name != 'nt':
            (self.root / 'a.txt').chmod(0o755)
        self.git('commit', '-qm', 'executable')
        before = capture(self.root, ['a.txt'], self.put)
        self.assertEqual(before['files']['a.txt']['mode'], '100755')
        (self.root / 'a.txt').write_bytes(b'executable changed\n')
        change = create(before, capture(self.root, ['a.txt'], self.put), [{'task': 'task'}], actor='agent', confirmation='Reviewed executable content')
        sha = self.commit('executable change')
        self.assertEqual(verify_coverage(self.root, change, sha, self.blobs.__getitem__)['commit'], sha)

    def test_malformed_self_consistent_contracts_return_typed_reasons(self):
        before = capture(self.root, ['a.txt'], self.put)
        (self.root / 'a.txt').write_bytes(b'changed')
        change = create(before, capture(self.root, ['a.txt'], self.put), [{'task': 'task'}], actor='agent', confirmation='Reviewed')
        sha = self.commit('change')
        variants = []
        missing = copy.deepcopy(change)
        del missing['baseHead']
        variants.append((missing, 'invalid_changeset'))
        malformed = copy.deepcopy(change)
        malformed['changes'][0]['after'] = 'not a file record'
        variants.append((malformed, 'invalid_blob'))
        bad_link = copy.deepcopy(change)
        bad_link['associations'] = [{'task': []}]
        variants.append((bad_link, 'association_required'))
        duplicate = copy.deepcopy(change)
        duplicate['changes'] *= 2
        variants.append((duplicate, 'invalid_changeset'))
        for value, reason in variants:
            value['id'] = digest(canonical({key: item for key, item in value.items() if key != 'id'}))
            with self.subTest(reason=reason), self.assertRaises(ChangesetError) as raised:
                verify_coverage(self.root, value, sha, self.blobs.__getitem__)
            self.assertEqual(raised.exception.reason_code, reason)
        del self.blobs[change['changes'][0]['after']['blob']]
        with self.assertRaises(ChangesetError) as raised:
            verify_coverage(self.root, change, sha, self.blobs.__getitem__)
        self.assertEqual(raised.exception.reason_code, 'content_corrupt')
