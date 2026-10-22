import time
import unittest
from unittest.mock import patch

import test_project_hub_plugin_api as fixtures
from plugin_api import ServerHub


class StageActivationTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PluginApiTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.call = self.fixture.invoke

    @property
    def registry(self):
        return self.fixture.registry

    def planned_stage(self, title='Activation'):
        task = self.call('a', 'hub_task', title=title, scope=['src'], acceptance=['Verified'])['task']
        plan = self.call('a', 'hub_plan', task=task, stage='work', title='Work', remaining=['Verify'])
        self.call('a', 'hub_task_update', task=task, expected=plan['revision'],
                  patch={'status': 'planned'})
        return task

    def plan(self, task):
        return self.call('a', 'hub_plan', task=task)

    def stage(self, task):
        return next(stage for stage in self.plan(task)['task']['stages'] if stage['id'] == 'work')

    def coordination(self):
        return ServerHub(self.registry).connect()

    def begin_pending(self, title):
        task = self.planned_stage(title)
        with patch('hub_memory.Memory.deliver_activation', side_effect=OSError('delivery unavailable')):
            result = self.call('a', 'hub_begin', task=task, stage='work', title='Implement', resources=['src'])
        self.assertEqual(result['status'], 'active')
        self.assertEqual(result['planSync'], 'pending')
        return task, result

    def test_begin_promotes_planned_task_and_stage_with_active_badges(self):
        task = self.planned_stage()
        result = self.call('a', 'hub_begin', task=task, stage='work', title='Implement', resources=['src'])
        self.assertEqual(result['status'], 'active')
        current = self.plan(task)['task']
        self.assertEqual(current['status'], 'active')
        self.assertEqual(current['agentActivity']['state'], 'active')
        self.assertEqual(self.stage(task)['status'], 'active')
        self.assertEqual(self.stage(task)['agentActivity']['state'], 'active')

    def test_begin_retry_is_exact_and_does_not_duplicate_activation(self):
        task = self.planned_stage('Retry activation')
        args = dict(task=task, stage='work', title='Implement', resources=['src'])
        first = self.call('a', 'hub_begin', **args)
        store = self.registry.store(self.fixture.ids['a'])
        before = store.snapshot()
        second = self.call('a', 'hub_begin', **args)
        after = store.snapshot()
        self.assertEqual(second, first)
        self.assertEqual(after['revision'], before['revision'])
        self.assertEqual(len(after['allEvents']), len(before['allEvents']))

    def test_active_report_reactivates_a_manually_reset_planned_task(self):
        task = self.planned_stage('Active report')
        work = self.call('a', 'hub_begin', task=task, stage='work', title='Implement', resources=['src'])
        plan = self.plan(task)
        self.call('a', 'hub_task_update', task=task, expected=plan['revision'], patch={'status': 'planned'})
        plan = self.plan(task)
        self.call('a', 'hub_plan', task=task, stage='work', title='Work', status='planned', expected=plan['revision'])
        self.call('a', 'hub_report', work=work['work'], revision=work['revision'], result='Still working', status='active')
        self.assertEqual(self.plan(task)['task']['status'], 'active')
        self.assertEqual(self.stage(task)['status'], 'active')

    def test_terminal_stage_status_drops_pending_activation(self):
        for status in ('done', 'cancelled', 'blocked'):
            with self.subTest(status=status):
                task, _ = self.begin_pending('Terminal stage ' + status)
                store = self.registry.store(self.fixture.ids['a'])
                state = store.snapshot()
                store.record(dict(id='stage-' + status, taskId=task, stageId='work', kind='stage.updated',
                                  title='Terminal stage', patch={'status': status}), expected_revision=state['revision'])
                self.call('a', 'hub_plan', task=task)
                self.assertEqual(self.plan(task)['task']['status'], 'planned')
                self.assertEqual(self.stage(task)['status'], status)

    def test_closed_or_waiting_work_drops_pending_activation(self):
        for work_status in ('waiting', 'done', 'cancelled'):
            with self.subTest(work_status=work_status):
                task, work = self.begin_pending('Closed work ' + work_status)
                with self.coordination() as connection:
                    connection.execute('UPDATE work SET status=? WHERE id=?', (work_status, work['work']))
                self.call('a', 'hub_plan', task=task)
                self.assertEqual(self.plan(task)['task']['status'], 'planned')
                self.assertEqual(self.stage(task)['status'], 'planned')

    def test_stale_or_unknown_active_session_drops_pending_activation(self):
        for update in ({'state': 'unknown'}, {'seen': time.time() - 901}):
            with self.subTest(update=update):
                clause = next(iter(update))
                task, _ = self.begin_pending('Invalid session '+clause)
                with self.coordination() as connection:
                    connection.execute('UPDATE sessions SET ' + clause + '=? WHERE id=?', (update[clause], 'session-a'))
                self.call('a', 'hub_plan', task=task)
                self.assertEqual(self.plan(task)['task']['status'], 'planned')
                self.assertEqual(self.stage(task)['status'], 'planned')

    def test_terminal_task_and_superseded_work_signal_do_not_reopen(self):
        for status in ('done', 'cancelled'):
            with self.subTest(status=status):
                task, _ = self.begin_pending('Terminal task '+status)
                store = self.registry.store(self.fixture.ids['a'])
                store.record(dict(taskId=task, kind='task.updated', title='Close task',
                                  patch={'status': status}), expected_revision=store.snapshot()['revision'])
                self.assertEqual(self.plan(task)['task']['status'], status)
                self.assertEqual(self.stage(task)['status'], 'planned')
        task, work = self.begin_pending('Superseded signal')
        with self.coordination() as connection:
            connection.execute('UPDATE work SET revision=revision+1 WHERE id=?', (work['work'],))
        self.assertEqual(self.plan(task)['task']['status'], 'planned')
        self.assertEqual(self.stage(task)['status'], 'planned')

    def test_session_only_hook_cannot_promote_an_existing_linked_stage(self):
        task = self.planned_stage('Session-only linked work')
        self.call('a', 'hub_begin', task=task, stage='work', title='Implement', resources=['src'])
        plan = self.plan(task)
        self.call('a', 'hub_plan', task=task, stage='work', title='Work', status='planned',
                  expected=plan['revision'])
        self.fixture.client.hook(dict(cwd=str(self.fixture.base / 'a'), session_id='session-a',
                                      hook_event_name='SessionStart'))
        self.assertEqual(self.stage(task)['status'], 'planned')

    def test_unlinked_begin_and_session_start_do_not_promote_planned_task(self):
        task = self.planned_stage('Unlinked activation')
        with self.assertRaisesRegex(ValueError, 'Only initial planning'):
            self.call('a', 'hub_begin', task=task, title='Unlinked', resources=['src'])
        self.fixture.client.hook(dict(cwd=str(self.fixture.base / 'a'), session_id='session-a', hook_event_name='SessionStart'))
        self.assertEqual(self.plan(task)['task']['status'], 'planned')
        self.assertEqual(self.stage(task)['status'], 'planned')


    def test_multistage_work_retries_freezes_once_and_requires_stage_selector(self):
        task = self.planned_stage('Shared work')
        self.call('a', 'hub_plan', task=task, stage='review', title='Review', remaining=['Review'],
                  expected=self.plan(task)['revision'])
        first = self.call('a', 'hub_begin', task=task, stages=['work', 'review'], phase='implementation',
                          title='Shared implementation', resources=['src'])
        second = self.call('a', 'hub_begin', task=task, stages=['review', 'work'], phase='implementation',
                           title='Shared implementation', resources=['src'])
        self.assertEqual(first['work'], second['work'])
        current = self.plan(task)['task']
        self.assertEqual(len(current['currentWorks']), 1)
        self.assertEqual(set(current['currentWorks'][0]['stageIds']), {'review', 'work'})
        self.assertTrue(all(stage['agentActivity']['sessions'] == 1 for stage in current['stages']))
        with self.assertRaisesRegex(ValueError, 'Select one linked stage'):
            self.call('a', 'hub_report', work=first['work'], revision=first['revision'], result='Verified',
                      status='done', stage_status='done')
        self.call('a', 'hub_report', work=first['work'], revision=first['revision'], result='Verified',
                  status='done', stage_status='done', stage='work')
        current = self.plan(task)['task']
        self.assertEqual(next(s for s in current['stages'] if s['id'] == 'work')['status'], 'done')
        review = next(s for s in current['stages'] if s['id'] == 'review')
        self.assertEqual(review['status'], 'active')
        self.assertIn('Verified', review['done'])
        with self.coordination() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM work WHERE task=?', (task,)).fetchone()[0], 1)

    def test_initial_planning_creator_and_user_confirmation_waiting(self):
        task = self.call('a', 'hub_task', title='Initial planning', scope=['src'], acceptance=['Verified'])['task']
        initial = self.call('a', 'hub_begin', task=task, phase='planning', title='Plan', resources=['src'], mode='read')
        self.assertEqual(initial['stages'], [])
        self.assertEqual(self.plan(task)['task']['createdBy']['session'], 'session-a')
        self.call('a', 'hub_report', work=initial['work'], revision=initial['revision'], status='waiting',
                  waiting_kind='user_confirmation', result='Plan awaits confirmation')
        current = self.plan(task)['task']
        self.assertEqual(current['agentActivity']['state'], 'waiting')
        with self.coordination() as c:
            self.assertEqual(c.execute('SELECT waiting_kind FROM work WHERE id=?', (initial['work'],)).fetchone()[0], 'user_confirmation')

    def test_stage_estimate_is_revision_guarded_and_preserves_task_estimate(self):
        task = self.planned_stage('Stage estimate')
        estimate = dict(percentLow=20, percentHigh=40, hoursLow=2, hoursHigh=4, confidence='low', note='Active agent hours')
        self.call('a', 'hub_plan', task=task, stage='work', estimate=estimate, expected=self.plan(task)['revision'])
        current = self.plan(task)['task']
        self.assertEqual(current['stages'][0]['estimate']['hoursHigh'], 4)
        self.assertNotIn('estimate', current)


if __name__ == '__main__':
    unittest.main()
