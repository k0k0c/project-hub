"""Research dispatch and historical task receipts cannot launch task execution."""
import json
import unittest
from unittest.mock import MagicMock, patch

from hub_action_context import ChatActionError
from unified_actions import UnifiedActions


class UnifiedResearchActionsTests(unittest.TestCase):
    def setUp(self):
        self.registry = MagicMock()
        self.providers = MagicMock()
        self.providers.selected.return_value = {'id':'provider', 'name':'Example provider',
            'config':{'model':'example-model', 'provider':'responses'}}
        self.context = MagicMock()
        self.history = MagicMock()
        self.api = MagicMock()
        self.api._stop.is_set.return_value = False
        self.api.existing.return_value = None
        self.history.existing.return_value = None
        self.history.recent.return_value = []
        self.api.recent.return_value = []
        for name, value in [('HubActionContext', self.context), ('LegacyActionReceipts', self.history), ('ApiAgentRuns', self.api)]:
            patcher = patch('unified_actions.' + name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.service = UnifiedActions(self.registry, providers=self.providers)

    def test_task_stage_and_project_execution_are_rejected_before_dispatch(self):
        for options in ({}, {'stage':'stage'}, {'thread_id':'old-chat'},
                        {'target':'project', 'intent':'review', 'mode':'plan'}, {'intent':'estimate'}):
            with self.subTest(options=options), self.assertRaises(ChatActionError) as error:
                self.service.start('project', 'task', 'action', **options)
            self.assertEqual(error.exception.code, 'task_execution_removed')
        self.api.start.assert_not_called()
        self.api.start_research.assert_not_called()

    def test_only_specialized_research_operations_reach_api(self):
        for operation in sorted(UnifiedActions.RESEARCH_OPERATIONS):
            request = {'operation':operation, 'objectId':'project:project', 'revision':2, 'providerId':'provider'}
            self.service.start_research('project', request, operation)
            self.api.start_research.assert_called_with('project', request, operation)
        self.api.start_research.reset_mock()
        for request in ({}, {'operation':'task'}, {'operation':'review'}, None):
            with self.assertRaises(ChatActionError) as error:
                self.service.start_research('project', request, 'forbidden')
            self.assertEqual(error.exception.code, 'invalid_research_operation')
        self.api.start_research.assert_not_called()

    def test_legacy_receipt_id_is_read_only_and_never_redispatched(self):
        self.history.existing.return_value = {'project':'project'}
        with self.assertRaises(ChatActionError) as error:
            self.service.start_research('project', {'operation':'architecture-analyze'}, 'legacy')
        self.assertEqual(error.exception.code, 'legacy_action_read_only')
        self.api.start_research.assert_not_called()
        with self.assertRaises(ChatActionError) as error:
            self.service.cancel('project', 'legacy')
        self.assertEqual(error.exception.code, 'legacy_action_read_only')
        self.api.cancel.assert_not_called()

    def test_cancel_only_routes_current_research(self):
        self.api.existing.return_value = {'body':json.dumps({'research':True})}
        self.service.cancel('project', 'research')
        self.api.cancel.assert_called_once_with('project', 'research')
        self.api.cancel.reset_mock()
        self.api.existing.return_value = {'body':json.dumps({'task':'task'})}
        with self.assertRaises(ChatActionError) as error:
            self.service.cancel('project', 'task-action')
        self.assertEqual(error.exception.code, 'task_execution_removed')
        self.api.cancel.assert_not_called()

    def test_task_receipt_history_is_preserved_with_resume_disabled(self):
        old = {'actionId':'legacy', 'createdAt':1, 'status':'completed', 'transport':'stdio', 'resumeAllowed':True}
        current = {'actionId':'api', 'createdAt':2, 'status':'completed', 'resultRef':'knowledge/document/result'}
        self.history.recent.return_value = [old]
        self.api.recent.return_value = [current]
        rows = self.service.recent('project', 'task')
        self.assertEqual([row['actionId'] for row in rows], ['api', 'legacy'])
        self.assertTrue(all(row['readOnly'] and not row['resumeAllowed'] for row in rows))
        self.assertEqual(rows[0]['resultRef'], current['resultRef'])
        self.assertTrue(old['resumeAllowed'], 'reading must not rewrite stored history')

    def test_capabilities_and_answers_do_not_offer_task_or_chat_execution(self):
        value = self.service.capabilities('project')
        self.assertFalse(value['taskExecution'])
        self.assertFalse(value['nativeChat'])
        self.assertFalse(value['sourceExecution'])
        self.assertEqual(set(value['operations']), UnifiedActions.RESEARCH_OPERATIONS)
        with self.assertRaises(ChatActionError) as error:
            self.service.answer('project', 'old', 'question', {})
        self.assertEqual(error.exception.code, 'task_execution_removed')
        self.api.answer.assert_not_called()


if __name__ == '__main__':
    unittest.main()
