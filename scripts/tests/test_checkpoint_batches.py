"""Public batch preview/reconciliation retains all original checkpoint history."""
import json
from urllib.parse import urlencode
from urllib.request import urlopen
from unittest.mock import patch
from test_checkpoint_reconciliation import CheckpointReconciliationTest


class CheckpointBatchTest(CheckpointReconciliationTest):
    def pair(self):
        task, stage, work = self.reserve()
        (self.root / 'feature.txt').write_text('first\n')
        with patch('completion_policy.commit_work', side_effect=ValueError('Fixture defers Git to explicit review')):
            first = self.close_stage(task, stage, work)
        other, next_stage, next_work = self.reserve()
        (self.root / 'feature.txt').write_text('first\nsecond\n')
        second = self.close_stage(other, next_stage, next_work)
        self.assertEqual(first['status'], 'error')
        self.assertEqual(second['status'], 'error')
        self.git('add', 'feature.txt')
        self.git('commit', '-qm', 'Shared integration without task trailers')
        sha = self.git('rev-parse', 'HEAD')
        return [{'task': task, 'stage': stage}, {'task': other, 'stage': next_stage}], sha, [first, second]

    def preview(self, targets, sha, **extra):
        return self.mutate('checkpoints/batch', dict(action='preview', targets=targets, commit=sha,
                           reason='Reviewed both sequential changes', **extra))

    def test_batch_preview_reconciliation_and_idempotent_publication(self):
        targets, sha, original = self.pair()
        with self.registry.connect() as c:
            bodies = [c.execute('SELECT body FROM completion_checkpoints WHERE id=?', (receipt['id'],)).fetchone()[0] for receipt in original]
        index = self.git('ls-files', '--stage')
        preview = self.preview(targets, sha)
        self.assertTrue(preview['ready'])
        self.assertEqual(preview['pathsCount'], 1)
        self.assertEqual(preview['changesetCount'], 2)
        self.assertEqual([self.target(**target)['gitCheckpoint']['status'] for target in targets], ['error', 'error'])
        details = self.invoke('hub_git_batch', action='details', blob=preview['batchBlob'], section='changes', limit=1)
        self.assertEqual(len(details['items']), 1)
        self.assertIsNotNone(details['next'])
        from completion_policy import batch_content
        first_change = details['items'][0]
        owned = batch_content(self.registry, self.pid, preview['batchBlob'], 'feature.txt', 'after', first_change['changeset'])
        query = urlencode(dict(project=self.pid, blob=preview['batchBlob'], path='feature.txt', side='after', changeset=first_change['changeset']))
        with urlopen('http://127.0.0.1:' + str(self.server.server_port) + '/api/checkpoints/batch-content?' + query) as response:
            self.assertEqual(response.read(), owned['data'])
            self.assertIn('attachment;', response.headers['Content-Disposition'])
        with self.assertRaises(ValueError):
            batch_content(self.registry, self.pid, preview['batchBlob'], 'proof.txt', 'after', version='0' * 64)
        result = self.mutate('checkpoints/batch', dict(action='reconcile', targets=targets, commit=sha,
                             reason=preview['reason'], confirmed=preview['batchId']))
        self.assertEqual({item['id'] for item in result['checkpoints']}, {item['id'] for item in original})
        self.assertEqual({item['batchId'] for item in result['checkpoints']}, {preview['batchId']})
        self.assertTrue(all(item['verification'] == 'reviewed-batch-content-and-ancestry' for item in result['checkpoints']))
        for target, old in zip(targets, original):
            saved = self.target(**target)['gitCheckpoint']
            self.assertEqual(saved['reconciliation']['previousResult']['reason'], old['reason'])
        revision = self.state()['revision']
        self.mutate('checkpoints/batch', dict(action='reconcile', targets=targets, commit=sha,
                    reason=preview['reason'], confirmed=preview['batchId']))
        self.assertEqual(self.state()['revision'], revision)
        self.assertEqual(self.git('ls-files', '--stage'), index)
        with self.registry.connect() as c:
            self.assertEqual(bodies, [c.execute('SELECT body FROM completion_checkpoints WHERE id=?', (receipt['id'],)).fetchone()[0] for receipt in original])

    def test_batch_wrong_confirmation_and_unknown_dirty_baseline_are_structured(self):
        targets, sha, _ = self.pair()
        preview = self.preview(targets, sha)
        refused = self.mutate('checkpoints/batch', dict(action='reconcile', targets=targets, commit=sha,
                              reason=preview['reason'], confirmed='0' * 64), expected_status=409)
        self.assertEqual(refused['reasonCode'], 'batch_preview_changed')
        self.assertEqual(refused['layer'], 'changeset')
        refused = self.mutate('checkpoints/batch', dict(action='preview', targets=[targets[1]], commit=sha,
                              reason=preview['reason']), expected_status=409)
        self.assertEqual(refused['reasonCode'], 'batch_baseline_unknown')
        self.assertTrue(all(self.target(**target)['gitCheckpoint']['status'] == 'error' for target in targets))

    def test_batch_registration_backup_and_transfer_preserve_original_access(self):
        targets, sha, _ = self.pair()
        preview = self.preview(targets, sha)
        from completion_policy import batch_details, batch_content
        from knowledge_store import KnowledgeStore
        from git_batch_store import load
        from git_changesets import ChangesetError
        from task_transfer import transfer
        source = KnowledgeStore(self.registry, self.pid)
        marker = source.data / 'git-batches' / preview['batchBlob']
        marker.unlink()
        with self.assertRaises(ChangesetError) as refused:
            batch_details(self.registry, self.pid, preview['batchBlob'])
        self.assertEqual(refused.exception.reason_code, 'batch_unregistered')
        # Repeating the legitimate preview registers the immutable evidence.
        self.preview(targets, sha)
        backup = source.backup()
        self.assertEqual(backup['gitBatches'], [preview['batchBlob']])
        other = self.projects['b']
        restored = KnowledgeStore(self.registry, other)
        incomplete = dict(backup, blobs=dict(backup['blobs']))
        del incomplete['blobs'][preview['batchBlob']]
        with self.assertRaises(ValueError):
            restored.restore_backup(incomplete)
        restored.restore_backup(backup)
        self.assertEqual(load(restored, preview['batchBlob'])['id'], preview['batchId'])
        # A copied CAS/marker alone does not grant access in another project.
        with self.assertRaises(ChangesetError) as refused:
            batch_details(self.registry, other, preview['batchBlob'])
        self.assertEqual(refused.exception.reason_code, 'batch_reference_missing')
        self.mutate('checkpoints/batch', dict(action='reconcile', targets=targets, commit=sha,
                    reason=preview['reason'], confirmed=preview['batchId']))
        moved = transfer(self.registry, self.pid, other, targets[0]['task'], preview=True)
        transfer(self.registry, self.pid, other, targets[0]['task'], moved['revision'], 'batch-transfer')
        # The historical checkpoint retains its source CAS and full batch proof.
        (restored.data / 'git-batches' / preview['batchBlob']).unlink()
        details = batch_details(self.registry, other, preview['batchBlob'])
        self.assertEqual(details['batchId'], preview['batchId'])
        self.assertEqual(batch_content(self.registry, other, preview['batchBlob'], 'feature.txt')['data'], (self.root / 'feature.txt').read_bytes())

    def test_batch_legacy_migration_preview_does_not_fabricate_content(self):
        task, stage, work = self.reserve(dirty=True, legacy=True)
        self.commit(task)
        original = self.close_stage(task, stage, work)
        preview = self.preview([{'task': task, 'stage': stage}], self.git('rev-parse', 'HEAD'))
        self.assertFalse(preview['ready'])
        self.assertEqual(preview['issues'][0]['reasonCode'], 'legacy_boundary_unproven')
        self.assertEqual(self.target(task, stage)['gitCheckpoint'], original)
        self.assertNotIn('batchId', preview)

    def test_batch_partial_publication_retries_metadata_without_git_write(self):
        targets, sha, original = self.pair()
        preview = self.preview(targets, sha)
        from project_portal import Store
        record = Store.record
        failed = [False]
        def once(store, event, *args, **kwargs):
            if event.get('patch', {}).get('gitCheckpoint', {}).get('sha') == sha and not failed[0]:
                failed[0] = True
                raise OSError('Fixture journal interruption')
            return record(store, event, *args, **kwargs)
        with patch.object(Store, 'record', once):
            result = self.mutate('checkpoints/batch', dict(action='reconcile', targets=targets, commit=sha,
                                reason=preview['reason'], confirmed=preview['batchId']))
        self.assertTrue(failed[0])
        pending = [item for item in result['checkpoints'] if item.get('publication', {}).get('status') == 'pending']
        self.assertEqual(len(pending), 1)
        with patch('completion_policy._run', side_effect=AssertionError('No Git read on publication retry')), \
                patch('completion_policy.commit_work', side_effect=AssertionError('No Git write on publication retry')):
            self.mutate('checkpoints/batch', dict(action='reconcile', targets=targets, commit=sha,
                        reason=preview['reason'], confirmed=preview['batchId']))
        self.assertEqual(self.git('rev-parse', 'HEAD'), sha)
        self.assertTrue(all(not self.target(**target)['gitCheckpoint'].get('publication') for target in targets))


def load_tests(loader, tests, pattern):
    import unittest
    return unittest.TestSuite(CheckpointBatchTest(name) for name in CheckpointBatchTest.__dict__ if name.startswith('test_batch_'))
