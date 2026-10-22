"""No-model MCP fixtures, including independent private bridge restarts."""
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_stdio_client import Bridge, MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES
from mcp_transport import dispatch, LEGACY, MODERN, META_VERSION, META_CAPABILITIES


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.mode = None
        self.token = 'private-fixture-token'
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers['Content-Length']))
                message = json.loads(raw)
                owner.requests.append((self.path, message, dict(self.headers)))
                if owner.mode == 'slow':
                    time.sleep(.25)
                if owner.mode == 'bad':
                    status, body = 503, b'private-fixture-token invalid upstream'
                elif owner.mode == 'big':
                    status, body = 200, b' ' * (MAX_RESPONSE_BYTES + 1)
                elif owner.mode == 'echo':
                    status, body = 401, json.dumps(dict(jsonrpc='2.0', id=message['id'], error=dict(code=-33001, message=owner.token))).encode()
                else:
                    status, value = dispatch(None, message, self.headers, '# Fixture workflow')
                    body = b'' if value is None else json.dumps(value).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                try:
                    if owner.mode == 'slow-body':
                        self.wfile.write(body[:1])
                        self.wfile.flush()
                        time.sleep(.25)
                        body = body[1:]
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.connection = dict(baseUrl=f'http://127.0.0.1:{self.server.server_port}', token=self.token)
        authenticate = patch('mcp_transport.Connections')
        authenticate.start().return_value.authenticate.side_effect = self.authenticate
        self.addCleanup(authenticate.stop)
        tool_list = patch('mcp_transport.tools', return_value=[dict(name='hub_context', inputSchema=dict(type='object', required=['session']))])
        tool_list.start()
        self.addCleanup(tool_list.stop)
        tool_call = patch('mcp_transport.call', side_effect=lambda registry, token, tool, args, **kwargs: dict(project='fixture', session=args.get('session')))
        tool_call.start()
        self.addCleanup(tool_call.stop)

    def authenticate(self, token):
        self.assertEqual(token, self.token)

    def request(self, method='tools/list', params=None, identifier=1):
        message = dict(jsonrpc='2.0', method=method, params={} if params is None else params)
        if identifier is not None:
            message['id'] = identifier
        return message

    def serve(self, messages, *, timeout=2):
        outgoing, diagnostic = io.BytesIO(), io.StringIO()
        raw = b''.join(item if isinstance(item, bytes) else json.dumps(item).encode() + b'\n' for item in messages)
        Bridge(self.connection, timeout=timeout).serve(io.BytesIO(raw), outgoing, diagnostic)
        self.assertNotIn(self.token, outgoing.getvalue().decode())
        self.assertNotIn(self.token, diagnostic.getvalue())
        return [json.loads(line) for line in outgoing.getvalue().splitlines()], diagnostic.getvalue()

    def test_two_process_restarts_read_private_connection_without_environment(self):
        with tempfile.TemporaryDirectory() as temporary:
            connection = Path(temporary) / 'connection.json'
            connection.write_text(json.dumps(self.connection), encoding='utf-8')
            for session in ('new-chat-one', 'new-chat-two'):
                messages = [self.request('initialize', dict(protocolVersion=LEGACY[-1], capabilities={}, clientInfo=dict(name='fixture', version='1'))),
                            self.request('notifications/initialized', identifier=None),
                            self.request('tools/list', identifier=2),
                            self.request('tools/call', dict(name='hub_context', arguments={'session': session}), identifier=3)]
                completed = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'mcp_stdio_client.py'), '--connection', str(connection)],
                                           input=b''.join(json.dumps(item).encode() + b'\n' for item in messages), capture_output=True, timeout=10)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                replies = [json.loads(line) for line in completed.stdout.splitlines()]
                self.assertEqual(len(replies), 3)
                self.assertEqual(replies[0]['result']['protocolVersion'], LEGACY[-1])
                self.assertEqual(replies[2]['result']['structuredContent']['session'], session)
                self.assertNotIn(self.token.encode(), completed.stdout + completed.stderr)
            self.assertEqual(len(self.requests), 8)
            self.assertTrue(all(path == '/mcp' and headers['Authorization'] == 'Bearer ' + self.token for path, message, headers in self.requests))

    def test_modern_metadata_headers_and_session_unchanged(self):
        params = dict(name='hub_context', arguments={'session': 'caller-session'},
                      _meta={META_VERSION: MODERN, META_CAPABILITIES: {}})
        replies, diagnostics = self.serve([self.request('tools/call', params)])
        self.assertEqual(replies[0]['result']['structuredContent']['session'], 'caller-session')
        self.assertEqual(self.requests[0][1]['params'], params)
        self.assertEqual(self.requests[0][2]['Mcp-Method'], 'tools/call')
        self.assertEqual(diagnostics, '')

    def test_hub_protocol_error_and_tool_error_are_not_transport_failures(self):
        replies, diagnostics = self.serve([self.request('unknown/method'), self.request('tools/call', dict(name='missing'))])
        self.assertEqual([reply['error']['code'] for reply in replies], [-32601, -32602])
        self.assertEqual(diagnostics, '')
        with patch('mcp_transport.call', side_effect=ValueError('fixture bad arguments')):
            replies, diagnostics = self.serve([self.request('tools/call', dict(name='hub_context', arguments={}))])
        self.assertTrue(replies[0]['result']['isError'])
        self.assertIn('invalid_arguments', replies[0]['result']['content'][0]['text'])
        self.assertEqual(diagnostics, '')

    def test_invalid_input_is_local_and_next_request_survives(self):
        replies, _ = self.serve([b'{bad\n', b'[]\n', self.request(params=[]), b'{"jsonrpc":"2.0","id":1,"id":2,"method":"ping"}\n',
                                b'x' * (MAX_REQUEST_BYTES + 1) + b'\n', self.request('ping')])
        self.assertEqual(replies[0]['error']['code'], -32700)
        self.assertEqual(replies[1]['error']['code'], -32600)
        self.assertEqual(replies[2]['error']['code'], -32602)
        self.assertEqual(replies[3]['error']['code'], -32700)
        self.assertEqual(replies[4]['error']['code'], -32600)
        self.assertEqual(replies[-1]['result'], {})
        self.assertEqual(len(self.requests), 1)

    def test_notifications_do_not_reply_including_errors(self):
        replies, _ = self.serve([self.request('unknown/notification', identifier=None)])
        self.assertEqual(replies, [])

    def test_transport_bounds_redaction_and_no_retry(self):
        for mode in ('bad', 'big', 'slow', 'slow-body', 'echo'):
            with self.subTest(mode=mode):
                self.mode = mode
                count = len(self.requests)
                replies, _ = self.serve([self.request('tools/call', dict(name='hub_context', arguments={'session': 'caller'}))], timeout=.05 if mode.startswith('slow') else 2)
                self.assertEqual(len(self.requests), count + 1)
                self.assertIn('error', replies[0])
                if mode == 'echo':
                    self.assertEqual(replies[0]['error']['code'], -33001)
                    self.assertEqual(replies[0]['error']['message'], '[redacted]')

    def test_missing_session_and_nonfinite_numbers_never_invent_identity(self):
        replies, _ = self.serve([self.request('tools/call', dict(name='hub_context', arguments={})),
                                b'{"jsonrpc":"2.0","id":1e999,"method":"ping"}\n'])
        self.assertEqual(self.requests[0][1]['params']['arguments'], {})
        self.assertIsNone(replies[0]['result']['structuredContent']['session'])
        self.assertEqual(replies[1]['error']['code'], -32700)

    def test_private_startup_error_has_no_path_or_token_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            connection = Path(temporary) / 'secret-fixture.json'
            connection.write_text(json.dumps(dict(self.connection, token=None)))
            completed = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'mcp_stdio_client.py'), '--connection', str(connection)], capture_output=True, timeout=10)
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(completed.stdout, b'')
            self.assertNotIn(str(connection).encode(), completed.stderr)
            self.assertNotIn(self.token.encode(), completed.stderr)


if __name__ == '__main__':
    unittest.main()
