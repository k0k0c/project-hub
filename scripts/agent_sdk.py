"""Dependency-free client for the loopback Project Hub agent API."""
import base64
import hashlib
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 1_000_000
MAX_AGENT_REQUEST_BYTES = 1_000_000
MAX_CONNECTION_BYTES = 1_000_000


def mcp_server_name(connection):
    """One credential-free stable name shared by CLI and native rules."""
    project, binding = connection.get('project'), connection.get('binding', '')
    if not isinstance(binding, str) or not binding or (project is not None and (not isinstance(project,str) or not project)):
        raise ValueError('an enrolled connection binding is required')
    return 'project_hub_' + hashlib.sha256(((project or 'global') + '\0' + binding).encode()).hexdigest()[:16]


class SDKError(Exception):
    def __init__(self, message, *, status=None, code=None, outcomeUnknown=False):
        super().__init__(message)
        self.status, self.code, self.outcomeUnknown = status, code, outcomeUnknown


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, new):
        return None


def _base_url(value):
    if not isinstance(value, str):
        raise ValueError('base URL must be a string')
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('base URL must use loopback HTTP')
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('base URL cannot contain credentials, query, fragment, or path')
    return f'http://{parsed.hostname}' + (f':{parsed.port}' if parsed.port else '')


def mcp_http_endpoint(base_url):
    """Native clients use the reserved loopback hostname, without proxy hacks."""
    parsed = urllib.parse.urlsplit(_base_url(base_url))
    return 'http://localhost' + (f':{parsed.port}' if parsed.port else '') + '/mcp'


def _absolute_path(value):
    path = Path(value) if isinstance(value, (str, os.PathLike)) else None
    if path is None or not path.is_absolute():
        raise ValueError('connection path must be absolute')
    from hub_launcher import external_path
    return external_path(path)


def save_connection(path, connection):
    path = _absolute_path(path)
    if not isinstance(connection, dict):
        raise ValueError('connection must be an object')
    data = {key: value for key, value in connection.items() if key != 'session'}
    Client(data.get('baseUrl'), data.get('token'))
    if not data.get('token'):
        raise ValueError('an enrolled connection token is required')
    stored = data
    if os.name=='nt':
        from secret_vault import _protect
        stored = {key:value for key,value in data.items() if key!='token'}
        stored.update(credentialProtection='windows-dpapi',
                      protectedToken=base64.b64encode(_protect(data['token'].encode())).decode('ascii'))
    encoded = json.dumps(stored, ensure_ascii=False, sort_keys=True) + '\n'
    if len(encoded.encode('utf-8')) > MAX_CONNECTION_BYTES:
        raise ValueError('connection file exceeds supported size')
    if path.exists():
        if load_connection(path) == data:
            return path
        raise ValueError('connection file already exists with different content; select a separate private file')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f'{path.name}.tmp-{uuid.uuid4().hex}')
    try:
        with temp.open('x', encoding='utf-8') as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o600)
        # Publish without replacing a concurrent or unrelated private file.
        os.link(temp, path)
        temp.unlink()
    except Exception:
        try:
            os.unlink(temp)
        except OSError:
            pass
        raise
    return path


def load_connection(path):
    path = _absolute_path(path)
    with path.open('rb') as handle:
        raw = handle.read(MAX_CONNECTION_BYTES + 1)
        if len(raw)>MAX_CONNECTION_BYTES:raise ValueError('connection file exceeds supported size')
        data = json.loads(raw)
    if isinstance(data,dict) and 'credentialProtection' in data:
        if data.get('credentialProtection')!='windows-dpapi' or os.name!='nt' or 'token' in data:
            raise ValueError('private connection requires its original Windows user environment')
        from secret_vault import _protect
        try:
            protected = base64.b64decode(data.pop('protectedToken'),validate=True)
            data['token'] = _protect(protected,True).decode('utf-8')
            data.pop('credentialProtection')
        except (KeyError,ValueError,UnicodeError):
            raise ValueError('private connection credential is invalid') from None
    if not isinstance(data, dict) or not isinstance(data.get('token'), str) or not isinstance(data.get('baseUrl'), str):
        raise ValueError('invalid connection file')
    _base_url(data['baseUrl'])
    return data


