import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from knowledge_store import KnowledgeStore, KnowledgeError
from project_registry import ProjectRegistry
from provider_runtime import RuntimeError
from research_api import ResearchBroker, normalize, parse_result, publication
from research_sources import ResearchSources
from hub_action_context import ChatActionError


class ResearchSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'source'
        self.other = Path(self.temp.name) / 'other'
        self.root.mkdir(); self.other.mkdir()
        self.registry = ProjectRegistry(Path(self.temp.name) / 'data', standalone=True)
        self.project = self.registry.create('Example', [str(self.root), str(self.other)])['id']
        self.store = KnowledgeStore(self.registry, self.project)
        (self.root / 'AGENTS.md').write_text('Project rule: inspect evidence.\n', encoding='utf-8')
        (self.root / 'src').mkdir()
        (self.root / 'src' / 'AGENTS.md').write_text('Module rule: preserve interfaces.\n', encoding='utf-8')
        (self.root / 'src' / 'selected.py').write_text('from neighbor import Neighbor\nclass Selected:\n    pass\n', encoding='utf-8')
        (self.other / 'neighbor.py').write_text('class Neighbor:\n    pass\n', encoding='utf-8')
        self.sources = ResearchSources(self.store)

    def test_tree_search_and_line_reads_cover_neighbor_in_another_root(self):
        self.assertEqual([r['id'] for r in self.sources.roots()['roots']], ['0', '1'])
        first = self.sources.call(dict(action='tree', limit=1))
        self.assertTrue(first['more']); self.assertEqual(first['next'], 1)
        search = self.sources.call(dict(action='search', query='class Neighbor'))
        self.assertEqual(search['items'][0]['path'], '@roots/1/neighbor.py')
        page = self.sources.call(dict(action='read', path='@roots/1/neighbor.py', line=1, lines=1))
        self.assertEqual(page['text'].splitlines(), ['class Neighbor:']); self.assertTrue(page['more'])
        self.assertEqual(page['hash'], hashlib.sha256((self.other / 'neighbor.py').read_bytes()).hexdigest())
        self.sources.validate(dict(path=page['path'], hash=page['hash'], line=1))
        with self.assertRaisesRegex(RuntimeError, 'research_evidence_unverified'):
            self.sources.validate(dict(path=page['path'], hash=page['hash'], line=2))

    def test_file_scoped_search_and_tree_do_not_require_directory_or_complete_inventory(self):
        self.sources.MAX_FILES = 1
        self.assertTrue(self.sources.call(dict(action='tree'))['partial'])
        self.assertNotIn('src/selected.py', self.sources.inventory)
        for path, query, line in (('src/selected.py', 'class Selected', 2),
                                  ('@roots/1/neighbor.py', 'class Neighbor', 1)):
            with self.subTest(path=path):
                tree = self.sources.call(dict(action='tree', path=path))
                self.assertEqual(tree['items'], [dict(path=path)])
                found = self.sources.call(dict(action='search', path=path, query=query))
                self.assertEqual([(item['path'], item['line']) for item in found['items']], [(path, line)])
                # Search locates evidence; it must not authorize unread lines.
                with self.assertRaisesRegex(RuntimeError, 'research_evidence_unverified'):
                    self.sources.validate(dict(path=path, hash=found['items'][0]['hash'], line=line))
                page = self.sources.call(dict(action='read', path=path, line=line, lines=1))
                self.sources.validate(dict(path=path, hash=page['hash'], line=line))

    def test_evidence_spans_adjacent_pages_but_never_unread_gaps(self):
        path = 'src/paged.py'
        (self.root / path).write_text(''.join(f'line {i}\n' for i in range(1, 9)), encoding='utf-8')
        page = self.sources.read(path, line=3, lines=2)
        self.assertEqual(page['evidenceRef'], dict(kind='source', path=path, hash=page['hash'], line=3, endLine=4))
        self.sources.read(path, line=1, lines=2)
        self.sources.read(path, line=4, lines=3)
        evidence = dict(path=path, hash=page['hash'], line=2, endLine=6)
        self.assertEqual(self.sources.validate(evidence)['endLine'], 6)
        self.sources.read(path, line=8, lines=1)
        with self.assertRaises(RuntimeError) as failure:
            self.sources.validate(dict(evidence, endLine=8))
        self.assertEqual(failure.exception.diagnostic, dict(validationReason='source_range_unread'))
        self.sources.read(path, line=7, lines=1)
        self.assertEqual(self.sources.validate(dict(evidence, endLine=8))['endLine'], 8)
        with self.assertRaises(RuntimeError) as failure:
            self.sources.validate(dict(evidence, hash='0' * 64))
        self.assertEqual(failure.exception.diagnostic, dict(validationReason='source_hash_mismatch'))

    def test_directory_search_stays_in_selected_root_and_file_scopes_keep_guards(self):
        (self.root / 'src' / 'other.py').write_text('class SelectedOther:\n    pass\n', encoding='utf-8')
        self.assertEqual([item['path'] for item in self.sources.call(
            dict(action='search', path='src', query='class'))['items']], ['src/other.py', 'src/selected.py'])
        self.assertEqual([item['path'] for item in self.sources.call(
            dict(action='tree', path='@roots/1/.'))['items']], ['@roots/1/neighbor.py'])
        for path in ('../other/neighbor.py', '.git/config', '.env', 'binary.exe'):
            for action in ('tree', 'search'):
                with self.subTest(path=path, action=action), self.assertRaisesRegex(RuntimeError, 'research_source_denied'):
                    self.sources.call(dict(action=action, path=path, **({'query':'class'} if action=='search' else {})))

    def test_search_does_not_hide_changed_source_or_workspace(self):
        for code in ('research_workspace_changed', 'research_source_changed'):
            with self.subTest(code=code), patch.object(self.sources, '_content', side_effect=RuntimeError(code)):
                with self.assertRaisesRegex(RuntimeError, code):
                    self.sources.call(dict(action='search', path='src/selected.py', query='class'))

    def test_file_search_reports_unreadable_content_instead_of_an_empty_match(self):
        for data, code in ((b'\xff', 'research_source_unavailable'),
                           (b'-----BEGIN PRIVATE KEY-----', 'research_source_denied'),
                           (b'x'*(self.sources.MAX_FILE+1), 'research_source_too_large')):
            (self.root / 'unreadable.py').write_bytes(data)
            with self.subTest(code=code), self.assertRaisesRegex(RuntimeError, code):
                self.sources.call(dict(action='search', path='unreadable.py', query='class'))

    def test_missing_source_returns_recoverable_tool_result_but_guards_remain_fatal(self):
        self.store.changeset(0, 'object', [dict(op='put', item=dict(
            id='component', kind='entity', type='component', title='Example'))], 'Fixture')
        class Client:
            session='api:own'; token='private'; timeout=1; cancel=threading.Event(); admission=threading.RLock()
            def closed(self): return False
        broker = ResearchBroker(Client(), self.store, normalize(dict(
            operation='architecture-analyze', objectId='component', revision=1)), [])
        unavailable = broker.call('research_source', dict(action='read', path='missing.py'), 1)
        self.assertEqual(unavailable['error']['code'], 'research_source_unavailable')
        self.assertIs(unavailable['error']['recoverable'], True)
        self.assertEqual(unavailable['error']['action'], 'read')
        self.assertEqual(unavailable['workspaceRevision'], broker.sources.signature)
        self.assertNotIn(str(self.root), json.dumps(unavailable))
        self.assertNotIn('missing.py', json.dumps(unavailable))
        self.assertEqual(broker.sources.reads, {})
        denied = broker.call('research_source', dict(action='read', path='.codex/config.toml'), 1)
        self.assertEqual(denied['error']['code'], 'research_source_denied')
        self.assertTrue(denied['error']['recoverable'])
        self.assertNotIn('config.toml', json.dumps(denied))
        self.assertEqual(broker.sources.reads, {})
        (self.root / 'large.py').write_bytes(b'x' * (broker.sources.MAX_FILE + 1))
        oversized = broker.call('research_source', dict(action='read', path='large.py'), 1)
        self.assertEqual(oversized['error']['code'], 'research_source_too_large')
        self.assertTrue(oversized['error']['recoverable'])
        self.assertEqual(broker.sources.reads, {})
        self.assertEqual(broker.sources.read_bytes, 0)
        self.assertNotIn('large.py', json.dumps(oversized))
        for code in ('research_read_limit', 'research_source_line_too_large'):
            error = RuntimeError(code); error.args = ('SECRET private path',)
            with self.subTest(code=code), patch.object(broker.sources, 'call', side_effect=error):
                refusal = broker.call('research_source', dict(action='read', path='src/selected.py'), 1)
                self.assertEqual(refusal['error']['code'], code)
                self.assertTrue(refusal['error']['recoverable'])
                self.assertNotIn('SECRET', json.dumps(refusal))
        with self.assertRaisesRegex(RuntimeError, 'research_evidence_unverified'):
            broker.evidence([dict(kind='source', path='missing.py', hash='a'*64, line=1)])
        error = RuntimeError('research_source_unavailable'); error.args = ('SECRET private path',)
        with patch.object(broker.sources, 'call', side_effect=error):
            self.assertNotIn('SECRET', json.dumps(broker.call('research_source', dict(action='tree'), 1)))
        for code in ('research_source_changed', 'research_workspace_changed', 'invalid_research_read', 'cancelled'):
            with self.subTest(code=code), patch.object(broker.sources, 'call', side_effect=RuntimeError(code)):
                with self.assertRaisesRegex(RuntimeError, code):
                    broker.call('research_source', dict(action='read', path='src/selected.py'), 1)
        with patch.object(broker, 'check', side_effect=RuntimeError('research_source_unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'research_source_unavailable'):
                broker.call('research_source', dict(action='roots'), 1)

    def test_missing_knowledge_read_is_recoverable_without_inventing_evidence(self):
        self.store.changeset(0, 'object', [dict(op='put', item=dict(
            id='component', kind='entity', type='component', title='Example'))], 'Fixture')
        class Client:
            session='api:own'; token='private'; timeout=1; cancel=threading.Event(); admission=threading.RLock()
            def closed(self): return False
        broker = ResearchBroker(Client(), self.store, normalize(dict(
            operation='architecture-analyze', objectId='component', revision=1)), [])
        for action in ('read', 'research-object'):
            with self.subTest(action=action):
                result = broker.call('hub_knowledge', dict(action=action, args=dict(id='unknown-object')), 1)
                self.assertEqual(result['error']['code'], 'research_knowledge_unavailable')
                self.assertTrue(result['error']['recoverable'])
                self.assertNotIn('unknown-object', json.dumps(result))
                self.assertNotIn(('unknown-object', 1), broker.knowledge_reads)
        known = broker.call('hub_knowledge', dict(action='read', args=dict(id='component')), 1)
        self.assertEqual(known['evidenceRef'], dict(kind='knowledge', id='component', revision=1))
        for code in ('stale_object', 'unsafe_source', 'revision_conflict'):
            with self.subTest(code=code), patch('research_api.read_object', side_effect=KnowledgeError(code, 'Private detail')):
                with self.assertRaises(KnowledgeError):
                    broker.call('hub_knowledge', dict(action='read', args=dict(id='component')), 1)

    def test_rule_discovery_covers_root_ancestor_and_available_skill(self):
        skill = self.root / '.agents' / 'skills' / 'example' / 'SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\nname: example\n---\nUse evidence.\n', encoding='utf-8')
        rules = self.sources.call(dict(action='rules', path='src/selected.py'))
        self.assertEqual(rules['paths'], ['AGENTS.md', 'src/AGENTS.md'])
        self.assertEqual(rules['availableSkills'], ['.agents/skills/example/SKILL.md'])
        self.assertIn('Use evidence', self.sources.call(dict(action='read', path=rules['availableSkills'][0]))['text'])
        with self.assertRaisesRegex(RuntimeError, 'research_source_denied'):
            self.sources.call(dict(action='read', path='.agents/skills/example/script.py'))

    def test_secret_service_binary_and_traversal_paths_are_denied(self):
        paths = ['.env', '.env.example', 'credentials.json', '.git/config', '.codex/config.toml',
                 '.aws/credentials', '.local/data.json', 'secrets/api.txt', 'node_modules/pkg/index.js', 'private.pem', 'binary.exe']
        for path in paths:
            file = self.root / path; file.parent.mkdir(parents=True, exist_ok=True); file.write_text('private bytes', encoding='utf-8')
        for path in [*paths, '../other/neighbor.py', str(self.other / 'neighbor.py'), '@roots/99/neighbor.py', 'src\\selected.py']:
            with self.subTest(path=path), self.assertRaises(RuntimeError):
                self.sources.call(dict(action='read', path=path))
        tree = [item['path'] for item in self.sources.call(dict(action='tree'))['items']]
        self.assertFalse(set(paths).intersection(tree))
        (self.root / 'key.txt').write_text('-----BEGIN PRIVATE KEY-----\nprivate\n', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'research_source_denied'):
            self.sources.call(dict(action='read', path='key.txt'))

    def test_link_outside_registered_root_is_denied(self):
        try:
            (self.root / 'link.py').symlink_to(self.other / 'neighbor.py')
        except OSError:
            self.skipTest('Host cannot create symbolic link fixtures')
        with self.assertRaisesRegex(RuntimeError, 'research_source_denied'):
            self.sources.call(dict(action='read', path='link.py'))
        self.assertNotIn('link.py', [item['path'] for item in self.sources.call(dict(action='tree'))['items']])

    def test_bounded_pages_budget_and_partial_coverage_are_explicit(self):
        self.sources.MAX_FILES = 2
        result = self.sources.call(dict(action='tree'))
        self.assertEqual(len(result['items']), 2); self.assertTrue(result['partial'])
        for arguments in [dict(action='read', path='src/selected.py', lines=201), dict(action='tree', offset=-1),
                          dict(action='search', query=''), dict(action='read', path='src/selected.py', command='execute')]:
            with self.subTest(arguments=arguments), self.assertRaises(RuntimeError):
                self.sources.call(arguments)
        self.sources.MAX_READ_BYTES = 1
        with self.assertRaisesRegex(RuntimeError, 'research_read_limit'):
            self.sources.call(dict(action='read', path='src/selected.py'))

    def test_pages_and_search_share_one_charge_but_still_detect_changed_content(self):
        path = 'src/selected.py'
        size = (self.root / path).stat().st_size
        self.sources.MAX_READ_BYTES = size
        self.sources.read(path, line=1, lines=1)
        self.sources.read(path, line=2, lines=1)
        self.sources.call(dict(action='search', path=path, query='class'))
        self.assertEqual(self.sources.read_bytes, size)
        self.assertEqual(self.sources.budget()['observedFiles'], 1)
        (self.root / path).write_text('class Modified:\n', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'research_source_changed'):
            self.sources.read(path, line=1, lines=1)
        self.assertEqual(self.sources.read_bytes, size)

    def test_partial_search_leaves_capacity_for_explicit_read_and_does_not_grant_evidence(self):
        self.sources.MAX_READ_BYTES = 300
        self.sources.MAX_SEARCH_BYTES = 80
        (self.root / 'a.py').write_text('#' * 120, encoding='utf-8')
        result = self.sources.call(dict(action='search', query='class Selected'))
        self.assertTrue(result['partial'])
        self.assertEqual(result['partialReason'], 'search_byte_limit')
        self.assertLessEqual(result['budget']['usedBytes'], 80)
        self.assertNotIn('a.py', self.sources.observed)
        page = self.sources.read('src/selected.py', line=2, lines=1)
        self.sources.validate(dict(path=page['path'], hash=page['hash'], line=2))
        self.assertIn('class Selected', page['text'])
        self.assertLessEqual(self.sources.read_bytes, 300)

    def test_failed_budget_charge_is_atomic_and_a_smaller_read_remains_possible(self):
        self.sources.MAX_READ_BYTES = 60
        (self.root / 'large.py').write_text('#' * 61, encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'research_read_limit'):
            self.sources.read('large.py')
        self.assertEqual(self.sources.read_bytes, 0)
        self.assertEqual(self.sources.observed, {})
        page = self.sources.read('src/selected.py')
        self.assertIn('class Selected', page['text'])
        before = self.sources.read_bytes
        result = self.sources.call(dict(action='search', path='large.py', query='class'))
        self.assertTrue(result['partial']); self.assertEqual(result['partialReason'], 'search_byte_limit')
        self.assertEqual(self.sources.read_bytes, before)

    def test_search_and_read_verify_every_observed_file_before_skipping_a_charge(self):
        self.sources.call(dict(action='search', path='src/selected.py', query='class'))
        size = self.sources.read_bytes
        (self.root / 'src' / 'selected.py').write_text('class Changed:\n', encoding='utf-8')
        for action in ('read', 'search'):
            with self.subTest(action=action), self.assertRaisesRegex(RuntimeError, 'research_source_changed'):
                self.sources.call(dict(action=action, path='src/selected.py', **({'query':'class'} if action=='search' else {})))
        self.assertEqual(self.sources.read_bytes, size)

    def test_changed_source_and_registered_roots_invalidate_evidence(self):
        page = self.sources.call(dict(action='read', path='src/selected.py'))
        (self.root / 'src' / 'selected.py').write_text('class Newer:\n    pass\n', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'research_source_changed'):
            self.sources.validate(dict(path=page['path'], hash=page['hash'], line=1))
        with self.registry.connect() as connection:
            connection.execute('UPDATE spaces SET roots=? WHERE id=?', (json.dumps([str(self.root)]), self.project))
        with self.assertRaisesRegex(RuntimeError, 'research_workspace_changed'):
            self.sources.call(dict(action='roots'))


class ResearchContractTests(unittest.TestCase):
    def broker(self, store, identifier):
        class Client:
            session = 'api:own'; token = 'private'; timeout = 1
            cancel = threading.Event(); admission = threading.RLock()
            def closed(self): return False
            def call(self, name, arguments):
                if name != 'hub_knowledge': raise AssertionError(name)
                return getattr(store, arguments['action'])(**arguments.get('args', {}))
        return ResearchBroker(Client(), store, normalize(dict(operation='architecture-analyze',
            objectId=identifier, revision=store.context()['revision'])),
            [dict(name='hub_knowledge', inputSchema=dict(type='object', properties={}))])

    def test_large_knowledge_search_pages_and_single_items_remain_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ProjectRegistry(Path(directory) / 'data', standalone=True)
            project = registry.create('Example')['id']; store = KnowledgeStore(registry, project)
            items = [dict(id=f'item-{i:02}', kind='entity', type='component', title=f'Component {i}',
                description=('説明😀"\n' * 2000 if i == 0 else 'Объяснение \\"\n' * 250)) for i in range(12)]
            store.changeset(0, 'fixture', [dict(op='put', item=item) for item in items], 'Fixture')
            broker = self.broker(store, items[0]['id'])
            for action in ('search', 'history'):
                for limit in (None, 'many', True, 1.5, 0):
                    with self.subTest(action=action, limit=limit), self.assertRaisesRegex(RuntimeError, 'invalid_research_read'):
                        broker.call('hub_knowledge', dict(action=action, args=dict(limit=limit)), 1)
            offset, seen, pages = 0, [], []
            while True:
                page = broker.call('hub_knowledge', dict(action='search', args=dict(limit=50, offset=offset)), 1)
                self.assertLessEqual(broker.result_bytes(page), 24000)
                seen.extend(item['id'] for item in page['items']); pages.append(page)
                if not page['more']: break
                self.assertGreater(page['next'], offset); offset = page['next']
            self.assertGreater(len(pages), 1)
            self.assertEqual(seen, [item['id'] for item in items])
            self.assertTrue(pages[0]['items'][0]['partial'])
            self.assertIn('description', pages[0]['items'][0]['omittedFields'])
            self.assertNotIn(('item-01', 1), broker.knowledge_reads)
            offset, text = 0, ''
            while True:
                page = broker.call('hub_knowledge', dict(action='read', args=dict(id='item-00', limit=12000, offset=offset)), 1)
                self.assertLessEqual(broker.result_bytes(page), 24000)
                text += page['text']
                if not page['more']: break
                self.assertGreater(page['next'], offset); offset = page['next']
            self.assertEqual(json.loads(text), items[0])
            self.assertEqual(broker.evidence([page['evidenceRef']])[0]['id'], 'item-00')

    def test_history_byte_paging_preserves_filtered_store_cursor_and_large_change(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ProjectRegistry(Path(directory) / 'data', standalone=True)
            project = registry.create('Example')['id']; store = KnowledgeStore(registry, project)
            items = [dict(id='item-' + str(i).zfill(3) + '-' * 160, kind='entity', type='class', title=f'Type {i}')
                     for i in range(190)]
            store.changeset(0, 'large', [dict(op='put', item=item) for item in items], 'Fixture')
            store.changeset(1, 'other', [dict(op='put', item=dict(items[1], description='Unrelated'))], 'Other')
            store.changeset(2, 'relevant', [dict(op='put', item=dict(items[0], description='Relevant'))], 'Relevant')
            broker = self.broker(store, items[0]['id'])
            offset, revisions, pages = 0, [], []
            while True:
                page = broker.call('hub_knowledge', dict(action='history', args=dict(identifier=items[0]['id'], limit=20, offset=offset)), 1)
                self.assertLessEqual(broker.result_bytes(page), 24000)
                revisions.extend(item['revision'] for item in page['items']); pages.append(page)
                if not page['more']: break
                self.assertGreater(page['next'], offset); offset = page['next']
            self.assertEqual(revisions, [3, 1])
            self.assertTrue(pages[-1]['items'][0]['partial'])
            self.assertEqual(pages[-1]['items'][0]['changedCount'], 190)
            self.assertIn('changed', pages[-1]['items'][0]['omittedFields'])

    def test_structured_map_saves_a_separate_view_preserving_original_and_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ProjectRegistry(Path(directory) / 'data', standalone=True)
            project = registry.create('Example')['id']; store = KnowledgeStore(registry, project)
            original = dict(id='saved-map', kind='view', viewType='research', title='Original map',
                            description='Original explanation', nodeIds=['first', 'second'], orderedEdges=[])
            policy = store.context()['policy']
            policy['components'] = [dict(id='domain', title='Domain', paths=[])]
            entities = [dict(id=identifier, kind='entity', type='class', title=identifier.title(), component='domain')
                        for identifier in ('first', 'second')]
            store.changeset(0, 'fixture', [dict(op='put', item=item) for item in [*entities, original]], 'Fixture', policy=policy)
            class Client:
                session = 'api:own'; token = 'private'; timeout = 1; cancel = threading.Event(); admission = threading.RLock()
                def closed(self): return False
                def call(self, name, arguments): raise AssertionError('Unbounded dispatch')
            request = normalize(dict(operation='architecture-analyze', objectId='saved-map', template='structure-map', revision=1,
                                     scope=dict(kind='canvas', viewId='saved-map')))
            broker = ResearchBroker(Client(), store, request, [dict(name='hub_knowledge', inputSchema=dict(type='object', properties={}))])
            for identifier in ('first', 'second'):
                broker.call('hub_knowledge', dict(action='read', args=dict(id=identifier)), 1)
            result = dict(schemaVersion=1, operation='architecture-analyze', summary='Grouped participants', description='An evidenced grouping.',
                          evidence=[dict(kind='knowledge', id='saved-map', revision=1)], limitations=[],
                          view=dict(title='Grouped map', nodeIds=['first', 'second'], orderedEdges=[],
                              presentationGroups=[dict(id='group', title='Participants', nodeIds=['first', 'second'])]))
            change, reference, components = publication(store, broker, request, 'grouped', result,
                actor='api:own', task=None, stage=None, provider='fixture', model='fixture')
            store.changeset(**change)
            self.assertEqual(reference, 'knowledge/view/view:api-result:grouped')
            self.assertEqual(components, [])
            self.assertEqual(store.read('saved-map'), original)
            self.assertEqual(store.context()['policy'], policy)
            self.assertEqual([store.read(identifier)['component'] for identifier in ('first', 'second')], ['domain', 'domain'])
            self.assertEqual(store.read('view:api-result:grouped')['presentationGroups'][0]['nodeIds'], ['first', 'second'])

    def test_operation_alias_revision_provider_and_scope_validation(self):
        value = normalize(dict(id='object', template='explain', revision=0))
        self.assertEqual(value['operation'], 'architecture-analyze'); self.assertEqual(value['objectId'], 'object')
        for body in [dict(objectId='a', id='b', revision=0), dict(objectId='a', revision=True),
                     dict(objectId='a', revision=0, providerId='../private'), dict(objectId='a', revision=0, operation='implementation')]:
            with self.subTest(body=body), self.assertRaises(ChatActionError): normalize(body)
        for limit in (0, 11, True, '5'):
            with self.subTest(limit=limit), self.assertRaises(ChatActionError):
                normalize(dict(objectId='project:example', revision=0, template='decompose', subsystemLimit=limit))
        with self.assertRaises(ChatActionError):
            normalize(dict(objectId='project:example', revision=0, template='explain', subsystemLimit=5))
        self.assertEqual(normalize(dict(objectId='project:example', revision=0, template='decompose', subsystemLimit=5))['subsystemLimit'], 5)

    def test_strict_schema_duplicate_unknown_fields_and_unsafe_markdown(self):
        request = normalize(dict(operation='documentation-draft', objectId='project:example', revision=0))
        body = dict(schemaVersion=1, operation=request['operation'], summary='A summary', evidence=[], limitations=[],
                    title='Guide', markdown='# Guide', entityRefs=[])
        self.assertEqual(parse_result(json.dumps(body), request), body)
        for text in ['```json\n' + json.dumps(body) + '\n```', json.dumps(dict(body, arbitrary='value')),
                     json.dumps(body).replace('"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1'),
                     json.dumps(dict(body, markdown='[Open](javascript:alert(1))')),
                     json.dumps(dict(body, schemaVersion=True))]:
            with self.subTest(text=text), self.assertRaisesRegex(RuntimeError, 'research_result_invalid'):
                parse_result(text, request)

    def test_broker_pages_previous_document_revision_and_never_exposes_tasks_or_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = ProjectRegistry(Path(directory) / 'data', standalone=True)
            project = registry.create('Example')['id']; store = KnowledgeStore(registry, project)
            first = dict(id='guide', kind='document', title='Guide', markdown='Old version ' * 1200)
            store.changeset(0, 'first', [dict(op='put', item=first)], 'Fixture')
            store.changeset(1, 'second', [dict(op='put', item=dict(first, markdown='Newer version'))], 'Fixture')
            class Client:
                session = 'api:own'; token = 'private'; timeout = 1; cancel = threading.Event(); admission = threading.RLock()
                def closed(self): return False
                def call(self, name, arguments): raise AssertionError('Unbounded broker dispatch')
            schema = dict(name='hub_knowledge', inputSchema=dict(type='object', properties={}))
            broker = ResearchBroker(Client(), store, normalize(dict(operation='documentation-review', objectId='guide', revision=2)), [schema])
            page = broker.call('hub_knowledge', dict(action='read', args=dict(id='guide', revision=1, limit=500)), 1)
            self.assertEqual(page['revision'], 1); self.assertTrue(page['more']); self.assertLessEqual(len(page['text']), 500)
            evidence = broker.evidence([page['evidenceRef']])
            self.assertEqual(evidence[0]['path'], 'knowledge/revision/1/document/guide')
            self.assertNotIn('tasks', broker.call('hub_knowledge', dict(action='context'), 1))
            for name, arguments in [('hub_context', {}), ('hub_task', {}), ('hub_knowledge', dict(action='changeset')),
                                    ('research_source', dict(action='roots', project='other'))]:
                with self.subTest(name=name), self.assertRaises(RuntimeError): broker.call(name, arguments, 1)


if __name__ == '__main__':
    unittest.main()
