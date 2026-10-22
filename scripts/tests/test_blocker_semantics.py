"""Typed impediments are audited separately from task execution state."""
from test_manual_editing import ManualApiCase


class BlockerSemanticsTest(ManualApiCase):
    def test_task_and_stage_blockers_roundtrip_and_clear_with_history(self):
        task = self.task()
        stage = self.stage(task)
        for kind in ('technical', 'user_input', 'administrative'):
            blocker = dict(kind=kind, reason='Receipt has wrong launch time', action='Correct the receipt with audit')
            state = self.mutate('tasks/update', dict(task=task, patch=dict(status='blocked', blocker=blocker)))
            self.assertEqual(state['tasks'][0]['blocker'], blocker)
            state = self.mutate('stages/update', dict(task=task, stage=stage, patch=dict(status='blocked', blocker=blocker)))
            self.assertEqual(state['tasks'][0]['stages'][0]['blocker'], blocker)
        self.mutate('tasks/update', dict(task=task, patch=dict(status='active', blocker=None)))
        state = self.mutate('stages/update', dict(task=task, stage=stage, patch=dict(status='active', blocker=None)))
        self.assertIsNone(state['tasks'][0]['blocker'])
        self.assertIsNone(state['tasks'][0]['stages'][0]['blocker'])
        self.assertTrue(any(e.get('patch', {}).get('blocker') == blocker for e in state['events']))

    def test_invalid_blocker_rejected_atomically_and_legacy_blocked_supported(self):
        task = self.task()
        self.mutate('tasks/update', dict(task=task, patch=dict(status='blocked')))
        for blocker in ({}, 'administrative', dict(kind='other', reason='r', action='a'),
                        dict(kind='technical', reason=' ', action='a'),
                        dict(kind='user_input', reason='r', action=''),
                        dict(kind='technical', reason='r' * 1201, action='a'),
                        dict(kind='technical', reason='r', action='a' * 1201)):
            before = self.state()['revision']
            self.mutate('tasks/update', dict(task=task, patch=dict(blocker=blocker)), expected_status=409)
            self.assertEqual(self.state()['revision'], before)
