"""Typed Hub-to-client requests over configured HTTP/MCP control interfaces."""
import hashlib
import json
import time

from agent_bindings import BindingError, Connections, fingerprint, text
from connection_capabilities import Profiles, HttpControl, visibility_evidence
from native_chats import open_uri, template_uri
from hub_action_context import HubActionContext
from project_bindings import ProjectBindings
from task_transfer import barrier
from outbound_http import OutboundError


class Launches:
    ACTIVE = frozenset({'dispatching','dispatch_unknown','awaiting_ack','accepted'})
    def __init__(self, registry, base=None):
        self.registry, self.base = registry, base
        self.bindings, self.profiles = ProjectBindings(registry), Profiles(registry)

    def setup(self):
        with self.registry.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS agent_launches(
                id TEXT PRIMARY KEY,connection TEXT NOT NULL,project TEXT NOT NULL,
                binding TEXT NOT NULL,revision INTEGER NOT NULL,request_hash TEXT NOT NULL,
                body TEXT NOT NULL,updated REAL NOT NULL)''')

    def read(self, connection, identifier):
        with self.registry.connect() as c:
            exists = c.execute("SELECT 1 FROM sqlite_master WHERE name='agent_launches'").fetchone()
            row = c.execute('SELECT * FROM agent_launches WHERE id=? AND connection=?',(identifier,connection)).fetchone() if exists else None
        if row is None: raise BindingError('launch_missing','Unknown request for this connection',404)
        return dict(row,body=json.loads(row['body']))

    def list(self, connection):
        with self.registry.connect() as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='agent_launches'").fetchone(): return []
            rows = c.execute('SELECT body FROM agent_launches WHERE connection=? ORDER BY updated DESC LIMIT 30',(connection,)).fetchall()
        return [json.loads(row['body']) for row in rows]

    @staticmethod
    def action_ready(profile, config, name):
        spec = profile.get('capabilities', {}).get(name) or {}
        placeholders = json.dumps(spec.get('arguments', {}))
        return bool(config and profile.get('control') == {key:config[key] for key in ('protocol','endpoint')} and
                    spec.get('projectRouting') is True and '$requestId' in placeholders and '$prompt' in placeholders and
                    (name != 'sendMessage' or '$nativeId' in placeholders) and
                    any(key in placeholders for key in ('$projectScope','$nativeProject','$workspace')) and
                    spec.get('tool' if config['protocol'] == 'mcp-http' else 'path'))

    def task_input(self, project, task, stage=None):
        self.bindings.connections.project(project)
        state = self.registry.store(project).task_context(task)
        item = next((t for t in state['tasks'] if t['id'] == task), None)
        if item is None:
            raise BindingError('task_missing','Task is outside the selected Hub project',404)
        selected = next((s for s in item.get('stages', []) if s['id'] == stage), None)
        if stage and selected is None:
            raise BindingError('stage_missing','Stage is outside the selected task',404)
        # Keep execution scope, not historical reports, activity or whole-plan
        # results. The agent can read the authoritative task through MCP.
        snapshot = {key:item[key] for key in ('id','title','scope','acceptance','status','priority') if key in item}
        snapshot['sources'] = [{key:s[key] for key in ('path','label','sourceProject') if key in s}
                               for s in item.get('sources', [])[:20]]
        stages = [selected] if selected else item.get('stages', [])[:40]
        snapshot['stages'] = [{key:s[key] for key in ('id','title','status','remaining') if key in s} for s in stages]
        return dict(task=snapshot, revision=state['revision'])

    def task_rows(self, project, task):
        with self.registry.connect() as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='agent_launches'").fetchone(): return []
            rows = c.execute('''SELECT connection,body FROM agent_launches WHERE project=?
                AND json_extract(body,'$.envelope.operation')='task-execute'
                AND json_extract(body,'$.envelope.resultDestination.task')=? ORDER BY updated DESC LIMIT 100''',
                (project,task)).fetchall()
        return [dict(json.loads(row['body']), connection=row['connection']) for row in rows]

    def related_chats(self, project, task):
        """Explicit task/stage provenance, never inferred from message text."""
        from native_chats import linked, for_actor, normalize, UUID
        store = self.registry.store(project)
        state = store.task_context(task)
        item = next((t for t in state['tasks'] if t['id'] == task), None)
        if item is None:
            raise BindingError('task_missing', 'Task is outside the selected Hub project', 404)
        stages = {s['id'] for s in item.get('stages', [])}
        result = []
        for link in linked(self.registry, project):
            if link['task'] == task and (link['stage'] is None or link['stage'] in stages):
                result.append(dict(native=link['resource'], stage=link['stage'],
                                   scope='stage' if link['stage'] else 'task'))
        creator = (item.get('createdBy') or {}).get('session')
        if creator:
            native = for_actor(self.registry, project, creator)
            if native:
                result.append(dict(native=native, stage=None, scope='task'))
        # Older native-hook tasks retain their real session IDs. Only the
        # application's project catalogue may establish those legacy identities.
        legacy = {}
        for actor in [creator, *item.get('participatingSessions', [])]:
            if isinstance(actor, str) and UUID.fullmatch(actor):
                legacy.setdefault(actor, set()).add(None)
        from task_chats import event_session
        events = list(state.get('allEvents', state.get('events', [])))
        missing = stages - {link['stage'] for link in result if link['stage']}
        before = None
        while missing:
            page = self.registry.read_models.history(project, task=task, kind='stage.created', before=before, limit=100)
            for event in page['events']:
                stage = event.get('stageId')
                if stage not in missing: continue
                missing.remove(stage)
                actor = event_session(event)
                native = for_actor(self.registry, project, actor) if actor else None
                if native:
                    result.append(dict(native=native, stage=stage, scope='stage'))
                events.append(event)
            before = page.get('next')
            if before is None: break
        for event in events:
            actor = event_session(event)
            if event.get('taskId') == task and actor and UUID.fullmatch(actor):
                stage = event.get('stageId')
                if stage is None or stage in stages:
                    legacy.setdefault(actor, set()).add(stage)
        if legacy:
            from codex_session_catalog import CATALOG
            catalog = CATALOG.read_project(self.registry, project, [], {}, include_archived=True)
            for row in catalog.get('sessions', []):
                if row['id'] in legacy:
                    native = normalize(dict(client='codex', nativeId=row['id'], title=row.get('title') or row.get('name')),
                                       provenance='codex-catalog')
                    for stage in legacy[row['id']]:
                        result.append(dict(native=native, stage=stage, scope='stage' if stage else 'task'))
        return result

    @staticmethod
    def matching_client(native, client, profile):
        def family(value):
            value = (value or '').casefold()
            return 'codex' if value in ('codex', 'codex-desktop', 'codex-desktop-bridge') else value
        if not native.get('nativeId') or family(native.get('client')) != family(client):
            return False
        for key in ('clientInstance', 'host'):
            if native.get(key) and profile.get(key) and native[key] != profile[key]:
                if key != 'host' or {native[key], profile[key]} != {'local', 'codex'}:
                    return False
        return True

    def chat_busy(self, connection, native_id):
        with self.registry.connect() as c:
            if not c.execute("SELECT 1 FROM sqlite_master WHERE name='agent_launches'").fetchone():
                return False
            return c.execute('''SELECT 1 FROM agent_launches WHERE connection=?
                AND (json_extract(body,'$.nativeId')=? OR json_extract(body,'$.targetNativeId')=?)
                AND json_extract(body,'$.status') IN ('dispatching','dispatch_unknown','awaiting_ack','accepted') LIMIT 1''',
                (connection, native_id, native_id)).fetchone() is not None

    def continuation(self, connection, binding, task, native_id, stage=None, *, related=None, rows=None):
        items = [item for item in (self.task_rows(binding['project'],task) if rows is None else rows)
                 if item['connection'] == connection and (item.get('nativeId') or item.get('targetNativeId')) == native_id]
        if self.chat_busy(connection, native_id):
            raise BindingError('native_chat_busy','The previous launch has not finished; inspect its outcome before continuing',409)
        profile = self.profiles.profile(connection)
        client = self.profiles.binding(connection)['client']
        for link in (self.related_chats(binding['project'], task) if related is None else related):
            native = link['native']
            if (native.get('nativeId') == native_id and self.matching_client(native, client, profile) and
                    (link['scope'] == 'task' or link['stage'] == stage)):
                return dict(kind='related', nativeId=native_id, task=task, stage=stage)
        for item in items:
            if (item['status'] in ('completed','failed') and item.get('ackSession') and item.get('nativeRoutingVerified') and
                item['envelope']['resultDestination'].get('stage') == stage):
                self.check_route(connection,item)
                if item['envelope']['bindingId'] == binding['id']:
                    return item
        raise BindingError('native_project_unverified','Choose a recorded source or related chat of this task and selected stage',409)

    def task_state(self, project, task):
        self.task_input(project,task)
        routes = []
        for row in Connections(self.registry).catalog()['bindings']:
            if row.get('revoked'): continue
            for binding in row.get('projectBindings', []):
                if binding['project'] != project or binding['status'] != 'active' or binding.get('pendingRelocation'): continue
                profile, config = row.get('profile') or {}, row.get('control')
                create, send = (self.action_ready(profile,config,key) for key in ('createChat','sendMessage'))
                if not create and not send: continue
                routes.append(dict(connection=row['id'],bindingId=binding['id'],application=row.get('metadata',{}).get('label') or row['client'],
                                   workspace=binding['scope'].get('root') or binding['scope'].get('nativeRef'),canCreate=create,canContinue=send))
        launches, chats = [], []
        related, rows = self.related_chats(project, task), self.task_rows(project, task)
        for item in rows:
            envelope = item['envelope']
            summary = {key:item[key] for key in ('requestId','status','nativeId','sourceUri','apiAcceptedAt','acknowledgedAt',
                       'finishedAt','createdAt','nativeVisibility','result','resultRef','error','connection') if key in item}
            summary.update(bindingId=envelope['bindingId'],task=task,stage=envelope['resultDestination'].get('stage'),canContinue=False)
            if item.get('nativeId') and any(r['connection']==item['connection'] and r['bindingId']==envelope['bindingId'] and r['canContinue'] for r in routes):
                try:
                    binding=self.bindings.read(item['connection'],envelope['bindingId'])
                    self.continuation(item['connection'],binding,task,item['nativeId'],envelope['resultDestination'].get('stage'), related=related, rows=rows)
                    summary['canContinue']=True
                except BindingError: pass
            launches.append(summary)
            if summary['canContinue']:
                chats.append(dict(summary, id='launch:'+summary['requestId'], scope='stage', origin='launch'))
        for route in routes:
            if not route['canContinue']: continue
            binding = self.bindings.read(route['connection'], route['bindingId'])
            for link in related:
                native = link['native']
                try:
                    self.continuation(route['connection'], binding, task, native.get('nativeId'), link['stage'], related=[link], rows=rows)
                except BindingError:
                    continue
                chats.append(dict(id=fingerprint([route['connection'], route['bindingId'], native['nativeId'], link['stage']]),
                    connection=route['connection'], bindingId=route['bindingId'], nativeId=native['nativeId'],
                    title=native.get('title'), sourceUri=native.get('openUri'), task=task, stage=link['stage'],
                    scope=link['scope'], origin='related', canContinue=True))
        # A task link can also have a stage link. Keep one choice per relation;
        # the UI additionally deduplicates the selected stage by native ID.
        chats = list({(c['connection'], c['bindingId'], c['nativeId'], c.get('stage'), c['scope']):c for c in chats}.values())
        return dict(project=project,task=task,routes=routes,launches=launches,chats=chats)

    def _save(self, c, identifier, body):
        body['updatedAt'] = time.time()
        c.execute('UPDATE agent_launches SET body=?,updated=? WHERE id=?',(json.dumps(body,ensure_ascii=False),time.time(),identifier))

    def check_route(self, connection, body):
        self.profiles.binding(connection)
        envelope=body['envelope']
        self.bindings.ensure_ready(connection,envelope['bindingId'])
        binding=self.bindings.read(connection,envelope['bindingId'])
        if (binding['status']!='active' or binding['project']!=envelope['project'] or
            binding['revision']!=envelope['bindingRevision'] or binding['scope']!=envelope['projectScope']):
            raise BindingError('project_binding_conflict','Project routing changed; refresh the binding before a new launch',409)
        row=self.profiles._read('connection_controls',connection)
        config=json.loads(row['body']) if row else None
        profile=self.profiles.profile(connection)
        routing=dict(control=profile.get('control'),capabilities=profile.get('capabilities'))
        if fingerprint(config)!=body['controlRevision'] or fingerprint(routing)!=body['routingRevision']:
            raise BindingError('launch_configuration_changed','Client routing configuration changed; create a new request after reviewing it',409)

    def start(self, connection, args):
        if not isinstance(args,dict) or set(args)-{'requestId','bindingId','operation','task','stage','research','prompt','nativeId'} or not {'requestId','bindingId','operation'}<=set(args):
            raise BindingError('invalid_launch','Supply requestId, bindingId and a typed operation')
        identifier = args['requestId']
        import re
        if not isinstance(identifier,str) or not re.fullmatch('[0-9a-f]{32}',identifier):
            raise BindingError('invalid_launch','Use a unique hexadecimal requestId')
        signature = fingerprint(args)
        with barrier(self.registry):
            self.profiles.binding(connection)
            self.setup()
            with self.registry.connect() as c:
                previous=c.execute('SELECT * FROM agent_launches WHERE id=?',(identifier,)).fetchone()
            if previous:
                if previous['connection']!=connection or previous['request_hash']!=signature:
                    raise BindingError('launch_conflict','Request ID was reused with different context',409)
                return json.loads(previous['body'])
            binding = self.bindings.read(connection,args['bindingId'])
            self.bindings.ensure_ready(connection,binding['id'])
            if binding['status']!='active': raise BindingError('project_binding_conflict','Binding was deliberately unbound',409)
            self.bindings.connections.project(binding['project'])
            profile_row = self.profiles._read('connection_profiles',connection)
            profile = self.profiles.profile(connection)
            control_row = self.profiles._read('connection_controls',connection)
            config = json.loads(control_row['body']) if control_row else None
            action_name = 'sendMessage' if args.get('nativeId') else 'createChat'
            spec = profile.get('capabilities',{}).get(action_name)
            if not self.action_ready(profile,config,action_name):
                raise BindingError('project_launcher_unavailable','Configure a documented project-routing control action with requestId and project placeholders',409)
            operation = args['operation']
            continuation_source = None
            context = HubActionContext(self.registry,portal_url=self.base or 'http://127.0.0.1:8769')
            if operation=='task-execute':
                task = text(args.get('task'),'task',200)
                inputs = self.task_input(binding['project'],task,args.get('stage'))
                if args.get('nativeId'):
                    self.continuation(connection,binding,task,text(args['nativeId'],'native chat ID',128),args.get('stage'))
                    continuation_source = dict(kind='task-chat', nativeId=args['nativeId'], task=task, stage=args.get('stage'))
                destination = dict(kind='task-report',project=binding['project'],task=task,stage=args.get('stage'))
                bookkeeping = dict(mode='tracked')
            else:
                if args.get('nativeId'):
                    raise BindingError('native_project_unverified','Research continuation is not configured',409)
                from research_api import normalize
                research = args.get('research')
                if isinstance(research,dict) and 'revision' not in research:
                    from knowledge_store import KnowledgeStore
                    research = dict(research,revision=KnowledgeStore(self.registry,binding['project']).context()['revision'])
                research = normalize(research)
                if research['operation']!=operation: raise BindingError('invalid_launch','Research operation does not match')
                _, prompt, digest, fields = context._research_context(binding['project'],research,identifier,require_code=False)
                inputs = dict(research=research,context=json.loads(prompt.split('\n',1)[1]),revision=fields['knowledgeRevision'])
                destination = dict(kind='knowledge-document',project=binding['project'],id='doc:agent-result:'+identifier,
                                   objectId=research['objectId'],expectedRevision=fields['knowledgeRevision'])
                # Server-owned policy: internal Hub research must not create
                # user task, stage or work records.
                bookkeeping = dict(mode='internal',createTask=False,createStage=False,createWork=False)
            if len(json.dumps(inputs).encode())>18000: raise BindingError('launch_context_too_large','Select a smaller launch scope',409)
            user_prompt = args.get('prompt','')
            if not isinstance(user_prompt,str) or len(user_prompt)>6000: raise BindingError('invalid_launch','Prompt exceeds its limit')
            envelope = dict(schemaVersion=1,requestId=identifier,connection=connection,project=binding['project'],
                bindingId=binding['id'],bindingRevision=binding['revision'],projectScope=binding['scope'],operation=operation,
                inputs=inputs,resultDestination=destination,userPrompt=user_prompt,bookkeeping=bookkeeping)
            body = dict(requestId=identifier,status='dispatching',envelope=envelope,createdAt=time.time(),updatedAt=time.time(),
                        profileRevision=profile_row['revision'],controlRevision=fingerprint(config),
                        routingRevision=fingerprint(dict(control=profile.get('control'),capabilities=profile.get('capabilities'))),nativeRoutingVerified=False)
            if operation=='task-execute': body['inputHash']=fingerprint(inputs['task'])
            if args.get('nativeId'): body['targetNativeId']=args['nativeId']
            if continuation_source: body['continuationSource']=continuation_source
            with self.registry.connect() as c:
                c.execute('INSERT INTO agent_launches VALUES(?,?,?,?,?,?,?,?)',(identifier,connection,binding['project'],binding['id'],binding['revision'],signature,json.dumps(body),time.time()))
        # Persist before contacting the client. An uncertain network response
        # never triggers an automatic second chat creation.
        try:
            with barrier(self.registry): self.check_route(connection,body)
            key = None
            if config.get('credentialRef'):
                from secret_vault import get
                key = get(self.registry,config['credentialRef'])
            client = HttpControl(config,key)
            def observe(diagnostics):
                with barrier(self.registry), self.registry.connect() as c:
                    latest=self.read(connection,identifier)['body']
                    latest['diagnostics']=diagnostics
                    self._save(c,identifier,latest)
            client.observer=observe
            if config['protocol']=='mcp-http' and spec.get('tool') not in client.discover():
                raise ValueError('Configured control tool is unavailable')
            with barrier(self.registry): self.check_route(connection,body)
            prompt = ('User requested work from Project Hub. Read hub_launch(action="read", requestId="'+identifier+'") '
                      'through your enrolled MCP connection, verify actual projectScope, call hub_context and '
                      'hub_launch(action="ack") before work. Follow the saved global workflow and typed result destination. '
                      'For internal research launches, do not create or update any user task, plan stage or work record; '
                      'do not call hub_task, hub_plan, hub_begin, hub_report or hub_task_close. Use only the launch acknowledgement '
                      'and the designated knowledge result/history through hub_launch(action="complete"). '
                      'Task-execute launches use the normal tracked task pipeline. Work on the EXISTING task and selected stage; '
                      'do not create a replacement task. After ACK, begin new owned work, publish hub_report(status="done"), '
                      'then hub_launch(action="complete", requestId=..., nativeId=..., work=..., revision=<returned work revision>). '
                      'If unable to execute, call hub_launch(action="fail", nativeId=..., result=<reason>) after ACK.\n'
                      +json.dumps(envelope,ensure_ascii=False))
            if continuation_source:
                with barrier(self.registry), self.registry.connect() as c:
                    latest = self.read(connection, identifier)['body']
                    latest['dispatchPromptSha256'] = hashlib.sha256(prompt.encode('utf-8')).hexdigest()
                    self._save(c, identifier, latest)
            response = client.action(spec,{'$prompt':prompt,'$envelope':envelope,'$requestId':identifier,
                '$projectScope':binding['scope'],'$workspace':binding['scope'].get('root'),
                '$nativeProject':binding['scope'].get('nativeRef'),'$nativeId':args.get('nativeId')})
            native = response
            for part in spec.get('idField','id').split('.'):
                native = native.get(part) if isinstance(native,dict) else None
            if args.get('nativeId') and native is not None and native != args['nativeId']:
                raise BindingError('launch_routing_conflict','The control API returned another native chat',409)
            native = args.get('nativeId') or text(native,'created native chat ID',128)
            if key and key in native: raise BindingError('launch_routing_conflict','The control response was not safe',409)
            try:
                visibility=visibility_evidence(response.get('visibility') if isinstance(response,dict) else None,native,binding['project'],binding['scope'])
                uri=response.get('url') if isinstance(response,dict) else None
                if key and isinstance(uri,str) and key in uri: raise ValueError('Control response exposed its credential')
                template=profile.get('capabilities',{}).get('openChat',{}).get('uriTemplate')
                source=open_uri(uri) if uri else template_uri(template,native) if template else None
            except (ValueError,BindingError) as error:
                raise BindingError('launch_routing_conflict','The control response did not verify the selected native chat and project',409) from error
            with barrier(self.registry), self.registry.connect() as c:
                current = self.read(connection,identifier)['body']
                self.check_route(connection,current)
                if current.get('ackSession') and current.get('nativeId') and current['nativeId']!=native:
                    current.update(status='routing_conflict',nativeRoutingVerified=False)
                else:
                    current['nativeId']=native
                    if current['status']=='dispatching': current['status']='awaiting_ack'
                current['apiAcceptedAt']=time.time()
                if visibility: current['nativeVisibility']=visibility
                if source: current['sourceUri']=source
                self._save(c,identifier,current)
                return current
        except Exception as error:
            with barrier(self.registry), self.registry.connect() as c:
                current=self.read(connection,identifier)['body']
                if isinstance(error,BindingError): current.update(status='routing_conflict' if error.code=='launch_routing_conflict' else 'cancelled',nativeRoutingVerified=False,error='Connection, project binding or native routing changed during dispatch.')
                elif current['status']=='dispatching': current.update(status='dispatch_unknown',error='Native dispatch outcome is unknown; inspect the client before retrying.')
                if isinstance(error,OutboundError): current['transportError']=error.diagnostic
                self._save(c,identifier,current)
                return current

    def execute(self, connection, session, args):
        if not isinstance(args,dict) or set(args)-{'action','requestId','projectScope','nativeId','result','work','revision'}:
            raise BindingError('invalid_launch','Use a documented launch operation')
        action=args.get('action')
        body=self.read(connection,text(args.get('requestId'),'request ID'))['body']
        if action=='read': return body
        if action not in ('ack','complete','fail'): raise BindingError('invalid_launch','Use read, ack, complete or fail')
        envelope=body['envelope']
        with barrier(self.registry):
            self.profiles.binding(connection)
            self.check_route(connection,body)
            self.bindings.validate(connection,session,envelope['bindingId'],envelope['bindingRevision'],envelope['project'],
                                   envelope['projectScope'].get('root'),scope=args.get('projectScope'))
            body=self.read(connection,envelope['requestId'])['body']
            # The read model may refresh its own persisted snapshot. Build it
            # under the routing barrier, before taking the registry SQL writer.
            current_input_hash = None
            input_missing = False
            if action=='ack' and envelope['operation']=='task-execute' and not body.get('ackSession'):
                try:
                    current_input_hash=fingerprint(self.task_input(envelope['project'],envelope['resultDestination']['task'],envelope['resultDestination'].get('stage'))['task'])
                except BindingError as error:
                    if error.code not in ('task_missing','stage_missing'):
                        raise
                    input_missing = True
            with self.registry.connect() as c:
                c.execute('BEGIN IMMEDIATE')
                body=self.read(connection,envelope['requestId'])['body']
                if body['status'] in ('routing_conflict','cancelled'):
                    raise BindingError('launch_routing_conflict','Reconcile rejected routing before starting another request',409)
                if body.get('ackSession') and body['ackSession']!=session:
                    raise BindingError('launch_session_conflict','Another conversation acknowledged this request',409)
                if action=='ack':
                    if args.get('projectScope') is None: raise BindingError('project_scope_required','Acknowledge the actual current native project scope',409)
                    native=text(args.get('nativeId'),'native chat ID',128)
                    if body.get('nativeId') and body['nativeId']!=native:
                        raise BindingError('launch_routing_conflict','Control API and agent reported different native chats',409)
                    if not body.get('ackSession'):
                        if envelope['operation']=='task-execute' and (input_missing or body.get('inputHash') != current_input_hash):
                            body.update(status='cancelled',nativeRoutingVerified=False,error='Task or selected stage changed before acknowledgement.')
                            self._save(c,envelope['requestId'],body)
                            c.commit()
                            raise BindingError('launch_inputs_changed','Task or selected stage changed before acknowledgement; review a new launch',409)
                        body.update(ackSession=session,nativeId=native,status='accepted',nativeRoutingVerified=True,acknowledgedAt=time.time())
                else:
                    if not body.get('ackSession'): raise BindingError('launch_ack_required','Acknowledge this launch before publishing',409)
                    if args.get('nativeId')!=body.get('nativeId'):
                        raise BindingError('launch_native_identity_required','Terminal requests must identify the acknowledged native chat',409)
                    proof=fingerprint({key:args.get(key) for key in ('action','result','work','revision')})
                    if body.get('completionHash'):
                        if body['completionHash']!=proof: raise BindingError('launch_result_conflict','Result was already published with different content',409)
                        return body
                    if body['status']!='accepted': raise BindingError('launch_ack_required','Only an acknowledged active request can publish a result',409)
                    if action=='fail':
                        body.update(status='failed',error=text(args.get('result'),'failure reason',1600))
                    elif envelope['resultDestination']['kind']=='task-report':
                        from agent_runtime import actor_id
                        actor=actor_id(connection,session,envelope['project'])
                        with self.registry.coordination_connect() as coordination:
                            work=coordination.execute('SELECT * FROM work WHERE id=? AND session=? AND project=? AND task=?',
                                (args.get('work'),actor,envelope['project'],envelope['resultDestination']['task'])).fetchone()
                            stage=coordination.execute('SELECT stage FROM work_stage_links WHERE work=? UNION SELECT stage FROM work_stages WHERE work=?',(args.get('work'),args.get('work'))).fetchall()
                        if not work or work['status']!='done' or work['revision']!=args.get('revision') or work['created']<body['acknowledgedAt'] or (envelope['resultDestination'].get('stage') and not any(s['stage']==envelope['resultDestination']['stage'] for s in stage)):
                            raise BindingError('launch_result_unverified','Publish the owned task/stage hub_report first and return its current work revision',409)
                        body.update(status='completed',resultRef=dict(kind='work',id=work['id'],project=envelope['project'],revision=work['revision']),
                                    result=dict(summary=work['result'],evidence=json.loads(work['evidence'])))
                    else:
                        # Commit the request ledger after knowledge publication.
                        # Its idempotency key repairs an interruption in between.
                        result=args.get('result')
                        if not isinstance(result,dict) or set(result)!={'title','markdown'} or not isinstance(result['title'],str) or not isinstance(result['markdown'],str) or not 1<=len(result['markdown'])<=120000:
                            raise BindingError('invalid_launch_result','Publish a title and Markdown result document')
                        from knowledge_store import KnowledgeStore, KnowledgeError
                        destination=envelope['resultDestination']
                        c.rollback()
                        knowledge=KnowledgeStore(self.registry,envelope['project'])
                        item=dict(id=destination['id'],kind='document',format='markdown',audience='developer',section='analysis',
                            type='explanation',status='draft',visibility='internal',title=result['title'],markdown=result['markdown'],entityRefs=[])
                        selected=knowledge.read(destination['objectId'])
                        if selected['kind']!='document': item['entityRefs']=[destination['objectId']]
                        try:
                            receipt=knowledge.changeset(expected=destination['expectedRevision'],key='agent-launch:'+envelope['requestId'],
                                operations=[dict(op='put',item=item)],reason='Save native agent research result',actor='agent-launch:'+envelope['requestId'])
                        except KnowledgeError as error:
                            raise BindingError('launch_result_conflict','Knowledge changed or result is invalid; preserve it and reconcile before publishing',409) from error
                        c.execute('BEGIN IMMEDIATE')
                        body.update(status='completed',validation='client-reported',resultRef=dict(kind='knowledge-document',id=destination['id'],project=envelope['project'],revision=receipt['revision']))
                    body['completionHash']=proof
                    body['finishedAt']=time.time()
                self._save(c,envelope['requestId'],body)
                c.commit()
                return body
