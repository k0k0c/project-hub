import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SDK_HOME = HERE.parent
sys.path.insert(0, str(SDK_HOME))
SPEC = importlib.util.spec_from_file_location('native_onboarding', SDK_HOME / 'native_onboarding.py')
native = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = native
SPEC.loader.exec_module(native)


class NativeOnboardingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='hub-native-rule-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.workspace = self.base / 'project'
        self.workspace.mkdir()
        self.connection = dict(baseUrl='http://127.0.0.1:8769', token='PrivateEnrollmentTokenDoNotPublish',
                               project='example-project', workspace=str(self.workspace), binding='binding-1')
        self.workflow = '# Workflow\n\nUse hub_context before work.\nGive every conversation its own session.\n'

    def plan(self, host='codex', **kwargs):
        return native.build_plan(host, self.connection, self.workflow, **kwargs)

    def apply(self, plan):
        return native.apply_plan(plan, expected_preview=plan.fingerprint)

    def test_preview_is_secret_free_and_does_not_write(self):
        plan = self.plan()
        preview = plan.preview()
        self.assertFalse(plan.path.exists())
        text = json.dumps(preview)
        self.assertNotIn(self.connection['token'], text)
        self.assertFalse(preview['setupVerified'])
        self.assertIn('bearer_token_env_var', preview['mcp']['fragment'])
        self.assertIn(preview['mcp']['credentialEnvironment'], preview['ruleDiff'])
        self.assertIn('--bearer-token-env-var', preview['steps'][1]['argv'])

    def test_codex_merge_preserves_unrelated_bytes_and_is_idempotent(self):
        path = self.workspace / 'AGENTS.md'
        original = b'\xef\xbb\xbf# Existing instructions\r\n\r\nKeep unrelated trailing spaces.  \r\n'
        path.write_bytes(original)
        plan = self.plan()
        self.assertTrue(plan.after.startswith(original))
        self.assertIn(b'\r\n', plan.after)
        self.apply(plan)
        first = path.read_bytes()
        repeated = self.plan()
        self.assertEqual(repeated.after, first)
        self.assertFalse(self.apply(repeated)['changed'])
        self.assertEqual(path.read_bytes(), first)

    def test_owned_block_update_preserves_prefix_and_suffix_exactly(self):
        prefix = b'User prefix\r\n\r\n'
        suffix = b'\r\n\r\nUser suffix  \r\n'
        path = self.workspace / 'AGENTS.md'
        path.write_bytes(prefix + native.BEGIN + b'\r\nold owned text\r\n' + native.END + suffix)
        plan = self.plan()
        self.assertTrue(plan.after.startswith(prefix))
        self.assertTrue(plan.after.endswith(suffix))
        self.assertNotIn(b'old owned text', plan.after)
        self.assertEqual(plan.after.count(native.BEGIN), 1)

    def test_apply_requires_the_exact_preview_and_rejects_stale_file(self):
        plan = self.plan()
        with self.assertRaisesRegex(native.OnboardingError, 'Preview'):
            native.apply_plan(plan, expected_preview=None)
        with self.assertRaises(native.OnboardingError):
            native.apply_plan(plan, expected_preview='0' * 64)
        plan.path.write_bytes(b'Added after preview\n')
        with self.assertRaisesRegex(native.OnboardingError, 'changed after preview'):
            self.apply(plan)
        self.assertEqual(plan.path.read_bytes(), b'Added after preview\n')

    def test_cursor_has_always_apply_rule_and_env_only_mcp_fragment(self):
        plan = self.plan('cursor')
        self.assertEqual(plan.path, self.workspace / '.cursor/rules/project-hub.mdc')
        self.assertTrue(plan.after.startswith(b'---\n'))
        self.assertIn(b'alwaysApply: true\n', plan.after)
        config = plan.preview()['mcp']['fragment']
        entry = next(iter(config['mcpServers'].values()))
        self.assertEqual(entry['url'], 'http://localhost:8769/mcp')
        self.assertTrue(entry['headers']['Authorization'].startswith('Bearer ${env:'))
        self.apply(plan)
        before = plan.path.read_bytes()
        self.assertEqual(self.plan('cursor').after, before)
        self.assertFalse((self.workspace / '.cursor/mcp.json').exists(), 'native MCP configuration was changed')

    def test_cursor_preserves_existing_activation_settings_and_metadata(self):
        path = self.workspace / '.cursor/rules/project-hub.mdc'
        path.parent.mkdir(parents=True)
        original = b'---\r\ndescription: User description\r\nalwaysApply: true\r\n---\r\n\r\nUser rule.  \r\n'
        path.write_bytes(original)
        self.assertTrue(self.plan('cursor').after.startswith(original))
        for value in [b'---\nalwaysApply: false\n---\nMy rule\n', b'User rule without metadata\n']:
            path.write_bytes(value)
            with self.assertRaises(native.OnboardingError):
                self.plan('cursor')
            self.assertEqual(path.read_bytes(), value)

    def test_duplicate_incomplete_or_embedded_ownership_markers_rejected(self):
        path = self.workspace / 'AGENTS.md'
        cases = [native.BEGIN, native.END, native.BEGIN + b'\ntext\n' + native.END + native.END,
                 b'inline ' + native.BEGIN + b'\ntext\n' + native.END]
        for raw in cases:
            with self.subTest(raw=raw):
                path.write_bytes(raw)
                with self.assertRaises(native.OnboardingError):
                    self.plan()
                self.assertEqual(path.read_bytes(), raw)

    def test_bound_workspace_and_override_are_checked(self):
        other = self.base / 'other'
        other.mkdir()
        with self.assertRaisesRegex(native.OnboardingError, 'differs'):
            self.plan(workspace=other)
        override = self.workspace / 'AGENTS.override.md'
        override.write_text('User override\n', encoding='utf-8')
        with self.assertRaisesRegex(native.OnboardingError, 'overrides'):
            self.plan()
        self.assertFalse((self.workspace / 'AGENTS.md').exists())
        override.write_bytes(b'')
        self.assertIsNotNone(self.plan().after)

    def test_links_reparse_and_hub_source_tree_are_rejected(self):
        path = self.workspace / 'AGENTS.md'
        original = Path.lstat
        for target, mode, attrs in [(path, stat.S_IFLNK, 0), (path.parent, stat.S_IFDIR, 0x400)]:
            def lstat(candidate, *args, **kwargs):
                if candidate == target:
                    return SimpleNamespace(st_mode=mode, st_file_attributes=attrs)
                return original(candidate, *args, **kwargs)
            with patch.object(Path, 'lstat', lstat), self.assertRaises(native.OnboardingError):
                self.plan()
        with self.assertRaises(native.OnboardingError):
            native.safe_path(Path(native.agent_sdk.__file__).resolve().parents[1] / 'AGENTS.md')
        with self.assertRaises(native.OnboardingError):
            self.plan(forbidden_roots=[self.workspace])
        with self.assertRaises(native.OnboardingError):
            native.safe_path(self.base / '.codex/config.toml')

    def test_generic_is_a_manual_capability_plan_without_native_write(self):
        plan = self.plan('generic')
        self.assertIsNone(plan.path)
        self.assertEqual(plan.mcp['format'], 'host-specific-plan')
        self.assertNotIn('${env:', json.dumps(plan.preview()))
        self.assertTrue(any('cannot discover or modify arbitrary applications' in value for value in plan.limitations))
        with self.assertRaises(native.OnboardingError):
            self.apply(plan)

    def test_installed_application_root_and_runtime_cannot_hold_rules_or_credentials(self):
        installed = self.base / 'installed'
        app = installed / 'app'
        sdk = app / 'scripts' / 'agent_sdk.py'
        sdk.parent.mkdir(parents=True)
        sdk.write_text('# installed SDK fixture', encoding='utf-8')
        runtime = installed / 'runtime'
        runtime.mkdir()
        (runtime / 'python.exe').write_bytes(b'fixture')
        rootless = {k:v for k,v in self.connection.items() if k != 'workspace'}
        with patch.object(native.agent_sdk, '__file__', str(sdk)):
            for folder in (installed, app, runtime):
                with self.subTest(folder=folder):
                    for host in ('codex','cursor'):
                        with self.assertRaisesRegex(native.OnboardingError, 'outside the Hub application'):
                            native.build_plan(host, rootless, self.workflow, workspace=folder)
                    with self.assertRaisesRegex(native.OnboardingError, 'outside the Hub application'):
                        native.safe_path(folder / 'private-connection.json')
            self.assertEqual(native.safe_path(self.workspace), self.workspace)
        self.assertFalse((installed / 'AGENTS.md').exists())
        self.assertFalse((runtime / '.cursor').exists())

    def test_credentials_and_markers_cannot_enter_persistent_workflow(self):
        for text in [self.connection['token'], native.BEGIN.decode(), native.END.decode()]:
            with self.subTest(text=text), self.assertRaises(native.OnboardingError):
                native.build_plan('codex', self.connection, self.workflow + text)
        for patch_value in [dict(token=None), dict(baseUrl='https://public.example'), dict(project='')]:
            with self.subTest(patch_value=patch_value), self.assertRaises(native.OnboardingError):
                native.build_plan('codex', {**self.connection, **patch_value}, self.workflow)

    def test_existing_secret_is_not_exposed_by_a_preview_diff(self):
        path = self.workspace / 'AGENTS.md'
        original = ('User instructions\n' + self.connection['token'] + '\n').encode()
        path.write_bytes(original)
        with self.assertRaisesRegex(native.OnboardingError, 'redact it separately'):
            self.plan()
        self.assertEqual(path.read_bytes(), original)

    def test_distinct_enrollment_bindings_do_not_share_global_credential_reference(self):
        first = self.plan()
        second = native.build_plan('codex', {**self.connection, 'binding':'binding-2'}, self.workflow)
        self.assertNotEqual(first.mcp['server'], second.mcp['server'])
        self.assertNotEqual(first.mcp['credentialEnvironment'], second.mcp['credentialEnvironment'])

    def test_cli_consumes_sdk_connection_and_preview_fingerprint(self):
        private = self.base / 'private/connection.json'
        native.agent_sdk.save_connection(private, self.connection)
        workflow = self.base / 'workflow.md'
        workflow.write_text(self.workflow, encoding='utf-8')
        args = ['--host', 'codex', '--connection', str(private), '--workflow', str(workflow)]
        with patch('sys.stdout', io.StringIO()) as stream:
            self.assertEqual(native.main(args), 0)
            preview = json.loads(stream.getvalue())
        self.assertNotIn(self.connection['token'], json.dumps(preview))
        with patch('sys.stdout', io.StringIO()) as stream:
            self.assertEqual(native.main(args + ['--apply', '--expected-preview', preview['previewSha256']]), 0)
            result = json.loads(stream.getvalue())
        self.assertTrue(result['changed'])
        self.assertFalse(result['setupVerified'])

    def test_private_connection_generates_only_secret_free_http_mcp(self):
        private = self.base / 'private/connection.json'
        native.agent_sdk.save_connection(private, self.connection)
        for host in ('codex', 'cursor'):
            with self.subTest(host=host):
                plan = self.plan(host, connection_path=private)
                self.assertEqual(plan.mcp['format'], 'streamable-http')
                entry = plan.mcp['entry']
                self.assertEqual(entry['url'],'http://localhost:8769/mcp')
                self.assertNotIn('command',entry)
                self.assertNotIn('args',entry)
                self.assertNotIn(self.connection['token'], json.dumps(plan.preview()))
                self.assertNotIn(self.connection['token'].encode(), plan.after)
                self.assertIn('PROJECT_HUB_TOKEN_', plan.after.decode())
                self.assertNotIn('mcp_stdio_client',json.dumps(plan.preview()))

    def test_private_connection_rejects_workspace_secret_or_mismatched_enrollment(self):
        private = self.workspace / 'connection.json'
        # This is deliberately a fixture for validating rejection, never native setup.
        private.write_text(json.dumps(self.connection), encoding='utf-8')
        with self.assertRaisesRegex(native.OnboardingError, 'outside'):
            self.plan(connection_path=private)
        outside = self.base / 'other-connection.json'
        outside.write_text(json.dumps({**self.connection, 'binding': 'different'}), encoding='utf-8')
        with self.assertRaisesRegex(native.OnboardingError, 'differs'):
            self.plan(connection_path=outside)

    def test_cli_registers_cursor_http_using_exact_combined_preview(self):
        private = self.base / 'private/connection.json'
        native.agent_sdk.save_connection(private, {**self.connection, 'workflow': self.workflow})
        config = self.base / 'native-user/mcp.json'
        config.parent.mkdir()
        config.write_text('{"foreignSetting":true,"mcpServers":{"foreign":{"command":"keep"}}}')
        args = ['--host', 'cursor', '--connection', str(private), '--register-mcp', '--host-config', str(config)]
        with patch('sys.stdout', io.StringIO()) as stream:
            self.assertEqual(native.main(args), 0)
            preview = json.loads(stream.getvalue())
        self.assertEqual(preview['mcp']['format'], 'streamable-http')
        self.assertIsNotNone(preview['registration'])
        self.assertNotIn(self.connection['token'], json.dumps(preview))
        with patch('sys.stdout', io.StringIO()) as stream:
            self.assertEqual(native.main(args + ['--apply', '--expected-preview', preview['previewSha256']]), 0)
            result = json.loads(stream.getvalue())
        self.assertTrue(result['mcpRegistration']['registered'])
        self.assertFalse(result['setupVerified'], 'Native registration does not prove a new conversation read its rule')
        actual = json.loads(config.read_bytes())
        self.assertTrue(actual['foreignSetting'])
        self.assertEqual(actual['mcpServers']['foreign']['command'], 'keep')
        self.assertNotIn(self.connection['token'].encode(), config.read_bytes())
        self.assertNotIn(self.connection['token'].encode(), (self.workspace / '.cursor/rules/project-hub.mdc').read_bytes())

    def test_global_connection_needs_no_workspace_and_previews_native_global_rule(self):
        connection = dict(baseUrl=self.connection['baseUrl'],token=self.connection['token'],
                          binding='global-binding',scope='global',project=None)
        for host in ('codex','cursor','generic'):
            plan = native.build_plan(host,connection,self.workflow)
            self.assertIsNone(plan.path)
            self.assertIsNone(plan.workspace)
            self.assertIn('hub_projects',plan.preview()['persistentRule'])
            self.assertIn('every project tool request',plan.preview()['persistentRule'])
            self.assertNotIn('Legacy bound project',plan.preview()['persistentRule'])
            self.assertNotIn(connection['token'],json.dumps(plan.preview()))
            self.assertNotIn('stdio',json.dumps(plan.preview()).lower())
        self.assertFalse((self.workspace/'AGENTS.md').exists())

    def test_global_http_registration_does_not_claim_global_instructions_persisted(self):
        connection = dict(baseUrl=self.connection['baseUrl'],token=self.connection['token'],
                          binding='global-binding',scope='global',project=None,workflow=self.workflow)
        private = self.base/'private/global.json'
        native.agent_sdk.save_connection(private,connection)
        config = self.base/'native-user/mcp.json'
        args = ['--host','cursor','--connection',str(private),'--register-mcp','--host-config',str(config)]
        with patch('sys.stdout',io.StringIO()) as stream:
            self.assertEqual(native.main(args),0)
            preview=json.loads(stream.getvalue())
        with patch('sys.stdout',io.StringIO()) as stream:
            self.assertEqual(native.main(args+['--apply','--expected-preview',preview['previewSha256']]),0)
            result=json.loads(stream.getvalue())
        self.assertTrue(result['mcpRegistration']['registered'])
        self.assertFalse(result['instructionsPersisted'])
        self.assertFalse(result['setupVerified'])
        self.assertEqual(next(iter(json.loads(config.read_text())['mcpServers'].values()))['url'],'http://localhost:8769/mcp')


if __name__ == '__main__':
    unittest.main()
