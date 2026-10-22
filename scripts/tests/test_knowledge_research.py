import json
import pathlib
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from knowledge_store import KnowledgeStore, KnowledgeError, execute
from knowledge_research import explore, fingerprint, capabilities, read_object
from scripts.tests.test_knowledge_store import Registry


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.temp.name)/'code'
        self.root.mkdir()
        self.registry=Registry(pathlib.Path(self.temp.name)/'data',self.root)
        self.store=KnowledgeStore(self.registry,'one')
        self.items=[{'id':'group','kind':'entity','type':'component','title':'Group'},
                    {'id':'child','kind':'entity','type':'component','title':'Child','parent':'group'},
                    {'id':'file','kind':'entity','type':'file','title':'A.java','component':'group','source':{'path':'A.java','line':1}},
                    {'id':'a','kind':'entity','type':'class','title':'A','component':'group','source':{'path':'A.java','line':1}},
                    {'id':'b','kind':'entity','type':'class','title':'B','component':'child'},
                    {'id':'ab','kind':'relation','type':'uses','from':'a','to':'b'},
                    {'id':'fa','kind':'relation','type':'contains','from':'file','to':'a'}]
        (self.root/'A.java').write_text('class A {}',encoding='utf-8')
        self.store.changeset(0,'fixture',[{'op':'put','item':i} for i in self.items],'Test')
    def tearDown(self): self.temp.cleanup()
    def test_directory_scope_is_safe_and_does_not_add_synthetic_graph_node(self):
        folder=self.root/'src';folder.mkdir()
        item=dict(id='inside',kind='entity',type='class',title='Inside',source={'path':'src/Inside.java','line':1})
        self.store.changeset(1,'directory-fixture',[{'op':'put','item':item}],'Directory fixture')
        identifier='directory:src'
        self.assertEqual(read_object(self.store,identifier)['type'],'directory')
        self.assertEqual([op['id'] for op in capabilities(self.store,identifier)['operations']],['own-code'])
        job=self.wait(execute(self.registry,'one','research',{'query':self.query('own-code',identifier,catalogOnly=True)}))
        self.assertEqual(job['state'],'done',job)
        page=execute(self.registry,'one','research-result',{'id':job['result']})
        self.assertEqual({n['id'] for n in page['items']},{'inside'})
        for unsafe in ('directory:../escape','directory:.git','directory:A.java'):
            with self.assertRaises(KnowledgeError):read_object(self.store,unsafe)
    def query(self,op,id='a',**extra):return dict(dict(operation=op,id=id,depth=1,representation='symbols'),**extra)
    def wait(self,job):
        for _ in range(200):
            job=self.store.job(job['id'])
            if job['state'] not in {'queued','running'}:return job
            time.sleep(.01)
        self.fail('research timed out')
    def test_hierarchy_and_own_code_are_different_scopes(self):
        children=explore(self.items,self.query('children','group'))
        self.assertEqual({n['id'] for n in children['nodes']},{'group','child'})
        own=explore(self.items,self.query('own-code','group'))
        self.assertEqual({n['id'] for n in own['nodes']},{'group','a'})
    def test_saved_composition_never_scans_sources_and_cache_tracks_catalog(self):
        with patch('knowledge_research.fingerprint',side_effect=AssertionError('Composition must not walk sources')):
            for operation,identifier in [('children','group'),('own-code','group'),('definitions','file'),('outgoing','a')]:
                job=self.wait(execute(self.registry,'one','research',{'query':self.query(operation,identifier,catalogOnly=True)}))
                self.assertEqual(job['state'],'done',job)
                page=execute(self.registry,'one','research-result',{'id':job['result']})
                self.assertFalse(page['stale']);self.assertEqual(page['fingerprintScope'],'catalog')
                actual={item['id'] for item in page['items']}
                expected=explore(self.items,self.query(operation,identifier))
                self.assertEqual(actual,{item['id'] for item in expected['nodes']+expected['relations']})
            repeated=self.wait(execute(self.registry,'one','research',{'query':self.query('children','group',catalogOnly=True)}))
            self.assertTrue(repeated['cached'])
            (self.root/'A.java').write_text('class Edited {}',encoding='utf-8')
            self.assertFalse(execute(self.registry,'one','research-result',{'id':repeated['result']})['stale'])
            self.store.changeset(1,'new-child',[{'op':'put','item':dict(id='new',kind='entity',type='component',title='New',parent='group')}],'Update composition')
            self.assertTrue(execute(self.registry,'one','research-result',{'id':repeated['result']})['stale'])
    def test_file_is_optional_and_contains_not_a_dependency(self):
        result=explore(self.items,self.query('definitions','file'))
        self.assertEqual([n['id'] for n in result['nodes']],['a'])
        self.assertFalse(result['relations'])
        result=explore(self.items,self.query('outgoing'))
        self.assertEqual([e['id'] for e in result['relations']],['ab'])
        result=explore(self.items,self.query('incoming'))
        self.assertFalse(result['relations'])

    def test_symbol_steps_cross_hidden_files_and_stop_at_next_symbol(self):
        bridge=[dict(id=i,kind='entity',type='file',title=i,source={'path':i}) for i in ('one.json','two.json')]
        bridge += [dict(id='c',kind='entity',type='class',title='C')]
        for identifier,a,b,kind in [('a1','a','one.json','uses'),('12','one.json','two.json','imports'),('2b','two.json','b','contains'),('cycle','two.json','one.json','imports'),('bc','b','c','uses')]:
            bridge.append(dict(id=identifier,kind='relation',type=kind,**{'from':a,'to':b}))
        items=[i for i in self.items if i['id']!='ab']+bridge
        self.store.changeset(1,'bridges',[{'op':'delete','id':'ab'}]+[{'op':'put','item':i} for i in bridge],'Bridge fixture')
        direct=explore(items,self.query('outgoing'))
        self.assertEqual({n['id'] for n in direct['nodes']},{'a','b'})
        relation=direct['relations'][0]
        self.assertEqual((relation['from'],relation['to'],relation['type']),('a','b','via-files'))
        self.assertEqual([e['id'] for e in relation['pathEdges']],['a1','12','2b'])
        self.assertEqual([n['id'] for n in relation['via']],['one.json','two.json'])
        self.assertEqual(relation['provenance'],'inferred')
        self.store.validate_item(relation)
        for depth in (1,2):
            job=self.wait(execute(self.registry,'one','research',{'query':self.query('outgoing',depth=depth,catalogOnly=True)}))
            page=execute(self.registry,'one','research-result',{'id':job['result']})
            self.assertEqual({n['id'] for n in page['items'] if n['kind']=='entity'},{'a','b'} if depth==1 else {'a','b','c'})
        next_step=explore(items,self.query('outgoing','b'))
        self.assertEqual({n['id'] for n in next_step['nodes']},{'b','c'})
        # Incoming traversal follows actual edge direction, never reverses contains.
        reverse_items=[{**i,'type':'uses'} if i['id']=='2b' else i for i in items]
        incoming=explore(reverse_items,self.query('incoming','b'))
        self.assertEqual({n['id'] for n in incoming['nodes']},{'a','b'})
        self.assertEqual((incoming['relations'][0]['from'],incoming['relations'][0]['to']),('a','b'))
        visible_files=explore(items,self.query('outgoing',representation='symbols-in-files'))
        self.assertIn('one.json',{n['id'] for n in visible_files['nodes']})
        self.assertNotIn('b',{n['id'] for n in visible_files['nodes']})
        # A saved projected chain still carries its facts and can be researched.
        job=self.wait(execute(self.registry,'one','research',{'query':self.query('outgoing',catalogOnly=True)}))
        page=execute(self.registry,'one','research-result',{'id':job['result']})
        saved=execute(self.registry,'one','research-save',dict(expected=2,key='bridge-map',title='Bridge',nodeIds=[n['id'] for n in page['items'] if n['kind']=='entity'],edgeIds=[n['id'] for n in page['items'] if n['kind']=='relation'],resultId=job['result']))
        self.assertTrue(saved['id'])
        projected=[n for n in direct['nodes']]+direct['relations']
        restored=explore(projected,self.query('outgoing'))
        self.assertEqual({n['id'] for n in restored['nodes']},{'a','b'})
        self.assertEqual(restored['relations'][0]['pathEdges'],relation['pathEdges'])

    def test_catalog_depth_is_composable_for_symbol_kinds_and_directions(self):
        for kind in ('class','interface','record','enum','type','method','function','constructor','field','property','variable','constant','enum-member','type-parameter','symbol','module','namespace','package'):
            for op,edge_kind in [('incoming','uses'),('outgoing','uses'),('base-types','extends'),('implementations','extends'),('definitions','contains')]:
                with self.subTest(kind=kind,operation=op):
                    nodes=[dict(id=i,kind='entity',type=kind,title=i) for i in ('x','y','z')]
                    reverse=op in {'incoming','implementations'}
                    edges=[dict(id=a+b,kind='relation',type=edge_kind,**{'from':b if reverse else a,'to':a if reverse else b}) for a,b in [('x','y'),('y','z')]]
                    one=explore(nodes+edges,self.query(op,'x'))
                    two=explore(nodes+edges,self.query(op,'x',depth=2))
                    continuation=explore(nodes+edges,self.query(op,'y'))
                    self.assertEqual({n['id'] for n in one['nodes']},{'x','y'})
                    self.assertEqual({n['id'] for n in one['nodes']+continuation['nodes']},{n['id'] for n in two['nodes']})
                    empty=explore(nodes,self.query(op,'x'))
                    empty_two=explore(nodes,self.query(op,'x',depth=2))
                    self.assertEqual(empty['nodes'],empty_two['nodes'])
                    self.assertFalse(empty['relations']);self.assertFalse(empty_two['relations'])
    def test_all_depth_has_no_50_node_limit_and_path_is_directional(self):
        nodes=[dict(id=str(i),kind='entity',type='class',title=str(i)) for i in range(501)]
        edges=[dict(id='e'+str(i),kind='relation',type='uses',**{'from':str(i),'to':str(i+1)}) for i in range(500)]
        q=self.query('outgoing','0');q['depth']='all'
        self.assertEqual(len(explore(nodes+edges,q)['nodes']),501)
        self.assertTrue(explore(self.items,self.query('path',target='b'))['found'])
        self.assertFalse(explore(self.items,self.query('path','b',target='a'))['found'])
    def test_file_dependencies_start_at_contained_types_and_share_browse_cache(self):
        graph=explore(self.items,self.query('outgoing','file'))
        self.assertEqual({n['id'] for n in graph['nodes']},{'a','b'})
        self.assertEqual({e['id'] for e in graph['relations']},{'ab'})
        with patch('knowledge_research.fingerprint',side_effect=AssertionError('Stored file scope must be indexed')):
            query=self.wait(execute(self.registry,'one','research',{'query':self.query('outgoing','file',provider='auto')}))
            self.assertEqual(query['state'],'done',query)
            page=execute(self.registry,'one','research-result',{'id':query['result']})
        self.assertEqual({e['to'] for e in page['items'] if e['kind']=='relation'},{'b'})
        self.assertEqual(query['status'],'partial')
        browse=self.wait(execute(self.registry,'one','research',{'query':self.query('children','group',intent='browse')}))
        complete=self.wait(execute(self.registry,'one','research',{'query':self.query('children','group')}))
        self.assertTrue(complete['cached']);self.assertEqual(complete['result'],browse['result'])
    def test_job_cache_fingerprint_pagination_and_project_partition(self):
        before=fingerprint(self.store)[0]
        job=self.wait(execute(self.registry,'one','research',{'query':self.query('outgoing')}))
        self.assertEqual(job['state'],'done',job)
        page=execute(self.registry,'one','research-result',{'id':job['result'],'limit':1})
        self.assertTrue(page['more']);self.assertEqual(page['total'],3)
        cached=self.wait(execute(self.registry,'one','research',{'query':self.query('outgoing')}))
        self.assertTrue(cached['cached'])
        with self.assertRaises(KnowledgeError): execute(self.registry,'two','research-result',{'id':job['result']})
        (self.root/'A.java').write_text('class A { void x() {} }',encoding='utf-8')
        self.assertNotEqual(before,fingerprint(self.store)[0])
        self.assertEqual(execute(self.registry,'one','research-result',{'id':job['result']})['status'],'stale')
    def test_invalid_operation_and_depth_do_not_queue(self):
        for q in [self.query('base-types','group'),self.query('outgoing',depth=0),self.query('symbols','file',catalogOnly=True),{'operation':'shell','id':'a'}]:
            with self.assertRaises((KnowledgeError,TypeError)):execute(self.registry,'one','research',{'query':q})
        ops=capabilities(self.store,'file')['operations']
        self.assertFalse(any(o['id']=='base-types' for o in ops))
        self.assertTrue(any(o['status']=='unconfigured' for o in ops))

    def test_symbol_action_matrix_and_auto_source_are_language_neutral(self):
        from knowledge_research import resolve_source, validate_query
        for language_name in ('java','python','typescript'):
            config={'providers':[{'id':'semantic','languages':[language_name],'command':['fake']}]}
            (self.registry.home/'language-servers.json').write_text(json.dumps(config),encoding='utf-8')
            for kind in ('class','interface','record','enum','type','method','function','constructor','field','property','variable','constant','enum-member','type-parameter','symbol','file','module','namespace','package'):
                item=dict(id='matrix',kind='entity',type=kind,title='Target',language=language_name,source={'path':'A.java','line':1,'column':7})
                with patch('knowledge_research.read_object',return_value=item):
                    ops={op['id'] for op in capabilities(self.store,'matrix')['operations']}
                    callable_kind=kind in {'method','function','constructor'}
                    type_kind=kind in {'class','interface','record','enum','type'}
                    self.assertEqual('incoming-calls' in ops,callable_kind,(language_name,kind,ops))
                    self.assertEqual('outgoing-calls' in ops,callable_kind)
                    self.assertEqual('base-types' in ops,type_kind)
                    self.assertEqual('implementations' in ops,type_kind and not (language_name=='java' and kind in {'record','enum'}))
                    self.assertEqual('definitions' in ops,type_kind or kind=='file' or kind in {'module','namespace','package'} and language_name!='java')
                    if kind!='file':
                        automatic=resolve_source(self.store,validate_query(self.store,self.query('incoming','matrix',provider='auto')))
                        self.assertEqual(automatic['provider'],'semantic')
                        self.assertTrue(automatic['automatic'])
                    if not callable_kind:
                        with self.assertRaises(KnowledgeError):validate_query(self.store,self.query('incoming-calls','matrix',provider='auto'))
        with patch('knowledge_research.providers',return_value=[]):
            with self.assertRaises(KnowledgeError):resolve_source(self.store,self.query('definition',provider='auto'))

    def test_automatic_semantic_empty_partial_and_cache_metadata(self):
        from knowledge_lsp import manager
        (self.registry.home/'language-servers.json').write_text(json.dumps({'providers':[{'id':'fake','languages':['java'],'command':['fake']}]}),encoding='utf-8')
        with patch.object(manager,'query',return_value={'status':'partial','results':[],'diagnostics':[{'code':'semantic-incomplete','message':'Incomplete project'}]}):
            partial=self.wait(execute(self.registry,'one','research',{'query':self.query('incoming',provider='auto')}))
            self.assertEqual(partial['status'],'partial',partial)
            self.assertEqual(partial['limitation'],'Incomplete project')
        with patch.object(manager,'query',return_value={'status':'empty','results':[]}) as server:
            complete=self.wait(execute(self.registry,'one','research',{'query':self.query('incoming',provider='auto')}))
            self.assertFalse(complete.get('cached'));self.assertEqual(complete['status'],'empty')
            cached=self.wait(execute(self.registry,'one','research',{'query':self.query('incoming',provider='auto')}))
            self.assertFalse(cached.get('cached'));self.assertEqual(cached['counts'],complete['counts']);self.assertEqual(cached['status'],'empty')
            self.assertEqual(server.call_count,2)

    def test_early_empty_semantic_cache_cannot_hide_later_ready_index(self):
        from knowledge_lsp import manager
        (self.registry.home/'language-servers.json').write_text(json.dumps({'providers':[{'id':'warming','languages':['java'],'command':['fake']}]}),encoding='utf-8')
        target=dict(name='B',kind=5,uri=(self.root/'A.java').as_uri(),selectionRange={'start':{'line':2,'character':6},'end':{'line':2,'character':7}})
        calls=[];ready=False
        def answer(*args,**kwargs):
            calls.append((args[2],args[4],args[5]))
            return {'status':'ok','results':[target]} if ready and args[4]==1 else {'status':'empty','results':[]}
        with patch.object(manager,'query',side_effect=answer):
            early=self.wait(execute(self.registry,'one','research',{'query':self.query('base-types',provider='auto')}))
            self.assertEqual(early['status'],'empty')
            ready=True
            deep=self.wait(execute(self.registry,'one','research',{'query':self.query('base-types',depth=2,provider='auto')}))
            self.assertGreater(deep['counts']['relations'],0)
            one=self.wait(execute(self.registry,'one','research',{'query':self.query('base-types',provider='auto')}))
            self.assertFalse(one.get('cached'));self.assertGreater(one['counts']['relations'],0)
            repeated=self.wait(execute(self.registry,'one','research',{'query':self.query('base-types',provider='auto')}))
            self.assertTrue(repeated['cached'])
        self.assertEqual(len(calls),4)
        self.assertEqual(calls[0],calls[1]);self.assertEqual(calls[0],calls[3])

    def test_recursive_semantic_steps_continue_from_returned_declarations(self):
        from knowledge_research import semantic
        from knowledge_lsp import manager
        (self.registry.home/'language-servers.json').write_text(json.dumps({'providers':[{'id':'steps','languages':['java'],'command':['fake']}]}),encoding='utf-8')
        for kind,symbol_kind,ops in [('class',5,['base-types','implementations']),('interface',11,['base-types','implementations']),('record',5,['base-types']),('enum',10,['base-types']),('type',23,['base-types','implementations']),('method',6,['incoming-calls','outgoing-calls']),('function',12,['incoming-calls','outgoing-calls']),('constructor',9,['incoming-calls','outgoing-calls'])]:
            for operation in ops:
                with self.subTest(kind=kind,operation=operation):
                    origin={**self.items[3],'type':kind}
                    def answer(*args,**kwargs):
                        line=args[4]
                        if line>2:return {'status':'empty','results':[]}
                        target=dict(name='B' if line==1 else 'C',kind=symbol_kind,uri=(self.root/'A.java').as_uri(),selectionRange={'start':{'line':line,'character':6},'end':{'line':line,'character':7}})
                        return {'status':'ok','results':[target]}
                    query=self.query(operation,provider='steps')
                    with patch('knowledge_research.read_object',return_value=origin),patch.object(manager,'query',side_effect=answer) as server:
                        one=semantic(self.store,query);self.assertEqual(server.call_count,1)
                        first_call=server.call_args
                        two=semantic(self.store,{**query,'depth':2});self.assertEqual(server.call_count,3)
                    target=next(n for n in one['nodes'] if n['id']!='a')
                    with patch('knowledge_research.read_object',return_value=target),patch.object(manager,'query',side_effect=answer) as server:
                        next_step=semantic(self.store,{**query,'id':target['id']});self.assertEqual(server.call_count,1)
                    self.assertEqual({n['id'] for n in one['nodes']+next_step['nodes']},{n['id'] for n in two['nodes']})
                    self.assertEqual(first_call.args[2],operation)

    def test_location_only_hierarchy_targets_keep_manual_continuation(self):
        from knowledge_lsp import manager
        negotiated={'implementationProvider':True,'typeHierarchyProvider':True,'callHierarchyProvider':True,'documentSymbolProvider':False}
        (self.registry.home/'language-servers.json').write_text(json.dumps({'providers':[{'id':'untyped','languages':['java'],'command':['fake']}]}),encoding='utf-8')
        (self.root/'A.java').write_text('class A {}\nclass B {}\nclass C {}',encoding='utf-8')
        caller={**self.items[3],'id':'caller','type':'method'}
        self.store.changeset(1,'caller',[{'op':'put','item':caller}],'Callable fixture')
        for operation in ('base-types','implementations','incoming-calls','outgoing-calls'):
            with self.subTest(operation=operation):
                calls=[]
                def answer(*args,**kwargs):
                    op,line=args[2],args[4]
                    calls.append((op,line))
                    if op=='symbols':return {'status':'unsupported','results':[],'capabilities':negotiated}
                    values=[] if line>2 else [{'uri':(self.root/'A.java').as_uri(),'range':{'start':{'line':line,'character':6},'end':{'line':line,'character':7}}}]
                    return {'status':'ok' if values else 'empty','results':values,'capabilities':negotiated}
                origin='caller' if 'calls' in operation else 'a'
                query=self.query(operation,origin,provider='auto')
                with patch.object(manager,'query',side_effect=answer):
                    one=self.wait(execute(self.registry,'one','research',{'query':query}))
                    self.assertEqual(one['state'],'done',one)
                    first=execute(self.registry,'one','research-result',{'id':one['result']})
                    target=next(n for n in first['items'] if n['kind']=='entity' and n['id']!=origin)
                    self.assertEqual(target['type'],'symbol')
                    self.assertEqual([line for op,line in calls if op==operation],[1])
                    available=capabilities(self.store,target['id'])['operations']
                    self.assertTrue(any(op['id']==operation and op['provider']=='untyped' and op['status']=='available' for op in available),available)
                    next_step=self.wait(execute(self.registry,'one','research',{'query':{**query,'id':target['id']}}))
                    self.assertEqual(next_step['state'],'done',next_step)
                    second=execute(self.registry,'one','research-result',{'id':next_step['result']})
                    self.assertEqual([line for op,line in calls if op==operation],[1,2])
                    deep=self.wait(execute(self.registry,'one','research',{'query':{**query,'depth':2}}))
                    self.assertEqual(deep['state'],'done',deep)
                    combined=execute(self.registry,'one','research-result',{'id':deep['result']})
                self.assertEqual({n['id'] for n in first['items']+second['items'] if n['kind']=='entity'},{n['id'] for n in combined['items'] if n['kind']=='entity'})
                self.assertEqual({n['id'] for n in first['items']+second['items'] if n['kind']=='relation'},{n['id'] for n in combined['items'] if n['kind']=='relation'})

    def test_moved_symbol_without_recorded_hash_is_resolved_before_query(self):
        from knowledge_lsp import manager
        (self.registry.home/'language-servers.json').write_text(json.dumps({'providers':[{'id':'position','languages':['java'],'command':['fake']}]}),encoding='utf-8')
        (self.root/'A.java').write_text('// moved\nclass A {}',encoding='utf-8')
        declaration={'name':'A','kind':5,'selectionRange':{'start':{'line':1,'character':6},'end':{'line':1,'character':7}}}
        with patch.object(manager,'query',side_effect=[{'status':'ok','results':[declaration]},{'status':'empty','results':[]}]) as server:
            job=self.wait(execute(self.registry,'one','research',{'query':self.query('incoming',provider='auto')}))
        self.assertEqual(job['state'],'done',job)
        self.assertEqual(server.call_args_list[0].args[2],'symbols')
        self.assertEqual(server.call_args_list[1].args[2],'references')
        self.assertEqual(server.call_args_list[1].args[4:6],(2,7))
        page=execute(self.registry,'one','research-result',{'id':job['result']})
        self.assertIn('symbol-refreshed',{d.get('code') for d in page['diagnostics'] if isinstance(d,dict)})

    def test_semantic_hidden_file_is_transparent_but_next_symbol_is_not_expanded(self):
        from knowledge_research import semantic
        from knowledge_lsp import manager
        (self.registry.home/'language-servers.json').write_text(json.dumps({'providers':[{'id':'steps','languages':['java'],'command':['fake']}]}),encoding='utf-8')
        def symbol(name,line,kind):
            return dict(name=name,kind=kind,uri=(self.root/'A.java').as_uri(),selectionRange={'start':{'line':line,'character':6},'end':{'line':line,'character':7}})
        origin={**self.items[3],'type':'method'}
        with patch('knowledge_research.read_object',return_value=origin),patch.object(manager,'query',side_effect=[{'status':'ok','results':[symbol('resource',1,1)]},{'status':'ok','results':[symbol('next',2,6)]}]) as server:
            one=semantic(self.store,self.query('outgoing-calls',provider='steps'))
        self.assertEqual(server.call_count,2)
        self.assertEqual({n['title'] for n in one['nodes']},{'A','next'})
        self.assertEqual(one['relations'][0]['type'],'via-files')
        self.assertEqual(len(one['relations'][0]['pathEdges']),2)

    def test_semantic_class_uses_indexed_static_counterpart_without_database_scan(self):
        from knowledge_lsp import manager
        (self.registry.home/'language-servers.json').write_text(json.dumps({'providers':[{'id':'fake','languages':['java'],'command':['fake']}]}),encoding='utf-8')
        declaration={'name':'A','kind':5,'selectionRange':{'start':{'line':0,'character':6},'end':{'line':0,'character':7}}}
        with patch.object(manager,'query',return_value={'status':'ok','results':[declaration]}):
            structure=self.wait(execute(self.registry,'one','research',{'query':self.query('symbols','file',provider='fake')}))
        page=execute(self.registry,'one','research-result',{'id':structure['result']})
        symbol=next(n for n in page['items'] if n.get('title')=='A')
        with patch('knowledge_research.fingerprint',side_effect=AssertionError('Static counterpart must use indexed catalog reads')):
            outgoing=self.wait(execute(self.registry,'one','research',{'query':self.query('outgoing',symbol['id'],provider='auto')}))
            self.assertEqual(outgoing['state'],'done',outgoing)
            self.assertEqual(outgoing['status'],'partial')
            result=execute(self.registry,'one','research-result',{'id':outgoing['result']})
        self.assertEqual({n['id'] for n in result['items'] if n['kind']=='entity'},{symbol['id'],'b'})
        edge=next(n for n in result['items'] if n['kind']=='relation')
        self.assertEqual((edge['from'],edge['to']),(symbol['id'],'b'))
        with patch('knowledge_research.catalog_items',side_effect=AssertionError('Complete static reads should reuse cache')):
            cached=self.wait(execute(self.registry,'one','research',{'query':self.query('outgoing',symbol['id'],provider='auto')}))
        self.assertTrue(cached['cached']);self.assertEqual(cached['status'],'partial')
        self.assertEqual(cached['limitation'],outgoing['limitation'])

    def test_research_history_labels_pages_and_hides_automatic_browsing(self):
        browse=self.wait(execute(self.registry,'one','research',{'query':self.query('children','group',intent='browse',catalogOnly=True)}))
        first=self.wait(execute(self.registry,'one','research',{'query':self.query('children','group')}))
        second=self.wait(execute(self.registry,'one','research',{'query':self.query('own-code','group')}))
        page=execute(self.registry,'one','research-history',{'limit':1})
        self.assertEqual(page['items'][0]['id'],second['id']);self.assertTrue(page['more'])
        self.assertEqual(page['items'][0]['object']['title'],'Group')
        earlier=execute(self.registry,'one','research-history',{'limit':1,'offset':page['next']})
        self.assertEqual(earlier['items'][0]['id'],first['id']);self.assertFalse(earlier['more'])
        self.assertNotEqual(earlier['items'][0]['id'],browse['id'])

    def test_new_source_invalidates_fingerprint_and_saved_map_replays(self):
        before=fingerprint(self.store)[0]
        (self.root/'New.java').write_text('class New {}',encoding='utf-8')
        self.assertNotEqual(before,fingerprint(self.store)[0])
        query=dict(expected=1,key='map',title='Map',nodeIds=['a','b'],edgeIds=['ab'])
        saved=execute(self.registry,'one','research-save',query)
        self.assertEqual(self.store.read(saved['id'])['nodeIds'],['a','b'])
        self.assertTrue(execute(self.registry,'one','research-save',query)['replayed'])
        with self.assertRaises(KnowledgeError):execute(self.registry,'one','research-save',{**query,'title':'Changed'})
        with self.assertRaises(KnowledgeError):execute(self.registry,'one','research-save',{**query,'key':'other','nodeIds':['foreign']})

    def test_semantic_children_have_owners_and_recursive_calls_are_stable(self):
        from knowledge_research import semantic
        from knowledge_lsp import manager
        config={'providers':[{'id':'fake','languages':['java'],'command':['fake']}]}
        (self.registry.home/'language-servers.json').write_text(json.dumps(config),encoding='utf-8')
        def symbol(name,line,column,kind=6,children=None):
            return dict(name=name,kind=kind,uri=(self.root/'A.java').as_uri(),selectionRange={'start':{'line':line,'character':column},'end':{'line':line,'character':column+1}},**({'children':children} if children else {}))
        methods=[symbol('start()',1,7),symbol('next()',2,7)]
        with patch.object(manager,'query',return_value={'status':'ok','results':[symbol('A',0,6,5,methods),symbol('Unrelated',4,6,5,[symbol('other()',5,7)])]}) as fake:
            definitions=semantic(self.store,{**self.query('definitions','a'),'provider':'fake'})
        self.assertEqual(fake.call_args.args[2],'symbols')
        self.assertEqual({n['title'] for n in definitions['nodes']},{'A','start()','next()'})
        self.assertTrue(all(e['from']=='a' for e in definitions['relations']))
        with patch.object(manager,'query',return_value={'status':'ok','results':[symbol('A',0,6,5,methods)]}):
            structure=semantic(self.store,{**self.query('symbols','file'),'provider':'fake','representation':'symbols-in-files'})
        classes=[n for n in structure['nodes'] if n['type']=='class']
        method_nodes=[n for n in structure['nodes'] if n['type']=='method']
        self.assertEqual(len(method_nodes),2)
        self.assertTrue(all(any(e['from']==classes[0]['id'] and e['to']==n['id'] and e['type']=='contains' for e in structure['relations']) for n in method_nodes))
        # Publish a fragment exactly as a worker would, to make its method
        # identity available for the next user-driven query.
        from knowledge_research import setup
        from knowledge_store import canonical
        setup(self.store)
        structure.update(fingerprint=fingerprint(self.store)[0],status='ok')
        with self.registry.connect() as c:c.execute('INSERT INTO knowledge_research VALUES(?,?,?,?)',('one','symbols','symbols',canonical(structure)))
        origin=method_nodes[0]
        with patch.object(manager,'query',side_effect=[{'status':'ok','results':[{'to':symbol('next() : void',2,7)}]},{'status':'empty','results':[]}]) as fake:
            calls=semantic(self.store,{**self.query('outgoing-calls',origin['id'],depth='all'),'provider':'fake'})
        self.assertEqual(fake.call_count,2)
        self.assertEqual(calls['relations'][0]['to'],method_nodes[1]['id'])
        saved=execute(self.registry,'one','research-save',dict(expected=1,key='semantic-map',title='Methods',nodeIds=[n['id'] for n in structure['nodes']],edgeIds=[e['id'] for e in structure['relations']]))
        self.assertTrue(read_object(self.store,origin['id']).get('analysisSourceHash'))
        (self.root/'A.java').write_text('class Changed {}',encoding='utf-8')
        with self.assertRaises(KnowledgeError) as stale:read_object(self.store,origin['id'])
        self.assertEqual(stale.exception.body['error'],'stale_object')
        # Saved maps remain readable as historical evidence; research cannot
        # continue at the old method position after editing its source.
        self.assertIn(origin['id'],self.store.read(saved['id'])['nodeIds'])

    def test_incremental_fingerprint_reuses_bytes_but_detects_edits_and_new_files(self):
        original=pathlib.Path.open
        reads=[]
        def tracked(path,*args,**kwargs):
            if path.name=='A.java' and args and args[0]=='rb':reads.append(path)
            return original(path,*args,**kwargs)
        with patch.object(pathlib.Path,'open',tracked):
            first=fingerprint(self.store)[0]
            self.assertEqual(first,fingerprint(self.store)[0])
            from knowledge_research import source_content_hash
            self.store.changeset(1,'symbol-hash',[{'op':'put','item':{**self.items[3],'analysisSourceHash':source_content_hash(self.store,self.root/'A.java').hex()}}],'Hash')
            read_object(self.store,'a');read_object(self.store,'a')
            first=fingerprint(self.store)[0]
            self.assertEqual(len(reads),1,'Unchanged source bytes are read once, even across freshness checks')
            (self.root/'A.java').write_text('class B {}',encoding='utf-8')
            edited=fingerprint(self.store)[0]
            self.assertNotEqual(first,edited)
            self.assertEqual(len(reads),2)
            (self.root/'New.java').write_text('class New {}',encoding='utf-8')
            self.assertNotEqual(edited,fingerprint(self.store)[0])

    def test_location_definition_preserves_record_identity_and_file_freshness(self):
        from knowledge_research import semantic, setup
        from knowledge_store import canonical
        from knowledge_lsp import manager
        (self.root/'A.java').write_text('record A(int width) {}',encoding='utf-8')
        self.store.changeset(1,'record',[{'op':'put','item':{**self.items[3],'type':'record','description':'Authored explanation'}}],'Record')
        (self.registry.home/'language-servers.json').write_text(json.dumps({'providers':[{'id':'fake','languages':['java'],'command':['fake']}]}),encoding='utf-8')
        selection={'start':{'line':0,'character':7},'end':{'line':0,'character':8}}
        location={'uri':(self.root/'A.java').as_uri(),'range':selection}
        declaration={'name':'A','kind':5,'selectionRange':selection}
        with patch.object(manager,'query',side_effect=[{'status':'ok','results':[location]},{'status':'ok','results':[declaration]}]) as fake:
            fragment=semantic(self.store,{**self.query('definition'),'provider':'fake'})
        self.assertEqual(fake.call_count,2)
        self.assertEqual(len(fragment['nodes']),1)
        record=fragment['nodes'][0]
        self.assertEqual((record['id'],record['title'],record['type']),('a','A','record'))
        self.assertEqual(record['description'],'Authored explanation')
        self.assertEqual(record['component'],'group')
        self.assertFalse(fragment['relations'])
        # Ephemeral positions depend on their own source bytes, not unrelated
        # catalog edits or changes in another source file.
        record={**record,'id':'research:symbol:record'}
        fragment.update(nodes=[record],fingerprint=fingerprint(self.store)[0],status='ok')
        setup(self.store)
        with self.registry.connect() as c:c.execute('INSERT INTO knowledge_research VALUES(?,?,?,?)',('one','record-fragment','record-fragment',canonical(fragment)))
        before=read_object(self.store,record['id'])
        (self.root/'Other.java').write_text('class Other {}',encoding='utf-8')
        self.store.changeset(2,'rename-group',[{'op':'put','item':{**self.items[0],'title':'Renamed group'}}],'Unrelated edit')
        self.assertEqual(read_object(self.store,record['id']),before)
        self.assertFalse(any(op['id'].endswith('-calls') for op in capabilities(self.store,record['id'])['operations']))
        (self.root/'A.java').write_text('// moved\nrecord A(long width) {}',encoding='utf-8')
        with self.assertRaises(KnowledgeError) as stale:read_object(self.store,record['id'])
        self.assertEqual(stale.exception.body['error'],'stale_object')
        fresh_selection={'start':{'line':1,'character':7},'end':{'line':1,'character':8}}
        fresh_declaration={**declaration,'selectionRange':fresh_selection}
        fresh_location={**location,'range':fresh_selection}
        with patch.object(manager,'query',side_effect=[{'status':'ok','results':[fresh_declaration]},{'status':'ok','results':[fresh_location]},{'status':'ok','results':[fresh_declaration]}]) as server:
            refreshed=self.wait(execute(self.registry,'one','research',{'query':self.query('definition',record['id'],provider='auto')}))
        self.assertEqual(refreshed['state'],'done',refreshed)
        self.assertEqual([call.args[2] for call in server.call_args_list],['symbols','definition','symbols'])
        self.assertEqual(server.call_args_list[1].args[4:6],(2,8))
        self.assertEqual(read_object(self.store,record['id'])['title'],'A')
        self.assertEqual(read_object(self.store,record['id'])['source']['line'],2)