class Client:
    def __init__(self, baseUrl, token=None, *, timeout=10, opener=None, session=None, project=None, workspace=None):
        self.baseUrl = _base_url(baseUrl)
        self.token = token
        self.timeout = timeout
        self.session = str(uuid.uuid4()) if session is None else session
        self.project,self.workspace = project,workspace
        if project is not None and (not isinstance(project,str) or not project.strip() or len(project)>128 or any(ord(c)<32 for c in project)):
            raise ValueError('project must be an explicit registered project ID')
        if workspace is not None and (not isinstance(workspace,str) or not workspace or any(ord(c)<32 for c in workspace)):
            raise ValueError('workspace must be an explicit server code folder')
        if not isinstance(self.session,str) or not self.session.strip() or len(self.session)>128 or any(ord(c)<32 for c in self.session):
            raise ValueError('session must be your nonempty current conversation ID')
        if token is not None and (not isinstance(token,str) or not token or len(token)>128 or any(ord(c)<33 for c in token)):
            raise ValueError('invalid connection token')
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirects())

    def _request(self, route, *, method='GET', body=None, credential=False, mutating=False):
        headers = {'Accept': 'application/json'}
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode()
            headers['Content-Type'] = 'application/json'
            limit = 28_000_000 if route == '/api/v1/agent/artifacts' else MAX_AGENT_REQUEST_BYTES if route == '/api/v1/agent/call' else 16_000
            if len(payload)>limit:raise ValueError('request exceeds supported route size')
        if credential:
            if not self.token:
                raise SDKError('connection token is required', code='connection_required')
            headers['Authorization'] = f'Bearer {self.token}'
        request = urllib.request.Request(self.baseUrl + route, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES+1)
                if len(raw)>MAX_RESPONSE_BYTES:
                    raise SDKError('response exceeds supported size',code='invalid_response',outcomeUnknown=bool(mutating))
                if not raw:
                    raise SDKError('Hub returned an empty acknowledgement', code='invalid_response', outcomeUnknown=bool(mutating))
                result = json.loads(raw.decode('utf-8'))
                if not isinstance(result,dict):
                    raise SDKError('response must be an object',code='invalid_response',outcomeUnknown=bool(mutating))
                return result
        except urllib.error.HTTPError as error:
            try:
                result = json.loads(error.read(MAX_RESPONSE_BYTES).decode('utf-8'))
            except Exception:
                result = {}
            if not isinstance(result,dict):result={}
            raise SDKError(result.get('message') or result.get('error') or f'HTTP {error.code}', status=error.code,
                code=result.get('code') or result.get('error'),outcomeUnknown=bool(mutating and error.code>=500)) from error
        except (urllib.error.URLError, TimeoutError, socket.timeout, OSError) as error:
            raise SDKError('Hub connection interrupted; read back before retrying a mutation', code='network_failure', outcomeUnknown=bool(mutating)) from error
        except (UnicodeError,json.JSONDecodeError):
            raise SDKError('Hub returned an invalid acknowledgement',code='invalid_response',outcomeUnknown=bool(mutating)) from None

    def connect(self, invitation):
        if not isinstance(invitation, str) or not invitation or '/' in invitation or '?' in invitation or '#' in invitation:
            raise ValueError('invitation must be one path segment')
        return self._request('/connect/' + urllib.parse.quote(invitation, safe=''))

    def enroll(self, invitation, client, externalId, *, workspace=None, name=None, roots=None,
               model=None, session=None, chat=None, metadata=None):
        body = {'invitation': invitation, 'client': client, 'externalId': externalId}
        if workspace is not None: body['workspace'] = workspace
        if name is not None: body['name'] = name
        if roots is not None: body['roots'] = list(roots)
        for key,value in (('model',model),('session',session),('chat',chat),('metadata',metadata)):
            if value is not None: body[key]=value
        return self._request('/api/v1/agent/enroll', method='POST', body=body, mutating=True)

    def call(self, tool, arguments=None):
        arguments = dict(arguments or {})
        if 'session' in arguments and arguments['session'] != self.session:
            raise ValueError('call arguments cannot override the client session')
        arguments['session'] = self.session
        if tool not in ('hub_projects', 'hub_connection','hub_instructions','hub_project_bindings','hub_launch'):
            if self.project is not None: arguments.setdefault('project',self.project)
            if self.workspace is not None: arguments.setdefault('workspace',self.workspace)
        return self._request('/api/v1/agent/call', method='POST', body={'tool': tool, 'arguments': arguments}, credential=True, mutating=True)

    def upload(self, name, content, *, roles=None, previous=None, project=None, workspace=None):
        if not isinstance(content, (bytes, bytearray, memoryview)):
            raise TypeError('artifact content must be bytes')
        content = bytes(content)
        if len(content) > MAX_ARTIFACT_BYTES:
            raise ValueError('artifact exceeds bounded upload size')
        body = {'name': name, 'content': base64.b64encode(content).decode('ascii')}
        if roles is not None: body['roles'] = roles
        if previous is not None: body['previous'] = previous
        for key,value in (('project',project if project is not None else self.project),
                          ('workspace',workspace if workspace is not None else self.workspace)):
            if value is not None: body[key]=value
        return self._request('/api/v1/agent/artifacts', method='POST', body=body, credential=True, mutating=True)


def generic_mcp_config(base_url, token=None, name='project_hub'):
    server = {'url': mcp_http_endpoint(base_url)}
    if token is not None:
        if not isinstance(token, str) or not token:
            raise ValueError('token must be a nonempty string')
        server['headers'] = {'Authorization': 'Bearer ' + token}
    return {'mcpServers': {name: server}}
