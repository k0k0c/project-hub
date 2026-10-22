"""Bounded client descriptions and explicit HTTP/MCP capability probes.

Descriptions are assertions, not authorization or proof. Only administrator-
configured endpoints can be contacted. No subprocess, stdin or shell transport
is supported. Probe callbacks have one purpose and confer no project access.
"""
from concurrent.futures import ThreadPoolExecutor
import base64
import datetime
import hashlib
import hmac
import json
import math
import secrets
import threading
import time
from urllib.parse import quote, urlsplit, urljoin
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from agent_bindings import BindingError, fingerprint, text
from native_chats import normalize, open_uri, template_uri
from outbound_http import OutboundError, json_request, opener_for
from task_transfer import barrier


TIMEOUT = 90
_MANAGER_LOCK = threading.Lock()
_FIELDS = {'schemaVersion', 'clientVersion', 'clientInstance', 'host', 'model', 'projectContext',
           'nativeChat', 'capabilities', 'control', 'persistentInstructions'}
CONTROL_ERROR_CODES = frozenset((
    'hub_bindings_unavailable', 'hub_project_binding_missing', 'hub_project_binding_ambiguous',
    'hub_project_binding_changed', 'native_project_missing', 'native_project_ambiguous',
    'native_catalog_unavailable', 'native_chat_not_visible_in_project', 'chat_not_owned',
    'codex_host_unavailable', 'codex_host_rejected', 'codex_outcome_unknown',
    'codex_protocol_changed', 'prior_outcome_requires_reconciliation', 'request_id_conflict'))


def probe_failure(error, phase):
    """Publish fixed identifiers only; remote messages may contain credentials."""
    result = dict(code='control_invalid_response', phase=phase, outcomeUnknown=True)
    if isinstance(error, BindingError):
        result.update(code='hub_project_binding_changed', outcomeUnknown=False)
    if isinstance(error, OutboundError):
        diagnostic = error.diagnostic
        code = diagnostic.get('controlErrorCode')
        if code == 'request_id_conflict':
            code = 'prior_outcome_requires_reconciliation'
        if code not in CONTROL_ERROR_CODES:
            category = diagnostic.get('category')
            code = ('control_auth_failed' if diagnostic.get('httpStatus') in (401, 403) else
                    'control_timeout' if category == 'timeout' else
                    'control_endpoint_unavailable' if category in ('connect', 'dns', 'tls') else
                    'control_http_error' if 'httpStatus' in diagnostic else 'control_invalid_response')
        result.update(code=code, outcomeUnknown=bool(diagnostic.get('outcomeUnknown')))
        if code in CONTROL_ERROR_CODES:
            result['outcomeUnknown'] = code in ('codex_outcome_unknown', 'codex_protocol_changed',
                'native_chat_not_visible_in_project', 'prior_outcome_requires_reconciliation')
        if type(diagnostic.get('httpStatus')) is int:
            result['httpStatus'] = diagnostic['httpStatus']
    return result


def visibility_evidence(visibility, native_id, project, scope):
    """Validate adapter evidence without equating native and Hub project IDs."""
    if visibility is None:
        return None
    allowed = {'nativeId','workspace','method','state','projectId','verifiedAt','guiOpened'}
    if not isinstance(visibility, dict) or not {'nativeId','workspace','method','state'} <= set(visibility) or set(visibility) - allowed:
        raise ValueError('The control adapter returned invalid visibility evidence')
    if visibility['nativeId'] != native_id or visibility['method'] not in ('codex_app.list_threads', 'codex_app.read_thread+list_threads') or visibility['state'] != 'verified':
        raise ValueError('The control adapter returned unverified visibility evidence')
    if 'projectId' in visibility and (not isinstance(visibility['projectId'], str) or not visibility['projectId'] or len(visibility['projectId']) > 256):
        raise ValueError('The control adapter returned an invalid native project ID')
    if 'verifiedAt' in visibility:
        if not isinstance(visibility['verifiedAt'], str) or len(visibility['verifiedAt']) > 128:
            raise ValueError('The control adapter returned an invalid visibility timestamp')
        datetime.datetime.fromisoformat(visibility['verifiedAt'].replace('Z', '+00:00'))
    if 'guiOpened' in visibility and visibility['guiOpened'] is not False:
        raise ValueError('The control adapter cannot claim that a GUI window opened')
    from pathlib import Path
    if not scope.get('root') or not isinstance(visibility['workspace'], str) or Path(visibility['workspace']).resolve() != Path(scope['root']).resolve():
        raise ValueError('The control adapter returned visibility for a different workspace')
    return dict(visibility, provenance='control-adapter', project=project)


def endpoint(value):
    value = text(value, 'endpoint', 2000)
    parsed = urlsplit(value)
    if (parsed.scheme not in ('https', 'http') or not parsed.hostname or
            parsed.username or parsed.password or parsed.query or parsed.fragment or
            '\\' in value or any(ch in value for ch in '\"<>') or
            parsed.scheme == 'http' and parsed.hostname.lower() not in ('localhost', '127.0.0.1', '::1')):
        raise BindingError('invalid_control_endpoint', 'Use HTTPS or a loopback HTTP endpoint without credentials, query or fragment')
    try:
        parsed.port
    except ValueError:
        raise BindingError('invalid_control_endpoint', 'Invalid endpoint port') from None
    return value.rstrip('/')


