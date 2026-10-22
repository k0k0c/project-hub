"""Agent identity, enrollment recovery and rootless task pipeline contracts."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from agent_bindings import BindingError, Connections, digest, fingerprint
from agent_runtime import actor_id, call, call_internal_research
from artifact_store import publish
from hub_core import HubError
from project_registry import ProjectRegistry


class AgentGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.registry = ProjectRegistry(Path(self.temp.name)/'home',standalone=True)
        self.addCleanup(self.registry.close_connection_pool)
        self.connections = Connections(self.registry)

    def enroll(self, project=None, request='a', external='workspace', **kwargs):
        if project is None:
            project = self.registry.create(kwargs.pop('name'),kwargs.pop('roots',None))['id']
        invite = self.connections.invite(project,request_id=request*32)
        return self.connections.enroll(invite['token'],'example-agent',external,**kwargs)

    def invoke(self, connection, tool, session='conversation', **arguments):
        return call(self.registry,connection['token'],tool,dict(session=session,**arguments))

    def test_internal_research_has_stable_principal_but_separate_sessions_and_no_app_token(self):
        project = self.registry.create('Example')['id']
        first = call_internal_research(self.registry,project,'hub_context',dict(session='api:first'))['connection']
        second = call_internal_research(self.registry,project,'hub_context',dict(session='api:second'))['connection']
        self.assertEqual(first['binding'],second['binding'])
        self.assertNotEqual(first['actor'],second['actor'])
        self.assertEqual(first['kind'],'internal-service')
        self.assertEqual(first['nativeIdentity'],'hub-owned')
        self.assertEqual(self.connections.catalog()['bindings'],[])
        with self.assertRaises(BindingError):
            call(self.registry,first['binding'],'hub_context',dict(session='outside'))
        other = self.registry.create('Other')['id']
        with self.assertRaises(BindingError):
            call_internal_research(self.registry,project,'hub_context',dict(session='api:first',project=other))
        for tool,args in (('hub_connection',dict(action='read')),('hub_launch',dict(action='read')),
                          ('hub_knowledge',dict(action='changeset')),('hub_context',dict(nativeChat={})),
                          ('hub_task',dict(title='Not an internal operation')),('hub_plan',{}),
                          ('hub_begin',{}),('hub_report',{})):
            with self.subTest(tool=tool),self.assertRaises(HubError):
                call_internal_research(self.registry,project,tool,dict(session='api:first',**args))

    def test_legacy_api_registrations_are_classified_by_host_receipts_without_revoking_keys(self):
        project = self.registry.create('Example')['id']
        action = 'old-analysis'
        invitation = self.connections.invite(project,request_id=digest('api-invite:'+action)[:32])
        internal = self.connections.enroll(invitation['token'],'hub-api',action)
        external = self.connections.enroll(self.connections.invite(project,request_id='b'*32)['token'],'hub-api','actual-installation')
        with self.registry.connect() as connection:
            connection.execute('CREATE TABLE api_agent_runs(project TEXT,action_id TEXT)')
            connection.execute('INSERT INTO api_agent_runs VALUES(?,?)',(project,action))
        catalog = self.connections.catalog()
        self.assertEqual([row['id'] for row in catalog['bindings']],[external['binding']])
        self.assertNotIn(invitation['id'],[row['id'] for row in catalog['invitations']])
        self.assertEqual(self.connections.authenticate(internal['token'])['id'],internal['binding'])
        self.assertEqual(self.connections.authenticate(external['token'])['id'],external['binding'])
        # Classification is a read-only projection; old credentials/history remain.
        with self.registry.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM client_bindings WHERE client='hub-api'").fetchone()[0],2)

    def test_rootless_pipeline_preserves_project_stage_result_and_completion(self):
        connection = self.enroll(name='Example project')
        with patch.object(self.registry.catalog,'assigned_project',side_effect=AssertionError('Native catalog must not bind generic actors')):
            context = self.invoke(connection,'hub_context')
            self.assertEqual(context['connection']['project'],connection['project'])
            self.assertEqual(context['connection']['actor'],actor_id(connection['binding'],'conversation'))
            self.assertFalse(context['workspace']['available'])
            task = self.invoke(connection,'hub_task',title='Investigate',scope=['Example scope'],acceptance=['Evidence retained'])['task']
            revision = self.invoke(connection,'hub_plan',task=task)['revision']
            self.invoke(connection,'hub_plan',task=task,stage='inspect',title='Inspect',expected=revision)
            work = self.invoke(connection,'hub_begin',task=task,stage='inspect',title='Inspect independent project',resources=['resource:analysis'])
            report = self.invoke(connection,'hub_report',work=work['work'],revision=work['revision'],result='Verified independent task pipeline',status='done',stage_status='done')
            self.assertEqual(report['planSync'],'saved')
            plan = self.invoke(connection,'hub_plan',task=task)
            self.assertEqual(plan['task']['stages'][0]['status'],'done')
            self.assertIn('Verified independent task pipeline',json.dumps(plan))
            self.invoke(connection,'hub_task_close',task=task,expected=plan['revision'],mode='auto')
            self.assertEqual(self.registry.store(connection['project']).task_context(task)['tasks'][0]['status'],'done')
        with self.registry.coordination_connect() as c:
            row = c.execute('SELECT project,workspace FROM sessions WHERE id=?',(context['connection']['actor'],)).fetchone()
            self.assertEqual(row['project'],connection['project'])
            self.assertIsNone(row['workspace'])

    def test_same_native_id_in_separate_bindings_does_not_share_work_authority(self):
        project = self.registry.create('Shared example',request_id='b'*32)['id']
        first = self.enroll(project,request='c',external='first')
        second = self.enroll(project,request='d',external='second')
        task = self.invoke(first,'hub_task',title='Example',scope=['Inspect'],acceptance=['Verified'])['task']
        self.invoke(first,'hub_plan',task=task,stage='inspect',title='Inspect')
        work = self.invoke(first,'hub_begin',task=task,stage='inspect',title='First actor work',resources=['resource:example'])
        with self.assertRaises(HubError):
            self.invoke(second,'hub_report',work=work['work'],revision=work['revision'],result='Cannot report another actor work')
        self.assertNotEqual(actor_id(first['binding'],'conversation'),actor_id(second['binding'],'conversation'))
        self.assertEqual(self.invoke(first,'hub_context',work=work['work'])['work'][0]['status'],'active')

    def test_project_scope_rejects_foreign_task_and_cross_project_link(self):
        first = self.enroll(name='First',request='e')
        second = self.enroll(name='Second',request='f',external='second')
        task = self.invoke(second,'hub_task',title='Private task',scope=['Second project'],acceptance=['Verified'])['task']
        with self.assertRaises(HubError):
            self.invoke(first,'hub_plan',task=task)
        own = self.invoke(first,'hub_task',title='Own task',scope=['First project'],acceptance=['Verified'])['task']
        revision = self.invoke(first,'hub_plan',task=own)['revision']
        with self.assertRaises(HubError) as failure:
            self.invoke(first,'hub_task_link',task=own,target=task,type='related',project=second['project'],expected=revision)
        self.assertEqual(failure.exception.body['error'],'project_unavailable')

    def test_invitation_and_enrollment_exact_retries_preserve_ids_and_credentials(self):
        invite = self.connections.invite(request_id='1'*32)
        self.assertEqual(invite,self.connections.invite(request_id='1'*32))
        first = self.connections.enroll(invite['token'],'example','workspace')
        self.assertEqual(first,self.connections.enroll(invite['token'],'example','workspace'))
        self.assertEqual(self.registry.list()['projects'],[])
        with self.assertRaises(BindingError):
            self.connections.enroll(invite['token'],'example','other')
        self.assertNotIn(invite['token'],json.dumps(self.connections.catalog()))
        self.assertNotIn(first['token'],json.dumps(self.connections.catalog()))

    def test_task_link_target_alias_works_for_global_and_legacy_connections(self):
        legacy = self.enroll(name='Registered example')
        global_connection = self.connections.enroll(self.connections.invite(request_id='d'*32)['token'],'example','global')
        for connection in (legacy,global_connection):
            with self.subTest(scope=connection.get('scope','project')):
                selected = {'project':legacy['project']} if connection is global_connection else {}
                task = self.invoke(connection,'hub_task',**selected,title='Source task',scope=['Inspect'],acceptance=['Linked'])['task']
                target = self.invoke(connection,'hub_task',**selected,title='Target task',scope=['Inspect'],acceptance=['Verified'])['task']
                revision = self.invoke(connection,'hub_plan',**selected,task=task)['revision']
                self.invoke(connection,'hub_task_link',**selected,task=task,target=target,type='related',
                            targetProject=legacy['project'],expected=revision)
                links = self.registry.store(legacy['project']).task_context(task)['tasks'][0]['links']
                self.assertIn({'type':'related','target':target,'project':legacy['project']},links)
        revision = self.invoke(legacy,'hub_plan',task=task)['revision']
        self.invoke(legacy,'hub_task_link',task=task,target=target,type='related',project=None,expected=revision)

    def test_revocation_blocks_existing_reads_and_enrollment_receipt_replay(self):
        invite = self.connections.invite(request_id='2'*32)
        connection = self.connections.enroll(invite['token'],'example','workspace')
        self.invoke(connection,'hub_projects')
        self.connections.revoke(connection['binding'])
        with self.assertRaises(BindingError):
            self.invoke(connection,'hub_plan',task='anything')
        with self.assertRaises(BindingError):
            self.connections.enroll(invite['token'],'example','workspace')

    def test_expired_invitation_cannot_create_project(self):
        invite = self.connections.invite(request_id='3'*32)
        with self.registry.connect() as c:
            c.execute('UPDATE agent_invitations SET expires=0 WHERE id=?',(invite['id'],))
        with self.assertRaises(BindingError) as failure:
            self.connections.enroll(invite['token'],'example','workspace',name='Example')
        self.assertEqual(failure.exception.code,'invitation_expired')
        self.assertEqual(self.registry.list()['projects'],[])

    def test_rootless_artifacts_work_but_raw_files_and_git_have_typed_refusal(self):
        connection = self.enroll(name='Example')
        task = self.invoke(connection,'hub_task',title='Example task',scope=['Inspect'],acceptance=['Evidence retained'])['task']
        item = publish(self.registry.store(connection['project']),'proof.txt',b'Immutable evidence',roles=['evidence'])
        revision = self.invoke(connection,'hub_plan',task=task)['revision']
        attached = self.invoke(connection,'hub_artifact',task=task,path=item['source']['path'],expected=revision)
        self.assertEqual(attached['source']['path'],item['source']['path'])
        evidence = self.invoke(connection,'hub_memory',ref='source:'+item['source']['path'])
        self.assertEqual(evidence['text'],'Immutable evidence')
        for tool,args in [('hub_artifact',dict(task=task,path='proof.txt',expected=attached['revision'])),
                          ('hub_git_batch',dict(action='preview',targets=[],expected=attached['revision'],reason='Inspect'))]:
            with self.subTest(tool=tool),self.assertRaises(HubError) as failure:
                self.invoke(connection,tool,**args)
            self.assertEqual(failure.exception.body['error'],'workspace_required')

    def test_unregistered_workspace_is_rejected_without_creating_binding(self):
        project = self.registry.create('Example',request_id='4'*32)['id']
        invite = self.connections.invite(project,request_id='5'*32)
        external = Path(self.temp.name)/'outside'
        external.mkdir()
        with self.assertRaises(BindingError) as failure:
            self.connections.enroll(invite['token'],'example','workspace',workspace=str(external))
        self.assertEqual(failure.exception.code,'workspace_unregistered')
        self.assertEqual(self.connections.catalog()['bindings'],[])

    def test_rooted_project_without_workspace_cannot_read_or_attach_local_files(self):
        root=Path(self.temp.name)/'code';root.mkdir();(root/'proof.txt').write_text('Private source')
        project=self.registry.create('Rooted example',[str(root)],request_id='6'*32)['id']
        connection=self.enroll(project,request='7')
        task=self.invoke(connection,'hub_task',title='Review',scope=['Inspect'],acceptance=['Verified'])['task']
        revision=self.invoke(connection,'hub_plan',task=task)['revision']
        self.invoke(connection,'hub_plan',task=task,stage='inspect',title='Inspect',expected=revision)
        work=self.invoke(connection,'hub_begin',task=task,stage='inspect',title='Inspect',resources=['resource:analysis'])
        revision=self.invoke(connection,'hub_plan',task=task)['revision']
        calls=[('hub_artifact',dict(task=task,path='proof.txt',expected=revision)),
            ('hub_image',dict(task=task,path='proof.txt',expected=revision)),
            ('hub_report',dict(work=work['work'],revision=work['revision'],result='Inspect',evidence=['proof.txt'])),
            ('hub_memory',dict(ref='source:proof.txt')),('hub_migration_preview',{}),
            ('hub_knowledge',dict(action='scan'))]
        for tool,args in calls:
            with self.subTest(tool=tool),self.assertRaises(HubError) as failure:self.invoke(connection,tool,**args)
            self.assertEqual(failure.exception.body['error'],'workspace_required')
        item=publish(self.registry.store(project),'proof.txt',b'Uploaded evidence',roles=['evidence'])
        attached=self.invoke(connection,'hub_artifact',task=task,path=item['source']['path'],expected=revision)
        self.assertEqual(attached['source']['path'],item['source']['path'])

    def test_local_evidence_is_scoped_to_the_registered_connection_workspace(self):
        root=Path(self.temp.name)/'code';root.mkdir();inside=root/'inside';inside.mkdir()
        (root/'outside.txt').write_text('Outside');(inside/'proof.txt').write_text('Inside')
        project=self.registry.create('Scoped example',[str(root)],request_id='8'*32)['id']
        connection=self.enroll(project,request='9',workspace=str(inside))
        task=self.invoke(connection,'hub_task',title='Review',scope=['Inspect'],acceptance=['Verified'])['task']
        revision=self.invoke(connection,'hub_plan',task=task)['revision']
        with self.assertRaises(HubError) as failure:self.invoke(connection,'hub_artifact',task=task,path='outside.txt',expected=revision)
        self.assertEqual(failure.exception.body['error'],'workspace_scope')
        attached=self.invoke(connection,'hub_artifact',task=task,path='inside/proof.txt',expected=revision)
        self.assertTrue(attached['source']['path'].startswith('hub-artifact/'))

    def test_global_connection_enrolls_unknown_host_before_any_project(self):
        invite = self.connections.invite(request_id='b'*32)
        connection = self.connections.enroll(invite['token'],'unknown-agent-host','connection-one',
            chat='Client-reported chat',metadata={'label':'Example connection','clientVersion':'example-version'})
        self.assertEqual(connection['scope'],'global')
        self.assertIsNone(connection['project'])
        self.assertEqual(self.invoke(connection,'hub_projects')['projects'],[])
        row = self.connections.catalog()['bindings'][0]
        self.assertEqual(row['client'],'unknown-agent-host')
        self.assertNotIn('model',row['metadata'])
        self.assertEqual(row['metadata']['chat'],'Client-reported chat')
        self.assertEqual(row['nativeIdentity'],'client-reported')
        self.assertEqual(row['activity']['state'],'unknown')
        self.assertFalse(row['activity']['runningVerified'])
        self.assertNotIn(connection['token'],json.dumps(self.connections.catalog()))
        second = self.connections.enroll(self.connections.invite(request_id='c'*32)['token'],
            'unknown-agent-host','connection-two',model='Exact reported model')
        self.assertNotEqual(connection['binding'],second['binding'])
        self.assertEqual(len(self.connections.catalog()['bindings']),2)
        self.assertEqual(self.registry.list()['projects'],[])

    def test_global_calls_select_project_each_time_and_isolate_actors_and_tasks(self):
        connection = self.connections.enroll(self.connections.invite(request_id='d'*32)['token'],'example','global')
        first = self.registry.create('First registered project')['id']
        second = self.registry.create('Second registered project')['id']
        self.assertEqual({row['id'] for row in self.invoke(connection,'hub_projects')['projects']},{first,second})
        context = self.invoke(connection,'hub_context',project=first)
        task = self.invoke(connection,'hub_task',project=first,title='Private task',scope=['Inspect'],acceptance=['Verified'])['task']
        other = self.invoke(connection,'hub_context',project=second)
        self.assertNotEqual(context['connection']['actor'],other['connection']['actor'])
        self.assertEqual(context['connection']['actor'],actor_id(connection['binding'],'conversation',first))
        self.assertEqual(other['connection']['project'],second)
        with self.assertRaises(BindingError) as failure:
            self.invoke(connection,'hub_context')
        self.assertEqual(failure.exception.code,'project_required')
        with self.assertRaises(HubError):
            self.invoke(connection,'hub_plan',project=second,task=task)
        with self.assertRaises(BindingError) as failure:
            self.invoke(connection,'hub_context',project='unregistered')
        self.assertEqual(failure.exception.code,'project_unavailable')
        row = self.connections.catalog()['bindings'][0]
        self.assertEqual(row['activity']['state'],'recent-request')
        self.assertFalse(row['activity']['runningVerified'])

    def test_global_workspace_selection_rejects_ambiguity_and_does_not_retain_code_access(self):
        root = Path(self.temp.name)/'registered-code';root.mkdir()
        (root/'proof.txt').write_text('Local evidence')
        connection = self.connections.enroll(self.connections.invite(request_id='e'*32)['token'],'example','global')
        first = self.registry.create('First',[str(root)])['id']
        context = self.invoke(connection,'hub_context',workspace=str(root))
        self.assertEqual(context['connection']['project'],first)
        self.assertTrue(context['workspace']['available'])
        self.registry.create('Second',[str(root)])
        with self.assertRaises(BindingError) as failure:
            self.invoke(connection,'hub_context',workspace=str(root))
        self.assertEqual(failure.exception.code,'project_ambiguous')
        self.assertEqual(self.invoke(connection,'hub_context',project=first,workspace=str(root))['project'],first)
        with self.assertRaises(HubError) as failure:
            self.invoke(connection,'hub_memory',project=first,ref='source:proof.txt')
        self.assertEqual(failure.exception.body['error'],'workspace_required')
        outside = Path(self.temp.name)/'unregistered-code';outside.mkdir()
        with self.assertRaises(BindingError) as failure:
            self.invoke(connection,'hub_context',project=first,workspace=str(outside))
        self.assertEqual(failure.exception.code,'workspace_unregistered')

    def test_global_enrollment_rejects_project_setup_and_credential_metadata(self):
        invite = self.connections.invite(request_id='f'*32)
        for kwargs in (dict(name='Unexpected project'),dict(roots=[]),dict(workspace='/unregistered'),
                       dict(metadata={'apiKey':'must-not-be-stored'}),dict(model={'unknown':True})):
            with self.subTest(kwargs=kwargs),self.assertRaises(BindingError):
                self.connections.enroll(invite['token'],'example','global',**kwargs)
        self.assertEqual(self.connections.catalog()['bindings'],[])
        self.assertEqual(self.registry.list()['projects'],[])

    def test_upgrade_preserves_legacy_credentials_receipts_and_pending_invitation_scope(self):
        project = self.registry.create('Legacy project')['id']
        receipt = dict(binding='legacy-binding',project=project,client='legacy-client',token='LegacyPrivateCredential',
                       workspace=None,nativeIdentity='client-reported')
        proof = fingerprint(dict(client='legacy-client',externalId='legacy-external',workspace=None,name=None,roots=None))
        with self.registry.connect() as c:
            c.executescript('''CREATE TABLE agent_invitations(
                id TEXT PRIMARY KEY,project TEXT REFERENCES spaces(id),token_hash TEXT UNIQUE NOT NULL,
                expires REAL NOT NULL,request_hash TEXT,response TEXT,revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE agent_access(binding TEXT PRIMARY KEY REFERENCES client_bindings(id),
                token_hash TEXT UNIQUE NOT NULL,revoked INTEGER NOT NULL DEFAULT 0);''')
            c.execute('INSERT INTO client_bindings VALUES(?,?,?,?,?,?)',
                      (receipt['binding'],project,'legacy-client','legacy-external',json.dumps({'workspace':None}),1))
            c.execute('INSERT INTO agent_access VALUES(?,?,0)',(receipt['binding'],digest(receipt['token'])))
            c.execute('INSERT INTO agent_invitations VALUES(?,?,?,?,?,?,0)',
                      ('legacy-invite',project,digest('LegacyInvitation'),2000000000,proof,json.dumps(receipt)))
            c.execute('INSERT INTO agent_invitations VALUES(?,?,?,?,?,?,0)',
                      ('e'*32,None,digest('PendingLegacyInvitation'),2000000000,None,None))
            c.commit()
        self.assertEqual(self.connections.authenticate(receipt['token'])['id'],receipt['binding'])
        self.assertEqual(self.connections.catalog()['bindings'][0]['scope'],'project')
        new_invite = self.connections.invite(request_id='0'*32)
        self.assertEqual(new_invite['scope'],'global')
        self.assertEqual(self.connections.enroll('LegacyInvitation','legacy-client','legacy-external'),receipt)
        context = self.invoke(receipt,'hub_context')
        self.assertEqual(context['connection']['actor'],actor_id('legacy-binding','conversation'))
        with self.registry.connect() as c:
            scopes = {row['id']:row['scope'] for row in c.execute('SELECT id,scope FROM agent_invitations')}
        self.assertEqual(scopes['legacy-invite'],'project')
        self.assertEqual(scopes['e'*32],'new-project')
        created = self.connections.enroll('PendingLegacyInvitation','legacy-client','legacy-new',name='Legacy new project')
        self.assertNotEqual(created['project'],project)


if __name__=='__main__':
    unittest.main()
