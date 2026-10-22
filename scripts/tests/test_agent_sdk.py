import json
import io
import os
import tempfile
import unittest
from pathlib import Path
from urllib.error import URLError
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from agent_sdk import Client, SDKError, generic_mcp_config, load_connection, save_connection, mcp_server_name


class Response:
    def __init__(self, payload): self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit=None): return self.payload if limit is None else self.payload[:limit]


class Opener:
    def __init__(self, payloads): self.payloads, self.requests = list(payloads), []
    def open(self, request, timeout):
        self.requests.append((request, timeout))
        payload = self.payloads.pop(0)
        if isinstance(payload, Exception): raise payload
        return Response(payload)


class AgentSdkTests(unittest.TestCase):
    def test_loopback_and_request_contract(self):
        opener = Opener([{'project': None, 'invitation': 'abc'}, {'token': 'secret', 'binding': 'b1', 'project': 'p1'}, {'ok': True}])
        client = Client('http://127.0.0.1:8769/', token='secret', opener=opener, session='session-1')
        self.assertEqual(client.connect('abc')['project'], None)
        client.enroll('abc', 'host', 'external', name='Example', roots=['C:/src'])
        client.call('hub_context', {})
        self.assertEqual(opener.requests[0][0].full_url, 'http://127.0.0.1:8769/connect/abc')
        self.assertNotIn('Authorization', opener.requests[0][0].headers)
        enroll = json.loads(opener.requests[1][0].data)
        self.assertNotIn('session', enroll)
        call = json.loads(opener.requests[2][0].data)
        self.assertEqual(call['arguments']['session'], 'session-1')
        self.assertEqual(opener.requests[2][0].headers['Authorization'], 'Bearer secret')

    def test_session_cannot_be_overridden_and_network_mutation_is_unknown(self):
        client = Client('http://localhost:8769', token='secret', opener=Opener([]), session='owned')
        with self.assertRaises(ValueError): client.call('hub_context', {'session': 'other'})
        client.opener = Opener([URLError('lost')])
        with self.assertRaises(SDKError) as caught: client.call('hub_task', {})
        self.assertTrue(caught.exception.outcomeUnknown)

    def test_upload_is_bounded_base64_and_bearer_scoped(self):
        opener = Opener([{'artifact': 'ok'}])
        client = Client('http://127.0.0.1', token='secret', opener=opener)
        client.upload('x.txt', b'hello', roles=['task'])
        request = opener.requests[0][0]
        self.assertEqual(request.headers['Authorization'], 'Bearer secret')
        self.assertEqual(json.loads(request.data)['content'], 'aGVsbG8=')

    def test_empty_non_object_broken_and_oversized_ack_are_typed_unknown(self):
        payloads = [b'', b'[]', b'not-json', b'x' * 240_001]
        for payload in payloads:
            opener = Opener([payload])
            client = Client('http://127.0.0.1', token='secret', opener=opener, session='s')
            with self.assertRaises(SDKError) as caught:
                client.call('hub_task', {})
            self.assertEqual(caught.exception.code, 'invalid_response')
            self.assertTrue(caught.exception.outcomeUnknown)
        opener = Opener([b''])
        with self.assertRaises(SDKError) as caught:
            Client('http://127.0.0.1', opener=opener).connect('invite')
        self.assertEqual(caught.exception.code, 'invalid_response')
        self.assertFalse(caught.exception.outcomeUnknown)

    def test_oversized_upload_is_rejected_before_network(self):
        opener = Opener([])
        client = Client('http://127.0.0.1', token='secret', opener=opener)
        with self.assertRaises(ValueError): client.upload('large.bin', b'x' * (20 * 1024 * 1024 + 1))
        self.assertEqual(opener.requests, [])

    def test_connection_file_is_atomic_private_and_config_has_no_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'connection.json'
            save_connection(path, {'baseUrl': 'http://127.0.0.1:8769', 'token': 'secret', 'session': 'omit'})
            self.assertNotIn('session', load_connection(path))
            if os.name=='nt':
                stored=json.loads(path.read_text(encoding='utf-8'))
                self.assertNotIn('token',stored)
                self.assertEqual(stored['credentialProtection'],'windows-dpapi')
                self.assertNotIn('secret',path.read_text(encoding='utf-8'))
            self.assertIn(path.stat().st_mode & 0o777, (0o600, 0o666))
            generic = generic_mcp_config('http://127.0.0.1:8769')
            self.assertEqual(generic['mcpServers']['project_hub']['url'],'http://localhost:8769/mcp')
            self.assertNotIn('secret', json.dumps(generic))
            self.assertNotIn('Authorization', generic['mcpServers']['project_hub'])
            self.assertEqual(generic_mcp_config('http://127.0.0.1:8769','secret')['mcpServers']['project_hub']['headers']['Authorization'],'Bearer secret')

    def test_non_loopback_and_redirects_are_rejected(self):
        for url in ('https://127.0.0.1', 'http://example.test', 'http://127.0.0.1/x', 'http://127.0.0.1/?x=1'):
            with self.assertRaises(ValueError): Client(url)

    def test_connection_retry_is_idempotent_and_never_replaces_existing_content(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'private.json'
            value = {'baseUrl': 'http://127.0.0.1:8769', 'token': 'secret'}
            save_connection(path, value)
            before = path.read_bytes()
            save_connection(path, value)
            self.assertEqual(path.read_bytes(), before)
            with self.assertRaises(ValueError):
                save_connection(path, {**value, 'token': 'other-secret'})
            self.assertEqual(path.read_bytes(), before)

    def test_private_connection_cannot_be_written_into_application_tree(self):
        import agent_sdk
        path = Path(agent_sdk.__file__).resolve().parents[1] / 'private-token.json'
        with self.assertRaises(ValueError):
            save_connection(path, {'baseUrl': 'http://127.0.0.1', 'token': 'secret'})
        self.assertFalse(path.exists())

    def test_cli_config_and_onboarding_share_secret_free_stable_server_name(self):
        import hub_cli
        import native_onboarding
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory).resolve()
            workspace = base / 'workspace'
            workspace.mkdir()
            path = base / 'private.json'
            connection = dict(baseUrl='http://127.0.0.1:8769', token='PrivateCliFixtureToken', project='example', binding='owned-binding', workspace=str(workspace))
            save_connection(path, connection)
            with patch('sys.stdout', io.StringIO()) as stream:
                self.assertEqual(hub_cli.main(['config', '--connection', str(path)]), 0)
                output = stream.getvalue()
            config = json.loads(output)
            name = mcp_server_name(connection)
            plan = native_onboarding.build_plan('cursor', connection, '# Workflow\nRead hub_context.', connection_path=path)
            self.assertEqual(list(config['mcpServers']), [name])
            self.assertEqual(plan.mcp['server'], name)
            self.assertEqual(config['mcpServers'][name], plan.mcp['entry'])
            self.assertNotIn(connection['token'], output)
            self.assertEqual(config['transport'],'streamable-http')
            self.assertIn(config['credentialEnvironment'],output)
            self.assertNotIn('command',config['mcpServers'][name])
            self.assertEqual(mcp_server_name({**connection, 'token': 'rotated'}), name)
            self.assertNotEqual(mcp_server_name({**connection, 'binding': 'other-binding'}), name)

    def test_global_client_publishes_explicit_selection_and_client_reported_metadata(self):
        opener = Opener([{'scope':'global'}, {'projects':[]}, {'ok':True}, {'source':{}}])
        client = Client('http://127.0.0.1:8769',token='PrivateHubToken',session='own',
                        project='explicit-project',workspace='C:/registered-code',opener=opener)
        client.enroll('invitation','unknown-host','connection-id',model='Actual model',
                      session='Reported session',chat='Reported chat',metadata={'clientVersion':'example'})
        enroll = json.loads(opener.requests[0][0].data)
        self.assertEqual(enroll['model'],'Actual model')
        self.assertNotIn('project',enroll)
        client.call('hub_projects')
        self.assertEqual(json.loads(opener.requests[1][0].data)['arguments'],{'session':'own'})
        client.call('hub_context')
        args = json.loads(opener.requests[2][0].data)['arguments']
        self.assertEqual(args['project'],'explicit-project')
        self.assertEqual(args['workspace'],'C:/registered-code')
        client.upload('proof.txt',b'proof')
        self.assertEqual(json.loads(opener.requests[3][0].data)['project'],'explicit-project')
        global_name = mcp_server_name({'binding':'global-binding','project':None})
        self.assertEqual(global_name,mcp_server_name({'binding':'global-binding'}))

    def test_cli_global_enrollment_requires_no_project_or_model(self):
        import hub_cli
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'private-connection.json'
            sdk = Client('http://127.0.0.1:8769',opener=Opener([
                {'invitation':'invite','scope':'global','project':None,'workflow':'Contract version: 2'},
                {'binding':'global-binding','scope':'global','project':None,'token':'PrivateHubToken'}]))
            with patch.object(hub_cli,'Client',return_value=sdk),patch('sys.stdout',io.StringIO()) as stream:
                self.assertEqual(hub_cli.main(['connect','http://127.0.0.1:8769/connect/invite',
                    '--client','unknown-host','--external-id','global-connection','--output',str(path)]),0)
            self.assertNotIn('PrivateHubToken',stream.getvalue())
            self.assertIsNone(load_connection(path)['project'])
            self.assertEqual(load_connection(path)['scope'],'global')


if __name__ == '__main__': unittest.main()
