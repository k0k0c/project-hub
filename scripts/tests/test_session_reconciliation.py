import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import unittest
import test_project_hub_bindings as bindings
from plugin_api import ServerHub, HubError, call
from task_transfer import transfer


class ReconciliationTest(unittest.TestCase):
    setUp=bindings.BindingsTest.setUp
    tearDown=bindings.BindingsTest.tearDown
    save_catalog=bindings.BindingsTest.save_catalog
    invoke=bindings.BindingsTest.invoke
    task=bindings.BindingsTest.task
    def assign(self, project):
        data=json.loads(self.catalog.read_text())
        data['thread-project-assignments']={'chat':{'projectKind':'local','projectId':project}}
        self.catalog.write_text(json.dumps(data))

    def events(self):
        with ServerHub(self.registry).connect() as c:
            return c.execute("SELECT project,body FROM events WHERE kind='session.project_changed'").fetchall()

    def test_chat_move_retains_reports_without_blocking_edits(self):
        self.assign('a')
        task=self.task(self.a,'chat')
        self.invoke(self.a,'chat','hub_plan',task=task,stage='step',title='Step',remaining=['Check'])
        work=self.invoke(self.a,'chat','hub_begin',task=task,stage='step',title='Original',resources=['src'])
        self.assign('b')
        context=self.invoke(self.a,'chat','hub_context')
        self.assertEqual(context['project'],self.ids['b'])
        self.assertEqual(context['taskLinks'][0]['currentTaskProjects'],[self.ids['a']])
        self.assertEqual(context['own'][0]['project'],self.ids['a'])
        with self.assertRaises(HubError) as caught:
            self.invoke(self.a,'chat','hub_begin',task=task,title='Wrong project',resources=['src'])
        self.assertEqual(caught.exception.body['error'],'task_project_mismatch')
        event=dict(session_id='chat',cwd=str(self.a),hook_event_name='PreToolUse',tool_name='Write',tool_input={'path':str(self.b/'src/file.py')})
        verdict=call(self.registry,dict(cwd=str(self.a),session='chat',tool='hook',arguments=event))
        self.assertEqual(verdict, {})
        other=self.task(self.a,'other')
        overlap=self.invoke(self.a,'other','hub_begin',task=other,title='Overlapping work',resources=['src'])
        self.assertEqual(overlap['warning'],'resource_overlap')
        self.assertEqual(overlap['conflicts'][0]['session'],'chat')
        with self.assertRaisesRegex(HubError,'original project'):
            self.invoke(self.a,'chat','hub_report',work=work['work'],revision=work['revision'],result='Continue',status='active')
        report=self.invoke(self.a,'chat','hub_report',work=work['work'],revision=work['revision'],result='Finished in original task',status='done')
        self.assertEqual(report['planSync'],'saved')
        old=self.registry.store(self.ids['a']).snapshot()
        self.assertIn('Finished in original task',json.dumps(old))
        self.assertFalse(self.registry.store(self.ids['b']).snapshot()['tasks'])
        self.assertEqual(len(self.events()),2)
        self.assertEqual(len(ServerHub(self.registry).overview(self.ids['a'])['projectChanges']),1)
        self.assertEqual(len(ServerHub(self.registry).overview(self.ids['b'])['projectChanges']),1)
        self.invoke(self.a,'chat','hub_context')
        self.assertEqual(len(self.events()),2)

    def test_task_and_chat_moves_in_either_order(self):
        for chat_first in (True,False):
            with self.subTest(chat_first=chat_first):
                self.assign('a')
                task=self.invoke(self.a,'chat','hub_task',title='Transfer '+str(chat_first),scope=['src'],acceptance=['Checked'])['task']
                work=self.invoke(self.a,'chat','hub_begin',task=task,title='Evidence',resources=['src'])
                self.invoke(self.a,'chat','hub_report',work=work['work'],revision=work['revision'],result='Saved',status='done')
                if chat_first:
                    self.assign('b');self.invoke(self.a,'chat','hub_context')
                preview=transfer(self.registry,self.ids['a'],self.ids['b'],task,preview=True)
                transfer(self.registry,self.ids['a'],self.ids['b'],task,preview['revision'],'move-'+task)
                ctx=self.invoke(self.a,'chat','hub_context')
                link=next(x for x in ctx['taskLinks'] if x['task']==task)
                self.assertEqual(link['currentTaskProjects'],[self.ids['b']])
                if not chat_first:self.assertEqual(ctx['project'],self.ids['a'])
                self.assign('b')
                self.assertEqual(self.invoke(self.a,'chat','hub_context')['project'],self.ids['b'])
                another=self.invoke(self.b,'new-chat','hub_begin',task=task,title='New participant',resources=['docs'])
                view=next(t for t in self.registry.store(self.ids['b']).snapshot()['tasks'] if t['id']==task)
                self.assertEqual(view['participatingSessions'],['chat','new-chat'])
                self.invoke(self.b,'new-chat','hub_report',work=another['work'],revision=another['revision'],result='Complete',status='done')
                self.assign('a')
                self.assertEqual(self.invoke(self.a,'chat','hub_context')['project'],self.ids['a'])

    def test_concurrent_observation_is_idempotent_and_metadata_outage_fails(self):
        self.assign('a');self.invoke(self.a,'chat','hub_context')
        self.assign('b')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.invoke(self.a,'chat','hub_context'),range(2)))
        self.assertEqual([r['project'] for r in results],[self.ids['b']]*2)
        self.assertEqual(len(self.events()),2)
        self.catalog.write_text('{broken')
        with self.assertRaises(HubError) as caught:self.invoke(self.a,'chat','hub_context')
        self.assertEqual(caught.exception.body['error'],'project_metadata_unavailable')

    def test_assignment_race_does_not_change_session(self):
        self.assign('a');self.invoke(self.a,'chat','hub_context')
        with patch.object(self.registry.catalog,'assigned_project',side_effect=['b','a']):
            with self.assertRaises(HubError) as caught:self.invoke(self.a,'chat','hub_context')
        self.assertEqual(caught.exception.body['error'],'project_metadata_changed')
        with ServerHub(self.registry).connect() as c:
            self.assertEqual(c.execute('SELECT project FROM sessions WHERE id=?',('chat',)).fetchone()[0],self.ids['a'])
        self.assertEqual(len(self.events()),0)
