import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
import windows_storage_broker as broker


class WindowsStorageBrokerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='storage-broker-')
        self.root = Path(self.temp.name)
        self.home = self.root / 'data'; self.home.mkdir()
        (self.home / 'marker.txt').write_text('old', encoding='utf-8')
        self.candidate = self.root / ('.data-publish-' + 'a' * 32)
        self.rollback = self.root / ('.data-before-' + 'a' * 32)
        self.candidate.mkdir(); (self.candidate / 'marker.txt').write_text('new', encoding='utf-8')
        self.config = self.root / 'installation.json'
        config = {'schemaVersion': 1, 'dataHome': str(self.home), 'port': 8769, 'language': 'en'}
        self.config.write_text(json.dumps(config), encoding='utf-8')
        self.receipt = self.root / ('a' * 32 + '.json')
        self.row = {'id': 'a' * 32, 'requestId': 'b' * 32, 'action': 'import',
                    'publication': {'originalConfig': config, 'nextConfig': config,
                                    'sourceIdentity': broker.identity(self.home),
                                    'candidateIdentity': broker.identity(self.candidate),
                                    'brokerPaths': {'source': str(self.home), 'target': str(self.home),
                                                    'candidate': str(self.candidate), 'rollback': str(self.rollback),
                                                    'failedTarget': str(self.root / ('.data-failed-' + 'a' * 32))},
                                    'physicalConfigPath': str(self.config),
                                    'physicalReceiptPath': str(self.receipt)}}
        self.receipt.write_text(json.dumps(self.row), encoding='utf-8')

    def tearDown(self):
        self.temp.cleanup()

    def _ticket(self, action='publish'):
        publication = self.row['publication']
        return {'action': action, 'row': self.row, 'configPath': str(self.config),
                'receiptPath': str(self.receipt), 'resultPath': str(self.root / 'result.json')}

    def test_publish_records_steps_and_moves_physical_tree(self):
        result = broker._perform(self._ticket())
        self.assertEqual('published', result['publication']['state'])
        self.assertTrue(self.home.is_dir())
        self.assertTrue(self.rollback.is_dir())
        self.assertFalse(self.candidate.exists())
        self.assertEqual('new', (self.home / 'marker.txt').read_text(encoding='utf-8'))
        self.assertEqual('published', json.loads(self.receipt.read_text())['publication']['state'])

    def test_rejects_untrusted_candidate_name(self):
        ticket = self._ticket()
        ticket['row']['publication']['brokerPaths']['candidate'] = str(self.root / 'candidate')
        with self.assertRaisesRegex(ValueError, 'Physical storage path'):
            broker._validate(ticket)

    def test_rollback_restores_retained_home_and_config(self):
        broker._perform(self._ticket('publish'))
        result = broker._perform(self._ticket('rollback'))
        self.assertEqual('rolled-back', result['publication']['state'])
        self.assertTrue(self.home.is_dir())
        self.assertFalse(self.rollback.exists())
        self.assertEqual('old', (self.home / 'marker.txt').read_text(encoding='utf-8'))
        self.assertEqual(str(self.home), json.loads(self.config.read_text())['dataHome'])

    def test_launcher_failure_is_bounded_and_does_not_claim_success(self):
        with patch.object(broker, '_launch', return_value=subprocess.CompletedProcess([], 1)):
            with self.assertRaisesRegex(broker.BrokerError, 'Не удалось запустить'):
                broker.run('publish', self.row, self.config)

    def test_missing_launcher_does_not_leave_an_unknown_live_broker(self):
        with patch.object(broker, '_launch', side_effect=FileNotFoundError('fixture missing launcher')):
            with self.assertRaises(broker.BrokerError):
                broker.run('publish', self.row, self.config)
        self.assertFalse(json.loads(self.receipt.read_text())['publication']['brokerPending'])
        self.assertEqual('old', (self.home / 'marker.txt').read_text(encoding='utf-8'))

    def test_dispatch_receipt_failure_keeps_helper_pending(self):
        completed = subprocess.CompletedProcess([], 0, stdout='424242\n')
        write = broker._write
        def denied_dispatch(path, value):
            if Path(path).name == 'dispatch.json':
                raise PermissionError('fixture sharing race after dispatch')
            return write(path, value)
        with patch.object(broker, '_launch', return_value=completed), patch.object(broker, '_write', side_effect=denied_dispatch):
            with self.assertRaises(broker.BrokerPendingError):
                broker.run('publish', self.row, self.config)
        self.assertTrue(json.loads(self.receipt.read_text())['publication']['brokerPending'])

    def test_changed_candidate_identity_is_rejected(self):
        self.row['publication']['candidateIdentity'] = [0, 0]
        self.receipt.write_text(json.dumps(self.row), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Physical storage directory changed'):
            broker._perform(self._ticket())

    def test_folder_change_keeps_original_source_and_restores_new_target(self):
        source = self.root / 'source'; target = self.root / 'target'
        source.mkdir(); target.mkdir()
        (source / 'marker.txt').write_text('old-source', encoding='utf-8')
        candidate = self.root / ('.target-publish-' + 'a' * 32); candidate.mkdir()
        (candidate / 'marker.txt').write_text('new-target', encoding='utf-8')
        retained = self.root / ('.target-before-' + 'a' * 32)
        failed = self.root / ('.target-failed-' + 'a' * 32)
        original = {'schemaVersion': 1, 'dataHome': str(source), 'port': 8769, 'language': 'en'}
        next_config = dict(original, dataHome=str(target))
        self.config.write_text(json.dumps(original), encoding='utf-8')
        self.row['publication'].update(originalConfig=original, nextConfig=next_config,
                                      sourceIdentity=broker.identity(source), candidateIdentity=broker.identity(candidate),
                                      brokerPaths={'source': str(source), 'target': str(target),
                                                   'candidate': str(candidate), 'rollback': str(retained),
                                                   'failedTarget': str(failed)})
        self.receipt.write_text(json.dumps(self.row), encoding='utf-8')
        broker._perform(self._ticket())
        self.assertEqual('old-source', (source / 'marker.txt').read_text(encoding='utf-8'))
        self.assertEqual('new-target', (target / 'marker.txt').read_text(encoding='utf-8'))
        broker._perform(self._ticket('rollback'))
        self.assertFalse(target.exists())
        self.assertEqual('old-source', (source / 'marker.txt').read_text(encoding='utf-8'))
        self.assertEqual('new-target', (failed / 'marker.txt').read_text(encoding='utf-8'))

    def test_shadow_stage_is_retired_and_restored(self):
        stage = self.root / 'stage'; stage.mkdir()
        candidate = stage / ('.data-publish-' + 'a' * 32); candidate.mkdir()
        (candidate / 'marker.txt').write_text('new', encoding='utf-8')
        shadow = stage / 'data'; shadow.mkdir(); (shadow / 'marker.txt').write_text('shadow-old', encoding='utf-8')
        shadow_retained = stage / ('.data-shadow-before-' + 'a' * 32)
        publication = self.row['publication']
        publication.update(candidateIdentity=broker.identity(candidate), shadowIdentity=broker.identity(shadow),
                           sourceIdentity=broker.identity(shadow),
                           brokerPaths={'source': str(self.home), 'target': str(self.home),
                                        'candidate': str(candidate), 'rollback': str(self.rollback),
                                        'failedTarget': str(self.root / ('.data-failed-' + 'a' * 32)),
                                        'shadowSource': str(shadow), 'shadowRollback': str(shadow_retained)})
        self.receipt.write_text(json.dumps(self.row), encoding='utf-8')
        broker._perform(self._ticket())
        self.assertTrue(shadow_retained.is_dir())
        self.assertEqual(broker.identity(shadow_retained), publication['runtimeSourceIdentity'])
        self.assertEqual(broker.identity(self.rollback), publication['sourceIdentity'])
        broker._perform(self._ticket('rollback'))
        self.assertTrue(shadow.is_dir())
        self.assertFalse(shadow_retained.exists())
        self.assertEqual('shadow-old', (shadow / 'marker.txt').read_text(encoding='utf-8'))

    def test_tampered_retained_identity_and_shadow_parent_are_rejected(self):
        broker._perform(self._ticket())
        self.row['publication']['sourceIdentity'] = [0, 0]
        self.receipt.write_text(json.dumps(self.row), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Physical storage directory changed'):
            broker._perform(self._ticket('rollback'))
        self.row['publication']['sourceIdentity'] = broker.identity(self.home)
        self.row['publication']['brokerPaths']['rollback'] = str(self.root / 'wrong-retained')
        self.receipt.write_text(json.dumps(self.row), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Physical storage path'):
            broker._validate(self._ticket('rollback'))
        self.row['publication']['brokerPaths']['rollback'] = str(self.rollback)
        self.row['publication']['brokerPaths']['shadowSource'] = str(self.root / 'wrong' / 'data')
        self.row['publication']['brokerPaths']['shadowRollback'] = str(self.root / 'wrong' / ('.data-shadow-before-' + 'a' * 32))
        self.receipt.write_text(json.dumps(self.row), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'shadow'):
            broker._validate(self._ticket('rollback'))

    def test_failure_after_retaining_keeps_journal_and_paths(self):
        calls = {'count': 0}
        original = broker._journal
        def fail_after_retain(ticket, state):
            calls['count'] += 1
            if calls['count'] == 2:
                raise OSError('fixture publish interruption')
            return original(ticket, state)
        with patch.object(broker, '_journal', side_effect=fail_after_retain):
            with self.assertRaisesRegex(OSError, 'interruption'):
                broker._perform(self._ticket())
        self.assertTrue(self.rollback.is_dir())
        self.assertTrue(self.candidate.is_dir())
        self.assertEqual('retaining', json.loads(self.receipt.read_text())['publication']['state'])
        broker._perform(self._ticket('rollback'))
        self.assertTrue(self.home.is_dir())
        self.assertEqual('old', (self.home / 'marker.txt').read_text(encoding='utf-8'))

    def test_config_write_failure_leaves_recovery_paths_for_retry(self):
        broker._perform(self._ticket())
        real_write = broker._write
        def fail_config(path, value):
            if Path(path) == self.config:
                raise OSError('fixture config lock')
            return real_write(path, value)
        with patch.object(broker, '_write', side_effect=fail_config):
            with self.assertRaisesRegex(OSError, 'config lock'):
                broker._perform(self._ticket('rollback'))
        self.assertTrue(self.home.is_dir())
        self.assertTrue((self.root / ('.data-failed-' + 'a' * 32)).is_dir())
        broker._perform(self._ticket('rollback'))
        self.assertEqual('old', (self.home / 'marker.txt').read_text(encoding='utf-8'))
        self.assertEqual('rolled-back', self.row['publication']['state'])

    def test_pending_launcher_preserves_ticket_and_receipt(self):
        completed = subprocess.CompletedProcess([], 0, stdout='424242\n')
        with patch.object(broker, '_launch', return_value=completed), patch.object(broker, 'MAX_WAIT', 0):
            with self.assertRaises(broker.BrokerPendingError) as raised:
                broker.run('publish', self.row, self.config)
        self.assertTrue(Path(raised.exception.row['publication']['brokerTicket']).is_file())
        self.assertTrue(self.receipt.is_file())

    def test_async_launcher_can_publish_result_before_returning_pid(self):
        def launch(ticket_path, application_home=None):
            self.assertEqual(0, broker._helper(ticket_path))
            return subprocess.CompletedProcess([], 0, stdout='424242\n')
        with patch.object(broker, '_launch', side_effect=launch):
            result = broker.run('publish', self.row, self.config)
        self.assertFalse(result['publication']['brokerPending'])
        self.assertEqual('new', (self.home / 'marker.txt').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
