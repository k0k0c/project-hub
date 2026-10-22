import io
import json
from pathlib import Path
import sys
import time
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
import test_project_hub_plugin_api as fixture
from task_transfer import transfer


class KnowledgeHttpTests(unittest.TestCase):
    setUp=fixture.PluginApiTest.setUp
    tearDown=fixture.PluginApiTest.tearDown
    invoke=fixture.PluginApiTest.invoke

    def request(self,action,args=None,project='a',download=False):
        from urllib.parse import urlencode
        path='/api/v1/knowledge'+('/download' if download else '')+'?'+urlencode(dict(project=self.ids[project],action=action))
        request=Request(self.client.url.removesuffix('/api/v1/plugin/call')+path,data=None if download else json.dumps(dict(action=action,args=args or {})).encode(),headers={'Content-Type':'application/json'})
        with urlopen(request,timeout=10) as response:
            data=response.read()
            return data if download else json.loads(data)

    def test_mcp_knowledge_and_bound_project(self):
        context=self.invoke('a','hub_knowledge',action='context')
        self.assertEqual(context['project'],self.ids['a'])
        self.assertFalse(context['capabilities']['methods'])
        self.invoke('a','hub_knowledge',action='changeset',args=dict(expected=0,key='mcp',reason='Create guide',operations=[dict(op='put',item=dict(id='guide',kind='document',title='Guide',markdown='Text'))]))
        self.assertEqual(self.invoke('a','hub_knowledge',action='read',args={'id':'guide'})['markdown'],'Text')
        self.assertEqual(self.invoke('b','hub_knowledge',action='search')['items'],[])

    def test_documentation_workspace_assets_are_served_locally(self):
        base=self.client.url.removesuffix('/api/v1/plugin/call')
        for name,content_type in [('documentation.js','javascript'),('documentation.css','text/css')]:
            with self.subTest(asset=name),urlopen(base+'/'+name,timeout=10) as response:
                self.assertEqual(response.status,200)
                self.assertIn(content_type,response.headers['Content-Type'])
                self.assertGreater(len(response.read()),100)

    def test_http_validates_and_downloads_portable_files(self):
        for action,args in [('read',{}),('changeset',{'actor':'spoof'}),('history',{'limit':'invalid'})]:
            with self.assertRaises(HTTPError) as raised: self.request(action,args)
            self.assertEqual(raised.exception.code,400)
        self.request('changeset',dict(expected=0,key='http',reason='New article',operations=[dict(op='put',item=dict(id='guide',kind='document',title='Guide',markdown='Text'))]))
        with zipfile.ZipFile(io.BytesIO(self.request('export',download=True))) as bundle:
            self.assertIn('knowledge.json',bundle.namelist())
            self.assertEqual(len([p for p in bundle.namelist() if p.endswith('.md')]),1)
        backup=json.loads(self.request('backup',download=True))
        self.request('restore-backup',{'backup':backup},project='b')
        self.assertEqual(self.request('read',{'id':'guide'},project='b')['markdown'],'Text')

    def test_task_timeline_publication_repairs_legacy_queue_and_follows_transfer(self):
        from knowledge_store import KnowledgeStore,canonical
        task=self.invoke('a','hub_task',title='Knowledge timeline',scope=['Guide'],acceptance=['Timeline'])['task']
        self.invoke('a','hub_plan',task=task,stage='docs',title='Documentation',remaining=['Create guide'])
        self.invoke('a','hub_knowledge',action='changeset',args=dict(expected=0,key='timeline',reason='Article',task=task,stage='docs',operations=[dict(op='put',item=dict(id='guide',kind='document',title='Guide',markdown='Text'))]))
        store=KnowledgeStore(self.registry,self.ids['a'])
        self.assertEqual(store.context()['publicationPending'],0)
        notes=[e for e in self.registry.store(self.ids['a']).snapshot()['allEvents'] if e['id']=='knowledge-'+self.ids['a']+'-1']
        self.assertEqual(len(notes),1)
        self.assertIn('Автор:',notes[0]['detail'])
        self.assertNotIn('actor',notes[0])
        self.assertEqual(notes[0]['evidence'][0]['path'],'knowledge/revision/1/document/guide')
        legacy=dict(id='legacy-knowledge-note',kind='note',taskId=task,stageId='docs',title='Queued note',detail='Before repair',actor='verified-legacy-author',evidence=[])
        with self.registry.connect() as connection:
            connection.execute('INSERT INTO knowledge_outbox VALUES(?,?,?,NULL)',(self.ids['a'],2,canonical(legacy)))
        store.flush_publication(); store.flush_publication()
        self.assertEqual(store.context()['publicationPending'],0)
        repaired=[e for e in self.registry.store(self.ids['a']).snapshot()['allEvents'] if e['id']==legacy['id']]
        self.assertEqual(len(repaired),1)
        self.assertIn('verified-legacy-author',repaired[0]['detail'])
        preview=transfer(self.registry,self.ids['a'],self.ids['b'],task,preview=True)
        transfer(self.registry,self.ids['a'],self.ids['b'],task,preview['revision'],'move')
        self.invoke('b','hub_knowledge',action='changeset',args=dict(expected=0,key='owner',reason='Owner article',task=task,stage='docs',operations=[dict(op='put',item=dict(id='owner-guide',kind='document',title='Owner guide',markdown='Owner text'))]))
        self.assertEqual(self.request('context',project='b')['publicationPending'],0)
        note=next(e for e in self.registry.store(self.ids['b']).snapshot()['allEvents'] if e['id']=='knowledge-'+self.ids['b']+'-1')
        self.assertEqual(note['evidence'][0]['path'],'knowledge/revision/1/document/owner-guide')
        self.assertEqual(self.invoke('b','hub_memory',ref='source:knowledge/revision/1/document/owner-guide')['text'],'Owner text')

    def test_mcp_large_import_has_recoverable_preview_and_paged_text(self):
        paths=[]
        for i in range(3):
            path='large-'+str(i)+'.md'; paths.append(path)
            (self.base/'a'/path).write_text('# Article '+str(i)+'\n'+'Text '*24000,encoding='utf-8')
        preview=self.invoke('a','hub_knowledge',action='import-preview',args={'paths':paths})
        self.assertTrue(preview['compact'])
        self.assertEqual(len(preview['items']),3)
        self.assertLess(len(json.dumps(preview).encode()),20000)
        args=preview['readArgs']; content=''
        while True:
            page=self.invoke('a','hub_knowledge',action='import-read',args=args)
            content+=page['text']
            if not page['more']: break
            args=dict(args,offset=page['next'])
        self.assertEqual(content,(self.base/'a'/paths[0]).read_bytes().decode('utf-8'))
        result=self.invoke('a','hub_knowledge',action='import-apply',args=dict(identifier=preview['id'],expected=0,key='large-import'))
        self.assertEqual(result['changed'],3)
        exported=self.invoke('a','hub_knowledge',action='export')
        self.assertTrue(exported['compact']); self.assertEqual(exported['itemsCount'],3)
        self.assertIn('/api/v1/knowledge/download?',exported['download'])
        self.assertEqual(len(self.request('export')['items']),3)

    def test_task_sources_keep_immutable_database_document_after_transfer(self):
        task=self.invoke('a','hub_task',title='Knowledge attachment',scope=['Guide'],acceptance=['Resolves'])['task']
        self.invoke('a','hub_plan',task=task,stage='docs',title='Documentation',remaining=['Create guide'])
        receipt=self.invoke('a','hub_knowledge',action='changeset',args=dict(expected=0,key='guide',reason='Task article',task=task,stage='docs',operations=[dict(op='put',item=dict(id='guide',kind='document',title='Guide',markdown='old'))]))
        revision=self.invoke('a','hub_plan',task=task)['revision']
        self.invoke('a','hub_task_update',task=task,expected=revision,patch={'sources':receipt['sources']})
        first=self.invoke('a','hub_memory',ref='source:knowledge/document/guide')
        self.assertEqual(first['text'],'old')
        self.invoke('a','hub_knowledge',action='changeset',args=dict(expected=1,key='new',reason='Update',operations=[dict(op='put',item=dict(id='guide',kind='document',title='Guide',markdown='new'))]))
        self.assertEqual(self.invoke('a','hub_memory',ref=first['versionRef'])['text'],'old')
        preview=transfer(self.registry,self.ids['a'],self.ids['b'],task,preview=True)
        transfer(self.registry,self.ids['a'],self.ids['b'],task,preview['revision'],'move')
        path='hub-source/'+self.ids['a']+'/knowledge/document/guide'
        self.assertEqual(self.invoke('b','hub_memory',ref='source:'+path)['text'],'new')
        with self.assertRaises(Exception): self.invoke('b','hub_memory',ref='source:knowledge/document/guide')

    def test_queue_ack_is_bounded_and_facts_unchanged_does_not_add_revision(self):
        (self.base/'a'/'entry.py').write_text('class Application: pass',encoding='utf-8')
        begin=time.perf_counter(); job=self.request('scan'); elapsed=time.perf_counter()-begin
        self.assertLess(elapsed,3) # Only enqueue, never run AST while holding HTTP/task barrier.
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            result=self.request('job',{'id':job['id']})
            if result['state'] not in ('queued','running'): break
            time.sleep(.02)
        self.assertEqual(result['state'],'ready',result)
        revision=self.request('context')['revision']
        job=self.request('scan')
        self.registry._knowledge_executor.shutdown(wait=True)
        self.assertEqual(self.request('context')['revision'],revision)


if __name__=='__main__': unittest.main()
