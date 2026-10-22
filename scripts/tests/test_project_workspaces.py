"""Draft focused checks on real temporary standalone registries only."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from knowledge_store import KnowledgeStore
from project_registry import ProjectRegistry, ProjectRevisionConflict
from project_workspaces import Workspaces, WorkspaceError


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.registry = ProjectRegistry(self.base / 'hub', standalone=True)
        self.project = self.registry.create('Example')['id']
        self.workspaces = Workspaces(self.registry, runtime_roots=[self.base / 'runtime'])

    def folder(self, name):
        path = self.base / name
        path.mkdir()
        return str(path)

    def change(self, action, expected, **arguments):
        return self.workspaces.change(self.project, action, expected=expected, request_id=uuid.uuid4().hex, **arguments)

    def test_rootless_tasks_and_documents_then_stable_add_relocate_disable(self):
        knowledge = KnowledgeStore(self.registry, self.project)
        document = dict(id='guide', kind='document', title='Guide', markdown='Authored text')
        knowledge.changeset(0, 'guide', [dict(op='put', item=document)], 'Authored guide')
        journal = self.registry.store(self.project)
        journal.record(dict(kind='task.created', taskId='example', title='Example',
                            patch=dict(title='Example', status='planned', stages=[])))
        self.assertEqual(self.workspaces.catalog(self.project)['items'], [])
        self.assertFalse(knowledge.context()['capabilities']['workspaceConfigured'])
        first = self.change('add', 1, root=self.folder('first'))
        second = self.change('add', 2, root=self.folder('second'))
        original_refs = KnowledgeStore(self.registry, self.project).context()['rootRefs']
        moved = self.change('relocate', 3, workspace=first['workspace']['id'], root=self.folder('moved'))
        self.assertEqual(moved['roots'][1], second['roots'][1])
        self.assertEqual(moved['workspace']['id'], first['workspace']['id'])
        self.assertEqual(moved['workspace']['descriptor']['rootRef'], '0')
        disabled = self.change('enable', 4, workspace=first['workspace']['id'], enabled=False)
        self.assertEqual(disabled['roots'], moved['roots'])
        self.assertEqual([(r['id'],r['prefix']) for r in KnowledgeStore(self.registry, self.project).context()['rootRefs']], [(r['id'],r['prefix']) for r in original_refs])
        catalog = self.workspaces.catalog(self.project)
        by_ref = {item['descriptor']['rootRef']: item for item in catalog['items']}
        self.assertFalse(by_ref['0']['capabilities']['source'])
        self.assertTrue(by_ref['1']['capabilities']['source'])
        self.assertEqual(knowledge.read('guide')['markdown'], 'Authored text')
        self.assertEqual(len(knowledge.history()['items']), 1)
        self.assertEqual(journal.snapshot()['tasks'][0]['id'], 'example')

    def test_exact_request_replay_survives_missing_folder_and_stale_revision(self):
        root = self.folder('replay')
        identifier = uuid.uuid4().hex
        result = self.workspaces.change(self.project, 'add', expected=1, request_id=identifier, root=root)
        Path(root).rmdir()
        self.assertEqual(self.workspaces.change(self.project, 'add', expected=1, request_id=identifier, root=root), result)
        with self.assertRaises(ValueError):
            self.workspaces.change(self.project, 'add', expected=2, request_id=identifier, root=root)
        with self.assertRaises(ProjectRevisionConflict):
            self.change('add', 1, root=self.folder('stale'))
        self.assertEqual(self.workspaces.catalog(self.project)['revision'], 2)

    def test_concurrent_cas_allows_only_one_write(self):
        candidates = [self.folder('a'), self.folder('b')]
        def attempt(root):
            try:
                return self.change('add', 1, root=root)
            except ProjectRevisionConflict:
                return None
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(attempt, candidates))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(len(self.workspaces.catalog(self.project)['rootRefs']), 1)
        with self.registry.connect() as connection:
            count = connection.execute('SELECT COUNT(*) FROM project_requests').fetchone()[0]
        self.assertEqual(count, 2)  # project creation + one workspace receipt

    def test_legacy_workspace_id_and_rootref_preserved(self):
        roots = [self.folder('old-a'), self.folder('old-b')]
        self.project = self.registry.create('Legacy example', roots)['id']
        before = self.workspaces.catalog(self.project)
        selected = next(item for item in before['items'] if item['descriptor']['rootRef']=='1')
        moved = self.change('relocate', 1, workspace=selected['id'], root=self.folder('new-b'))
        self.assertEqual(moved['workspace']['id'], selected['id'])
        self.assertEqual(moved['workspace']['descriptor']['rootRef'], '1')
        self.assertEqual(moved['roots'][0], roots[0])
        with self.registry.connect() as connection:
            descriptor = json.loads(connection.execute('SELECT descriptor FROM project_workspaces WHERE id=?', (selected['id'],)).fetchone()[0])
        self.assertEqual(descriptor['rootRef'], '1')

    def test_imported_roots_without_metadata_materialize_unique_legacy_ids(self):
        roots = [self.folder('import-a')]
        self.project = self.registry.create('Imported', roots)['id']
        other = self.registry.create('Other imported', [self.folder('import-b')])['id']
        with self.registry.connect() as connection:
            connection.execute('DELETE FROM project_workspaces WHERE project IN (?,?)', (self.project, other))
        item = self.workspaces.catalog(self.project)['items'][0]
        other_item = self.workspaces.catalog(other)['items'][0]
        self.assertNotEqual(item['id'], other_item['id'])
        self.change('enable', 1, workspace=item['id'], enabled=False)
        after = self.workspaces.catalog(self.project)['items'][0]
        self.assertEqual(after['id'], item['id'])
        self.assertFalse(after['enabled'])
        self.assertEqual(after['descriptor']['rootRef'], '0')

    def test_missing_folder_and_metadata_repository_have_separate_capabilities(self):
        root = self.folder('available')
        (Path(root) / '.git').mkdir()
        result = self.change('add', 1, root=root)
        item = self.workspaces.catalog(self.project)['items'][0]
        self.assertTrue(item['capabilities']['source'])
        self.assertTrue(item['capabilities']['git']['repository'])
        self.assertEqual(item['capabilities']['lsp']['state'], 'not-checked')
        (Path(root) / '.git').rmdir()
        Path(root).rmdir()
        with self.registry.connect() as connection:
            connection.execute('INSERT INTO project_workspaces VALUES(?,?,?,?,1,1,0)',
                               ('repository', self.project, 'repository', json.dumps(dict(url='https://example.invalid/repository', root=root))))
        catalog = self.workspaces.catalog(self.project)
        local = next(value for value in catalog['items'] if value['kind']=='local')
        external = next(value for value in catalog['items'] if value['kind']=='repository')
        self.assertEqual(local['availability'], 'workspace_missing')
        self.assertFalse(local['capabilities']['source'])
        self.assertEqual(external['availability'], 'metadata-only')
        self.assertFalse(external['capabilities']['source'])
        with self.assertRaises(WorkspaceError):
            self.change('enable', 2, workspace=result['workspace']['id'], enabled=True)
        disabled = self.change('enable', 2, workspace=result['workspace']['id'], enabled=False)
        self.assertEqual(disabled['roots'], [root])

    def test_protected_missing_relative_and_duplicate_paths_are_rejected(self):
        runtime = self.folder('runtime')
        for root in (str(self.registry.home), str(self.base), runtime, 'relative', str(self.base/'missing')):
            with self.subTest(root=root), self.assertRaises(WorkspaceError):
                self.change('add', 1, root=root)
        root = self.folder('source')
        self.change('add', 1, root=root)
        with self.assertRaises(WorkspaceError):
            self.change('add', 2, root=root)
        self.assertEqual(self.workspaces.catalog(self.project)['revision'], 2)

    def test_disabled_source_ref_is_denied_without_renumbering_or_losing_facts(self):
        from knowledge_store import KnowledgeError
        first=self.folder('source-a'); second=self.folder('source-b')
        for folder in (first,second):
            (Path(folder)/'model.py').write_text('class Example: pass',encoding='utf-8')
        a=self.change('add',1,root=first);self.change('add',2,root=second)
        knowledge=KnowledgeStore(self.registry,self.project)
        knowledge.start_scan();self.registry._knowledge_executor.shutdown(wait=True)
        facts=knowledge.search(kind='entity')['items']
        self.change('enable',3,workspace=a['workspace']['id'],enabled=False)
        with self.assertRaises(KnowledgeError):knowledge.source_location('model.py')
        self.assertEqual(knowledge.source_location('@roots/1/model.py')[1],Path(second)/'model.py')
        delattr(self.registry,'_knowledge_executor')
        knowledge.start_scan();self.registry._knowledge_executor.shutdown(wait=True)
        primary=[fact for fact in facts if fact.get('source',{}).get('path')=='model.py']
        self.assertTrue(primary)
        for fact in primary:
            after=knowledge.read(fact['id'])
            self.assertFalse(after.get('removed',False))
            self.assertEqual(after['analysisStatus'],'unavailable')

    def test_scanned_source_reader_is_bounded_and_rejects_changed_code(self):
        from knowledge_store import KnowledgeError
        folder=self.folder('read-source');file=Path(folder)/'model.py'
        file.write_text('class Example: pass',encoding='utf-8')
        self.change('add',1,root=folder)
        knowledge=KnowledgeStore(self.registry,self.project)
        knowledge.start_scan();self.registry._knowledge_executor.shutdown(wait=True)
        item=next(row for row in knowledge.search(kind='entity')['items'] if row.get('type')=='file')
        result=knowledge.source_read(item['id'],2,5)
        self.assertEqual(result['text'],'ass E');self.assertEqual(result['next'],7)
        file.write_text('class Changed: pass',encoding='utf-8')
        with self.assertRaises(KnowledgeError) as caught:knowledge.source_read(item['id'])
        self.assertEqual(caught.exception.body['error'],'source_changed')
        self.change('enable',2,workspace=self.workspaces.catalog(self.project)['items'][0]['id'],enabled=False)
        with self.assertRaises(KnowledgeError) as caught:knowledge.source_read(item['id'])
        self.assertEqual(caught.exception.body['error'],'workspace_unavailable')

    def test_symlink_is_rejected_when_supported(self):
        target = self.folder('target')
        linked = self.base / 'linked'
        try:
            linked.symlink_to(target, target_is_directory=True)
        except OSError:
            self.skipTest('Native environment cannot create test symlinks')
        with self.assertRaises(WorkspaceError):
            self.change('add', 1, root=str(linked))


if __name__ == '__main__':
    unittest.main()