def validate_profile(value):
    if not isinstance(value, dict) or set(value) - _FIELDS or value.get('schemaVersion') != 1:
        raise BindingError('invalid_connection_profile', 'Use the published schemaVersion 1 profile without credentials or commands')
    try:
        encoded = json.dumps(value, allow_nan=False)
    except (ValueError, TypeError):
        raise BindingError('invalid_connection_profile', 'Use a JSON profile') from None
    if len(encoded) > 24000:
        raise BindingError('invalid_connection_profile', 'Profile exceeds the supported size')
    result = {'schemaVersion': 1}
    if 'projectContext' in value:
        context = value['projectContext']
        if (not isinstance(context,dict) or set(context)-{'kind','identification','projectInstructions','globalInstructions'} or
            context.get('kind') not in ('repository','workspace','project') or context.get('identification') not in ('root','native-ref','both') or
            any(type(context.get(key)) is not bool for key in ('projectInstructions','globalInstructions'))):
            raise BindingError('invalid_connection_profile','Describe project context and native instruction support')
        result['projectContext'] = dict(context)
    for key in ('clientVersion', 'clientInstance', 'host', 'model'):
        if key in value and value[key] is not None:
            result[key] = text(value[key], key, 256)
    capabilities = value.get('capabilities', {})
    if not isinstance(capabilities, dict) or set(capabilities) - {'openChat', 'createChat', 'sendMessage'}:
        raise BindingError('invalid_connection_profile', 'Describe openChat, createChat or sendMessage capabilities')
    result['capabilities'] = {}
    for name, action in capabilities.items():
        if action is None or action is False:
            continue
        allowed = {'uriTemplate'} if name == 'openChat' else {'tool', 'arguments', 'path', 'method', 'idField', 'uriField','projectRouting','timeoutSeconds'}
        if not isinstance(action, dict) or set(action) - allowed:
            raise BindingError('invalid_connection_profile', 'Use declarative HTTP/MCP action fields')
        item = dict(action)
        for key in set(item) - {'arguments','projectRouting','timeoutSeconds'}:
            item[key] = text(item[key], key, 2000 if key == 'uriTemplate' else 256)
        if 'projectRouting' in item and type(item['projectRouting']) is not bool:
            raise BindingError('invalid_connection_profile','Project routing is a boolean capability declaration')
        if 'timeoutSeconds' in item:
            timeout = item['timeoutSeconds']
            if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0 or timeout > 60:
                raise BindingError('invalid_connection_profile', 'Action timeoutSeconds must be a finite number between 0 and 60')
        if name == 'openChat' and item.get('uriTemplate'):
            template_uri(item['uriTemplate'], '00000000-0000-4000-8000-000000000000')
        if 'arguments' in item and not isinstance(item['arguments'], dict):
            raise BindingError('invalid_connection_profile', 'Action arguments must be a JSON object')
        def check_arguments(arguments, depth=0):
            if depth > 12:
                raise BindingError('invalid_connection_profile', 'Action arguments are nested too deeply')
            if isinstance(arguments, dict):
                for key, literal in arguments.items():
                    compact = str(key).replace('_', '').replace('-', '').casefold()
                    if compact in ('apikey', 'key', 'token', 'bearertoken', 'authorization', 'password', 'secret', 'credentials', 'headers', 'command', 'cmd', 'script'):
                        raise BindingError('invalid_connection_profile', 'Keep credentials and executable commands out of the profile')
                    check_arguments(literal, depth + 1)
            elif isinstance(arguments, list):
                for literal in arguments:
                    check_arguments(literal, depth + 1)
            elif isinstance(arguments, str) and arguments.startswith('Bearer '):
                raise BindingError('invalid_connection_profile', 'Keep credentials out of the profile')
        check_arguments(item.get('arguments', {}))
        if item.get('method', 'POST') not in ('GET', 'POST'):
            raise BindingError('invalid_connection_profile', 'Use GET or POST')
        if 'path' in item:
            path = item['path']
            if not path.startswith('/') or path.startswith('//') or '\\' in path or any(ch in path for ch in ('?', '#')) or '..' in path.split('/'):
                raise BindingError('invalid_connection_profile', 'Use an absolute path on the configured endpoint')
        # Parameters are literals or named placeholders, never executable code.
        result['capabilities'][name] = item
    if value.get('nativeChat'):
        result['nativeChat'] = normalize(value['nativeChat'],
            uri_template=result['capabilities'].get('openChat', {}).get('uriTemplate'))
    if value.get('control'):
        control = value['control']
        if not isinstance(control, dict) or set(control) != {'protocol', 'endpoint'} or control['protocol'] not in ('mcp-http', 'http-json'):
            raise BindingError('invalid_connection_profile', 'Use mcp-http or http-json control metadata')
        result['control'] = dict(protocol=control['protocol'], endpoint=endpoint(control['endpoint']))
    if value.get('persistentInstructions'):
        rules = value['persistentInstructions']
        if (not isinstance(rules, dict) or set(rules) - {'scope', 'destination', 'consent', 'revision', 'status','manifestPath','loadVerified','compactionVerified','bootstrapSha256','connectionId'} or
                rules.get('scope') not in ('project', 'application') or rules.get('status') not in ('saved', 'manual') or
                type(rules.get('consent')) is not bool):
            raise BindingError('invalid_connection_profile', 'Report the rule destination, scope and existing user authorization')
        if rules['status'] == 'saved' and not rules['consent']:
            raise BindingError('instructions_consent_required', 'Saving persistent rules requires the user\'s setup authorization')
        result['persistentInstructions'] = dict(rules, verification='client-reported')
        if any(key in rules and type(rules[key]) is not bool for key in ('loadVerified','compactionVerified')):
            raise BindingError('invalid_connection_profile','Instruction verification claims must be booleans')
        for key in ('destination', 'revision','manifestPath','bootstrapSha256','connectionId'):
            if key in rules:
                result['persistentInstructions'][key] = text(rules[key], key, 2000)
    return result


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        # Never forward credentials to a different location supplied by a peer.
        return None


