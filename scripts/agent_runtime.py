"""Logical project admission for any agent with a local Hub connection.

Client conversation IDs are namespaced into separate Hub actors. They are
client-reported identifiers, never evidence of native chat authenticity.
"""
from copy import deepcopy
import hashlib
import json
import sqlite3
from pathlib import Path
import time

from agent_bindings import BindingError, Connections, text
from plugin_api import ServerHub, compact_write_ack, _notice_dependencies
from hub_core import HubError, canonical, git_common
from hub_plugin import Mcp, TOOLS
from task_transfer import barrier


def actor_id(binding, conversation, project=None):
    identity = [binding,text(conversation,'session')]
    if project is not None:
        identity.append(project)
    return hashlib.sha256(json.dumps(identity,ensure_ascii=True).encode()).hexdigest()


def tools():
    result = deepcopy(TOOLS)
    local_bookkeeping = {'hub_context','hub_memory','hub_notice','hub_wait','hub_migration_preview',
        'hub_task','hub_plan','hub_begin','hub_report','hub_review','hub_check','hub_artifact','hub_image','hub_task_close'}
    for tool in result:
        if tool['name'] in local_bookkeeping:
            # Session registration and journal publication are writes, but their
            # effects stay in the enrolled local project and retain history.
            tool['annotations'] = dict(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
        if tool['name'] == 'hub_context':
            tool['description'] = ('Read compact project context, current settings, relevant tasks and team observations. '
                'Supply your own current conversation session on every call: use its native ID when exposed, otherwise '
                'generate one unique ID and retain it for this conversation. Child agents use their own distinct IDs. '
                'Global connections select an explicit project and optional registered code workspace on every request. '
                'Use hub_projects to discover registered projects; never infer one from another conversation. '
                'Verify connection.project and connection.actor; never reuse another actor or infer identity from the MCP process. '
                'If unavailable, continue authorized work and disclose the recording gap.')
        schema = tool['inputSchema']
        schema['properties']['session'] = dict(type='string',minLength=1,maxLength=128,
            description='Your current conversation ID. Use a native ID when exposed, otherwise generate a unique ID for this conversation. Never reuse another conversation or parent agent ID.')
        schema['required'] = list(dict.fromkeys([*schema.get('required',[]),'session']))
        if tool['name'] in ('hub_context','hub_task','hub_task_update','hub_plan','hub_begin','hub_report','hub_task_close'):
            schema['properties']['nativeChat'] = dict(type='object', additionalProperties=False,
                properties={key:dict(type='string',maxLength=2000 if key=='openUri' else 256)
                    for key in ('client','clientInstance','host','nativeId','openUri','title','model')},
                description='Required when the host exposes the current chat: send its actual client/nativeId or verified openUri and available title. Keep this current on eligible calls. If unavailable, omit unknown fields and report the gap; never substitute a Hub actor, generated session or parent ID.')
        if tool['name'] == 'hub_task_link':
            schema['properties']['targetProject'] = deepcopy(schema['properties'].get('project',dict(type='string')))
        schema['properties']['project'] = dict(type=['string','null'] if tool['name']=='hub_task_link' else 'string',minLength=1,maxLength=128,
            description='Registered project ID for this request. Required for a global connection unless workspace selects exactly one registered project. Never select implicitly from prior calls.')
        schema['properties']['workspace'] = dict(type='string',
            description='Optional existing registered absolute server code folder for this request. A workspace shared by several projects requires explicit project.')
        schema['properties']['bindingId'] = dict(type='string',minLength=1,maxLength=128)
        schema['properties']['projectScope'] = dict(type='object',description='Actual current native project scope; required on hub_context for a bound project. Client-reported, not native identity proof.')
        schema['properties']['bindingRevision'] = dict(type='integer',minimum=1,
            description='Current project binding revision; read hub_context before scoped work, refresh on conflict.')
    result.append(dict(name='hub_projects',description='List available registered projects for this connection, without their tasks or documents. Global connections select a returned project explicitly on every project tool request. Native client identity and model are client-reported.',
        inputSchema=dict(type='object',properties=dict(session=dict(type='string',minLength=1,maxLength=128)),required=['session'],additionalProperties=False),
        annotations=dict(readOnlyHint=True,destructiveHint=False,openWorldHint=False)))
    result.append(dict(name='hub_connection', description='Read or describe this global client connection, supported interfaces, optional external chat and consented persistent-rule setup. No project is required. Self-reported capabilities are claims; credentials belong in administrator settings, never the profile.',
        inputSchema=dict(type='object',properties=dict(session=dict(type='string',minLength=1,maxLength=128),
            action=dict(type='string',enum=['read','describe']),profile=dict(type='object')),
            required=['session','action'],additionalProperties=False),
        annotations=dict(readOnlyHint=False,destructiveHint=False,openWorldHint=False)))
    result.append(dict(name='hub_instructions', description='Read the current instruction manifest or full verified snapshot without selecting a project. Compare revisions by equality; persist separate workflow and user-addition files, and a short native global rule.',
        inputSchema=dict(type='object', properties=dict(session=dict(type='string',minLength=1,maxLength=128),
            action=dict(type='string',enum=['manifest','read'])), required=['session','action'],additionalProperties=False),
        annotations=dict(readOnlyHint=True,destructiveHint=False,openWorldHint=False)))
    result.append(dict(name='hub_project_bindings', description='Manage this connection\'s scoped Hub project mappings. Resolve once per new project, persist the canonical ID in native project rules. Names are not identity. Update/rebind/repair/unbind requires expectedRevision and a stable hexadecimal requestId; unbind leaves a tombstone. Verify is a client report, not proof of loading.',
        inputSchema=dict(type='object',properties=dict(session=dict(type='string',minLength=1,maxLength=128),
            action=dict(type='string',enum=['list','read','history','workspaces','resolve','create','update','relocate','resume','verify','repair','unbind']),
            bindingId=dict(type='string'),project=dict(type='string'),name=dict(type='string'),
            scope=dict(type='object',additionalProperties=False,properties=dict(kind=dict(type='string',enum=['workspace','project']),root=dict(type='string'),nativeRef=dict(type='string')),required=['kind']),
            expectedRevision=dict(type='integer',minimum=1),requestId=dict(type='string',pattern='^[0-9a-f]{32}$'),
            expectedProjectRevision=dict(type='integer',minimum=1),workspaceId=dict(type='string'),
            rulePath=dict(type='string'),status=dict(type='string',enum=['saved','missing','manual'])),
            required=['session','action'],additionalProperties=False),annotations=dict(readOnlyHint=False,destructiveHint=False,openWorldHint=False)))
    result.append(dict(name='hub_launch',description='Read, acknowledge or finish a typed request launched from Hub. Read hub_context in the actual bound native scope first. ACK correlates this request and real native chat; research completion publishes only to the fixed Hub result document with its captured revision. Task completion references an already saved owned hub_report.',
        inputSchema=dict(type='object',properties=dict(session=dict(type='string',minLength=1,maxLength=128),
            action=dict(type='string',enum=['read','ack','complete','fail']),requestId=dict(type='string'),
            projectScope=dict(type='object'),nativeId=dict(type='string'),result=dict(type=['object','string']),work=dict(type='string'),revision=dict(type='integer')),
            required=['session','action','requestId'],additionalProperties=False),annotations=dict(readOnlyHint=False,destructiveHint=False,openWorldHint=False)))
    from agent_contracts import enrich_tools
    return enrich_tools(result)


class AgentHub(ServerHub):
    def __init__(self, registry, binding, actor):
        super().__init__(registry, resolve_host=False)
        self.binding, self.actor = binding, actor
        self.project_id = binding['project']
        self.project = Connections(registry).project(self.project_id)
        self.workspace = binding['metadata'].get('workspace')

    def available_workspaces(self):
        from project_workspaces import local_access
        return local_access(self.registry, self.project_id, [Path(root) for root in self.project['roots']])['available']

    def workspace_available(self):
        if self.workspace is None:
            return False
        from project_workspaces import no_reparse, WorkspaceError
        try:
            path=Path(self.workspace)
            no_reparse(path)
            return path.is_dir() and any(path == Path(root) or path.is_relative_to(Path(root))
                for i,root in enumerate(self.project['roots']) if str(i) in self.available_workspaces())
        except (OSError, WorkspaceError):
            return False

    def locate(self, cwd=None):
        available=self.available_workspaces()
        roots = [root for i,root in enumerate(self.project['roots']) if str(i) in available]
        bound=next((root for root in roots if self.workspace and Path(self.workspace).is_relative_to(Path(root))),None)
        primary = canonical(bound or roots[0]) if roots else None
        return dict(id=self.project_id,root=primary,git_common=None,workspace_root=self.workspace,
                    guard_roots=[(root,'' if i==0 else self.root_prefix(root)) for i,root in enumerate(roots)])

    def verified_read_binding(self, session, cwd=None):
        if session != self.actor:
            return False
        with self.connect() as c:
            row = c.execute('SELECT project,workspace FROM sessions WHERE id=?',(session,)).fetchone()
        return row is not None and row['project']==self.project_id and row['workspace']==self.workspace

    def reconcile_session(self, session, cwd=None):
        if session != self.actor:
            raise HubError('binding_identity_mismatch','Use the actor assigned to this conversation')
        if self.verified_read_binding(session):
            if not getattr(self,'defer_outbox_for_read',False):
                with self.transaction() as c:
                    c.execute("UPDATE sessions SET seen=?,state='active' WHERE id=?",(time.time(),session))
            return dict(registered=True)
        available = self.available_workspaces()
        roots = [root for index, root in enumerate(self.project['roots']) if str(index) in available]
        primary = canonical(roots[0]) if roots else None
        common = git_common(primary) if primary else None
        with self.transaction() as c:
            existing = c.execute('SELECT project FROM sessions WHERE id=?',(session,)).fetchone()
            if existing and existing['project']!=self.project_id:
                raise HubError('binding_project_mismatch','Conversation belongs to another project')
            # Legacy root discovery has one owner per folder. MCP routes by
            # canonical ID and uses registry workspaces, so a second explicit
            # project can share the folder without stealing that legacy owner.
            owner = c.execute('SELECT id FROM projects WHERE root=?',(primary,)).fetchone() if primary else None
            if owner and owner['id']!=self.project_id:
                primary, common = None, None
            c.execute('''INSERT INTO projects VALUES(?,?,?) ON CONFLICT(id) DO UPDATE
                         SET root=excluded.root,git_common=excluded.git_common''',(self.project_id,primary,common))
            if self.workspace:
                c.execute('INSERT OR IGNORE INTO workspace_bindings VALUES(?,?)',(self.project_id,canonical(self.workspace)))
            c.execute('''INSERT INTO sessions(id,project,workspace,state,seen) VALUES(?,?,?,'active',?)
                         ON CONFLICT(id) DO UPDATE SET workspace=excluded.workspace''',
                      (session,self.project_id,self.workspace,time.time()))
            if not existing:
                self.emit(c,self.project_id,session,'McpConnect',dict(binding=self.binding['id'],
                    client=self.binding['client'],nativeIdentity=self.binding.get('nativeIdentity','client-reported')))
        return dict(registered=True)

    def ensure_session(self, session, cwd=None):
        return self.reconcile_session(session)

    def context(self, session, *args, **kwargs):
        result = super().context(session,*args,**kwargs)
        if not args or args[0] is None:
            result['connection'] = dict(binding=self.binding['id'],client=self.binding['client'],
                actor=session,project=self.project_id,scope=self.binding.get('scope','project'),
                nativeIdentity=self.binding.get('nativeIdentity','client-reported'),kind=self.binding.get('kind','external-app'))
            result['workspace']['available'] = self.workspace_available()
            if not result['workspace']['available']:
                result['workspace']['reasonCode'] = 'workspace_required' if self.workspace is None else 'workspace_unavailable'
        return result

    def require_task_context(self, session, task):
        if not self.registry.store(self.project_id).task_context(task)['tasks']:
            raise HubError('task_missing','Choose a task in the connected project')

    def link_task(self, session, task, target, type, expected, project=None):
        if project is not None and project != self.project_id:
            raise HubError('project_unavailable','This connection is scoped to one project')
        return super().link_task(session,task,target,type,expected,project)

    def require_files(self, path, *, archive=False):
        if not isinstance(path,str):
            raise HubError('invalid_evidence','Use a source reference or a project-relative path')
        if path.startswith(('hub-artifact/','knowledge/')):
            return
        store = self.registry.store(self.project_id)
        origin,relative = store.evidence_origin(path) if path.startswith('hub-source/') else (store,path)
        if relative.startswith(('hub-artifact/','knowledge/')):
            return
        if archive:
            from source_snapshots import entry_for
            if entry_for(origin,relative):
                return
        if not self.workspace_available():
            raise HubError('workspace_required','Connect a code workspace or use an uploaded immutable artifact')
        resolved = origin.resolve_path(relative)
        if not resolved.is_relative_to(Path(self.workspace).resolve()):
            raise HubError('workspace_scope','Source path is outside this connection code workspace')

    def preflight(self, tool, arguments):
        if tool == 'hub_memory':
            ref = arguments.get('ref','')
            if isinstance(ref,str) and ref.startswith(('source:','source-archive:','source-version:')):
                if ref.startswith('source-version:'):
                    parts=ref.split(':',3)
                    if len(parts)==4:self.require_files(parts[3],archive=parts[1]=='archive')
                else:self.require_files(ref.split(':',1)[1],archive=ref.startswith('source-archive:'))
        if tool == 'hub_task_update' and isinstance(arguments.get('patch'),dict):
            for source in arguments['patch'].get('sources',[]):
                if isinstance(source,dict) and 'path' in source:self.require_files(source['path'])

    def knowledge(self, session, action, args=None):
        if not self.workspace_available() and action in ('scan','source-location','import-preview','research'):
            raise HubError('workspace_required','Connect a code workspace for local source import and analysis')
        if action=='import-preview' and isinstance(args,dict):
            for path in args.get('paths',[]):self.require_files(path)
        return super().knowledge(session,action,args)

    def validate_report_evidence(self, evidence, project):
        for path in evidence:
            self.require_files(path)
        return super().validate_report_evidence(evidence,project)

    def attach_artifact(self, session, task, path, expected, **kwargs):
        self.require_files(path)
        return super().attach_artifact(session,task,path,expected,**kwargs)

    def attach_image(self, session, task, path, expected, **kwargs):
        self.require_files(path)
        return super().attach_image(session,task,path,expected,**kwargs)

    def git_batch(self, session, **args):
        if not self.workspace_available():
            raise HubError('workspace_required','Connect an accessible code workspace for Git operations')
        return super().git_batch(session,**args)

    def migration_preview(self, session):
        if not self.workspace_available():
            raise HubError('workspace_required','Connect a code workspace for local source migration')
        return super().migration_preview(session)


def call(registry, credential, tool, arguments, *, base=None):
    connections = Connections(registry)
    binding = connections.authenticate(credential)
    return _call_bound(registry, binding, tool, arguments, base=base,
                       reauthenticate=lambda:connections.authenticate(credential))


def call_internal_research(registry, project, tool, arguments):
    """Trusted in-process host work; never an external bearer credential or app.

    This entry point is not exposed by HTTP/MCP. The principal is stable per
    project, while the supplied API action session retains separate actor history.
    """
    allowed = {'hub_context','hub_knowledge'}
    if tool not in allowed or not isinstance(arguments,dict) or any(
            key in arguments for key in ('bindingId','bindingRevision','projectScope','nativeChat','workspace')):
        raise HubError('internal_scope_denied','Internal research has a fixed project and no client controls')
    if tool == 'hub_knowledge' and arguments.get('action') not in {'context','search','read','history','research-object'}:
        raise HubError('internal_scope_denied','Internal research tools only read knowledge')
    connections = Connections(registry)
    connections.project(project)
    identifier = 'hub-research:' + hashlib.sha256(project.encode()).hexdigest()
    binding = dict(id=identifier, project=project, client='hub', scope='project', metadata={},
                   nativeIdentity='hub-owned', kind='internal-service')
    return _call_bound(registry,binding,tool,arguments,
                       reauthenticate=lambda:connections.project(project))


def _call_bound(registry, binding, tool, arguments, *, base=None, reauthenticate):
    if not isinstance(arguments,dict) or 'session' not in arguments:
        raise HubError('identity_missing','Supply your own current conversation ID as session')
    arguments = dict(arguments)
    conversation = arguments.pop('session')
    connections = Connections(registry)
    from storage_operations import status
    storage_status = status(registry)
    storage_paused = storage_status['writesPaused']
    read_plan_request = tool == 'hub_plan' and set(arguments) <= {'task', 'expected', 'project', 'workspace'}
    read_connection = tool == 'hub_connection' and arguments.get('action') == 'read'
    read_bindings = tool == 'hub_project_bindings' and arguments.get('action') in ('list','read','history','workspaces')
    read_launch = tool == 'hub_launch' and arguments.get('action')=='read'
    if storage_paused and tool not in ('hub_projects','hub_instructions') and not read_plan_request and not read_connection and not read_bindings and not read_launch:
        code = 'backup_in_progress' if storage_status.get('reason') == 'backup_snapshot' else 'storage_operation_in_progress'
        raise HubError(code, 'Viewing remains available; retry changes after the storage operation completes', retryable=True)
    # Validate the caller's own ID even for global discovery, before any data read.
    text(conversation,'session')
    if tool == 'hub_instructions':
        from agent_instructions import bundle, connection_context
        if set(arguments) != {'action'} or arguments['action'] not in ('manifest','read'):
            raise HubError('invalid_request','Use manifest or read')
        snapshot = bundle(registry,base)
        descriptor=connection_context(binding['id'],base)
        return dict(snapshot['instructionManifest'],connectionContext=descriptor) if arguments['action']=='manifest' else dict(snapshot['instructionBundle'],connectionContext=descriptor)
    if tool == 'hub_project_bindings':
        from project_bindings import ProjectBindings
        return ProjectBindings(registry).execute(binding['id'],arguments)
    if tool == 'hub_launch':
        from agent_launches import Launches
        return Launches(registry,base).execute(binding['id'],conversation,arguments)
    if tool == 'hub_connection':
        from connection_capabilities import Profiles
        profiles = Profiles(registry)
        action = arguments.pop('action', None)
        if action == 'read' and not arguments:
            if not storage_paused:
                connections.observed_request(binding)
            binding['last_seen'] = time.time()
            return profiles.public(binding['id'], binding=binding)
        if action == 'describe' and set(arguments) == {'profile'}:
            result = profiles.describe(binding['id'], arguments['profile'], binding=binding, base=base)
            connections.observed_request(binding)
            return result
        raise HubError('invalid_request', 'Use read or describe with a profile')
    if tool == 'hub_projects':
        if arguments:
            raise HubError('invalid_request','hub_projects accepts only your current session')
        return dict(scope=binding['scope'],projects=connections.projects(binding),nativeIdentity='client-reported')
    global_connection = binding['scope'] == 'global'
    project = arguments.pop('project',None) if global_connection or tool != 'hub_task_link' else None
    project_binding_id = arguments.pop('bindingId',None)
    project_binding_revision = arguments.pop('bindingRevision',None)
    project_scope = arguments.pop('projectScope',None)
    from project_bindings import ProjectBindings
    project_bindings = ProjectBindings(registry)
    if project_binding_id: project_bindings.ensure_ready(binding['id'],project_binding_id)
    selected,workspace = connections.select_project(binding,project,arguments.pop('workspace',None))
    if (project_binding_id is None) != (project_binding_revision is None):
        raise BindingError('project_binding_required','Supply bindingId and bindingRevision together',409)
    if project_binding_id is None and any(item['project']==selected['id'] for item in project_bindings.list(binding['id'])):
        raise BindingError('project_binding_required','Use the registered project binding for this connection',409)
    explicit_native_chat = 'nativeChat' in arguments
    native_chat = arguments.pop('nativeChat', None)
    from connection_capabilities import Profiles
    connection_profile = Profiles(registry).profile(binding['id'])
    if native_chat is not None:
        from native_chats import normalize
        native_chat = normalize(native_chat, client=binding['client'],
            uri_template=connection_profile.get('capabilities', {}).get('openChat', {}).get('uriTemplate'))
    else:
        native_chat = connection_profile.get('nativeChat')
    if tool == 'hub_task_link' and 'targetProject' in arguments:
        target_project = arguments.pop('targetProject')
        if 'project' in arguments and arguments['project'] != target_project:
            raise HubError('invalid_request','Conflicting target project fields')
        arguments['project'] = target_project
    actor = actor_id(binding['id'],conversation,selected['id'] if global_connection else None)
    recorded_native_chat = False
    if not explicit_native_chat and (not native_chat or native_chat.get('nativeId') != conversation):
        from native_chats import for_actor
        native_chat = for_actor(registry, selected['id'], actor)
        recorded_native_chat = native_chat is not None
    binding = dict(binding,project=selected['id'],metadata=dict(binding['metadata'],workspace=workspace))
    hub = AgentHub(registry,binding,actor)
    hub.preflight(tool,arguments)
    read_plan = tool=='hub_plan' and set(arguments)<={'task','expected'}
    from contextlib import nullcontext
    ready = read_plan and hub.verified_read_binding(actor)
    if ready:
        with hub.connect() as c:
            ready = c.execute('SELECT 1 FROM plan_outbox LIMIT 1').fetchone() is None
        ready = ready and next((hub.home/'outbox').glob('*.json'),None) is None
    if not ready:
        from backup_session import active
        if active(registry) is not None:
            raise HubError('backup_in_progress','Snapshot writes are paused; continue work and retry after the snapshot',retryable=True)
    with nullcontext() if ready else barrier(registry):
        # Mutating requests recheck revocation under the administrative barrier.
        if not ready:
            reauthenticate()
        if project_binding_id:
            project_bindings.validate(binding['id'],conversation,project_binding_id,project_binding_revision,
                                      selected['id'],workspace,start=tool=='hub_context',scope=project_scope)
        hub.defer_outbox_for_read = ready
        mcp = Mcp(hub,session=actor)
        mcp.cwd = hub.workspace
        result = compact_write_ack(tool,mcp.call(tool,arguments))
        if project_binding_id and isinstance(result,dict):
            result['projectBinding'] = dict(bindingId=project_binding_id,revision=project_binding_revision,project=selected['id'])
        if native_chat and isinstance(result, dict) and not storage_paused:
            from native_chats import register
            # Only an explicit per-conversation resource is associated. A profile's
            # current chat applies only when its native ID matches this conversation.
            usable = explicit_native_chat or recorded_native_chat or native_chat.get('nativeId') == conversation
            if usable:
                task = arguments.get('task') or (result.get('task') if tool == 'hub_task' else None)
                stage = arguments.get('stage')
                if isinstance(stage, dict):
                    stage = stage.get('id')
                clean_chat = {key:value for key,value in native_chat.items() if key in
                              ('client','clientInstance','host','nativeId','openUri','title','model')}
                if not task and arguments.get('work'):
                    with hub.connect() as c:
                        own_work = c.execute('SELECT task FROM work WHERE id=? AND project=?', (arguments['work'], selected['id'])).fetchone()
                        work_stage = c.execute('SELECT stage FROM work_stages WHERE work=?', (arguments['work'],)).fetchone()
                    if own_work:
                        task, stage = own_work['task'], work_stage['stage'] if work_stage else None
                try:
                    result['nativeChat'] = register(registry,selected['id'],actor,clean_chat,task=task,stage=stage,client=binding['client'])
                except (BindingError, OSError, sqlite3.Error, ValueError):
                    # The core task write may have committed already. Report a link
                    # recording gap without falsely rejecting the acknowledged write.
                    result['nativeChatRegistration'] = dict(saved=False, retryable=True)
        if tool in ('hub_context', 'hub_begin', 'hub_report') and isinstance(result, dict):
            saved_chat = result.get('nativeChat') or {}
            result['chatContext'] = dict(status='reported' if saved_chat else 'unreported',
                titleAvailable=bool(saved_chat.get('title')), openingAvailable=bool(saved_chat.get('openUri')))
            if not saved_chat:
                result['chatContext']['action'] = ('Send nativeChat with the actual current chat identity and available title '
                    'from the host metadata interface. If the host does not expose it, report that gap once; '
                    'never invent an ID/title/link or reuse the parent identity. Continue authorized work.')
        if not ready:
            connections.observed_request(binding)
        if tool in ('hub_context','hub_begin','hub_report') and isinstance(result,dict):
            from agent_instructions import bundle
            result['instructionManifest'] = bundle(registry,base)['instructionManifest']
            from hub_notices import wait,refresh_all
            try:
                dependencies = _notice_dependencies(hub,actor)
                if tool in ('hub_begin','hub_report'):
                    refresh_all(hub,{hub.project_id:dependencies},project=hub.project_id)
                result['parallelNotices'] = wait(hub,actor,0,0,max_bytes=1500,dependencies=dependencies)
            except (OSError,sqlite3.Error,ValueError,HubError):
                result['parallelNotices'] = dict(unavailable=True,description='Advisory notices unavailable; continue work')
        return result
