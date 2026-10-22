"""Native user-config registration fixtures; never launch a real Codex host."""
from dataclasses import replace
import json
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import native_mcp_setup as setup
from native_onboarding import OnboardingError, build_plan
from agent_sdk import save_connection


class NativeMcpSetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='hub-mcp-registration-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.workspace = self.base / 'workspace'
        self.workspace.mkdir()
        self.connection = dict(baseUrl='http://127.0.0.1:8769', token='PrivateFixtureToken', project='example', binding='binding', workspace=str(self.workspace))
        self.private = self.base / 'private/connection.json'
        save_connection(self.private, self.connection)
        self.executable = self.base / 'codex-fixture.exe'
        self.executable.write_bytes(b'Never execute this fixture')

    def plan(self, host='cursor'):
        return build_plan(host, self.connection, '# Workflow\nRead hub_context.', connection_path=self.private)

    def registration(self, host='cursor', path=None):
        path = path or self.base / ('user/config.toml' if host == 'codex' else 'user/mcp.json')
        return setup.build_registration(self.plan(host), host_config=path, codex_executable=self.executable)

    def fake_codex(self, argv, **kwargs):
        self.assertEqual(argv[:3], [str(self.executable), 'mcp', 'add'])
        self.assertEqual(argv[4], '--url')
        self.assertEqual(argv[6], '--bearer-token-env-var')
        self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
        self.assertTrue(kwargs['capture_output'])
        self.assertEqual(kwargs['timeout'], 60)
        self.assertEqual(kwargs['creationflags'], getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
        self.assertNotIn(self.connection['token'], json.dumps(argv))
        self.assertNotIn(self.connection['token'], json.dumps(kwargs['env']))
        path = Path(kwargs['env']['CODEX_HOME']) / 'config.toml'
        path.parent.mkdir(parents=True, exist_ok=True)
        prefix = path.read_bytes() if path.exists() else b''
        section = '\n[mcp_servers.' + argv[3] + ']\nurl = ' + json.dumps(argv[5]) + '\nbearer_token_env_var = ' + json.dumps(argv[7]) + '\n'
        path.write_bytes(prefix + section.encode())
        return SimpleNamespace(returncode=0, stdout=b'', stderr=b'')

    def test_codex_native_command_preserves_foreign_config_and_is_idempotent(self):
        path = self.base / 'codex-user/config.toml'
        path.parent.mkdir()
        original = b'# Preserve user comment\nmodel = "fixture-model"\n[mcp_servers.foreign]\ncommand = "foreign-command"\nargs = ["--foreign"]\n'
        path.write_bytes(original)
        registration = self.registration('codex', path)
        with patch.dict(os.environ, {'CODEX_HOME': 'unrelated-parent-home'}), patch.object(setup.subprocess, 'run', side_effect=self.fake_codex) as launch:
            result = setup.apply_registration(registration)
            self.assertEqual(os.environ['CODEX_HOME'], 'unrelated-parent-home')
        self.assertTrue(result['registered'])
        self.assertTrue(path.read_bytes().startswith(original))
        self.assertEqual(launch.call_args.kwargs['env']['CODEX_HOME'], str(path.parent))
        before = path.read_bytes()
        with patch.object(setup.subprocess, 'run') as launch:
            self.assertFalse(setup.apply_registration(self.registration('codex', path))['changed'])
            launch.assert_not_called()
        self.assertEqual(path.read_bytes(), before)
        self.assertNotIn(self.connection['token'].encode(), before)

    def test_cursor_json_preserves_foreign_fields_and_idempotence(self):
        path = self.base / 'cursor-user/mcp.json'
        path.parent.mkdir()
        foreign = dict(mcpServers={'foreign': {'url': 'https://example.invalid/mcp'}}, userSetting={'keep': [1, True, 'yes']})
        path.write_text(json.dumps(foreign))
        registration = self.registration(path=path)
        self.assertTrue(setup.apply_registration(registration)['changed'])
        actual = json.loads(path.read_bytes())
        self.assertEqual(actual['userSetting'], foreign['userSetting'])
        self.assertEqual(actual['mcpServers']['foreign'], foreign['mcpServers']['foreign'])
        self.assertEqual(actual['mcpServers'][registration.server], registration.entry)
        before = path.read_bytes()
        self.assertFalse(setup.apply_registration(self.registration(path=path))['changed'])
        self.assertEqual(path.read_bytes(), before)
        self.assertNotIn(self.connection['token'].encode(), before)

    def test_conflicting_generated_name_is_preserved(self):
        for host in ('codex', 'cursor'):
            registration = self.registration(host)
            path = registration.path
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = ('[mcp_servers.' + registration.server + ']\ncommand="unrelated"\nargs=[]\n').encode() if host == 'codex' else json.dumps({'mcpServers': {registration.server: {'command': 'unrelated', 'args': []}}}).encode()
            path.write_bytes(raw)
            with self.subTest(host=host), self.assertRaisesRegex(OnboardingError, 'different configuration'):
                self.registration(host, path)
            self.assertEqual(path.read_bytes(), raw)

    def test_loopback_endpoint_repair_preserves_options_comments_and_foreign_servers(self):
        registration = self.registration('codex')
        path = registration.path
        path.parent.mkdir(parents=True)
        raw = ('# Keep all other settings\nmodel="fixture"\n[mcp_servers.'+registration.server+']\n'
            'url = "http://127.0.0.1:8769/mcp" # Keep comment\n'
            'bearer_token_env_var = '+json.dumps(registration.entry['bearer_token_env_var'])+'\n'
            'enabled = true\ntool_timeout_sec = 42\n[mcp_servers.foreign]\ncommand="foreign"\n').encode()
        path.write_bytes(raw)
        with patch.object(setup.subprocess,'run',side_effect=AssertionError('No host launch for endpoint repair')):
            result = setup.apply_registration(self.registration('codex',path))
        self.assertTrue(result['endpointRepaired'])
        self.assertEqual(path.read_bytes(),raw.replace(b'http://127.0.0.1:8769/mcp',b'http://localhost:8769/mcp'))
        self.assertFalse(setup.apply_registration(self.registration('codex',path))['changed'])

    def test_endpoint_repair_never_changes_origin_port_credentials_or_transport(self):
        self.assertTrue(setup.same_local_endpoint('http://127.0.0.1:8769/mcp','http://localhost:8769/mcp'))
        for value in ('http://localhost:8768/mcp','http://other.invalid:8769/mcp',
                      'http://user@localhost:8769/mcp','http://localhost:8769/mcp?key=x',None):
            self.assertFalse(setup.same_local_endpoint(value,'http://localhost:8769/mcp'))

    def test_native_discovery_requires_complete_catalog_without_running_a_chat(self):
        registration=self.registration('codex')
        with patch.object(setup.subprocess,'run',side_effect=self.fake_codex):
            setup.apply_registration(registration)
        def process(catalog):
            message=dict(id=1,result=dict(data=[dict(name=registration.server,tools={name:dict(name=name) for name in catalog})]))
            return SimpleNamespace(stdin=io.BytesIO(),stdout=io.BytesIO((json.dumps(message)+'\n').encode()),
                stderr=io.BytesIO(b'Private native log must not be published'),poll=lambda:0)
        for catalog,verified in [(['hub_context','hub_instructions'],True),(['hub_context'],False)]:
            with self.subTest(catalog=catalog),patch.dict(os.environ,{registration.entry['bearer_token_env_var']:'FixtureCredential'}), \
                 patch('agent_runtime.tools',return_value=[dict(name=name) for name in ('hub_context','hub_instructions')]), \
                 patch.object(setup.subprocess,'Popen',return_value=process(catalog)) as launch:
                result=setup.verify_registration(registration,timeout=1)
            self.assertEqual(result['nativeDiscoveryVerified'],verified)
            self.assertFalse(result['conversationLoadVerified'])
            self.assertNotIn('Private',json.dumps(result))
            self.assertNotIn('thread/start',json.dumps(launch.call_args.args))

    def test_native_discovery_uses_bare_app_server_without_per_server_overrides(self):
        registration=self.registration('codex')
        with patch.object(setup.subprocess, 'run', side_effect=self.fake_codex):
            setup.apply_registration(registration)
        message=dict(id=1,result=dict(data=[dict(name=registration.server,
            tools={'hub_context':dict(name='hub_context')})]))
        process=SimpleNamespace(stdin=io.BytesIO(),stdout=io.BytesIO((json.dumps(message)+'\n').encode()),
            stderr=io.BytesIO(),poll=lambda:0)
        with patch.dict(os.environ,{registration.entry['bearer_token_env_var']:'FixtureCredential'}), \
             patch('agent_runtime.tools',return_value=[dict(name='hub_context')]), \
             patch.object(setup.subprocess,'Popen',return_value=process) as launch:
            setup.verify_registration(registration,timeout=1)
        self.assertEqual(launch.call_args.args[0], [str(self.executable),'app-server','--stdio'])

    def test_native_discovery_distinguishes_exit_timeout_missing_target_and_protocol_error(self):
        registration=self.registration('codex')
        with patch.object(setup.subprocess, 'run', side_effect=self.fake_codex):
            setup.apply_registration(registration)
        env=patch.dict(os.environ,{registration.entry['bearer_token_env_var']:'FixtureCredential'})
        tools_patch=patch('agent_runtime.tools',return_value=[dict(name='hub_context')])
        def process(payload, code=0):
            return SimpleNamespace(stdin=io.BytesIO(),stdout=io.BytesIO(payload),stderr=io.BytesIO(),poll=lambda:code,
                terminate=lambda:None,wait=lambda timeout=None:None,kill=lambda:None)
        with env,tools_patch,patch.object(setup.subprocess,'Popen',return_value=process(b'' ,17)):
            result=setup.verify_registration(registration,timeout=1)
        self.assertEqual((result['reason'],result['exitCode']),('native_process_exit',17))
        with patch.dict(os.environ,{registration.entry['bearer_token_env_var']:'FixtureCredential'}), \
             patch('agent_runtime.tools',return_value=[dict(name='hub_context')]), \
             patch.object(setup.subprocess,'Popen',return_value=process(b'',None)), \
             patch.object(setup.queue.Queue,'get',side_effect=setup.queue.Empty):
            result=setup.verify_registration(registration,timeout=0.01)
        self.assertEqual(result['reason'],'native_timeout')
        missing=json.dumps(dict(id=1,result=dict(data=[]))).encode()+b'\n'
        with patch.dict(os.environ,{registration.entry['bearer_token_env_var']:'FixtureCredential'}),patch('agent_runtime.tools',return_value=[dict(name='hub_context')]),patch.object(setup.subprocess,'Popen',return_value=process(missing)):
            self.assertEqual(setup.verify_registration(registration,timeout=1)['reason'],'target_server_missing')
        protocol=json.dumps(dict(id=1,error={'message':'private detail'})).encode()+b'\n'
        with patch.dict(os.environ,{registration.entry['bearer_token_env_var']:'FixtureCredential'}),patch('agent_runtime.tools',return_value=[dict(name='hub_context')]),patch.object(setup.subprocess,'Popen',return_value=process(protocol)):
            result=setup.verify_registration(registration,timeout=1)
        self.assertEqual(result['reason'],'native_protocol_error')
        self.assertNotIn('private detail',json.dumps(result))

    def test_native_discovery_does_not_claim_readiness_without_credentials(self):
        registration=self.registration('codex')
        with patch.object(setup.subprocess,'run',side_effect=self.fake_codex):
            setup.apply_registration(registration)
        with patch.dict(os.environ,{},clear=True),patch.object(setup.subprocess,'Popen') as launch:
            result=setup.verify_registration(registration)
        self.assertEqual(result['state'],'pending')
        self.assertFalse(result['nativeDiscoveryVerified'])
        launch.assert_not_called()

    def test_stale_config_rejected_before_any_registration(self):
        for host in ('codex', 'cursor'):
            registration = self.registration(host)
            registration.path.parent.mkdir(parents=True, exist_ok=True)
            updated = b'model="new-user-model"\n' if host == 'codex' else b'{"newUserField":true}'
            registration.path.write_bytes(updated)
            with self.subTest(host=host), patch.object(setup.subprocess, 'run') as launch, self.assertRaisesRegex(OnboardingError, 'changed after preview'):
                setup.apply_registration(registration)
            launch.assert_not_called()
            self.assertEqual(registration.path.read_bytes(), updated)

    def test_malformed_config_and_registry_preserved(self):
        for host, cases in [('codex', [b'[broken', b'mcp_servers="wrong"']), ('cursor', [b'{broken', b'[]', b'{"mcpServers":[]}'])]:
            path = self.registration(host).path
            path.parent.mkdir(parents=True, exist_ok=True)
            for raw in cases:
                path.write_bytes(raw)
                with self.subTest(host=host, raw=raw), self.assertRaises(OnboardingError):
                    self.registration(host, path)
                self.assertEqual(path.read_bytes(), raw)

    def test_non_object_existing_server_is_a_bounded_config_error(self):
        for host in ('codex', 'cursor'):
            registration = self.registration(host)
            path = registration.path
            path.parent.mkdir(parents=True, exist_ok=True)
            raw = ('[mcp_servers]\n' + registration.server + '="wrong"\n').encode() if host == 'codex' else json.dumps({'mcpServers': {registration.server: 'wrong'}}).encode()
            path.write_bytes(raw)
            with self.subTest(host=host), self.assertRaises(OnboardingError):
                self.registration(host, path)
            self.assertEqual(path.read_bytes(), raw)

    def test_codex_failure_output_is_redacted_and_config_not_claimed_registered(self):
        registration = self.registration('codex')
        failure = SimpleNamespace(returncode=1, stdout=self.connection['token'].encode(), stderr=self.connection['token'].encode())
        with patch.object(setup.subprocess, 'run', return_value=failure), self.assertRaises(OnboardingError) as caught:
            setup.apply_registration(registration)
        self.assertNotIn(self.connection['token'], str(caught.exception))
        self.assertFalse(registration.path.exists())

    def test_codex_timeout_is_bounded_redacted_and_never_retried(self):
        registration = self.registration('codex')
        timeout = subprocess.TimeoutExpired('fixture', 60, output=self.connection['token'].encode(), stderr=self.connection['token'].encode())
        with patch.object(setup.subprocess, 'run', side_effect=timeout) as launch, self.assertRaises(OnboardingError) as caught:
            setup.apply_registration(registration)
        self.assertEqual(launch.call_count, 1)
        self.assertNotIn(self.connection['token'], str(caught.exception))
        self.assertFalse(registration.path.exists())

    def test_codex_verification_detects_missing_entry_and_foreign_changes(self):
        registration = self.registration('codex')
        with patch.object(setup.subprocess, 'run', return_value=SimpleNamespace(returncode=0)), self.assertRaisesRegex(OnboardingError, 'could not be verified'):
            setup.apply_registration(registration)
        def changed(argv, **kwargs):
            result = self.fake_codex(argv, **kwargs)
            with registration.path.open('a', encoding='utf-8') as stream:
                stream.write('\n[foreign-added]\nchanged=true\n')
            return result
        with patch.object(setup.subprocess, 'run', side_effect=changed), self.assertRaisesRegex(OnboardingError, 'Unrelated'):
            setup.apply_registration(registration)
        self.assertTrue(tomllib.loads(registration.path.read_text())['foreign-added']['changed'])

    def test_native_config_must_be_outside_workspace_and_enter_fingerprint(self):
        with self.assertRaisesRegex(OnboardingError, 'outside'):
            self.registration(path=self.workspace / 'mcp.json')
        plan = self.plan()
        registration = self.registration()
        combined = replace(plan, registration=registration)
        self.assertNotEqual(plan.fingerprint, combined.fingerprint)
        self.assertNotIn(self.connection['token'], json.dumps(combined.preview()))
        self.assertFalse(registration.path.exists())


if __name__ == '__main__':
    unittest.main()
