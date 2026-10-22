"""Real transport contracts on disposable registry/catalog/data homes only."""
import json
import os
import sqlite3
import unittest
from unittest.mock import patch

import test_project_hub_plugin_api as api_fixture
from hub_core import HubError, hook_actor
from hub_plugin import Mcp
from plugin_api import ServerHub, call


class SubagentIntegrationTest(unittest.TestCase):
    setUp=api_fixture.PluginApiTest.setUp
    tearDown=api_fixture.PluginApiTest.tearDown

    def invoke(self, sid, tool, **args):
        return self.client.call(self.base/'a',sid,tool,args)

    def prepare_team(self):
        db=self.base/'state_5.sqlite'
        with sqlite3.connect(db) as c:
            c.execute('CREATE TABLE threads(id TEXT,name TEXT,cwd TEXT,updated_at INTEGER,archived INTEGER,source TEXT)')
            for sid in ('parent','one','two'):
                source='vscode' if sid=='parent' else json.dumps({'subagent':{'thread_spawn':{
                    'parent_thread_id':'parent','depth':1,'agent_path':'/root/'+sid}}})
                c.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',(sid,sid,str(self.base/'a'),1,0,source))
        c.close()
        for sid in ('parent','one','two'):self.invoke(sid,'hub_context')
        task=self.invoke('parent','hub_task',title='Team integration',scope=['Coordination'],acceptance=['Independent agents'])['task']
        self.invoke('parent','hub_plan',task=task,stage='test',title='Team test',remaining=['Verify'])
        return task

    def hook(self, agent, path, kind='PreToolUse'):
        raw=dict(session_id='parent',agent_id=agent,cwd=str(self.base/'a'),hook_event_name=kind,
                 tool_name='apply_patch',tool_input={'patch':'*** Update File: '+path+'\n+private-text'})
        return self.client.hook(raw)

    def test_child_edits_are_independent_of_claims_and_actor_is_preserved_for_observations(self):
        task=self.prepare_team()
        for sid,path in [('parent','root.py'),('one','one.py'),('two','two.py')]:
            self.invoke(sid,'hub_begin',task=task,stage='test',title=sid,resources=[path])
        self.assertNotEqual(self.hook('one','one.py').get('hookSpecificOutput',{}).get('permissionDecision'),'deny')
        for path in ('root.py','two.py','unclaimed.py'):
            self.assertEqual(self.hook('one',path), {})
        self.hook('one', 'one.py', kind='UserPromptSubmit')
        with ServerHub(self.registry).connect() as c:
            row=c.execute("SELECT session,body FROM events WHERE kind='UserPromptSubmit' ORDER BY seq DESC LIMIT 1").fetchone()
            self.assertEqual(row['session'],'one')
            self.assertEqual(json.loads(row['body'])['origin_session_id'],'parent')
            self.assertNotIn('private-text',row['body'])

    def test_conflict_details_and_saved_result_reused_by_sibling(self):
        task=self.prepare_team()
        one=self.invoke('one','hub_begin',task=task,stage='test',title='Identity result',resources=['one.py'])
        overlap=self.invoke('two','hub_begin',task=task,stage='test',title='Conflicting work',resources=['one.py'])
        self.assertEqual(overlap['warning'],'resource_overlap')
        self.assertEqual(overlap['conflicts'][0]['session'],'one')
        self.assertEqual(overlap['conflicts'][0]['id'],one['work'])
        with self.assertRaises(HubError) as denied:
            self.invoke('parent','hub_report',work=one['work'],revision=one['revision'],result='Not owner',status='done')
        self.assertEqual(denied.exception.body['error'],'not_owner')
        self.invoke('one','hub_report',work=one['work'],revision=one['revision'],result='REUSE-IDENTITY verified',status='done')
        memory=self.invoke('two','hub_memory',task=task,query='REUSE-IDENTITY')
        self.assertTrue(memory['results'])
        context=self.invoke('two','hub_context',limit=1)
        self.assertEqual(context['team']['actor']['parentSession'],'parent')
        self.assertTrue(any(w['id']==one['work'] and w['result']=='REUSE-IDENTITY verified' for w in context['team']['work']))
        self.assertNotIn('stages',context['tasks'][0])
        self.invoke('two','hub_begin',task=task,stage='test',title='Reuse after release',resources=['one.py'])

    def test_parent_stop_preserves_child_claims_and_relation_survives_catalog_loss(self):
        task=self.prepare_team()
        own=self.invoke('one','hub_begin',task=task,stage='test',title='Child work',resources=['one.py'])
        self.client.hook(dict(session_id='parent',cwd=str(self.base/'a'),hook_event_name='Stop'))
        self.assertNotEqual(self.hook('one','one.py').get('hookSpecificOutput',{}).get('permissionDecision'),'deny')
        (self.base/'state_5.sqlite').unlink()
        context=self.invoke('one','hub_context')
        self.assertEqual(context['team']['actor']['parentSession'],'parent')
        self.assertEqual(context['own'][0]['id'],own['work'])
        self.assertEqual(context['own'][0]['resources'],[dict(name='one.py',mode='write')])

    def test_mcp_prefers_own_host_thread_and_rejects_parent_rebind(self):
        with patch.dict(os.environ,{'CODEX_THREAD_ID':'own','CODEX_SESSION_ID':'parent'},clear=True):
            mcp=Mcp(None,str(self.base/'a'),client=self.client)
            self.assertEqual(mcp.call('hub_context',{})['session'],'own')
            with self.assertRaises(HubError) as caught:mcp.call('hub_context',{'session':'parent'})
            self.assertEqual(caught.exception.body['error'],'session_mismatch')
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaises(HubError) as caught:Mcp(None,client=self.client).call('hub_context',{})
            self.assertEqual(caught.exception.body['error'],'identity_missing')

    def test_large_team_keeps_actor_parent_and_signals_truncation(self):
        task=self.prepare_team()
        with sqlite3.connect(self.base/'state_5.sqlite') as c:
            for n in range(16):
                sid='sibling-'+str(n)
                source=json.dumps({'subagent':{'thread_spawn':{'parent_thread_id':'parent','depth':1}}})
                c.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',(sid,sid,str(self.base/'a'),n+2,0,source))
        c.close()
        for n in range(16):self.invoke('sibling-'+str(n),'hub_context')
        own=self.invoke('one','hub_begin',task=task,stage='test',title='Actor work',resources=['actor.py'])
        team=self.invoke('one','hub_context')['team']
        self.assertEqual([m['id'] for m in team['members'][:2]],['one','parent'])
        self.assertLessEqual(len(team['members']),12)
        self.assertTrue(team['more'])
        self.assertTrue(any(w['id']==own['work'] for w in team['work']))

    def test_nested_agent_uses_immediate_parent_without_inheriting_claims(self):
        task=self.prepare_team()
        with sqlite3.connect(self.base/'state_5.sqlite') as c:
            source=json.dumps({'subagent':{'thread_spawn':{'parent_thread_id':'one','depth':2}}})
            c.execute('INSERT INTO threads VALUES(?,?,?,?,?,?)',('grandchild','grandchild',str(self.base/'a'),2,0,source))
        c.close()
        context=self.invoke('grandchild','hub_context')
        self.assertEqual(context['team']['actor']['parentSession'],'one')
        self.invoke('one','hub_begin',task=task,stage='test',title='Immediate parent work',resources=['parent-owned.py'])
        self.invoke('grandchild','hub_begin',task=task,stage='test',title='Nested work',resources=['nested.py'])
        self.assertEqual(self.hook('grandchild','parent-owned.py'), {})
        self.assertNotEqual(self.hook('grandchild','nested.py').get('hookSpecificOutput',{}).get('permissionDecision'),'deny')

    def test_malformed_agent_id_cannot_fall_back_to_parent(self):
        for value in ('',False,{},'x'*151):
            with self.assertRaises(HubError):hook_actor(dict(session_id='parent',agent_id=value))
        self.assertEqual(hook_actor(dict(session_id='parent'))['session_id'],'parent')

    def test_old_client_tool_hook_skips_registry_and_barriers(self):
        with patch('plugin_api.barrier', side_effect=AssertionError('Must not wait for ownership')):
            result=call(None, dict(tool='hook', arguments=dict(
                hook_event_name='PreToolUse', agent_id=False,
                tool_name='apply_patch', tool_input={'patch':'*** Update File: missing.py'})))
        self.assertEqual(result, {})


if __name__=='__main__':unittest.main()
