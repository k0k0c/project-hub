import json
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import closing

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from knowledge_store import KnowledgeStore, KnowledgeError, DEFAULT_POLICY, execute
from knowledge_scan import scan


class Registry:
    def __init__(self, home, root):
        self.home=home; home.mkdir()
        self.database=home/'registry.sqlite3'
        with self.connect() as c:
            c.execute('CREATE TABLE spaces(id TEXT PRIMARY KEY, roots TEXT NOT NULL)')
            c.execute('INSERT INTO spaces VALUES(?,?)',('one',json.dumps([str(root)])))
            c.execute('INSERT INTO spaces VALUES(?,?)',('two',json.dumps([str(root)])))
    def connect(self):
        db=sqlite3.connect(self.database,timeout=5,isolation_level=None)
        db.row_factory=sqlite3.Row
        return closing(db)


class KnowledgeTests(unittest.TestCase):
    def test_map_groups_validate_hierarchy_and_do_not_change_ownership(self):
        item=dict(id='map:test',kind='view',viewType='research',title='Categories',nodeIds=['class:a','class:b'],presentationGroups=[dict(id='root',title='Root'),dict(id='math',title='Math',parent='root',nodeIds=['class:a'])])
        self.assertEqual(KnowledgeStore.validate_item(item),item)
        for groups in ([dict(id='a',title='A',parent='b'),dict(id='b',title='B',parent='a')],
                       [dict(id='a',title='A',nodeIds=['foreign'])],
                       [dict(id='a',title='A',nodeIds=['class:a']),dict(id='b',title='B',nodeIds=['class:a'])],
                       [dict(id='a',title='A',parent='missing')]):
            with self.subTest(groups=groups),self.assertRaises(KnowledgeError):
                KnowledgeStore.validate_item(dict(item,presentationGroups=groups))

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)/'source'; self.root.mkdir()
        self.registry=Registry(pathlib.Path(self.temp.name)/'data',self.root)
        self.store=KnowledgeStore(self.registry,'one')
        def stop_workers():
            if hasattr(self.registry,'_knowledge_executor'): self.registry._knowledge_executor.shutdown(wait=True)
        self.addCleanup(stop_workers)
    def put(self,item,key='test',expected=0):
        return self.store.changeset(expected,key,[dict(op='put',item=item)],'Test verified changeset')
    def article(self,markdown='Example'):
        return dict(id='article',kind='document',title='Guide',markdown=markdown,entityRefs=[])
    def test_detailed_selected_object_description_is_preserved_and_bounded(self):
        item = dict(id='component',kind='entity',type='component',title='Example',description='Detailed ' * 1000)
        self.put(item)
        self.assertEqual(self.store.read('component')['description'], item['description'])
        with self.assertRaises(KnowledgeError):
            self.put(dict(item, description='x' * 12001), 'too-long', 1)
        self.assertEqual(self.store.read('component')['description'], item['description'])
    def test_conflict_does_not_lose_text_and_replay_is_idempotent(self):
        item=self.article(); self.put(item)
        self.assertEqual(self.put(item)['revision'],1)
        with self.assertRaises(KnowledgeError): self.put(self.article('overwritten'),'other',0)
        self.assertEqual(self.store.read('article')['markdown'],'Example')
        with self.assertRaises(KnowledgeError): self.put(self.article('different'),'test',0)
    def test_validate_does_not_write_and_links_are_atomic(self):
        op=dict(op='put',item=dict(id='edge',kind='relation',**{'from':'a','to':'b'},type='uses'))
        with self.assertRaises(KnowledgeError): self.store.changeset(0,'key',[op],'Missing endpoints')
        self.assertEqual(self.store.context()['revision'],0)
        self.store.changeset(0,'preview',[dict(op='put',item=self.article())],'Validate',validate_only=True)
        self.assertEqual(self.store.context()['revision'],0)
    def test_project_boundaries(self):
        self.put(self.article())
        with self.assertRaises(KnowledgeError): KnowledgeStore(self.registry,'two').read('article')
        self.assertEqual(KnowledgeStore(self.registry,'two').context()['revision'],0)

    def test_compact_source_tree_pages_preserve_revision_scope_and_escaping(self):
        items=[dict(id=str(i),kind='entity',type='class',title='Title '+str(i),component='one' if i<3 else 'other',source={'path':'src/T'+str(i)+'.java','line':1},description='x'*1000) for i in range(6)]
        self.store.changeset(0,'tree',[dict(op='put',item=i) for i in items],'Source inventory')
        first=self.store.source_tree(limit=2,component='one')
        self.assertEqual((first['revision'],first['more'],first['next']),(1,True,2))
        second=self.store.source_tree(limit=2,component='one',offset=first['next'])
        self.assertEqual([n['id'] for n in first['items']+second['items']],['0','1','2'])
        self.assertNotIn('description',first['items'][0])
        self.assertEqual(first['items'][0]['source']['path'],'src/T0.java')
        self.assertEqual(self.store.source_tree(query='%')['items'],[])
        self.assertEqual(KnowledgeStore(self.registry,'two').source_tree()['items'],[])

    def test_filtered_search_reports_total_before_pagination(self):
        entities=[dict(id=str(i),kind='entity',title='Thing '+str(i),type='class',component='a' if i<4 else 'b',entrypoint=i==0) for i in range(6)]
        edge=dict(id='edge',kind='relation',type='uses',**{'from':'0','to':'1'})
        self.store.changeset(0,'catalog',[dict(op='put',item=x) for x in entities+[edge]],'Search fixture')
        first=self.store.search(kind='entity',component='a',limit=2)
        self.assertEqual((first['total'],first['more'],first['next']),(4,True,2))
        last=self.store.search(kind='entity',component='a',offset=2,limit=2)
        self.assertEqual((last['total'],last['more'],last['next']),(4,False,None))
        self.assertEqual(self.store.search(query='Thing',type='class')['total'],6)
        self.assertEqual(self.store.search(entrypoint=True)['total'],1)
        self.assertEqual(self.store.search(kind='relation',endpoint='0')['total'],1)
        self.assertEqual(self.store.search(query='missing')['total'],0)

    def test_component_policy_rejects_ambiguous_or_cyclic_hierarchy(self):
        component=lambda identifier,parent=None: dict(id=identifier,title=identifier,paths=[],parent=parent)
        for components in ([component('a'),component('a')],[component('a','missing')],
                           [component('a','a')],[component('a','b'),component('b','a')],
                           [component('a',1)]):
            with self.assertRaises(KnowledgeError): KnowledgeStore.validate_policy(dict(DEFAULT_POLICY,components=components))
        KnowledgeStore.validate_policy(dict(DEFAULT_POLICY,components=[component('child','parent'),component('parent')]))

    def test_nested_components_assign_specific_paths_and_roll_up_unique_dependencies(self):
        (self.root/'ui').mkdir(); (self.root/'shared').mkdir()
        (self.root/'shared'/'model.py').write_text('class Model: pass\n',encoding='utf-8')
        (self.root/'ui'/'view.py').write_text('from shared.model import Model\nclass View(Model): pass\nclass Dialog(Model): pass\n',encoding='utf-8')
        components=[dict(id='app',title='Application',paths=['ui/']),
                    dict(id='shared',title='Shared',paths=['shared/']),
                    dict(id='ui',title='UI',paths=['ui/'],parent='app')]
        # The nested component wins an equally specific path, independent of
        # policy declaration order; unrelated ties retain declaration order.
        result=scan(self.root,dict(components=components))
        ui_files=[x for x in result['entities'] if x.get('source',{}).get('path')=='ui/view.py']
        self.assertTrue(ui_files); self.assertTrue(all(x['component']=='ui' for x in ui_files))
        self.assertEqual(next(x for x in result['entities'] if x['id']=='ui')['parent'],'app')
        self.assertTrue(any(x['type']=='contains' and x['from']=='app' and x['to']=='ui' for x in result['relations']))
        dependencies=[x for x in result['relations'] if x['type']=='depends-on']
        self.assertEqual({(x['from'],x['to']) for x in dependencies},{('ui','shared'),('app','shared')})
        # Two inheritance facts and one shared file import, even though each
        # class parser recorded that same import.
        self.assertTrue(all(x['count']==3 for x in dependencies))
        self.assertTrue(all(len(x['evidence'])<=10 for x in dependencies))

    def test_component_paths_respect_directory_and_file_boundaries(self):
        for directory in ['ui','ui-tests','uix']:
            (self.root/directory).mkdir()
            (self.root/directory/'view.py').write_text('class View: pass\n',encoding='utf-8')
        result=scan(self.root,dict(components=[dict(id='ui',title='UI',paths=['ui']),
                                               dict(id='test',title='Test file',paths=['ui-tests/view.py'])]))
        files={x['source']['path']:x['component'] for x in result['entities'] if x.get('type')=='file'}
        self.assertEqual(files,{'ui/view.py':'ui','ui-tests/view.py':'test','uix/view.py':None})
    def test_history_restore_creates_new_revision(self):
        self.put(self.article('old'))
        self.put(self.article('new'),'new',1)
        self.assertEqual(self.store.read('article',1)['markdown'],'old')
        self.store.restore('article',1,2,'restore')
        self.assertEqual(self.store.read('article')['markdown'],'old')
        self.assertEqual(self.store.context()['revision'],3)
        self.assertEqual(self.store.read('article',2)['markdown'],'new')
        with self.assertRaises(KnowledgeError): self.store.read('article',9999)

    def test_history_byte_cursor_does_not_skip_revisions(self):
        for i in range(40): self.store.changeset(i,'change-'+str(i),[],'Причина '*350)
        revisions=[]; offset=0
        while True:
            page=self.store.history(offset=offset,limit=100)
            self.assertLess(len(json.dumps(page,ensure_ascii=False).encode('utf-8')),190000)
            revisions.extend(x['revision'] for x in page['items'])
            if not page['more']: break
            self.assertGreater(page['next'],offset); offset=page['next']
        self.assertEqual(revisions,list(range(40,0,-1)))

    def test_publication_and_policy_cannot_overflow_journal_or_context(self):
        payload=dict(id='event',kind='note',taskId='task',detail='Текст '*10000,
                     evidence=[dict(path='knowledge/document/doc:'+str(i),label='Название '*1000) for i in range(500)])
        compact=self.store.publication_payload(payload)
        self.assertLess(len(json.dumps(compact,ensure_ascii=False).encode('utf-8')),64000)
        self.assertIn('500 документов',compact['detail'])
        for policy in [dict(DEFAULT_POLICY,components=1),dict(DEFAULT_POLICY,components=[dict(id='a',title='a'*301,paths=[])]),dict(DEFAULT_POLICY,sections=['x'*300]*1000)]:
            with self.assertRaises(KnowledgeError): self.store.changeset(0,'invalid',[],'Test',policy=policy)
        self.assertEqual(self.store.context()['revision'],0)

    def test_public_articles_with_same_title_keep_distinct_contents(self):
        items=[dict(self.article('One'),id='one',visibility='public-approved'),dict(self.article('Two'),id='two',visibility='public-approved')]
        self.store.changeset(0,'public',[dict(op='put',item=x) for x in items],'Two reviewed articles')
        export=self.store.export(public=True)
        self.assertEqual(len({x['id'] for x in export['items']}),2)
    def test_import_survives_removal_with_assets_and_dedup(self):
        (self.root/'image.png').write_bytes(b'original-image-bytes')
        (self.root/'guide.md').write_text('# Guide\n![sample](image.png)',encoding='utf-8')
        (self.root/'duplicate.md').write_bytes((self.root/'guide.md').read_bytes())
        preview=self.store.import_preview(['guide.md','duplicate.md'])
        self.assertEqual([x['action'] for x in preview['items']],['create','duplicate'])
        self.store.import_apply(preview['id'],0,'import')
        item=self.store.read(preview['items'][0]['item']['id'])
        for path in self.root.iterdir(): path.unlink()
        self.assertIn('knowledge-asset:',item['markdown'])
        self.assertEqual(self.store.read_blob(item['sources'][0]['assets'][0]['hash']),b'original-image-bytes')
    def test_reimport_requires_review_and_keeps_manual_edits(self):
        path=self.root/'guide.md'; path.write_text('# Guide\nsource',encoding='utf-8')
        preview=self.store.import_preview(['guide.md']); self.store.import_apply(preview['id'],0,'import')
        item=self.store.read(preview['items'][0]['item']['id']); item['markdown']='manual correction'
        self.put(item,'manual',1)
        path.write_text('# Guide\nchanged source',encoding='utf-8')
        preview=self.store.import_preview(['guide.md']); self.assertEqual(preview['items'][0]['action'],'review')
        self.store.import_apply(preview['id'],2,'not-selected')
        self.assertEqual(self.store.read(item['id'])['markdown'],'manual correction')
    def test_backup_restores_without_source_tree(self):
        self.put(self.article())
        backup=self.store.backup(); shutil.rmtree(self.root)
        other=KnowledgeStore(self.registry,'two'); other.restore_backup(backup)
        self.assertEqual(other.read('article')['markdown'],'Example')
        with self.assertRaises(KnowledgeError): other.restore_backup(backup)
    def test_private_dependencies_block_public_export(self):
        item=dict(self.article('![private](file.png)'),visibility='public-approved')
        self.put(item)
        with self.assertRaises(KnowledgeError): self.store.export(public=True)
    def test_architecture_does_not_accept_method_catalog(self):
        with self.assertRaises(KnowledgeError): self.put(dict(id='type',kind='entity',title='Type',methods=['method']))
    def test_impact_distinguishes_behavior_from_structure(self):
        impact=self.store.impact(change={'cosmetic':True})
        self.assertEqual(impact['architecture'],'no-impact'); self.assertEqual(impact['documentation'],'no-impact')
        impact=self.store.impact(change={'behavior':True,'noStructuralImpact':True})
        self.assertEqual(impact['architecture'],'no-impact'); self.assertEqual(impact['documentation'],'review-required')
        self.store.impact(change={'structure':True,'reason':'New component'},task='task',record=True)
        self.assertEqual(self.store.context()['reviews'][0]['state'],'review-needed')
        self.store.impact(change={'structure':True,'reason':'Updated linked articles','knowledgeUpdated':True},task='task',record=True)
        self.assertEqual(self.store.context()['reviews'][0]['state'],'resolved')

    def test_export_is_deterministic_and_timeline_delivery_failure_is_visible(self):
        self.store.changeset(0,'timeline',[dict(op='put',item=self.article())],'Task article',task='task',stage='docs')
        self.assertEqual(self.store.context()['publicationPending'],1)
        self.assertEqual(self.store.export_bundle(),self.store.export_bundle())
        self.assertEqual(self.store.history()['items'][0]['task'],'task')
        self.assertEqual(self.store.history()['items'][0]['codeRevision']['basis'],'source-revision-unavailable')
    def test_api_rejects_internal_override_and_actor_spoofing(self):
        for field in ('_scan','actor'):
            with self.assertRaises(KnowledgeError): execute(self.registry,'one','changeset',{field:True})

    def test_malformed_operations_and_sources_are_rejected_before_revision(self):
        for operation in [dict(op='delete'),dict(op='delete',id=None),dict(op='delete',id=[]),dict(op='put',item=dict(self.article(),sources=[None]))]:
            with self.assertRaises(KnowledgeError): self.store.changeset(0,'invalid',[operation],'Validate malformed item')
        self.assertEqual(self.store.context()['revision'],0)

    def test_public_export_excludes_internal_identity_and_raw_html(self):
        self.put(dict(self.article('Safe public text'),visibility='public-approved'))
        exported=self.store.export(public=True)
        self.assertNotIn('project',exported); self.assertNotIn('revision',exported)
        self.assertNotEqual(exported['items'][0]['id'],'article')
        self.put(dict(self.article('<img src="file:///private.png">'),visibility='public-approved'),'html',1)
        with self.assertRaises(KnowledgeError): self.store.export(public=True)

    def test_second_registered_root_scan_and_import_are_distinct(self):
        second=self.root.parent/'second'; second.mkdir()
        with self.registry.connect() as c: c.execute('UPDATE spaces SET roots=? WHERE id=?',(json.dumps([str(self.root),str(second)]),'one'))
        self.store=KnowledgeStore(self.registry,'one')
        for root in (self.root,second): (root/'model.py').write_text('class Model: pass',encoding='utf-8')
        (second/'guide.md').write_text('# Multi-root guide',encoding='utf-8')
        preview=self.store.import_preview(['@roots/1/guide.md'])
        self.store.import_apply(preview['id'],0,'multi-import')
        job=self.store.start_scan(); self.registry._knowledge_executor.shutdown(wait=True)
        self.assertEqual(self.store.job(job['id'])['state'],'ready')
        classes=[x for x in self.store.search(kind='entity')['items'] if x.get('type')=='class']
        self.assertEqual(len({x['id'] for x in classes}),2)
        self.assertTrue(any(x['source']['path']=='@roots/1/model.py' for x in classes))

    def test_configured_scan_roots_do_not_mix_attached_projects(self):
        second=self.root.parent/'attached'; second.mkdir()
        with self.registry.connect() as c: c.execute('UPDATE spaces SET roots=? WHERE id=?',(json.dumps([str(self.root),str(second)]),'one'))
        self.store=KnowledgeStore(self.registry,'one')
        (self.root/'model.py').write_text('class OwnProject: pass',encoding='utf-8')
        (second/'foreign.py').write_text('class OtherProject: pass',encoding='utf-8')
        self.store.changeset(0,'roots',[],'Scan only primary source',policy=dict(DEFAULT_POLICY,scanRoots=['0']))
        job=self.store.start_scan(); self.registry._knowledge_executor.shutdown(wait=True)
        self.assertEqual(self.store.job(job['id'])['state'],'ready')
        titles=[x['title'] for x in self.store.search(kind='entity')['items']]
        self.assertIn('OwnProject',titles); self.assertNotIn('OtherProject',titles)
        with self.assertRaises(KnowledgeError): self.store.changeset(self.store.context()['revision'],'missing',[],'Invalid root',policy=dict(DEFAULT_POLICY,scanRoots=['2']))
    def test_scan_preserves_authored_description_and_marks_removed(self):
        (self.root/'model.py').write_text('class Base: pass\nclass Derived(Base): pass\n',encoding='utf-8')
        job=self.store.start_scan()
        self.registry._knowledge_executor.shutdown(wait=True)
        self.assertEqual(self.store.job(job['id'])['state'],'ready')
        cls=next(x for x in self.store.search(kind='entity')['items'] if x.get('title')=='Derived')
        cls['description']='Author explains its role'; self.put(cls,'annotate',self.store.context()['revision'])
        delattr(self.registry,'_knowledge_executor')
        (self.root/'model.py').write_text('class Base: pass\n',encoding='utf-8')
        self.store.start_scan(); self.registry._knowledge_executor.shutdown(wait=True)
        self.assertEqual(self.store.read(cls['id'])['description'],'Author explains its role')
        self.assertTrue(self.store.read(cls['id'])['removed'])

    def test_plain_source_scan_without_git_retains_fingerprint_and_optional_provenance(self):
        from unittest.mock import patch
        (self.root / '.svn').mkdir()
        (self.root / 'model.py').write_text('class Model: pass\n', encoding='utf-8')
        initial = self.store.start_scan()
        self.registry._knowledge_executor.shutdown(wait=True)
        expected = self.store.job(initial['id'])['fingerprint']
        delattr(self.registry, '_knowledge_executor')
        with patch('version_control.shutil.which', return_value=None):
            job = self.store.start_scan()
            self.registry._knowledge_executor.shutdown(wait=True)
            result = self.store.job(job['id'])
            self.assertEqual(result['state'], 'ready', result)
            self.assertEqual(result['fingerprint'], expected)
        history = self.store.history()['items']
        change = next(row for row in history if row['codeRevision'].get('basis') == 'local-source-scan')
        self.assertEqual(change['codeRevision']['heads'], [None])

    def test_partial_parse_retains_prior_facts_without_false_removal(self):
        path=self.root/'model.py'; path.write_text('class Model: pass',encoding='utf-8')
        self.store.start_scan(); self.registry._knowledge_executor.shutdown(wait=True)
        cls=next(x for x in self.store.search(kind='entity')['items'] if x.get('title')=='Model')
        delattr(self.registry,'_knowledge_executor')
        path.write_text('class Model(',encoding='utf-8')
        job=self.store.start_scan(); self.registry._knowledge_executor.shutdown(wait=True)
        self.assertEqual(self.store.job(job['id'])['state'],'partial')
        self.assertFalse(self.store.read(cls['id']).get('removed'))
        self.assertEqual(self.store.read(cls['id'])['analysisStatus'],'stale')

    def test_changed_source_during_analysis_is_not_published(self):
        from unittest.mock import patch
        first=scan(self.root); second=dict(first,fingerprint='changed')
        with patch('knowledge_scan.scan',side_effect=[first,second]):
            job=self.store.start_scan(); self.registry._knowledge_executor.shutdown(wait=True)
        self.assertEqual(self.store.job(job['id'])['state'],'stale')
        self.assertEqual(self.store.context()['revision'],0)

    def test_invalid_backup_cannot_create_partial_database(self):
        self.put(self.article()); backup=self.store.backup()
        backup['items'][0]['markdown']='tampered current state'
        other=KnowledgeStore(self.registry,'two')
        with self.assertRaises(KnowledgeError): other.restore_backup(backup)
        self.assertEqual(other.context()['revision'],0)
        self.assertEqual(other.search()['items'],[])


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
    def test_python_shallow_graph_and_cached_entrypoint(self):
        (self.root/'sample.py').write_text('class Base: pass\nclass Child(Base):\n def ignored(self, x): return x\nif __name__ == "__main__": pass\n',encoding='utf-8')
        first=scan(self.root); second=scan(self.root,previous=first['cache'])
        self.assertEqual(first['fingerprint'],second['fingerprint'])
        self.assertEqual(second['counts']['reused'],1)
        self.assertTrue(next(x for x in second['entities'] if x['type']=='file')['entrypoint'])
        self.assertTrue(any(x['type']=='extends' for x in first['relations']))
        self.assertFalse(any('methods' in x or 'parameters' in x for x in first['entities']))
    def test_unsupported_language_is_explicit_and_build_dirs_excluded(self):
        (self.root/'module.rs').write_text('struct Foo {}',encoding='utf-8')
        (self.root/'build').mkdir(); (self.root/'build'/'secret.py').write_text('class Hidden: pass',encoding='utf-8')
        result=scan(self.root)
        self.assertEqual(result['capabilities']['rust'],['files'])
        self.assertEqual(result['counts']['files'],1)

    @unittest.skipUnless(shutil.which('java'),'Local JDK adapter unavailable')
    def test_duplicate_java_declarations_are_distinct_and_not_falsely_resolved(self):
        for directory in ('app1','app2'):
            (self.root/directory).mkdir()
            (self.root/directory/'Base.java').write_text('package same; class Base {}',encoding='utf-8')
        (self.root/'Child.java').write_text('package same; class Child extends Base {}',encoding='utf-8')
        result=scan(self.root)
        bases=[x for x in result['entities'] if x['title']=='Base' and x['type']=='class']
        self.assertEqual(len({x['id'] for x in bases}),2)
        edge=next(x for x in result['relations'] if x['type']=='extends')
        self.assertTrue(any(x['id']==edge['to'] and x['type']=='external' for x in result['entities']))
    @unittest.skipUnless(shutil.which('java'),'Local JDK adapter unavailable')
    def test_java_types_interfaces_entrypoint_and_local_dependencies(self):
        (self.root/'Example.java').write_text('package example; interface API {} class Base {} class Example extends Base implements API { Base field; public static void main(String[] args) { new Example(); } void hidden(int p) {} }',encoding='utf-8')
        result=scan(self.root)
        self.assertEqual(result['status'],'ready',result['diagnostics'])
        self.assertEqual(result['counts']['types'],3)
        self.assertTrue(any(x['title']=='Example' and x['entrypoint'] for x in result['entities']))
        self.assertEqual({'extends','implements','uses'} - {x['type'] for x in result['relations']},set())
        self.assertFalse(any(x.get('title')=='hidden' for x in result['entities']))


if __name__=='__main__': unittest.main()
