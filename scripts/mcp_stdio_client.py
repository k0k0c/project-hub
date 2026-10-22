"""Credential-private, newline JSON-RPC bridge to the local Hub MCP endpoint.

Conversation identity belongs to tools/call arguments, never this process.
There are no transport retries, including after an uncertain write outcome.
"""
import argparse
import base64
import http.client
import json
import math
import socket
import sys
import threading

from urllib.parse import urlsplit

from agent_sdk import _base_url, load_connection
from mcp_transport import LEGACY, META_VERSION, ProtocolError, error, protocol

MAX_REQUEST_BYTES = 256_000
MAX_RESPONSE_BYTES = 4_000_000


class BridgeError(ValueError):
    pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field')
        result[key] = value
    return result


def _json(raw):
    def finite(number):
        value = float(number)
        if not math.isfinite(value):
            raise ValueError('Invalid JSON number')
        return value

    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_float=finite,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Invalid JSON number')))


def _redact(value, token):
    if isinstance(value, str):
        return value.replace(token, '[redacted]')
    if isinstance(value, list):
        return [_redact(item, token) for item in value]
    if isinstance(value, dict):
        return {_redact(key, token): _redact(item, token) for key, item in value.items()}
    return value


class Bridge:
    def __init__(self, connection, *, timeout=20):
        token = connection.get('token')
        if not isinstance(token, str) or not token or len(token) > 128 or any(ord(char) < 33 for char in token):
            raise BridgeError('An enrolled credential is required')
        if not isinstance(timeout, (int, float)) or not 0 < timeout <= 60:
            raise BridgeError('Timeout must be greater than zero and at most 60 seconds')
        self.base_url, self.token = _base_url(connection.get('baseUrl')), token
        self.timeout = timeout
        self.version = LEGACY[0]

    def forward(self, message):
        headers = {'Accept': 'application/json, text/event-stream',
                   'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.token}
        params = message.get('params', {}) if isinstance(message, dict) else {}
        meta = params.get('_meta', {}) if isinstance(params, dict) else {}
        version = meta.get(META_VERSION) if isinstance(meta, dict) else None
        headers['MCP-Protocol-Version'] = version if version is not None else self.version
        if version is not None:
            headers['Mcp-Method'] = message.get('method', '')
            if message.get('method') in ('tools/call', 'resources/read', 'prompts/get'):
                name = params.get('uri') if message['method'] == 'resources/read' else params.get('name')
                if isinstance(name, str):
                    headers['Mcp-Name'] = '=?base64?' + base64.b64encode(name.encode()).decode() + '?='
        # Reuse the Hub's exact request contract, without injecting metadata/session.
        protocol(message, {key.lower(): value for key, value in headers.items()})
        payload = json.dumps(message, ensure_ascii=False, allow_nan=False).encode('utf-8')
        if len(payload) > MAX_REQUEST_BYTES:
            raise BridgeError('Request exceeds the supported size')
        target = urlsplit(self.base_url)
        connection = http.client.HTTPConnection(target.hostname, target.port, timeout=self.timeout)
        deadline = None
        active_socket = None
        expired = threading.Event()
        try:
            def interrupt():
                expired.set()
                current_socket = active_socket or connection.sock
                if current_socket is not None:
                    try:
                        current_socket.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass

            deadline = threading.Timer(self.timeout, interrupt)
            deadline.daemon = True
            deadline.start()
            connection.request('POST', '/mcp', body=payload, headers=headers)
            active_socket = connection.sock
            if expired.is_set():
                raise BridgeError('Transport timeout; outcome may be unknown')
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if expired.is_set():
                raise BridgeError('Transport timeout; outcome may be unknown')
            if len(raw) > MAX_RESPONSE_BYTES:
                raise BridgeError('Response exceeds the supported size')
            # Notifications never produce an outbound JSON-RPC response.
            if 'id' not in message:
                return None
            if response.getheader('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
                raise BridgeError('Expected a JSON MCP response')
            try:
                body = _json(raw.decode('utf-8'))
            except (ValueError, UnicodeError, RecursionError):
                raise BridgeError('Invalid JSON MCP response') from None
            if (not isinstance(body, dict) or body.get('jsonrpc') != '2.0' or
                    type(body.get('id')) != type(message['id']) or body.get('id') != message['id'] or
                    ('result' in body) == ('error' in body)):
                raise BridgeError('Invalid JSON-RPC MCP response')
            if message['method'] == 'initialize' and isinstance(body.get('result'), dict):
                selected = body['result'].get('protocolVersion')
                if selected in LEGACY:
                    self.version = selected
            return _redact(body, self.token)
        except (OSError, http.client.HTTPException):
            raise BridgeError('Transport unavailable; outcome may be unknown') from None
        finally:
            if deadline is not None:
                deadline.cancel()
            connection.close()

    def serve(self, incoming, outgoing, diagnostics):
        while True:
            raw = incoming.readline(MAX_REQUEST_BYTES + 1)
            if not raw:
                return
            message = None
            try:
                if len(raw) > MAX_REQUEST_BYTES:
                    # Drain this one invalid line with bounded memory before continuing.
                    while raw and not raw.endswith(b'\n'):
                        raw = incoming.readline(MAX_REQUEST_BYTES + 1)
                    raise ProtocolError(-32600, 'Request exceeds the supported size')
                try:
                    message = _json(raw.decode('utf-8'))
                except (ValueError, UnicodeError, RecursionError):
                    raise ProtocolError(-32700, 'Invalid JSON') from None
                body = self.forward(message)
            except ProtocolError as failure:
                identifier = message.get('id') if isinstance(message, dict) else None
                # Invalid IDs must not be echoed, especially arbitrary large objects.
                if type(identifier) not in (str, int, float):
                    identifier = None
                body = error(identifier, failure.code, str(failure))
            except (BridgeError, ValueError, RecursionError):
                identifier = message.get('id') if isinstance(message, dict) else None
                body = error(identifier, -32000, 'MCP transport failed; outcome may be unknown. No automatic retry.')
                diagnostics.write('project-hub MCP bridge: transport failure (details redacted)\n')
                diagnostics.flush()
            if isinstance(message, dict) and 'id' not in message and isinstance(message.get('method'), str):
                body = None
            if body is not None:
                outgoing.write(json.dumps(_redact(body, self.token), ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n')
                outgoing.flush()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Private local Project Hub STDIO MCP bridge')
    parser.add_argument('--connection', required=True, help='Absolute private SDK connection file')
    parser.add_argument('--timeout', type=float, default=20)
    args = parser.parse_args(argv)
    try:
        bridge = Bridge(load_connection(args.connection), timeout=args.timeout)
        bridge.serve(sys.stdin.buffer, sys.stdout.buffer, sys.stderr)
    except (ValueError, OSError, http.client.HTTPException, RecursionError):
        print('project-hub MCP bridge: startup or stream failure (details redacted)', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
