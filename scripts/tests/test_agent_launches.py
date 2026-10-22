"""Typed task-launch snapshots and continuation authorization contracts."""
import json
import shutil
import subprocess
from pathlib import Path
import tempfile
import time
import unittest
import uuid
import threading
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch

from agent_bindings import BindingError, Connections, fingerprint
from agent_launches import Launches
from agent_runtime import call
from project_bindings import ProjectBindings
from project_registry import ProjectRegistry
from project_portal import PortalServer


class AgentLaunchContractsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.registry = ProjectRegistry(Path(self.temporary.name) / 'hub', standalone=True)
        self.addCleanup(self.registry.close_connection_pool)
        self.connections = Connections(self.registry)
        invite = self.connections.invite(request_id=uuid.uuid4().hex)
        self.connection = self.connections.enroll(invite['token'], 'codex', 'bridge-client')
        self.workspace = Path(self.temporary.name) / 'workspace'
        self.workspace.mkdir()
        self.binding = ProjectBindings(self.registry).execute(self.connection['binding'], dict(
            action='resolve', scope=dict(kind='workspace', root=str(self.workspace.resolve()), nativeRef='native-project'),
            name='Launch project', requestId=uuid.uuid4().hex))['binding']
        self.launches = Launches(self.registry)
        selected = dict(project=self.binding['project'], bindingId=self.binding['id'],
                        bindingRevision=self.binding['revision'], projectScope=self.binding['scope'])
        self.launches.profiles.configure(dict(action='configure-integration', id=self.connection['binding'],
            protocol='http-json', endpoint='http://127.0.0.1:8769/bridge', apiKey='test-key', requestId='1' * 32,
            profile=dict(schemaVersion=1, control=dict(protocol='http-json', endpoint='http://127.0.0.1:8769/bridge'),
                capabilities=dict(createChat=dict(path='/create', projectRouting=True,
                    arguments=dict(prompt='$prompt', requestId='$requestId', workspace='$workspace', projectScope='$projectScope')),
                    sendMessage=dict(path='/send', projectRouting=True,
                    arguments=dict(prompt='$prompt', requestId='$requestId', nativeId='$nativeId', workspace='$workspace', projectScope='$projectScope')))),
            expectedProfileRevision=None))
        call(self.registry, self.connection['token'], 'hub_context', dict(session='task-owner', **selected))
        self.task = call(self.registry, self.connection['token'], 'hub_task', dict(
            session='task-owner', **selected, title='Launch task', scope=['Launch'], acceptance=['Result']))['task']

    def selected(self, binding=None):
        binding = binding or self.binding
        return dict(project=binding['project'], bindingId=binding['id'],
                    bindingRevision=binding['revision'], projectScope=binding['scope'])

    def seed_launch(self, *, task=None, status='completed', native_id='native-chat',
                    binding=None, request_id=None, result=None, connection=None):
        binding = binding or self.binding
        connection = connection or self.connection['binding']
        request_id = request_id or uuid.uuid4().hex
        task = task or self.task
        inputs = self.launches.task_input(binding['project'], task)
        config = json.loads(self.launches.profiles._read('connection_controls', connection)['body'])
        profile = self.launches.profiles.profile(connection)
        body = dict(requestId=request_id, status=status, nativeId=native_id,
                    ackSession='task-owner', acknowledgedAt=time.time(), finishedAt=time.time(),
                    profileRevision=self.launches.profiles._read('connection_profiles', connection)['revision'],
                    controlRevision=fingerprint(config),
                    routingRevision=fingerprint(dict(control=profile.get('control'), capabilities=profile.get('capabilities'))),
                    nativeRoutingVerified=True, envelope=dict(requestId=request_id, connection=connection,
                        project=binding['project'], bindingId=binding['id'], bindingRevision=binding['revision'],
                        projectScope=binding['scope'], operation='task-execute',
                        inputs=inputs,
                        resultDestination=dict(kind='task-report', project=binding['project'], task=task),
                        bookkeeping=dict(mode='tracked')), result=result or dict(summary='Done', evidence=['evidence']))
        self.launches.setup()
        with self.registry.connect() as db:
            db.execute('INSERT INTO agent_launches VALUES(?,?,?,?,?,?,?,?)',
                (request_id, connection, binding['project'], binding['id'], binding['revision'],
                 fingerprint(body['envelope']), json.dumps(body), time.time()))
        return body

    def test_task_state_projects_only_selected_task_and_safe_launch_fields(self):
        other = call(self.registry, self.connection['token'], 'hub_task', dict(
            session='task-owner', **self.selected(), title='Other task', scope=['Other'], acceptance=['Result']))['task']
        first = self.seed_launch()
        second = self.seed_launch(task=other, native_id='other-chat')
        snapshot = self.launches.task_state(self.binding['project'], self.task)
        self.assertEqual({item['requestId'] for item in snapshot['launches']}, {first['requestId']})
        self.assertTrue(snapshot['routes'])
        route = snapshot['routes'][0]
        self.assertEqual(route['connection'], self.connection['binding'])
        self.assertEqual(route['bindingId'], self.binding['id'])
        self.assertTrue(route['canContinue'])
        self.assertNotIn('envelope', snapshot['launches'][0])
        self.assertNotIn(self.connection['token'], json.dumps(snapshot))
        self.assertNotIn(second['requestId'], json.dumps(snapshot))

    def test_task_state_bounds_context_and_projects_native_visibility(self):
        launch = self.seed_launch(result=dict(summary='x' * 2000, evidence=['y' * 2000]), native_id='native-visible')
        launch['nativeVisibility'] = dict(nativeId='native-visible', projectId='native-project-id-different-from-hub',
            workspace=str(self.workspace), method='codex_app.list_threads', state='verified', provenance='control-adapter')
        with self.registry.connect() as connection:
            connection.execute('UPDATE agent_launches SET body=? WHERE id=?', (json.dumps(launch), launch['requestId']))
        snapshot = self.launches.task_state(self.binding['project'], self.task)
        item = snapshot['launches'][0]
        self.assertEqual(item['nativeVisibility']['provenance'], 'control-adapter')
        self.assertEqual(item['result']['summary'], 'x' * 2000)
        self.assertNotIn('inputs', json.dumps(snapshot))
        self.assertLess(len(json.dumps(snapshot).encode()), 12000)

    def test_task_and_stage_creation_chats_continue_without_a_prior_launch(self):
        creator = dict(client='codex', nativeId='11111111-1111-4111-8111-111111111111', title='Task source')
        stage_chat = dict(client='codex', nativeId='22222222-2222-4222-8222-222222222222', title='Stage source')
        selected = dict(session='task-owner', **self.selected())
        task = call(self.registry, self.connection['token'], 'hub_task', dict(selected,
            nativeChat=creator, title='Created in chat', scope=['Inspect'], acceptance=['Done']))['task']
        call(self.registry, self.connection['token'], 'hub_plan', dict(selected, task=task,
            stage='inspect', title='Inspect', nativeChat=stage_chat))
        snapshot = self.launches.task_state(self.binding['project'], task)
        self.assertEqual(snapshot['launches'], [])
        chats = {c['nativeId']: c for c in snapshot['chats']}
        self.assertEqual(chats[creator['nativeId']]['scope'], 'task')
        self.assertEqual(chats[creator['nativeId']]['title'], 'Task source')
        self.assertEqual(chats[stage_chat['nativeId']]['stage'], 'inspect')
        self.assertEqual(chats[stage_chat['nativeId']]['scope'], 'stage')
        args = dict(requestId='a'*32, bindingId=self.binding['id'], operation='task-execute',
                    task=task, stage='inspect', nativeId=creator['nativeId'])
        def send(spec, variables):
            stored = self.launches.read(self.connection['binding'], args['requestId'])['body']
            import hashlib
            self.assertEqual(stored['dispatchPromptSha256'], hashlib.sha256(variables['$prompt'].encode()).hexdigest())
            self.assertEqual(stored['continuationSource']['task'], task)
            return dict(id=creator['nativeId'])
        with patch('agent_launches.HttpControl.action', side_effect=send) as action:
            started = self.launches.start(self.connection['binding'], args)
            replay = self.launches.start(self.connection['binding'], args)
        action.assert_called_once()
        self.assertEqual(started, replay)
        self.assertEqual(started['status'], 'awaiting_ack')
        ack = self.launches.execute(self.connection['binding'], 'task-owner', dict(action='ack',
            requestId=args['requestId'], projectScope=self.binding['scope'], nativeId=creator['nativeId']))
        self.assertEqual(ack['status'], 'accepted')
        self.assertNotIn(creator['nativeId'], [c['nativeId'] for c in self.launches.task_state(self.binding['project'], task)['chats']])
        with self.assertRaises(BindingError) as failure:
            self.launches.start(self.connection['binding'], dict(args, requestId='b'*32))
        self.assertEqual(failure.exception.code, 'native_chat_busy')
        other = call(self.registry, self.connection['token'], 'hub_task', dict(selected,
            nativeChat=creator, title='Another task in the same chat', scope=['Inspect'], acceptance=['Done']))['task']
        with self.assertRaises(BindingError) as failure:
            self.launches.start(self.connection['binding'], dict(args, requestId='c'*32, task=other, stage=None))
        self.assertEqual(failure.exception.code, 'native_chat_busy')

    def test_related_chat_scope_client_and_instance_are_not_borrowed(self):
        from native_chats import register
        call(self.registry, self.connection['token'], 'hub_plan', dict(session='task-owner',
            **self.selected(), task=self.task, stage='one', title='One'))
        call(self.registry, self.connection['token'], 'hub_plan', dict(session='task-owner',
            **self.selected(), task=self.task, stage='two', title='Two'))
        native = dict(client='codex', nativeId='11111111-1111-4111-8111-111111111111', title='Stage one')
        register(self.registry, self.binding['project'], 'stage-author', native, task=self.task, stage='one')
        self.assertEqual(self.launches.continuation(self.connection['binding'], self.binding,
            self.task, native['nativeId'], 'one')['kind'], 'related')
        with self.assertRaises(BindingError):
            self.launches.continuation(self.connection['binding'], self.binding, self.task, native['nativeId'], 'two')
        for i, resource in enumerate([dict(native, client='other-app', nativeId='other-client'),
                                     dict(native, clientInstance='other-instance', nativeId='other-instance'),
                                     dict(native, host='other-machine', nativeId='other-host')]):
            register(self.registry, self.binding['project'], 'unrelated-'+str(i), resource, task=self.task)
        profile = self.launches.profiles.profile(self.connection['binding'])
        profile.update(clientInstance='current-instance', host='local')
        self.launches.profiles.describe(self.connection['binding'], profile)
        ids = {c['nativeId'] for c in self.launches.task_state(self.binding['project'], self.task)['chats']}
        self.assertEqual(ids, {native['nativeId']})
        with self.assertRaises(BindingError):
            self.launches.continuation(self.connection['binding'], self.binding, self.task, 'not-linked', 'one')

    def test_legacy_creator_requires_native_catalog_evidence(self):
        native_id = '33333333-3333-4333-8333-333333333333'
        store = self.registry.store(self.binding['project'])
        context = store.task_context(self.task)
        context['tasks'][0]['createdBy'] = dict(session=native_id, project=self.binding['project'])
        with patch.object(self.registry, 'store', return_value=store), patch.object(store, 'task_context', return_value=context), \
             patch('codex_session_catalog.CATALOG.read_project', return_value=dict(sessions=[])):
            self.assertEqual(self.launches.task_state(self.binding['project'], self.task)['chats'], [])
        with patch.object(self.registry, 'store', return_value=store), patch.object(store, 'task_context', return_value=context), \
             patch('codex_session_catalog.CATALOG.read_project', return_value=dict(sessions=[
                 dict(id=native_id, name='Original task chat')])):
            chats = self.launches.task_state(self.binding['project'], self.task)['chats']
        self.assertEqual(chats[0]['nativeId'], native_id)
        self.assertEqual(chats[0]['title'], 'Original task chat')
        self.assertEqual(chats[0]['scope'], 'task')

    def test_legacy_stage_creation_uses_recorded_history_without_a_task_creator_chat(self):
        call(self.registry, self.connection['token'], 'hub_plan', dict(session='task-owner',
            **self.selected(), task=self.task, stage='legacy-stage', title='Legacy stage'))
        native_id = '44444444-4444-4444-8444-444444444444'
        event = dict(taskId=self.task, stageId='legacy-stage', session=native_id, kind='stage.created')
        with patch.object(self.registry.read_models, 'history', return_value=dict(events=[event], next=None)), \
             patch('codex_session_catalog.CATALOG.read_project', return_value=dict(sessions=[dict(id=native_id, name='Stage creator')])):
            chats = self.launches.task_state(self.binding['project'], self.task)['chats']
        self.assertEqual(chats[0]['nativeId'], native_id)
        self.assertEqual(chats[0]['scope'], 'stage')
        self.assertEqual(chats[0]['stage'], 'legacy-stage')

    @unittest.skipUnless(shutil.which('node'), 'Node is required for the source-chat HTTP adapter contract')
    def test_source_chat_dispatch_crosses_real_hub_and_adapter_http_boundaries(self):
        from connection_capabilities import Profiles
        server = PortalServer(('127.0.0.1', 0), registry=self.registry)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = 'http://127.0.0.1:' + str(server.server_port)
        bridge = Path(__file__).resolve().parents[1] / 'codex_desktop_bridge.mjs'
        script = '''
import {once} from 'node:events';
const [modulePath,base,connection,root,journal,key] = process.argv.slice(1);
const {DesktopControl,Journal,HubBindings,serve} = await import(modulePath);
const id='11111111-1111-4111-8111-111111111111';let sends=0;
const host={call:async(name,args)=>{
  if(name==='list_projects')return {projects:[{projectId:'native-project',projectKind:'local',hostId:'local',path:root}]};
  if(name==='list_threads')return {threads:[{id,hostId:'local',projectId:'native-project',cwd:root}]};
  if(name==='send_message_to_thread'&&args.threadId===id&&++sends===1)return {status:'queued'};
  throw Error('Unexpected native action');
}};
const server=serve(new DesktopControl(host,new Journal(journal,'test-instance'),new HubBindings(base,connection)),key);
await once(server,'listening');console.log(JSON.stringify({port:server.address().port}));
'''
        key = 'test-private-adapter-key-' * 3
        process = subprocess.Popen([shutil.which('node'), '--input-type=module', '-e', script,
            bridge.as_uri(), base, self.connection['binding'], str(self.workspace),
            str(Path(self.temporary.name) / 'bridge-journal.json'), key],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        def stop():
            process.terminate()
            process.communicate(timeout=5)
        self.addCleanup(stop)
        endpoint = 'http://127.0.0.1:' + str(json.loads(process.stdout.readline())['port'])
        profile = self.launches.profiles.profile(self.connection['binding'])
        profile['control']['endpoint'] = endpoint
        profile['capabilities']['sendMessage']['path'] = '/v1/chats/send'
        profile['capabilities']['sendMessage']['arguments'].pop('projectScope', None)
        # Hub scope is verified through its saved binding; no duplicate folder grant.
        native_scope = dict(self.binding['scope'])
        native_scope.pop('nativeRef', None)
        with self.registry.connect() as db:
            db.execute('UPDATE agent_project_bindings SET scope=? WHERE id=?',
                       (json.dumps(native_scope), self.binding['id']))
        self.binding['scope'] = native_scope
        Profiles(self.registry).configure(dict(action='configure-integration', id=self.connection['binding'],
            protocol='http-json', endpoint=endpoint, apiKey=key, requestId='d'*32, profile=profile,
            expectedProfileRevision=self.launches.profiles._read('connection_profiles', self.connection['binding'])['revision']))
        native = dict(client='codex', nativeId='11111111-1111-4111-8111-111111111111', title='Source chat')
        selected = dict(session='task-owner', **self.selected())
        task = call(self.registry, self.connection['token'], 'hub_task', dict(selected, nativeChat=native,
            title='Created before launch', scope=['Inspect'], acceptance=['Done']))['task']
        call(self.registry, self.connection['token'], 'hub_plan', dict(selected, task=task, stage='inspect', title='Inspect'))
        args = dict(requestId='e'*32, bindingId=self.binding['id'], operation='task-execute',
                    task=task, stage='inspect', nativeId=native['nativeId'])
        result = self.launches.start(self.connection['binding'], args)
        self.assertEqual(result['status'], 'awaiting_ack', result)
        self.assertEqual(result['nativeVisibility']['state'], 'verified')
        self.assertEqual(self.launches.start(self.connection['binding'], args), result)

    def test_actual_start_ack_report_complete_and_continuation(self):
        call(self.registry, self.connection['token'], 'hub_plan', dict(session='task-owner', **self.selected(),
            task=self.task, stage='step', title='Inspect'))
        with patch('agent_launches.HttpControl.action', return_value={'id': 'native-live'}):
            started = self.launches.start(self.connection['binding'], dict(requestId='2' * 32,
                bindingId=self.binding['id'], operation='task-execute', task=self.task, stage='step'))
        self.assertEqual(started['status'], 'awaiting_ack')
        ack = self.launches.execute(self.connection['binding'], 'task-owner', dict(action='ack', requestId='2' * 32,
            projectScope=self.binding['scope'], nativeId='native-live'))
        self.assertEqual(ack['status'], 'accepted')
        work = call(self.registry, self.connection['token'], 'hub_begin', dict(session='task-owner', **self.selected(),
            task=self.task, stage='step', title='Inspect', resources=['resource:test']))
        report = call(self.registry, self.connection['token'], 'hub_report', dict(session='task-owner', **self.selected(),
            work=work['work'], revision=work['revision'], result='Verified', status='done'))
        completed = self.launches.execute(self.connection['binding'], 'task-owner', dict(action='complete', requestId='2' * 32,
            projectScope=self.binding['scope'], nativeId='native-live', work=work['work'], revision=report['revision']))
        self.assertEqual(completed['status'], 'completed')
        call(self.registry, self.connection['token'], 'hub_plan', dict(session='task-owner', **self.selected(),
            task=self.task, stage='other', title='Other stage'))
        with self.assertRaises(BindingError):
            self.launches.start(self.connection['binding'], dict(requestId='8' * 32,
                bindingId=self.binding['id'], operation='task-execute', task=self.task,
                stage='other', nativeId='native-live'))
        with patch('agent_launches.HttpControl.action', return_value={'id': 'native-live'}):
            continuation = self.launches.start(self.connection['binding'], dict(requestId='3' * 32,
                bindingId=self.binding['id'], operation='task-execute', task=self.task, stage='step', nativeId='native-live'))
        self.assertEqual(continuation['status'], 'awaiting_ack')
        profile = self.launches.profiles.profile(self.connection['binding'])
        profile['capabilities']['sendMessage']['path'] = '/changed-after-launch'
        self.launches.profiles.describe(self.connection['binding'], profile)
        historical = next(item for item in self.launches.task_state(self.binding['project'], self.task)['launches']
                          if item['requestId'] == '2' * 32)
        self.assertFalse(historical['canContinue'])

    def test_start_replay_busy_wrong_task_and_stale_configuration_are_blocked(self):
        args = dict(requestId='4' * 32, bindingId=self.binding['id'], operation='task-execute', task=self.task)
        with patch('agent_launches.HttpControl.action', return_value={'id': 'native-replay'}) as action:
            first = self.launches.start(self.connection['binding'], args)
            replay = self.launches.start(self.connection['binding'], args)
        self.assertEqual(replay, first)
        action.assert_called_once()
        with self.assertRaises(BindingError) as failure:
            self.launches.start(self.connection['binding'], dict(requestId='5' * 32, bindingId=self.binding['id'],
                operation='task-execute', task=self.task, nativeId='native-replay'))
        self.assertEqual(failure.exception.code, 'native_chat_busy')
        with self.assertRaises(BindingError):
            self.launches.start(self.connection['binding'], dict(requestId='6' * 32, bindingId=self.binding['id'],
                operation='task-execute', task='missing-task'))

    def test_ack_rejects_stale_task_input_snapshot(self):
        with patch('agent_launches.HttpControl.action', return_value={'id': 'native-stale'}):
            started = self.launches.start(self.connection['binding'], dict(requestId='9' * 32,
                bindingId=self.binding['id'], operation='task-execute', task=self.task))
        self.assertEqual(started['status'], 'awaiting_ack')
        started['inputHash'] = 'stale-input-hash'
        with self.registry.connect() as db:
            db.execute('UPDATE agent_launches SET body=? WHERE id=?', (json.dumps(started), '9' * 32))
        with self.assertRaises(BindingError) as failure:
            self.launches.execute(self.connection['binding'], 'task-owner', dict(action='ack', requestId='9' * 32,
                projectScope=self.binding['scope'], nativeId='native-stale'))
        self.assertEqual(failure.exception.code, 'launch_inputs_changed')

    def test_stage_change_before_ack_cancels_launch(self):
        call(self.registry, self.connection['token'], 'hub_plan', dict(session='task-owner', **self.selected(),
            task=self.task, stage='changed', title='Original'))
        with patch('agent_launches.HttpControl.action', return_value={'id': 'native-stage'}):
            started = self.launches.start(self.connection['binding'], dict(requestId='a' * 32,
                bindingId=self.binding['id'], operation='task-execute', task=self.task, stage='changed'))
        current = call(self.registry, self.connection['token'], 'hub_plan', dict(
            session='task-owner', **self.selected(), task=self.task))
        call(self.registry, self.connection['token'], 'hub_plan', dict(session='task-owner', **self.selected(),
            task=self.task, stage='changed', title='Modified', expected=current['revision']))
        with self.assertRaises(BindingError) as failure:
            self.launches.execute(self.connection['binding'], 'task-owner', dict(action='ack', requestId='a' * 32,
                projectScope=self.binding['scope'], nativeId='native-stage'))
        self.assertEqual(failure.exception.code, 'launch_inputs_changed')
        self.assertEqual(self.launches.read(self.connection['binding'], started['requestId'])['body']['status'], 'cancelled')

    def test_missing_task_or_stage_during_ack_is_cancelled(self):
        with patch('agent_launches.HttpControl.action', return_value={'id': 'native-missing'}):
            started = self.launches.start(self.connection['binding'], dict(requestId='b' * 32,
                bindingId=self.binding['id'], operation='task-execute', task=self.task))
        with patch.object(self.launches, 'task_input', side_effect=BindingError('task_missing', 'gone', 404)):
            with self.assertRaises(BindingError):
                self.launches.execute(self.connection['binding'], 'task-owner', dict(action='ack', requestId='b' * 32,
                    projectScope=self.binding['scope'], nativeId='native-missing'))
        self.assertEqual(self.launches.read(self.connection['binding'], started['requestId'])['body']['status'], 'cancelled')

    def test_two_bindings_route_independently_and_cross_project_attempts_do_not_dispatch(self):
        second_workspace = Path(self.temporary.name) / 'second-workspace'
        second_workspace.mkdir()
        second = ProjectBindings(self.registry).execute(self.connection['binding'], dict(action='resolve',
            scope=dict(kind='workspace', root=str(second_workspace.resolve()), nativeRef='native-second'),
            name='Second project', requestId='c' * 32))['binding']
        second_selected = self.selected(second)
        call(self.registry, self.connection['token'], 'hub_context', dict(session='task-owner', **second_selected))
        second_task = call(self.registry, self.connection['token'], 'hub_task', dict(session='task-owner',
            **second_selected, title='Second task', scope=['Second'], acceptance=['Result']))['task']
        calls = []
        with patch('agent_launches.HttpControl.action', side_effect=lambda spec, args: calls.append(args) or {'id': 'native-' + str(len(calls))}):
            first = self.launches.start(self.connection['binding'], dict(requestId='d' * 32,
                bindingId=self.binding['id'], operation='task-execute', task=self.task))
            second_start = self.launches.start(self.connection['binding'], dict(requestId='e' * 32,
                bindingId=second['id'], operation='task-execute', task=second_task))
            with self.assertRaises(BindingError):
                self.launches.start(self.connection['binding'], dict(requestId='f' * 32,
                    bindingId=self.binding['id'], operation='task-execute', task=second_task))
            with self.assertRaises(BindingError):
                self.launches.start(self.connection['binding'], dict(requestId='0' * 32,
                    bindingId=second['id'], operation='task-execute', task=second_task, nativeId=first['nativeId']))
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]['$projectScope']['root'], self.binding['scope']['root'])
        self.assertEqual(calls[1]['$projectScope']['root'], second['scope']['root'])
        self.assertNotEqual(first['envelope']['project'], second_start['envelope']['project'])

    def test_revoked_connection_blocks_ack_and_complete_and_changed_routing_blocks_result(self):
        with patch('agent_launches.HttpControl.action', return_value={'id': 'native-revoked'}):
            started = self.launches.start(self.connection['binding'], dict(requestId='1' * 32,
                bindingId=self.binding['id'], operation='task-execute', task=self.task))
        self.connections.revoke(self.connection['binding'])
        with self.assertRaises(BindingError):
            self.launches.execute(self.connection['binding'], 'task-owner', dict(action='ack', requestId='1' * 32,
                projectScope=self.binding['scope'], nativeId='native-revoked'))
        accepted = self.seed_launch(status='accepted', native_id='native-complete')
        with self.assertRaises(BindingError):
            self.launches.execute(self.connection['binding'], 'task-owner', dict(action='complete', requestId=accepted['requestId'],
                projectScope=self.binding['scope'], nativeId='native-complete', work='missing', revision='missing'))

    def test_changed_control_routing_blocks_late_result(self):
        accepted = self.seed_launch(status='accepted', native_id='native-routing')
        profile = self.launches.profiles.profile(self.connection['binding'])
        profile['capabilities']['sendMessage']['path'] = '/changed-late-result'
        self.launches.profiles.describe(self.connection['binding'], profile)
        with self.assertRaises(BindingError) as failure:
            self.launches.execute(self.connection['binding'], 'task-owner', dict(action='complete', requestId=accepted['requestId'],
                projectScope=self.binding['scope'], nativeId='native-routing', work='missing', revision='missing'))
        self.assertEqual(failure.exception.code, 'launch_configuration_changed')

    def test_continuation_requires_same_task_binding_and_completed_acknowledged_chat(self):
        completed = self.seed_launch(status='completed', native_id='native-chat')
        self.assertTrue(self.launches.task_state(self.binding['project'], self.task)['routes'][0]['canContinue'])
        wrong_task = call(self.registry, self.connection['token'], 'hub_task', dict(
            session='task-owner', **self.selected(), title='Wrong task', scope=['Wrong'], acceptance=['Result']))['task']
        self.seed_launch(task=wrong_task, status='completed', native_id='wrong-chat')
        self.assertFalse(any(item['canContinue'] and item.get('nativeId') == 'wrong-chat'
                             for item in self.launches.task_state(self.binding['project'], self.task)['launches']))
        active = self.seed_launch(status='awaiting_ack', native_id='active-chat')
        state = self.launches.task_state(self.binding['project'], self.task)
        self.assertFalse(any(item.get('nativeId') == active['nativeId'] and item['canContinue'] for item in state['launches']))
        self.assertEqual(completed['envelope']['bindingId'], self.binding['id'])

    def test_task_state_isolates_foreign_connection_and_binding(self):
        foreign = self.connections.enroll(
            self.connections.invite(request_id=uuid.uuid4().hex)['token'], 'other-client', 'other-client')['binding']
        body = self.seed_launch()
        with self.registry.connect() as connection:
            connection.execute('UPDATE agent_launches SET connection=? WHERE id=?', (foreign, body['requestId']))
        snapshot = self.launches.task_state(self.binding['project'], self.task)
        history = next(item for item in snapshot['launches'] if item['requestId'] == body['requestId'])
        self.assertFalse(history['canContinue'])

    def test_task_state_rejects_unknown_project_or_task(self):
        with self.assertRaises(BindingError):
            self.launches.task_state('missing-project', self.task)
        with self.assertRaises(BindingError):
            self.launches.task_state(self.binding['project'], 'missing-task')

    def test_task_launches_http_boundary_requires_explicit_valid_project_and_task(self):
        server = PortalServer(('127.0.0.1', 0), registry=self.registry)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = 'http://127.0.0.1:' + str(server.server_port) + '/api/task-launches'
        for asset in ('/task-launches.js','/task-launches.css'):
            with urlopen('http://127.0.0.1:' + str(server.server_port) + asset, timeout=5) as response:
                self.assertEqual(response.status,200)
                self.assertTrue(response.read())
        with urlopen(base + '?project=' + self.binding['project'] + '&task=' + self.task, timeout=5) as response:
            payload = json.loads(response.read())
        self.assertEqual(payload['project'], self.binding['project'])
        self.assertIsInstance(payload['chats'], list)
        for query in ('project=missing-project&task=' + self.task,
                      'project=' + self.binding['project'] + '&task=missing-task'):
            with self.assertRaises(HTTPError) as failure:
                urlopen(base + '?' + query, timeout=5)
            self.assertIn(failure.exception.code, (400, 404, 409))


if __name__ == '__main__':
    unittest.main()
