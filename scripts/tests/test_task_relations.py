from test_manual_editing import ManualApiCase
from task_transfer import transfer


class TaskRelationsTest(ManualApiCase):
    def test_create_accepts_links_and_projects_incoming_direction(self):
        target = self.task()
        state = self.mutate('tasks/create', {'task': {'title': 'Linked', 'links': [{'target': target, 'type': 'blocks'}]}})
        row = next(t for t in state['tasks'] if t['id'] == target)
        self.assertEqual(row['relations'][0]['type'], 'blocked-by')
        self.mutate('tasks/create', {'task': {'title': 'Empty links', 'links': []}})
        self.mutate('tasks/create', {'task': {'title': 'Bad links', 'links': [{'target': 'missing', 'type': 'related'}]}}, expected_status=409)

    def test_inverse_types_and_no_persisted_duplicates(self):
        source, target = self.task('Source'), self.task('Target')
        for forward, reverse in [('blocks', 'blocked-by'), ('duplicates', 'duplicated-by'), ('related', 'related')]:
            state = self.mutate('tasks/update', {'task': source, 'patch': {'links': [{'target': target, 'type': forward}]}})
            rows = {t['id']: t for t in state['tasks']}
            self.assertEqual(rows[target]['links'], [])
            self.assertEqual(rows[target]['relations'][0]['type'], reverse)
            self.assertEqual(rows[target]['relations'][0]['sourceTask'], source)
            self.assertEqual(rows[source]['relations'][0]['direction'], 'outgoing')
        state = self.mutate('tasks/update', {'task': source, 'patch': {'links': []}})
        self.assertTrue(all(t['relations'] == [] for t in state['tasks']))

    def test_cross_project_relations_and_missing_targets(self):
        source = self.task('Source')
        other = self.projects['b']
        target = self.task('Foreign', other)
        self.mutate('tasks/link', {'task': source, 'target': target, 'project': other, 'type': 'blocks'})
        status, state = self.request('/api/v1/state', project=other)
        self.assertEqual(status, 200)
        relation = state['tasks'][0]['relations'][0]
        self.assertEqual((relation['target'], relation['project'], relation['type']), (source, self.pid, 'blocked-by'))
        self.assertEqual(state['tasks'][0]['links'], [])
        local_revision, relation_revision = state['revision'], state['relationsRevision']
        self.mutate('tasks/update', {'task': source, 'patch': {'links': []}})
        _, refreshed = self.request('/api/v1/state', project=other)
        self.assertEqual(refreshed['revision'], local_revision)
        self.assertNotEqual(refreshed['relationsRevision'], relation_revision)
        self.mutate('tasks/update', {'task': source, 'patch': {'links': [{'target': 'missing', 'project': other, 'type': 'related'}]}}, expected_status=409)

    def test_explicit_inverse_is_deduplicated_in_projection(self):
        source, target = self.task(), self.task()
        self.mutate('tasks/link', {'task': source, 'target': target, 'type': 'blocks'})
        state = self.mutate('tasks/link', {'task': target, 'target': source, 'type': 'blocked-by'})
        self.assertEqual([len(t['relations']) for t in state['tasks']], [1, 1])

    def test_relation_follows_transferred_target(self):
        source, target = self.task(), self.task()
        self.mutate('tasks/link', {'task': source, 'target': target, 'type': 'related'})
        transfer(self.registry, self.pid, self.projects['b'], target, expected=self.state()['revision'], request='move-target')
        _, state = self.request('/api/v1/state')
        self.assertEqual(state['tasks'][0]['relations'][0]['project'], self.projects['b'])
        _, state = self.request('/api/v1/state', project=self.projects['b'])
        self.assertEqual(state['tasks'][0]['relations'][0]['target'], source)
