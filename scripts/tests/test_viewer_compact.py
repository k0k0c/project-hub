"""Exercise the viewer with an isolated DOM/fetch fixture; no Hub data access."""
import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('node'), 'Node.js is required')
class CompactViewerTests(unittest.TestCase):
    def test_source_toggle_metadata_and_status(self):
        script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor() { this.hidden=false; this.value=''; this.textContent=''; this.attrs={};
    this.options=[{},{}]; this.classList={toggle(){},remove(){},add(){}}; }
  setAttribute(k,v){this.attrs[k]=v;}
  removeAttribute(k){delete this.attrs[k];}
  append(){} replaceChildren(){} querySelectorAll(){return [];} contains(){return false;}
  addEventListener(k,v){this[k]=v;} showModal(){this.open=true;}
}
const elements={}; const dialog=new Element(); const controls=new Element();
dialog.querySelector=s=>s==='.artifact-controls'?controls:(elements[s]??=new Element());
const document={body:new Element(),createElement:tag=>tag==='dialog'?dialog:new Element(),
  createTextNode:text=>({textContent:text}),addEventListener(k,v){this[k]=v;}};
const source={available:true,currentAvailable:true,archiveAvailable:true,kind:'current',
  path:'fixture.py',sourceProject:'temporary',projectRoot:'/fixture',resolvedPath:'/fixture/fixture.py',
  version:'v1',modifiedAt:'today'};
let unavailable=false, failure=false, documentFailure=false, content='one\ntwo\nthree';
const requests=[];
const sandbox={document,uiIcon:()=>'<svg></svg>',window:{projectApi:x=>x},URL,URLSearchParams,AbortController,
  marked:{parse:x=>x},DOMPurify:{sanitize:x=>x},
  hljs:{getLanguage:()=>false},fetch:async url=>(requests.push(url),{ok:!failure && !((unavailable || documentFailure) && !url.startsWith('/api/source')),status:500,
    json:async()=>failure?{error:'fixture failure'}:documentFailure && !url.startsWith('/api/source')?{error:'Source exceeds preview limit'}:url.startsWith('/api/source')?
      {...source,available:!unavailable}:url.startsWith('/api/log')?
      {source,rows:[],more:false,next:100,size:200}: unavailable?{error:'missing file'}:{source,text:content}})};
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),sandbox);
const el=id=>dialog.querySelector('#artifact-'+id);
assert.match(dialog.innerHTML,/aria-expanded="false" aria-controls="artifact-provenance"/);
assert.match(dialog.innerHTML,/<p id="artifact-provenance" hidden>/);
el('provenance').hidden=true;
el('source-toggle').onclick();
assert.equal(el('provenance').hidden,false);
assert.equal(el('source-toggle').attrs['aria-expanded'],'true');
el('source-toggle').onclick();
assert.equal(el('provenance').hidden,true);
const settle=()=>new Promise(resolve=>setImmediate(resolve));
async function open(path){document.click({target:{closest:()=>({href:'http://fixture/api/evidence?path='+path})},preventDefault(){}});await settle();}
(async()=>{
  let intercepted=false;
  document.click({target:{closest:()=>({href:'http://fixture/api/evidence?path=plan.html&preview=html'})},preventDefault(){intercepted=true;}});
  assert.equal(intercepted,false);assert.equal(requests.length,0);
  await open('fixture.py');
  assert.equal(requests.length,1);assert.match(requests[0],/^\/api\/document/);
  assert.match(el('metadata').textContent,/python.*3 строк/);
  assert.match(el('status').textContent,/Поиск по всему документу/);
  assert.equal(el('provenance').textContent.split('\n').length,7);
  assert.equal(el('provenance').hidden,true);
  el('source-toggle').onclick();dialog.close();
  assert.equal(el('source-toggle').attrs['aria-expanded'],'false');
  await open('fixture.md');
  assert.match(el('metadata').textContent,/Markdown.*3 строк/);
  assert.match(el('status').textContent,/13 символов.*поиск/);
  content='';await open('empty.txt');
  assert.match(el('metadata').textContent,/Текст.*0 строк/);
  await open('fixture.log');
  assert.match(el('metadata').textContent,/Лог.*0 строк на странице/);
  assert.match(el('status').textContent,/Страница 1.*50%.*совпадений/);
  assert.equal(requests.some(url=>url.startsWith('/api/source')),false);
  documentFailure=true;await open('large.py');
  assert.match(el('status').textContent,/Файл превышает лимит/);
  assert.match(el('provenance').textContent,/Исходный проект: temporary/);
  assert.equal(el('raw').hidden,false);assert.equal(el('source-mode').options[1].textContent,'Архив');
  documentFailure=false;
  unavailable=true;await open('fixture.py');
  assert.match(el('status').textContent,/Текущий файл недоступен/);
  assert.equal(el('metadata').textContent,'');
  failure=true;await open('fixture.py');
  assert.match(el('status').textContent,/fixture failure/);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result = subprocess.run(
            ['node', '-e', script, str(ROOT / 'tools/project-portal/web/viewer.js')],
            capture_output=True, text=True, encoding='utf-8', timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
