"""Portable settings discovery and dispatch, without production storage."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

PLUGIN = Path(__file__).resolve().parents[2] / 'tools/project-portal/plugins/project-hub'
sys.path.insert(0, str(PLUGIN / 'scripts'))
from hub_core import Hub, HubError
from hub_http import Client
from hub_plugin import Mcp, TOOLS


class SettingsPluginContractTest(unittest.TestCase):
    def test_discovery_has_portable_exact_property_names(self):
        result = Mcp(None, session='test-child').dispatch(
            dict(id=1, method='tools/list'))['result']
        tools = {tool['name']: tool for tool in result['tools']}
        schema = tools['hub_settings']['inputSchema']
        self.assertEqual(set(schema['properties']), {'patch', 'expected', 'reset'})
        self.assertFalse(schema['additionalProperties'])
        self.assertEqual(schema['oneOf'][0], {'maxProperties': 0})
        sections = schema['properties']['patch']['properties']
        self.assertEqual(set(sections), {'git', 'tasks', 'viewer'})
        self.assertEqual(set(sections['git']['properties']), {'autoCommit', 'commitOn'})
        self.assertEqual(sections['git']['properties']['commitOn']['enum'],
                         ['stage-and-task', 'stage', 'task'])
        self.assertEqual(set(sections['tasks']['properties']),
                         {'columns', 'sort', 'overviewSort', 'showCompleted', 'showEpicsOnOverview',
                          'showUpcomingOnOverview'})
        self.assertEqual(sections['tasks']['properties']['showEpicsOnOverview']['type'], 'boolean')
        self.assertEqual(sections['tasks']['properties']['showUpcomingOnOverview']['type'], 'boolean')
        self.assertEqual(set(sections['viewer']['properties']),
                         {'wrapLines', 'showSourceDetails'})
        self.assertEqual(schema['properties']['reset']['enum'], ['git', 'tasks', 'viewer'])
        for section in sections.values():
            self.assertFalse(section['additionalProperties'])
        self.assertIn('projectSettings', tools['hub_context']['description'])
        self.assertIn('revision', tools['hub_context']['description'])

    def test_canonical_dispatch_preserves_envelope_and_optional_arguments(self):
        hub = MagicMock()
        envelope = dict(project='test', settings=dict(git=dict(autoCommit=False,
            commitOn='stage-and-task'), tasks=dict(columns=['title'], sort='created',
            overviewSort='created', showCompleted=False, showEpicsOnOverview=False,
            showUpcomingOnOverview=True), viewer=dict(wrapLines=True,
            showSourceDetails=False)), revision='settings:1', configured=False, history=[])
        hub.settings.return_value = envelope
        api = Mcp(hub, cwd='test-workspace', session='test-child')
        for args in ({}, {'patch': {'git': {'autoCommit': True}}, 'expected': 'settings:1'},
                     {'reset': 'viewer', 'expected': 'settings:2'}):
            self.assertIs(api.call('hub_settings', args), envelope)
            hub.settings.assert_called_with('test-child', **args)

    def test_remote_route_uses_existing_http_transport(self):
        client = Client('http://127.0.0.1:1')
        client.opener = MagicMock()
        response = client.opener.open.return_value.__enter__.return_value
        response.read.return_value = b'{"revision":"settings:2"}'
        api = Mcp(None, cwd='test-workspace', session='test-child', client=client)
        for name, args in (('hub_settings', {}),
                           ('hub_settings', {'reset': 'git', 'expected': 'settings:1'}),
                           ('hub_checkpoint', {'task': 'test-task', 'stage': 'settings-contract',
                                               'expected': 'project:2'}),
                           ('hub_checkpoint', {'task': 'test-task', 'expected': 'project:2',
                                               'commits': ['a' * 40, 'B' * 64],
                                               'reason': 'Reviewed existing commits'})):
            self.assertEqual(api.call(name, args), {'revision': 'settings:2'})
            request = client.opener.open.call_args.args[0]
            self.assertEqual(request.full_url, 'http://127.0.0.1:1/api/v1/plugin/call')
            self.assertEqual(json.loads(request.data), dict(cwd='test-workspace',
                session='test-child', tool=name, arguments=args))

    def test_invalid_update_shapes_do_not_reach_server(self):
        client = MagicMock()
        api = Mcp(None, session='test-child', client=client)
        for args in ({'expected': 1}, {'patch': {}}, {'reset': 'git'},
                     {'patch': {}, 'reset': 'git', 'expected': 1}, {'credentials': {}}):
            with self.subTest(args=args), self.assertRaises(HubError):
                api.call('hub_settings', args)
        client.call.assert_not_called()

    def test_checkpoint_discovery_and_dispatch(self):
        schema = next(t for t in TOOLS if t['name'] == 'hub_checkpoint')['inputSchema']
        self.assertEqual(set(schema['properties']), {'task', 'stage', 'expected', 'commits', 'reason'})
        self.assertEqual(schema['required'], ['task', 'expected'])
        self.assertFalse(schema['additionalProperties'])
        commits = schema['properties']['commits']
        self.assertEqual((commits['minItems'], commits['maxItems']), (1, 20))
        self.assertTrue(commits['uniqueItems'])
        self.assertIn('unique ignoring case', commits['description'])
        for sha in ('a' * 40, 'B' * 64):
            self.assertRegex(sha, commits['items']['pattern'])
        for sha in ('a' * 39, 'a' * 41, 'a' * 63, 'a' * 65, 'g' * 40):
            self.assertNotRegex(sha, commits['items']['pattern'])
        self.assertEqual(schema['properties']['reason']['maxLength'], 1200)
        self.assertEqual(schema['oneOf'], [dict(required=['commits', 'reason']),
            {'not': {'anyOf': [dict(required=['commits']), dict(required=['reason'])]}}])
        hub = MagicMock()
        hub.checkpoint.return_value = {'gitCheckpoint': {'id': 'checkpoint-1',
            'status': 'pending', 'settingsRevision': 'settings:1'}}
        api = Mcp(hub, cwd='test-workspace', session='test-child')
        for stage in (None, 'settings-contract'):
            args = dict(task='test-task', expected='project:2')
            if stage is not None:
                args['stage'] = stage
            self.assertIs(api.call('hub_checkpoint', args), hub.checkpoint.return_value)
            hub.checkpoint.assert_called_with('test-child', 'test-task', 'project:2', stage=stage)
        with self.assertRaises(HubError):
            api.call('hub_checkpoint', {'task': 'test-task'})

    def test_reconciliation_dispatch_preserves_order_reason_and_server_result(self):
        hub = MagicMock()
        hub.checkpoint.return_value = {'gitCheckpoint': {'status': 'committed',
            'commits': ['b' * 40, 'A' * 64]}}
        api = Mcp(hub, session='test-child')
        for stage in (None, 'settings-contract'):
            for commits, reason in ((['b' * 40, 'A' * 64], ' Reviewed commits '),
                                    ([format(i, '040x') for i in range(20)], 'r' * 1200)):
                args = dict(task='test-task', expected='project:2', commits=commits, reason=reason)
                if stage is not None:
                    args['stage'] = stage
                self.assertIs(api.call('hub_checkpoint', args), hub.checkpoint.return_value)
                hub.checkpoint.assert_called_with('test-child', 'test-task', 'project:2',
                    stage=stage, commits=commits, reason=reason)

    def test_invalid_reconciliation_never_reaches_local_or_remote_backend(self):
        malformed = [dict(commits=['a' * 40]), dict(reason='Reviewed'),
            dict(commits=None, reason='Reviewed'), dict(commits=[], reason='Reviewed'),
            dict(commits=['a' * 40] * 21, reason='Reviewed'),
            dict(commits='a' * 40, reason='Reviewed')]
        malformed += [dict(commits=[sha], reason='Reviewed') for sha in
                      ('a' * 39, 'a' * 41, 'a' * 63, 'a' * 65, 'g' * 40, 'a' * 40 + '\n', None, 42)]
        malformed += [dict(commits=['a' * 40], reason=reason)
                      for reason in (None, '', ' \t\n', 'r' * 1201, 42)]
        malformed += [dict(commits=commits, reason='Reviewed') for commits in
                      (['a' * 40, 'a' * 40], ['a' * 40, 'A' * 40],
                       ['b' * 64, 'B' * 64])]
        for remote in (False, True):
            hub, client = MagicMock(), MagicMock()
            api = Mcp(hub, session='test-child', client=client if remote else None)
            for extra in malformed:
                with self.subTest(remote=remote, extra=extra), self.assertRaises(HubError):
                    api.call('hub_checkpoint', dict(task='test-task', expected='project:2', **extra))
            hub.checkpoint.assert_not_called()
            client.call.assert_not_called()

    def test_standalone_reconciliation_requires_server(self):
        with self.assertRaises(HubError) as raised:
            Hub.checkpoint(None, 'test-child', 'test-task', 'project:2',
                           commits=['a' * 40], reason='Reviewed')
        self.assertEqual(raised.exception.body['error'], 'server_required')

    def test_instructions_cover_policy_and_failure_boundaries(self):
        text = (PLUGIN / 'skills/project-hub/SKILL.md').read_text(encoding='utf-8')
        # These are the safety-critical portable instruction contracts, not headings.
        for requirement in ('MUST read authoritative `projectSettings`',
                            '`autoCommit=false`, do not create automatic commits',
                            '`commitOn=stage`', '`commitOn=task`', '`commitOn=stage-and-task`',
                            'no_changes', 'missing safe scope', 'pre-existing index',
                            'duplicate or empty commits', 'audit/read-only request',
                            'unknown policy', 'publication pending',
                            'never assume a universal autoCommit',
                            'Change settings only for explicit user intent',
                            'gitCheckpoint', 'gitCommit', 'pending Git',
                            'hub_checkpoint(task, expected=projectRevision',
                            'Never blindly expand safe scope',
                            'Supply `commits` and `reason` together',
                            '1-20 full 40- or 64-hex', 'oldest to newest',
                            'at most 1200 characters', 'ordinary retry is unchanged',
                            'error checkpoint and a completed target', 'legacy-scope-and-trailers',
                            'frozen completed result', 'no Git writes',
                            'uppercase or lowercase', 'other stages are allowed',
                            'Duplicate SHAs are rejected ignoring',
                            'server normalizes accepted SHAs to lowercase',
                            'all intervening commits', 'HEAD has advanced',
                            'dirty paths must have matching changed paths',
                            'snapshots and error journal', 'commits/reason is idempotent',
                            'conflicting completed adoption is rejected',
                            'Push always requires separate', 'no credentials or new approval'):
            self.assertIn(' '.join(requirement.lower().split()), ' '.join(text.lower().split()))


if __name__ == '__main__':
    unittest.main()
