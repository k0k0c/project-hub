import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import urlopen
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from knowledge_store import KnowledgeStore, KnowledgeError
from knowledge_html import content, embedded_theme
from test_knowledge_store import Registry
import test_knowledge_http as http_fixture


def document(root):
    (root/'docs').mkdir(exist_ok=True)
    (root/'docs'/'page.html').write_text('<!doctype html><title>Prototype</title><link rel="stylesheet" href="theme.css"><h1>Example</h1><button id="run">Run</button><script src="app.js"></script>',encoding='utf-8')
    (root/'docs'/'theme.css').write_text('body { color: red; background: url(pic.svg); }',encoding='utf-8')
    (root/'docs'/'pic.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>',encoding='utf-8')
    (root/'docs'/'app.js').write_text('document.getElementById("run").onclick=()=>document.body.dataset.clicked="yes";',encoding='utf-8')


class HtmlStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'source';self.root.mkdir()
        self.registry=Registry(Path(self.temp.name)/'data',self.root)
        self.store=KnowledgeStore(self.registry,'one');document(self.root)

    def apply(self,preview,key='import',metadata=None,selections=None):
        return self.store.import_apply(preview['id'],self.store.context()['revision'],key,metadata=metadata,selections=selections)

    def test_bundle_preserves_markup_dependencies_and_search_after_source_removal(self):
        preview=self.store.import_preview(['docs/page.html']);item=preview['items'][0]['item']
        self.assertEqual(item['format'],'html')
        self.assertEqual(len(item['htmlBundle']['files']),4)
        raw=(self.root/'docs/page.html').read_bytes()
        self.apply(preview,metadata={item['id']:dict(title='Named prototype',section='Editors/Contracts',documentDate='2026-10-03',versionLabel='V2',status='historical')})
        (self.root/'docs/page.html').unlink();(self.root/'docs/theme.css').unlink()
        saved=self.store.read(item['id']);self.assertEqual(content(self.store,saved),raw)
        self.assertIn(b'color: red',content(self.store,saved,'docs/theme.css'))
        search=self.store.search(query='Named prototype',kind='document')['items'][0]
        self.assertEqual(search['section'],'Editors/Contracts');self.assertEqual(search['format'],'html')
        self.assertIn('Example',search['excerpt'])

    def test_dependency_change_requires_review_and_old_revision_keeps_old_css(self):
        first=self.store.import_preview(['docs/page.html']);item=first['items'][0]['item'];self.apply(first,metadata={item['id']:dict(description='Reviewed explanation')})
        (self.root/'docs/theme.css').write_text('body { color: blue; }',encoding='utf-8')
        second=self.store.import_preview(['docs/page.html']);self.assertEqual(second['items'][0]['action'],'review')
        self.assertEqual(second['items'][0]['item']['description'],'Reviewed explanation')
        self.assertIn('Bundle assets changed',second['items'][0]['diff'])
        self.apply(second,key='not-selected')
        self.assertIn(b'color: red',content(self.store,self.store.read(item['id']),'docs/theme.css'))
        self.apply(second,key='selected',selections=[item['id']])
        self.assertIn(b'color: blue',content(self.store,self.store.read(item['id']),'docs/theme.css'))
        self.assertIn(b'color: red',content(self.store,self.store.read(item['id'],1),'docs/theme.css'))

    def test_missing_external_and_protected_dependencies_are_reported_not_read(self):
        (self.root/'.env').write_text('secret',encoding='utf-8')
        (self.root/'docs/page.html').write_text('<title>P</title><img src="missing.png"><script src="https://invalid.example/script.js"></script><a href="../.env">secret</a><img src="../../outside.png">',encoding='utf-8')
        item=self.store.import_preview(['docs/page.html'])['items'][0]['item']
        self.assertTrue(item['missingAssets']);self.assertEqual(item['externalResources'],['https://invalid.example/script.js'])
        self.assertEqual(len(item['htmlBundle']['files']),1)

    def test_metadata_cannot_replace_bundle_or_unknown_candidate(self):
        preview=self.store.import_preview(['docs/page.html']);identifier=preview['items'][0]['item']['id']
        for metadata in ({identifier:{'htmlBundle':{}}},{'unknown':{'status':'current'}},{identifier:{'documentDate':'bad'}}):
            with self.assertRaises(KnowledgeError):self.apply(preview,metadata=metadata)
        self.assertEqual(self.store.context()['revision'],0)

    def test_inline_assets_ignore_css_like_javascript_expressions(self):
        (self.root/'docs/page.html').write_text('<title>P</title><style>body {background:url(pic.svg)}</style><script>const a=URL.createObjectURL(blob); const b="text(url)"; import("./app.js");</script>',encoding='utf-8')
        item=self.store.import_preview(['docs/page.html'])['items'][0]['item']
        self.assertEqual(item['missingAssets'],[])
        self.assertEqual({f['path'] for f in item['htmlBundle']['files']},{'docs/page.html','docs/pic.svg','docs/app.js'})

    def test_source_pages_export_backup_restore_are_self_contained(self):
        preview=self.store.import_preview(['docs/page.html']);identifier=preview['items'][0]['item']['id'];self.apply(preview)
        page=self.store.import_read(preview['id'],field='source',limit=20)
        self.assertTrue(page['more']);self.assertIn('<!doctype',page['text'])
        with zipfile.ZipFile(io.BytesIO(self.store.export_bundle())) as archive:
            paths=archive.namelist();self.assertTrue(any(p.endswith('/docs/page.html') for p in paths))
            self.assertTrue(any(p.endswith('/docs/theme.css') for p in paths))
        backup=self.store.backup();other=KnowledgeStore(self.registry,'two');other.restore_backup(backup)
        self.assertEqual(content(other,other.read(identifier)),content(self.store,self.store.read(identifier)))
        saved=self.store.read(identifier);saved['visibility']='public-approved'
        self.store.changeset(1,'public',[dict(op='put',item=saved)],'Mark reviewed')
        with self.assertRaises(KnowledgeError):self.store.export(public=True)

    def test_manifest_rejects_entry_type_and_forged_sizes(self):
        item=self.store.import_preview(['docs/page.html'])['items'][0]['item']
        item['htmlBundle']['files'][0]['size']=0
        with self.assertRaises(KnowledgeError):self.store.changeset(0,'bad',[dict(op='put',item=item)],'Forged size')
        item['htmlBundle']['entry']='docs/app.js'
        with self.assertRaises(KnowledgeError):self.store.validate_item(item)


