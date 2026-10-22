import shutil
import subprocess
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / 'tools/project-portal/web'


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class DocumentationUiTest(unittest.TestCase):
    def test_spaces_tree_links_pagination_and_concurrent_refresh(self):
        script = r'''
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const ctx={window:{},history:{replaceState:()=>{}},console};vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/documentation.js','utf8'),ctx);
const ui=ctx.window.DocumentationUI;
const v={mode:'docs',selected:'',filters:{query:'',audience:'',section:'',type:''},context:{revision:7,policy:{audiences:['custom-team']}},drafts:new Map(),items:[]};
(async()=>{
let calls=0;const all=Array.from({length:251},(_,i)=>({kind:'document',id:'doc:'+i,title:'Page '+i,audience:i===250?'user':'developer',section:'Guide / Build'}));
await ui.ensureIndex(v,async(_a,args)=>{calls++;const end=Math.min(args.offset+200,all.length);return {revision:7,items:all.slice(args.offset,end),more:end<all.length,next:end<all.length?end:null};});
assert.equal(calls,2);assert.equal(v.documentIndex.length,251);
await ui.ensureIndex(v,()=>{throw Error('Unchanged index must be reused');});
let html=ui.layout(v,'');assert.match(html,/Руководство пользователя/);assert.match(html,/Разработка приложения/);assert.match(html,/data-d-space="custom-team"/);assert.doesNotMatch(html,/Аудитория|<select|d-tree/);
v.filters.audience='developer';html=ui.layout(v,'');assert.match(html,/Дерево документации/);assert.match(html,/data-d-folder="Guide\/Build"/);assert.doesNotMatch(html,/doc%3A250/);
v.selected='doc:250';html=ui.layout(v,'<article>Loaded article</article>');assert.match(html,/Руководство пользователя/);assert.match(html,/doc%3A250/);assert.doesNotMatch(html,/doc%3A249/);
const article=v.documentIndex.find(d=>d.id==='doc:250');article.markdown='# Page 250\n\nBody';
const panel='<article><h2>Page 250</h2><div class="k-markdown"><h1>Page 250</h1><p>Body</p></div><textarea># Page 250\n\nBody</textarea></article>';
html=ui.layout(v,panel);assert.doesNotMatch(html,/<h1>Page 250<\/h1>/);assert.match(html,/<h2>Page 250<\/h2>/);assert.match(html,/<textarea># Page 250/);assert.equal(article.markdown,'# Page 250\n\nBody');
article.markdown='# Another heading\n\nBody';html=ui.layout(v,panel.replace('<h1>Page 250</h1>','<h1>Another heading</h1>'));assert.match(html,/<h1>Another heading<\/h1>/);
v.selected='';v.filters.audience='developer';v.documentIndex.push({kind:'document',id:'doc:unsafe',title:'<img src=x onerror=alert(1)>',audience:'developer',section:'<script>'});
html=ui.catalog(v);assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img|<script/);
let selected=null,refreshed=0,persisted=0;const api={select:id=>{selected=id;v.selected=id;},refresh:()=>refreshed++,draw:()=>{},persist:()=>persisted++};
assert.equal(ui.handleClick(v,{preventDefault(){},target:{closest:selector=>selector==='[data-d-home]'?{}:null}},api),true);
assert.equal(selected,'');assert.equal(v.filters.audience,'');assert.equal(persisted,1);assert.equal(refreshed,1);
v.context.revision=8;await assert.rejects(()=>ui.ensureIndex(v,async()=>({revision:7,items:[]})),/обновилась/);assert.equal(v.documentIndexRevision,7);
console.log('documentation contracts passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-e', script, str(WEB.resolve())], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
