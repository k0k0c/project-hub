import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api_agent_runs import ApiAgentRuns
from hub_action_context import ChatActionError, HubActionContext
from knowledge_store import KnowledgeStore
from project_registry import ProjectRegistry
from provider_runtime import HubTools, RuntimeError as ProviderRuntimeError
from unified_actions import UnifiedActions

SECRET = 'private-test-provider-secret'


class FakeProviders:
    def __init__(self):
        self.item = dict(id='provider-one', name='Test provider', config=dict(
            provider='chat', model='test-model', credential_env='TEST_API_KEY', deadline=2, timeout=1))
        self.other = dict(id='provider-two', name='Other provider', config=dict(
            provider='chat', model='other-model', credential_env='OTHER_API_KEY', deadline=2, timeout=1))
    def selected(self):
        return self.item
    def read(self):
        return dict(items=[self.other, *([self.item] if self.item else [])]), 'revision'
    def credential(self, item):
        return SECRET


class ApiRunsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = ProjectRegistry(Path(self.temp.name) / 'hub', standalone=True)
        self.project = self.registry.create('Example')['id']
        KnowledgeStore(self.registry, self.project).changeset(0, 'existing', [dict(op='put', item=dict(
            id='existing', kind='document', title='Existing document', markdown='Existing source', audience='user',
            section='guide', type='how-to', status='current', visibility='internal'))], 'Existing fixture')
        self.registry.store(self.project).record(dict(kind='task.created', taskId='task', title='Example task',
            patch=dict(title='Example task', status='planned', sources=[dict(label='Existing document',
                path='knowledge/document/existing')], stages=[])))
        self.providers = FakeProviders()
        self.existing_task = self.registry.store(self.project).task_context('task')['tasks'][0]
        self.calls, self.ready, self.errors, self.source_reads, self.instructions, self.prompts = [], [], [], [], [], []
        self.configs = []
        self.gate, self.failure, self.raw_text, self.hook = None, None, None, None
        self.overrides, self.read_source = {}, False
        owner = self
        class FakeDriver:
            def __init__(self, config, broker, *, environ):
                self.config, self.broker = config, broker
                owner.configs.append(config)
                owner.assertEqual(environ[config.credential_env], SECRET)
            def run(self, prompt, *, instructions, cancel):
                owner.calls.append(self.broker.client.session)
                owner.instructions.append(instructions)
                owner.prompts.append(prompt)
                self.broker.verify()
                owner.assertEqual(self.broker.names, {'hub_knowledge', 'research_source'})
                owner.assertEqual(self.broker.call('hub_knowledge', dict(action='context'), 1)['project'], owner.project)
                research = self.broker.research
                evidence = [dict(kind='knowledge', id=research['objectId'], revision=research['revision'])]
                if owner.read_source:
                    paths = self.broker.call('research_source', dict(action='tree'), 1)['items']
                    path = next(item['path'] for item in paths if item['path'].endswith('example.py'))
                    page = self.broker.call('research_source', dict(action='read', path=path), 1)
                    owner.source_reads.append(page)
                    evidence.append(dict(kind='source', path=page['path'], hash=page['hash'], line=page['line'], endLine=page['endLine']))
                if owner.hook:
                    owner.hook(self.broker)
                owner.ready.append(self.broker.client.session)
                while owner.gate is not None and not owner.gate.is_set():
                    if cancel.wait(.01):
                        raise ProviderRuntimeError('cancelled', outcome_unknown=True)
                if owner.failure is not None:
                    raise owner.failure
                result = dict(schemaVersion=1, operation=research['operation'], summary='Verified research findings.', evidence=evidence, limitations=[])
                if research['operation'] == 'architecture-analyze':
                    result['description'] = 'Explains the responsibility using the inspected evidence.'
                else:
                    result.update(title='Research findings', markdown='# Findings\n\nAn evidence-backed explanation.', entityRefs=[])
                result.update(owner.overrides)
                return dict(text=owner.raw_text if owner.raw_text is not None else json.dumps(result))
        self.driver = FakeDriver
        self.service = self.make_service()

    def make_service(self, driver=None):
        service = ApiAgentRuns(self.registry, HubActionContext(self.registry), providers=self.providers, driver_factory=driver or self.driver)
        original = service._save
        def saving(*args, **kwargs):
            try:
                return original(*args, **kwargs)
            except Exception as error:
                self.errors.append((type(error).__name__, getattr(error, 'body', {})))
                raise
        service._save = saving
        self.addCleanup(service.close)
        return service

    def research(self, **changes):
        return dict(dict(operation='documentation-draft', objectId='existing', revision=1), **changes)

    def start(self, action, research=None, service=None):
        return (service or self.service).start_research(self.project, research or self.research(), action)

    def await_status(self, action, statuses=('completed',), service=None):
        service = service or self.service
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            body = json.loads(service.existing(self.project, action)['body'])
            if body['status'] in statuses:
                return body
            time.sleep(.01)
        self.fail('API action did not reach ' + str(statuses) + ': ' + json.dumps(body) + ' errors: ' + repr(self.errors))

    def wait_model(self, count=1):
        # Worker scheduling and admitted Hub writes can take longer under the
        # integrated suite. Wait for the actual model boundary, failing early
        # on a terminal receipt rather than relying on a three-second race.
        deadline = time.monotonic() + 15
        while len(self.ready) < count and time.monotonic() < deadline:
            with self.registry.connect() as connection:
                bodies = [json.loads(row[0]) for row in connection.execute(
                    'SELECT body FROM api_agent_runs WHERE project=?', (self.project,))]
            terminal = [body for body in bodies if 'api:' + body['actionId'] not in self.ready
                        and body['status'] in ('failed', 'outcome_unknown', 'interrupted')]
            if terminal:
                self.fail('API action ended before the model boundary: ' + json.dumps(terminal))
            time.sleep(.01)
        self.assertGreaterEqual(len(self.ready), count)

    def assert_task_unchanged(self):
        current = self.registry.store(self.project).task_context('task')['tasks'][0]
        self.assertEqual({key: value for key, value in current.items() if not key.startswith('_')},
                         {key: value for key, value in self.existing_task.items() if not key.startswith('_')})

    def test_exact_replay_conflict_and_rootless_result_preserve_unrelated_task(self):
        self.start('one')
        result = self.await_status('one')
        self.assertEqual(self.start('one'), result)
        self.assertEqual(self.calls, ['api:one'])
        with self.assertRaises(ChatActionError) as caught:
            self.start('one', self.research(prompt='Different request'))
        self.assertEqual(caught.exception.code, 'action_id_conflict')
        self.assertFalse(result['nativeChat'])
        self.assertFalse(result['sourceExecution'])
        document = KnowledgeStore(self.registry, self.project).read('doc:api-result:one')
        self.assertIn('# Findings', document['markdown'])
        self.assertEqual(document['status'], 'draft')
        self.assertTrue(document['evidence'])
        self.assert_task_unchanged()
        self.assertFalse({'hostTask','hostStage','work'} & result.keys())
        self.assertEqual(result['bookkeeping'], dict(mode='internal',createTask=False,createStage=False,createWork=False))
        self.assertEqual([item['id'] for item in self.registry.store(self.project).memory_snapshot()['tasks']], ['task'])
        with self.registry.connect() as connection:
            self.assertIsNone(connection.execute("SELECT * FROM client_bindings WHERE client='hub-api'").fetchone())
            ledger = connection.execute('SELECT body FROM api_agent_runs').fetchone()[0]
        self.assertNotIn(SECRET, ledger)
        self.assertNotIn('TEST_API_KEY', ledger)
        self.providers.item = None
        self.assertEqual(self.start('one'), result)

    def test_all_research_operations_publish_without_tasks_stages_or_work(self):
        for operation in ('architecture-analyze','documentation-draft','documentation-refresh','documentation-review'):
            revision = KnowledgeStore(self.registry, self.project).context()['revision']
            self.start('untracked-' + operation, self.research(operation=operation, template='custom', revision=revision))
            result = self.await_status('untracked-' + operation)
            self.assertFalse({'hostTask','hostStage','work'} & result.keys())
            self.assertEqual(result['bookkeeping']['mode'], 'internal')
            self.assertIsNotNone(result['resultRef'])
            self.assert_task_unchanged()
            self.assertEqual([item['id'] for item in self.registry.store(self.project).memory_snapshot()['tasks']], ['task'])
            with self.registry.coordination_connect() as connection:
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM work WHERE project=?', (self.project,)).fetchone()[0], 0)
            with self.registry.connect() as connection:
                change = connection.execute('SELECT task,stage FROM knowledge_changes WHERE project=? ORDER BY revision DESC LIMIT 1', (self.project,)).fetchone()
            self.assertIsNone(change['task']); self.assertIsNone(change['stage'])

    def test_multiple_api_runs_keep_external_app_identity_and_credentials_unchanged(self):
        from agent_bindings import Connections
        connections = Connections(self.registry)
        app = connections.enroll(connections.invite(request_id='a'*32)['token'], 'example-client', 'one-installation')
        before = connections.catalog()
        self.start('first-analysis'); self.await_status('first-analysis')
        revision = KnowledgeStore(self.registry,self.project).context()['revision']
        self.start('second-analysis',self.research(revision=revision)); self.await_status('second-analysis')
        self.assertEqual(connections.catalog(), before)
        self.assertEqual(connections.authenticate(app['token'])['id'], app['binding'])
        with self.registry.connect() as connection:
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM api_agent_runs').fetchone()[0], 2)
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM agent_invitations').fetchone()[0], 1)

    def test_capacity_and_concurrent_publication_revision_conflict(self):
        self.gate = threading.Event()
        self.start('first'); self.start('second')
        with self.assertRaises(ChatActionError) as caught:
            self.start('third')
        self.assertEqual(caught.exception.code, 'adapter_capacity')
        self.assertIsNone(self.service.existing(self.project, 'third'))
        self.wait_model(2)
        self.gate.set()
        results = [self.await_status(action, ('completed', 'failed')) for action in ('first', 'second')]
        self.assertEqual(sorted(result['status'] for result in results), ['completed', 'failed'])
        failed = next(result for result in results if result['status'] == 'failed')
        self.assertEqual(failed['error']['code'], 'research_revision_changed')
        self.assertIsNone(failed['resultRef'])

    def test_action_id_is_global_and_rejected_across_projects(self):
        self.start('global'); self.await_status('global')
        other = self.registry.create('Other example')['id']
        with self.assertRaises(ChatActionError) as caught:
            self.service.start_research(other, self.research(), 'global')
        self.assertEqual(caught.exception.code, 'action_id_conflict')
        self.assertEqual(len(self.calls), 1)

    def test_pending_replay_and_second_instance_preserve_live_lease(self):
        self.gate = threading.Event()
        self.start('pending'); self.await_status('pending', ('running',)); self.wait_model()
        other = self.make_service()
        self.assertEqual(json.loads(other.existing(self.project, 'pending')['body'])['status'], 'running')
        self.start('pending', service=other)
        self.assertEqual(len(self.calls), 1)
        self.gate.set(); self.await_status('pending')

    def test_restart_marks_unowned_active_receipt_interrupted_without_retry(self):
        body = dict(project=self.project, task='task', actionId='orphan', status='running', createdAt=1, updatedAt=1)
        with self.registry.connect() as connection:
            connection.execute('INSERT INTO api_agent_runs VALUES(?,?,?,?,?,?)', (self.project, 'orphan', 'signature', 'running', json.dumps(body), 1))
        other = self.make_service()
        result = json.loads(other.existing(self.project, 'orphan')['body'])
        self.assertEqual(result['status'], 'interrupted')
        self.assertEqual(result['error']['code'], 'process_interrupted')
        self.assertEqual(self.calls, [])

    def test_restart_preserves_pending_transport_and_marks_outcome_unknown(self):
        diagnostic=dict(requestId='local-exchange',status='running',category='pending',outcomeUnknown=True)
        body=dict(project=self.project,actionId='orphan-http',status='running',diagnostics=[diagnostic])
        with self.registry.connect() as connection:
            connection.execute('INSERT INTO api_agent_runs VALUES(?,?,?,?,?,?)',
                (self.project,'orphan-http','signature','running',json.dumps(body),1))
        other=self.make_service()
        result=json.loads(other.existing(self.project,'orphan-http')['body'])
        self.assertEqual(result['status'],'outcome_unknown')
        self.assertEqual(result['diagnostics'],[diagnostic])
        self.assertEqual(self.calls,[])

    def test_provider_edit_during_request_prevents_publication(self):
        self.hook=lambda broker:self.providers.item['config'].update(model='changed-model')
        self.start('changed-provider')
        result=self.await_status('changed-provider',('failed',))
        self.assertEqual(result['error']['code'],'provider_revision_changed')
        self.assertIsNone(result['resultRef'])
        self.assertEqual(KnowledgeStore(self.registry,self.project).context()['counts'],{'document':1})

    def test_real_driver_records_safe_transport_details_on_research_receipt(self):
        from provider_runtime import Driver
        result=dict(schemaVersion=1,operation='documentation-draft',summary='Evidence-backed result',
            evidence=[dict(kind='knowledge',id='existing',revision=1)],limitations=[],
            title='Result',markdown='An evidence-backed explanation.',entityRefs=[])
        class Response:
            status=200
            headers={'X-Request-ID':'upstream-research-1'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def read(self,size):return json.dumps(dict(choices=[dict(finish_reason='stop',
                message=dict(role='assistant',content=json.dumps(result)))])).encode()[:size]
        class Opener:
            def open(self,request,timeout):return Response()
        service=self.make_service(driver=Driver)
        with patch('provider_runtime.opener_for',return_value=Opener()):
            self.start('http-receipt',service=service)
            receipt=self.await_status('http-receipt',('completed','failed','outcome_unknown'),service=service)
        self.assertEqual(receipt['status'],'completed',receipt)
        self.assertEqual(receipt['diagnostics'][0]['status'],'completed')
        self.assertEqual(receipt['diagnostics'][0]['upstreamRequestId'],'upstream-research-1')
        self.assertNotIn(SECRET,json.dumps(receipt))

    def test_oauth_credential_failure_records_safe_diagnostics_before_model_dispatch(self):
        diagnostic = dict(operation='oauth', oauthAction='openid_configuration',
            host='auth.openai.com', category='timeout', timeoutMs=60000,
            outcomeUnknown=False, tlsReason='certificate_verification', tlsVerifyCode=20,
            message='private response', response='private response',
            url='https://private.invalid/secret', access_token='private token')
        with patch.object(self.providers, 'credential', side_effect=ProviderRuntimeError(
                'chatgpt_network_error', diagnostic=diagnostic)):
            self.start('oauth-before-model')
            result = self.await_status('oauth-before-model', ('failed',))
        self.assertEqual(self.calls, [])
        self.assertEqual(result['error']['code'], 'chatgpt_network_error')
        self.assertEqual(result['diagnostics'], [dict(operation='oauth', oauthAction='openid_configuration',
            host='auth.openai.com', category='timeout', timeoutMs=60000, outcomeUnknown=False,
            tlsReason='certificate_verification', tlsVerifyCode=20)])
        self.assertNotIn('private', json.dumps(result))
        self.assertIsNone(result['resultRef'])

    def test_research_timeout_honors_api_config_and_chatgpt_answer_window_without_settings_write(self):
        from copy import deepcopy
        self.providers.item['config'].update(timeout=45)
        before = deepcopy(self.providers.item)
        self.start('configured-timeout')
        self.await_status('configured-timeout')
        self.assertEqual(self.configs[-1].timeout, 45)
        self.assertEqual(self.providers.item, before)
        self.providers.item['config'].update(provider='responses', auth_method='chatgpt_oauth', timeout=20)
        before = deepcopy(self.providers.item)
        self.start('chatgpt-timeout', self.research(revision=2))
        self.await_status('chatgpt-timeout')
        self.assertEqual(self.configs[-1].timeout, 60)
        self.assertEqual(self.configs[-1].deadline, before['config']['deadline'])
        self.assertEqual(self.providers.item, before)

    def test_chatgpt_recovers_missing_path_and_partial_search_before_verified_publication(self):
        from provider_runtime import Driver
        research = self.code_research()
        self.addCleanup(self.drain_scans)
        (Path(self.temp.name) / 'source' / 'a.py').write_text('#' * 121, encoding='utf-8')
        self.providers.item['config'].update(provider='responses', auth_method='chatgpt_oauth',
                                              network_mode='system', deadline=15)
        provider_before = json.loads(json.dumps(self.providers.item))
        requests = []
        class Response:
            status = 200
            headers = {}  # Completed items are needed even without Content-Type.
            def __init__(self, items):
                events = [dict(type='response.output_item.done', output_index=i, item=item)
                          for i, item in enumerate(items)]
                events.append(dict(type='response.completed', response=dict(status='completed', output=[])))
                self.raw = ''.join('data: ' + json.dumps(event) + '\n\n' for event in events).encode()
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, size): return self.raw[:size]
        owner = self
        class Opener:
            def open(self, request, timeout):
                body = json.loads(request.data); requests.append(body)
                owner.assertEqual(request.full_url, 'https://api.openai.com/v1/responses')
                if len(requests) == 1:
                    return Response([dict(type='reasoning', id='r', encrypted_content='opaque-final'),
                        dict(type='function_call', id='denied', call_id='call-denied', name='research_source',
                             arguments=json.dumps(dict(action='read', path='.codex/config.toml'))),
                        dict(type='function_call', id='missing', call_id='call-missing', name='research_source',
                             arguments=json.dumps(dict(action='read', path='missing.py')))])
                value = json.loads(body['input'][-1]['output'])
                if len(requests) == 2:
                    denial = json.loads(body['input'][-2]['output'])
                    owner.assertEqual(denial['error']['code'], 'research_source_denied')
                    owner.assertIs(denial['error']['recoverable'], True)
                    owner.assertEqual(value['error']['code'], 'research_source_unavailable')
                    owner.assertIs(value['error']['recoverable'], True)
                    return Response([dict(type='function_call', id='broad-search', call_id='call-broad-search', name='research_source',
                        arguments=json.dumps(dict(action='search', query='class Example')))])
                if len(requests) == 3:
                    owner.assertTrue(value['partial'])
                    owner.assertEqual(value['partialReason'], 'search_byte_limit')
                    owner.assertLessEqual(value['budget']['usedBytes'], 120)
                    return Response([dict(type='function_call', id='search', call_id='call-search', name='research_source',
                        arguments=json.dumps(dict(action='search', path='example.py', query='class Example')))])
                if len(requests) == 4:
                    owner.assertEqual(value['items'][0]['path'], 'example.py')
                    owner.assertEqual(value['items'][0]['line'], 1)
                    return Response([dict(type='function_call', id='read', call_id='call-source', name='research_source',
                        arguments=json.dumps(dict(action='read', path=value['items'][0]['path'], line=1, lines=2)))])
                owner.assertEqual(len(requests), 5)  # Distinct tool continuations, never retries.
                page = value
                owner.assertIn('class Example', json.dumps(page))
                result = dict(schemaVersion=1, operation='architecture-analyze', summary='Source-backed explanation',
                    description='Example declares a class with no methods.', limitations=[], evidence=[
                        dict(kind='source', path=page['path'], hash=page['hash'], line=page['line'], endLine=page['endLine'])])
                return Response([dict(type='message', id='m', role='assistant', status='completed',
                    content=[dict(type='output_text', text=json.dumps(result))])])
        service = self.make_service(driver=Driver)
        with patch('research_sources.ResearchSources.MAX_SEARCH_BYTES', 120), \
                patch('provider_runtime.opener_for', return_value=Opener()) as openers:
            self.start('oauth-stream-analysis', research, service=service)
            receipt = self.await_status('oauth-stream-analysis', ('completed', 'failed', 'outcome_unknown'), service=service)
        self.assertEqual(receipt['status'], 'completed', receipt)
        self.assertEqual(receipt['resultRef'], 'knowledge/entity/component')
        knowledge = KnowledgeStore(self.registry, self.project)
        updated = knowledge.read('component')
        self.assertEqual(updated['description'], 'Example declares a class with no methods.')
        self.assertIn('descriptionBasis', updated)
        self.assertEqual(knowledge.context()['counts'].get('document', 0), 0)
        self.assertEqual(len(requests), 5)
        for body in requests:
            self.assertIs(body['stream'], True); self.assertIs(body['store'], False)
            self.assertNotIn('max_output_tokens', body); self.assertNotIn('tools', body)
        self.assertEqual(requests[1]['input'][2]['encrypted_content'], 'opaque-final')
        self.assertEqual(requests[1]['input'][-1]['call_id'], 'call-missing')
        self.assertEqual(requests[-1]['input'][-1]['call_id'], 'call-source')
        self.assertEqual(len(receipt['diagnostics']), 5)
        self.assertEqual(receipt['sourceReadBudget']['observedFiles'], 1)
        self.assertEqual(receipt['sourceReadBudget']['readFiles'], 1)
        self.assertEqual(receipt['sourceReadBudget']['limitBytes'], 4_000_000)
        self.assertEqual(receipt['sourceReadBudget']['usedBytes'], (Path(self.temp.name) / 'source' / 'example.py').stat().st_size)
        self.assertTrue(all(item['attempt'] == 1 and item['status'] == 'completed' for item in receipt['diagnostics']))
        self.assertTrue(all(call.args[1] == 'system' for call in openers.call_args_list))
        self.assertEqual(self.providers.item, provider_before)
        self.assertNotIn(SECRET, json.dumps(receipt))

    def test_provider_error_is_sanitized_and_unknown_outcome_not_retried(self):
        self.failure = Exception(SECRET + ' upstream private details')
        self.start('error')
        result = self.await_status('error', ('outcome_unknown',))
        self.assertNotIn(SECRET, json.dumps(result)); self.assertNotIn('upstream', json.dumps(result))
        self.assertEqual(self.start('error'), result)
        self.assertEqual(len(self.calls), 1)
        self.assert_task_unchanged()
        self.assertFalse({'hostTask','hostStage','work'} & result.keys())
        self.assertEqual([item['id'] for item in self.registry.store(self.project).memory_snapshot()['tasks']], ['task'])

    def test_key_echo_rejected_without_document_or_raw_receipt(self):
        self.raw_text = 'Result ' + SECRET
        self.start('echo')
        result = self.await_status('echo', ('failed',))
        self.assertEqual(result['error']['code'], 'credential_echo_rejected')
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual(KnowledgeStore(self.registry, self.project).context()['counts'], {'document': 1})

    def test_all_ordinary_task_stage_plan_review_implementation_resume_requests_rejected(self):
        for options in ({}, dict(stage='stage'), dict(mode='plan'), dict(mode='default'), dict(thread_id='native'),
                        dict(target='project', mode='plan', intent='review'), dict(expected=1)):
            with self.subTest(options=options), self.assertRaises(ChatActionError) as caught:
                self.service.start(self.project, 'task', 'ordinary', **options)
            self.assertEqual(caught.exception.code, 'task_execution_removed')
        self.assertEqual(self.calls, [])
        self.assertIsNone(self.service.existing(self.project, 'ordinary'))
        class Client:
            session = 'own'; token = 'private'; timeout = 1
            def call(self, *args):
                raise AssertionError('Mutation dispatched')
        broker = HubTools(Client(), self.project, [dict(name='hub_knowledge', inputSchema=dict(type='object', properties={}))], trusted_host_grants={'hub_knowledge': {'read'}})
        with self.assertRaises(ProviderRuntimeError):
            broker.call('hub_knowledge', dict(action='changeset'), 1)

    def test_stale_knowledge_unknown_operation_and_missing_provider_rejected_before_model(self):
        for research, code in ((self.research(revision=999), 'stale_revision'), (self.research(operation='task-review'), 'task_execution_removed'),
                               (self.research(providerId='missing'), 'api_provider_unavailable')):
            with self.subTest(code=code), self.assertRaises(ChatActionError) as caught:
                self.start('rejected', research)
            self.assertEqual(caught.exception.code, code)
        self.assertEqual(self.calls, [])

    def test_explicit_provider_selection_preserves_global_default(self):
        self.start('provider', self.research(providerId='provider-two'))
        result = self.await_status('provider')
        self.assertEqual(result['provider'], 'provider-two'); self.assertEqual(result['model'], 'other-model')
        self.assertEqual(self.providers.selected()['id'], 'provider-one')

    def test_authored_description_preserves_static_metadata_and_does_not_create_article(self):
        knowledge = KnowledgeStore(self.registry, self.project)
        item = dict(id='component', kind='entity', type='component', title='Example component', provenance='static', generatedBy='fixture',
                    source=dict(path='example.py', line=1), documentRefs=['existing'])
        knowledge.changeset(1, 'object', [dict(op='put', item=item)], 'Object fixture')
        self.start('research', self.research(operation='architecture-analyze', objectId='component', template='explain', revision=2))
        result = self.await_status('research'); updated = knowledge.read('component')
        self.assertEqual(updated['provenance'], 'static'); self.assertEqual(updated['source'], item['source'])
        self.assertEqual(updated['documentRefs'], ['existing']); self.assertIn('descriptionBasis', updated)
        self.assertEqual(result['resultRef'], 'knowledge/entity/component')
        self.assertEqual(knowledge.context()['counts']['document'], 1)
        self.assertEqual(self.service.research_history(self.project)['items'][0]['actionId'], 'research')
        self.assertEqual(result['sourceBasis']['kind'], 'saved-knowledge')

    def code_research(self):
        root = Path(self.temp.name) / 'source'; root.mkdir()
        (root / 'example.py').write_text('class Example:\n    pass\n', encoding='utf-8')
        self.project = self.registry.create('Source example', [str(root)])['id']
        KnowledgeStore(self.registry, self.project).changeset(0, 'component', [dict(op='put', item=dict(id='component', kind='entity', type='component', title='Example component'))], 'Component fixture')
        return dict(operation='architecture-analyze', objectId='component', template='explain', revision=1)

    def drain_scans(self):
        executor = getattr(self.registry, '_knowledge_executor', None)
        if executor is not None: executor.shutdown(wait=True)

    def test_first_code_research_scans_then_reads_guarded_source(self):
        research = self.code_research(); self.addCleanup(self.drain_scans); self.read_source = True
        self.start('first-scan', research); result = self.await_status('first-scan')
        self.assertEqual(result['sourceBasis']['kind'], 'verified-first-scan'); self.assertEqual(result['sourceBasis']['revision'], 2)
        self.assertEqual(result['sourceBasis']['state'], 'ready'); self.assertEqual(len(self.calls), 1)
        self.assertIn('class Example', json.dumps(self.source_reads[0]))
        knowledge = KnowledgeStore(self.registry, self.project); job = knowledge.job(result['scanJob'])
        self.assertEqual(job['receipt']['revision'], 2)
        self.assertIsNone(job['task']); self.assertIsNone(job['stage'])
        self.start('already-scanned', dict(research, revision=knowledge.context()['revision']))
        again = self.await_status('already-scanned')
        self.assertNotIn('scanJob', again); self.assertEqual(again['sourceBasis']['kind'], 'saved-knowledge')

    def test_scan_failure_prevents_model_call(self):
        research = self.code_research()
        def failed(store, job):
            job = dict(job, state='failed', error='Synthetic scan failure')
            with store.registry.connect() as connection:
                connection.execute('UPDATE knowledge_jobs SET state=?,body=? WHERE project=? AND id=?', ('failed', json.dumps(job), store.project, job['id']))
        self.addCleanup(self.drain_scans)
        with patch.object(KnowledgeStore, '_scan_job', failed):
            self.start('failed-scan', research); result = self.await_status('failed-scan', ('failed',))
        self.assertEqual(result['error']['code'], 'scan_not_ready'); self.assertEqual(self.calls, [])

    def test_scan_concurrent_revision_and_foreign_ownership_are_not_adopted(self):
        research = self.code_research(); original = KnowledgeStore._scan_job
        def concurrent(store, job):
            store.changeset(store.context()['revision'], 'concurrent', [dict(op='put', item=dict(id='user-note', kind='document', title='User note', markdown='Concurrent content'))], 'Concurrent edit')
            original(store, job)
        self.addCleanup(self.drain_scans)
        with patch.object(KnowledgeStore, '_scan_job', concurrent):
            self.start('concurrent-scan', research); result = self.await_status('concurrent-scan', ('failed',))
        self.assertEqual(result['error']['code'], 'scan_revision_conflict'); self.assertEqual(self.calls, [])
        self.assertEqual(KnowledgeStore(self.registry, self.project).read('user-note')['markdown'], 'Concurrent content')
    def test_foreign_scan_ownership_is_not_adopted(self):
        research = self.code_research()
        def foreign(store, **arguments):
            return dict(id='foreign-scan', state='running', actor='api:other', task='other-task', stage='other-stage', workspaceRevision=store.context()['workspaceRevision'])
        with patch.object(KnowledgeStore, 'start_scan', foreign):
            self.start('foreign-scan', research); result = self.await_status('foreign-scan', ('failed',))
        self.assertEqual(result['error']['code'], 'scan_ownership_conflict'); self.assertEqual(self.calls, [])

    def test_empty_first_scan_has_explicit_reason_without_paid_call(self):
        research = self.code_research(); (Path(self.temp.name) / 'source' / 'example.py').unlink(); self.addCleanup(self.drain_scans)
        self.start('empty-scan', research); result = self.await_status('empty-scan', ('failed',))
        self.assertEqual(result['error']['code'], 'scan_empty_inventory'); self.assertIn('No supported source files', result['error']['message'])
        self.assertEqual(self.calls, [])

    def test_history_markers_and_old_task_receipts_remain_readable(self):
        self.gate = threading.Event(); self.start('marker')
        self.assertEqual(self.service.recent(self.project, '__research__:existing')[0]['actionId'], 'marker')
        self.assertEqual(self.service.recent(self.project, '__research__:other'), [])
        self.gate.set(); self.await_status('marker')
        self.assertEqual(self.service.recent(self.project, '__research__:existing')[0]['status'], 'completed')
        self.assertEqual(self.service.recent(self.project, 'task'), [])
        body = dict(project=self.project, task=None, target='project', actionId='past', status='completed', research=False, transport='api', createdAt=1)
        with self.registry.connect() as connection:
            connection.execute('INSERT INTO api_agent_runs VALUES(?,?,?,?,?,?)', (self.project, 'past', 'old-signature', 'completed', json.dumps(body), 1))
        self.assertEqual(self.service.recent(self.project, '__project_review__')[0], body)
        with self.assertRaises(ChatActionError): self.service.start(self.project, None, 'past', target='project', mode='plan', intent='review')
        with self.assertRaises(ChatActionError): self.service.cancel(self.project, 'past')

    def test_project_decomposition_publishes_components_and_view_atomically(self):
        self.overrides = dict(components=[dict(title='Planning', description='Coordinates planned work.', paths=[]), dict(title='Knowledge', description='Retains documents.', paths=[])])
        self.start('decompose', dict(operation='architecture-analyze', objectId='project:' + self.project, template='decompose', revision=1))
        result = self.await_status('decompose'); knowledge = KnowledgeStore(self.registry, self.project)
        self.assertEqual(result['proposalState'], 'applied'); self.assertEqual(result['componentRevision'], 2)
        self.assertEqual(len(result['componentIds']), 2); self.assertEqual(knowledge.context()['counts'], {'document': 1, 'entity': 2, 'view': 1})
        self.assertEqual(knowledge.read('view:api-result:decompose')['nodeIds'], result['componentIds'])
        self.assertEqual(knowledge.history()['items'][0]['changedCount'], 3); self.assertIn('strict JSON object', self.instructions[0])

    def test_malformed_result_preserved_only_in_receipt_without_knowledge_changes(self):
        self.raw_text = '```json\n{"summary":"Bad fenced payload","components":[]}\n```'
        self.start('invalid'); result = self.await_status('invalid', ('failed',))
        self.assertEqual(result['error']['code'], 'research_result_invalid'); self.assertEqual(result['resultText'], self.raw_text)
        self.assertIsNone(result['resultRef']); self.assertEqual(KnowledgeStore(self.registry, self.project).context()['revision'], 1)

    def test_unread_evidence_records_fixed_reason_without_publishing(self):
        self.overrides = dict(evidence=[dict(kind='source', path='unread.py', hash='0' * 64, line=1)])
        self.start('unread-evidence')
        result = self.await_status('unread-evidence', ('failed',))
        self.assertEqual(result['error']['code'], 'research_evidence_unverified')
        self.assertEqual(result['error']['validationReason'], 'source_not_read')
        self.assertIsNone(result['resultRef'])
        self.assertEqual(KnowledgeStore(self.registry, self.project).context()['revision'], 1)

    def test_tool_limit_records_only_safe_operation_and_size_diagnostics(self):
        self.failure = ProviderRuntimeError('research_tool_result_limit', diagnostic=dict(
            tool='hub_knowledge', action='context', resultBytes=25000, limitBytes=24000,
            private='provider secret and source content'))
        self.start('tool-limit')
        result = self.await_status('tool-limit', ('failed',))
        self.assertEqual({key: result['error'][key] for key in ('tool', 'action', 'resultBytes', 'limitBytes')},
            dict(tool='hub_knowledge', action='context', resultBytes=25000, limitBytes=24000))
        self.assertNotIn('private', result['error'])
        self.assertIsNone(result['resultRef'])
        self.assertEqual(KnowledgeStore(self.registry, self.project).context()['revision'], 1)

    def test_project_overview_is_visible_in_context_and_keeps_earlier_versions(self):
        identifier = 'project:' + self.project
        request = dict(operation='architecture-analyze', objectId=identifier, template='explain', revision=1)
        self.overrides = dict(description='Project purpose and main responsibilities.')
        self.start('project-overview', request)
        first = self.await_status('project-overview')
        self.assertEqual(first['resultRef'], 'knowledge/entity/' + identifier)
        knowledge = KnowledgeStore(self.registry, self.project)
        overview = knowledge.context()['projectOverview']
        self.assertEqual(overview['id'], identifier)
        self.assertEqual(overview['description'], self.overrides['description'])
        self.assertEqual(overview['revision'], 2)
        self.overrides = dict(description='Updated project purpose and responsibilities.')
        self.start('project-overview-updated', dict(request, revision=2))
        self.await_status('project-overview-updated')
        self.assertEqual(knowledge.read(identifier, 2)['description'], 'Project purpose and main responsibilities.')
        self.assertEqual(knowledge.context()['projectOverview']['description'], self.overrides['description'])
        from knowledge_research import read_object
        self.assertEqual(read_object(knowledge, identifier)['description'], self.overrides['description'])
        self.assertEqual(knowledge.context()['counts'], dict(document=1, entity=1))

    def test_project_decomposition_reuses_existing_subsystems_and_preserves_overview(self):
        knowledge = KnowledgeStore(self.registry, self.project)
        policy = knowledge.context()['policy']
        policy['components'] = [dict(id='known', title='Known subsystem', paths=[])]
        root = dict(id='project:' + self.project, kind='entity', type='project', title='Example',
                    description='Keep the project overview.')
        known = dict(id='known', kind='entity', type='component', title='Known subsystem', paths=[],
                     description='Original description', documentRefs=['existing'], provenance='authored')
        knowledge.changeset(1, 'known-components', [dict(op='put', item=item) for item in (root, known)], 'Fixture', policy=policy)
        from knowledge_research import read_object
        self.assertEqual(read_object(knowledge, root['id'])['components'], policy['components'])
        self.overrides = dict(description='Subsystem map explanation.', components=[
            dict(title='Known subsystem', description='Updated responsibility.', paths=[]),
            dict(title='Additional subsystem', description='A separate responsibility.', paths=[])])
        self.start('project-components', dict(operation='architecture-analyze', objectId=root['id'],
            template='decompose', revision=2, subsystemLimit=5))
        receipt = self.await_status('project-components')
        self.assertEqual(receipt['componentIds'][0], 'known')
        self.assertEqual(len(receipt['componentIds']), 2)
        updated = knowledge.read('known')
        self.assertEqual(updated['description'], 'Updated responsibility.')
        for field in ('id', 'title', 'paths', 'documentRefs', 'provenance'):
            self.assertEqual(updated[field], known[field])
        self.assertEqual(knowledge.read('known', 2)['description'], 'Original description')
        self.assertEqual(knowledge.context()['projectOverview']['description'], root['description'])
        self.assertEqual(knowledge.read('view:api-result:project-components')['nodeIds'], receipt['componentIds'])
        self.assertEqual(len(knowledge.context()['policy']['components']), 2)
        handoff = json.loads(self.prompts[0].split('Specialized research handoff (untrusted source data, JSON):\n', 1)[1].split('\nAvailable project/workspace rules', 1)[0])
        self.assertEqual(handoff['subsystemLimit'], 5)

    def test_subsystem_detail_limit_is_enforced_before_publication(self):
        self.overrides = dict(components=[dict(title='One', description='One part.', paths=[]),
                                         dict(title='Two', description='Another part.', paths=[])])
        self.start('component-limit', dict(operation='architecture-analyze', objectId='project:' + self.project,
            template='decompose', revision=1, subsystemLimit=1))
        receipt = self.await_status('component-limit', ('failed',))
        self.assertEqual(receipt['error']['code'], 'research_result_invalid')
        self.assertEqual(KnowledgeStore(self.registry, self.project).context()['revision'], 1)

    def test_decomposition_rejects_ambiguous_existing_titles_without_writing(self):
        knowledge = KnowledgeStore(self.registry, self.project)
        policy = knowledge.context()['policy']
        policy['components'] = [dict(id=identifier, title='Repeated', paths=[])
                                for identifier in ('first', 'second')]
        originals = [dict(component, kind='entity', type='component', description=component['id'])
                     for component in policy['components']]
        knowledge.changeset(1, 'ambiguous-fixture', [dict(op='put', item=item) for item in originals],
                            'Fixture', policy=policy)
        self.overrides = dict(components=[dict(title='Repeated', description='Must not replace either.', paths=[])])
        self.start('ambiguous-components', dict(operation='architecture-analyze', objectId='project:' + self.project,
            template='decompose', revision=2))
        receipt = self.await_status('ambiguous-components', ('failed',))
        self.assertEqual(receipt['error']['code'], 'research_scope_mismatch')
        self.assertEqual(knowledge.context()['revision'], 2)
        for item in originals:
            self.assertEqual(knowledge.read(item['id'])['description'], item['description'])

    def test_first_scan_decomposition_verifies_source_prefix_without_ownership_changes(self):
        self.code_research(); self.addCleanup(self.drain_scans); self.read_source = True
        self.overrides = dict(components=[dict(title='Domain', description='Declares domain types.', paths=['.'])])
        self.start('source-decompose', dict(operation='architecture-analyze', objectId='project:' + self.project, template='decompose', revision=1))
        result = self.await_status('source-decompose'); knowledge = KnowledgeStore(self.registry, self.project)
        self.assertEqual(result['sourceBasis']['revision'], 2); self.assertEqual(result['componentRevision'], 3)
        component = knowledge.read(result['componentIds'][0]); self.assertEqual(component['paths'], ['.'])
        self.assertTrue(any(source.get('hash') for source in component['evidence']))
        self.assertTrue(all(file.get('component') is None for file in knowledge.search(kind='entity', type='file')['items']))

    def test_decomposition_revision_conflict_and_unverified_prefix_preserve_knowledge(self):
        self.overrides = dict(components=[dict(title='Proposed', description='Concept.', paths=[])])
        self.gate = threading.Event(); request = dict(operation='architecture-analyze', objectId='project:' + self.project, template='decompose', revision=1)
        self.start('stale', request); self.wait_model(); knowledge = KnowledgeStore(self.registry, self.project)
        knowledge.changeset(1, 'newer', [dict(op='put', item=dict(id='newer', kind='document', title='Newer data', markdown='Keep this'))], 'Newer edit')
        self.gate.set(); result = self.await_status('stale', ('failed',))
        self.assertEqual(result['error']['code'], 'research_revision_changed'); self.assertIsNone(result['resultRef']); self.assertIn('resultText', result)
        self.assertEqual(knowledge.context()['policy']['components'], []); self.assertEqual(knowledge.context()['counts'], {'document': 2})
        self.overrides = dict(components=[dict(title='Invented', description='No verified source.', paths=['invented'])])
        self.start('unverified', dict(request, revision=2)); result = self.await_status('unverified', ('failed',))
        self.assertEqual(result['error']['code'], 'research_publication_invalid'); self.assertEqual(knowledge.context()['revision'], 2)

    def test_cancel_scan_wait_stops_writes_and_model_call(self):
        research = self.code_research(); entered, gate = threading.Event(), threading.Event()
        def waiting(store, job):
            entered.set(); gate.wait(5); job = dict(job, state='interrupted')
            with store.registry.connect() as connection:
                connection.execute('UPDATE knowledge_jobs SET state=?,body=? WHERE project=? AND id=?', ('interrupted', json.dumps(job), store.project, job['id']))
        self.addCleanup(gate.set); self.addCleanup(self.drain_scans)
        with patch.object(KnowledgeStore, '_scan_job', waiting):
            self.start('cancel-scan', research); self.assertTrue(entered.wait(3)); self.service.close()
            before = json.loads(self.service.existing(self.project, 'cancel-scan')['body']); gate.set(); self.drain_scans()
            after = json.loads(self.service.existing(self.project, 'cancel-scan')['body'])
        self.assertEqual(before, after); self.assertEqual(after['status'], 'interrupted'); self.assertIsNone(after['resultRef']); self.assertEqual(self.calls, [])

    def test_explicit_cancel_and_shutdown_retain_receipt_without_writes(self):
        self.gate = threading.Event(); self.start('cancel'); self.wait_model()
        receipt = self.service.cancel(self.project, 'cancel'); self.assertTrue(receipt['cancelRequested'])
        result = self.await_status('cancel', ('outcome_unknown', 'interrupted'))
        self.assertEqual(result['error']['code'], 'cancelled'); self.assertIsNone(result['resultRef'])
        self.assertEqual(KnowledgeStore(self.registry, self.project).context()['revision'], 1)
        self.assertEqual(self.service.cancel(self.project, 'cancel'), result)
        self.start('cancel-close'); self.wait_model(2); self.service.close()
        self.assertIsNone(self.await_status('cancel-close', ('outcome_unknown', 'interrupted'))['resultRef'])

    def test_post_context_project_revision_change_rejects_before_model_queue(self):
        original = self.service.context_builder._research_context
        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            self.registry.store(self.project).record(dict(kind='note', taskId='task', title='Concurrent update', detail='Fresh data'))
            return result
        self.service.context_builder._research_context = changed
        with self.assertRaises(ChatActionError) as caught: self.start('changed')
        self.assertEqual(caught.exception.code, 'stale_revision'); self.assertEqual(self.calls, []); self.assertIsNone(self.service.existing(self.project, 'changed'))

    def test_context_system_rules_are_independent_of_native_task_bookkeeping(self):
        self.start('context'); self.await_status('context')
        self.assertNotIn('Bind your own', self.prompts[0]); self.assertNotIn('select or create your own research task', self.prompts[0])
        self.assertIn('does not inherit', self.instructions[0]); self.assertIn('AGENTS.md', self.instructions[0]); self.assertIn('not a read boundary', self.instructions[0])

    def test_documentation_refresh_preserves_classification_and_review_is_separate(self):
        self.start('refresh', self.research(operation='documentation-refresh')); result = self.await_status('refresh')
        self.assertEqual(result['resultRef'], 'knowledge/document/existing'); knowledge = KnowledgeStore(self.registry, self.project)
        document = knowledge.read('existing')
        self.assertEqual([document[field] for field in ('audience', 'section', 'type', 'status', 'visibility')], ['user', 'guide', 'how-to', 'current', 'internal'])
        self.start('review', self.research(operation='documentation-review', revision=2)); result = self.await_status('review')
        self.assertEqual(result['resultRef'], 'knowledge/document/doc:api-result:review'); self.assertEqual(knowledge.read('existing'), document)
        self.assertEqual(knowledge.read('doc:api-result:review')['status'], 'draft')

    def test_unverified_evidence_and_executable_markdown_leave_knowledge_unchanged(self):
        for action, fields, code in [('empty', dict(evidence=[]), 'research_evidence_unverified'),
            ('invented', dict(evidence=[dict(kind='source', path='missing.py', hash='a' * 64, line=1)]), 'research_evidence_unverified'),
            ('html', dict(markdown='<script>alert(1)</script>'), 'research_result_invalid')]:
            with self.subTest(action=action):
                self.overrides = fields; self.start(action); result = self.await_status(action, ('failed',))
                self.assertEqual(result['error']['code'], code); self.assertEqual(KnowledgeStore(self.registry, self.project).context()['revision'], 1)

    def test_source_change_after_read_prevents_publication(self):
        research = self.code_research(); self.addCleanup(self.drain_scans); self.read_source = True
        self.hook = lambda broker: (Path(self.temp.name) / 'source' / 'example.py').write_text('class Newer:\n    pass\n', encoding='utf-8')
        self.start('source-changed', research); result = self.await_status('source-changed', ('failed',))
        self.assertEqual(result['error']['code'], 'research_source_changed'); self.assertIsNone(result['resultRef'])
        self.assertEqual(KnowledgeStore(self.registry, self.project).context()['revision'], 2)

    def test_late_transport_cannot_write_after_close(self):
        entered, gate = threading.Event(), threading.Event()
        class LateDriver:
            def __init__(self, *args, **kwargs): pass
            def run(self, *args, **kwargs):
                entered.set(); gate.wait(2); return dict(text='Late result')
        service = self.make_service(LateDriver); self.start('late', service=service); self.assertTrue(entered.wait(3)); service.close(timeout=.12)
        before = json.loads(service.existing(self.project, 'late')['body']); gate.set(); service._runs['late']['future'].result(timeout=3)
        self.assertEqual(json.loads(service.existing(self.project, 'late')['body']), before); self.assertIsNone(before['resultRef'])
        other = self.make_service(); self.assertEqual(json.loads(other.existing(self.project, 'late')['body'])['status'], 'interrupted')

    def test_facade_preserves_native_receipts_after_provider_selection(self):
        from hub_chat_actions import ChatActions
        native = ChatActions(self.registry); self.addCleanup(native.close)
        facade = UnifiedActions(self.registry, providers=self.providers, driver_factory=self.driver); self.addCleanup(facade.close)
        now = time.time(); receipt = dict(project=self.project, task='task', actionId='native', status='completed', transport='stdio', createdAt=now)
        with self.registry.connect() as connection:
            connection.execute('INSERT INTO codex_chat_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (self.project, 'task', 'native', 'digest', 'completed', 'thread', 'turn', None, 'context', now, now, json.dumps(receipt)))
        rows = facade.recent(self.project, 'task'); self.assertEqual(rows[0]['transport'], 'stdio'); self.assertFalse(rows[0]['resumeAllowed'])

    def test_facade_research_runs_without_native_executor_modules_or_ledger(self):
        with patch.dict(sys.modules, {'hub_chat_actions': None, 'codex_adapter': None}):
            facade = UnifiedActions(self.registry, providers=self.providers, driver_factory=self.driver); self.addCleanup(facade.close)
            self.assertEqual(facade.recent(self.project, 'task'), []); self.assertEqual(facade.research_history(self.project)['items'], [])
            facade.start_research(self.project, self.research(), 'independent-api'); self.assertEqual(self.await_status('independent-api', service=facade.api)['status'], 'completed')
            self.providers.item = None
            with self.assertRaises(ChatActionError) as caught: facade.start(self.project, 'task', 'no-executor')
            self.assertEqual(caught.exception.code, 'task_execution_removed')


if __name__ == '__main__':
    unittest.main()