class HtmlHttpTests(unittest.TestCase):
    setUp=http_fixture.KnowledgeHttpTests.setUp
    tearDown=http_fixture.KnowledgeHttpTests.tearDown
    invoke=http_fixture.KnowledgeHttpTests.invoke
    request=http_fixture.KnowledgeHttpTests.request

    def prepare(self):
        document(self.base/'a')
        preview=self.request('import-preview',{'paths':['docs/page.html']})
        self.request('import-apply',dict(identifier=preview['id'],expected=0,key='html'))
        item=preview['items'][0]['item']
        self.page=item;self.origin=self.client.url.removesuffix('/api/v1/plugin/call')
        return self.origin+'/api/v1/knowledge/html/'+quote(self.ids['a'],safe='')+'/1/'+quote(item['id'],safe='')+'/files/'

    def test_standalone_and_assets_have_strict_sandbox_without_cors(self):
        base=self.prepare()
        with urlopen(base+'docs/page.html') as response:
            body=response.read();policy=response.headers['Content-Security-Policy']
            self.assertIn(b'<title>Prototype</title>',body);self.assertNotIn(b'Project Hub',body)
            self.assertIn('sandbox allow-scripts;',policy);self.assertNotIn('allow-same-origin',policy)
            self.assertIn("connect-src 'none'",policy);self.assertIn("worker-src 'none'",policy)
            self.assertNotIn('Access-Control-Allow-Origin',response.headers)
        for path,mime in [('docs/theme.css','text/css'),('docs/app.js','text/javascript'),('docs/pic.svg','image/svg+xml')]:
            with urlopen(base+path) as response:
                self.assertTrue(response.headers['Content-Type'].startswith(mime));self.assertEqual(response.read(),(self.base/'a'/path).read_bytes())
        task=self.invoke('a','hub_task',title='HTML source attachment',scope=['Saved source'],acceptance=['Source resolves'])['task']
        revision=self.invoke('a','hub_plan',task=task)['revision']
        self.invoke('a','hub_task_update',task=task,expected=revision,patch={'sources':[dict(label='HTML prototype',path='knowledge/document/'+self.page['id'])]})
        info=self.invoke('a','hub_memory',ref='source:knowledge/document/'+self.page['id'])
        self.assertIn('<title>Prototype</title>',info['text'])

    def test_exact_revision_project_and_manifest_authorization(self):
        base=self.prepare()
        for path in ('docs/unknown.js','%2e%2e/.env','docs/%5c..%5csecret','docs/page.html?project='+self.ids['b']):
            with self.assertRaises(HTTPError) as raised:urlopen(base+path)
            self.assertIn(raised.exception.code,(400,404))
        with self.assertRaises(HTTPError):urlopen(base.replace('/1/','/0/')+'docs/page.html')
        with self.assertRaises(HTTPError):urlopen(base.replace('/'+quote(self.ids['a'],safe='')+'/', '/'+quote(self.ids['b'],safe='')+'/')+'docs/page.html')
        (self.base/'a'/'docs'/'page.html').unlink()
        with urlopen(base+'docs/page.html') as response:self.assertIn(b'Prototype',response.read())

    def test_embedded_html_gets_dark_theme_metadata_without_byte_rewriting(self):
        from urllib.request import Request
        base=self.prepare()
        original=(self.base/'a'/'docs'/'page.html').read_bytes()
        for request in (base+'docs/page.html?hub-embed=1',Request(base+'docs/page.html',headers={'Sec-Fetch-Dest':'iframe'})):
            with urlopen(request) as response:
                rendered=response.read()
                self.assertEqual(rendered,embedded_theme(original))
                self.assertIn(b'<meta name="color-scheme" content="dark" data-hub-theme>',rendered)
                self.assertNotIn(b'data-hub-document-height',rendered)
                self.assertIn("sandbox allow-scripts;",response.headers['Content-Security-Policy'])
                self.assertNotIn('allow-same-origin',response.headers['Content-Security-Policy'])
                self.assertIn("connect-src 'none'",response.headers['Content-Security-Policy'])
                self.assertEqual(response.headers['Cache-Control'],'no-store')
        with urlopen(base+'docs/page.html') as response:self.assertEqual(response.read(),original)
        with urlopen(base+'docs/theme.css?hub-embed=1') as response:
            self.assertEqual(response.read(),(self.base/'a'/'docs'/'theme.css').read_bytes())

    def test_mcp_html_import_preview_is_bounded_and_format_aware(self):
        document(self.base/'a')
        preview=self.invoke('a','hub_knowledge',action='import-preview',args={'paths':['docs/page.html']})
        self.assertEqual(preview['items'][0]['format'],'html');self.assertTrue(preview['compact'])
        self.assertLess(len(json.dumps(preview)),5000)
        page=self.invoke('a','hub_knowledge',action='import-read',args=preview['readArgs'])
        self.assertIn('<title>Prototype</title>',page['text'])


