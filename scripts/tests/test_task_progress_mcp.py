"""Progress updates through the real HTTP/MCP boundary, isolated catalogs only."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_project_hub_plugin_api as fixtures
from hub_core import HubError
from hub_plugin import Mcp, TOOLS


class ProgressMcpTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PluginApiTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.call = self.fixture.invoke
        self.task = self.call('a','hub_task',title='Progress task',scope=['Feature'],acceptance=['Verified'])['task']

    def estimate(self, **extra):
        return dict(percentLow=35, percentHigh=45, hoursLow=4, hoursHigh=8,
                    confidence='Средняя', note='Реализация проверена; интеграция впереди', **extra)

    def plan(self):
        return self.call('a','hub_plan',task=self.task)

    def update(self, **args):
        return self.call('a','hub_plan',task=self.task,expected=self.plan()['revision'],**args)

    def test_estimate_primary_and_idempotent_retry(self):
        args = dict(task=self.task, expected=self.plan()['revision'], estimate=self.estimate(), primary=True)
        self.call('a','hub_plan',**args)
        first = self.plan()
        self.call('a','hub_plan',**args)
        second = self.plan()
        self.assertEqual(first['revision'], second['revision'])
        self.assertEqual(first['task']['estimate'], second['task']['estimate'])
        self.assertEqual(second['task']['estimate']['updatedBy'], 'session-a')
        self.assertTrue(second['task']['estimate']['updatedAt'])
        self.assertEqual(second['mainTask'], dict(task=self.task,reason='explicit'))
        with self.assertRaises(HubError):
            self.call('a','hub_plan',**{**args, 'estimate':{**self.estimate(),'percentLow':36}})
        self.update(primary=False)
        self.assertEqual(self.plan()['mainTask'], dict(task=self.task, reason='largest-active'))

    def test_unchanged_review_updates_date_and_clears_unknown_hours(self):
        self.update(estimate=self.estimate())
        first = self.plan()['task']['estimate']['updatedAt']
        value = self.estimate()
        value.pop('hoursLow');value.pop('hoursHigh')
        self.update(estimate=value)
        result = self.plan()['task']['estimate']
        self.assertNotEqual(first, result['updatedAt'])
        self.assertNotIn('hoursHigh', result)
        self.assertEqual(result['percentLow'],35)

    def test_invalid_estimates_and_missing_revision_preserve_plan(self):
        revision = self.plan()['revision']
        values = [{**self.estimate(),'percentLow':True}, {**self.estimate(),'percentHigh':101},
                  {**self.estimate(),'hoursLow':9}, {**self.estimate(),'note':''},
                  {**self.estimate(),'updatedAt':'fake'}, {**self.estimate(),'hoursHigh':None}]
        for estimate in values:
            with self.assertRaises(HubError): self.update(estimate=estimate)
        with self.assertRaises(HubError): self.call('a','hub_plan',task=self.task,estimate=self.estimate())
        with self.assertRaises(HubError): self.update(primary='true')
        with self.assertRaises(HubError): self.update(primary=True,stage='mixed')
        self.assertEqual(revision, self.plan()['revision'])

    def test_other_project_cannot_change_estimate_or_primary(self):
        self.call('b','hub_context')
        with self.assertRaises(HubError) as error:
            self.call('b','hub_plan',task=self.task,expected=self.plan()['revision'],estimate=self.estimate(),primary=True)
        self.assertEqual(error.exception.body['error'],'task_project_mismatch')

    def test_report_defers_review_hint_without_changing_percent(self):
        self.call('a','hub_plan',task=self.task,stage='feature',title='Feature',remaining=['Verify'])
        work = self.call('a','hub_begin',task=self.task,stage='feature',title='Implement',resources=['src'])
        self.assertTrue(work['progressHint']['tasks'][0]['reviewDue'])
        self.update(estimate=self.estimate())
        result = self.call('a','hub_report',work=work['work'],revision=work['revision'],result='Verified',status='done',stage_status='done')
        self.assertEqual(result['planSync'],'saved')
        self.assertTrue(result['progressHint']['deferred'])
        plan = self.plan()
        self.assertTrue(plan['task']['progress']['reviewDue'])
        self.assertEqual(plan['task']['estimate']['percentLow'],35)
        self.update(estimate=self.estimate())
        self.assertFalse(self.plan()['task']['progress']['reviewDue'])
        context = self.call('a','hub_context')
        self.assertIn('progressHint', context)

    def test_client_schema_accepts_new_fields_and_string_revision(self):
        api = Mcp(None, str(self.fixture.base/'a'), 'session-a', client=self.fixture.client)
        result = api.call('hub_plan',dict(task=self.task,expected=self.plan()['revision'],estimate=self.estimate(),primary=True))
        self.assertEqual(result['mainTask']['task'],self.task)
        schema = next(t for t in TOOLS if t['name']=='hub_plan')['inputSchema']
        self.assertIn('string',schema['properties']['expected']['type'])


if __name__ == '__main__': unittest.main()
