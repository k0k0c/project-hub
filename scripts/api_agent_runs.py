"""Durable API analysis actions. Models receive read grants; the host owns writes."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
import re
import threading
import time

from agent_providers import Providers
from hub_action_context import ChatActionError, _digest, _json
from hub_lifecycle import file_lock
from knowledge_store import KnowledgeError, KnowledgeStore
from provider_runtime import Config, Driver, RuntimeError as ProviderRuntimeError
from research_api import GRANTS, ResearchBroker, instructions, normalize, parse_result, publication
from task_transfer import barrier


ACTIVE = ('requested', 'running')
READ_GRANTS = GRANTS


class LocalClient:
    """Trusted host service calls, with one stable principal and per-run session."""
    def __init__(self, registry, project, session, *, cancel=None, admission=None, closed=None):
        self.registry, self.project, self.session = registry, project, session
        self.token = None  # No external app credential is created or sent to the model.
        self.timeout = 20
        self.cancel = cancel
        self.actor = None
        self.admission = admission or threading.RLock()
        self.closed = closed or (lambda:False)

    def call(self, tool, arguments):
        with self.admission:
            if self.closed() or self.cancel is not None and self.cancel.is_set():
                raise ProviderRuntimeError('cancelled')
            if not isinstance(arguments, dict) or 'session' in arguments:
                raise ProviderRuntimeError('tool_binding_override')
            from agent_runtime import call_internal_research
            return call_internal_research(self.registry, self.project, tool, dict(arguments, session=self.session))


class ApiAgentRuns:
    def __init__(self, registry, context_builder, *, providers=None, driver_factory=Driver):
        self.registry, self.context_builder = registry, context_builder
        self.providers = providers or Providers(registry)
        self.driver_factory = driver_factory
        self._lock = threading.RLock()
        self._admission = threading.RLock()
        self._closed = False
        self._stop = threading.Event()
        self._runs = {}
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='hub-api-analysis')
        with barrier(registry), registry.connect() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS api_agent_runs(
                project TEXT NOT NULL, action_id TEXT PRIMARY KEY, signature TEXT NOT NULL,
                status TEXT NOT NULL, body TEXT NOT NULL, updated REAL NOT NULL)''')
            connection.execute('CREATE INDEX IF NOT EXISTS api_runs_history ON api_agent_runs(project,updated DESC,action_id)')
        self._recover()

    def _lease(self, action_id):
        return file_lock(self.registry.home / '.local' / 'api-agent-runs' /
                         (hashlib.sha256(action_id.encode()).hexdigest()+'.lock'), timeout=0)

    def _recover(self):
        with self.registry.connect() as connection:
            rows = connection.execute("SELECT action_id,body FROM api_agent_runs WHERE status IN ('requested','running')").fetchall()
        for row in rows:
            try:
                with self._lease(row['action_id']):
                    pending=any(item.get('status')=='running' for item in json.loads(row['body']).get('diagnostics',[]))
                    self._update(row['action_id'], 'outcome_unknown' if pending else 'interrupted', error=dict(code='process_interrupted',message='API process interrupted; review its saved receipt.'))
            except TimeoutError:
                pass  # A live process owns this exact run; do not steal it.

    def existing(self, project, action_id):
        with self.registry.connect() as connection:
            row = connection.execute('SELECT * FROM api_agent_runs WHERE action_id=?', (action_id,)).fetchone()
        if row is None:
            return None
        if row['project'] != project:
            raise ChatActionError('action_id_conflict', 409, 'Action ID belongs to another project')
        return row

    def _update(self, action_id, status=None, **fields):
        with self._admission, barrier(self.registry), self.registry.connect() as connection:
            if self._closed:
                raise ProviderRuntimeError('cancelled')
            connection.execute('BEGIN IMMEDIATE')
            try:
                row = connection.execute('SELECT * FROM api_agent_runs WHERE action_id=?', (action_id,)).fetchone()
                if row is None:
                    raise ValueError('Unknown API action')
                body = json.loads(row['body'])
                body.update(fields, updatedAt=time.time())
                if status is not None:
                    body['status'] = status
                connection.execute('UPDATE api_agent_runs SET status=?,body=?,updated=? WHERE action_id=?',
                                   (body['status'], _json(body), body['updatedAt'], action_id))
                connection.commit()
                return body
            except BaseException:
                connection.rollback()
                raise

    @staticmethod
    def _validate(project, task, action_id, stage, thread_id, target, mode, intent, expected):
        for value, name in ((project, 'project'), (action_id, 'action_id')):
            if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value):
                raise ChatActionError('invalid_request', 400, 'Invalid '+name)
        if len(action_id)>124:
            raise ChatActionError('invalid_request', 400, 'Action ID exceeds the API session limit')
        for value, name in ((task, 'task'), (stage, 'stage')):
            if value is not None and (not isinstance(value, str) or not value or len(value)>200 or any(ord(c)<32 for c in value)):
                raise ChatActionError('invalid_request', 400, 'Invalid '+name)
        if thread_id is not None:
            raise ChatActionError('api_resume_unsupported', 409, 'API analysis cannot resume a native chat')
        if any(value is not None for value in (task, stage, target, mode, intent, expected)):
            raise ChatActionError('task_execution_removed', 409, 'Hub starts specialized architecture and documentation research only')
        if expected is not None and not (type(expected) is int and expected>=0 or
                                        isinstance(expected,str) and 1<=len(expected)<=100):
            raise ChatActionError('invalid_request', 400, 'Invalid expected revision')

    def start(self, project, task, action_id, stage=None, thread_id=None, *, target=None,
              mode=None, intent=None, expected=None, _research=None):
        # Historical task receipts remain readable, but POST never replays or
        # continues a task/stage/planning/review request, including exact retries.
        raise ChatActionError('task_execution_removed', 409, 'Hub starts specialized architecture and documentation research only')

    def _start_research(self, project, research, action_id):
        self._validate(project, None, action_id, None, None, None, None, None, None)
        request = dict(project=project, task=None, stage=None, threadId=None,
                       target=None, mode=None, intent=None, expected=None, research=research)
        signature = _digest(request)
        with self._lock:
            previous = self.existing(project, action_id)
            if previous is not None:
                if previous['signature'] != signature:
                    raise ChatActionError('action_id_conflict', 409, 'Action ID has different request content')
                return json.loads(previous['body'])
            if self._stop.is_set():
                raise ChatActionError('adapter_disabled', 503, 'API analysis service is stopping')
            if research.get('providerId'):
                catalog, _ = self.providers.read()
                provider = deepcopy(next((item for item in catalog['items'] if item['id'] == research['providerId']), None))
            else:
                provider = deepcopy(self.providers.selected())
            if provider is None:
                raise ChatActionError('api_provider_unavailable', 409, 'Select an API provider')
            config = Config(**provider['config'])
            # Research answers can take longer than a small probe. Use the
            # ChatGPT request window without rewriting saved provider settings;
            # the driver's overall deadline still bounds the complete analysis.
            if config.auth_method == 'chatgpt_oauth':
                config = replace(config, timeout=60)
            lease = self._lease(action_id)
            lease.__enter__()
            queued = False
            try:
                with barrier(self.registry), self.registry.connect() as connection:
                    try:
                        raced = connection.execute('SELECT * FROM api_agent_runs WHERE action_id=?', (action_id,)).fetchone()
                        if raced is not None:
                            if raced['project'] != project or raced['signature'] != signature:
                                raise ChatActionError('action_id_conflict', 409, 'Action ID has different request content')
                            connection.rollback()
                            return json.loads(raced['body'])
                        count = connection.execute("SELECT COUNT(*) FROM api_agent_runs WHERE status IN ('requested','running')").fetchone()[0]
                        if count>=2 or sum(not run['future'].done() for run in self._runs.values())>=2:
                            raise ChatActionError('adapter_capacity', 503, 'API analysis capacity reached')
                        state = self.registry.store(project).memory_snapshot()
                        # Context builders validate task/object membership and budgets.
                        _, prompt, digest, metadata = self.context_builder._research_context(project, research, action_id, require_code=False)
                        captured = KnowledgeStore(self.registry, project).context()
                        if captured['revision'] != research['revision']:
                            raise ChatActionError('stale_revision', 409, 'Knowledge changed while building research context')
                        metadata.setdefault('knowledgeRevision', captured['revision'])
                        metadata.setdefault('workspaceRevision', captured['workspaceRevision'])
                        now = time.time()
                        body = dict(project=project, task=None, stage=None, actionId=action_id,
                                    status='requested', provider=provider['id'], model=config.model,
                                    protocol=config.provider, transport='api', nativeChat=False,
                                    networkMode=config.network_mode,diagnostics=[],
                                    sourceExecution=False, resumeAllowed=False, threadId=None, turnId=None,
                                    contextDigest=digest, projectRevision=state['revision'],
                                    target=None,
                                    createdAt=now, updatedAt=now, error=None,
                                    research=True, researchOperation=research['operation'], resultRef=None,
                                    bookkeeping=dict(mode='internal',createTask=False,createStage=False,createWork=False))
                        # Only public scope metadata; never persist prompts/config/keys.
                        for field in ('target', 'intent', 'scopeRef', 'scopeRevision', 'researchObject',
                                      'researchObjectId','researchTitle','researchTemplate','knowledgeRevision',
                                      'detailLevel','researchModel','agentSummaries','researchScope',
                                      'researchOperation','workspaceRevision'):
                            if field in metadata:
                                body[field] = metadata[field]
                        # Builders may initialize knowledge metadata using their
                        # own connection. Reserve the SQLite writer only after
                        # context reads, still inside the administrative barrier.
                        if self.registry.store(project).memory_snapshot()['revision'] != state['revision']:
                            raise ChatActionError('stale_revision',409,'Project changed while building analysis context')
                        connection.execute('BEGIN IMMEDIATE')
                        raced = connection.execute('SELECT * FROM api_agent_runs WHERE action_id=?', (action_id,)).fetchone()
                        if raced is not None:
                            if raced['project'] != project or raced['signature'] != signature:
                                raise ChatActionError('action_id_conflict', 409, 'Action ID has different request content')
                            connection.rollback()
                            return json.loads(raced['body'])
                        if connection.execute("SELECT COUNT(*) FROM api_agent_runs WHERE status IN ('requested','running')").fetchone()[0]>=2:
                            raise ChatActionError('adapter_capacity',503,'API analysis capacity reached')
                        connection.execute('INSERT INTO api_agent_runs VALUES(?,?,?,?,?,?)',
                                           (project, action_id, signature, 'requested', _json(body), now))
                        connection.commit()
                    except BaseException:
                        connection.rollback()
                        raise
                self._runs = {identifier:run for identifier,run in self._runs.items() if not run['future'].done()}
                cancel = threading.Event()
                future = self._executor.submit(self._run, action_id, request, provider, config, prompt, cancel, lease)
                self._runs[action_id] = dict(future=future, cancel=cancel)
                queued = True
                return body
            finally:
                if not queued:
                    lease.__exit__(None, None, None)

    def start_research(self, project, research, action_id):
        return self._start_research(project, normalize(research), action_id)

    def _prepare_context(self, client, request):
        context = client.call('hub_context', {})
        connection = context.get('connection',{})
        if connection.get('project') != request['project'] or not connection.get('actor'):
            raise ProviderRuntimeError('project_binding_mismatch')
        client.actor = connection['actor']

    def _save(self, client, action_id, project, text, request, broker, provider, model):
        knowledge = KnowledgeStore(self.registry, project)
        result = parse_result(text, request['research'])
        change, reference, components = publication(knowledge, broker, request['research'], action_id, result,
            actor=client.actor, task=None, stage=None, provider=provider, model=model)
        receipt = knowledge.changeset(**change)
        fields = dict(resultRef=reference, resultRevision=receipt['revision'], validation='verified',
                      evidenceCount=len(result['evidence']))
        if components:
            fields.update(proposalState='applied', componentIds=components, componentRevision=receipt['revision'])
        self._update(action_id, **fields)
        attachment = reference
        if not reference.startswith('knowledge/document/'):
            from artifact_store import publish
            artifact = publish(self.registry.store(project), 'research-' + hashlib.sha256(action_id.encode()).hexdigest()[:16] + '.json',
                _json(dict(result=result, resultRef=reference, revision=receipt['revision'],
                    actionId=action_id, provider=provider, model=model)).encode(),
                roles=['evidence', 'deliverable'], provenance='validated-api-research', artifact_id='research:' + action_id)
            attachment = artifact['source']['path']
            self._update(action_id, artifactRef=attachment)
        knowledge.flush_publication()
        return reference

    def _research_inventory(self, action_id, request, client, prompt, cancel, *, timeout=90):
        """First inventory for explicit architecture research, before paid work.

        The scanner has no expected-revision input and can coalesce another
        caller's job. Accept only our own exact single-revision publication.
        Waiting never holds the API write-admission gate.
        """
        research = request.get('research')
        if research is None or research.get('operation') != 'architecture-analyze' or research.get('template') not in {'explain','decompose','custom','relationship','scenario'}:
            return prompt
        with self._admission:
            if self._closed or cancel.is_set() or self._stop.is_set():
                raise ProviderRuntimeError('cancelled')
            knowledge = KnowledgeStore(self.registry,request['project'])
            before = knowledge.context()
            if before['revision'] != research['revision']:
                raise ProviderRuntimeError('research_revision_changed')
            with self.registry.connect() as connection:
                scanned = connection.execute('''SELECT 1 FROM knowledge_items
                    WHERE project=? AND kind='entity' AND json_extract(body,'$.type')='file'
                    AND json_extract(body,'$.generatedBy') IS NOT NULL
                    AND json_extract(body,'$.source.hash') IS NOT NULL
                    AND COALESCE(json_extract(body,'$.removed'),0)=0
                    AND COALESCE(json_extract(body,'$.analysisStatus'),'current') NOT IN ('stale','unavailable')
                    LIMIT 1''',(request['project'],)).fetchone()
            if not before['capabilities'].get('scan') or scanned is not None:
                self._update(action_id,sourceBasis=dict(kind='saved-knowledge',revision=before['revision'],
                    codeInventory=bool(scanned)))
                return prompt
            with barrier(self.registry):
                job = knowledge.start_scan(actor=client.session)
            self._update(action_id,scanJob=job['id'],sourceBasis=dict(kind='preparing-inventory',revision=before['revision']))
            if (job.get('actor') != client.session or job.get('task') is not None or job.get('stage') is not None or
                    job.get('workspaceRevision') != before.get('workspaceRevision')):
                raise ProviderRuntimeError('scan_ownership_conflict')
        deadline=time.monotonic()+min(90,timeout)
        while True:
            if cancel.is_set() or self._stop.is_set():
                raise ProviderRuntimeError('cancelled')
            if time.monotonic()>=deadline:
                raise ProviderRuntimeError('scan_deadline_exceeded')
            with self._admission:
                if self._closed:
                    raise ProviderRuntimeError('cancelled')
                job=knowledge.job(job['id'])
            if time.monotonic()>=deadline:
                raise ProviderRuntimeError('scan_deadline_exceeded')
            if job.get('state') not in ('queued','running'):
                break
            remaining=deadline-time.monotonic()
            if remaining<=0:
                raise ProviderRuntimeError('scan_deadline_exceeded')
            cancel.wait(min(.1,remaining))
        with self._admission:
            if self._closed or cancel.is_set() or self._stop.is_set():
                raise ProviderRuntimeError('cancelled')
            if job.get('state') not in ('ready','partial'):
                raise ProviderRuntimeError('scan_not_ready')
            current=knowledge.context()
            receipt=job.get('receipt',{})
            revision=before['revision']+1
            if receipt.get('unchanged') or not receipt.get('changed'):
                raise ProviderRuntimeError('scan_empty_inventory' if job.get('counts',{}).get('files')==0 else 'scan_unchanged_inventory')
            if (type(receipt.get('revision')) is not int or receipt['revision']!=revision or
                    not receipt.get('changed') or current['revision']!=revision or
                    current['policy']!=before['policy'] or
                    current.get('workspaceRevision')!=before.get('workspaceRevision')):
                raise ProviderRuntimeError('scan_revision_conflict')
            with self.registry.connect() as connection:
                applied=connection.execute('''SELECT key,actor,task,stage FROM knowledge_changes
                    WHERE project=? AND revision=?''',(request['project'],revision)).fetchone()
            if (applied is None or applied['key']!='scan:'+job['id'] or applied['actor']!=client.session or
                    applied['task'] is not None or applied['stage'] is not None):
                raise ProviderRuntimeError('scan_receipt_unverified')
            refreshed=deepcopy(research)
            refreshed['revision']=revision
            _, refreshed_prompt, digest, metadata=self.context_builder._research_context(
                request['project'],refreshed,action_id,require_code=False)
            # Context construction can access independent stores. Recheck the
            # exact verified revision rather than adopting later user edits.
            final=knowledge.context()
            if final['revision']!=revision or final.get('workspaceRevision')!=before.get('workspaceRevision'):
                raise ProviderRuntimeError('scan_revision_conflict')
            public={field:metadata[field] for field in ('researchObjectId','researchTitle','researchTemplate',
                'knowledgeRevision','detailLevel','researchModel','agentSummaries','researchScope') if field in metadata}
            self._update(action_id,contextDigest=digest,scanJob=job['id'],
                sourceBasis=dict(kind='verified-first-scan',revision=revision,state=job['state'],
                                 fingerprint=job.get('fingerprint'),rootRefs=current.get('rootRefs',[])),**public)
            return refreshed_prompt

    def _run(self, action_id, request, provider, config, prompt, cancel, lease):
        started_model = False
        client = None
        broker = None
        try:
            if self._stop.is_set() or cancel.is_set():
                raise ProviderRuntimeError('cancelled')
            self._update(action_id, 'running')
            with self._admission:
                if self._closed or cancel.is_set():
                    raise ProviderRuntimeError('cancelled')
                client = LocalClient(self.registry, request['project'], 'api:'+action_id, cancel=cancel,
                    admission=self._admission,closed=lambda:self._closed)
                self._prepare_context(client, request)
            prompt=self._research_inventory(action_id,request,client,prompt,cancel)
            body = json.loads(self.existing(request['project'], action_id)['body'])
            effective = deepcopy(request)
            effective['research']['revision'] = body.get('sourceBasis', {}).get('revision', request['research']['revision'])
            from agent_runtime import tools
            descriptors = [descriptor for descriptor in tools() if descriptor['name'] in READ_GRANTS]
            for descriptor in descriptors:
                actions = READ_GRANTS[descriptor['name']]
                if actions is not None:
                    descriptor['inputSchema']['properties']['action']['enum'] = sorted(actions)
            knowledge = KnowledgeStore(self.registry, request['project'])
            broker = ResearchBroker(client, knowledge, effective['research'], descriptors)
            if broker.sources.signature != body['workspaceRevision']:
                raise ProviderRuntimeError('research_workspace_changed')
            rules = broker.initial_rules()
            prompt += '\nAvailable project/workspace rules (JSON):\n' + _json(rules)
            key = self.providers.credential(provider)
            if next((item for item in self.providers.read()[0]['items'] if item['id']==provider['id']),None)!=provider:
                raise ProviderRuntimeError('provider_revision_changed')
            driver = self.driver_factory(config, broker, environ={config.credential_env:key})
            from provider_runtime import HTTP
            if isinstance(getattr(driver,'transport',None),HTTP):
                driver.transport.observer=lambda values:self._update(action_id,diagnostics=values)
            started_model = True
            result = driver.run(prompt,instructions=instructions(effective['research']),cancel=cancel)
            if cancel.is_set() or self._stop.is_set():
                raise ProviderRuntimeError('cancelled', outcome_unknown=started_model)
            text = result.get('text') if isinstance(result, dict) else None
            if not isinstance(text, str) or not text.strip() or len(text.encode())>150000:
                raise ProviderRuntimeError('invalid_result')
            if key in text:
                raise ProviderRuntimeError('credential_echo_rejected')
            # The raw response is durable recovery evidence, never a fallback
            # document. Invalid schema/evidence/revisions cannot modify knowledge.
            self._update(action_id, resultText=text)
            with self._admission, barrier(self.registry):
                if self._closed or cancel.is_set():
                    raise ProviderRuntimeError('cancelled',outcome_unknown=started_model)
                if next((item for item in self.providers.read()[0]['items'] if item['id']==provider['id']),None)!=provider:
                    raise ProviderRuntimeError('provider_revision_changed')
                reference = self._save(client, action_id, request['project'], text,
                    effective, broker, provider['id'], config.model)
            self._update(action_id, 'completed', resultRef=reference, sourceReadBudget=broker.sources.budget())
        except Exception as error:
            if cancel.is_set() or self._stop.is_set():
                code, status = 'cancelled', 'outcome_unknown' if started_model else 'interrupted'
            elif isinstance(error, ProviderRuntimeError):
                code = error.code
                status = 'outcome_unknown' if error.outcome_unknown else ('interrupted' if code=='cancelled' else 'failed')
            elif isinstance(error, KnowledgeError):
                code = 'research_revision_changed' if error.body['error'] == 'revision_conflict' else 'research_publication_invalid'
                status = 'failed'
            else:
                code, status = 'api_outcome_unknown' if started_model else 'api_host_failed', 'outcome_unknown' if started_model else 'failed'
            try:
                # Credential acquisition has its own OAuth transport, before
                # the model HTTP observer exists. Keep that failure's safe
                # facts too, without implying that a model request was sent.
                if isinstance(error, ProviderRuntimeError) and code.startswith('chatgpt_') and error.diagnostic:
                    from chatgpt_auth import model_diagnostic
                    diagnostic = model_diagnostic(error.diagnostic, {})
                    if diagnostic:
                        self._update(action_id, diagnostics=[diagnostic])
                message={'scan_empty_inventory':'No supported source files were found; API analysis was not started.',
                         'scan_unchanged_inventory':'The scan did not publish a new inventory revision; API analysis was not started.'}.get(code)
                validation_detail = getattr(error, 'diagnostic', None)
                validation_reason = validation_detail.get('validationReason') if isinstance(validation_detail, dict) else None
                validation = ({'validationReason':validation_reason} if code=='research_evidence_unverified' and isinstance(validation_reason,str) and
                    validation_reason in {'source_not_read','source_hash_mismatch','source_range_invalid',
                                          'source_range_unread','knowledge_not_read'} else {})
                if isinstance(error, KnowledgeError) and error.body.get('error') in {
                        'item_missing', 'stale_object', 'unsafe_source', 'invalid_source', 'invalid_policy',
                        'invalid_item', 'invalid_kind', 'invalid_links', 'description_too_long'}:
                    validation['validationReason'] = error.body['error']
                if code == 'research_tool_result_limit' and isinstance(validation_detail, dict):
                    if validation_detail.get('tool') == 'hub_knowledge':
                        validation['tool'] = 'hub_knowledge'
                    if validation_detail.get('action') in {'context', 'search', 'history', 'read', 'research-object'}:
                        validation['action'] = validation_detail['action']
                    for field in ('resultBytes', 'limitBytes'):
                        value = validation_detail.get(field)
                        if type(value) is int and 0 <= value <= 100_000_000:
                            validation[field] = value
                self._update(action_id, status, error=dict(code=code, message=message or
                    ('API analysis requires review.' if status=='outcome_unknown' else 'API analysis did not complete.'), **validation),
                    **({'sourceReadBudget':broker.sources.budget()} if broker is not None else {}))
            except Exception:
                pass  # Leave the durable active receipt for lease-based recovery.
        finally:
            lease.__exit__(None, None, None)

    def cancel(self, project, action_id):
        with self._lock:
            existing = self.existing(project, action_id)
            if existing is None:
                raise ChatActionError('action_not_found', 404, 'Unknown API research request')
            body = json.loads(existing['body'])
            if not body.get('research'):
                raise ChatActionError('task_execution_removed', 409, 'Historical task actions are read-only')
            if body['status'] not in ACTIVE:
                return body
            run = self._runs.get(action_id)
            if run is None:
                raise ChatActionError('api_cancel_unavailable', 409, 'This process does not own the live research run')
            run['cancel'].set()
            return self._update(action_id, cancelRequested=True)

    def recent(self, project, task):
        if not isinstance(task,str) or not task or len(task)>240:
            raise ChatActionError('invalid_request',400,'Invalid task history handle')
        with self.registry.connect() as connection:
            if task.startswith('__research__:'):
                rows=connection.execute("""SELECT body FROM api_agent_runs WHERE project=?
                    AND json_extract(body,'$.research')=1 AND COALESCE(json_extract(body,'$.researchObjectId'),
                    json_extract(body,'$.researchObject'))=? ORDER BY updated DESC,action_id DESC LIMIT 20""",
                    (project,task[len('__research__:'):])).fetchall()
            elif task=='__project_review__':
                rows=connection.execute("""SELECT body FROM api_agent_runs WHERE project=?
                    AND json_extract(body,'$.target')='project' AND json_extract(body,'$.task') IS NULL
                    ORDER BY updated DESC,action_id DESC LIMIT 20""",(project,)).fetchall()
            else:
                rows = connection.execute("SELECT body FROM api_agent_runs WHERE project=? AND (json_extract(body,'$.task')=? OR json_extract(body,'$.hostTask')=?) ORDER BY updated DESC,action_id DESC LIMIT 20", (project,task,task)).fetchall()
        return [json.loads(row['body']) for row in rows]

    def research_history(self, project, offset=0, limit=20):
        try:
            offset, limit = max(0,int(offset)), min(20,max(1,int(limit)))
        except (ValueError, TypeError):
            raise ChatActionError('invalid_request', 400, 'Invalid history page') from None
        with self.registry.connect() as connection:
            rows = connection.execute("SELECT body FROM api_agent_runs WHERE project=? AND json_extract(body,'$.research')=1 ORDER BY updated DESC,action_id DESC LIMIT ? OFFSET ?", (project,limit+1,offset)).fetchall()
        more = len(rows)>limit
        return dict(items=[json.loads(row['body']) for row in rows[:limit]], offset=offset,
                    more=more, next=offset+limit if more else None)

    def close(self, *, timeout=30):
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 0<timeout<=30:
            raise ValueError('Shutdown timeout must be within thirty seconds')
        self._stop.set()
        with self._lock:
            runs = list(self._runs.items())
            for _, run in runs:
                run['cancel'].set()
        # A bounded shutdown never marks an in-flight accepted write completed.
        started=time.monotonic()
        deadline = started+min(25,timeout*5/6)
        for _, run in runs:
            try:
                run['future'].result(timeout=max(0,deadline-time.monotonic()))
            except Exception:
                pass
        # After admitted writes drain, a late transport completion cannot write
        # into a closed/switched data home. Failure to drain forbids safe close.
        if not self._admission.acquire(timeout=max(0,timeout-(time.monotonic()-started))):
            raise ChatActionError('api_shutdown_pending',503,'API Hub writes have not drained; storage activation must wait')
        try:
            self._closed=True
        finally:
            self._admission.release()
        self._executor.shutdown(wait=False, cancel_futures=False)
