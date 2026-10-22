"""Consent, optional native identity and bounded control-probe contracts."""
from contextlib import closing
import hashlib
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from agent_bindings import BindingError, Connections, fingerprint
from agent_instructions import BOOTSTRAP, bundle, read, update
from agent_launches import Launches
from agent_runtime import call
from connection_capabilities import HttpControl, Profiles, validate_profile, probe_failure
from outbound_http import OutboundError
from native_chats import linked, normalize
from knowledge_store import KnowledgeStore
from project_bindings import ProjectBindings
from project_registry import ProjectRegistry
from project_portal import PortalServer
from task_chats import chat_history

CHAT = '11111111-1111-4111-8111-111111111111'


class ConnectionOnboardingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.registry = ProjectRegistry(Path(self.temporary.name) / 'home', standalone=True)
        self.addCleanup(self.registry.close_connection_pool)
        self.connections = Connections(self.registry)
        invite = self.connections.invite(request_id='a' * 32)
        self.connection = self.connections.enroll(invite['token'], 'example-client', 'example-binding')
        self.profiles = Profiles(self.registry)

    def invoke(self, tool, **arguments):
        return call(self.registry, self.connection['token'], tool, dict(session='own-conversation', **arguments))

    def project_binding(self, request_id='9' * 32):
        root = Path(self.temporary.name) / ('workspace-' + request_id[:4])
        root.mkdir()
        project = self.registry.create('Routed project', roots=[str(root.resolve())])['id']
        return ProjectBindings(self.registry).execute(self.connection['binding'], dict(
            action='resolve', scope=dict(kind='workspace', root=str(root.resolve())),
            project=project, name='Routed project', requestId=request_id))['binding']

    def test_portable_workflow_and_separate_user_rules_are_the_same_bundle(self):
        original = (ROOT / 'scripts/agent-workflow.md').read_text(encoding='utf-8').rstrip()
        shipped = (ROOT / 'tools/project-portal/plugins/project-hub/assets/agent-workflow.md').read_text(encoding='utf-8')
        self.assertEqual(original, shipped.rstrip(), 'the shipped connection rules must not drift from the canonical workflow')
        self.assertIn('you MUST send nativeChat on hub_context', original)
        self.assertIn('task.sources', original)
        self.assertIn('nativeChat identity and available title', BOOTSTRAP)
        self.assertIn('Do not create or update a user\ntask, plan stage or work record', original)
        self.assertIn('Do not create or update a user\ntask, plan stage or work record', shipped)
        self.assertIn('creates no user task, stage or work', BOOTSTRAP)
        before = read(self.registry)
        custom = 'Keep evidence and preserve user documents.'
        changed = update(self.registry, dict(expected=before['revision'], text=custom))
        value = bundle(self.registry, 'http://127.0.0.1:8769')
        self.assertIn(original, value['workflow'])
        self.assertIn(custom, value['workflow'])
        self.assertFalse(value['persistentInstructions']['requiresConsent'])
        self.assertTrue(value['persistentInstructions']['nativePermissionsRequired'])
        self.assertEqual(value['instructionBundle']['files']['user-additions.md'],custom)
        self.assertFalse(value['persistentInstructions']['credentialsIncluded'])
        self.assertEqual(value['revision'], changed['revision'])
        self.assertEqual(update(self.registry, dict(expected=before['revision'], text=custom))['revision'], changed['revision'])
        with self.assertRaises(BindingError):
            update(self.registry, dict(expected=before['revision'], text='A conflicting edit'))
        self.assertEqual(read(self.registry)['text'], custom)

    def test_server_launch_envelope_separates_internal_research_from_tracked_tasks(self):
        workspace = Path(self.temporary.name) / 'workspace'
        workspace.mkdir()
        scope = dict(kind='workspace', root=str(workspace.resolve()), nativeRef='example-workspace')
        binding = ProjectBindings(self.registry).execute(self.connection['binding'], dict(
            action='resolve', scope=scope, requestId='1' * 32))['binding']
        selected = dict(project=binding['project'], workspace=binding['scope']['root'],
                        bindingId=binding['id'], bindingRevision=binding['revision'], projectScope=binding['scope'])
        self.invoke('hub_context', **selected)
        task = self.invoke('hub_task', **selected, title='Example implementation', scope=['Example'],
                           acceptance=['Result is recorded'])['task']
        self.invoke('hub_plan', **selected, task=task, stage='implement', title='Implement')
        KnowledgeStore(self.registry, binding['project']).changeset(
            0, 'fixture', [dict(op='put', item=dict(id='component', kind='entity', type='component', title='Component'))], 'Fixture')

        endpoint = 'http://127.0.0.1:9988'
        self.profiles.describe(self.connection['binding'], dict(
            schemaVersion=1, control=dict(protocol='http-json', endpoint=endpoint), capabilities=dict(
                createChat=dict(path='/chats', projectRouting=True,
                                arguments=dict(prompt='$prompt', requestId='$requestId', projectScope='$projectScope')))))
        self.profiles.configure(dict(id=self.connection['binding'], protocol='http-json', endpoint=endpoint,
                                     apiKey='', requestId='2' * 32))

        sent = []
        def capture(_spec, payload):
            sent.append(payload)
            return dict(id='example-native-chat')

        with patch('agent_launches.HttpControl.action', side_effect=capture):
            Launches(self.registry).start(self.connection['binding'], dict(
                requestId='3' * 32, bindingId=binding['id'], operation='architecture-analyze',
                research=dict(operation='architecture-analyze', objectId='component', revision=1)))
            research_prompt = sent[-1]['$prompt']
            self.assertEqual(sent[-1]['$envelope']['bookkeeping'],
                             dict(mode='internal', createTask=False, createStage=False, createWork=False))
            self.assertIn('do not create or update any user task', research_prompt)
            self.assertIn('do not call hub_task, hub_plan, hub_begin, hub_report or hub_task_close', research_prompt)
            self.assertEqual(sent[-1]['$envelope']['resultDestination']['kind'], 'knowledge-document')

            Launches(self.registry).start(self.connection['binding'], dict(
                requestId='4' * 32, bindingId=binding['id'], operation='task-execute', task=task, stage='implement'))
            self.assertEqual(sent[-1]['$envelope']['bookkeeping'], dict(mode='tracked'))
            self.assertIn('Task-execute launches use the normal tracked task pipeline', sent[-1]['$prompt'])
            self.assertEqual(sent[-1]['$envelope']['resultDestination']['kind'], 'task-report')

    def test_reading_rules_never_creates_native_configuration(self):
        before = {str(path) for path in self.registry.home.rglob('*')}
        read(self.registry)
        self.profiles.public(self.connection['binding'])
        self.assertEqual({str(path) for path in self.registry.home.rglob('*')}, before)

    def test_native_links_keep_resource_parameters_but_reject_credentials(self):
        from native_chats import normalize, open_uri
        source = 'https://example.test/chat?id=resource#messages'
        self.assertEqual(open_uri(source), source)
        for suffix in ('?access_token=private', '?api%5Fkey=private', '#access_token=private',
                       '#chat?client_secret=private', '?X-Amz-Signature=private'):
            with self.assertRaises(BindingError):
                open_uri('https://example.test/chat' + suffix)
        unknown = normalize(dict(client='chatgpt-desktop', nativeId=CHAT))
        self.assertNotIn('openUri', unknown)
        self.assertFalse(unknown['openingDocumented'])

    def test_native_chat_templates_keep_identity_encoded_and_do_not_prove_opening(self):
        from native_chats import template_uri
        self.assertEqual(template_uri('https://example.test/chats/{nativeId}', 'chat/one?x=1'),
                         'https://example.test/chats/chat%2Fone%3Fx%3D1')
        for template in ('javascript:{nativeId}', 'https://{nativeId}.example.test/chat',
                         'https://example.test/chat?access_token={nativeId}'):
            with self.assertRaises(BindingError):
                template_uri(template, 'native-chat')
        self.profiles.describe(self.connection['binding'], dict(schemaVersion=1,
            nativeChat=dict(client='example-client', nativeId='native-chat'),
            capabilities=dict(openChat=dict(uriTemplate='https://example.test/chats/{nativeId}'))))
        value = self.profiles.public(self.connection['binding'])
        self.assertEqual(value['nativeChat']['openUri'], 'https://example.test/chats/native-chat')
        self.assertEqual(value['capabilities']['openChat']['state'], 'client-reported')
        self.assertFalse(value['capabilities']['openChat']['guiVerified'])
        project = self.registry.create('Example project')['id']
        self.invoke('hub_task', project=project, title='Linked task', scope=['Example'], acceptance=['Linked'],
                    nativeChat=dict(client='example-client', nativeId='another-chat'))
        self.assertEqual(linked(self.registry, project)[0]['resource']['openUri'],
                         'https://example.test/chats/another-chat')

    def test_description_needs_no_project_and_is_not_verification(self):
        value = self.invoke('hub_connection', action='describe', profile={
            'schemaVersion': 1, 'clientVersion': 'example', 'model': 'reported-model',
            'nativeChat': {'client': 'codex', 'nativeId': CHAT},
            'capabilities': {'createChat': {'tool': 'create_conversation', 'arguments': {'prompt': '$prompt'}}},
            'persistentInstructions': {'scope': 'project', 'destination': 'AGENTS.md', 'consent': True, 'revision': 'v1', 'status': 'saved'}})
        self.assertEqual(self.registry.list()['projects'], [])
        self.assertEqual(value['nativeChat']['openUri'], 'codex://threads/' + CHAT)
        self.assertEqual(value['capabilities']['createChat']['state'], 'unknown')
        self.assertFalse(value['capabilities']['openChat']['guiVerified'])
        self.assertEqual(value['profile']['persistentInstructions']['verification'], 'client-reported')
        with self.assertRaises(BindingError):
            validate_profile({'schemaVersion': 1, 'persistentInstructions': {'scope': 'application', 'destination': 'rules', 'consent': False, 'status': 'saved'}})
        with self.assertRaises(BindingError):
            validate_profile({'schemaVersion': 1, 'apiKey': 'private'})

    def test_reconnect_preserves_binding_actor_profile_and_old_history(self):
        identifier = self.connection['binding']
        self.profiles.describe(identifier, {'schemaVersion': 1, 'model': 'Example'})
        self.connections.revoke(identifier)
        invitation = self.connections.reconnect(identifier, request_id='b' * 32)
        self.assertEqual(invitation, self.connections.reconnect(identifier, request_id='b' * 32))
        restored = self.connections.enroll(invitation['token'], 'example-client', 'example-binding')
        self.assertEqual(restored['binding'], identifier)
        self.assertEqual(self.profiles.profile(identifier)['model'], 'Example')
        self.assertNotEqual(restored['token'], self.connection['token'])
        with self.assertRaises(BindingError):
            self.connections.authenticate(self.connection['token'])
        self.assertEqual(restored, self.connections.enroll(invitation['token'], 'example-client', 'example-binding'))

    def test_control_is_explicit_and_private_key_cannot_follow_a_changed_origin(self):
        identifier = self.connection['binding']
        self.profiles.describe(identifier, {'schemaVersion': 1, 'control': {'protocol': 'http-json', 'endpoint': 'https://example.invalid/api'}})
        self.assertEqual(self.profiles.test(identifier, 'http://127.0.0.1:8769')['tests'][0]['state'], 'configuration_required')
        config = dict(action='configure-control', id=identifier, protocol='http-json', endpoint='https://example.invalid/api', apiKey='PrivateKeyValue', requestId='c' * 32)
        with patch('secret_vault.save') as save:
            self.assertEqual(self.profiles.configure(config), dict(saved=True, id=identifier))
            self.assertEqual(self.profiles.configure(config), dict(saved=True, id=identifier))
            self.assertEqual(save.call_count, 1)
        public = json.dumps(self.profiles.public(identifier))
        self.assertNotIn('PrivateKeyValue', public)
        self.assertNotIn('credentialRef', public)
        with self.assertRaises(BindingError) as failure:
            self.profiles.configure(dict(config, endpoint='https://another.invalid/api', apiKey='', requestId='d' * 32))
        self.assertEqual(failure.exception.code, 'control_key_required')

    def test_configure_integration_atomically_saves_profile_and_control_and_replays(self):
        identifier = self.connection['binding']
        endpoint_value = 'https://integration.example'
        profile = dict(schemaVersion=1, control=dict(protocol='http-json', endpoint=endpoint_value),
                       capabilities=dict(createChat=dict(path='/create')))
        self.profiles.describe(identifier, dict(schemaVersion=1, model='before'))
        expected = self.profiles.public(identifier)['profileRevision']
        request = dict(action='configure-integration', id=identifier, protocol='http-json',
                       endpoint=endpoint_value, apiKey='integration-key', requestId='c' * 32,
                       profile=profile, expectedProfileRevision=expected)
        with patch('secret_vault.save') as save:
            result = self.profiles.configure(request)
            self.assertEqual(save.call_count, 1)
            self.assertEqual(self.profiles.configure(request), result)
        self.assertEqual(result['profileRevision'], fingerprint(profile))
        self.assertEqual(self.profiles.profile(identifier), profile)
        self.assertEqual(self.profiles.public(identifier)['control']['endpoint'], endpoint_value)

    def test_configure_integration_accepts_explicit_null_revision_for_first_profile(self):
        identifier = self.connection['binding']
        endpoint_value = 'https://first-integration.example'
        profile = dict(schemaVersion=1, control=dict(protocol='http-json', endpoint=endpoint_value),
                       capabilities=dict(createChat=dict(path='/create')))
        with patch('secret_vault.save'):
            result = self.profiles.configure(dict(action='configure-integration', id=identifier,
                protocol='http-json', endpoint=endpoint_value, apiKey='first-key', requestId='0' * 32,
                profile=profile, expectedProfileRevision=None))
        self.assertEqual(result['profileRevision'], fingerprint(profile))
        self.assertEqual(self.profiles.profile(identifier), profile)

    def test_configure_integration_rejects_stale_profile_before_secret_save(self):
        identifier = self.connection['binding']
        self.profiles.describe(identifier, dict(schemaVersion=1, model='before'))
        expected = self.profiles.public(identifier)['profileRevision']
        changed = dict(schemaVersion=1, model='changed')
        changed = dict(changed, capabilities={})
        self.profiles.describe(identifier, changed)
        target = dict(schemaVersion=1, control=dict(protocol='http-json', endpoint='https://stale.example'),
                      capabilities=dict(createChat=dict(path='/create')))
        with patch('secret_vault.save') as save, self.assertRaises(BindingError) as error:
            self.profiles.configure(dict(action='configure-integration', id=identifier, protocol='http-json',
                endpoint='https://stale.example', apiKey='stale-key', requestId='d' * 32,
                profile=target, expectedProfileRevision=expected))
        self.assertEqual(error.exception.code, 'profile_revision_conflict')
        save.assert_not_called()
        self.assertEqual(self.profiles.profile(identifier), changed)

    def test_configure_integration_credential_failure_preserves_previous_profile_and_control(self):
        identifier = self.connection['binding']
        old_endpoint = 'https://old-integration.example'
        old = dict(schemaVersion=1, control=dict(protocol='http-json', endpoint=old_endpoint),
                   capabilities=dict(createChat=dict(path='/old')))
        self.profiles.describe(identifier, old)
        expected = self.profiles.public(identifier)['profileRevision']
        with patch('secret_vault.save'):
            self.profiles.configure(dict(action='configure-integration', id=identifier, protocol='http-json',
                endpoint=old_endpoint, apiKey='old-key', requestId='e' * 32, profile=old,
                expectedProfileRevision=expected))
        new = dict(schemaVersion=1, control=dict(protocol='http-json', endpoint='https://new-integration.example'),
                   capabilities=dict(createChat=dict(path='/new')))
        current_revision = self.profiles.public(identifier)['profileRevision']
        with self.assertRaises(BindingError) as error:
            self.profiles.configure(dict(action='configure-integration', id=identifier, protocol='http-json',
                endpoint='https://new-integration.example', apiKey='', requestId='f' * 32,
                profile=new, expectedProfileRevision=current_revision))
        self.assertEqual(error.exception.code, 'control_key_required')
        self.assertEqual(self.profiles.profile(identifier), old)
        self.assertEqual(self.profiles.public(identifier)['control']['endpoint'], old_endpoint)

    def test_describe_and_configure_with_base_do_not_start_a_probe(self):
        identifier = self.connection['binding']
        control = dict(protocol='http-json', endpoint='https://example.test')
        profile = dict(schemaVersion=1, control=control,
                       capabilities=dict(createChat=dict(path='/chats')))
        with patch.object(self.profiles, 'test') as probe, patch.object(HttpControl, 'action') as action:
            self.profiles.describe(identifier, profile, base='http://127.0.0.1:8769')
            self.profiles.configure(dict(action='configure-control', id=identifier,
                                         requestId='1' * 32, apiKey='', **control),
                                    base='http://127.0.0.1:8769')
            probe.assert_not_called()
            action.assert_not_called()
        with self.registry.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM connection_probes').fetchone()[0], 0)

    def test_describe_and_configure_preserve_existing_probe_history(self):
        identifier = self.connection['binding']
        self.profiles.describe(identifier, dict(schemaVersion=1))
        revision = self.profiles.public(identifier)['profileRevision']
        self.profiles.setup()
        body = dict(id='history-fixture', state='passed', profileRevision=revision,
                    controlRevision=None, capabilities=dict(createChat=dict(state='verified')))
        with self.registry.connect() as c:
            c.execute('INSERT INTO connection_probes VALUES(?,?,?,?,?,?,?)',
                      ('history-fixture', identifier, revision, json.dumps(body),
                       hashlib.sha256(b'history-nonce').hexdigest(), time.time() + 60, time.time()))
        control = dict(protocol='http-json', endpoint='https://example.test')
        with patch.object(self.profiles, 'test') as probe, patch.object(HttpControl, 'action') as action:
            self.profiles.describe(identifier, dict(schemaVersion=1, control=control,
                capabilities=dict(createChat=dict(path='/chats'))), base='http://127.0.0.1:8769')
            self.profiles.configure(dict(action='configure-control', id=identifier,
                requestId='8' * 32, apiKey='', **control), base='http://127.0.0.1:8769')
            probe.assert_not_called()
            action.assert_not_called()
        self.assertEqual(self.profiles.public(identifier)['tests'][0]['id'], 'history-fixture')

    def test_declared_internal_create_without_control_is_interface_missing(self):
        identifier = self.connection['binding']
        self.profiles.describe(identifier, dict(schemaVersion=1,
            capabilities=dict(createChat=dict(tool='create_conversation'))))
        value = self.profiles.public(identifier)
        self.assertEqual(value['controlStatus']['state'], 'interface_missing')
        self.assertFalse(value['controlStatus']['canTest'])
        self.assertEqual(value['features']['createChat']['state'], 'interface_missing')

    def test_history_pages_all_attempts_with_global_counts_and_connection_isolation(self):
        identifier = self.connection['binding']
        self.profiles.describe(identifier, dict(schemaVersion=1))
        invite = self.connections.invite(request_id='c' * 32)
        other = self.connections.enroll(invite['token'], 'other-client', 'other-connection')['binding']
        revision = self.profiles._read('connection_profiles', identifier)['revision']
        now = time.time()
        rows = []
        for index in range(1003):
            state = 'passed' if index < 1000 else 'failed' if index < 1002 else 'awaiting_reply'
            body = dict(id=f'probe-{index:04}', state=state, startedAt=now-30,
                        profileRevision=revision, controlRevision=None, capabilities={})
            rows.append((body['id'], identifier, revision, json.dumps(body), 'nonce-hash', now-1, index//2))
        foreign = dict(id='foreign-probe', state='passed', message='OTHER-CONNECTION', capabilities={})
        rows.append((foreign['id'], other, 'other-revision', json.dumps(foreign), 'other-nonce', now+30, 2000))
        with self.registry.connect() as c:
            c.executemany('INSERT INTO connection_probes VALUES(?,?,?,?,?,?,?)', rows)
        first = self.profiles.history(identifier)
        self.assertEqual((first['total'], first['offset'], first['limit'], len(first['tests'])), (1003, 0, 20, 20))
        self.assertEqual(first['counts'], dict(passed=1000, failed=2, timeout=1, configuration=0, cancelled=0, running=0))
        self.assertEqual(first['tests'][0]['state'], 'timed_out')
        self.assertTrue(first['tests'][0]['current'])
        self.assertNotIn('OTHER-CONNECTION', json.dumps(first))
        second = self.profiles.history(identifier, offset=20)
        self.assertFalse({t['id'] for t in first['tests']} & {t['id'] for t in second['tests']})
        self.assertEqual(first['counts'], second['counts'])
        self.assertEqual(first, self.profiles.history(identifier), 'tied timestamps must keep a stable order')
        last = self.profiles.history(identifier, offset=999999)
        self.assertEqual((last['offset'], len(last['tests'])), (1000, 3))
        self.assertEqual(last['tests'][-1]['id'], 'probe-0000')
        self.assertEqual(len(self.profiles.public(identifier)['tests']), 8, 'the catalog remains bounded')
        self.connections.revoke(identifier)
        self.assertEqual(self.profiles.history(identifier)['total'], 1003, 'revocation preserves readable history')
        with self.assertRaises(BindingError):
            self.profiles.test(identifier, 'http://127.0.0.1:8769')

    def test_history_http_validates_pages_and_handles_empty_connections(self):
        from urllib.error import HTTPError
        from urllib.request import urlopen
        server = PortalServer(('127.0.0.1', 0), registry=self.registry)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        base = f'http://127.0.0.1:{server.server_port}/api/v1/connection-tests?id={self.connection["binding"]}'
        with urlopen(base) as reply:
            data = json.load(reply)
        self.assertEqual((data['total'], data['offset'], data['tests']), (0, 0, []))
        for query in ('&offset=-1', '&limit=0', '&limit=101', '&limit=2.5', '&offset=abc', '&limit=2&limit=3', '&other=1'):
            with self.subTest(query=query), self.assertRaises(HTTPError) as error:
                urlopen(base+query)
            self.assertEqual(error.exception.code, 400)
        with self.assertRaises(BindingError) as error:
            self.profiles.history('unknown-connection')
        self.assertEqual(error.exception.code, 'connection_missing')

    def test_invitation_explains_separate_optional_native_chat_setup(self):
        from agent_api import bootstrap
        invitation = self.connections.invite(request_id='d' * 32)
        with patch('subprocess.Popen') as spawn, patch.object(Profiles, 'configure') as configure:
            instructions = bootstrap(self.registry, invitation['token'], 'http://127.0.0.1:8769')
        setup = instructions['setupInstructions']
        self.assertIn('MCP enrollment does not connect native chat control', setup)
        self.assertIn('optional local Codex desktop adapter', setup)
        self.assertIn('separate step from the current Codex chat', setup)
        self.assertIn('generates its own private key', setup)
        self.assertIn('For other clients report chat control as unavailable', setup)
        self.assertIn('Never invent a control endpoint', setup)
        self.assertEqual(instructions['localSetup']['supportedNativeHosts'], ['codex', 'cursor'])
        spawn.assert_not_called()
        configure.assert_not_called()

    def test_project_routing_requires_an_explicit_binding_before_creating_a_probe(self):
        identifier = self.connection['binding']
        control = dict(protocol='http-json', endpoint='https://example.test')
        self.profiles.describe(identifier, dict(schemaVersion=1, control=control,
            capabilities=dict(createChat=dict(path='/chats', projectRouting=True))))
        self.profiles.configure(dict(action='configure-control', id=identifier,
            requestId='1' * 32, apiKey='', **control))
        with self.assertRaises(BindingError) as error:
            self.profiles.test(identifier, 'http://127.0.0.1:8769')
        self.assertEqual(error.exception.code, 'project_binding_required')
        with self.registry.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM connection_probes').fetchone()[0], 0)
        with self.assertRaises(BindingError) as error:
            self.profiles.test(identifier, 'http://127.0.0.1:8769', binding_id='foreign-binding')
        self.assertEqual(error.exception.code, 'project_binding_missing')

    def routed_probe_fixture(self):
        identifier = self.connection['binding']
        first, second = self.project_binding('1' * 32), self.project_binding('2' * 32)
        control = dict(protocol='http-json', endpoint='https://example.test')
        profile = dict(schemaVersion=1, control=control, capabilities=dict(
            createChat=dict(path='/create', projectRouting=True)))
        self.profiles.describe(identifier, profile)
        self.profiles.configure(dict(action='configure-control', id=identifier,
            requestId='3' * 32, apiKey='', **control))
        executor = Mock()
        self.registry._connection_executor = executor
        self.profiles.test(identifier, 'http://127.0.0.1:8769', binding_id=first['id'])
        self.profiles.test(identifier, 'http://127.0.0.1:8769', binding_id=second['id'])
        return identifier, first, second, executor

    def test_project_probes_keep_their_destination_and_publish_application_wide_proof(self):
        identifier, first, second, executor = self.routed_probe_fixture()
        self.assertEqual(executor.submit.call_count, 2, 'another project needs its own probe')
        self.profiles.test(identifier, 'http://127.0.0.1:8769', binding_id=first['id'])
        self.assertEqual(executor.submit.call_count, 2, 'the same current project probe must not be duplicated')
        args = executor.submit.call_args_list[0].args[1:]
        with patch('connection_capabilities.HttpControl.action', return_value=dict(id='first-chat')):
            self.profiles._probe(*args)
        body, nonce = args[3], args[4]
        self.profiles.answer(dict(id=body['id'], nonce=nonce, nativeId='first-chat'))
        value = self.profiles.public(identifier)
        self.assertEqual(value['features']['createChat']['state'], 'verified')
        self.assertEqual(value['features']['callback']['state'], 'verified')
        self.assertNotIn('projectVerifications', value, 'application features must not be projected per project')
        self.assertEqual({t['projectBinding']['bindingId'] for t in value['tests']}, {first['id'], second['id']})

        # A later attempt in another project updates the same application result.
        args = executor.submit.call_args_list[1].args[1:]
        with patch('connection_capabilities.HttpControl.action', side_effect=RuntimeError('unavailable')):
            self.profiles._probe(*args)
        value = self.profiles.public(identifier)
        self.assertEqual(value['features']['callback']['state'], 'failed')
        self.assertEqual(value['tests'][0]['projectBinding']['bindingId'], second['id'])
        self.assertEqual(next(t for t in value['tests'] if t['projectBinding']['bindingId'] == first['id'])['state'], 'passed')

    def test_probe_retains_a_fixed_adapter_reason_and_operation_without_remote_messages(self):
        identifier, first, _, executor = self.routed_probe_fixture()
        args = executor.submit.call_args_list[0].args[1:]
        private = 'PrivateRemoteResponseShouldNeverReachTheCatalog'
        failure = HTTPError('https://example.test/create', 409, 'conflict',
            {'Content-Type': 'application/json'}, io.BytesIO(json.dumps({
                'error': 'native_catalog_unavailable', 'message': private, 'private': private}).encode()))
        opener = Mock()
        opener.open.side_effect = failure
        with patch('connection_capabilities.opener_for', return_value=opener):
            self.profiles._probe(*args)
        probe = next(t for t in self.profiles.public(identifier)['tests'] if t['id'] == args[3]['id'])
        self.assertEqual(probe['state'], 'failed')
        self.assertEqual(probe['error'], dict(code='native_catalog_unavailable', phase='create',
                                            httpStatus=409, outcomeUnknown=False))
        self.assertNotIn(private, json.dumps(probe))

    def test_control_errors_allow_only_fixed_codes_and_never_reflect_private_keys(self):
        for code in ('hub_project_binding_missing', '<script>arbitrary-remote-value</script>'):
            with self.subTest(code=code):
                secret = 'SeparatePrivateCredential'
                error = HTTPError('https://example.test/create', 403, 'no',
                    {'Content-Type': 'application/json'}, io.BytesIO(json.dumps({
                        'error': code, 'message': secret}).encode()))
                opener = Mock()
                opener.open.side_effect = error
                with patch('connection_capabilities.opener_for', return_value=opener):
                    control = HttpControl(dict(protocol='http-json', endpoint='https://example.test'), secret)
                    with self.assertRaises(OutboundError) as caught:
                        control.request({})
                diagnostic = caught.exception.diagnostic
                self.assertNotIn(secret, json.dumps(diagnostic))
                if code.startswith('<'):
                    self.assertNotIn('controlErrorCode', diagnostic)
                else:
                    self.assertEqual(diagnostic['controlErrorCode'], code)

    def test_probe_timeout_and_unknown_result_have_distinct_safe_reasons(self):
        for diagnostic, expected in ((dict(category='timeout',outcomeUnknown=True), 'control_timeout'),
                                     (dict(category='connect',outcomeUnknown=False), 'control_endpoint_unavailable'),
                                     (dict(category='http',controlErrorCode='request_id_conflict',outcomeUnknown=False), 'prior_outcome_requires_reconciliation'),
                                     (dict(category='http',httpStatus=401,outcomeUnknown=False), 'control_auth_failed')):
            result = probe_failure(OutboundError(diagnostic), 'send')
            self.assertEqual(result['code'], expected)
            self.assertEqual(result['phase'], 'send')

    def test_binding_change_rejects_late_callback_and_late_transport_update(self):
        identifier, first, _, executor = self.routed_probe_fixture()
        args = executor.submit.call_args_list[0].args[1:]
        with patch('connection_capabilities.HttpControl.action', return_value=dict(id='first-chat')):
            self.profiles._probe(*args)
        body, nonce = args[3], args[4]
        with self.registry.connect() as c:
            c.execute('UPDATE agent_project_bindings SET revision=revision+1 WHERE id=?', (first['id'],))
        value = self.profiles.public(identifier)
        old = next(t for t in value['tests'] if t['id'] == body['id'])
        self.assertFalse(old['current'])
        self.assertEqual(value['features']['callback']['state'], 'stale')
        with self.assertRaises(BindingError) as failure:
            self.profiles.answer(dict(id=body['id'], nonce=nonce, nativeId='first-chat'))
        self.assertEqual(failure.exception.code, 'probe_changed')
        late = dict(body, state='passed', capabilities=dict(callback=dict(state='verified')))
        self.profiles._save_probe(body['id'], late)
        saved = json.loads(self.profiles._read('connection_probes', body['id'], 'id')['body'])
        self.assertEqual(saved['state'], 'cancelled')
        self.assertEqual(saved['capabilities'], {})

    def test_probe_passes_project_variables_and_stops_before_send_after_binding_change(self):
        identifier = self.connection['binding']
        binding = self.project_binding()
        control = dict(protocol='http-json', endpoint='https://example.test')
        profile = dict(schemaVersion=1, control=control, capabilities=dict(
            createChat=dict(path='/create', projectRouting=True, arguments={
                'prompt': '$prompt', 'requestId': '$requestId', 'workspace': '$workspace',
                'projectScope': '$projectScope', 'nativeProject': '$nativeProject'}),
            sendMessage=dict(path='/send', arguments={'nativeId': '$nativeId', 'requestId': '$requestId',
                'workspace': '$workspace', 'projectScope': '$projectScope', 'nativeProject': '$nativeProject'})))
        self.profiles.describe(identifier, profile)
        self.profiles.configure(dict(action='configure-control', id=identifier,
            requestId='b' * 32, apiKey='', **control))
        body = dict(id='probe-project', state='running', startedAt=time.time(), deadline=time.time()+60,
                    profileRevision=self.profiles.public(identifier)['profileRevision'],
                    controlRevision=fingerprint(json.loads(self.profiles._read('connection_controls', identifier)['body'])),
                    capabilities={}, projectBinding=dict(bindingId=binding['id'], revision=binding['revision'],
                                                         project=binding['project'], scope=binding['scope']))
        seen=[]
        def action(spec, variables):
            seen.append((spec, variables))
            if len(seen)==1:
                with self.registry.connect() as c:
                    c.execute('UPDATE agent_project_bindings SET revision=revision+1 WHERE id=?', (binding['id'],))
                    c.commit()
                return dict(id='created-chat', visibility=dict(nativeId='created-chat', projectId='native-project-id-different-from-hub',
                    workspace=binding['scope']['root'], method='codex_app.list_threads', state='verified',
                    verifiedAt='2026-10-19T12:00:00Z', guiOpened=False))
            return dict(id='unexpected-send')
        with patch('connection_capabilities.HttpControl.action', side_effect=action):
            self.profiles._probe(identifier, profile, json.loads(self.profiles._read('connection_controls', identifier)['body']),
                                 body, 'nonce', 'http://127.0.0.1:8769', body['projectBinding'])
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][1]['$requestId'], 'probe-project')
        self.assertEqual(seen[0][1]['$workspace'], binding['scope']['root'])
        self.assertEqual(seen[0][1]['$projectScope'], binding['scope'])
        self.assertIsNone(seen[0][1]['$nativeProject'])
        self.assertEqual(body['nativeVisibility']['provenance'], 'control-adapter')
        self.assertEqual(body['nativeVisibility']['project'], binding['project'])
        self.assertFalse(body['nativeVisibility']['guiOpened'])
        self.assertEqual(body['nativeVisibility']['method'], 'codex_app.list_threads')

    def test_declared_control_without_saved_configuration_is_not_configured(self):
        identifier = self.connection['binding']
        self.profiles.describe(identifier, dict(schemaVersion=1,
            control=dict(protocol='http-json', endpoint='https://example.test'),
            capabilities=dict(createChat=dict(path='/chats'))))
        value = self.profiles.public(identifier)
        self.assertEqual(value['controlStatus']['state'], 'not_configured')
        self.assertFalse(value['controlStatus']['canTest'])
        self.assertEqual(value['features']['createChat']['state'], 'not_configured')

    def test_saved_endpoint_different_from_declaration_is_configuration_mismatch(self):
        identifier = self.connection['binding']
        self.profiles.describe(identifier, dict(schemaVersion=1,
            control=dict(protocol='http-json', endpoint='https://declared.example'),
            capabilities=dict(createChat=dict(path='/chats'))))
        self.profiles.configure(dict(action='configure-control', id=identifier,
            requestId='2' * 32, apiKey='', protocol='http-json', endpoint='https://saved.example'))
        value = self.profiles.public(identifier)
        self.assertEqual(value['controlStatus']['state'], 'configuration_mismatch')
        self.assertFalse(value['controlStatus']['canTest'])
        self.assertEqual(value['features']['createChat']['state'], 'configuration_mismatch')

    def test_matching_saved_endpoint_without_create_action_is_action_missing(self):
        identifier = self.connection['binding']
        control = dict(protocol='http-json', endpoint='https://example.test')
        self.profiles.describe(identifier, dict(schemaVersion=1, control=control,
            capabilities=dict(sendMessage=dict(path='/send'))))
        self.profiles.configure(dict(action='configure-control', id=identifier,
            requestId='3' * 32, apiKey='', **control))
        value = self.profiles.public(identifier)
        self.assertEqual(value['controlStatus']['state'], 'action_missing')
        self.assertFalse(value['controlStatus']['canTest'])
        self.assertEqual(value['features']['createChat']['state'], 'action_missing')

    def test_matching_configured_create_path_is_ready_before_probe(self):
        identifier = self.connection['binding']
        control = dict(protocol='http-json', endpoint='https://example.test')
        self.profiles.describe(identifier, dict(schemaVersion=1, control=control,
            capabilities=dict(createChat=dict(path='/chats'))))
        self.profiles.configure(dict(action='configure-control', id=identifier,
            requestId='4' * 32, apiKey='', **control))
        value = self.profiles.public(identifier)
        self.assertEqual(value['controlStatus']['state'], 'ready')
        self.assertTrue(value['controlStatus']['canTest'])
        self.assertEqual(value['features']['createChat']['state'], 'ready')

    def test_changed_profile_or_control_marks_old_probe_evidence_stale(self):
        identifier = self.connection['binding']
        control = dict(protocol='http-json', endpoint='https://example.test')
        self.profiles.describe(identifier, dict(schemaVersion=1, control=control,
            capabilities=dict(createChat=dict(path='/chats'))))
        self.profiles.configure(dict(action='configure-control', id=identifier,
            requestId='5' * 32, apiKey='', **control))
        current = self.profiles.public(identifier)
        config_revision = fingerprint(json.loads(self.profiles._read('connection_controls', identifier)['body']))
        body = dict(id='stale-fixture', state='passed', profileRevision=current['profileRevision'],
                    controlRevision=config_revision, capabilities=dict(createChat=dict(state='verified')))
        self.profiles.setup()
        with self.registry.connect() as c:
            c.execute('INSERT INTO connection_probes VALUES(?,?,?,?,?,?,?)',
                      ('stale-fixture', identifier, current['profileRevision'], json.dumps(body),
                       hashlib.sha256(b'stale-nonce').hexdigest(), time.time() + 60, time.time()))
        self.profiles.describe(identifier, dict(schemaVersion=1, control=control,
            capabilities=dict(createChat=dict(path='/changed'))))
        self.assertEqual(self.profiles.public(identifier)['features']['createChat']['state'], 'stale')

        with patch('secret_vault.save'):
            self.profiles.configure(dict(action='configure-control', id=identifier,
                requestId='6' * 32, apiKey='changed-key', **control))
        self.assertEqual(self.profiles.public(identifier)['features']['createChat']['state'], 'stale')

    def test_revoked_binding_cannot_publish_verified_feature_evidence(self):
        identifier = self.connection['binding']
        control = dict(protocol='http-json', endpoint='https://example.test')
        self.profiles.describe(identifier, dict(schemaVersion=1, control=control,
            capabilities=dict(createChat=dict(path='/chats'))))
        self.profiles.configure(dict(action='configure-control', id=identifier,
            requestId='7' * 32, apiKey='', **control))
        value = self.profiles.public(identifier)
        self.profiles.setup()
        body = dict(id='revoked-fixture', state='passed', profileRevision=value['profileRevision'],
                    controlRevision=fingerprint(json.loads(self.profiles._read('connection_controls', identifier)['body'])),
                    capabilities=dict(createChat=dict(state='verified')))
        with self.registry.connect() as c:
            c.execute('INSERT INTO connection_probes VALUES(?,?,?,?,?,?,?)',
                      ('revoked-fixture', identifier, value['profileRevision'], json.dumps(body),
                       hashlib.sha256(b'revoked-nonce').hexdigest(), time.time() + 60, time.time()))
        revoked = self.profiles.public(identifier, binding=dict(revoked=True))
        self.assertEqual(revoked['controlStatus']['state'], 'revoked')
        self.assertEqual(revoked['features']['createChat']['state'], 'revoked')

    def test_open_chat_source_is_independent_of_control_configuration(self):
        identifier = self.connection['binding']
        self.profiles.describe(identifier, dict(schemaVersion=1,
            nativeChat=dict(client='example-client', nativeId='native-chat',
                            openUri='https://example.test/chats/native-chat'),
            capabilities=dict(openChat=dict(uriTemplate='https://example.test/chats/{nativeId}'))))
        value = self.profiles.public(identifier)
        self.assertEqual(value['features']['openChat']['state'], 'source_available')

    def test_timeout_is_inconclusive_and_reply_requires_the_api_returned_identity(self):
        identifier = self.connection['binding']
        self.profiles.describe(identifier, {'schemaVersion': 1})
        revision = self.profiles.public(identifier)['profileRevision']
        body = dict(id='probe', state='awaiting_reply', startedAt=time.time(), deadline=time.time()+60,
                    profileRevision=revision, nativeId='created-chat', capabilities={})
        with self.registry.connect() as c:
            c.execute('INSERT INTO connection_probes VALUES(?,?,?,?,?,?,?)',
                      ('probe', identifier, revision, json.dumps(body), hashlib.sha256(b'nonce').hexdigest(), body['deadline'], time.time()))
        with self.assertRaises(BindingError):
            self.profiles.answer(dict(id='probe', nonce='nonce', nativeId='different-chat'))
        result = self.profiles.answer(dict(id='probe', nonce='nonce', nativeId='created-chat'))
        self.assertTrue(result['accepted'])
        self.assertEqual(self.profiles.public(identifier)['tests'][0]['state'], 'passed')
        self.assertEqual(self.profiles.answer(dict(id='probe', nonce='nonce', nativeId='created-chat')), result)
        with self.registry.connect() as c:
            body.update(state='awaiting_reply')
            c.execute('UPDATE connection_probes SET body=?,deadline=0 WHERE id=?', (json.dumps(body), 'probe'))
        self.assertEqual(self.profiles.public(identifier)['tests'][0]['state'], 'timed_out')
        with self.assertRaises(BindingError):
            self.profiles.answer(dict(id='probe', nonce='nonce', nativeId='created-chat'))

    def test_explicit_chat_links_task_and_stage_without_inventing_native_identity(self):
        project = self.registry.create('Example project')['id']
        native = dict(client='example-client', nativeId='real-native-chat', openUri='https://example.invalid/chats/one')
        task = self.invoke('hub_task', project=project, nativeChat=native, title='Inspect', scope=['Example'], acceptance=['Reviewed'])['task']
        self.invoke('hub_plan', project=project, task=task, stage='inspect', title='Inspect', nativeChat=native)
        links = linked(self.registry, project)
        self.assertEqual({link['stage'] for link in links}, {None, 'inspect'})
        with patch('codex_session_catalog.CATALOG.read_project', return_value={'available': True, 'sessions': [], 'registered': []}), patch('project_portal.SESSION_TITLES.get', return_value={}):
            history = chat_history(self.registry.store(project), task=task)
        self.assertEqual(len(history['sessions']), 1)
        self.assertEqual(history['sessions'][0]['nativeChat']['nativeId'], 'real-native-chat')
        self.assertEqual(history['sessions'][0]['stageLinks'][0]['stage'], 'inspect')
        self.assertNotIn('codex://', json.dumps(history))

    def test_chat_context_is_saved_without_task_and_reused_by_later_work(self):
        project = self.registry.create('Example project')['id']
        native = dict(client='example-client', nativeId='conversation-one', title='A named conversation',
                      openUri='https://example.test/chat/one')
        first = self.invoke('hub_context', project=project, nativeChat=native)
        self.assertIn('resourceId', first['nativeChat'])
        self.assertIsNone(linked(self.registry, project)[0]['task'])
        # Refreshing partial metadata must retain the known name/address.
        self.invoke('hub_context', project=project, nativeChat=dict(client='example-client', nativeId='conversation-one'))
        self.assertEqual(len(linked(self.registry, project)), 1)
        self.assertEqual(linked(self.registry, project)[0]['resource']['title'], native['title'])
        task = self.invoke('hub_task', project=project, title='Inspect', scope=['Example'], acceptance=['Reviewed'])['task']
        self.invoke('hub_plan', project=project, task=task, stage='inspect', title='Inspect')
        self.invoke('hub_begin', project=project, task=task, stage='inspect', title='Inspect', resources=['resource:example'])
        with patch('codex_session_catalog.CATALOG.read_project', return_value={'available': True, 'sessions': [], 'registered': []}), patch('project_portal.SESSION_TITLES.get', return_value={}):
            history = chat_history(self.registry.store(project))
        self.assertEqual(history['total'], 1)
        row = history['sessions'][0]
        self.assertEqual(row['title'], native['title'])
        self.assertEqual(row['nativeChat']['openUri'], native['openUri'])
        self.assertEqual([t['id'] for t in row['taskLinks']], [task])
        self.assertEqual([s['stage'] for s in row['stageLinks']], ['inspect'])

    def test_startup_acknowledges_missing_chat_metadata_and_saved_identity(self):
        project = self.registry.create('Example project')['id']
        missing = self.invoke('hub_context', project=project)['chatContext']
        self.assertEqual(missing['status'], 'unreported')
        self.assertFalse(missing['titleAvailable'])
        self.assertFalse(missing['openingAvailable'])
        self.assertIn('never invent', missing['action'])
        native = dict(client='example-client', nativeId='one', title='Known title', openUri='https://example.test/chat/one')
        self.invoke('hub_context', project=project, nativeChat=native)
        restored = self.invoke('hub_context', project=project)
        self.assertEqual(restored['chatContext'], dict(status='reported', titleAvailable=True, openingAvailable=True))
        self.assertEqual(restored['nativeChat']['title'], native['title'])

    def test_catalog_chat_and_new_connection_actors_join_without_losing_task_history(self):
        project = self.registry.create('Example project')['id']
        native = dict(client='codex', nativeId=CHAT, title='Reported title')
        tasks = []
        for session in ('first-conversation', 'second-conversation'):
            result = call(self.registry, self.connection['token'], 'hub_task', dict(session=session,
                project=project, nativeChat=native, title='Task ' + session, scope=['Example'], acceptance=['Reviewed']))
            tasks.append(result['task'])
        discovered = dict(id=CHAT, name='Current catalog title', cwd='.', updated_at=1, archived=False,
                          kind='agent', parentSession=None)
        with patch('codex_session_catalog.CATALOG.read_project', return_value={'available': True, 'sessions': [discovered], 'registered': []}), patch('project_portal.SESSION_TITLES.get', return_value={}):
            history = chat_history(self.registry.store(project))
            filtered = chat_history(self.registry.store(project), task=tasks[0])
        self.assertEqual(history['total'], 1)
        self.assertEqual(len(history['sessions']), 1)
        row = history['sessions'][0]
        self.assertEqual(row['id'], CHAT)
        self.assertEqual(row['title'], 'Current catalog title')
        self.assertEqual({t['id'] for t in row['taskLinks']}, set(tasks))
        self.assertEqual(len(row['hubActors']), 2)
        self.assertEqual(row['nativeChat']['openUri'], 'codex://threads/' + CHAT)
        self.assertEqual(filtered['total'], 1)
        # Projection does not rewrite existing creators or journal/work identity.
        self.assertNotEqual(self.registry.store(project).task_context(tasks[0])['tasks'][0]['createdBy']['session'], CHAT)

    def test_equal_native_ids_from_different_clients_and_instances_stay_separate(self):
        project = self.registry.create('Example project')['id']
        for session, client, instance, host in [('one', 'example-client', 'one', 'host-a'),
                ('two', 'other-client', 'one', 'host-a'), ('three', 'example-client', 'two', 'host-a'),
                ('four', 'example-client', 'one', 'host-b'), ('five', 'codex', None, None),
                ('six', 'codex-desktop', None, None)]:
            call(self.registry, self.connection['token'], 'hub_context', dict(session=session, project=project,
                nativeChat=dict(client=client, clientInstance=instance, host=host, nativeId='same-id', title=session)))
        with patch('codex_session_catalog.CATALOG.read_project', return_value={'available': True, 'sessions': [], 'registered': []}), patch('project_portal.SESSION_TITLES.get', return_value={}):
            history = chat_history(self.registry.store(project))
        self.assertEqual(history['total'], 6)
        self.assertEqual({row['title'] for row in history['sessions']}, {'one', 'two', 'three', 'four', 'five', 'six'})
        self.assertTrue(all('openUri' not in row['nativeChat'] for row in history['sessions']))

    def test_ambiguous_actor_does_not_assign_unrelated_work_to_both_chats(self):
        project = self.registry.create('Example project')['id']
        for native_id in ('one', 'two'):
            self.invoke('hub_context', project=project, nativeChat=dict(client='example-client', nativeId=native_id))
        task = self.invoke('hub_task', project=project, title='Unattributed', scope=['Example'], acceptance=['Reviewed'])['task']
        self.assertNotIn(task, {row['task'] for row in linked(self.registry, project)})

    def test_report_uses_owned_work_task_and_optional_native_chat(self):
        project = self.registry.create('Example project')['id']
        task = self.invoke('hub_task', project=project, title='Inspect', scope=['Example'], acceptance=['Reviewed'])['task']
        self.invoke('hub_plan', project=project, task=task, stage='inspect', title='Inspect')
        work = self.invoke('hub_begin', project=project, task=task, stage='inspect', title='Inspect', resources=['resource:example'])
        result = self.invoke('hub_report', project=project, work=work['work'], revision=work['revision'], result='Reviewed', status='done',
                             nativeChat=dict(client='codex', nativeId=CHAT))
        self.assertEqual(result['nativeChat']['nativeId'], CHAT)
        self.assertEqual(linked(self.registry, project)[0]['stage'], 'inspect')

    def test_report_keeps_primary_stage_when_work_has_secondary_links(self):
        project = self.registry.create('Example project')['id']
        task = self.invoke('hub_task', project=project, title='Inspect', scope=['Example'], acceptance=['Reviewed'])['task']
        for stage in ('z-primary', 'a-secondary'):
            self.invoke('hub_plan', project=project, task=task, stage=stage, title=stage)
        work = self.invoke('hub_begin', project=project, task=task, stage='z-primary',
                           title='Inspect', resources=['resource:example'])
        # A legacy/imported work can gain another link without replacing its
        # recorded primary stage. Ordering a UNION must not choose that link.
        with self.registry.coordination_connect() as connection:
            connection.execute('INSERT INTO work_stage_links VALUES(?,?)', (work['work'], 'a-secondary'))
        self.invoke('hub_report', project=project, work=work['work'], revision=work['revision'], result='Reviewed',
                    status='done', nativeChat=dict(client='codex', nativeId=CHAT))
        self.assertEqual(linked(self.registry, project)[0]['stage'], 'z-primary')

    def test_real_http_probe_correlates_created_chat_and_reply_with_separate_key(self):
        seen, answered = [], threading.Event()
        profiles = self.profiles
        class Peer(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                value = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                seen.append((self.path, value, self.headers.get('Authorization')))
                reply = {'id': 'returned-chat', 'url': 'http://127.0.0.1:'+str(self.server.server_port)+'/chats/returned-chat'}
                if self.path == '/send':
                    profiles.answer(dict(id=value['probeId'], nonce=value['nonce'], nativeId=value['nativeId']))
                    answered.set()
                    reply = {'accepted': True}
                data = json.dumps(reply).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
        peer = ThreadingHTTPServer(('127.0.0.1', 0), Peer)
        thread = threading.Thread(target=peer.serve_forever, daemon=True); thread.start()
        self.addCleanup(peer.server_close); self.addCleanup(peer.shutdown)
        control = dict(protocol='http-json', endpoint='http://127.0.0.1:'+str(peer.server_port))
        self.profiles.describe(self.connection['binding'], dict(schemaVersion=1, control=control, capabilities={
            'createChat': {'path': '/create', 'arguments': {'prompt': '$prompt', 'callback': '$callback', 'probeId': '$probeId', 'nonce': '$nonce'}},
            'sendMessage': {'path': '/send', 'arguments': {'nativeId': '$nativeId', 'prompt': '$prompt', 'probeId': '$probeId', 'nonce': '$nonce'}}}))
        with patch('secret_vault.save'), patch('secret_vault.get', return_value='SeparateControlKey'):
            self.profiles.configure(dict(action='configure-control', id=self.connection['binding'], apiKey='SeparateControlKey', requestId='e'*32, **control))
            self.assertEqual(seen, [])
            self.profiles.test(self.connection['binding'], 'http://127.0.0.1:8769')
            self.assertTrue(answered.wait(5))
            self.registry._connection_executor.shutdown(wait=True)
        value = self.profiles.public(self.connection['binding'])
        self.assertEqual(value['tests'][0]['state'], 'passed')
        self.assertEqual([item[0] for item in seen], ['/create', '/send'])
        self.assertEqual(seen[1][1]['nativeId'], 'returned-chat')
        self.assertTrue(all(item[2] == 'Bearer SeparateControlKey' for item in seen))
        self.assertNotIn('SeparateControlKey', json.dumps(value))
        self.assertFalse(value['capabilities']['openChat']['guiVerified'])
        self.assertEqual(value['tests'][0]['nativeChat']['nativeId'], 'returned-chat')
        confirmed=value['tests'][0]
        self.profiles._save_probe(confirmed['id'],dict(confirmed,state='failed',message='Late transport error'))
        self.assertEqual(self.profiles.public(self.connection['binding'])['tests'][0]['state'],'passed')

    def test_control_response_never_publishes_an_echoed_private_key(self):
        secret = 'PrivateControlFixtureKey'
        control = dict(protocol='http-json', endpoint='https://example.test')
        self.profiles.describe(self.connection['binding'], dict(schemaVersion=1,
            control=control, capabilities=dict(createChat=dict(path='/create'))))
        with patch('secret_vault.save'), patch('secret_vault.get', return_value=secret), \
             patch('connection_capabilities.HttpControl.action', return_value=dict(
                 id=secret, url='https://example.test/chats/' + secret)):
            self.profiles.configure(dict(id=self.connection['binding'], apiKey=secret,
                requestId='f' * 32, **control))
            self.profiles.test(self.connection['binding'], 'http://127.0.0.1:8769')
            self.registry._connection_executor.shutdown(wait=True)
        value = self.profiles.public(self.connection['binding'])
        self.assertEqual(value['tests'][0]['state'], 'failed')
        self.assertNotIn(secret, json.dumps(value))

    def test_nested_profile_credentials_and_command_fallbacks_are_rejected(self):
        for argument in ({'apiKey': 'Private'}, {'nested': {'token': 'Private'}}, {'cmd': 'execute something'}, {'prompt': 'Bearer Private'}):
            with self.subTest(argument=argument), self.assertRaises(BindingError):
                validate_profile({'schemaVersion': 1, 'capabilities': {'createChat': {'tool': 'create', 'arguments': argument}}})

    def test_action_timeout_is_bounded_and_passed_to_http_transport(self):
        for timeout in (0, -1, 61, True, float('inf'), '30'):
            with self.subTest(timeout=timeout), self.assertRaises(BindingError):
                validate_profile({'schemaVersion': 1, 'capabilities': {
                    'createChat': {'path': '/create', 'timeoutSeconds': timeout}}})
        profile = validate_profile({'schemaVersion': 1, 'capabilities': {
            'createChat': {'path': '/create', 'timeoutSeconds': 30},
            'sendMessage': {'path': '/send', 'timeoutSeconds': 20}}})
        self.assertEqual(profile['capabilities']['createChat']['timeoutSeconds'], 30)
        control = HttpControl(dict(protocol='http-json', endpoint='https://example.test'), self.connection['token'])
        with patch('connection_capabilities.json_request', return_value=({}, {})) as request:
            control.action(profile['capabilities']['createChat'], {})
            self.assertEqual(request.call_args.kwargs['timeout'], 30)
            control.action({'path': '/default'}, {})
            self.assertEqual(request.call_args.kwargs['timeout'], 12)

    def test_http_mcp_control_discovers_the_stateless_protocol_and_resource(self):
        server = PortalServer(('127.0.0.1', 0), registry=self.registry)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        control = HttpControl(dict(protocol='mcp-http', endpoint='http://127.0.0.1:'+str(server.server_port)+'/mcp'), self.connection['token'])
        tools = control.discover()
        self.assertEqual(control.version, '2026-07-28')
        self.assertIn('hub_connection', tools)
        self.assertIn('hub_task', tools)
        result = control.rpc('resources/read', dict(uri='project-hub://workflow'))
        self.assertIn('Contract version: 5', result['contents'][0]['text'])


if __name__ == '__main__':
    unittest.main()
