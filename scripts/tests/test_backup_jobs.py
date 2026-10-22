"""Focused background backup job lifecycle checks."""
from contextlib import nullcontext
from pathlib import Path
import json
import tempfile
import time
import types
import unittest
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import backup_api
import project_portal
from backup_api import Backups, BackupError


class BackupJobTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.registry = types.SimpleNamespace(home=Path(self.temporary.name) / 'hub')
        self.backups = Backups(self.registry)

    def test_start_is_immediate_idempotent_and_reports_completion(self):
        request = 'a' * 32
        with patch.object(self.backups, '_lock', return_value=nullcontext()), \
             patch.object(self.backups, 'execute', return_value={'backup': {'id': 'fixture'}}):
            first = self.backups.start({'action': 'create'}, request)
            replay = self.backups.start({'action': 'create'}, request)
            self.assertEqual(replay['id'], first['id'])
            deadline = time.time() + 2
            while self.backups.job(first['id'])['status'] in ('queued', 'running') and time.time() < deadline:
                time.sleep(.01)
            result = self.backups.job(first['id'])
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(result['result']['backup']['id'], 'fixture')
        with self.assertRaisesRegex(BackupError, 'другого запроса'):
            self.backups.start({'action': 'restore-copy', 'id': 'b' * 32,
                                'expectedSha256': 'hash', 'confirmed': True}, request)

    def test_expired_running_job_becomes_interrupted_without_waiting_for_lock(self):
        job = {'id': 'c' * 32, 'requestId': 'd' * 32, 'fingerprint': 'hash',
               'action': 'create', 'status': 'running', 'leaseUntil': time.time() - 1}
        self.backups._save_job(job)
        result = self.backups.job(job['id'])
        self.assertEqual(result['status'], 'interrupted')
        self.assertIn('прервана', result['error'])

    def test_catalog_includes_jobs_without_backup_lock(self):
        job = {'id': 'e' * 32, 'requestId': 'f' * 32, 'fingerprint': 'hash',
               'action': 'create', 'status': 'queued', 'createdAt': '2026-01-01T00:00:00+00:00'}
        self.backups._save_job(job)
        catalog = self.backups.catalog()
        self.assertEqual(catalog['jobs'][0]['id'], job['id'])
        self.assertEqual(catalog['jobs'][0]['status'], 'queued')

    def test_job_read_retries_one_transient_windows_permission_error(self):
        job = {'id': 'f' * 32, 'requestId': '0' * 32, 'fingerprint': 'hash',
               'action': 'create', 'status': 'queued'}
        self.backups._save_job(job)
        path = self.backups._job_path(job['id'])
        contents = path.read_text(encoding='utf-8')
        with patch.object(backup_api.os, 'name', 'nt'), \
             patch.object(type(path), 'read_text', side_effect=[PermissionError('sharing'), contents]):
            self.assertEqual(self.backups.job(job['id'])['id'], job['id'])

    def test_job_save_retries_same_fsynced_snapshot_after_transient_sharing_error(self):
        job = {'id':'1'*32,'status':'queued','progress':{'visited':0}}
        self.backups._save_job(job)
        path = self.backups._job_path(job['id'])
        previous = path.read_bytes()
        job.update(status='running',progress={'visited':3})
        attempts = []
        replace = project_portal.os.replace
        fsync = project_portal.os.fsync
        def transient(source, target):
            self.assertEqual(target,path)
            snapshot=type(path)(source).read_bytes()
            self.assertEqual(json.loads(snapshot),job)
            attempts.append((source,snapshot))
            if len(attempts)==1:
                self.assertEqual(path.read_bytes(),previous)
                raise PermissionError('reader holds job JSON')
            return replace(source,target)
        with patch.object(project_portal.os,'name','nt'), \
             patch.object(project_portal.os,'replace',side_effect=transient), \
             patch.object(project_portal.os,'fsync',wraps=fsync) as synced:
            self.backups._save_job(job)
        self.assertEqual(len(attempts),2)
        self.assertEqual(attempts[0],attempts[1])
        synced.assert_called_once()
        self.assertEqual(json.loads(path.read_text(encoding='utf-8')),job)
        self.assertEqual(list(path.parent.glob(path.name+'.*')),[])

    def test_persistent_windows_job_save_failure_is_bounded_and_cleans_snapshot(self):
        job={'id':'2'*32,'status':'queued'}
        self.backups._save_job(job)
        path=self.backups._job_path(job['id']); previous=path.read_bytes()
        started=time.monotonic()
        with patch.object(project_portal.os,'name','nt'), \
             patch.object(project_portal.os,'replace',side_effect=PermissionError('persistent sharing')) as replace:
            with self.assertRaises(PermissionError):
                self.backups._save_job(dict(job,status='running'))
        elapsed=time.monotonic()-started
        self.assertGreater(replace.call_count,1)
        self.assertGreaterEqual(elapsed,.5)
        self.assertLess(elapsed,1.5)
        self.assertEqual(path.read_bytes(),previous)
        self.assertEqual(list(path.parent.glob(path.name+'.*')),[])

    def test_posix_permission_error_does_not_retry_replacement(self):
        path=self.registry.home/'job.json'
        project_portal.atomic_write(path,json.dumps({'status':'queued'}))
        previous=path.read_bytes()
        with patch.object(project_portal.os,'name','posix'), \
             patch.object(project_portal.os,'replace',side_effect=PermissionError('denied')) as replace, \
             patch.object(project_portal.time,'sleep') as sleep:
            with self.assertRaises(PermissionError):
                project_portal.atomic_write(path,json.dumps({'status':'running'}))
            replace.assert_called_once()
            sleep.assert_not_called()
        self.assertEqual(path.read_bytes(),previous)
        self.assertEqual(list(path.parent.glob(path.name+'.*')),[])

    def test_job_read_does_not_hide_persistent_permission_error(self):
        job = {'id': 'a' * 32, 'requestId': 'b' * 32, 'fingerprint': 'hash',
               'action': 'create', 'status': 'queued'}
        self.backups._save_job(job)
        path = self.backups._job_path(job['id'])
        started = time.monotonic()
        with patch.object(type(path), 'read_text', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError):
                self.backups.job(job['id'])
        self.assertLess(time.monotonic() - started, 1)

    def test_backup_execution_timeout_is_failed_without_retrying_execution(self):
        job = {'id': '9' * 32, 'requestId': '8' * 32, 'fingerprint': 'hash',
               'action': 'create', 'status': 'queued'}
        self.backups._save_job(job)
        with patch.object(self.backups, '_lock', return_value=nullcontext()), \
             patch.object(self.backups, 'execute', side_effect=TimeoutError('copy timeout')) as execute:
            self.backups._run_job(job['id'], {'action': 'create'})
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(self.backups.job(job['id'])['status'], 'failed')

    def test_archive_lock_wait_retries_acquisition_and_reports_waiting(self):
        job = {'id': '7' * 32, 'requestId': '6' * 32, 'fingerprint': 'hash',
               'action': 'create', 'status': 'queued'}
        self.backups._save_job(job)
        attempts = [0]

        class FlakyLock:
            def __enter__(self):
                attempts[0] += 1
                if attempts[0] == 1:
                    raise TimeoutError('busy')
                return self

            def __exit__(self, *_args):
                return False

        with patch.object(self.backups, '_lock', return_value=FlakyLock()), \
             patch.object(self.backups, 'execute', return_value={'backup': {'id': 'fixture'}}) as execute:
            self.backups._run_leased_job(job['id'], {'action': 'create'})
        self.assertEqual(attempts[0], 2)
        self.assertEqual(execute.call_count, 1)

    def test_real_background_create_uses_one_archive_lock(self):
        from project_registry import ProjectRegistry, CodexProjects
        import json
        catalog = Path(self.temporary.name) / 'catalog.json'
        catalog.write_text(json.dumps({'local-projects': {}}))
        registry = ProjectRegistry(self.registry.home, CodexProjects(catalog))
        backups = Backups(registry)
        first = backups.start({'action': 'create'}, '0' * 32)
        row = None
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                row = backups.job(first['id'])
                if row['status'] not in ('queued', 'running'):
                    break
                time.sleep(.01)
            self.assertEqual('succeeded', row['status'], row)
            self.assertTrue(backups.download(row['result']['backup']['id'])[0].is_file())
        finally:
            # Let the owned worker release its job lease before temp cleanup,
            # including when an assertion above fails.
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                row = backups.job(first['id'])
                if row['status'] not in ('queued', 'running'):
                    break
                time.sleep(.01)

    def test_live_lease_keeps_long_operation_running_and_limits_admission(self):
        from project_portal import Store
        job = {'id': '1' * 32, 'requestId': '2' * 32, 'fingerprint': 'hash',
               'action': 'create', 'status': 'running', 'leaseUntil': time.time() - 1000}
        self.backups._save_job(job)
        with Store.lock_probe(self.backups.jobs_home / (job['id'] + '.lock')).locked():
            self.assertEqual('running', self.backups.job(job['id'])['status'])
            with self.assertRaisesRegex(BackupError, 'завершения'):
                self.backups.start({'action': 'create'}, '3' * 32)
        self.assertEqual('interrupted', self.backups.job(job['id'])['status'])


if __name__ == '__main__':
    unittest.main()
