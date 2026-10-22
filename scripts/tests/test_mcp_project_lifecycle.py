"""MCP-only instruction snapshots, binding recovery and native handoff contracts."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

PAYLOAD=os.environ.get('HUB_MCP_VERIFY_PAYLOAD')
ROOT=Path(PAYLOAD).resolve()/'app' if PAYLOAD else Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from agent_bindings import BindingError, Connections
from agent_instructions import bundle, read, update, validate_bundle, connection_context
from agent_runtime import call
from agent_launches import Launches
from connection_capabilities import Profiles
from knowledge_store import KnowledgeStore
from native_onboarding import build_plan, apply_plan, OnboardingError
from native_project_rule import plan as project_rule, apply as apply_rule
from project_bindings import ProjectBindings
from project_registry import ProjectRegistry


class McpLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.registry=ProjectRegistry(self.root/'hub',standalone=True)
        self.addCleanup(self.registry.close_connection_pool)
        self.connections=Connections(self.registry)
        invite=self.connections.invite(request_id=uuid.uuid4().hex)
        self.connection=self.connections.enroll(invite['token'],'example-client','client-one')
        self.native=dict(self.connection,baseUrl='http://127.0.0.1:8769')
        self.bindings=ProjectBindings(self.registry)
        self.workspace=self.root/'repository'
        self.workspace.mkdir()
        self.scope=dict(kind='workspace',root=str(self.workspace.resolve()),nativeRef='native-project-one')

    def invoke(self, tool, session='conversation-one', **args):
        return call(self.registry,self.connection['token'],tool,dict(session=session,**args))

    def resolve(self, **args):
        return self.bindings.execute(self.connection['binding'],dict(action='resolve',scope=self.scope,requestId=uuid.uuid4().hex,**args))['binding']

    def selected(self,binding,scope=True):
        result=dict(project=binding['project'],workspace=binding['scope'].get('root'),bindingId=binding['id'],bindingRevision=binding['revision'])
        if scope: result['projectScope']=binding['scope']
        return result

    def native_plan(self,value=None,host='codex'):
        return build_plan(host,self.native,value or bundle(self.registry)['instructionBundle'],native_home=self.root/'.codex',instructions_home=self.root/'instructions')

    @unittest.skipUnless(PAYLOAD,'Embedded Python smoke check applies to a retained installer payload')
    def test_embedded_python_serves_versioned_mcp_instructions(self):
        code='''import json,tempfile,threading,uuid
from pathlib import Path
from agent_bindings import Connections
from agent_sdk import Client
from project_registry import ProjectRegistry
from project_portal import PortalServer
from native_onboarding import build_plan,apply_plan
with tempfile.TemporaryDirectory() as directory:
 root=Path(directory); registry=ProjectRegistry(root/'hub',standalone=True)
 server=PortalServer(('127.0.0.1',0),registry=registry)
 thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
 try:
  base='http://127.0.0.1:'+str(server.server_port); client=Client(base)
  invite=Connections(registry).invite(request_id=uuid.uuid4().hex)
  setup=client.connect(invite['token']); assert setup['contractVersion']==5
  enrolled=client.enroll(setup['invitation'],'fixture-client','packaged-probe')
  client=Client(base,enrolled['token'],session='packaged-conversation')
  snapshot=client.call('hub_instructions',{'action':'read'})
  native=dict(baseUrl=base,token=enrolled['token'],binding=enrolled['binding'],scope='global')
  plan=build_plan('codex',native,snapshot,native_home=root/'native',instructions_home=root/'instructions')
  saved=apply_plan(plan,expected_preview=plan.fingerprint)
  assert saved['instructionsPersisted'] and not saved['setupVerified']
  workspace=root/'repository'; workspace.mkdir()
  binding=client.call('hub_project_bindings',{'action':'resolve','scope':{'kind':'workspace','root':str(workspace)},'requestId':uuid.uuid4().hex})['binding']
  context=client.call('hub_context',{'project':binding['project'],'bindingId':binding['id'],'bindingRevision':binding['revision'],'projectScope':binding['scope'],'workspace':str(workspace)})
  assert context['projectBinding']['project']==binding['project']
  print('Embedded MCP installation and project routing verified')
 finally:
  server.shutdown(); server.server_close(); thread.join(); registry.close_connection_pool()
'''
        result=subprocess.run([str(Path(PAYLOAD)/'runtime/python.exe'),'-I','-B','-c',code],cwd=self.root,capture_output=True,text=True,timeout=40)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('Embedded MCP installation and project routing verified',result.stdout)

    def test_component_revisions_and_global_manifest_read(self):
        first=self.invoke('hub_instructions',action='read')
        validate_bundle(first)
        compact=self.invoke('hub_instructions',action='manifest')
        self.assertNotIn('files',compact)
        self.assertEqual(first['manifest']['revision'],compact['revision'])
        self.assertEqual(first['connectionContext'],compact['connectionContext'])
        reference=first['files']['api-reference.md']
        self.assertIn('hub_knowledge',reference)
        self.assertIn('hub_task_update',reference)
        self.assertIn('expectedState',reference)
        self.assertLess(len(reference.encode()),160_000)
        update(self.registry,dict(expected=read(self.registry)['revision'],text='Preserve user-authored documentation.'))
        second=self.invoke('hub_instructions',action='read')
        self.assertNotEqual(first['manifest']['revision'],second['manifest']['revision'])
        self.assertEqual(first['manifest']['components']['workflow.md'],second['manifest']['components']['workflow.md'])
        self.assertEqual(second['files']['user-additions.md'],'Preserve user-authored documentation.')
        second['files']['workflow.md']+='Corrupt'
        with self.assertRaises(ValueError): validate_bundle(second)

    def test_empty_additions_do_not_import_the_legacy_plugin_template(self):
        self.assertEqual(bundle(self.registry)['instructionBundle']['files']['user-additions.md'],'')
        from hub_instructions import default_body
        state=dict(initialized=True,body=default_body(),history=[])
        with patch('hub_instructions.Instructions.read',return_value=state):
            self.assertEqual(read(self.registry)['text'],'')
        with patch('hub_instructions.Instructions.read',return_value=dict(state,body='User-authored addition.')):
            self.assertEqual(read(self.registry)['text'],'User-authored addition.')

    def test_previous_instruction_snapshot_remains_readable_for_upgrade(self):
        from copy import deepcopy
        from agent_instructions import _revision
        import json
        previous=deepcopy(bundle(self.registry)['instructionBundle'])
        previous['manifest']['contractVersion']=4
        previous['files'].pop('api-reference.md')
        previous['manifest']['components'].pop('api-reference.md')
        previous['manifest'].pop('revision')
        previous['manifest']['revision']=_revision(json.dumps(previous['manifest'],sort_keys=True,separators=(',',':')))
        validate_bundle(previous)
        incomplete=deepcopy(bundle(self.registry)['instructionBundle'])
        incomplete['files'].pop('api-reference.md')
        with self.assertRaises(ValueError):validate_bundle(incomplete)

    def test_parallel_manifest_reads_reuse_static_reference_but_refresh_user_additions(self):
        from agent_instructions import operation_reference
        from agent_contracts import api_reference
        operation_reference.cache_clear()
        try:
            with patch('agent_contracts.api_reference',wraps=api_reference) as generate:
                first=bundle(self.registry)['instructionBundle']
                update(self.registry,dict(expected=read(self.registry)['revision'],text='Updated user rule.'))
                second=bundle(self.registry)['instructionBundle']
                self.assertEqual(generate.call_count,1)
            self.assertEqual(first['files']['api-reference.md'],second['files']['api-reference.md'])
            self.assertEqual(second['files']['user-additions.md'],'Updated user rule.')
            self.assertNotEqual(first['manifest']['revision'],second['manifest']['revision'])
        finally:
            operation_reference.cache_clear()

    def test_local_address_aliases_keep_the_same_connection_context(self):
        self.assertEqual(connection_context('id','http://localhost/'),connection_context('id','http://127.0.0.1:80'))
        value=dict(bundle(self.registry)['instructionBundle'],connectionContext=dict(connection=self.connection['binding'],baseUrl=self.native['baseUrl']))
        native=dict(self.native,baseUrl=self.native['baseUrl'].replace('127.0.0.1','localhost'))
        plan=build_plan('codex',native,value,native_home=self.root/'.codex',instructions_home=self.root/'instructions')
        self.assertEqual(plan.manifest['connectionContext'],value['connectionContext'])
        with self.assertRaises(OnboardingError):
            build_plan('codex',dict(native,baseUrl='http://localhost:8768'),value,native_home=self.root/'.codex',instructions_home=self.root/'instructions')

    def test_global_rule_is_short_preserves_personal_rules_and_is_idempotent(self):
        path=self.root/'.codex/AGENTS.md'
        path.parent.mkdir()
        original=b'# Personal rules\r\nKeep exact bytes.  \r\n'
        path.write_bytes(original)
        value=self.native_plan()
        result=apply_plan(value,expected_preview=value.fingerprint)
        self.assertTrue(result['instructionsPersisted'])
        self.assertFalse(result['setupVerified'])
        self.assertTrue(path.read_bytes().startswith(original))
        self.assertLess(len(path.read_bytes()),6000)
        self.assertNotIn(self.connection['token'],path.read_text())
        self.assertNotIn('## Task pipeline',path.read_text())
        manifest=result['instructionManifest']
        self.assertIn('## Task pipeline',Path(manifest['paths']['workflow.md']).read_text())
        repeated=self.native_plan()
        self.assertFalse(apply_plan(repeated,expected_preview=repeated.fingerprint)['changed'])

    def test_snapshot_update_and_corruption_repair_never_modify_active_files(self):
        first=self.native_plan()
        old=apply_plan(first,expected_preview=first.fingerprint)['instructionManifest']
        old_path=Path(old['paths']['workflow.md'])
        original=old_path.read_bytes()
        update(self.registry,dict(expected=read(self.registry)['revision'],text='New user addition.'))
        second=self.native_plan()
        current=apply_plan(second,expected_preview=second.fingerprint)['instructionManifest']
        self.assertEqual(old_path.read_bytes(),original)
        corrupt=Path(current['paths']['workflow.md'])
        corrupt.write_text('damaged',encoding='utf-8')
        repair=self.native_plan()
        repaired=apply_plan(repair,expected_preview=repair.fingerprint)['instructionManifest']
        self.assertNotEqual(repaired['paths']['workflow.md'],current['paths']['workflow.md'])
        self.assertEqual(corrupt.read_text(),'damaged')
        self.assertIn('## Task pipeline',Path(repaired['paths']['workflow.md']).read_text())

    def test_cursor_snapshot_reports_native_global_installation_pending(self):
        plan=self.native_plan(host='cursor')
        result=apply_plan(plan,expected_preview=plan.fingerprint)
        self.assertTrue(result['bundleSaved'])
        self.assertFalse(result['instructionsPersisted'])
        self.assertIsNone(result['rulePath'])

    def test_global_snapshot_cannot_be_saved_in_an_explicit_workspace(self):
        with self.assertRaises(OnboardingError):
            build_plan('codex',self.native,bundle(self.registry)['instructionBundle'],workspace=self.workspace,
                       native_home=self.root/'.codex',instructions_home=self.workspace/'instructions')

    def test_stale_native_preview_does_not_touch_the_global_rule(self):
        plan=self.native_plan()
        target=plan.native.path
        target.parent.mkdir()
        target.write_text('Concurrent user rule',encoding='utf-8')
        with self.assertRaises(OnboardingError): apply_plan(plan,expected_preview=plan.fingerprint)
        self.assertEqual(target.read_text(),'Concurrent user rule')
        self.assertFalse((self.root/'instructions').exists())

    def test_resolve_creates_one_project_and_repairs_interrupted_baseline(self):
        request=dict(action='resolve',scope=self.scope,requestId=uuid.uuid4().hex)
        original=self.registry.base_store
        with patch.object(self.registry,'base_store',side_effect=OSError('Simulated interruption')):
            with self.assertRaises(OSError): self.bindings.execute(self.connection['binding'],request)
        with patch.object(self.registry,'base_store',wraps=original) as repair:
            value=self.bindings.execute(self.connection['binding'],request)
            repair.assert_called_once_with(value['binding']['project'])
        repeated=self.bindings.execute(self.connection['binding'],dict(request,requestId=uuid.uuid4().hex))
        self.assertEqual(value['binding']['id'],repeated['binding']['id'])
        self.assertFalse(repeated['created'])
        self.assertEqual(len(self.connections.projects(dict(scope='global'))),1)

    def test_ambiguous_roots_never_guess_or_create_a_third_project(self):
        for name in ('First','Second'):self.registry.create(name,[str(self.workspace)])
        with self.assertRaises(BindingError) as error:self.resolve()
        self.assertEqual(error.exception.code,'project_ambiguous')
        self.assertEqual(len(self.connections.projects(dict(scope='global'))),2)

    def test_bound_startup_requires_actual_scope_and_revision(self):
        b=self.resolve()
        with self.assertRaises(BindingError):self.invoke('hub_context',**self.selected(b,False))
        wrong=dict(b['scope'],nativeRef='another-project')
        with self.assertRaises(BindingError):self.invoke('hub_context',**dict(self.selected(b),projectScope=wrong))
        context=self.invoke('hub_context',**self.selected(b))
        self.assertEqual(context['projectBinding']['project'],b['project'])
        self.assertIn('instructionManifest',context)
        with self.assertRaises(BindingError):self.invoke('hub_task',session='cold-chat',**self.selected(b),title='No admission',scope=['X'],acceptance=['Y'])

    def test_binding_edit_tombstone_history_and_cross_connection_isolation(self):
        b=self.resolve()
        value=project_rule('codex',b,self.workspace)
        apply_rule(value,value['previewSha256'])
        self.assertIn(b['project'],value['path'].read_text())
        unbound=self.bindings.execute(self.connection['binding'],dict(action='unbind',bindingId=b['id'],expectedRevision=1,requestId=uuid.uuid4().hex))['binding']
        self.assertEqual(unbound['revision'],2)
        self.assertEqual(self.resolve()['status'],'unbound')
        removal=project_rule('codex',unbound,self.workspace)
        apply_rule(removal,removal['previewSha256'])
        self.assertNotIn('project-hub:binding',value['path'].read_text())
        with self.assertRaises(BindingError):self.invoke('hub_context',**self.selected(unbound))
        with self.assertRaises(BindingError):self.bindings.read('another-connection',b['id'])
        self.assertEqual(len(self.bindings.history(self.connection['binding'],b['id'])),2)

    def control(self):
        endpoint='http://127.0.0.1:9988'
        profile=dict(schemaVersion=1,control=dict(protocol='http-json',endpoint=endpoint),capabilities=dict(createChat=dict(
            path='/chats',projectRouting=True,arguments=dict(prompt='$prompt',scope='$projectScope',requestId='$requestId'))))
        profiles=Profiles(self.registry)
        profiles.describe(self.connection['binding'],profile)
        profiles.configure(dict(id=self.connection['binding'],protocol='http-json',endpoint=endpoint,apiKey='',requestId=uuid.uuid4().hex))

    def test_rebind_preserves_tasks_and_requires_a_new_session(self):
        b=self.resolve()
        self.invoke('hub_context',**self.selected(b))
        task=self.invoke('hub_task',**self.selected(b),title='Original task',scope=['Scope'],acceptance=['Evidence'])['task']
        other=self.registry.create('Other project',[str(self.workspace)])['id']
        rebound=self.bindings.execute(self.connection['binding'],dict(action='update',bindingId=b['id'],project=other,expectedRevision=1,requestId=uuid.uuid4().hex))['binding']
        with self.assertRaises(BindingError):self.invoke('hub_context',**self.selected(rebound))
        self.invoke('hub_context',session='new-project-session',**self.selected(rebound))
        self.assertTrue(any(item['id']==task for item in self.registry.store(b['project']).task_context(task)['tasks']))
        self.assertFalse(any(item['id']==task for item in self.registry.store(other).snapshot()['tasks']))

    def test_directory_relocation_recovers_after_partial_commit(self):
        b=self.resolve()
        catalog=self.bindings.execute(self.connection['binding'],dict(action='workspaces',bindingId=b['id']))['workspaces']
        moved=self.root/'moved-repository';moved.mkdir()
        request=dict(action='relocate',bindingId=b['id'],scope=dict(b['scope'],root=str(moved)),expectedRevision=1,
                     expectedProjectRevision=catalog['revision'],workspaceId=catalog['items'][0]['id'],requestId=uuid.uuid4().hex)
        with patch.object(self.bindings.connections,'workspace',side_effect=BindingError('interruption','Simulated interruption')):
            with self.assertRaises(BindingError):self.bindings.execute(self.connection['binding'],request)
        with self.assertRaises(BindingError) as error:self.invoke('hub_context',**self.selected(b))
        self.assertEqual(error.exception.code,'project_relocation_pending')
        with self.assertRaises(BindingError):self.bindings.execute(self.connection['binding'],dict(action='unbind',bindingId=b['id'],expectedRevision=1,requestId=uuid.uuid4().hex))
        self.control()
        with self.assertRaises(BindingError):Launches(self.registry).start(self.connection['binding'],dict(requestId=uuid.uuid4().hex,bindingId=b['id'],operation='task-execute',task='missing'))
        with self.assertRaises(BindingError):self.bindings.execute(self.connection['binding'],dict(request,scope=dict(request['scope'],nativeRef='different')))
        pending=self.bindings.read(self.connection['binding'],b['id'])['pendingRelocation']
        self.assertTrue(pending['workspaceCommitted'])
        self.assertEqual(pending['arguments'],{key:value for key,value in request.items() if key!='action'})
        with self.assertRaises(BindingError):self.bindings.execute('another-connection',dict(action='resume',bindingId=b['id'],requestId=pending['requestId']))
        resume=dict(action='resume',bindingId=b['id'],requestId=pending['requestId'])
        result=self.bindings.execute(self.connection['binding'],resume)['binding']
        self.assertEqual(result['project'],b['project'])
        self.assertEqual(result['scope']['root'],str(moved.resolve()))
        self.assertEqual(result['revision'],2)
        self.assertEqual(self.connections.project(b['project'])['roots'],[str(moved.resolve())])
        self.assertEqual(self.bindings.execute(self.connection['binding'],request)['binding'],result)
        self.assertEqual(self.bindings.execute(self.connection['binding'],resume)['binding'],result)
        self.assertNotIn('pendingRelocation',self.bindings.read(self.connection['binding'],b['id']))
        self.invoke('hub_context',**self.selected(result))

    def test_legacy_relocation_reservation_is_preserved_without_guessing(self):
        b=self.resolve();request_id=uuid.uuid4().hex
        with self.registry.connect() as c:
            c.execute('DROP TABLE agent_project_moves')
            c.execute('CREATE TABLE agent_project_moves(id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,binding TEXT NOT NULL)')
            c.execute('INSERT INTO agent_project_moves VALUES(?,?,?)',(request_id,'legacy',b['id']))
        pending=self.bindings.read(self.connection['binding'],b['id'])['pendingRelocation']
        self.assertFalse(pending['recoverable'])
        with self.assertRaises(BindingError) as error:
            self.bindings.execute(self.connection['binding'],dict(action='resume',bindingId=b['id'],requestId=request_id))
        self.assertEqual(error.exception.code,'project_relocation_unrecoverable')
        with self.registry.connect() as c:
            self.assertIsNotNone(c.execute('SELECT 1 FROM agent_project_moves WHERE id=?',(request_id,)).fetchone())

    def test_rejected_relocation_releases_its_uncommitted_reservation(self):
        b=self.resolve()
        catalog=self.bindings.execute(self.connection['binding'],dict(action='workspaces',bindingId=b['id']))['workspaces']
        moved=self.root/'moved-repository';moved.mkdir()
        request=dict(action='relocate',bindingId=b['id'],scope=dict(b['scope'],root=str(moved)),expectedRevision=1,
                     expectedProjectRevision=catalog['revision']+1,workspaceId=catalog['items'][0]['id'],requestId=uuid.uuid4().hex)
        with self.assertRaises(BindingError):self.bindings.execute(self.connection['binding'],request)
        self.invoke('hub_context',**self.selected(b))
        result=self.bindings.execute(self.connection['binding'],dict(request,requestId=uuid.uuid4().hex,expectedProjectRevision=catalog['revision']))
        self.assertEqual(result['binding']['scope']['root'],str(moved.resolve()))

    def launch(self,b,**args):
        self.control()
        request=dict(requestId=uuid.uuid4().hex,bindingId=b['id'],**args)
        with patch('agent_launches.HttpControl.action',return_value=dict(id='native-chat-one')) as action:
            result=Launches(self.registry).start(self.connection['binding'],request)
            sent=action.call_args.args[1]
            self.assertEqual(sent['$envelope']['project'],b['project'])
            self.assertEqual(sent['$projectScope'],b['scope'])
            repeated=Launches(self.registry).start(self.connection['binding'],request)
            self.assertEqual(result,repeated)
            self.assertEqual(action.call_count,1)
        self.assertEqual(result['status'],'awaiting_ack')
        self.invoke('hub_context',**self.selected(b))
        acknowledged=self.invoke('hub_launch',action='ack',requestId=result['requestId'],projectScope=b['scope'],nativeId='native-chat-one')
        self.assertTrue(acknowledged['nativeRoutingVerified'])
        return result

    def test_launch_is_unavailable_without_documented_project_control(self):
        b=self.resolve()
        with self.assertRaises(BindingError):Launches(self.registry).start(self.connection['binding'],dict(requestId=uuid.uuid4().hex,bindingId=b['id'],operation='task-execute',task='missing'))

    def test_launch_management_requires_trusted_admin_boundary(self):
        from agent_api import execute
        with self.assertRaises(BindingError) as error:
            execute(self.registry,'/api/v1/connections',dict(action='launch',id=self.connection['binding'],request={}),{},'http://127.0.0.1:8769')
        self.assertEqual(error.exception.status,403)

    def test_uncertain_dispatch_does_not_create_another_chat(self):
        b=self.resolve();self.control()
        knowledge=KnowledgeStore(self.registry,b['project'])
        knowledge.changeset(0,'fixture',[dict(op='put',item=dict(id='component',kind='entity',type='component',title='Component'))],'Fixture')
        args=dict(requestId=uuid.uuid4().hex,bindingId=b['id'],operation='architecture-analyze',research=dict(operation='architecture-analyze',objectId='component',revision=1))
        with patch('agent_launches.HttpControl.action',side_effect=OSError('Unknown outcome')) as action:
            first=Launches(self.registry).start(self.connection['binding'],args)
            second=Launches(self.registry).start(self.connection['binding'],args)
            self.assertEqual(first,second);self.assertEqual(action.call_count,1)
        self.assertEqual(first['status'],'dispatch_unknown')

    def test_control_routing_conflict_blocks_result_publication(self):
        b=self.resolve();self.control()
        knowledge=KnowledgeStore(self.registry,b['project'])
        knowledge.changeset(0,'fixture',[dict(op='put',item=dict(id='component',kind='entity',type='component',title='Component'))],'Fixture')
        args=dict(requestId=uuid.uuid4().hex,bindingId=b['id'],operation='architecture-analyze',research=dict(operation='architecture-analyze',objectId='component',revision=1))
        def receive(*_):
            self.invoke('hub_context',**self.selected(b))
            self.invoke('hub_launch',action='ack',requestId=args['requestId'],nativeId='actual-native-chat',projectScope=b['scope'])
            return dict(id='different-control-chat')
        with patch('agent_launches.HttpControl.action',side_effect=receive):result=Launches(self.registry).start(self.connection['binding'],args)
        self.assertEqual(result['status'],'routing_conflict')
        with self.assertRaises(BindingError):self.invoke('hub_launch',action='complete',requestId=args['requestId'],nativeId='actual-native-chat',result=dict(title='Rejected',markdown='Wrong routing.'))
        self.assertEqual(knowledge.context()['revision'],1)

    def test_binding_change_before_or_during_dispatch_cancels_launch(self):
        b=self.resolve();self.control()
        knowledge=KnowledgeStore(self.registry,b['project'])
        knowledge.changeset(0,'fixture',[dict(op='put',item=dict(id='component',kind='entity',type='component',title='Component'))],'Fixture')
        def repair():
            current=self.bindings.read(self.connection['binding'],b['id'])
            self.bindings.execute(self.connection['binding'],dict(action='repair',bindingId=b['id'],expectedRevision=current['revision'],requestId=uuid.uuid4().hex))
        def dispatch(*_):
            repair()
            return dict(id='native-chat-one')
        args=dict(bindingId=b['id'],operation='architecture-analyze',research=dict(operation='architecture-analyze',objectId='component',revision=1))
        with patch('agent_launches.HttpControl.action',side_effect=dispatch) as action:
            result=Launches(self.registry).start(self.connection['binding'],dict(args,requestId=uuid.uuid4().hex))
            self.assertEqual(action.call_count,1)
        self.assertEqual(result['status'],'cancelled')
        client=Mock()
        def construct(*_):
            repair()
            return client
        with patch('agent_launches.HttpControl',side_effect=construct):
            result=Launches(self.registry).start(self.connection['binding'],dict(args,requestId=uuid.uuid4().hex))
        self.assertEqual(result['status'],'cancelled')
        client.action.assert_not_called()

    def test_task_launch_correlates_saved_owned_report_and_rejects_other_chat(self):
        b=self.resolve()
        self.invoke('hub_context',**self.selected(b))
        task=self.invoke('hub_task',**self.selected(b),title='Example task',scope=['Work'],acceptance=['Evidence'])['task']
        self.invoke('hub_plan',**self.selected(b),task=task,stage='step',title='Inspect')
        result=self.launch(b,operation='task-execute',task=task,stage='step')
        with self.assertRaises(BindingError):self.invoke('hub_launch',session='different-chat',action='ack',requestId=result['requestId'],projectScope=b['scope'],nativeId='native-chat-one')
        work=self.invoke('hub_begin',**self.selected(b),task=task,stage='step',title='Inspect',resources=['resource:test'])
        report=self.invoke('hub_report',**self.selected(b),work=work['work'],revision=work['revision'],result='Verified',status='done')
        with self.assertRaises(BindingError):self.invoke('hub_launch',action='complete',requestId=result['requestId'],nativeId='wrong-native-chat',work=work['work'],revision=report['revision'])
        complete=self.invoke('hub_launch',action='complete',requestId=result['requestId'],nativeId='native-chat-one',work=work['work'],revision=report['revision'])
        self.assertEqual(complete['status'],'completed')
        self.assertEqual(complete['resultRef']['project'],b['project'])
        self.assertEqual(self.invoke('hub_launch',action='complete',requestId=result['requestId'],nativeId='native-chat-one',work=work['work'],revision=report['revision']),complete)

    def test_research_result_has_fixed_destination_and_revision_conflict(self):
        b=self.resolve()
        knowledge=KnowledgeStore(self.registry,b['project'])
        knowledge.changeset(0,'fixture',[dict(op='put',item=dict(id='component',kind='entity',type='component',title='Component'))],'Fixture')
        result=self.launch(b,operation='architecture-analyze',research=dict(operation='architecture-analyze',objectId='component',revision=1))
        complete=self.invoke('hub_launch',action='complete',requestId=result['requestId'],nativeId='native-chat-one',result=dict(title='Description',markdown='Evidence and limitations.'))
        self.assertEqual(complete['status'],'completed')
        document=knowledge.read(complete['resultRef']['id'])
        self.assertEqual(document['entityRefs'],['component'])
        self.assertEqual(document['markdown'],'Evidence and limitations.')
        # Another request captures revision 2, then concurrent authors advance it.
        second=self.launch(b,operation='architecture-analyze',research=dict(operation='architecture-analyze',objectId='component',revision=2))
        knowledge.changeset(2,'concurrent',[dict(op='put',item=dict(id='note',kind='document',title='Note',markdown='Keep me'))],'Concurrent edit')
        with self.assertRaises(BindingError):self.invoke('hub_launch',action='complete',requestId=second['requestId'],nativeId='native-chat-one',result=dict(title='Stale',markdown='Do not overwrite.'))
        self.assertEqual(knowledge.read('note')['markdown'],'Keep me')

    def test_connection_project_ui_escapes_data_and_sends_revision_checked_requests(self):
        script=ROOT/'tools/project-portal/web/connection-projects.js'
        harness='''const fs=require('fs'),vm=require('vm'),assert=require('assert');
        const c={crypto:{randomUUID:()=> '12345678-1234-4234-8234-123456789abc'},HubI18n:{locale:'en'}};c.window=c;
        vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),c);
        const b={id:'binding',connection:'owner',project:'p',scope:{kind:'workspace',root:'<directory>'},revision:3,status:'active',ruleState:'needs-repair'};
        const row={id:'owner',scope:'global',projectBindings:[b],profile:{schemaVersion:1},launches:[]};
        const html=c.HubConnectionProjects.render(row,[{id:'p',name:'<Project>'}],false);
        assert(html.includes('&lt;Project&gt;'));assert(!html.includes('<Project>'));assert(html.includes('data-binding-action="manage"'));
        assert(!html.includes('data-project-binding-form'));assert(!html.includes('data-project-launch-form'));assert(!html.includes('name="root"'));assert(!html.includes('name="nativeRef"'));
        (async()=>{
        await c.HubConnectionProjects.click({dataset:{owner:'owner',binding:'binding',bindingAction:'manage'}},[row],()=>{});
        const managed=c.HubConnectionProjects.render(row,[{id:'p',name:'<Project>'}],false);assert(managed.includes('&lt;directory&gt;'));assert(managed.includes('Project directory'));assert(!managed.includes('<select'));
        for(const action of ['repair','history'])await c.HubConnectionProjects.click({dataset:{owner:'owner',binding:'binding',bindingAction:action}},[row],(body,kind)=>{assert.equal(kind,'project-binding');assert.equal(body.operation.bindingId,'binding');assert.equal(body.operation.action,action);if(action==='repair')assert.equal(body.operation.expectedRevision,3);assert(!body.operation.scope);assert(!body.operation.project);});
        b.status='unbound';c.confirm=()=>true;
        await c.HubConnectionProjects.click({dataset:{owner:'owner',binding:'binding',bindingAction:'reconnect'}},[row],body=>{assert.equal(body.operation.action,'repair');assert.equal(body.operation.expectedRevision,3);assert(!body.operation.project);});
        b.pendingRelocation={requestId:'original-request',recoverable:true,arguments:{scope:{root:'<moved>'}}};
        assert(c.HubConnectionProjects.render(row,[],false).includes('Resume relocation'));
        await c.HubConnectionProjects.click({dataset:{owner:'owner',binding:'binding',bindingAction:'resume'}},[row],body=>{assert.equal(body.operation.action,'resume');assert.equal(body.operation.requestId,'original-request');assert(!body.operation.scope);});
        row.projectBindings=[];
        c.fetch=async()=>({ok:true,json:async()=>({project:'p',items:[{kind:'local',enabled:true,descriptor:{rootRef:'1',root:'/external-resource'}},{kind:'local',enabled:true,descriptor:{rootRef:'0',root:'/primary-source'}}]})});
        await c.HubConnectionProjects.click({dataset:{owner:'owner',project:'p',bindingAction:'connect'}},[row],()=>{});
        const preview=c.HubConnectionProjects.render(row,[{id:'p',name:'Example'}],false);assert(preview.includes('/primary-source'));assert(!preview.includes('/external-resource'));assert(!preview.includes('<input'));
        await c.HubConnectionProjects.click({dataset:{owner:'owner',bindingAction:'confirm-connect'}},[row],body=>{assert.equal(body.operation.action,'resolve');assert.equal(body.operation.project,'p');assert.equal(body.operation.scope.root,'/primary-source');});
        })().catch(error=>{console.error(error);process.exitCode=1});'''
        result=subprocess.run(['node','-e',harness,str(script)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
