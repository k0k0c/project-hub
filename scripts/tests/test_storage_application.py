"""Active-path publication, rollback and shared-write admission on disposable homes."""
from contextlib import ExitStack
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
import uuid
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import storage_application as application
from storage_operations import Operations, status, internal, backup_directory
from project_registry import ProjectRegistry
from project_portal import PortalServer
from hub_backup import BackupError
from hub_launcher import validate_config
from hub_import import inspect_home
from backup_api import Backups


class StorageApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='hub-storage-application-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.active = self.root / 'data'
        self.config_path = self.root / 'installation.json'
        self.config = dict(schemaVersion=1, dataHome=str(self.active), port=8769, language='ru')
        self.config_path.write_text(json.dumps(self.config), encoding='utf-8')
        self.environment = patch.dict(os.environ, {'PROJECT_HUB_INSTALLATION_CONFIG': str(self.config_path),
                'PROJECT_HUB_CONTROL': str(self.root / 'lifecycle/runtime-test'),
                'PROJECT_HUB_OPERATION_HOME': str(self.root / 'operations'),
                'PROJECT_HUB_CONFIGURED_HOME': str(self.active),
                'PROJECT_HUB_BACKUP_HOME': str(self.root / 'data-backups')})
        self.environment.start(); self.addCleanup(self.environment.stop)
        self.registry = ProjectRegistry(self.active, standalone=True)
        self.addCleanup(self.registry.close_connection_pool)
        self.project = self.registry.create('Current project', [], request_id=uuid.uuid4().hex)
        self.operations = Operations(self.registry)

    def prepare(self, body):
        body = dict(body, requestId=uuid.uuid4().hex, confirmed=True, origin={'section': 'data'})
        row, created = self.operations.register(body, body['requestId'])
        self.assertTrue(created)
        with patch('hub_lifecycle.supervisor_alive', return_value=True):
            self.operations.run(row['id'], lambda payload, progress: application.prepare(self.registry, payload, self.operations, progress))
        row = self.operations.read(row['id'])
        self.assertEqual(row['status'], 'running', row)
        self.assertTrue(row['blocking'])
        return row

    def incoming(self):
        incoming = ProjectRegistry(self.root / 'historical', standalone=True)
        project = incoming.create('Imported project', [], request_id=uuid.uuid4().hex)
        incoming.close_connection_pool()
        backups = Backups(self.registry)
        result = backups.execute({'action': 'import-folder', 'path': str(incoming.home),
                                  'expected': inspect_home(incoming.home)['revision']})
        from hub_import import compare_source
        compare_source(self.registry, {'action':'inspect-copy','id':result['copyId']}, lambda value:None)
        return project, result

    def publish(self, row, *, ready_failure=False):
        self.registry.close_connection_pool()
        old, new = Mock(), Mock()
        old.poll.return_value = 0
        new.poll.return_value = None
        control = self.root / 'lifecycle/runtime-test'; control.mkdir(parents=True, exist_ok=True)
        with patch('hub_lifecycle._stop'), patch('hub_lifecycle._start', return_value=new), \
             patch('hub_lifecycle._ready', side_effect=RuntimeError('not ready') if ready_failure else None):
            result = application.publish(row, self.operations, self.config_path, self.config, old, control,
                                         self.root / 'program', 8769, control.parent)
            self.assertTrue(status(self.registry)['writesPaused'])
            application.complete(row, self.operations)
            return result

    def test_import_adds_in_place_preserves_source_and_backup(self):
        from storage_merge import revision
        imported, result = self.incoming()
        source = Path(result['path']); before = revision(source)
        with patch('runtime_diagnostics.record') as events:
            row = self.prepare({'action': 'apply-import', 'id': result['copyId'],
                                'expected': inspect_home(source)['revision'], 'mode': 'add'})
        steps = [call.kwargs.get('progress', {}).get('step') for call in events.call_args_list
                 if call.args and call.args[0] == 'operation.progress']
        for step in ('current-backup', 'current-format', 'prepared-source',
                     'import-compatibility', 'import-project-files', 'current-revision', 'prepared-candidate'):
            self.assertIn(step, steps)
        self.assertNotIn('source-format', steps)
        self.assertNotIn('source-copy', steps)
        self.assertNotIn('current-copy', steps)
        file_progress = [call.kwargs['progress'] for call in events.call_args_list
                         if call.args and call.args[0] == 'operation.progress'
                         and call.kwargs.get('progress', {}).get('step') == 'import-project-files']
        self.assertTrue(file_progress[-1]['total'] > 0)
        self.assertEqual(file_progress[-1]['total'], file_progress[-1]['completed'])
        self.assertEqual('files', file_progress[-1]['unit'])
        self.assertTrue(file_progress[-1]['currentFile'].startswith('projects/' + imported['id'] + '/'))
        final, _, _ = self.publish(row)
        self.assertEqual(final['dataHome'], str(self.active))
        self.assertEqual(revision(source), before)
        self.assertFalse((self.operations.home / 'work' / row['id'] / 'current').exists())
        self.assertEqual(self.operations.read(row['id'])['cleanup']['state'], 'complete')
        self.assertTrue(Path(row['publication']['rollback']).is_dir())
        self.assertTrue(Backups(self.registry)._path(row['publication']['backupId'], '.zip').is_file())
        fresh = ProjectRegistry(self.active, standalone=True)
        try:
            self.assertEqual({p['id'] for p in fresh.list()['projects']}, {self.project['id'], imported['id']})
        finally:
            fresh.close_connection_pool()

    def test_cleanup_retains_snapshot_when_safety_archive_changed(self):
        _, result = self.incoming()
        row = self.prepare({'action':'apply-import', 'id':result['copyId'],
                            'expected':inspect_home(Path(result['path']))['revision'], 'mode':'add'})
        archive = Backups(self.registry)._path(row['publication']['backupId'], '.zip')
        with archive.open('ab') as stream:
            stream.write(b'changed-after-creation')
        self.publish(row)
        self.assertEqual(self.operations.read(row['id'])['status'], 'succeeded')
        self.assertTrue((self.operations.home / 'work' / row['id'] / 'current').is_dir())
        self.assertTrue(Path(row['publication']['rollback']).is_dir())

    def test_cleanup_rejects_a_snapshot_link_to_active_data(self):
        _, result = self.incoming()
        row = self.prepare({'action':'apply-import', 'id':result['copyId'],
                            'expected':inspect_home(Path(result['path']))['revision'], 'mode':'add'})
        self.publish(row)
        saved = self.operations.read(row['id'])
        saved.pop('cleanup', None)
        work = self.operations.home / 'work' / row['id']
        work.mkdir(parents=True, exist_ok=True)
        snapshot = work / 'current'
        try:
            snapshot.symlink_to(self.active, target_is_directory=True)
        except OSError:
            self.skipTest('Directory symlink permission unavailable')
        try:
            application.cleanup_snapshot(saved, self.operations)
            self.assertTrue(self.active.is_dir())
            self.assertTrue(snapshot.is_symlink())
        finally:
            snapshot.unlink()
        self.assertFalse(status(self.registry)['writesPaused'])
        self.assertTrue(Path(row['publication']['rollback']).is_dir())
        self.assertTrue(Backups(self.registry)._path(row['publication']['backupId'], '.zip').is_file())

    def test_change_folders_preserves_original_and_existing_archive_location(self):
        new_home, new_backups = self.root / 'new-data', self.root / 'new-backups'
        row = self.prepare({'action': 'change-folders', 'dataHome': str(new_home), 'backupHome': str(new_backups)})
        final, _, _ = self.publish(row)
        self.assertEqual(final['dataHome'], str(new_home))
        self.assertEqual(final['backupHome'], str(new_backups))
        self.assertTrue(self.active.is_dir())
        self.assertTrue(new_home.is_dir())
        self.assertTrue((self.root / 'data-backups').is_dir())
        self.assertEqual(self.operations.read(row['id'])['status'], 'succeeded')

    def test_failed_start_can_restore_previous_data_and_configuration(self):
        from storage_merge import revision
        imported, result = self.incoming()
        row = self.prepare({'action': 'apply-import', 'id': result['copyId'],
                            'expected': inspect_home(result['path'])['revision'], 'mode': 'replace-all'})
        # Snapshot preparation may initialize missing domain schemas. Verify the
        # exact live state just before publication, not a pre-initialization DB.
        before = revision(self.active)
        self.assertEqual(before, row['publication']['expectedActive'])
        with self.assertRaisesRegex(RuntimeError, 'not ready'):
            self.publish(row, ready_failure=True)
        application.rollback(row, self.operations, self.config_path)
        self.assertEqual(revision(self.active), before)
        self.assertEqual(json.loads(self.config_path.read_text()), self.config)
        self.assertFalse(status(self.registry)['writesPaused'])

    def test_stale_preview_is_rejected_before_creating_safety_backup(self):
        imported, result = self.incoming()
        from hub_import import compare_source
        preview = compare_source(self.registry, {'action':'inspect-copy','id':result['copyId']}, lambda value:None)
        self.registry.create('Changed after preview', [], request_id=uuid.uuid4().hex)
        before = len(Backups(self.registry).catalog()['backups'])
        payload = dict(action='apply-import',id=result['copyId'],expected=preview['preview']['revision'],
                       expectedActive=preview['comparison']['activeRevision'],mode='add',confirmed=True,
                       requestId=uuid.uuid4().hex)
        row,_=self.operations.register(payload,payload['requestId'])
        self.operations.run(row['id'], lambda body,progress: application.prepare(self.registry,body,self.operations,progress))
        failed=self.operations.read(row['id'])
        self.assertEqual('failed',failed['status'])
        self.assertIn('после предварительного просмотра',failed['error'])
        self.assertEqual(before,len(Backups(self.registry).catalog()['backups']))

    def test_legacy_source_is_normalized_once_and_reused_by_preview(self):
        from contextlib import closing
        import sqlite3
        from test_storage_upgrade import registry_v1, coordination_v1
        from hub_import import compare_source
        from storage_preparation import prepare as migrate
        legacy=self.root/'legacy';legacy.mkdir()
        registry_v1(legacy/'registry.sqlite3')
        (legacy/'coordination').mkdir()
        coordination_v1(legacy/'coordination/coordination.sqlite3')
        (legacy/'projects/p1').mkdir(parents=True)
        (legacy/'projects/p1/events.jsonl').write_text('',encoding='utf-8')
        original=(legacy/'registry.sqlite3').read_bytes()
        copied=Backups(self.registry).execute(dict(action='import-folder',path=str(legacy),expected=inspect_home(legacy)['revision']))
        with patch('storage_preparation.prepare',wraps=migrate) as migration:
            first=compare_source(self.registry,dict(action='inspect-copy',id=copied['copyId']),lambda value:None)
            second=compare_source(self.registry,dict(action='inspect-copy',id=copied['copyId']),lambda value:None)
        self.assertEqual(1,migration.call_count)
        self.assertTrue(first['preview']['converted'])
        self.assertEqual(first['preview']['preparedSchemas']['projectJournal'], 1)
        self.assertEqual(first['comparison']['incomingRevision'],second['comparison']['incomingRevision'])
        self.assertEqual(original,(legacy/'registry.sqlite3').read_bytes())
        cached=Backups(self.registry)._read(copied['copyId'])['preparedImport']
        self.assertTrue(Path(cached['path']).is_dir())
        with closing(sqlite3.connect(Path(cached['path'])/'registry.sqlite3')) as db:
            self.assertEqual(2,db.execute('SELECT version FROM registry_meta').fetchone()[0])

    def test_current_format_uses_the_verified_copy_without_conversion(self):
        from hub_import import compare_source
        _, copied = self.incoming()
        with patch('hub_import.copy_folder', side_effect=AssertionError('Redundant current-format copy')), \
             patch('storage_preparation.prepare', side_effect=AssertionError('Redundant current-format conversion')):
            inspected = compare_source(self.registry, dict(action='inspect-copy', id=copied['copyId']), lambda value:None)
        cached = Backups(self.registry)._read(copied['copyId'])['preparedImport']
        self.assertEqual(Path(cached['path']), Path(copied['path']))
        self.assertFalse(inspected['preview']['converted'])
        self.assertEqual(inspected['preview']['preparedSchemas']['projectJournal'], 1)

    def test_preview_rebuilds_an_outdated_cache_binding_without_reading_it(self):
        from hub_import import compare_source, prepared_import
        _, copied = self.incoming()
        backups = Backups(self.registry)
        metadata = backups._read(copied['copyId'])
        original_revision = metadata['preparedImport']['preview']['revision']
        foreign = self.root / 'another-launcher/data'
        foreign.mkdir(parents=True)
        sentinel = foreign / 'unrelated.bin'
        sentinel.write_bytes(b'Preserve this unrelated tree')
        metadata['preparedImport']['path'] = str(foreign)
        backups._save(metadata)
        with self.assertRaises(BackupError):
            prepared_import(self.registry, copied['copyId'], expected=original_revision)
        inspected = compare_source(self.registry, dict(action='inspect-copy', id=copied['copyId']), lambda value:None)
        rebound = backups._read(copied['copyId'])['preparedImport']
        self.assertEqual(Path(rebound['path']), Path(copied['path']))
        self.assertEqual(inspected['preview']['revision'], original_revision)
        self.assertEqual(sentinel.read_bytes(), b'Preserve this unrelated tree')

    def test_prepared_source_tampering_does_not_modify_active_data(self):
        from storage_merge import revision
        imported,result=self.incoming()
        source=Path(Backups(self.registry)._read(result['copyId'])['preparedImport']['path'])
        (source/'projects'/imported['id']/'unexpected-file.txt').write_text('changed',encoding='utf-8')
        payload=dict(action='apply-import',id=result['copyId'],expected=Backups(self.registry)._read(result['copyId'])['preparedImport']['preview']['revision'],
                     mode='add',confirmed=True,requestId=uuid.uuid4().hex)
        row,_=self.operations.register(payload,payload['requestId'])
        before=revision(self.active)
        self.operations.run(row['id'],lambda body,progress:application.prepare(self.registry,body,self.operations,progress))
        self.assertEqual('failed',self.operations.read(row['id'])['status'])
        self.assertEqual(before,revision(self.active))

    def test_interrupted_source_normalization_resumes_the_owned_copy(self):
        from test_storage_upgrade import registry_v1, coordination_v1
        from hub_import import compare_source
        legacy=self.root/'interrupted-legacy';legacy.mkdir()
        registry_v1(legacy/'registry.sqlite3')
        (legacy/'coordination').mkdir()
        coordination_v1(legacy/'coordination/coordination.sqlite3')
        (legacy/'projects/p1').mkdir(parents=True)
        (legacy/'projects/p1/events.jsonl').write_text('',encoding='utf-8')
        copied=Backups(self.registry).execute(dict(action='import-folder',path=str(legacy),expected=inspect_home(legacy)['revision']))
        body=dict(action='inspect-copy',id=copied['copyId'])
        with patch('storage_preparation.prepare',side_effect=RuntimeError('fixture migration stopped')):
            with self.assertRaisesRegex(RuntimeError,'migration stopped'):
                compare_source(self.registry,body,lambda value:None)
        pending=Backups(self.registry)._read(copied['copyId'])['preparedImport']
        self.assertEqual('normalizing',pending['state'])
        with patch('hub_import.copy_folder',side_effect=AssertionError('must reuse the existing source copy')):
            result=compare_source(self.registry,body,lambda value:None)
        ready=Backups(self.registry)._read(copied['copyId'])['preparedImport']
        self.assertEqual(pending['path'],ready['path'])
        self.assertEqual('ready',ready['state'])
        self.assertEqual(result['comparison']['incomingRevision'],ready['normalizedRevision'])

    def test_crash_between_renames_recovers_before_opening_database(self):
        body = {'action': 'change-folders', 'dataHome': str(self.active),
                'backupHome': str(self.root / 'data-backups')}
        row = self.prepare(body)
        stage = Path(row['publication']['candidate']); retained = Path(row['publication']['rollback'])
        self.registry.close_connection_pool()
        self.active.rename(retained)
        row['publication']['state'] = 'publishing'
        self.operations.save(row)
        config = application.recover(self.config_path)
        self.assertEqual(config, self.config)
        self.assertTrue((self.active / 'registry.sqlite3').is_file())
        self.assertTrue(stage.is_dir())
        self.assertEqual(self.operations.read(row['id'])['rollback'], 'succeeded')

    def test_folder_validation_does_not_replace_nonempty_or_nested_destination(self):
        occupied = self.root / 'occupied'; occupied.mkdir(); (occupied / 'other.txt').write_text('keep')
        with self.assertRaisesRegex(BackupError, 'не пуста'):
            application.folder_preview(self.registry, {'action': 'change-folders', 'dataHome': str(occupied),
                              'backupHome': str(self.root / 'backups'), 'confirmed': False})
        with self.assertRaises(ValueError):
            validate_config({**self.config, 'backupHome': str(self.active / 'backups')})
        self.assertEqual(backup_directory(self.registry), self.root / 'data-backups')

    def test_second_storage_change_is_not_accepted_before_first_completes(self):
        body = {'action': 'change-folders', 'dataHome': str(self.active),
                'backupHome': str(self.root / 'data-backups'), 'requestId': 'd'*32}
        row, _ = self.operations.register(body, body['requestId'])
        with self.assertRaisesRegex(BackupError, 'Дождитесь'):
            self.operations.register(dict(body, requestId='e'*32), 'e'*32)
        replay, created = self.operations.register(body, body['requestId'])
        self.assertFalse(created)
        self.assertEqual(replay['id'], row['id'])

    def test_project_management_uses_receipt_and_replays_while_paused(self):
        from project_registry import start_operation
        body = {'action': 'create', 'name': 'Durable project', 'roots': [], 'requestId': 'f'*32,
                'background': True, 'origin': {'section': 'projects'}}
        with patch('storage_operations.threading.Thread') as worker:
            first = start_operation(self.registry, body)['operation']
            replay = start_operation(self.registry, body)['operation']
        self.assertEqual(first['id'], replay['id'])
        self.assertEqual(first['action'], 'project-create')
        self.assertTrue(status(self.registry)['writesPaused'])
        self.assertEqual(worker.call_count, 1)
        self.operations.run(*worker.call_args.kwargs['args'])
        completed = self.operations.read(first['id'])
        self.assertEqual(completed['status'], 'succeeded', completed)
        self.assertEqual(completed['result']['project']['name'], 'Durable project')
        self.assertFalse(status(self.registry)['writesPaused'])

    def test_backup_job_retry_remains_idempotent_during_pause(self):
        backups = Backups(self.registry)
        with patch('threading.Thread'):
            first = backups.start({'action': 'create', 'origin': {'section': 'backups'}}, '1'*32)
            self.assertTrue(status(self.registry)['writesPaused'])
            replay = backups.start({'action': 'create', 'origin': {'section': 'backups'}}, '1'*32)
        self.assertEqual(first['id'], replay['id'])

    def test_upload_retry_is_confirmed_while_upload_barrier_is_active(self):
        backups = Backups(self.registry)
        body = {'action': 'upload-start', 'requestId': '2'*32, 'name': 'example.zip', 'size': 20,
                'origin': {'section': 'backups'}}
        first = backups.execute(body)
        self.assertTrue(status(self.registry)['writesPaused'])
        self.assertEqual(backups.upload_replay(body), first)

    def test_stale_prepared_configuration_is_rejected_without_draining(self):
        row = self.prepare({'action': 'change-folders', 'dataHome': str(self.active),
                            'backupHome': str(self.root / 'data-backups')})
        changed = dict(self.config, language='en')
        self.config_path.write_text(json.dumps(changed), encoding='utf-8')
        with patch('hub_lifecycle._stop') as stop:
            with self.assertRaisesRegex(BackupError, 'configuration changed'):
                application.publish(row, self.operations, self.config_path, changed, Mock(),
                                    self.root / 'runtime', self.root / 'program', 8769, self.root)
        stop.assert_not_called()
        self.assertNotIn('drainStarted', row['publication'])
        self.assertEqual(json.loads(self.config_path.read_text()), changed)

    def redirected_candidate(self):
        row = self.prepare({'action': 'change-folders', 'dataHome': str(self.active),
                            'backupHome': str(self.root / 'data-backups')})
        logical = Path(row['publication']['candidate'])
        physical = self.root / 'virtual-parent' / logical.name
        physical.parent.mkdir()
        logical.rename(physical)
        original_path = application.external_path
        def redirected(value, **kwargs):
            if Path(value) == logical:
                return physical
            return original_path(value, **kwargs)
        return row, redirected

    def physical_broker(self, action, row, config_path, **kwargs):
        import windows_storage_broker as broker
        publication = row['publication']
        return broker._perform(dict(action=action, row=row, configPath=str(config_path),
                                    receiptPath=publication['physicalReceiptPath']))

    def test_redirected_sibling_is_published_at_configured_home_and_can_roll_back(self):
        from types import SimpleNamespace
        from storage_merge import revision
        row, redirected = self.redirected_candidate()
        before = revision(self.active)
        with patch('storage_application.external_path', side_effect=redirected), \
             patch('storage_application.os', SimpleNamespace(name='nt')), \
             patch('windows_storage_broker.run', side_effect=self.physical_broker) as broker:
            self.publish(row)
            self.assertEqual('publish', broker.call_args.args[0])
            self.assertTrue(row['publication']['brokerRequired'])
            self.assertEqual(str(self.active), json.loads(self.config_path.read_text())['dataHome'])
            self.assertTrue(Path(row['publication']['brokerPaths']['rollback']).is_dir())
            application.rollback(row, self.operations, self.config_path)
        self.assertEqual(before, revision(self.active))
        self.assertEqual(self.config, json.loads(self.config_path.read_text()))

    def test_redirected_publication_failed_start_uses_physical_recovery_receipt(self):
        from types import SimpleNamespace
        from storage_merge import revision
        row, redirected = self.redirected_candidate()
        before = revision(self.active)
        with patch('storage_application.external_path', side_effect=redirected), \
             patch('storage_application.os', SimpleNamespace(name='nt')), \
             patch('windows_storage_broker.run', side_effect=self.physical_broker):
            with self.assertRaisesRegex(RuntimeError, 'not ready'):
                self.publish(row, ready_failure=True)
            application.rollback(row, self.operations, self.config_path)
        self.assertEqual(before, revision(self.active))
        self.assertEqual('succeeded', row['rollback'])
        self.assertFalse(status(self.registry)['writesPaused'])

    def test_changed_candidate_name_is_rejected_before_drain(self):
        row = self.prepare({'action': 'change-folders', 'dataHome': str(self.active),
                            'backupHome': str(self.root / 'data-backups')})
        row['publication']['candidate'] = str(self.root / 'unrelated-data')
        with patch('hub_lifecycle._stop') as stop:
            with self.assertRaisesRegex(BackupError, 'подтвердить папки'):
                self.publish(row)
        stop.assert_not_called()
        self.assertTrue(self.active.is_dir())

    def test_active_broker_keeps_recovery_barrier_without_renaming(self):
        from windows_storage_broker import BrokerPendingError
        row = self.prepare({'action': 'change-folders', 'dataHome': str(self.active),
                            'backupHome': str(self.root / 'data-backups')})
        row['publication'].update(brokerRequired=True, brokerPending=True, brokerPid=None, drainStarted=True)
        self.operations.save(row)
        with self.assertRaises(BrokerPendingError):
            application.recover(self.config_path)
        self.assertTrue(self.active.is_dir())
        self.assertFalse(Path(row['publication']['rollback']).exists())
        self.assertTrue(status(self.registry)['writesPaused'])

    def test_admission_pause_is_durable_and_blocks_ui_writes_but_allows_browsing(self):
        body = {'action': 'inspect-folder', 'path': str(self.root / 'source'), 'requestId': 'a'*32}
        row, _ = self.operations.register(body, body['requestId'])
        replay, created = self.operations.register(body, body['requestId'])
        self.assertFalse(created); self.assertEqual(replay['id'], row['id'])
        server = PortalServer(('127.0.0.1', 0), registry=self.registry)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        def request(path, body=None):
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            try:
                conn.request('GET' if body is None else 'POST', path, json.dumps(body) if body else None,
                             {'Content-Type': 'application/json'})
                response = conn.getresponse(); contents = response.read()
                return response.status, json.loads(contents)
            finally:
                conn.close()
        try:
            code, result = request('/api/v1/backups/status')
            self.assertEqual(code, 200); self.assertTrue(result['writesPaused'])
            self.assertEqual(result['operations'][0]['id'], row['id'])
            self.assertEqual(request('/api/v1/projects')[0], 200)
            self.assertEqual(request('/api/v1/projects', {'action': 'create', 'name': 'Blocked', 'roots': [], 'requestId': uuid.uuid4().hex})[0], 423)
        finally:
            server.shutdown(); server.server_close(); thread.join()

    def test_mcp_mutation_rejected_during_inspection_and_discovery_remains_readable(self):
        from agent_bindings import Connections
        from agent_runtime import call
        from hub_core import HubError
        connections = Connections(self.registry)
        invite = connections.invite(self.project['id'], request_id='b'*32)
        connection = connections.enroll(invite['token'], 'example-client', 'example-instance')
        self.operations.register({'action': 'inspect-folder', 'path': str(self.root / 'old')}, 'c'*32)
        result = call(self.registry, connection['token'], 'hub_projects', {'session': 'example-chat'})
        self.assertEqual(result['projects'][0]['id'], self.project['id'])
        with self.assertRaises(HubError) as error:
            call(self.registry, connection['token'], 'hub_task', {'session': 'example-chat', 'title': 'Must be blocked'})
        self.assertEqual(error.exception.body['error'], 'storage_operation_in_progress')

    def test_progress_is_throttled_without_losing_stage_final_count_or_failure_context(self):
        import runtime_diagnostics as diagnostics
        diagnostics.configure('fixture',self.root/'diagnostics')
        try:
            payload={'action':'inspect-folder','path':str(self.root/'source'),'requestId':uuid.uuid4().hex}
            row,_=self.operations.register(payload,payload['requestId'])
            def execute(payload,report):
                for completed in range(100):
                    report({'phase':'verifying','step':'hashing','currentFile':'fixture.bin',
                            'completed':completed,'total':100,'unit':'files'})
                report({'phase':'verifying','step':'hashing','completed':100,'total':100,'unit':'files'})
                final=self.operations.read(row['id'])
                self.assertEqual(final['progress']['completed'],100)
                report({'phase':'comparing','step':'database-rows','currentFile':'registry.sqlite3'})
                raise ValueError('fixture error')
            with patch('storage_operations.time.monotonic',return_value=10), \
                 patch.object(self.operations,'save',wraps=self.operations.save) as save:
                self.operations.run(row['id'],execute)
            self.assertLessEqual(save.call_count,6)
            failed=self.operations.read(row['id']);self.assertEqual(failed['status'],'failed')
            incident=diagnostics.report()['incident']
            self.assertEqual(incident['operationId'],row['id'])
            self.assertEqual(failed['phase'],'comparing')
            self.assertEqual(incident['phase'],'comparing')
            self.assertEqual(incident['currentFile'],'registry.sqlite3')
            self.assertIn('fixture error',incident['traceback'])
        finally:
            diagnostics.cleanup()


    def test_failed_import_records_choices_conflicts_and_last_attempted_file(self):
        import runtime_diagnostics as diagnostics
        from storage_merge import MergeError
        diagnostics.configure('fixture', self.root / 'diagnostics')
        self.addCleanup(diagnostics.cleanup)
        payload = dict(action='apply-import', id='a'*32, mode='add', projects=['north', 'south'],
                       includeGlobals=False, expected='revision', resolutions={'north':'replace'},
                       requestId=uuid.uuid4().hex, secret='not-a-diagnostic-field')
        row, _ = self.operations.register(payload, payload['requestId'])
        conflict = dict(type='ambiguous-global-data', area='file', path='unknown.json')
        def execute(body, report):
            report(dict(phase='comparing', step='database-rows', currentFile='registry.sqlite3'))
            report(dict(phase='comparing', step='database-rows', currentFile='incoming.sqlite3'))
            raise MergeError('Fixture conflict', conflicts=[conflict])
        with patch('storage_operations.time.monotonic', return_value=10):
            self.operations.run(row['id'], execute)
        failed = self.operations.read(row['id'])
        self.assertEqual('failed', failed['status'])
        self.assertEqual('comparing', failed['phase'])
        self.assertEqual('incoming.sqlite3', failed['progress']['currentFile'])
        self.assertEqual([conflict], failed['errorBody']['conflicts'])
        self.assertNotIn('publication', failed)
        incident = diagnostics.report()['incident']
        self.assertEqual('storage_import_conflict', incident['errorCode'])
        self.assertEqual(1, incident['conflictCount'])
        self.assertEqual('unknown.json', incident['conflictSample'][0]['path'])
        self.assertEqual('incoming.sqlite3', incident['currentFile'])
        events = [json.loads(line) for path in (self.root/'diagnostics').glob('fixture-*.jsonl')
                  for line in path.read_text(encoding='utf-8').splitlines()]
        started = next(event for event in events if event['event']=='operation.started')
        self.assertEqual(payload['requestId'], started['requestId'])
        self.assertEqual(['north', 'south'], started['choices']['projects'])
        self.assertEqual('add', started['choices']['mode'])
        self.assertFalse(started['choices']['includeGlobals'])
        self.assertNotIn('secret', started['choices'])


    def test_receipt_read_retries_only_bounded_windows_sharing_denials(self):
        from types import SimpleNamespace
        row, _ = self.operations.register({'action':'inspect-folder'}, uuid.uuid4().hex)
        receipt = self.operations.path(row['id'])
        real_open = Path.open
        attempts = []
        def transient_open(path, *args, **kwargs):
            if path == receipt:
                attempts.append(path)
                if len(attempts) < 3:
                    raise PermissionError('Fixture atomic replacement in progress')
            return real_open(path, *args, **kwargs)
        with patch('storage_operations.os', SimpleNamespace(name='nt')), \
             patch.object(Path, 'open', transient_open), patch('storage_operations.time.sleep') as sleep:
            self.assertEqual(row['id'], self.operations.read(row['id'])['id'])
        self.assertEqual(3, len(attempts))
        self.assertEqual(2, sleep.call_count)
        with patch('storage_operations.os', SimpleNamespace(name='nt')), \
             patch.object(Path, 'open', side_effect=PermissionError('Permanent denial')) as denied, \
             patch('storage_operations.time.monotonic', side_effect=[0, 1]):
            with self.assertRaisesRegex(PermissionError, 'Permanent denial'):
                self.operations.read(row['id'])
        self.assertEqual(1, denied.call_count)
        with patch('storage_operations.os', SimpleNamespace(name='posix')), \
             patch.object(Path, 'open', side_effect=PermissionError('Ordinary denial')) as denied:
            with self.assertRaisesRegex(PermissionError, 'Ordinary denial'):
                self.operations.read(row['id'])
        self.assertEqual(1, denied.call_count)


if __name__ == '__main__':
    unittest.main()
