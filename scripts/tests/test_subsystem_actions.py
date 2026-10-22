"""Focused draft tests; all registry/source data lives in TemporaryDirectory."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_registry import ProjectRegistry
from knowledge_store import KnowledgeStore, KnowledgeError, execute
from knowledge_scan import scan
from subsystem_actions import build_subsystem_request, subsystem_references, plan_subsystem, plan_first_level


class SubsystemActionsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.registry = ProjectRegistry(self.base / 'hub', standalone=True)
        project = self.registry.create('Example')['id']
        self.store = KnowledgeStore(self.registry, project)

    def request(self, action, identifier, patch=None, **extra):
        return build_subsystem_request(self.store.context(), action, identifier, patch,
                                       key='request-' + str(self.store.context()['revision']),
                                       reason='Verified subsystem edit', task='task', stage='architecture', **extra)

    def apply(self, action, identifier, patch=None, **extra):
        return self.store.changeset(**self.request(action, identifier, patch, **extra))

    def assert_error(self, code, callback):
        with self.assertRaises(KnowledgeError) as caught:
            callback()
        self.assertEqual(caught.exception.body['error'], code)

    def test_rootless_create_preserves_exact_policy_and_detaches_input(self):
        context = self.store.context()
        context['policy']['sections'] = ['reference']
        context['policy']['maxFiles'] = 73
        original = deepcopy(context)
        patch = dict(title='Service', paths=['src'])
        request = build_subsystem_request(context, 'create', 'service', patch,
                                           key='create', reason='Create service')
        patch['paths'].append('changed')
        self.assertEqual(context, original)
        self.assertEqual(request['policy']['sections'], ['reference'])
        self.assertEqual(request['policy']['maxFiles'], 73)
        self.assertEqual(request['policy']['components'][0]['paths'], ['src'])
        self.store.changeset(**request)
        self.assertEqual(self.store.context()['policy'], request['policy'])
        self.assertFalse(self.store.roots)

    def test_rename_reparent_and_cycle_rejection_keep_ids(self):
        self.apply('create', 'root', dict(title='Root'))
        self.apply('create', 'child', dict(title='Child', parent='root'))
        self.apply('update', 'child', dict(title='Renamed', parent=None))
        child = self.store.context()['policy']['components'][1]
        self.assertEqual(child['id'], 'child')
        self.assertEqual(child['title'], 'Renamed')
        self.assertNotIn('parent', child)
        self.apply('update', 'child', dict(parent='root'))
        self.assert_error('invalid_policy', lambda: self.request('update', 'root', dict(parent='child')))
        self.assert_error('invalid_policy', lambda: self.request('update', 'child', dict(parent='missing')))
        self.assert_error('invalid_subsystem', lambda: self.request('update', 'child', dict(id='new')))
        self.assert_error('subsystem_exists', lambda: self.request('create', 'child', dict(title='Duplicate')))

    def test_conflict_replay_and_changed_key_content(self):
        request = self.request('create', 'service', dict(title='Service'))
        self.assertEqual(self.store.changeset(**request)['revision'], 1)
        self.assertTrue(self.store.changeset(**request)['replayed'])
        changed = deepcopy(request)
        changed['policy']['components'][0]['title'] = 'Other'
        self.assert_error('idempotency_conflict', lambda: self.store.changeset(**changed))
        stale = deepcopy(request)
        stale['key'] = 'different-key'
        self.assert_error('revision_conflict', lambda: self.store.changeset(**stale))
        self.assertEqual(self.store.context()['revision'], 1)

    def test_remove_requires_empty_leaf_and_keeps_history(self):
        self.apply('create', 'root', dict(title='Root'))
        self.apply('create', 'child', dict(title='Child', parent='root'))
        self.assert_error('subsystem_has_children', lambda: self.request('remove', 'root', references=[]))
        self.assert_error('subsystem_unchecked', lambda: self.request('remove', 'child'))
        self.apply('remove', 'child', references=subsystem_references(self.store, 'child'))
        self.assertEqual(len(self.store.context()['policy']['components']), 1)
        history = self.store.history()['items']
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]['task'], 'task')
        self.assertEqual(history[0]['stage'], 'architecture')

    def test_policy_edits_preserve_real_scan_facts_and_authored_history(self):
        source = self.base / 'source'
        source.mkdir()
        (source / 'example.py').write_text('class Example:\n    pass\n', encoding='utf-8')
        project = self.registry.create('Source example', [str(source)])['id']
        self.store = KnowledgeStore(self.registry, project)
        self.apply('create', 'service', dict(title='Service', paths=['.']))
        result = scan(source, self.store.context()['policy'])
        items = result['entities'] + result['relations']
        self.store.changeset(1, 'facts', [dict(op='put', item=item) for item in items], 'Actual scan fixtures')
        component = self.store.read('service')
        component['description'] = 'Authored explanation'
        self.store.changeset(2, 'authored', [dict(op='put', item=component)], 'Explain service')
        before = {item['id']: self.store.read(item['id']) for item in items}
        history = self.store.history(identifier='service')
        self.apply('update', 'service', dict(title='Renamed', description='Policy summary'))
        self.assertEqual({item['id']: self.store.read(item['id']) for item in items}, before)
        # Filtered history pagination can move with a policy-only commit; compare
        # the actual immutable item entries rather than paging metadata.
        self.assertEqual(self.store.history(identifier='service')['items'], history['items'])
        refs = subsystem_references(self.store, 'service')
        self.assertIn('service', refs)
        self.assert_error('subsystem_in_use', lambda: self.request('remove', 'service', references=refs))

    def test_ui_plan_renames_projection_and_replays_without_losing_authored_fields(self):
        planned = plan_subsystem(self.store, expected=0, action='create', identifier='service',
                                 patch={'title':'Service'}, key='ui-create', reason='Create subsystem')['request']
        self.store.changeset(**planned)
        item = self.store.read('service')
        item['description'] = 'Preserved explanation'
        item['evidence'] = [{'path':'reference.txt'}]
        self.store.changeset(1, 'author', [{'op':'put','item':item}], 'Explain subsystem')
        planned = plan_subsystem(self.store, expected=2, action='update', identifier='service',
                                 patch={'title':'Controller editor'}, key='ui-rename', reason='Rename subsystem')['request']
        self.assertEqual(self.store.read('service')['title'], 'Service')
        result = self.store.changeset(**planned)
        self.assertTrue(self.store.changeset(**planned)['replayed'])
        self.assertEqual(self.store.read('service'), {**item, 'title':'Controller editor', 'paths':[]})
        self.assertEqual(len(self.store.history(identifier='service')['items']), 3)
        self.assertEqual(result['revision'], 3)

    def test_remove_empty_projection_preserves_item_history_and_rejects_used_projection(self):
        planned = plan_subsystem(self.store, expected=0, action='create', identifier='empty',
                                 patch={'title':'Empty'}, key='ui-create', reason='Create')['request']
        self.store.changeset(**planned)
        removal = plan_subsystem(self.store, expected=1, action='remove', identifier='empty',
                                 key='ui-remove', reason='Remove')['request']
        self.store.changeset(**removal)
        self.assertEqual(self.store.context()['policy']['components'], [])
        self.assertTrue(self.store.read('empty')['removed'])
        self.assertEqual(len(self.store.history(identifier='empty')['items']), 2)

    def test_whole_project_research_subject_is_virtual_and_project_scoped(self):
        from knowledge_research import read_object
        item = read_object(self.store, 'project:' + self.store.project)
        self.assertEqual(item['type'], 'project')
        self.assertTrue(item['virtual'])
        self.assertEqual(self.store.context()['counts'], {})
        with self.assertRaises(KnowledgeError):
            read_object(self.store, 'project:unregistered')

    def test_http_action_envelope_keeps_subsystem_operation_separate(self):
        payload = dict(action='subsystem-plan', operation='create', expected=0,
            identifier='service', patch={'title':'Service'}, key='http-create', reason='Create subsystem')
        action = payload.pop('action')
        result = execute(self.registry, self.store.project, action, payload)
        execute(self.registry, self.store.project, 'changeset', result['request'])
        self.assertEqual(self.store.read('service')['title'], 'Service')

    def test_first_level_adds_verified_boundaries_and_preserves_authored_subsystems(self):
        source = self.base / 'code'
        (source / 'src').mkdir(parents=True)
        (source / 'src' / 'example.py').write_text('class Example: pass', encoding='utf-8')
        project = self.registry.create('Inventory', [str(source)])['id']
        store = KnowledgeStore(self.registry, project)
        facts = scan(source, store.context()['policy'])
        store.changeset(0, 'inventory', [{'op':'put','item':item} for item in facts['entities'] + facts['relations']], 'Scan')
        original = plan_subsystem(store, expected=1, action='create', identifier='manual',
            patch={'title':'Manual','description':'User explanation'}, key='manual', reason='User subsystem')['request']
        store.changeset(**original)
        before = store.read('manual')
        request = plan_first_level(store, 2, [{'title':'Application','description':'Verified code','paths':['src']}],
            key='api-components:one', reason='Analyzed first level', actor='actor', task='task', stage='stage')
        self.assertEqual(store.context()['revision'], 2, 'Planning is read only')
        result = store.changeset(**request)
        self.assertTrue(store.changeset(**request)['replayed'])
        self.assertEqual(store.read('manual'), before)
        created = request['operations'][0]['item']
        self.assertEqual(created['evidence'][0]['path'], 'src/example.py')
        self.assertEqual(len(created['evidence'][0]['hash']), 64)
        self.assertEqual(result['revision'], 3)
        self.assertEqual(store.history()['items'][0]['actor'], 'actor')

    def test_first_level_rejects_unverified_paths_ids_duplicates_and_stale_revision(self):
        valid = {'title':'Service','description':'Conceptual subsystem','paths':[]}
        invalids = [dict(valid, paths=['unknown']), dict(valid, paths=['../code']),
                    dict(valid, id='chosen-by-model'), [valid, valid], dict(valid, title='\nHidden')]
        for candidate in invalids:
            proposals = candidate if isinstance(candidate, list) else [candidate]
            self.assert_error('invalid_subsystem_proposal', lambda: plan_first_level(self.store, 0, proposals,
                key='api-invalid', reason='Reject unsafe proposal'))
        request = plan_first_level(self.store, 0, [valid], key='api-concept', reason='Conceptual first level')
        self.store.changeset(**request)
        self.assert_error('revision_conflict', lambda: plan_first_level(self.store, 0, [valid], key='stale', reason='Stale'))
        self.assert_error('invalid_subsystem_proposal', lambda: plan_first_level(self.store, 1, [valid], key='duplicate', reason='Duplicate'))
        self.assertEqual(self.store.context()['revision'], 1)

    def test_proposal_titles_are_scoped_to_parent_without_changing_existing_branch(self):
        policy = self.store.context()['policy']
        policy['components'] = [dict(id='parent', title='Parent', paths=[]),
                                dict(id='root-service', title='Service', paths=[])]
        self.store.changeset(0, 'branches', [], 'Fixture', policy=policy)
        proposal = dict(title='Service', description='Child responsibility', paths=[])
        request = plan_first_level(self.store, 1, [proposal], key='child-service', reason='Nested proposal', parent='parent')
        self.store.changeset(**request)
        child = request['operations'][0]['item']
        self.assertEqual(child['parent'], 'parent')
        self.assertEqual(child['title'], 'Service')
        self.assertEqual(self.store.context()['policy']['components'][1]['id'], 'root-service')
        self.assert_error('invalid_subsystem_proposal', lambda: plan_first_level(self.store, 2, [proposal],
            key='duplicate-child', reason='Reject same branch duplicate', parent='parent'))


if __name__ == '__main__':
    unittest.main()
