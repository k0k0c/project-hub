"""Notice envelope/cursor and work signals on disposable HTTP Hub storage."""
import json
import threading
import time
from test_manual_editing import ManualApiCase
from hub_http import Client
from hub_instructions import Instructions


class NoticeHttpTest(ManualApiCase):
    def setUp(self):
        super().setUp()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        self.root=self.registry.base_store(self.pid).root
        self.a=Client(self.url);self.b=Client(self.url)
        self.task_id=self.task()
        self.stage_id=self.stage(self.task_id)
        self.a.call(self.root,'notice-a','hub_context',{})
        self.b.call(self.root,'notice-b','hub_context',{})

    def begin(self,client,session,scope='src'):
        return client.call(self.root,session,'hub_begin',dict(task=self.task_id,stage=self.stage_id,
            title='Own work '+session,resources=[scope]))

    def test_registered_work_delivers_facts_once_and_status_cycle_requeues(self):
        self.begin(self.a,'notice-a')
        foreign=self.begin(self.b,'notice-b')
        first=self.a.call(self.root,'notice-a','hub_context',{})['parallelNotices']
        self.assertEqual(first['notices'][0]['work'],foreign['work'])
        self.assertFalse(first['notices'][0]['runningVerified'])
        cursor=first['cursor']
        second=self.a.call(self.root,'notice-a','hub_context',{})['parallelNotices']
        self.assertEqual(second['notices'],[])
        self.assertEqual(second['cursor'],cursor)
        for status in ('waiting','active','done'):
            foreign=self.b.call(self.root,'notice-b','hub_report',dict(work=foreign['work'],
                revision=foreign['revision'],result='Factual '+status,status=status))
            current=self.a.call(self.root,'notice-a','hub_context',{})['parallelNotices']
            self.assertEqual(current['notices'][0]['status'],status)
            self.assertGreater(current['cursor'],cursor)
            cursor=current['cursor']
        replay=self.a.call(self.root,'notice-a','hub_notice',dict(after=0,seconds=0))
        self.assertTrue(replay['notices'])

    def test_wait_does_not_hold_ownership_barrier_and_uploads_no_user_rules(self):
        instruction=Instructions(self.registry.home)
        first=instruction.initialize()
        instruction.update(first['revision'],dict(userInstructions='PRIVATE-USER-RULE-TEXT'))
        own=self.begin(self.a,'notice-a')
        output=[]
        waiter=threading.Thread(target=lambda:output.append(self.a.call(self.root,'notice-a',
            'hub_notice',dict(after=0,seconds=3))))
        waiter.start()
        time.sleep(.1)
        started=time.monotonic()
        self.begin(self.b,'notice-b')
        self.assertLess(time.monotonic()-started,2.5)
        waiter.join(4)
        self.assertFalse(waiter.is_alive())
        self.assertTrue(output[0]['notices'])
        context=self.a.call(self.root,'notice-a','hub_context',{})
        self.assertNotIn('PRIVATE-USER-RULE-TEXT',json.dumps([own,output,context]))

    def test_dependency_notice_uses_declared_task_link(self):
        other=self.task('Dependency')
        stage=self.stage(other)
        self.mutate('tasks/link',{'task':self.task_id,'target':other,'type':'blocked-by'})
        self.begin(self.a,'notice-a','one-file')
        foreign=self.b.call(self.root,'notice-b','hub_begin',dict(task=other,stage=stage,
            title='Dependency work',resources=['other-file']))
        result=self.a.call(self.root,'notice-a','hub_notice',dict(after=0,seconds=0))
        self.assertEqual(result['notices'][0]['reason'],'task_dependency')
        self.assertEqual(result['notices'][0]['work'],foreign['work'])
        self.assertEqual(result['coverage']['dependencyCoverage'],'declared')

    def test_dependency_notice_preserves_legacy_orphan_parent_history(self):
        other=self.task('Legacy dependency')
        stage=self.stage(other)
        self.mutate('tasks/link',{'task':self.task_id,'target':other,'type':'blocked-by'})
        self.begin(self.a,'notice-a','one-file')
        foreign=self.b.call(self.root,'notice-b','hub_begin',dict(task=other,stage=stage,
            title='Dependency work',resources=['other-file']))
        store=self.registry.base_store(self.pid)
        # Emulate existing legacy history, bypassing current write validation
        # only in this disposable fixture. Keep the referenced parent absent.
        events=[json.loads(line) for line in store.journal.read_text(encoding='utf-8').splitlines()]
        created=next(event for event in events
                     if event['kind']=='task.created' and event['taskId']==self.task_id)
        created['patch']['parentTask']='legacy-missing-parent'
        store.journal.write_text(''.join(json.dumps(event)+'\n' for event in events),encoding='utf-8')
        baseline=store.data/'project.json'
        before=(baseline.read_bytes(),store.journal.read_bytes())
        with self.assertRaisesRegex(ValueError,'Unknown task parent: legacy-missing-parent'):
            store.snapshot()
        result=self.a.call(self.root,'notice-a','hub_notice',dict(after=0,seconds=0))
        self.assertEqual(result['notices'][0]['reason'],'task_dependency')
        self.assertEqual(result['notices'][0]['work'],foreign['work'])
        self.assertEqual(result['coverage']['dependencyCoverage'],'declared')
        context=self.a.call(self.root,'notice-a','hub_context',{})
        self.assertNotIn('unavailable',context['parallelNotices'])
        self.assertEqual(context['parallelNotices']['coverage']['dependencyCoverage'],'declared')
        self.assertEqual((baseline.read_bytes(),store.journal.read_bytes()),before)