class HttpControl:
    """A bounded, redirect-free HTTP client; HTTP MCP includes initialization."""
    def __init__(self, config, credential=None):
        self.config, self.credential, self.session = config, credential, None
        self.version = '2026-07-28'
        self.counter = 0
        self.opener = opener_for(config['endpoint'], 'system')
        self.diagnostics, self.observer = [], None

    def observe(self, value):
        self.diagnostics = [item for item in self.diagnostics if item['requestId'] != value['requestId']][-31:] + [value]
        if self.observer:
            self.observer(list(self.diagnostics))

    def request(self, body, path=None, method='POST', timeout=12):
        target = self.config['endpoint']
        if path is not None:
            base = urlsplit(target)
            target = urljoin(target, path)
            actual = urlsplit(target)
            if (actual.scheme, actual.netloc) != (base.scheme, base.netloc):
                raise BindingError('invalid_control_endpoint', 'Control requests must stay on the configured origin')
        headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream'}
        if self.credential:
            headers['Authorization'] = 'Bearer ' + self.credential
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        if self.config['protocol'] == 'mcp-http':
            headers['MCP-Protocol-Version'] = self.version
            if self.version == '2026-07-28':
                headers['Mcp-Method'] = body['method']
                if body['method'] in ('tools/call', 'resources/read', 'prompts/get'):
                    name = body.get('params', {}).get('uri' if body['method'] == 'resources/read' else 'name', '')
                    headers['Mcp-Name'] = name if name.isascii() else '=?base64?' + base64.b64encode(name.encode()).decode('ascii') + '?='
        data = None if method == 'GET' else json.dumps(body).encode('utf-8')
        value, response_headers = json_request(Request(target, data=data, headers=headers, method=method),
            opener=self.opener, timeout=timeout, limit=262144, network_mode='system', operation='client-control',
            observer=self.observe, allow_empty=True, sse_id=body.get('id') if isinstance(body,dict) else None,
            error_codes=CONTROL_ERROR_CODES)
        if response_headers.get('Mcp-Session-Id'):
            self.session = response_headers['Mcp-Session-Id']
        return value

    def rpc(self, method, params, notification=False, timeout=12):
        self.counter += 1
        if self.version == '2026-07-28':
            params = dict(params, _meta={'io.modelcontextprotocol/protocolVersion': self.version,
                                        'io.modelcontextprotocol/clientCapabilities': {}})
        request = dict(jsonrpc='2.0', method=method, params=params)
        if not notification:
            request['id'] = self.counter
        value = self.request(request, timeout=timeout)
        if notification:
            return {}
        if not isinstance(value, dict) or value.get('id') != self.counter or value.get('error'):
            raise ValueError('The control endpoint rejected the MCP request')
        return value.get('result', {})

    def discover(self):
        try:
            result = self.rpc('server/discover', {})
            if '2026-07-28' not in result.get('supportedVersions', []):
                raise ValueError('The stateless protocol is not supported')
        except (ValueError, HTTPError, OutboundError) as failure:
            if isinstance(failure, HTTPError) and failure.code not in (400, 404, 405, 406, 415, 422):
                raise
            if isinstance(failure, OutboundError) and failure.diagnostic.get('httpStatus') not in (400,404,405,406,415,422):
                raise
            self.version = '2025-03-26'
            result = self.rpc('initialize', dict(protocolVersion=self.version, capabilities={},
                             clientInfo=dict(name='project-hub', version='1')))
            if not isinstance(result, dict) or result.get('protocolVersion') not in ('2025-03-26', '2025-06-18', '2025-11-25'):
                raise ValueError('Unsupported MCP protocol version')
            self.version = result['protocolVersion']
            self.rpc('notifications/initialized', {}, notification=True)
        tools, cursor = set(), None
        for page in range(4):
            listing = self.rpc('tools/list', {'cursor': cursor} if cursor else {})
            tools.update(tool['name'] for tool in listing.get('tools', []) if isinstance(tool, dict) and isinstance(tool.get('name'), str))
            cursor = listing.get('nextCursor')
            if not cursor:
                return tools
        raise ValueError('MCP discovery exceeds the supported page limit')

    def action(self, spec, variables):
        def substitute(value, depth=0):
            if depth > 12:
                raise ValueError('Action arguments are nested too deeply')
            if isinstance(value, str) and value.startswith('$'):
                if value not in variables:
                    raise ValueError('Unknown action placeholder')
                return variables[value]
            if isinstance(value, dict):
                return {key: substitute(item, depth + 1) for key, item in value.items()}
            if isinstance(value, list):
                return [substitute(item, depth + 1) for item in value]
            return value
        arguments = substitute(spec.get('arguments', {}))
        if self.config['protocol'] == 'mcp-http':
            result = self.rpc('tools/call', dict(name=spec['tool'], arguments=arguments), timeout=spec.get('timeoutSeconds', 12))
            if result.get('isError'):
                raise ValueError('The MCP tool rejected the probe')
            if isinstance(result.get('structuredContent'), dict):
                return result['structuredContent']
            for item in result.get('content', []):
                if item.get('type') == 'text':
                    try:
                        value = json.loads(item['text'])
                    except (ValueError, KeyError):
                        continue
                    if isinstance(value, dict):
                        return value
            return {}
        return self.request(arguments, path=spec['path'], method=spec.get('method', 'POST'), timeout=spec.get('timeoutSeconds', 12))


