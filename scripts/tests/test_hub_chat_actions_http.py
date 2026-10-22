"""Research-only HTTP routes, disposable catalogs and no external model calls."""
from unittest.mock import Mock
from test_manual_editing import ManualApiCase


class ChatActionsHttpTest(ManualApiCase):
    def test_task_launch_continue_review_and_answers_are_removed_without_side_effects(self):
        task = self.task()
        before = self.state()['revision']
        self.server.chat_actions = Mock()
        attempts = [
            ('/api/v1/chat-actions', {'task':task,'actionId':'task-launch'}),
            ('/api/v1/chat-actions', {'target':{'kind':'project'},'mode':'new','expected':before,'actionId':'review'}),
            ('/api/v1/chat-actions', {'threadId':'existing','task':task,'actionId':'continue'}),
            ('/api/v1/chat-answer', {'actionId':'old','requestId':'old-request','answers':{}}),
            ('/api/v1/review-apply', {'ref':'old-review','selected':[task],'expected':before}),
        ]
        for route, body in attempts:
            with self.subTest(route=route, body=body):
                status, result = self.request(route, body)
                self.assertEqual(status, 410, result)
                self.assertEqual(result['code'], 'task_execution_removed')
        self.assertEqual(self.state()['revision'], before)
        self.server.chat_actions.start.assert_not_called()
        self.server.chat_actions.start_research.assert_not_called()
        self.server.chat_actions.answer.assert_not_called()

    def test_documentation_new_and_cancel_route_to_specialized_service(self):
        service = self.server.chat_actions = Mock()
        service.start_research.return_value = {'actionId':'documentation-1','research':True,'status':'accepted'}
        service.cancel.return_value = {'actionId':'documentation-1','research':True,'status':'cancelled'}
        research = dict(operation='documentation-draft',objectId='project:'+self.pid,
                        revision=0,prompt='Describe the public interfaces',providerId='selected')
        status, result = self.request('/api/v1/chat-actions',
            {'action':'new','actionId':'documentation-1','research':research})
        self.assertEqual(status, 202, result)
        service.start_research.assert_called_once_with(self.pid, research, 'documentation-1')
        status, result = self.request('/api/v1/chat-actions', {'action':'cancel','actionId':'documentation-1'})
        self.assertEqual(status, 202, result)
        service.cancel.assert_called_once_with(self.pid, 'documentation-1')

    def test_architecture_route_preserves_explicit_project_and_action_identity(self):
        service = self.server.chat_actions = Mock()
        service.start_research.return_value = {'status':'accepted','research':True}
        research = dict(operation='architecture-analyze',objectId='project:'+self.pid,
                        template='overview',revision=0)
        status, result = self.request('/api/v1/architecture-agent', {'research':research,'actionId':'architecture-1'})
        self.assertEqual(status, 202, result)
        service.start_research.assert_called_once_with(self.pid, research, 'architecture-1')

    def test_research_route_rejects_unrecognized_fields_and_no_implicit_launch(self):
        service = self.server.chat_actions = Mock()
        for body in ({'action':'new','actionId':'bad'},
                     {'action':'cancel','actionId':'bad','research':{}},
                     {'action':'new','actionId':'bad','research':{},'cwd':'outside'},
                     {'actionId':'bad','research':{}}, []):
            status, result = self.request('/api/v1/chat-actions', body)
            self.assertEqual(status, 409, result)
        service.start_research.assert_not_called()
        service.cancel.assert_not_called()

    def test_read_only_capabilities_and_empty_history_do_not_launch(self):
        status, result = self.request('/api/architecture-agent-history')
        self.assertEqual(status, 200, result)
        self.assertEqual(result['items'], [])
        status, result = self.request('/api/architecture-agent-models')
        self.assertEqual(status, 200, result)
        self.assertEqual(result['models'], [])

    def test_tray_visibility_preference_is_removed(self):
        status, result = self.request('/api/v1/runtime', {'showTray':False})
        self.assertEqual(status, 410, result)
        self.assertEqual(result['code'], 'tray_visibility_removed')
