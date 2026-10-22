"""Stateless Streamable HTTP with explicit legacy handshake compatibility.

Application conversation identity remains in tool arguments. MCP connections,
transport sessions and self-reported clientInfo never grant project authority.
"""
import base64
import json
import math
import sqlite3

from agent_bindings import Connections, BindingError
from agent_runtime import call, tools
from hub_core import HubError


MODERN = '2026-07-28'
LEGACY = ('2025-03-26','2025-06-18','2025-11-25')
VERSIONS = (*LEGACY,MODERN)
META_VERSION = 'io.modelcontextprotocol/protocolVersion'
META_CAPABILITIES = 'io.modelcontextprotocol/clientCapabilities'
META_INFO = 'io.modelcontextprotocol/serverInfo'
from pathlib import Path
SERVER_INFO = dict(name='project-hub',version=json.loads((Path(__file__).resolve().parents[1] /
                   'tools/project-portal/plugins/project-hub/plugin.json').read_text(encoding='utf-8'))['version'])
WORKFLOW_URI = 'project-hub://workflow'
INSTRUCTIONS = 'Read hub_instructions during authorized setup; install its verified separate files and short native global rule, preserving unrelated instructions and native permissions. At startup and after compaction read both local full files. Compare the manifest once at startup and refresh changed snapshots. tools/list publishes the complete command schemas; use project-hub://instructions/api-reference or local api-reference.md for exact action arguments. Missing native tools means setup is incomplete, even if registration was saved. Resolve an unbound project through hub_project_bindings; persist its canonical Hub ID in a scoped native rule. Use distinct conversation sessions and explicit projects. Read hub_context and projectSettings before substantive work. No plugin is required. Hub is advisory and never blocks the user task.'


class ProtocolError(ValueError):
    def __init__(self, code, message, status=400, data=None):
        super().__init__(message)
        self.code,self.status,self.data = code,status,data


def error(identifier, code, message, data=None):
    body = dict(code=code,message=message)
    if data is not None:
        body['data'] = data
    return dict(jsonrpc='2.0',id=identifier,error=body)


def headers_map(headers):
    result = {}
    for key,value in headers.items():
        key = key.lower()
        if key in result:
            raise ProtocolError(-32020,'Ambiguous request header: '+key)
        if not isinstance(value,str) or any(ord(c)<32 and c!='\t' or ord(c)>126 for c in value):
            raise ProtocolError(-32020,'Invalid request header: '+key)
        result[key] = value
    return result


def decode_header(value):
    if value.startswith('=?base64?') and value.endswith('?='):
        try:
            return base64.b64decode(value[9:-2],validate=True).decode('utf-8')
        except (ValueError,UnicodeError):
            raise ProtocolError(-32020,'Invalid encoded request header') from None
    if value.strip()!=value:
        raise ProtocolError(-32020,'Padded request header requires encoded representation')
    return value


def protocol(message, headers):
    if (not isinstance(message,dict) or message.get('jsonrpc')!='2.0' or
            not isinstance(message.get('method'),str) or not message['method'] or
            set(message)-{'jsonrpc','id','method','params'}):
        raise ProtocolError(-32600,'Invalid JSON-RPC request')
    identifier = message.get('id')
    if 'id' in message and (type(identifier) not in (str,int,float) or
                            isinstance(identifier,float) and not math.isfinite(identifier)):
        raise ProtocolError(-32600,'Invalid JSON-RPC request ID')
    params = message.get('params',{})
    if not isinstance(params,dict):
        raise ProtocolError(-32602,'Request params must be an object')
    meta = params.get('_meta',{})
    if not isinstance(meta,dict):
        raise ProtocolError(-32602,'Request metadata must be an object')
    version = headers.get('mcp-protocol-version')
    body_version = meta.get(META_VERSION)
    modern = version==MODERN or body_version is not None
    if modern:
        if not isinstance(body_version,str) or not isinstance(meta.get(META_CAPABILITIES),dict):
            raise ProtocolError(-32602,'Per-request protocolVersion and clientCapabilities are required')
        if version != body_version:
            raise ProtocolError(-32020,'Protocol version header does not match request metadata')
        if body_version != MODERN:
            raise ProtocolError(-32022,'Unsupported protocol version',data=dict(supportedVersions=list(VERSIONS),requestedVersion=body_version))
        if headers.get('mcp-method') != message['method']:
            raise ProtocolError(-32020,'Mcp-Method header is missing or does not match')
        if message['method'] in ('tools/call','resources/read','prompts/get'):
            source = params.get('uri') if message['method']=='resources/read' else params.get('name')
            name = headers.get('mcp-name')
            if not isinstance(source,str) or name is None or decode_header(name)!=source:
                raise ProtocolError(-32020,'Mcp-Name header is missing or does not match')
        return MODERN,params
    version = version or LEGACY[0]
    if version not in LEGACY:
        raise ProtocolError(-32022,'Unsupported protocol version',data=dict(supportedVersions=list(VERSIONS),requestedVersion=version))
    return version,params


def fields(params, allowed, required=()):
    if set(params)-set(allowed)-{'_meta'} or set(required)-set(params):
        raise ProtocolError(-32602,'Missing or unsupported method parameter')


