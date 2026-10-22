"""Fixed action scopes and explicit review application use disposable Hub stores."""
import http.client
import json
import os
import time
from unittest.mock import patch

from test_manual_editing import ManualApiCase
from test_hub_chat_actions import FakeAdapter
from hub_chat_actions import ChatActions, ChatActionError
from hub_project_review import basis, summary_from, page, publish_review, publish_estimates, apply_review, read_scope
from plugin_api import ServerHub
from hub_plugin import Mcp


class ProjectReviewTest(ManualApiCase):
    def setUp(self):
        super().setUp()
        self.adapter=FakeAdapter('owned-review')
        self.service=ChatActions(self.registry,lambda:self.adapter,
            portal_url='http://127.0.0.1:'+str(self.server.server_port))
        self.server.chat_actions=self.service
        self.env=patch.dict(os.environ,{'PROJECT_HUB_CODEX_ADAPTER':'stdio'});self.env.start();self.addCleanup(self.env.stop)

    def start(self, task=None, stage=None, intent='review', mode='default', identity='review-action'):
        target='stage' if stage else 'task' if task else 'project'
        return self.service.start(self.pid,task,identity,stage=stage,target=target,mode=mode,intent=intent,
                                  expected=self.state()['revision'])

    def own(self, task, stage=None, phase='review', mode='read'):
        hub=ServerHub(self.registry);root=self.registry.store(self.pid).root
        mcp=Mcp(hub,cwd=root,session='owned-review');mcp.call('hub_context',{})
        return hub, mcp.call('hub_begin',dict(task=task,stage=stage,phase=phase,mode=mode,resources=['resource:review'],title='Review'))

    def task_row(self,task):
        return next(t for t in self.state()['tasks'] if t['id']==task)

    def proposal(self,task,stage=None,decision='current',**fields):
        response=self.service.recent(self.pid,'__project_review__')[0]
        return dict(task=task,stage=stage,decision=decision,reason='Reviewed requirements',confidence='low; explicit evidence',
                    evidence=[response['scopeRef']],expectedState=basis(self.task_row(task),stage),**fields)

    def test_fixed_scope_plan_revision_idempotency_and_one_native_turn(self):
        task=self.task();done=self.stage(task,id='done',status='done');todo=self.stage(task,id='todo');cancel=self.stage(task,id='cancelled',status='cancelled')
        expected=self.state()['revision']
        first=self.service.start(self.pid,task,'fixed',target='task',mode='plan',expected=expected)
        self.assertEqual(first['status'],'accepted');self.assertEqual(self.adapter.native_options,{'collaboration_mode':'plan'})
        frozen=read_scope(self.registry,self.pid,first['scopeRef'],'fixed')
        self.assertEqual(frozen['scope']['tasks'],[dict(task=task,stages=[todo,cancel])])
        self.mutate('tasks/update',dict(task=task,patch={'summary':'changed'}))
        second=self.service.start(self.pid,task,'fixed',target='task',mode='plan',expected=expected);self.assertEqual({k:second.get(k) for k in ('actionId','threadId','turnId','digest')},{k:first.get(k) for k in ('actionId','threadId','turnId','digest')});self.assertEqual(self.adapter.turn_count,1)
        self.assertEqual(self.adapter.turn_count,1)
        with self.assertRaises(ChatActionError):
            self.service.start(self.pid,task,'stale',target='task',mode='default',expected=expected)
        self.assertEqual(self.adapter.turn_count,1)
        prompt=self.adapter.calls[-1][2];self.assertLessEqual(len(prompt.encode()),12000)
        self.assertNotIn('Current task context',prompt)

    def test_project_marker_all_unfinished_paging_unique_chats_and_unknown_estimates(self):
        state=dict(project={'id':'p'},revision='r',tasks=[])
        for i in range(120):
            state['tasks'].append(dict(id='t'+str(i),title='Требование '+('я'*160),status='queued',stages=[],
                agentActivity={'state':'active'},agentSessions={'active':['same'],'waiting':[],'unknown':[]},
                estimate={'hoursLow':1,'hoursHigh':2} if i==0 else None))
        summary=summary_from(state);self.assertEqual(summary['activity']['activeChats'],1)
        self.assertEqual(summary['estimate']['unknownGroups'],119)
        ids=[];offset=0
        while offset is not None:
            result=page(summary,offset);self.assertLessEqual(len(__import__('hub_project_review').encoded(result)),12000)
            ids.extend(r['id'] for r in result['rows']);offset=result['next']
        self.assertEqual(len(ids),120);self.assertEqual(len(set(ids)),120)
        task=self.task();self.start()
        self.assertEqual(self.service.recent(self.pid,'__project_review__')[0]['task'],None)
        self.assertEqual(self.service.recent(self.pid,task),[])

    def test_retained_resume_sends_delta_and_preserves_full_immutable_scope(self):
        task=self.task();stage=self.stage(task,id='one',remaining=['Original requirement'])
        first=self.start(task=task,identity='initial')
        def finish():
            self.adapter.results.put({'status':'completed'})
            deadline=time.monotonic()+3
            while self.service._runtimes['owned-review']['status']!='completed' and time.monotonic()<deadline:
                time.sleep(.01)
            self.assertEqual(self.service._runtimes['owned-review']['status'],'completed')
        finish()
        second=self.service.start(self.pid,task,'unchanged',thread_id='owned-review',target='task',mode='default',
            intent='review',expected=self.state()['revision'])
        context=json.loads(self.adapter.calls[-1][2].split('Current fixed context (JSON):\n')[1])
        self.assertEqual(context['rows'],[]);self.assertTrue(context['delta']['complete'])
        self.assertEqual(context['delta']['previousScopeRef'],first['scopeRef'])
        finish()
        self.mutate('stages/update',dict(task=task,stage=stage,patch={'remaining':['Changed requirement']}))
        third=self.service.start(self.pid,task,'changed',thread_id='owned-review',target='task',mode='default',
            intent='review',expected=self.state()['revision'])
        context=json.loads(self.adapter.calls[-1][2].split('Current fixed context (JSON):\n')[1])
        self.assertEqual(context['delta']['changedTaskCount'],1)
        self.assertEqual(context['rows'][0]['stages'][0]['id'],stage)
        frozen=read_scope(self.registry,self.pid,third['scopeRef'],'changed')
        self.assertEqual(frozen['scope']['tasks'],[dict(task=task,stages=[stage])])
        self.assertIn('Changed requirement',frozen['rows'][0]['remaining'][0]['text'])
        self.assertLessEqual(len(self.adapter.calls[-1][2].encode()),12000)

    def test_read_review_does_not_activate_plan_and_proposals_require_user_apply(self):
        task=self.task();stage=self.stage(task,id='reviewed',remaining=['Requirement'])
        action=self.start();hub,work=self.own(task,stage)
        self.assertEqual(self.task_row(task)['stages'][0]['status'],'planned')
        proposal=self.proposal(task,decision='current')
        before=self.task_row(task)['status']
        result=publish_review(self.registry,self.pid,'owned-review',action['actionId'],work['work'],self.state()['revision'],[proposal])
        self.assertEqual(self.task_row(task)['status'],before)
        replay=publish_review(self.registry,self.pid,'owned-review',action['actionId'],work['work'],result.get('reviewedRevision',
            __import__('hub_project_review').read_review(self.registry,self.pid,result['source']['path'])['reviewedRevision']),[proposal])
        self.assertTrue(replay['replayed'])
        Mcp(hub,cwd=self.registry.store(self.pid).root,session='owned-review').call('hub_report',dict(
            work=work['work'],revision=work['revision'],result='Review published for user selection',status='done'))
        self.assertEqual(self.task_row(task)['stages'][0]['done'],[])
        applied=apply_review(self.registry,self.pid,result['source']['path'],[result['proposals'][0]['id']],self.state()['revision'])
        self.assertEqual(applied['status'],'applied');revision=self.state()['revision']
        self.assertTrue(apply_review(self.registry,self.pid,result['source']['path'],applied['applied'],'old')['replay'])
        self.assertEqual(self.state()['revision'],revision)

    def test_duplicate_preserves_requirements_sources_and_existing_stage(self):
        task=self.task();stage=self.stage(task,id='source',remaining=['Keep requirement'])
        destination=self.task('Replacement');dest=self.stage(destination,id='existing',remaining=['Prior requirement'])
        action=self.start();hub,work=self.own(task,stage)
        proposal=self.proposal(task,decision='duplicate',requirements=['Keep requirement'],
            replacement=dict(task=destination,stage=dest,expectedState=basis(self.task_row(destination),dest)))
        result=publish_review(self.registry,self.pid,'owned-review',action['actionId'],work['work'],self.state()['revision'],[proposal])
        selected=[result['proposals'][0]['id']]
        applied=apply_review(self.registry,self.pid,result['source']['path'],selected,self.state()['revision'])
        self.assertEqual(applied['status'],'applied',applied)
        self.assertEqual(self.task_row(task)['status'],'cancelled')
        target=self.task_row(destination);self.assertEqual([s['id'] for s in target['stages']],[dest])
        self.assertEqual(target['stages'][0]['remaining'],['Prior requirement','Keep requirement'])
        self.assertTrue(any(s['path']==result['source']['path'] for s in target['stages'][0]['evidence']))

    def test_priority_requires_explicit_apply_and_fresh_basis_and_respects_writer(self):
        task=self.task();stage=self.stage(task,id='one',remaining=['Requirement'])
        self.mutate('tasks/update',dict(task=task,patch={'status':'active'}))
        self.mutate('stages/update',dict(task=task,stage=stage,patch={'status':'active'}))
        action=self.start();hub,work=self.own(task,stage)
        original=self.task_row(task).get('priority')
        for priority in ([], 'unsupported'):
            with self.assertRaises(ValueError):
                publish_review(self.registry,self.pid,'owned-review',action['actionId'],work['work'],
                    self.state()['revision'],[self.proposal(task,priority=priority)])
        proposal=self.proposal(task,priority='critical')
        result=publish_review(self.registry,self.pid,'owned-review',action['actionId'],work['work'],self.state()['revision'],[proposal])
        self.assertEqual(self.task_row(task).get('priority'),original)
        root=self.registry.store(self.pid).root
        hub.ensure_session('writer',root)
        writer=hub.begin('writer',task,'Implementation',['resource:implementation'],stage=stage)
        with self.assertRaisesRegex(ValueError,'Implementation work remains open'):
            apply_review(self.registry,self.pid,result['source']['path'],[result['proposals'][0]['id']],self.state()['revision'])
        Mcp(hub,cwd=root,session='writer').call('hub_report',dict(work=writer['work'],revision=writer['revision'],
            result='Verification work released',status='done'))
        # A work result changes the reviewed requirements. Priority must be
        # reconsidered against that new semantic state, even at a fresh revision.
        with self.assertRaisesRegex(ValueError,'Reviewed target changed'):
            apply_review(self.registry,self.pid,result['source']['path'],[result['proposals'][0]['id']],self.state()['revision'])
        self.adapter.results.put({'status':'completed'})
        deadline=time.monotonic()+3
        while self.service._runtimes['owned-review']['status']!='completed' and time.monotonic()<deadline:time.sleep(.01)
        new=self.service.start(self.pid,None,'priority-refresh',thread_id='owned-review',target='project',mode='default',
            intent='review',expected=self.state()['revision'])
        fresh=publish_review(self.registry,self.pid,'owned-review','priority-refresh',work['work'],self.state()['revision'],[
            dict(self.proposal(task,priority='critical'),expectedState=basis(self.task_row(task)))])
        selected=[fresh['proposals'][0]['id']]
        applied=apply_review(self.registry,self.pid,fresh['source']['path'],selected,self.state()['revision'])
        self.assertEqual(applied['status'],'applied');self.assertEqual(self.task_row(task)['priority'],'critical')
        revision=self.state()['revision']
        self.assertTrue(apply_review(self.registry,self.pid,fresh['source']['path'],selected,'old')['replay'])
        self.assertEqual(self.state()['revision'],revision)

    def test_stage_scope_rejects_task_proposal_malformed_criteria_and_mutable_completion_evidence(self):
        task=self.task();stage=self.stage(task,id='one',remaining=['Acceptance'])
        action=self.start(task,stage);hub,work=self.own(task,stage)
        response=self.service.recent(self.pid,task)[0]
        proposal=dict(task=task,stage=None,decision='current',reason='Read',confidence='low',evidence=[response['scopeRef']],expectedState=basis(self.task_row(task)))
        with self.assertRaises(ValueError):publish_review(self.registry,self.pid,'owned-review',action['actionId'],work['work'],self.state()['revision'],[proposal])
        proposal.update(stage=stage,decision='done',expectedState=basis(self.task_row(task),stage),criteria=[dict(requirement={},evidence=response['scopeRef'])])
        with self.assertRaises(ValueError):publish_review(self.registry,self.pid,'owned-review',action['actionId'],work['work'],self.state()['revision'],[proposal])
        proposal.update(criteria=[dict(requirement='Acceptance',evidence='proof.txt')],evidence=['proof.txt'])
        with self.assertRaises(ValueError):publish_review(self.registry,self.pid,'owned-review',action['actionId'],work['work'],self.state()['revision'],[proposal])

    def test_explicit_estimate_only_metadata_revision_and_read_claim_guard(self):
        task=self.task();stage=self.stage(task,id='one',remaining=['Check'])
        action=self.start(task,stage,intent='estimate');hub,work=self.own(task,stage)
        values=[dict(task=task,stage=stage,expectedState=basis(self.task_row(task),stage),
            estimate=dict(hoursLow=1,hoursHigh=3,confidence='low',note='Active agent time; waits excluded'))]
        expected=self.state()['revision']
        result=publish_estimates(self.registry,self.pid,'owned-review',action['actionId'],work['work'],expected,values)
        self.assertEqual(result['status'],'published');row=self.task_row(task)
        self.assertNotIn('estimate',row);self.assertEqual(row['stages'][0]['estimate']['hoursHigh'],3)
        self.assertEqual(row['stages'][0]['status'],'planned');self.assertEqual(row['stages'][0]['remaining'],['Check'])
        self.assertTrue(publish_estimates(self.registry,self.pid,'owned-review',action['actionId'],work['work'],expected,values)['replayed'])
        with self.assertRaises(ValueError):publish_estimates(self.registry,self.pid,'foreign',action['actionId'],work['work'],result['revision'],values)

    def test_static_history_assets_and_removed_task_review_apply_route(self):
        for path in ('/chat-actions.js','/chat-actions.css'):
            connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
            connection.request('GET',path+'?project='+self.pid);response=connection.getresponse()
            self.assertEqual(response.status,200);self.assertTrue(response.read());connection.close()
        status,error=self.request('/api/v1/review-apply',dict(ref='missing',selected=[],expected=self.state()['revision']))
        self.assertEqual(status,410,error)
        self.assertEqual(error['code'],'task_execution_removed')

    def test_owned_native_question_answer_does_not_handle_approval_or_store_answer(self):
        task=self.task();stage=self.stage(task,id='one');action=self.start(task,stage)
        question=dict(id='question-1',method='item/tool/requestUserInput',params=dict(threadId='owned-review',turnId='turn-1',
            questions=[dict(id='choice',header='Choice',question='Choose next step',isSecret=False,
                            options=[dict(label='Continue',description='Proceed')])]))
        self.adapter.results.put(dict(status='needs-attention',request=question))
        for _ in range(100):
            row=self.service.recent(self.pid,task)[0]
            if row['status']=='needs_attention':break
            time.sleep(.01)
        self.assertEqual(row['attention']['requestId'],'question-1')
        replies=[]
        def reply(identity,answers):
            if not isinstance(answers,dict) or set(answers)!={'choice'}:raise ValueError('wrong')
            replies.append((identity,answers))
        self.adapter.respond_user_input=reply
        with self.assertRaises(ChatActionError) as caught:self.service.answer(self.pid,action['actionId'],'question-1',{})
        self.assertEqual(caught.exception.code,'invalid_answer')
        answered=self.service.answer(self.pid,action['actionId'],'question-1',{'choice':['Private answer']})
        self.assertEqual(answered['status'],'accepted');self.assertIsNone(answered['attention'])
        self.assertNotIn('Private answer',json.dumps(self.service.recent(self.pid,task)))
        with self.assertRaises(ChatActionError):self.service.answer(self.pid,action['actionId'],'question-1',{'choice':['again']})
        self.assertEqual(len(replies),1)
        self.assertIsNone(ChatActions._question(dict(question,id=None),'owned-review','turn-1'))
        self.assertIsNone(ChatActions._question(dict(question,method='item/commandExecution/requestApproval'),'owned-review','turn-1'))

    def test_completion_proves_all_requirements_and_defers_to_open_write_owner(self):
        task=self.task();stage=self.stage(task,id='one',remaining=['Acceptance'])
        self.mutate('stages/update',dict(task=task,stage=stage,patch={'status':'active'}))
        self.mutate('tasks/update',dict(task=task,patch={'status':'active'}))
        action=self.start();hub,work=self.own(task,stage)
        ref=action['scopeRef']
        proposal=self.proposal(task,stage,decision='done',criteria=[dict(requirement='Acceptance',evidence=ref)])
        result=publish_review(self.registry,self.pid,'owned-review',action['actionId'],work['work'],self.state()['revision'],[proposal])
        root=self.registry.store(self.pid).root
        other=Mcp(ServerHub(self.registry),cwd=root,session='implementation-owner');other.call('hub_context',{})
        active=other.call('hub_begin',dict(task=task,stage=stage,phase='implementation',resources=['proof.txt'],title='Implementation'))
        # Activation changes the semantic basis; either changed target or open
        # write ownership must refuse every selected decision before mutation.
        with self.assertRaises(ValueError):apply_review(self.registry,self.pid,result['source']['path'],[result['proposals'][0]['id']],self.state()['revision'])
        self.assertNotEqual(self.task_row(task)['stages'][0]['status'],'done')

    def test_task_or_stage_selection_is_nonoverlapping_and_foreign_chat_cannot_publish(self):
        task=self.task();stage=self.stage(task,id='one',remaining=['Requirement'])
        action=self.start();hub,work=self.own(task,stage)
        before=self.state()['revision']
        with self.assertRaises(ValueError):publish_review(self.registry,self.pid,'foreign',action['actionId'],work['work'],before,[self.proposal(task)])
        with self.assertRaises(ValueError):publish_review(self.registry,self.pid,'owned-review',action['actionId'],work['work'],before,[self.proposal(task),self.proposal(task,stage)])
        self.assertEqual(self.state()['revision'],before)

    def test_service_intent_blocks_generic_business_writes_and_write_claims(self):
        task=self.task();stage=self.stage(task,id='one');self.start(task,stage)
        root=self.registry.store(self.pid).root
        mcp=Mcp(ServerHub(self.registry),cwd=root,session='owned-review');mcp.call('hub_context',{})
        from hub_core import HubError
        for name,args in [('hub_task_update',dict(task=task,expected=self.state()['revision'],patch={'summary':'Changed'})),
            ('hub_begin',dict(task=task,stage=stage,title='Illegal implementation',phase='implementation',resources=['proof.txt'])),
            ('hub_plan',dict(task=task,stage='new',title='New stage',remaining=['Scope'],expected=self.state()['revision']))]:
            with self.assertRaises(HubError) as caught:mcp.call(name,args)
            self.assertEqual(caught.exception.body['error'],'service_read_only')
        self.assertEqual(len(self.task_row(task)['stages']),1)
