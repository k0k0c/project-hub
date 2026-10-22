"""Exercise the prepared package as a separate process against disposable servers."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_project_hub_plugin import prepare
from install_project_hub_plugin import check_installed
import install_project_hub_plugin as installer
import test_project_hub_plugin_api as api_fixture


def hook_argv(handler):
    if os.name == 'nt':
        shell = shutil.which('pwsh') or shutil.which('powershell')
        if not shell:
            raise RuntimeError('PowerShell required to verify Windows hooks')
        return [shell, '-NoProfile', '-NonInteractive', '-Command', handler['commandWindows']]
    return ['/bin/sh', '-c', handler['command']]


class InstallerUpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.home = self.base / 'user'
        self.data_home = self.base / 'hub data'
        self.target = self.home / 'plugins/project-hub'
        self.manifest = self.target / '.codex-plugin/plugin.json'
        self.manifest.parent.mkdir(parents=True)
        self.manifest.write_text(json.dumps({'name': 'project-hub', 'version': '0.2.0+codex.20260929222425'}))
        (self.target / 'old-marker').write_text('backup evidence')
        self.marketplace = self.home / '.agents/plugins/marketplace.json'
        self.marketplace.parent.mkdir(parents=True)
        self.entries = {'name': 'personal', 'plugins': [
            {'name': 'project-hub', 'source': {'source': 'local', 'path': './plugins/project-hub'}}]}
        self.write_marketplace(self.entries)

    def tearDown(self):
        self.tmp.cleanup()

    def write_marketplace(self, entries):
        self.marketplace.write_text(json.dumps(entries), encoding='utf-8')

    def run_install(self, snapshots=None, health=None, health_raw=None):
        health_response = Mock()
        health_response.__enter__ = Mock(return_value=health_response)
        health_response.__exit__ = Mock(return_value=False)
        health = health if health is not None else dict(service='project-hub', multiProject=True,
                                                      dataHome=str(self.data_home.resolve()))
        health_response.read.return_value = health_raw if health_raw is not None else json.dumps(health).encode('utf-8')
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = b'{"schemaVersion":1,"projects":[]}'
        client = Mock()
        client.opener.open.side_effect = [health_response, response]
        self.last_client = client
        self.last_health_response = health_response
        snapshots = snapshots or [{'installed': []}, {'installed': []}]
        with patch.object(installer.Path, 'home', return_value=self.home), \
                patch.object(installer, 'ROOT', self.base / 'repo'), \
                patch('hub_http.Client', return_value=client), \
                patch.object(installer.subprocess, 'check_output', side_effect=[json.dumps(s) for s in snapshots]) as inspect, \
                patch.object(installer.subprocess, 'run') as command:
            self.last_inspect = inspect
            self.last_command = command
            result = installer.install('http://127.0.0.1:1')
        return result, inspect, command

    def test_existing_update_without_creator_preserves_marketplace_and_backup(self):
        original = self.marketplace.read_bytes()
        result, inspect, command = self.run_install()
        self.assertEqual(self.marketplace.read_bytes(), original)
        backup = Path(result['backup']) / 'project-hub'
        self.assertEqual((backup / 'old-marker').read_text(), 'backup evidence')
        self.assertEqual(json.loads((backup / '.codex-plugin/plugin.json').read_text())['version'],
                         '0.2.0+codex.20260929222425')
        version = json.loads(self.manifest.read_text())['version']
        self.assertRegex(version, r'^0\.2\.0\+codex\.\d{14}$')
        self.assertNotEqual(version, '0.2.0+codex.20260929222425')
        self.assertEqual(json.loads((self.target / 'connection.json').read_text())['url'], 'http://127.0.0.1:1')
        connection = json.loads((self.target / 'connection.json').read_text())
        companion = self.home / '.agents/skills/project-hub-user'
        self.assertEqual(connection['userSkillRoot'], str(companion.resolve()))
        self.assertEqual(connection['instructionsDataHome'], str(self.data_home.resolve()))
        self.assertTrue((companion / 'SKILL.md').is_file())
        self.assertTrue((companion / '.project-hub-owned.json').is_file())
        self.assertIn(str(companion / 'SKILL.md'), (self.target / 'skills/project-hub/SKILL.md').read_text())
        self.assertEqual([call.args[0].full_url for call in self.last_client.opener.open.call_args_list],
                         ['http://127.0.0.1:1/api/v1/health', 'http://127.0.0.1:1/api/v1/projects'])
        self.last_health_response.read.assert_called_once_with(16001)
        mcp = json.loads((self.target / '.mcp.json').read_text())['mcpServers']['project_hub']
        self.assertIn(str(self.target), mcp['args'][0])
        self.assertEqual(inspect.call_count, 2)
        for call in inspect.call_args_list:
            self.assertEqual(call.args[0], ['codex', 'plugin', 'list', '--json'])
        command.assert_called_once_with(['codex', 'plugin', 'add', 'project-hub@personal', '--json'], check=True, timeout=60)

    def test_reinstall_preserves_owned_user_body_and_history(self):
        self.run_install()
        from hub_instructions import Instructions
        instructions = Instructions(self.data_home)
        current = instructions.read()
        instructions.update(current['revision'], patch={'userInstructions': '# Personal preferences\nKeep my instructions.\n'})
        skill = self.home / '.agents/skills/project-hub-user/SKILL.md'
        before = skill.read_bytes()
        history = (self.data_home / 'instructions/history.json').read_bytes()
        self.run_install()
        self.assertEqual(skill.read_bytes(), before)
        self.assertEqual((self.data_home / 'instructions/history.json').read_bytes(), history)

    def test_existing_configured_location_is_retained_without_adopting_standard_foreign_skill(self):
        from hub_instructions import Instructions
        alternate = self.base / 'custom/.agents/skills/project-hub-user'
        instructions = Instructions(self.data_home)
        instructions.initialize(alternate, package_root=self.target)
        skill = alternate / 'SKILL.md'
        before = skill.read_bytes()
        foreign = self.home / '.agents/skills/project-hub-user'
        foreign.mkdir(parents=True)
        (foreign / 'SKILL.md').write_text('Foreign instructions', encoding='utf-8')
        self.run_install()
        self.assertEqual(skill.read_bytes(), before)
        self.assertEqual((foreign / 'SKILL.md').read_text(), 'Foreign instructions')
        self.assertFalse((foreign / '.project-hub-owned.json').exists())
        connection = json.loads((self.target / 'connection.json').read_text())
        self.assertEqual(connection['userSkillRoot'], str(alternate.resolve()))

    def test_foreign_companion_directory_fails_before_plugin_copy(self):
        foreign = self.home / '.agents/skills/project-hub-user'
        foreign.mkdir(parents=True)
        (foreign / 'SKILL.md').write_text('Do not adopt', encoding='utf-8')
        before = self.manifest.read_bytes()
        with self.assertRaisesRegex(ValueError, 'unowned skill directory'):
            self.run_install()
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertEqual((foreign / 'SKILL.md').read_text(), 'Do not adopt')
        self.assertFalse((foreign / '.project-hub-owned.json').exists())
        self.assertFalse((self.base / 'project-hub-backups').exists())

    def test_health_requires_identity_multi_project_and_absolute_data_home_before_cli(self):
        valid = dict(service='project-hub', multiProject=True, dataHome=str(self.data_home.resolve()))
        invalid = [{}, [], dict(valid, service='other'), dict(valid, multiProject=False),
                   dict(valid, multiProject=1), dict(valid, dataHome=None),
                   dict(valid, dataHome='relative/data'), dict(valid, dataHome='')]
        before = self.manifest.read_bytes()
        for health in invalid:
            with self.subTest(health=health), self.assertRaises(ValueError):
                self.run_install(health=health)
            self.assertEqual(self.manifest.read_bytes(), before)
            self.assertFalse(self.data_home.exists())
            self.assertEqual(self.last_client.opener.open.call_count, 1)
            self.last_inspect.assert_not_called()
            self.last_command.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'health response is too large'):
            self.run_install(health_raw=b'x' * 16001)
        self.assertFalse(self.data_home.exists())

    def test_marketplace_fails_closed_before_copy(self):
        invalid = [[], {'name': 'other', 'plugins': []}, {'name': 'personal', 'plugins': {}},
                   {'name': 'personal', 'plugins': [None]}, {'name': 'personal', 'plugins': []},
                   {'name': 'personal', 'plugins': self.entries['plugins'] * 2}]
        for source in (None, {}, {'source': 'remote', 'path': './plugins/project-hub'},
                       {'source': 'local'}, {'source': 'local', 'path': '../plugins/project-hub'},
                       {'source': 'local', 'path': './plugins/other'},
                       {'source': 'local', 'path': ['./plugins/project-hub']}):
            invalid.append({'name': 'personal', 'plugins': [{'name': 'project-hub', 'source': source}]})
        for entries in invalid:
            with self.subTest(entries=entries):
                self.write_marketplace(entries)
                before = self.manifest.read_bytes()
                with self.assertRaises(ValueError):
                    self.run_install()
                self.assertEqual(self.manifest.read_bytes(), before)
                self.assertFalse((self.base / 'project-hub-backups').exists())
        self.marketplace.write_text('{')
        with self.assertRaises(ValueError):
            self.run_install()

    def test_missing_marketplace_and_wrong_destination_fail_closed(self):
        self.marketplace.unlink()
        with self.assertRaisesRegex(ValueError, 'no personal marketplace'):
            self.run_install()
        self.write_marketplace(self.entries)
        self.manifest.write_text('{"name":"other"}')
        with self.assertRaisesRegex(ValueError, 'another plugin'):
            self.run_install()
        self.assertFalse((self.base / 'project-hub-backups').exists())

    def test_marketplace_requires_exact_resolved_destination(self):
        with self.assertRaisesRegex(ValueError, 'exact update destination'):
            installer.read_marketplace(self.marketplace, self.base / 'elsewhere/project-hub')

    def test_first_install_without_scaffold_is_explicitly_unavailable(self):
        shutil.rmtree(self.target)
        with self.assertRaisesRegex(ValueError, 'scaffold helper; unavailable'):
            self.run_install()
        self.assertFalse(self.target.exists())
        self.assertFalse((self.base / 'project-hub-backups').exists())

    def test_second_guard_blocks_changed_plugin_ownership(self):
        with self.assertRaisesRegex(ValueError, 'different marketplace'):
            self.run_install([{'installed': []}, {'installed': [{'name': 'project-hub', 'marketplaceName': 'other'}]}])
        self.assertTrue((self.base / 'project-hub-backups').exists())

    def test_cache_version_changes_on_same_second(self):
        now = datetime(2026, 10, 2, 0, 0, 0, tzinfo=timezone.utc)
        with patch.object(installer, 'datetime') as clock:
            clock.now.return_value = now
            installer.cache_version(self.target, '0.2.0+codex.20261002000000')
        self.assertEqual(json.loads(self.manifest.read_text())['version'], '0.2.0+codex.20261002000001')


class PackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.package = self.base / 'with spaces/project-hub'
        prepare(self.package, 'http://127.0.0.1:1')

    def tearDown(self):
        self.tmp.cleanup()

    def run_package(self, command, payload, **overrides):
        env = dict(os.environ, PROJECT_HUB_HOME=str(self.base / 'must-not-exist'),
                   PLUGIN_ROOT=str(self.package))
        env.pop('PROJECT_HUB_URL', None)
        env.pop('CODEX_THREAD_ID', None)
        env.pop('CODEX_SESSION_ID', None)
        env.update(overrides)
        mcp=json.loads((self.package/'.mcp.json').read_text())['mcpServers']['project_hub']
        argv=[mcp['command'],*mcp['args']] if command=='mcp' else [
            sys.executable, str(self.package/'scripts/client_entry.py'),
            *([command] if isinstance(command, str) else command)]
        return subprocess.run(argv,
                              input=payload, capture_output=True, text=True, encoding='utf-8',
                              env=env, timeout=8)

    def test_neutral_manifest_shared_entry_and_no_overwrite(self):
        manifest = json.loads((self.package / '.codex-plugin/plugin.json').read_text())
        self.assertEqual(manifest['name'], self.package.name)
        mcp = json.loads((self.package / '.mcp.json').read_text())['mcpServers']
        self.assertEqual(list(mcp), ['project_hub'])
        self.assertIn('client_entry.py', mcp['project_hub']['args'][0])
        hooks = json.loads((self.package / 'hooks/hooks.json').read_text())['hooks']
        for groups in hooks.values():
            for group in groups:
                for hook in group['hooks']:
                    self.assertIn('client_entry.py', hook['command'])
                    self.assertNotIn('PROJECT_HUB_URL', hook['command'])
        with self.assertRaisesRegex(ValueError, 'not overwritten'):
            prepare(self.package, 'http://127.0.0.1:1')

    def test_configured_check_offline_preserves_runner_argv_exit_and_pending_flush(self):
        project = self.base / 'independent project with spaces'
        project.mkdir()
        literal = 'space & | ; $(literal) --url=http://example.com'
        command = [sys.executable, '-c', 'import sys; print(sys.argv[1]); sys.exit(7)', literal]
        result = self.run_package(['check', 'exec', '--project', 'independent', '--task', 'task',
            '--cwd', str(project), '--title', 'Custom runner', '--profile', 'custom-profile', '--', *command], '')
        self.assertEqual(result.returncode, 7, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual((output['status'], output['publication']), ('failed', 'pending'))
        run = Path(output['localLog']).parent
        start = json.loads((run / 'start.json').read_text())
        finish = json.loads((run / 'finish.json').read_text())
        self.assertEqual(start['project'], 'independent')
        self.assertEqual(start['payload']['command'], command)
        self.assertEqual(finish['exitCode'], 7)
        self.assertIn(literal, (run / 'output.log').read_text())
        pending = self.run_package(['check', 'flush', '--project', 'independent', '--cwd', str(project)], '')
        self.assertEqual(pending.returncode, 1, pending.stderr)
        self.assertEqual(json.loads(pending.stdout), {'pending': 1})
        self.assertFalse((self.base / 'must-not-exist').exists())

    def test_configured_check_requires_task_before_launch(self):
        marker = self.base / 'must-not-launch'
        result = self.run_package(['check', 'exec', '--project', 'independent', '--cwd', str(self.base),
            '--', sys.executable, '-c', 'from pathlib import Path; Path("must-not-launch").touch()'], '')
        self.assertEqual(result.returncode, 2)
        self.assertIn('--task', result.stderr)
        self.assertFalse(marker.exists())

    def test_installation_refuses_duplicate_handlers_and_unknown_catalog(self):
        with self.assertRaisesRegex(ValueError, 'Unknown'):
            check_installed({})
        with self.assertRaisesRegex(ValueError, 'different marketplace'):
            check_installed({'installed':[{'name':'project-hub','marketplaceName':'other'}]})
        check_installed({'installed':[{'name':'unrelated','enabled':True}]})

    def test_missing_invalid_config_and_outage_never_write_local_storage(self):
        event = json.dumps(dict(hook_event_name='PreToolUse', tool_name='Write',
                                session_id='package-test', cwd=str(self.base), tool_input={'path':'x.py'}))
        config = self.package / 'connection.json'
        for value in ('{}', '[]', '{"url":null}', '{"url":"https://example.com"}',
                      '{"url":"http://127.0.0.1:1"}'):
            with self.subTest(config=value):
                config.write_text(value)
                result = self.run_package('hook', event)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {})
                self.assertFalse((self.base / 'must-not-exist').exists())
        config.unlink()
        self.assertEqual(json.loads(self.run_package('hook', event).stdout), {})

    def test_mcp_initializes_with_neutral_name_and_reports_outage(self):
        messages = [dict(jsonrpc='2.0',id=1,method='initialize',params={'protocolVersion':'2024-11-05'}),
                    dict(jsonrpc='2.0',id=2,method='tools/call',params=dict(name='hub_context',arguments={'session':'package-test'}))]
        result = self.run_package('mcp', '\n'.join(json.dumps(x) for x in messages)+'\n')
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(rows[0]['result']['serverInfo']['name'], 'project-hub')
        self.assertTrue(rows[1]['result']['isError'])
        self.assertIn('server_unavailable', json.dumps(rows[1]))
        self.assertFalse((self.base / 'must-not-exist').exists())

    def test_tool_hooks_do_not_even_import_transport_or_require_identity(self):
        (self.package / 'scripts/hub_http.py').unlink()
        (self.package / 'connection.json').unlink()
        for kind in ('PreToolUse', 'PostToolUse'):
            for tool in ('apply_patch', 'Edit', 'Write', 'Bash'):
                with self.subTest(kind=kind, tool=tool):
                    result = self.run_package('hook', json.dumps(dict(
                        hook_event_name=kind, tool_name=tool, agent_id='broken-identity')))
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(json.loads(result.stdout), {})
        result = self.run_package('hook', json.dumps(dict(hook_event_name='SessionStart')))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {})

    def test_observation_outages_and_malformed_events_cannot_block(self):
        for payload in ('{', '[]', 'null'):
            result = self.run_package('hook', payload)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {})
        for kind in ('SessionStart', 'UserPromptSubmit', 'Stop', 'Interrupt', 'SessionEnd'):
            result = self.run_package('hook', json.dumps(dict(
                hook_event_name=kind, session_id='offline', cwd=str(self.base))))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {})
        self.assertFalse((self.base / 'must-not-exist').exists())


class LivePackageTest(unittest.TestCase):
    def test_prepared_hook_and_mcp_share_configured_server(self):
        fixture = api_fixture.PluginApiTest()
        fixture.setUp()
        try:
            package = fixture.base / 'package with spaces/project-hub'
            prepare(package, 'http://127.0.0.1:' + str(fixture.server.server_port))
            env = dict(os.environ, PLUGIN_ROOT=str(package), PROJECT_HUB_HOME=str(fixture.base/'no-local-db'))
            env.pop('PROJECT_HUB_URL', None)
            env.pop('CODEX_THREAD_ID', None)
            env.pop('CODEX_SESSION_ID', None)
            event = dict(hook_event_name='SessionStart',session_id='package-live',cwd=str(fixture.base/'a'))
            hook = json.loads((package/'hooks/hooks.json').read_text())['hooks']['SessionStart'][0]['hooks'][0]
            # Match Codex's actual shell, not Python's shell=True (cmd.exe on Windows).
            result = subprocess.run(hook_argv(hook), input=json.dumps(event), capture_output=True,
                                    text=True, encoding='utf-8', env=env, timeout=8)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('package-live',result.stdout)
            request = dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(name='hub_context',arguments={'session':'package-live'}))
            result = subprocess.run([sys.executable,str(package/'scripts/client_entry.py'),'mcp','--root',str(fixture.base/'a')],
                                    input=json.dumps(request)+'\n',capture_output=True,text=True,encoding='utf-8',env=env,timeout=8)
            self.assertEqual(result.returncode,0,result.stderr)
            body = json.loads(json.loads(result.stdout)['result']['content'][0]['text'])
            self.assertEqual(body['project'],fixture.ids['a'])
            edit = dict(event, hook_event_name='PreToolUse', tool_name='apply_patch',
                        tool_input={'command': '*** Begin Patch\n*** Add File: src/probe.py\n+pass\n*** End Patch'})
            guard = json.loads((package/'hooks/hooks.json').read_text())['hooks']['PreToolUse'][0]['hooks'][0]
            def check_guard():
                result = subprocess.run(hook_argv(guard), input=json.dumps(edit), capture_output=True,
                                        text=True, encoding='utf-8', env=env, timeout=8)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout).get('hookSpecificOutput', {}).get('permissionDecision')
            self.assertIsNone(check_guard())
            task = fixture.client.call(fixture.base/'a', 'package-live', 'hub_task',
                                       dict(title='Package guard', scope=['src'], acceptance=['Guard']))['task']
            fixture.client.call(fixture.base/'a', 'package-live', 'hub_begin',
                                dict(task=task, title='Claim path', resources=['src']))
            self.assertNotEqual(check_guard(), 'deny')
            self.assertFalse((fixture.base/'no-local-db').exists())
        finally:
            fixture.tearDown()


if __name__ == '__main__':
    unittest.main()
