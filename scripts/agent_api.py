"""Local administrative onboarding and bearer-scoped agent HTTP API."""
from functools import lru_cache
from pathlib import Path
import sys
import time

from agent_bindings import Connections, BindingError, digest, text
from agent_runtime import call


@lru_cache(maxsize=1)
def workflow():
    from agent_instructions import base_workflow
    return base_workflow()


def credential(headers):
    values = headers.get_all('Authorization') if hasattr(headers,'get_all') else [headers.get('Authorization')]
    if len(values or []) != 1 or not isinstance(values[0],str) or not values[0].startswith('Bearer '):
        raise BindingError('connection_required','Use one Hub connection credential',401)
    return values[0][7:]


def bootstrap(registry, token, base):
    connections = Connections(registry)
    token = text(token,'invitation')
    with registry.connect() as c:
        exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='agent_invitations'").fetchone()
        row = c.execute('SELECT * FROM agent_invitations WHERE token_hash=?',
                        (digest(token),)).fetchone() if exists else None
    if row is None or row['revoked']:
        raise BindingError('invitation_unavailable','Create a new connection invitation',401)
    if row['response'] is None and row['expires'] < time.time():
        raise BindingError('invitation_expired','Create a new connection invitation',401)
    if row['project']:
        connections.project(row['project'])
    from hub_launcher import default_base
    from hub_lifecycle import control_directory
    control = control_directory()
    local_setup = dict(sameMachineOnly=True,
        launcher=[sys.executable,'-B',str(Path(__file__).resolve().with_name('hub_cli.py'))],
        privateConnectionDirectory=str((control.parent.parent if control else default_base())/'connections'),
        supportedNativeHosts=['codex','cursor'],transport='streamable-http',manualSetupAvailable=True)
    scope = row['scope'] if 'scope' in row.keys() else ('project' if row['project'] else 'new-project')
    legacy = '' if scope == 'global' else (
        'This is a legacy invitation. It retains its original project scope; a legacy new-project invitation '
        'also requires name and optional roots. ')
    from agent_instructions import bundle, CONTRACT_VERSION
    rules = bundle(registry, base)
    rules.pop('scope')
    rules.pop('contractVersion')
    reconnect = dict(binding=row['reconnect']) if 'reconnect' in row.keys() and row['reconnect'] else None
    if reconnect:
        with registry.connect() as c:
            previous = c.execute('SELECT client,external_id FROM agent_connections WHERE id=?', (row['reconnect'],)).fetchone()
            if previous is None:
                previous = c.execute('SELECT client,external_id FROM client_bindings WHERE id=?', (row['reconnect'],)).fetchone()
        if previous:
            reconnect.update(client=previous['client'], externalId=previous['external_id'])
    from agent_sdk import mcp_http_endpoint
    return dict(schemaVersion=3,contractVersion=CONTRACT_VERSION,project=row['project'],scope=scope,expires=row['expires'],localSetup=local_setup,
        reconnect=reconnect,
        invitation=token,endpoints=dict(enroll=base+'/api/v1/agent/enroll',mcp=mcp_http_endpoint(base),
        call=base+'/api/v1/agent/call',upload=base+'/api/v1/agent/artifacts'),
        setupInstructions=(
            legacy + 'Connect the agent to this Hub installation once. For reconnection reuse reconnect.client and '
            'reconnect.externalId to preserve its binding and history. POST to endpoints.enroll with invitation, client '
            '(your actual host name, including an unknown host), externalId (a unique connection ID), and optional '
            'client-reported model, session, chat or metadata {label,clientVersion}. Do not infer an unavailable '
            'model or native conversation ID. A global invitation needs no project, workspace or model selection '
            'and never creates a project. Reuse the identical enrollment payload after an uncertain response. '
            'It returns a private Hub token, independent of every model-provider API key. Configure the '
            'host\'s native Streamable HTTP MCP connection with endpoints.mcp and Authorization: Bearer token. '
            'On this server machine, localSetup.launcher can enroll with connect, your client/external-id and '
            'a private output file. Its onboarding command previews documented HTTP MCP configuration for Codex '
            'or Cursor, or a manual capability plan for other hosts. Review before applying a supported native '
            'registration and provision the token privately in the host secret store or referenced environment. '
            'Keep credentials in private native user configuration or its secret store, outside source '
            'control and public project instructions. Preserve unrelated configuration and native approvals. '
            'If the host has no MCP client, use endpoints.call with {tool,arguments}; every arguments object '
            'includes the current conversation session ID. Call hub_projects to discover registered projects. '
            'Every project tool request selects an explicit project and, for local code access, a registered '
            'workspace. An ambiguous workspace or omitted project is rejected; never guess the project from '
            'another conversation. Install the verified instructionBundle as separate local files and a short '
            'application-wide rule using onboarding, preserving existing content. The authorized connection '
            'request includes owned rule installation; honor actual native approvals without adding a second '
            'confirmation. Save the Hub address and MCP '
            'connection name; keep the token only in private connection configuration. If writing is unavailable '
            'provide manual steps and report instructionsPersisted=false. '
            'Call hub_connection(action="describe", profile=...) to report known client interfaces and optional '
            'native chat identity. Unknown values are valid. Client declarations do not prove capabilities; '
            'MCP enrollment does not connect native chat control. This Hub includes an optional local Codex '
            'desktop adapter, connected in a separate step from the current Codex chat after the user selects '
            'allowed project folders. The adapter setup generates its own private key and saves its actual '
            'HTTP JSON endpoint, protocol and capabilities in Hub; Codex does not automatically publish that '
            'HTTP interface when enrolling. For other clients report chat control as unavailable unless they '
            'provide an actual compatible external interface. Never invent a control endpoint from internal '
            'agent tool names or a model-service API. The user configures client-control access independently '
            'of model-provider keys. Verify the complete '
            'tools/list catalog and hub_instructions through native HTTP MCP. A saved config or SDK request '
            'does not prove native tool loading. Keep native HTTP transport and global proxy settings '
            'unchanged while diagnosing failures. Verify hub_context '
            'and a new conversation before claiming setup complete. If the host cannot configure itself, '
            'explain the exact manual action required.'), **rules)