def dispatch(registry, message, headers, workflow, *, base=None):
    identifier = message.get('id') if isinstance(message,dict) else None
    if type(identifier) not in (str,int,float) or isinstance(identifier,float) and not math.isfinite(identifier):
        identifier = None
    try:
        headers = headers_map(headers)
        accepts = {part.split(';',1)[0].strip() for part in headers.get('accept','').split(',')}
        if not {'application/json','text/event-stream'} <= accepts:
            raise ProtocolError(-32600,'Accept must include application/json and text/event-stream',406)
        version,params = protocol(message,headers)
        authorization = headers.get('authorization','')
        if not authorization.startswith('Bearer ') or not authorization[7:]:
            raise BindingError('connection_required','Use the Hub connection credential',401)
        credential = authorization[7:]
        Connections(registry).authenticate(credential)
        method = message['method']
        if 'id' not in message:
            if version in LEGACY and method=='notifications/initialized':
                fields(params,())
                return 202,None
            raise ProtocolError(-32601,'Unsupported client notification')
        if method=='initialize' and version in LEGACY:
            fields(params,('protocolVersion','capabilities','clientInfo'),('protocolVersion','capabilities','clientInfo'))
            if not isinstance(params['protocolVersion'],str) or not isinstance(params['capabilities'],dict) or not isinstance(params['clientInfo'],dict):
                raise ProtocolError(-32602,'Invalid initialization parameters')
            requested = params['protocolVersion']
            selected = requested if requested in LEGACY else LEGACY[-1]
            result = dict(protocolVersion=selected,capabilities=dict(tools={},resources={}),
                          serverInfo=SERVER_INFO,instructions=INSTRUCTIONS)
        elif method=='server/discover' and version==MODERN:
            fields(params,())
            result = dict(supportedVersions=list(VERSIONS),capabilities=dict(tools={},resources={}),instructions=INSTRUCTIONS)
        elif method=='ping':
            fields(params,())
            result = {}
        elif method=='tools/list':
            fields(params,('cursor',))
            if params.get('cursor'):
                raise ProtocolError(-32602,'This tool list has no continuation cursor')
            result = dict(tools=tools())
        elif method=='resources/list':
            fields(params,('cursor',))
            if params.get('cursor'):
                raise ProtocolError(-32602,'This resource list has no continuation cursor')
            result = dict(resources=[dict(uri=WORKFLOW_URI,name='Project Hub workflow',mimeType='text/markdown',
                          description='Universal workflow reference'),
                *[dict(uri='project-hub://instructions/'+name,name=name,mimeType='application/json' if name=='manifest' else 'text/markdown')
                  for name in ('manifest','workflow','user-additions','bootstrap','api-reference')]])
        elif method=='resources/templates/list':
            fields(params,('cursor',))
            if params.get('cursor'):
                raise ProtocolError(-32602,'This resource template list has no continuation cursor')
            result = dict(resourceTemplates=[])
        elif method=='resources/read':
            fields(params,('uri',),('uri',))
            uri = params['uri']
            if uri==WORKFLOW_URI:
                content, mime = workflow, 'text/markdown'
            elif uri in {'project-hub://instructions/'+name for name in ('manifest','workflow','user-additions','bootstrap','api-reference')}:
                from agent_instructions import bundle
                snapshot = bundle(registry,base)['instructionBundle']
                name = uri.rsplit('/',1)[1]
                content = json.dumps(snapshot['manifest'],ensure_ascii=False) if name=='manifest' else snapshot['files'][{'workflow':'workflow.md','user-additions':'user-additions.md','bootstrap':'bootstrap.md','api-reference':'api-reference.md'}[name]]
                mime = 'application/json' if name=='manifest' else 'text/markdown'
            else:
                raise ProtocolError(-32602,'Unknown resource URI')
            result = dict(contents=[dict(uri=uri,mimeType=mime,text=content)])
        elif method=='tools/call':
            fields(params,('name','arguments'),('name',))
            if not isinstance(params['name'],str) or params['name'] not in {item['name'] for item in tools()}:
                raise ProtocolError(-32602,'Unknown tool name')
            try:
                value = call(registry,credential,params['name'],params.get('arguments',{}),base=base)
                result = dict(content=[dict(type='text',text=json.dumps(value,ensure_ascii=False))],isError=False)
                if isinstance(value,dict):
                    result['structuredContent'] = value
            except (HubError, BindingError) as failure:
                result = dict(content=[dict(type='text',text=json.dumps(failure.body,ensure_ascii=False))],isError=True)
            except (ValueError,TypeError,KeyError) as failure:
                result = dict(content=[dict(type='text',text=json.dumps(dict(error='invalid_arguments',message=str(failure)[:240])))],isError=True)
            except (OSError,sqlite3.Error):
                result = dict(content=[dict(type='text',text=json.dumps(dict(error='unavailable',message='Hub storage is temporarily unavailable; continue work and retry later')))],isError=True)
        else:
            raise ProtocolError(-32601,'Method not found',404)
        if version==MODERN:
            result = dict(result,resultType='complete',_meta={META_INFO:SERVER_INFO})
        return 200,dict(jsonrpc='2.0',id=identifier,result=result)
    except ProtocolError as failure:
        return failure.status,error(identifier,failure.code,str(failure),failure.data)
    except BindingError as failure:
        return failure.status,error(identifier,-33001,str(failure),failure.body)
