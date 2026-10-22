"""Check discovery and dispatch without production storage."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

PLUGIN = Path(__file__).resolve().parents[2] / 'tools/project-portal/plugins/project-hub'
sys.path.insert(0, str(PLUGIN / 'scripts'))
from hub_check import validate_check
from hub_core import Hub, HubError
from hub_http import Client
from hub_plugin import Mcp, TOOLS


def event(**extra):
    return dict(dict(runId='contract-run', task='task', stage='stage', status='running',
                     command=['runner', 'literal;argument'], scope=['scripts'],
                     startedAt='2026-09-19T12:00:00Z'), **extra)


class CheckPluginContractTest(unittest.TestCase):
    def test_discovery_and_server_dispatch(self):
        schema = next(item['inputSchema'] for item in TOOLS if item['name'] == 'hub_check')
        self.assertFalse(schema['additionalProperties'])
        self.assertNotIn('project', schema['properties'])
        self.assertNotIn('session', schema['properties'])
        hub = MagicMock()
        api = Mcp(hub, cwd='workspace', session='own-child')
        args = event(title='Verify publication', profile='opaque', profileVersion='v1', revision={'head': 'abc', 'dirty': True})
        self.assertIs(api.call('hub_check', args), hub.check.return_value)
        hub.check.assert_called_once_with('own-child', **args)

    def test_remote_preserves_envelope(self):
        client = Client('http://127.0.0.1:1')
        client.opener = MagicMock()
        client.opener.open.return_value.__enter__.return_value.read.return_value = b'{"ok":true}'
        self.assertEqual(Mcp(None, cwd='workspace', session='child', client=client).call('hub_check', event()), {'ok': True})
        request = client.opener.open.call_args.args[0]
        self.assertEqual(json.loads(request.data), dict(cwd='workspace', session='child', tool='hub_check', arguments=event()))

    def test_core_requires_server(self):
        with self.assertRaises(HubError) as error:
            Hub.check(None, 'child', **event())
        self.assertEqual(error.exception.body['error'], 'server_required')

    def test_invalid_shapes_do_not_reach_remote(self):
        client = MagicMock()
        api = Mcp(None, session='child', client=client)
        invalid = [event(project='elsewhere'), event(command=[]), event(scope=['../private']),
                   event(scope=['C:\\secret']), event(status='passed'),
                   event(status='passed', finishedAt='2026-09-19T12:01:00Z', exitCode=1),
                   event(exitCode=0), event(startedAt='yesterday'), event(profile='x' * 241),
                   event(title=''), event(title='x' * 241),
                   event(counts={'huge': 'x' * 16000}), event(counts={'nan': float('nan')}),
                   event(revision={'head': 'abc', 'dirty': 'yes'}),
                   event(status='failed', finishedAt='2026-09-19T12:01:00Z'),
                   event(status='passed', exitCode=0, finishedAt='2026-09-19T11:59:00Z'),
                   event(counts={'passed': 0})]
        for args in invalid:
            with self.subTest(args=str(args)[:100]), self.assertRaises(HubError):
                api.call('hub_check', args)
        client.call.assert_not_called()

    def test_finish_variants_and_runner_defined_counts(self):
        for status, extra in [('passed', {'exitCode': 0}), ('failed', {'exitCode': 7}),
                              ('interrupted', {'exitCode': -2}), ('unknown', {})]:
            validate_check(event(status=status, finishedAt='2026-09-19T12:01:00Z',
                                 counts={'runnerSpecificCount': 4}, **extra))

    def test_optional_scope_nongit_revision_and_empty_argv(self):
        payload = event(command=['test-runner', ''], revision={'head': None, 'dirty': True})
        del payload['scope']
        self.assertEqual(json.loads(validate_check(payload)), payload)
        validate_check(event(revision={}, stage=None))
        validate_check(event(status='unknown', finishedAt='2026-09-19T12:01:00Z',
                             exitCode=None, durationMs=None, summary=''))

    def test_contract_boundaries(self):
        for field, value in [('runId', 'x' * 121), ('task', 'x' * 151),
                             ('command', ['runner'] * 101), ('scope', ['src'] * 101),
                             ('evidence', [{'label': 'log', 'path': 'log'}] * 21),
                             ('counts', {'x' * 41: 1}), ('counts', {'x': -1}),
                             ('counts', {'x': True}), ('durationMs', float('inf'))]:
            payload = event(status='unknown', finishedAt='2026-09-19T12:01:00Z', **{field: value})
            with self.subTest(field=field, value=str(value)[:80]), self.assertRaises(HubError):
                validate_check(payload)


if __name__ == '__main__':
    unittest.main()