class Profiles:
    def __init__(self, registry):
        self.registry = registry

    def setup(self):
        with self.registry.connect() as c:
            c.executescript('''CREATE TABLE IF NOT EXISTS connection_profiles(
                binding TEXT PRIMARY KEY,body TEXT NOT NULL,revision TEXT NOT NULL,updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS connection_controls(
                binding TEXT PRIMARY KEY,body TEXT NOT NULL,updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS connection_probes(
                id TEXT PRIMARY KEY,binding TEXT NOT NULL,revision TEXT NOT NULL,body TEXT NOT NULL,
                nonce_hash TEXT NOT NULL,deadline REAL NOT NULL,updated REAL NOT NULL);''')

    def _read(self, table, identifier, column='binding'):
        with self.registry.connect() as c:
            if not c.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
                return None
            row = c.execute('SELECT * FROM ' + table + ' WHERE ' + column + '=?', (identifier,)).fetchone()
        return dict(row) if row else None

    def binding(self, identifier, *, allow_revoked=False):
        identifier = text(identifier, 'connection ID')
        with self.registry.connect() as c:
            tables = {row[0] for row in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            row = c.execute('SELECT id,client,revoked,last_seen FROM agent_connections WHERE id=?', (identifier,)).fetchone() if 'agent_connections' in tables else None
            if row is None and 'agent_access' in tables:
                row = c.execute('SELECT b.id,b.client,a.revoked,NULL AS last_seen FROM client_bindings b JOIN agent_access a ON a.binding=b.id WHERE b.id=?', (identifier,)).fetchone()
        if row is None:
            raise BindingError('connection_missing', 'Unknown connection', 404)
        if row['revoked'] and not allow_revoked:
            raise BindingError('connection_unavailable', 'Connection is revoked', 409)
        return dict(row)

    def profile(self, identifier):
        row = self._read('connection_profiles', identifier)
        return json.loads(row['body']) if row else {}

    def _public_tests(self, identifier, rows, profile_revision, control_revision):
        tests = []
        for probe in rows:
            body = json.loads(probe['body'])
            if body['state'] in ('running', 'awaiting_reply') and probe['deadline'] < time.time():
                body.update(state='timed_out', finishedAt=probe['deadline'], message='No correlated reply arrived before the deadline; capability remains unconfirmed')
                body['error'] = dict(code='control_timeout', phase='callback' if body.get('nativeId') else 'create', outcomeUnknown=True)
            body['current'] = bool(profile_revision and body.get('profileRevision') == profile_revision and
                                   body.get('controlRevision') == control_revision)
            if body['current'] and body.get('projectBinding'):
                try:
                    self._probe_project_binding(identifier, body['projectBinding'])
                except BindingError:
                    body['current'] = False
            tests.append(body)
        return tests

    def history(self, identifier, *, offset=0, limit=20):
        self.binding(identifier, allow_revoked=True)
        try:
            if isinstance(offset, bool) or isinstance(limit, bool):
                raise ValueError()
            offset, limit = int(str(offset)), int(str(limit))
            if offset < 0 or not 1 <= limit <= 100:
                raise ValueError()
        except (ValueError, TypeError):
            raise BindingError('invalid_history_page', 'Use a nonnegative offset and a limit from 1 to 100')
        profile = self._read('connection_profiles', identifier)
        control = self._read('connection_controls', identifier)
        control_revision = fingerprint(json.loads(control['body'])) if control else None
        counts = dict(passed=0, configuration=0, failed=0, timeout=0, cancelled=0, running=0)
        rows = []
        with self.registry.connect() as c:
            exists = c.execute("SELECT 1 FROM sqlite_master WHERE name='connection_probes'").fetchone()
            if exists:
                grouped = c.execute('''SELECT CASE WHEN json_extract(body,'$.state') IN ('running','awaiting_reply')
                    AND deadline < ? THEN 'timed_out' ELSE json_extract(body,'$.state') END AS state, COUNT(*) AS n
                    FROM connection_probes WHERE binding=? GROUP BY state''', (time.time(), identifier)).fetchall()
                for item in grouped:
                    state = item['state']
                    category = ('passed' if state in ('passed', 'verified') else 'configuration' if state == 'configuration_required'
                                else 'timeout' if state in ('timeout', 'timed_out') else 'cancelled' if state == 'cancelled'
                                else 'running' if state in ('running', 'awaiting_reply', 'queued', 'pending') else 'failed')
                    counts[category] += item['n']
                total = sum(counts.values())
                offset = min(offset // limit, max(0, (total - 1) // limit)) * limit
                rows = c.execute('SELECT * FROM connection_probes WHERE binding=? ORDER BY updated DESC,id DESC LIMIT ? OFFSET ?',
                                 (identifier, limit, offset)).fetchall()
        return dict(connection=identifier, tests=self._public_tests(identifier, rows, profile['revision'] if profile else None,
                    control_revision), total=sum(counts.values()), offset=offset if rows else 0, limit=limit, counts=counts)

    def describe(self, identifier, profile, *, binding=None, base=None):
        self.binding(identifier)
        value = validate_profile(profile)
        value_revision = fingerprint(value)
        with barrier(self.registry):
            self.binding(identifier)
            self.setup()
            with self.registry.connect() as c:
                c.execute('INSERT INTO connection_profiles VALUES(?,?,?,?) ON CONFLICT(binding) DO UPDATE SET body=excluded.body,revision=excluded.revision,updated=excluded.updated',
                          (identifier, json.dumps(value, ensure_ascii=False), value_revision, time.time()))
        return self.public(identifier, binding=binding)

    def public(self, identifier, *, binding=None):
        row = self._read('connection_profiles', identifier)
        profile = json.loads(row['body']) if row else {}
        caps = {name: dict(state='unknown', message='Capability has not been tested') for name in ('mcp', 'openChat', 'createChat', 'sendMessage', 'callback')}
        seen = (binding or {}).get('last_seen') or (binding or {}).get('activity', {}).get('lastRequest')
        if seen:
            caps['mcp'] = dict(state='verified', testedAt=seen, message='Hub received an authenticated tool request')
        native = profile.get('nativeChat')
        if native and native.get('openUri'):
            caps['openChat'] = dict(state='documented' if native.get('openingDocumented') else 'client-reported',
                documented=bool(native.get('openingDocumented')), message='Source link available; opening in the native application has not been tested', guiVerified=False)
        with self.registry.connect() as c:
            exists = c.execute("SELECT 1 FROM sqlite_master WHERE name='connection_probes'").fetchone()
            rows = c.execute('SELECT * FROM connection_probes WHERE binding=? ORDER BY updated DESC,id DESC LIMIT 8', (identifier,)).fetchall() if exists else []
        control = self._read('connection_controls', identifier)
        config = json.loads(control['body']) if control else None
        tests = self._public_tests(identifier, rows, row['revision'] if row else None, fingerprint(config) if config else None)
        # The project identifies the test chat's destination. Capability results
        # belong to the application connection, regardless of that destination.
        if tests and tests[0]['current']:
            caps.update(tests[0].get('capabilities', {}))
        revoked = bool((binding or {}).get('revoked'))
        if revoked:
            caps = {name: dict(state='unavailable', message='Connection is revoked') for name in caps}
        control_status, features = self.integration_status(profile, config, caps, tests, revoked=revoked)
        from project_bindings import ProjectBindings
        project_bindings = ProjectBindings(self.registry).list(identifier)
        if config:
            config = dict(protocol=config['protocol'], endpoint=config['endpoint'], hasCredential=bool(config.get('credentialRef')))
        from agent_instructions import bundle
        manifest = bundle(self.registry)['instructionManifest']
        from agent_launches import Launches
        return dict(id=identifier, profile=profile, profileRevision=row['revision'] if row else None,
                    nativeChat=native, capabilities=caps, tests=tests, control=config,
                    controlStatus=control_status, features=features,
                    projectBindings=project_bindings, instructionManifest=manifest,
                    instructionsCurrent=profile.get('persistentInstructions',{}).get('revision')==manifest['revision'],
                    launches=Launches(self.registry).list(identifier))

    def configure(self, body, base=None):
        identifier = text(body['id'], 'connection ID')
        protocol = body['protocol']
        if protocol not in ('mcp-http', 'http-json'):
            raise BindingError('invalid_control_protocol', 'Use HTTP MCP or HTTP JSON')
        target = endpoint(body['endpoint'])
        key = body['apiKey']
        if not isinstance(key, str) or len(key) > 4096 or key and any(ord(ch) < 33 for ch in key):
            raise BindingError('invalid_control_key', 'Use a private API credential without whitespace')
        integration_profile = None
        expected_profile_revision = None
        if 'profile' in body:
            integration_profile = validate_profile(body['profile'])
            if integration_profile.get('control') != dict(protocol=protocol, endpoint=target):
                raise BindingError('profile_control_mismatch', 'The profile control must match the saved protocol and endpoint', 409)
            if 'expectedProfileRevision' not in body or body['expectedProfileRevision'] is not None and not isinstance(body['expectedProfileRevision'], str):
                raise BindingError('invalid_profile_revision', 'Provide the current profile revision or explicit null for a first setup')
            expected_profile_revision = body['expectedProfileRevision']
        # Receipts contain a digest only; the private key is never copied into Hub data.
        request = dict(action='connection.integration' if integration_profile else 'connection.control', id=identifier,
                       protocol=protocol, endpoint=target, credentialDigest=hashlib.sha256(key.encode()).hexdigest())
        if integration_profile:
            request.update(profile=integration_profile, expectedProfileRevision=expected_profile_revision)
        with barrier(self.registry):
            self.binding(identifier)
            self.setup()
            with self.registry.connect() as c:
                proof, old = self.registry._request(c, body['requestId'], request)
                if old is not None:
                    return old
                if integration_profile:
                    current_profile = c.execute('SELECT revision FROM connection_profiles WHERE binding=?', (identifier,)).fetchone()
                    current_revision = current_profile['revision'] if current_profile else None
                    if current_revision != expected_profile_revision:
                        raise BindingError('profile_revision_conflict', 'The application profile changed; refresh it before saving the integration', 409)
                previous = c.execute('SELECT body FROM connection_controls WHERE binding=?', (identifier,)).fetchone()
                previous = json.loads(previous['body']) if previous else {}
                same = previous.get('endpoint') == target and previous.get('protocol') == protocol
                if previous.get('credentialRef') and not same and not key:
                    raise BindingError('control_key_required', 'Changing the endpoint requires a new credential; the existing key is never sent to the new address', 409)
                ref = previous.get('credentialRef') if same else None
                if key:
                    from secret_vault import save
                    # A fresh immutable reference makes receipt retries and crash recovery safe.
                    ref = 'control-' + identifier + '-' + proof[:16]
                    save(self.registry, ref, key)
                config = dict(protocol=protocol, endpoint=target, credentialRef=ref)
                c.execute('INSERT INTO connection_controls VALUES(?,?,?) ON CONFLICT(binding) DO UPDATE SET body=excluded.body,updated=excluded.updated',
                          (identifier, json.dumps(config), time.time()))
                if integration_profile:
                    profile_revision = fingerprint(integration_profile)
                    c.execute('INSERT INTO connection_profiles VALUES(?,?,?,?) ON CONFLICT(binding) DO UPDATE SET body=excluded.body,revision=excluded.revision,updated=excluded.updated',
                              (identifier, json.dumps(integration_profile, ensure_ascii=False), profile_revision, time.time()))
                    result = dict(saved=True, id=identifier, profileRevision=profile_revision)
                else:
                    result = dict(saved=True, id=identifier)
                c.execute('INSERT INTO project_requests VALUES(?,?,?)', (body['requestId'], proof, json.dumps(result)))
                c.commit()
        return result

    @staticmethod
    def integration_status(profile, config, capabilities, tests, *, revoked=False):
        """Separate declarations, configured routes and the facts a probe observed.

        This is a read-only projection. Saving a profile or endpoint never probes
        a peer. A declared agent tool alone is not an external control interface.
        """
        declared = profile.get('control')
        actions = profile.get('capabilities', {})
        if revoked:
            configuration = 'revoked'
        elif not declared:
            configuration = 'interface_missing'
        elif not config:
            configuration = 'not_configured'
        elif declared != {key: config[key] for key in ('protocol', 'endpoint')}:
            configuration = 'configuration_mismatch'
        else:
            configuration = 'ready'

        def action_available(name):
            action = actions.get(name) or {}
            protocol = (config or declared or {}).get('protocol')
            return bool(action.get('tool') if protocol == 'mcp-http' else action.get('path') if protocol == 'http-json' else False)

        can_test = configuration == 'ready' and action_available('createChat')
        route_state = 'action_missing' if configuration == 'ready' and not can_test else configuration
        control = dict(state=route_state, reason=route_state, canTest=can_test, direction='hub-to-application')
        latest = tests[0] if tests else None
        current = bool(latest and latest['current'] and not revoked)
        features = {}
        incoming = capabilities['mcp']
        features['mcp'] = dict(direction='agent-to-hub', support='provided', configuration='revoked' if revoked else 'configured',
            state='revoked' if revoked else 'verified' if incoming.get('state') == 'verified' else 'not_observed',
            reason='authenticated_request' if incoming.get('state') == 'verified' and not revoked else 'not_observed',
            verification=dict(incoming, source='authenticated-request', current=not revoked))
        for name in ('createChat', 'sendMessage', 'callback'):
            action_name = 'createChat' if name == 'callback' else name
            reported = bool(actions.get(action_name))
            feature_configuration = configuration
            if feature_configuration == 'ready' and not action_available(action_name):
                feature_configuration = 'action_missing'
            evidence = capabilities.get(name, {})
            state = feature_configuration
            if state == 'ready':
                if not current and latest:
                    state = 'stale'
                elif evidence.get('state') == 'verified':
                    state = 'verified'
                elif current and latest['state'] in ('running', 'awaiting_reply', 'failed', 'timed_out', 'cancelled', 'unavailable'):
                    state = latest['state']
            if not reported and not revoked and configuration != 'ready':
                state = 'not_reported'
            verification = dict(evidence, source='control-probe', current=current)
            if current and state in ('running', 'awaiting_reply', 'failed', 'timed_out', 'cancelled', 'unavailable'):
                verification.update(state=state, message=latest.get('message', ''))
            features[name] = dict(direction='application-to-hub' if name == 'callback' else 'hub-to-application',
                support=('derived' if name == 'callback' else 'declared') if reported else 'not_reported',
                configuration=feature_configuration, state=state, reason=state,
                verification=verification)
        link = capabilities.get('openChat', {})
        has_source = bool(profile.get('nativeChat', {}).get('openUri')) or link.get('state') in ('documented', 'client-reported')
        features['openChat'] = dict(direction='browser-to-application',
            support='declared' if actions.get('openChat') or has_source else 'not_reported', configuration='not_required',
            state='source_available' if has_source else 'link_template' if actions.get('openChat') else 'not_reported',
            reason='source_available' if has_source else 'link_template' if actions.get('openChat') else 'not_reported',
            verification=dict(link, source='source-link', current=has_source, guiVerified=False))
        return control, features

    def _save_probe(self, identifier, body):
        with barrier(self.registry), self.registry.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT binding,revision,body FROM connection_probes WHERE id=?', (identifier,)).fetchone()
            if row is None:
                return
            try:
                self.binding(row['binding'])
                current_profile = self._read('connection_profiles', row['binding'])
                current_control = self._read('connection_controls', row['binding'])
                if current_profile is None or current_profile['revision'] != body['profileRevision'] or body.get('controlRevision') != (fingerprint(json.loads(current_control['body'])) if current_control else None):
                    raise ValueError('Configuration changed')
                self._probe_project_binding(row['binding'], body.get('projectBinding'))
            except (BindingError, ValueError):
                body = dict(body, state='cancelled', finishedAt=time.time(), capabilities={}, message='Connection or configuration changed during the probe')
            confirmed=json.loads(row['body'])
            if confirmed.get('state')=='passed' and body.get('state')!='cancelled':
                # A callback may commit while the response is still being read.
                # Later transport observations cannot revoke verified correlation.
                body=dict(body,state='passed',finishedAt=confirmed['finishedAt'],message=confirmed['message'],
                          capabilities={**body.get('capabilities',{}),**confirmed.get('capabilities',{})})
            c.execute('UPDATE connection_probes SET body=?,updated=? WHERE id=?', (json.dumps(body), time.time(), identifier))
            c.commit()

    def _probe_project_binding(self, identifier, context):
        if not context:
            return None
        from project_bindings import ProjectBindings
        bindings = ProjectBindings(self.registry)
        current = bindings.read(identifier, context['bindingId'])
        bindings.ensure_ready(identifier, context['bindingId'])
        if (current.get('status') != 'active' or current.get('revision') != context['revision'] or
                current.get('project') != context['project'] or current.get('scope') != context['scope']):
            raise BindingError('project_binding_changed', 'The selected project binding changed; choose it again before testing', 409)
        return current

    def test(self, identifier, base, binding_id=None):
        with barrier(self.registry):
            self.binding(identifier)
            self.setup()
            profile_row = self._read('connection_profiles', identifier)
            profile = json.loads(profile_row['body']) if profile_row else {}
            revision = profile_row['revision'] if profile_row else ''
            config_row = self._read('connection_controls', identifier)
            config = json.loads(config_row['body']) if config_row else None
            create_spec = profile.get('capabilities', {}).get('createChat') if profile else None
            if create_spec and create_spec.get('projectRouting') and not binding_id:
                raise BindingError('project_binding_required', 'Select a project binding before testing this project-routed chat interface', 409)
            project_context = None
            if binding_id:
                from project_bindings import ProjectBindings
                selected = ProjectBindings(self.registry).read(identifier, binding_id)
                ProjectBindings(self.registry).ensure_ready(identifier, binding_id)
                if selected.get('status') != 'active':
                    raise BindingError('project_binding_unavailable', 'Select an active project binding before testing', 409)
                project_context = dict(bindingId=selected['id'], revision=selected['revision'],
                    project=selected['project'], scope=selected['scope'])
            test_id, nonce = secrets.token_hex(16), secrets.token_urlsafe(32)
            body = dict(id=test_id, state='running', startedAt=time.time(), deadline=time.time() + TIMEOUT,
                        profileRevision=revision, controlRevision=fingerprint(config) if config else None,
                        message='Testing the configured interface', capabilities={})
            if project_context:
                body['projectBinding'] = project_context
            if not profile:
                body.update(state='unknown', finishedAt=time.time(), message='The client has not supplied its interface profile')
            elif not config:
                body.update(state='configuration_required', finishedAt=time.time(), message='Confirm the control endpoint and its separate credential in settings before testing')
            elif profile.get('control') != {key: config[key] for key in ('protocol', 'endpoint')}:
                body.update(state='configuration_required', finishedAt=time.time(), message='The confirmed endpoint does not match the client profile')
            else:
                with self.registry.connect() as c:
                    for previous in c.execute('SELECT id,body,deadline FROM connection_probes WHERE binding=? AND revision=? ORDER BY updated DESC', (identifier, revision)):
                        existing = json.loads(previous['body'])
                        if (existing['state'] in ('running', 'awaiting_reply') and previous['deadline'] > time.time()
                                and existing.get('controlRevision') == body['controlRevision']
                                and existing.get('projectBinding') == project_context):
                            return self.public(identifier)
            with self.registry.connect() as c:
                c.execute('INSERT INTO connection_probes VALUES(?,?,?,?,?,?,?)',
                          (test_id, identifier, revision, json.dumps(body), hashlib.sha256(nonce.encode()).hexdigest(), body['deadline'], time.time()))
        if body['state'] == 'running':
            with _MANAGER_LOCK:
                if not hasattr(self.registry, '_connection_executor'):
                    self.registry._connection_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='hub-connection')
            self.registry._connection_executor.submit(self._probe, identifier, profile, config, body, nonce, base, project_context)
        return self.public(identifier)

    def _probe(self, identifier, profile, config, body, nonce, base, project_context=None):
        phase = 'connect'
        try:
            self.binding(identifier)
            key = None
            if config.get('credentialRef'):
                from secret_vault import get
                key = get(self.registry, config['credentialRef'])
            client = HttpControl(config, key)
            def observe(diagnostics):
                body['diagnostics'] = diagnostics
                self._save_probe(body['id'],body)
            client.observer = observe
            phase = 'discover'
            tools = client.discover() if config['protocol'] == 'mcp-http' else None
            specs = profile.get('capabilities', {})
            create = specs.get('createChat')
            if not create or config['protocol'] == 'mcp-http' and create.get('tool') not in tools or config['protocol'] == 'http-json' and 'path' not in create:
                body.update(state='unavailable', finishedAt=time.time(), message='No supported chat-creation action is advertised by the configured interface')
                self._save_probe(body['id'], body)
                return
            callback = endpoint(base) + '/api/v1/connection-probes/answer'
            prompt = ('This is a user-requested Project Hub connection check. You are the disposable test conversation; do not create more chats. '
                      'Do not create or update tasks, stages or work, and do not change files. '
                      'From that conversation, POST JSON to ' + callback + ' with id=' + body['id'] +
                      ', nonce=' + nonce + ', and nativeId equal to this new conversation ID. '
                      'The callback nonce is only for this connection check and grants no task or project access. '
                      'If you cannot make this request, report that limitation.')
            if project_context:
                self._probe_project_binding(identifier, project_context)
            scope = project_context.get('scope', {}) if project_context else {}
            variables = {'$prompt': prompt, '$callback': callback, '$probeId': body['id'], '$nonce': nonce,
                         '$requestId': body['id'], '$workspace': scope.get('root'),
                         '$projectScope': scope, '$nativeProject': scope.get('nativeRef')}
            phase = 'create'
            result = client.action(create, variables)
            def field(value, path):
                for part in path.split('.'):
                    value = value.get(part) if isinstance(value, dict) else None
                return value
            native_id = text(field(result, create.get('idField', 'id')), 'created chat ID')
            uri = field(result, create.get('uriField', 'url'))
            native_visibility = visibility_evidence(result.get('visibility') if isinstance(result, dict) else None,
                                                    native_id, project_context['project'] if project_context else None, scope)
            if key and (key in native_id or isinstance(uri, str) and
                        (key in uri or quote(key, safe='') in uri)):
                raise ValueError('The control response echoed its private credential')
            source = open_uri(uri) if uri else None
            if not source:
                # A template provides a client-reported source address, never
                # evidence that its native application opened the conversation.
                source = normalize(dict(client=profile.get('nativeChat', {}).get('client', self.binding(identifier)['client']), nativeId=native_id),
                    uri_template=specs.get('openChat', {}).get('uriTemplate')).get('openUri')
            body.update(nativeId=native_id, sourceUri=source, state='awaiting_reply',
                        message='The API created a test conversation; waiting for its correlated reply')
            if native_visibility:
                body['nativeVisibility'] = native_visibility
            body['nativeChat'] = normalize(dict(client=profile.get('nativeChat', {}).get('client', self.binding(identifier)['client']),
                                                nativeId=native_id, **({'openUri': source} if source else {})), provenance='control-api')
            body['capabilities']['createChat'] = dict(state='verified', testedAt=time.time(), message='Configured API returned a new conversation ID')
            documented = body['nativeChat']['openingDocumented']
            body['capabilities']['openChat'] = dict(state='documented' if documented else 'client-reported' if source else 'unknown', documented=documented, guiVerified=False,
                message='Source link returned; native application opening is not proven' if source else 'The API returned no usable source link')
            self._save_probe(body['id'], body)
            send = specs.get('sendMessage')
            if send:
                phase = 'send'
                if project_context:
                    self._probe_project_binding(identifier, project_context)
                self.binding(identifier)
                current_profile = self._read('connection_profiles', identifier)
                current_control = self._read('connection_controls', identifier)
                if current_profile is None or current_profile['revision'] != body['profileRevision'] or current_control is None or fingerprint(json.loads(current_control['body'])) != body['controlRevision']:
                    raise ValueError('Connection changed during the probe')
                if tools is not None and send.get('tool') not in tools:
                    raise ValueError('The message action is not advertised by the configured MCP server')
                client.action(send, {**variables, '$nativeId': native_id})
                body['capabilities']['sendMessage'] = dict(state='verified', testedAt=time.time(), message='Configured API accepted a message for the returned conversation ID')
                # A callback may already have completed the row; preserve its state.
                current = self._read('connection_probes', body['id'], 'id')
                if current and json.loads(current['body']).get('state') == 'passed':
                    body.update(state='passed', finishedAt=json.loads(current['body'])['finishedAt'], message='A correlated reply arrived from the test conversation')
                    body['capabilities'].update(json.loads(current['body']).get('capabilities', {}))
                self._save_probe(body['id'], body)
        except Exception as error:
            # Never expose upstream response bodies, credentials or executable peer
            # instructions through the administrative catalog.
            body.update(state='failed', finishedAt=time.time(), message='The configured interface did not complete the probe; check its protocol, credential and declared actions')
            body['error'] = probe_failure(error, phase)
            if isinstance(error,OutboundError):
                body['transportError'] = error.diagnostic
            self._save_probe(body['id'], body)

    def answer(self, value):
        if not isinstance(value, dict) or set(value) != {'id', 'nonce', 'nativeId'}:
            raise BindingError('invalid_probe_reply', 'Use id, nonce and nativeId')
        identifier = text(value['id'], 'probe ID')
        nonce = text(value['nonce'], 'probe nonce')
        native_id = text(value['nativeId'], 'native chat ID')
        with barrier(self.registry), self.registry.connect() as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='connection_probes'").fetchone():
                raise BindingError('probe_unavailable', 'Probe is unavailable', 404)
            c.execute('BEGIN IMMEDIATE')
            row = c.execute('SELECT * FROM connection_probes WHERE id=?', (identifier,)).fetchone()
            if row is None or not hmac.compare_digest(row['nonce_hash'], hashlib.sha256(nonce.encode()).hexdigest()) or row['deadline'] < time.time():
                raise BindingError('probe_unavailable', 'Probe is unavailable or expired', 404)
            self.binding(row['binding'])
            current = self._read('connection_profiles', row['binding'])
            control = self._read('connection_controls', row['binding'])
            body = json.loads(row['body'])
            if current is None or current['revision'] != row['revision'] or body.get('controlRevision') != (fingerprint(json.loads(control['body'])) if control else None):
                raise BindingError('probe_changed', 'The client profile changed; run another test', 409)
            if body.get('nativeId') != native_id or body['state'] not in ('awaiting_reply', 'passed'):
                raise BindingError('probe_identity', 'Reply must come from the conversation returned by the configured API', 409)
            try:
                self._probe_project_binding(row['binding'], body.get('projectBinding'))
            except BindingError:
                body.update(state='cancelled', finishedAt=time.time(), capabilities={},
                    message='Connection or configuration changed during the probe')
                c.execute('UPDATE connection_probes SET body=?,updated=? WHERE id=?', (json.dumps(body), time.time(), identifier))
                c.commit()
                raise BindingError('probe_changed', 'The project binding changed; run another test', 409) from None
            if body['state'] != 'passed':
                body.update(state='passed', finishedAt=time.time(), message='A correlated reply arrived from the test conversation')
                body['capabilities']['callback'] = dict(state='verified', testedAt=time.time(), message='Probe nonce and returned conversation ID matched')
                c.execute('UPDATE connection_probes SET body=?,updated=? WHERE id=?', (json.dumps(body), time.time(), identifier))
            c.commit()
        return dict(accepted=True, id=identifier)
