import shutil
import subprocess
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / 'tools/project-portal/web'


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class HtmlDocumentsUiTest(unittest.TestCase):
    def test_html_renderer_contract_and_safe_metadata(self):
        script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ctx={window:{}};vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/html-documents.js','utf8'),ctx);
const ui=ctx.window.HtmlDocuments;
const item={id:'doc/1',title:'<Danger>',description:'A & B',format:'html',status:'historical',documentDate:'2026-01-02',dateBasis:'Редакция 4',versionLabel:'v2',htmlBundle:{entry:'site/index.html'},missingAssets:['img/a.png'],missingLinks:[{url:'/missing'}],externalResources:['https://example.test/x']};
const bundle={entry:'site/index.html',files:[{path:'z.css',hash:'z'.repeat(64),size:4},{path:'index.html',hash:'a'.repeat(64),size:2}]};
const same={...item,htmlBundle:{entry:bundle.entry,files:[bundle.files[1],bundle.files[0]]}},reordered={...item,htmlBundle:{entry:bundle.entry,files:[bundle.files[0],bundle.files[1]]}},changed={...reordered,htmlBundle:{...reordered.htmlBundle,files:[bundle.files[0],{...bundle.files[1],hash:'b'.repeat(64)}]}};
assert.equal(ui.comparisonText(same),ui.comparisonText(reordered));
assert.notEqual(ui.comparisonText(same),ui.comparisonText(changed));
const changedHash='"hash": "'+'b'.repeat(64)+'",';const changedLine=ui.comparisonText(changed).split('\n').find(line=>line.includes(changedHash));assert.equal(changedLine.trim(),changedHash);assert.ok(changedLine.length<500);
assert.equal(ui.comparisonText({format:'markdown',markdown:'# Hello'}),'# Hello');
const href=ui.url(item,'proj/name',12);
assert.equal(href,'/api/v1/knowledge/html/proj%2Fname/12/doc%2F1/files/site/index.html');
const html=ui.render(item,'proj/name',12);
assert.match(html,/class="d-html-document"/);
assert.match(html,/sandbox="allow-scripts"/);
assert.doesNotMatch(html,/allow-popups|allow-same-origin/);
assert.match(html,/src="[^"]+"/);assert.doesNotMatch(html,/scrolling="no"/);assert.match(html,/href="[^"]+" target="_blank"/);assert.doesNotMatch(html,/href="[^"]+\?hub-embed=1"/);
assert.doesNotMatch(html,/<iframe[^>]+style=/);assert.match(fs.readFileSync(process.argv[1]+'/html-documents.css','utf8'),/\.d-html-frame[^}]*background:var\(--bg\)/);assert.match(fs.readFileSync(process.argv[1]+'/html-documents.css','utf8'),/\.d-html-frame[^}]*height:clamp\(560px,75vh,1200px\)/);assert.match(fs.readFileSync(process.argv[1]+'/html-documents.css','utf8'),/\.d-html-frame[^}]*color-scheme:\s*dark/);
assert.match(html,/title="&lt;Danger&gt;"/);
assert.match(html,/target="_blank" rel="noopener noreferrer"/);
assert.ok(html.indexOf('Открыть отдельно')<html.indexOf('<iframe'));
assert.match(html,/Исторический материал/);assert.match(html,/2026-01-02/);assert.match(html,/Основание даты: Редакция 4/);assert.match(html,/v2/);
assert.match(html,/<details class="d-html-warning">/);assert.match(html,/<summary>Не найдены ресурсы/);
assert.match(html,/Не найдены ресурсы/);assert.match(html,/Не найдены ссылки/);assert.match(html,/Внешние ресурсы не выполняются в изолированном просмотре/);
assert.doesNotMatch(html,/<h1|Инспектор/);
/* Auto-height handshake tests intentionally removed with the feedback bridge. */
console.log('html document renderer passed');
'''
        result = subprocess.run(['node', '-e', script, str(WEB.resolve())], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_catalog_html_metadata_sorting_and_tree_collapse(self):
        script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ctx={window:{},history:{replaceState:()=>{}},console};vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/documentation.js','utf8'),ctx);
const ui=ctx.window.DocumentationUI;
const v={mode:'docs',selected:'',filters:{query:'',audience:'user',section:'',type:''},documentIndex:[
 {id:'old',title:'Same',audience:'user',section:'Guide',documentDate:'2025-01-01',format:'markdown',status:'historical'},
 {id:'new',title:'Same',audience:'user',section:'Guide',documentDate:'2026-01-01',format:'html',versionLabel:'v2',status:'current'}]};
let html=ui.catalog(v);assert.ok(html.indexOf('data-k-select="new"')<html.indexOf('data-k-select="old"'));
assert.match(html,/HTML/);assert.match(html,/Markdown/);assert.match(html,/2026-01-01/);assert.match(html,/Исторический материал/);
v.documentIndex.push({id:'nested',title:'Nested',audience:'user',section:'Guide / Nested',documentDate:'2024-01-01'});
html=ui.catalog(v);assert.match(html,/data-d-folder="Guide"[\s\S]*?<small>3<\/small>/);
assert.match(ui.toolbar(v),/Скрыть содержание/);
let selected=null,persisted=0,drawn=0;
const api={select:id=>selected=id,persist:()=>persisted++,draw:()=>drawn++,refresh:()=>{}};
assert.equal(ui.handleClick(v,{target:{closest:s=>s==='[data-d-tree-collapse]'?{}:null}},api),true);
assert.equal(v.filters.docsTreeCollapsed,true);assert.equal(persisted,1);assert.equal(drawn,1);
assert.doesNotMatch(ui.catalog(v),/data-k-select="new"/);
v.selected='new';v.filters.docsTreeCollapsed=false;html=ui.layout(v,'<article></article>');assert.match(html,/--d-tree-width:310px/);assert.match(html,/d-tree-splitter/);assert.match(html,/aria-orientation="vertical"/);
v.filters.docsTreeCollapsed=true;html=ui.layout(v,'<article></article>');assert.doesNotMatch(html,/d-tree-splitter|class="d-tree"/);assert.match(html,/d-space-layout-tree-collapsed/);assert.match(ui.toolbar(v),/Показать содержание/);
const css=fs.readFileSync(process.argv[1]+'/documentation.css','utf8');assert.match(css,/main:has\(\.knowledge-root\[data-k-mode="docs"\]\)/);assert.doesNotMatch(css,/\.d-page::before/);
const source=fs.readFileSync(process.argv[1]+'/documentation.js','utf8');assert.match(source,/bindResize/);assert.match(css,/d-tree-splitter/);
const split={setAttribute(name,value){this[name]=value;}};let containerWidth=1000;const pane={style:{setProperty(){}},getBoundingClientRect:()=>({width:containerWidth}),querySelector:()=>split};const listeners={};const root={querySelector:()=>pane,addEventListener:(name,fn)=>{listeners[name]=fn;},removeEventListener(){},contains:()=>true};let resizePersists=0;const cleanup=ui.bindResize(v,root,{persist:()=>resizePersists++});listeners.keydown({target:{closest:()=>split},key:'ArrowRight',preventDefault(){}});assert.equal(v.filters.docsTreeWidth,330);listeners.keydown({target:{closest:()=>split},key:'Home',preventDefault(){}});assert.equal(v.filters.docsTreeWidth,180);containerWidth=600;listeners.keydown({target:{closest:()=>split},key:'End',preventDefault(){}});assert.equal(v.filters.docsTreeWidth,232);assert.equal(split['aria-valuemax'],'232');assert.equal(resizePersists,3);cleanup();
console.log('documentation html catalog passed');
'''
        result = subprocess.run(['node', '-e', script, str(WEB.resolve())], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