def execute(registry, route, body, headers, base, *, administrator=False):
    if not isinstance(body,dict):
        raise BindingError('invalid_request','Use a request object')
    connections = Connections(registry)
    if route == '/api/v1/connections':
        if body.get('action') in ('launch','project-binding','describe-profile') and not administrator:
            raise BindingError('administrator_required','Use the trusted local Hub administration interface',403)
        if body.get('action')=='launch' and set(body)=={'action','id','request'}:
            from agent_launches import Launches
            return Launches(registry,base).start(body['id'],body['request'])
        if body.get('action')=='project-binding' and set(body)=={'action','id','operation'}:
            from project_bindings import ProjectBindings
            return ProjectBindings(registry).execute(body['id'],body['operation'])
        if body.get('action')=='describe-profile' and set(body)=={'action','id','profile'}:
            from connection_capabilities import Profiles
            return Profiles(registry).describe(body['id'],body['profile'])
        if body.get('action')=='invite' and set(body)<={'action','project','requestId'} and 'requestId' in body:
            result = connections.invite(body.get('project'),request_id=body['requestId'])
            return dict(result,url=base+'/connect/'+result['token'])
        if body.get('action')=='revoke' and set(body)=={'action','id'}:
            return connections.revoke(body['id'])
        if body.get('action')=='reconnect' and set(body)=={'action','id','requestId'}:
            result = connections.reconnect(body['id'], request_id=body['requestId'])
            return dict(result,url=base+'/connect/'+result['token'])
        if body.get('action')=='test' and set(body)<= {'action','id','bindingId'} and {'action','id'}<=set(body):
            from connection_capabilities import Profiles
            return Profiles(registry).test(body['id'], base, binding_id=body.get('bindingId'))
        if body.get('action')=='configure-integration' and set(body)=={'action','id','protocol','endpoint','apiKey','requestId','profile','expectedProfileRevision'}:
            if not administrator:
                raise BindingError('administrator_required','Use the trusted local Hub administration interface',403)
            from connection_capabilities import Profiles
            return Profiles(registry).configure(body, base)
        if body.get('action')=='configure-control' and set(body)=={'action','id','protocol','endpoint','apiKey','requestId'}:
            from connection_capabilities import Profiles
            return Profiles(registry).configure(body, base)
        raise BindingError('invalid_request','Use an explicit connection operation')
    if route == '/api/v1/agent/enroll':
        fields = ('workspace','name','roots','model','session','chat','metadata')
        if set(body)-{'invitation','client','externalId',*fields} or not {'invitation','client','externalId'}<=set(body):
            raise BindingError('invalid_request','Use invitation, client, externalId and optional client-reported metadata')
        return connections.enroll(body['invitation'],body['client'],body['externalId'],
            **{key:body[key] for key in fields if key in body})
    token = credential(headers)
    if route == '/api/v1/agent/call':
        if set(body)!={'tool','arguments'} or not isinstance(body['tool'],str):
            raise BindingError('invalid_request','Use tool and arguments, including your current session')
        return call(registry,token,body['tool'],body['arguments'],base=base)
    if route == '/api/v1/agent/artifacts':
        if set(body)-{'name','content','roles','previous','project','workspace'} or not {'name','content'}<=set(body):
            raise BindingError('invalid_request','Use artifact name, base64 content and an explicit project for a global connection')
        from artifact_store import upload
        from task_transfer import barrier
        with barrier(registry):
            binding = connections.authenticate(token)
            project,_ = connections.select_project(binding,body.get('project'),body.get('workspace'))
            return upload(registry.store(project['id']),body['name'],body['content'],
                **{key:body[key] for key in ('roles','previous') if key in body})
    raise BindingError('unknown_route','Unknown agent operation',404)
