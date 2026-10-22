"""Socket-level model probes independent of native application control.

The model and OAuth account are disposable fixtures. This verifies the server
path, not whether the user's desktop application has physically been closed.
"""
from contextlib import ExitStack
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, ProxyHandler, build_opener
import uuid

from agent_providers import Providers
from api_agent_runs import ApiAgentRuns
from hub_action_context import HubActionContext
from knowledge_store import KnowledgeStore
from project_portal import PortalServer
from project_registry import ProjectRegistry


class IndependentModelConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.registry = ProjectRegistry(Path(self.temporary.name) / 'hub', standalone=True)
        self.addCleanup(self.registry.close_connection_pool)
        self.calls = []
        owner = self

        class Model(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                owner.calls.append((self.path, self.headers.get('Authorization'),
                    json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
                events = []
                if hasattr(owner, 'research_result'):
                    item = dict(type='message', role='assistant', content=[dict(type='output_text',
                        text=json.dumps(owner.research_result))])
                    events.append(dict(type='response.output_item.done', output_index=0, item=item))
                events.append(dict(type='response.completed', response=dict(status='completed', output=[])))
                data = ''.join('data: ' + json.dumps(event) + '\n\n' for event in events).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('X-Request-ID', 'fixture-model-request')
                self.end_headers()
                self.wfile.write(data)

        self.peer = ThreadingHTTPServer(('127.0.0.1', 0), Model)
        self.hub = PortalServer(('127.0.0.1', 0), registry=self.registry)
        for server in (self.peer, self.hub):
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
        self.opener = build_opener(ProxyHandler({}))
        self.base = 'http://127.0.0.1:' + str(self.hub.server_port)
        account = dict(id='a' * 32, label='Example account', status='connected',
            planUsageEnabled=True, generation=1, models=[dict(slug='example-model', displayName='Example model')])
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.patches.enter_context(patch('chatgpt_auth.ChatGPTAuth.account', return_value=account))
        self.patches.enter_context(patch('chatgpt_auth.ChatGPTAuth.catalog', return_value=dict(accounts=[account])))
        self.patches.enter_context(patch('chatgpt_auth.ChatGPTAuth.access_token', return_value='fixture-oauth-token'))
        self.provider = self.post(dict(action='save-chatgpt', expected=Providers(self.registry).catalog()['revision'],
            requestId=uuid.uuid4().hex, name='Example ChatGPT service', accountId=account['id'],
            model='example-model', networkMode='direct'))

    def post(self, body):
        request = Request(self.base + '/api/v1/agent-providers', data=json.dumps(body).encode(),
            headers={'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=5) as response:
            return json.loads(response.read())

    def probe(self):
        return dict(action='probe', id=self.provider['id'], requestId=uuid.uuid4().hex,
            expected=Providers(self.registry).catalog()['revision'])

    def test_chatgpt_http_probe_and_exact_retry_need_no_native_app_or_environment(self):
        owner = self

        class Forwarder:
            def open(self, request, timeout):
                owner.assertEqual(request.full_url, 'https://api.openai.com/v1/responses')
                owner.assertEqual(timeout, 60)
                forwarded = Request('http://127.0.0.1:' + str(owner.peer.server_port) + '/responses',
                    data=request.data, headers=dict(request.header_items()), method=request.method)
                return owner.opener.open(forwarded, timeout=5)

        environment = {key: value for key, value in os.environ.items() if not key.startswith('CODEX_')}
        request = self.probe()
        with patch.dict(os.environ, environment, clear=True), \
                patch('subprocess.Popen', side_effect=AssertionError('A model probe must not start an application')), \
                patch('agent_launches.Launches.start', side_effect=AssertionError('Native launch was used')), \
                patch('connection_capabilities.HttpControl.action', side_effect=AssertionError('Native control was used')), \
                patch('provider_runtime.opener_for', return_value=Forwarder()):
            first = self.post(request)
            self.assertEqual(first['status'], 'completed')
            self.assertEqual(self.post(request), first)
            reloaded = Providers(self.registry).probe_receipt(request['requestId'])
            self.assertEqual(reloaded, first)
        self.assertEqual(len(self.calls), 1)
        path, authorization, payload = self.calls[0]
        self.assertEqual((path, authorization), ('/responses', 'Bearer fixture-oauth-token'))
        self.assertTrue(payload['stream'])
        self.assertNotIn('tools', payload)
        self.assertNotIn('fixture-oauth-token', json.dumps(first))
        self.assertEqual(first['diagnostics'][0]['upstreamRequestId'], 'fixture-model-request')

    def test_chatgpt_timeout_preserves_unknown_outcome_and_does_not_fall_back_or_resend(self):
        class Timeout:
            calls = 0

            def open(self, request, timeout):
                self.calls += 1
                raise TimeoutError('fixture-oauth-token')

        transport = Timeout()
        request = self.probe()
        with patch('provider_runtime.opener_for', return_value=transport), \
                patch('connection_capabilities.HttpControl.action', side_effect=AssertionError('Native fallback')):
            first = self.post(request)
            self.assertEqual(first['status'], 'outcome_unknown')
            self.assertEqual(self.post(request), first)
        self.assertEqual(transport.calls, 1)
        self.assertEqual(first['diagnostics'][0]['category'], 'timeout')
        self.assertNotIn('fixture-oauth-token', json.dumps(first))

    def test_full_chatgpt_research_publishes_in_hub_without_a_native_chat(self):
        project = self.registry.create('Example documentation')['id']
        knowledge = KnowledgeStore(self.registry, project)
        knowledge.changeset(0, 'fixture', [dict(op='put', item=dict(id='existing', kind='document',
            title='Existing guide', markdown='Existing source.', audience='user', section='guide',
            type='how-to', status='current', visibility='internal'))], 'Fixture')
        self.research_result = dict(schemaVersion=1, operation='documentation-draft', summary='Verified findings',
            evidence=[dict(kind='knowledge', id='existing', revision=1)], limitations=[],
            title='Example result', markdown='An explanation grounded in the selected document.', entityRefs=[])
        owner = self

        class Forwarder:
            def open(self, request, timeout):
                owner.assertEqual(request.full_url, 'https://api.openai.com/v1/responses')
                return owner.opener.open(Request('http://127.0.0.1:' + str(owner.peer.server_port) + '/responses',
                    data=request.data, headers=dict(request.header_items()), method=request.method), timeout=5)

        service = ApiAgentRuns(self.registry, HubActionContext(self.registry))
        self.addCleanup(service.close)
        environment = {key: value for key, value in os.environ.items() if not key.startswith('CODEX_')}
        with patch.dict(os.environ, environment, clear=True), \
                patch('subprocess.Popen', side_effect=AssertionError('Native process was started')), \
                patch('agent_launches.Launches.start', side_effect=AssertionError('Native launch was used')), \
                patch('connection_capabilities.HttpControl.action', side_effect=AssertionError('Native control was used')), \
                patch('provider_runtime.opener_for', return_value=Forwarder()):
            service.start_research(project, dict(operation='documentation-draft', objectId='existing', revision=1), 'independent')
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                result = json.loads(service.existing(project, 'independent')['body'])
                if result['status'] in ('completed', 'failed', 'outcome_unknown'):
                    break
                time.sleep(.01)
        self.assertEqual(result['status'], 'completed', result)
        self.assertFalse(result['nativeChat'])
        self.assertEqual(len(self.calls), 1)
        self.assertTrue(result['resultRef'].startswith('knowledge/document/'))
        self.assertEqual(knowledge.read(result['resultRef'].removeprefix('knowledge/document/'))['title'], 'Example result')
        self.assertNotIn('fixture-oauth-token', json.dumps(result))

    def test_identity_failure_stops_before_model_dispatch_and_preserves_the_receipt(self):
        from chatgpt_auth import AuthError
        request = self.probe()
        with patch('chatgpt_auth.ChatGPTAuth.access_token', side_effect=AuthError('chatgpt_identity_invalid')), \
                patch('provider_runtime.opener_for', side_effect=AssertionError('Model dispatch after identity failure')):
            result = self.post(request)
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['error']['code'], 'chatgpt_identity_invalid')
            self.assertEqual(result['diagnostics'], [])
            self.assertEqual(self.post(request), result)
        self.assertEqual(self.calls, [])


if __name__ == '__main__':
    unittest.main()
