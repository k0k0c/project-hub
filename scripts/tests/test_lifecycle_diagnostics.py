"""Lifecycle recovery and diagnostic edits against isolated Hub data only."""
import os
import json
import time
import subprocess
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_project_hub_plugin_api as fixtures
from hub_core import HubError
from hub_plugin import Mcp, TOOLS, hook
from hub_core import Hub
from prepare_project_hub_plugin import prepare
from test_project_hub_package import hook_argv


class LifecycleDiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PluginApiTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.base / 'a'

    def connection(self):
        with patch.dict(os.environ, {}, clear=True):
            return Mcp(None, str(self.root), client=self.fixture.client)

    def test_binding_persists_on_instance_and_requires_rebind_on_replacement(self):
        api = self.connection()
        with self.assertRaises(HubError) as error:
            api.call('hub_context', {})
        self.assertEqual(error.exception.body['error'], 'identity_missing')
        self.assertIn('retry once', error.exception.body['message'])
        bound = api.call('hub_context', {'session': 'diagnostic-child'})
        self.assertEqual(bound['project'], self.fixture.ids['a'])
        self.assertEqual(bound['session'], 'diagnostic-child')
        self.assertEqual(api.session, 'diagnostic-child')
        api.dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})
        self.assertEqual(api.call('hub_context', {})['project'], bound['project'])
        replacement = self.connection()
        with self.assertRaises(HubError) as error:
            replacement.call('hub_context', {})
        self.assertEqual(error.exception.body['error'], 'identity_missing')
        replacement.call('hub_context', {'session': 'diagnostic-child'})
        self.assertEqual(replacement.call('hub_context', {})['project'], bound['project'])
        with self.assertRaises(HubError) as error:
            replacement.call('hub_context', {'session': 'another-child'})
        self.assertEqual(error.exception.body['error'], 'session_mismatch')
        self.assertEqual(replacement.session, 'diagnostic-child')

    def test_decision_requires_title_without_creating_stage(self):
        api = self.connection()
        api.call('hub_context', {'session': 'diagnostic-child'})
        task = api.call('hub_task', dict(title='Lifecycle', scope=['Diagnostics'],
                                        acceptance=['Verified']))['task']
        before = api.call('hub_plan', {'task': task})
        for title in (None, '', '   '):
            args = dict(task=task, decision='Bounded recovery', expected=before['revision'])
            if title is not None:
                args['title'] = title
            with self.assertRaises(HubError):
                api.call('hub_plan', args)
            self.assertEqual(api.call('hub_plan', {'task': task})['revision'], before['revision'])
        api.call('hub_plan', dict(task=task, title='Recovery policy',
                                 decision='Bounded recovery', expected=before['revision']))
        after = api.call('hub_plan', {'task': task})
        self.assertEqual(after['task']['stages'], [])
        events = self.fixture.registry.store(self.fixture.ids['a']).snapshot()['allEvents']
        self.assertTrue(any(e['kind'] == 'decision' and e['title'] == 'Recovery policy' for e in events))
        tool = next(t for t in TOOLS if t['name'] == 'hub_plan')
        self.assertIn('nonempty title', tool['description'])
        self.assertIn('nonempty title', tool['inputSchema']['properties']['decision']['description'])

    def diagnostic_hub(self):
        return Hub(self.fixture.registry.home / 'coordination')

    def diagnostics(self):
        with self.diagnostic_hub().connect() as c:
            return [dict(r) for r in c.execute("SELECT * FROM events WHERE kind='diagnostic.edit_without_write_work'")]

    def edit(self, **extra):
        return dict(session_id='session-a', cwd=str(self.root), hook_event_name='PreToolUse',
                    tool_name='Write', tool_input={'path':'diagnostic.txt', 'content':'PRIVATE'}, **extra)

    def test_edit_without_work_emits_observation_only_for_bound_actor(self):
        self.fixture.invoke('a','hub_context')
        raw = self.edit()
        self.assertEqual(self.fixture.client.hook(raw), {})
        rows = self.diagnostics()
        self.assertEqual(len(rows), 1)
        body = json.loads(rows[0]['body'])
        self.assertEqual(body['paths'], ['diagnostic.txt'])
        self.assertEqual(body['phase'], 'PreToolUse')
        self.assertEqual(body['observation'], 'edit_tool_received')
        self.assertNotIn('PRIVATE', rows[0]['body'])
        self.assertEqual(rows[0]['session'], 'session-a')
        self.assertEqual(self.fixture.client.hook({**raw, 'agent_id':'unbound-child'}), {})
        self.assertEqual(len(self.diagnostics()), 1)
        self.assertEqual(self.fixture.client.hook({**raw, 'hook_event_name':'PostToolUse',
            'tool_name':'apply_patch', 'tool_input':'*** Begin Patch\n*** Add File: observed.txt\n+PRIVATE\n*** End Patch'}), {})
        last = json.loads(self.diagnostics()[-1]['body'])
        self.assertEqual(last['paths'], ['observed.txt'])
        self.assertEqual(last['phase'], 'PostToolUse')
        self.assertNotIn('PRIVATE', json.dumps(last))

    def test_matching_stage_write_work_suppresses_diagnostic(self):
        task = self.fixture.invoke('a','hub_task', title='Edit', scope=['Edit'], acceptance=['Checked'])['task']
        self.fixture.invoke('a','hub_plan', task=task, stage='edit', title='Edit')
        self.fixture.invoke('a','hub_begin', task=task, stage='edit', title='Edit', resources=['diagnostic.txt'])
        self.assertEqual(self.fixture.client.hook(self.edit()), {})
        self.assertEqual(self.diagnostics(), [])
        self.assertEqual(self.fixture.client.hook({**self.edit(), 'tool_input':{'path':'other.txt'}}), {})
        self.assertEqual(len(self.diagnostics()), 1)

    def test_read_work_is_not_write_work_and_read_tools_are_ignored(self):
        task = self.fixture.invoke('a','hub_task', title='Review', scope=['Read'], acceptance=['Checked'])['task']
        self.fixture.invoke('a','hub_plan', task=task, stage='read', title='Read')
        self.fixture.invoke('a','hub_begin', task=task, stage='read', title='Read', resources=['diagnostic.txt'], mode='read')
        for tool in ('Read', 'Bash', 'exec_command'):
            self.assertEqual(self.fixture.client.hook({**self.edit(), 'tool_name':tool}), {})
        self.assertEqual(self.diagnostics(), [])
        self.fixture.client.hook(self.edit())
        self.assertEqual(len(self.diagnostics()), 1)

    def test_missing_metadata_failures_and_locked_database_return_empty(self):
        self.assertEqual(hook(None, self.edit()), {})
        self.fixture.invoke('a','hub_context')
        for change in ({'session_id':'unknown'}, {'cwd':''}, {'tool_input':{}}, {'agent_id':None, 'session_id':''}):
            self.assertEqual(self.fixture.client.hook({**self.edit(), **change}), {})
        self.assertEqual(self.diagnostics(), [])
        with patch.object(Hub, 'observe_edit', side_effect=RuntimeError('unavailable')):
            self.assertEqual(self.fixture.client.hook(self.edit()), {})
        with self.diagnostic_hub().connect() as c:
            c.execute('BEGIN IMMEDIATE')
            start = time.monotonic()
            self.assertEqual(self.fixture.client.hook(self.edit()), {})
            self.assertLess(time.monotonic() - start, 1.5)
        with patch.object(self.fixture.client.opener, 'open', side_effect=OSError('offline')) as send:
            self.assertEqual(self.fixture.client.hook(self.edit()), {})
            self.assertEqual(send.call_args.kwargs['timeout'], .5)
        self.assertEqual(self.diagnostics(), [])

    def test_prepared_hook_command_records_diagnostics_without_permission_output(self):
        package = self.fixture.base / 'package with spaces' / 'project-hub'
        prepare(package, 'http://127.0.0.1:' + str(self.fixture.server.server_port))
        env = dict(os.environ, PLUGIN_ROOT=str(package),
                   PROJECT_HUB_HOME=str(self.fixture.base / 'no-client-storage'))
        for key in ('PROJECT_HUB_URL', 'CODEX_THREAD_ID', 'CODEX_SESSION_ID'):
            env.pop(key, None)
        mcp = json.loads((package / '.mcp.json').read_text())['mcpServers']['project_hub']
        request = dict(jsonrpc='2.0', id=1, method='tools/call',
                       params=dict(name='hub_context', arguments={'session':'session-a'}))
        result = subprocess.run([mcp['command'], *mcp['args'], '--root', str(self.root)],
                                input=json.dumps(request) + '\n', capture_output=True,
                                text=True, encoding='utf-8', env=env, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        response = json.loads(result.stdout)['result']
        self.assertFalse(response['isError'], response)
        bound = json.loads(response['content'][0]['text'])
        self.assertEqual(bound['session'], 'session-a')
        self.assertEqual(bound['project'], self.fixture.ids['a'])
        group = json.loads((package / 'hooks/hooks.json').read_text())['hooks']['PreToolUse'][0]
        self.assertEqual(set(group['matcher'].split('|')), {'apply_patch','Edit','Write'})
        handler = group['hooks'][0]
        self.assertLessEqual(handler['timeout'], 3)

        def run_hook(raw):
            start = time.monotonic()
            result = subprocess.run(hook_argv(handler), input=json.dumps(raw), capture_output=True,
                                    text=True, encoding='utf-8', env=env, timeout=8)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), {})
            return time.monotonic() - start

        run_hook(self.edit())
        self.assertEqual(len(self.diagnostics()), 1)
        body = json.loads(self.diagnostics()[0]['body'])
        self.assertEqual(body['paths'], ['diagnostic.txt'])
        self.assertNotIn('PRIVATE', json.dumps(body))
        task = self.fixture.invoke('a','hub_task', title='Prepared edit', scope=['Edit'], acceptance=['Checked'])['task']
        self.fixture.invoke('a','hub_plan', task=task, stage='edit', title='Edit')
        self.fixture.invoke('a','hub_begin', task=task, stage='edit', title='Edit', resources=['diagnostic.txt'])
        run_hook(self.edit())
        self.assertEqual(len(self.diagnostics()), 1)
        for change in ({'tool_name':'Read'}, {'tool_name':'Bash'}, {'session_id':'unbound'}, {'session_id':''}):
            run_hook({**self.edit(), **change})
        self.assertEqual(len(self.diagnostics()), 1)
        config = package / 'connection.json'
        for value in ('{}', '{"url":"http://127.0.0.1:1"}'):
            config.write_text(value, encoding='utf-8')
            self.assertLess(run_hook(self.edit()), 4)
        self.assertEqual(len(self.diagnostics()), 1)
        self.assertFalse((self.fixture.base / 'no-client-storage').exists())


if __name__ == '__main__':
    unittest.main()