class EmbeddedThemeTests(unittest.TestCase):
    def test_theme_metadata_preserves_markup_and_ignores_fake_head_markup(self):
        marker=b'<meta name="color-scheme" content="dark" data-hub-theme>'
        for source in (b'<!doctype html><head><!-- fake <head> --><title>X</title></head><body style="background:#123456">Body</body>',b'<title>Fragment</title><!-- fake <head> -->',b'\xef\xbb\xbf<!doctype html>\r<!-- mixed\r\n lines -->\n<head><title>X</title></head>'):
            rendered=embedded_theme(source)
            self.assertEqual(rendered.count(marker),1)
            self.assertEqual(rendered.replace(marker,b''),source)
            self.assertIn(b'<title>',rendered)
        headed=embedded_theme(b'<!doctype html>\r<!-- mixed\r\n lines -->\n<head><title>X</title></head>')
        self.assertGreater(headed.index(marker),headed.index(b'<head>'))
        self.assertLess(headed.index(marker),headed.index(b'<title>'))

    def test_existing_color_scheme_is_preserved_including_bom(self):
        for source in (b'<meta name="color-scheme" content="light">',b'\xef\xbb\xbf<!doctype html><meta name="color-scheme" content="light">'):
            self.assertEqual(embedded_theme(source),source)
