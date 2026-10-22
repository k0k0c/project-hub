"""Disposable native-host fixtures; these tests never connect to live Codex."""
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import codex_desktop_setup as setup


class DesktopBridgeTests(unittest.TestCase):
    def test_restricted_native_bridge_contracts(self):
        node = os.environ.get('CODEX_MCP_NODE_PATH') or shutil.which('node')
        self.assertTrue(node, 'Node.js is required for the Codex Desktop bridge contracts')
        environment = {key: value for key, value in os.environ.items()
                       if key not in ('CODEX_APP_TOOLS_PIPE_PATH', 'CODEX_THREAD_ID', 'PROJECT_HUB_CODEX_BRIDGE_KEY')}
        result = subprocess.run([node, '--test', str(Path(__file__).with_name('fixtures') / 'codex_desktop_bridge.test.mjs')],
                                cwd=ROOT, env=environment, text=True, encoding='utf-8',
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=35)
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_setup_rejects_nonlocal_and_credential_urls(self):
        spec = importlib.util.spec_from_file_location('bridge_setup', ROOT / 'scripts/codex_desktop_setup.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for value in ('https://example.test', 'http://127.0.0.1:80@remote.test',
                      'http://127.0.0.1:80?key=private', 'http://127.0.0.1:80/path'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                module.local_url(value)
        self.assertEqual(module.local_url('http://127.0.0.1:27706/'), 'http://127.0.0.1:27706')

    def test_stale_lock_recovery_retains_unknown_mutation_reservations(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'journal.json'
            state.write_text('{"operations":{"create:one":{"status":"dispatching"}}}')
            lock = Path(str(state) + '.lock')
            lock.write_text('{"pid":123}')
            with patch.object(setup, 'process_alive', return_value=True), self.assertRaises(ValueError):
                setup.reclaim_lock(state)
            self.assertTrue(lock.exists())
            with patch.object(setup, 'process_alive', return_value=False):
                setup.reclaim_lock(state)
            self.assertFalse(lock.exists())
            self.assertIn('dispatching', state.read_text())

    def test_process_owner_check_is_read_only_and_recognizes_own_process(self):
        self.assertTrue(setup.process_alive(os.getpid()))

    def test_profile_revalidation_preserves_user_claims_and_removes_only_generated_annotations(self):
        profile = {'schemaVersion': 1, 'capabilities': {}, 'persistentInstructions': {
            'scope': 'application', 'status': 'saved', 'consent': True, 'verification': 'client-reported'},
            'nativeChat': {'client': 'codex', 'nativeId': 'real-id', 'title': 'Current chat',
                           'provenance': 'client-reported', 'openingDocumented': True}}
        value = setup.input_profile(profile)
        self.assertEqual(value['nativeChat'], {'client': 'codex', 'nativeId': 'real-id', 'title': 'Current chat'})
        self.assertNotIn('verification', value['persistentInstructions'])
        self.assertEqual(profile['persistentInstructions']['verification'], 'client-reported')

    def test_setup_uses_live_hub_bindings_without_separate_workspace_arguments(self):
        caller = '11111111-1111-4111-8111-111111111111'
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / 'runtime'
            runtime.mkdir()
            bound = Path(directory) / 'plain-project'
            bound.mkdir()
            project_binding = dict(id='bound', project='plain', revision=1,
                                   status='active', scope=dict(root=str(bound)))
            catalog = dict(bindings=[dict(id='connection', client='codex',
                profileRevision='one', profile={'schemaVersion': 1}, projectBindings=[project_binding])])
            ready = dict(endpoint='http://127.0.0.1:1234', pid=123, instance='instance', callerNativeId=caller)
            process = Mock(stdout=io.StringIO(json.dumps(ready) + '\n'))
            def peer(base, route, body=None, key=None):
                if route == '/api/connections':
                    return catalog
                if route == '/v1/health':
                    return dict(status='ready', callerNativeId=caller,
                                projectRouting='hub-project-bindings', projectBindings=[project_binding])
                self.assertEqual(route, '/api/v1/connections')
                self.assertEqual(body['action'], 'configure-integration')
                return dict(saved=True)
            with patch.dict(os.environ, CODEX_APP_TOOLS_PIPE_PATH='inherited-test-pipe', CODEX_THREAD_ID=caller), \
                    patch.object(setup, 'request', side_effect=peer), \
                    patch.object(setup.subprocess, 'Popen', return_value=process) as launch:
                value = setup.connect('http://127.0.0.1:27706', 'connection', runtime, node='node-test')
            command = launch.call_args.args[0]
            self.assertNotIn('--root', command)
            self.assertNotIn(str(bound), command)
            self.assertIn('--hub-url', command)
            self.assertEqual(value['projectRouting'], 'hub-project-bindings')
            self.assertNotIn('allowedWorkspaces', value)


if __name__ == '__main__':
    unittest.main()
