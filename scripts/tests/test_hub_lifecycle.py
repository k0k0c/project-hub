"""Focused lifecycle lease, activation and supervisor sequencing checks."""
import json
from contextlib import nullcontext
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import sys
sys.path.insert(0, str(Path(__file__).parents[1]))
import hub_lifecycle as lifecycle


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hub-lifecycle-test-')
        self.root = Path(self.temp.name)
        self.environment = patch.dict(lifecycle.os.environ, {'PROJECT_HUB_INSTANCE_HOME':str(self.root / 'instances'),
                                                             'PROJECT_HUB_RUNTIME_MODE':'installed'})
        self.environment.start()

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def test_home_lease_excludes_another_process_and_releases_on_exit(self):
        home = self.root / 'data'
        home.mkdir()
        with lifecycle.home_lease(home):
            with self.assertRaises(TimeoutError):
                with lifecycle.home_lease(home):
                    pass
        with lifecycle.home_lease(home):
            pass

    def test_publication_diagnostic_context_keeps_paths_and_pre_drain_state(self):
        row = {'id': 'a' * 32, 'requestId': 'b' * 32, 'action': 'import', 'phase': 'publishing',
               'publication': {'source': 'C:/source', 'target': 'C:/target',
                               'candidate': 'C:/candidate', 'rollback': 'C:/rollback',
                               'normalization': {'projects': ['one', 'two']},
                               'state': 'validating'}}
        fields = lifecycle._publication_diagnostic_fields(row)
        self.assertEqual('C:/source', fields['source'])
        self.assertEqual('C:/candidate', fields['candidate'])
        self.assertEqual('C:/rollback', fields['rollback'])
        self.assertEqual('validating', fields['publicationState'])
        self.assertFalse(fields['drainStarted'])

    def test_activation_request_is_idempotent_and_rejects_pending_conflict(self):
        control = self.root / 'control'
        control.mkdir()
        source = self.root / 'active'; target = self.root / 'copy'
        source.mkdir(); target.mkdir()
        (self.root / 'supervisor.lock').touch()
        with patch.dict(lifecycle.os.environ, {'PROJECT_HUB_CONTROL': str(control)}), \
             patch.object(lifecycle, 'supervisor_alive', return_value=True), \
             patch('hub_import.inspect_home', return_value={'revision': 'hash'}), \
             patch('hub_launcher.external_path', side_effect=lambda value: Path(value).resolve()):
            first = lifecycle.request_activation(target, current_home=source,
                                                 request_id='a' * 32, expected='hash')
            self.assertEqual(lifecycle.request_activation(target, current_home=source,
                                                          request_id='a' * 32, expected='hash'), first)
            with self.assertRaisesRegex(lifecycle.LifecycleError, 'already pending'):
                lifecycle.request_activation(target, current_home=source,
                                             request_id='b' * 32, expected='hash')
        self.assertEqual(json.loads((control / 'switch.json').read_text())['id'], 'a' * 32)

    def test_lost_ack_replays_receipt_after_catalog_changes(self):
        control = self.root / 'control'; control.mkdir()
        source = self.root / 'active'; target = self.root / 'copy'
        source.mkdir(); target.mkdir(); (self.root / 'supervisor.lock').touch()
        with patch.dict(lifecycle.os.environ, {'PROJECT_HUB_CONTROL': str(control)}), \
             patch.object(lifecycle, 'supervisor_alive', return_value=True), \
             patch('hub_import.inspect_home', return_value={'revision': 'hash'}), \
             patch('hub_launcher.external_path', side_effect=lambda value: Path(value).resolve()):
            first = lifecycle.request_activation(target, current_home=source,
                                                 request_id='c' * 32, expected='hash', copy_id='copy-1')
            path = control.parent / 'activation-jobs' / ('c' * 32 + '.json')
            row = json.loads(path.read_text())
            row.update(status='succeeded', activeHome=str(target))
            path.write_text(json.dumps(row), encoding='utf-8')
            with patch('hub_import.inspect_home', side_effect=AssertionError('replayed receipt must not re-inspect')):
                replay = lifecycle.request_activation(target, current_home=source,
                                                      request_id='c' * 32, expected='hash', copy_id='copy-1')
        self.assertEqual(replay['status'], 'succeeded')

    def test_supervisor_rolls_back_when_new_runtime_fails_ready(self):
        config_path = self.root / 'installation.json'
        application_home = self.root / 'app'; application_home.mkdir()
        active = self.root / 'active'; target = self.root / 'target'
        active.mkdir(); target.mkdir()
        original = {'schemaVersion': 1, 'dataHome': str(active), 'port': 8769, 'language': 'en'}
        config_path.write_text(json.dumps(original), encoding='utf-8')
        jobs = config_path.parent / 'lifecycle' / 'activation-jobs'; jobs.mkdir(parents=True)
        job_path = jobs / ('a' * 32 + '.json')
        old, new, rollback = (Mock() for _ in range(3))
        old.poll.return_value = None; new.poll.return_value = None; rollback.poll.return_value = 0
        def ready(process, home, port):
            if not hasattr(ready, 'calls'):
                ready.calls = 0
            ready.calls += 1
            if ready.calls == 3:
                self.assertEqual(json.loads(config_path.read_text(encoding='utf-8')), original)
            if ready.calls == 2:
                raise lifecycle.LifecycleError('new runtime failed')
        def enqueue(_):
            if not job_path.exists():
                job_path.write_text(json.dumps({'id': 'a' * 32, 'status': 'queued', 'payload': {
                    'source': str(active), 'target': str(target), 'expected': 'hash'}}), encoding='utf-8')

        with patch.object(lifecycle, 'file_lock', return_value=nullcontext()), \
             patch.object(lifecycle, 'home_lease', return_value=nullcontext()), \
             patch.object(lifecycle, '_start', side_effect=[old, new, rollback]) as start, \
             patch.object(lifecycle, '_ready', side_effect=ready), \
             patch.object(lifecycle, '_stop') as stop, \
             patch.object(lifecycle.time, 'sleep', side_effect=enqueue), \
             patch('hub_launcher.configure', return_value=original), \
             patch('hub_launcher.available_port', return_value=8769), \
             patch('hub_launcher.remember'), patch('hub_launcher.validate_config', side_effect=lambda value, **_: value), \
             patch('hub_import.inspect_home', return_value={'revision': 'hash', 'storageSchemas': {'registry': 2}}), \
             patch('backup_api.Backups') as backups:
            backups.return_value.catalog.return_value = {'jobs': []}
            lifecycle.supervise(config_path, application_home=application_home)
        self.assertEqual(start.call_count, 3)
        self.assertEqual(start.call_args_list[1].kwargs, {'expected': 'hash'})
        self.assertEqual(start.call_args_list[0].kwargs, {})
        self.assertEqual(start.call_args_list[2].kwargs, {})
        self.assertEqual(stop.call_count, 2)
        result = json.loads(job_path.read_text(encoding='utf-8'))
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['rollback'], 'succeeded')
        self.assertEqual(json.loads(config_path.read_text(encoding='utf-8')), original)

    def test_only_activation_start_receives_expected_revision(self):
        config = {'dataHome': str(self.root / 'data'), 'language': 'en'}
        with patch.dict(lifecycle.os.environ, {'PROJECT_HUB_ACTIVATION_EXPECTED': 'inherited'}), \
             patch.object(lifecycle.subprocess, 'Popen') as spawn:
            lifecycle._start(config, self.root / 'app', 8769, self.root / 'control', expected='confirmed')
            self.assertEqual(spawn.call_args.kwargs['env']['PROJECT_HUB_ACTIVATION_EXPECTED'], 'confirmed')
            lifecycle._start(config, self.root / 'app', 8769, self.root / 'control')
            self.assertNotIn('PROJECT_HUB_ACTIVATION_EXPECTED', spawn.call_args.kwargs['env'])

    def test_restart_preserves_first_launch_endpoint_and_refuses_port_takeover(self):
        import hub_launcher
        config_path = self.root / 'installation.json'
        app = self.root / 'app'; app.mkdir()
        home = self.root / 'data'; home.mkdir()
        config = {'schemaVersion':1,'dataHome':str(home),'port':8769,'language':'en'}
        config_path.write_text(json.dumps(config),encoding='utf-8')
        process = Mock(); process.poll.return_value=0; process.returncode=0
        state = hub_launcher.state_path(config_path,app)
        with patch.object(lifecycle,'_start',return_value=process) as start, \
             patch.object(lifecycle,'_ready'), \
             patch('hub_launcher.available_port',return_value=17770) as available:
            self.assertEqual(lifecycle.supervise(config_path,application_home=app),0)
            available.assert_called_once_with(8769)
            self.assertEqual(start.call_args.args[2],17770)
        self.assertEqual(hub_launcher.remembered_port(state,home),17770)
        with patch.object(lifecycle,'_start',return_value=process) as start, \
             patch.object(lifecycle,'_ready'), \
             patch('hub_launcher.available_port',return_value=17770) as available:
            self.assertEqual(lifecycle.supervise(config_path,application_home=app),0)
            available.assert_called_once_with(17770)
            self.assertEqual(start.call_args.args[2],17770)
        previous = state.read_bytes()
        with patch.object(lifecycle,'_start') as start, \
             patch('hub_launcher.available_port',return_value=17771) as available:
            with self.assertRaisesRegex(lifecycle.LifecycleError,'saved Hub endpoint port 17770 is occupied'):
                lifecycle.supervise(config_path,application_home=app)
            available.assert_called_once_with(17770)
            start.assert_not_called()
        self.assertEqual(state.read_bytes(),previous)
        self.assertEqual(json.loads(config_path.read_text()),config)

    def test_metadata_read_failure_keeps_owned_runtime_alive_and_blocks_activation(self):
        config_path=self.root/'installation.json'
        app=self.root/'app';app.mkdir()
        home=self.root/'data';home.mkdir()
        config={'schemaVersion':1,'dataHome':str(home),'port':8769,'language':'en'}
        config_path.write_text(json.dumps(config),encoding='utf-8')
        jobs=self.root/'lifecycle/activation-jobs';jobs.mkdir(parents=True)
        broken=jobs/('c'*32+'.json');broken.write_text('{',encoding='utf-8')
        process=Mock();process.poll.return_value=None;process.returncode=0
        sleeps=[]
        def step(_):
            sleeps.append(1)
            if len(sleeps)==3:
                lifecycle.atomic_json(self.root/'lifecycle/shutdown.json',{})
        with patch.object(lifecycle,'_start',return_value=process),patch.object(lifecycle,'_ready'), \
             patch.object(lifecycle,'_stop') as stop,patch.object(lifecycle.time,'sleep',side_effect=step), \
             patch('storage_operations.Operations.catalog',side_effect=[PermissionError('busy receipt'),[]]), \
             patch('storage_application.complete_recovery',side_effect=[PermissionError('recovery receipt busy'),None]), \
             patch('hub_desktop.start_tray',side_effect=OSError('tray state busy')), \
             patch('hub_launcher.available_port',return_value=8769),patch('hub_launcher.remember'):
            self.assertEqual(lifecycle.supervise(config_path,application_home=app),0)
        self.assertEqual(len(sleeps),3)
        stop.assert_called_once()
        self.assertEqual(broken.read_text(encoding='utf-8'),'{')
        logs=''.join(p.read_text(encoding='utf-8') for p in (self.root/'diagnostics').glob('*.jsonl'))
        self.assertIn('supervisor.operation_catalog_failed',logs)
        self.assertIn('supervisor.activation_catalog_failed',logs)
        self.assertIn('supervisor.recovery_receipt_failed',logs)
        self.assertIn('supervisor.tray_start_failed',logs)

    def test_unhandled_supervisor_failure_is_durable(self):
        with patch.object(lifecycle,'_supervise',side_effect=RuntimeError('fixture crash')):
            with self.assertRaisesRegex(RuntimeError,'fixture crash'):
                lifecycle.supervise(self.root/'installation.json',application_home=self.root/'app')
        incident=json.loads((self.root/'diagnostics/last-incident.json').read_text(encoding='utf-8'))
        self.assertEqual(incident['event'],'supervisor.failed')
        self.assertIn('fixture crash',incident['traceback'])


if __name__ == '__main__':
    unittest.main()
