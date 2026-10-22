import unittest

import test_project_hub_plugin_api as fixtures
from hub_core import HubError


class KnowledgeReportEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PluginApiTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.call = self.fixture.invoke

    def task_work(self, title='Evidence'):
        task = self.call('a', 'hub_task', title=title, scope=['src'], acceptance=['Verified'])['task']
        self.call('a', 'hub_plan', task=task, stage='work', title='Work', remaining=['Verify'])
        work = self.call('a', 'hub_begin', task=task, stage='work', title='Implement', resources=['src'])
        return task, work

    def register_document(self, task, identifier='doc:alpha'):
        result = self.call('a', 'hub_knowledge', action='changeset', args=dict(
            expected=0, key='document-'+identifier, reason='Report evidence', task=task, stage='work',
            operations=[dict(op='put', item=dict(id=identifier, kind='document', title='Evidence', markdown='# Evidence'))]))
        plan = self.call('a', 'hub_plan', task=task)
        self.call('a', 'hub_task_update', task=task, expected=plan['revision'], patch={'sources': result['sources']})
        return result

    def register_entity_source(self, task, expected=0, identifier='entity:alpha'):
        self.call('a', 'hub_knowledge', action='changeset', args=dict(
            expected=expected, key='entity-'+identifier, reason='Entity evidence rejection', task=task, stage='work',
            operations=[dict(op='put', item=dict(id=identifier, kind='entity', title='Entity'))]))
        plan = self.call('a', 'hub_plan', task=task)
        with self.assertRaises(HubError):
            self.call('a', 'hub_task_update', task=task, expected=plan['revision'], patch={
                'sources': [dict(path='knowledge/document/'+identifier, label='Entity source')]})
        store = self.fixture.registry.store(self.fixture.ids['a'])
        with self.assertRaises(ValueError):
            store.record(dict(id='entity-evidence-reference', taskId=task, kind='note', title='Entity source',
                              evidence=[dict(path='knowledge/document/'+identifier, label='Entity source')]),
                         expected_revision=store.snapshot()['revision'])

    def report(self, work, evidence, status='done'):
        return self.call('a', 'hub_report', work=work['work'], revision=work['revision'],
                         result='Verified', status=status, evidence=evidence)

    def test_registered_current_and_revision_documents_are_valid_evidence(self):
        task, work = self.task_work()
        result = self.register_document(task)
        current = result['sources'][0]['path']
        revision = 'knowledge/revision/{}/document/doc:alpha'.format(result['revision'])

        first = self.report(work, [current, revision])
        replay = self.report(work, [current, revision])

        self.assertEqual(replay, first)
        self.assertEqual(first['status'], 'done')

    def test_ordinary_relative_file_evidence_remains_valid(self):
        task, work = self.task_work('File evidence')
        (self.fixture.base / 'a' / 'proof.md').write_text('proof', encoding='utf-8')

        result = self.report(work, ['proof.md'])

        self.assertEqual(result['status'], 'done')

    def test_unknown_entity_and_malformed_knowledge_evidence_are_rejected(self):
        task, work = self.task_work('Invalid knowledge evidence')
        self.register_document(task)
        self.register_entity_source(task, expected=1)
        for evidence in ('knowledge/document/missing:doc',
                         'knowledge/revision/x/document/doc:alpha',
                         'knowledge/document/../doc:alpha',
                         'knowledge/document/entity:alpha'):
            with self.subTest(evidence=evidence), self.assertRaises(HubError) as caught:
                self.report(work, [evidence], status='active')
            self.assertEqual(caught.exception.body['error'], 'invalid_evidence')

    def test_absolute_and_traversal_filesystem_evidence_are_rejected(self):
        task, work = self.task_work('Invalid file evidence')
        for evidence in ('C:/proof.md', '/proof.md', '../proof.md'):
            with self.subTest(evidence=evidence), self.assertRaises(HubError) as caught:
                self.report(work, [evidence], status='active')
            self.assertEqual(caught.exception.body['error'], 'invalid_resource')

    def test_document_registered_in_another_project_is_rejected(self):
        other = self.call('b', 'hub_task', title='Other evidence', scope=['src'], acceptance=['Verified'])['task']
        self.call('b', 'hub_plan', task=other, stage='work', title='Work', remaining=['Verify'])
        result = self.call('b', 'hub_knowledge', action='changeset', args=dict(
            expected=0, key='other-document', reason='Other project evidence', task=other, stage='work',
            operations=[dict(op='put', item=dict(id='doc:shared', kind='document', title='Other', markdown='# Other'))]))
        task, work = self.task_work('Wrong project evidence')

        with self.assertRaises(HubError) as caught:
            self.report(work, [result['sources'][0]['path']], status='active')

        self.assertEqual(caught.exception.body['error'], 'invalid_evidence')


if __name__ == '__main__':
    unittest.main()
