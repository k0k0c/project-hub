"""Focused image attachment contracts, executed without a server or real data."""
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class ImageUiTest(unittest.TestCase):
    def run_js(self, code):
        result = subprocess.run(
            ['node', '-e', code, str(ROOT / 'tools/project-portal/web/images.js')],
            capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_gallery_union_encoding_and_provenance(self):
        self.run_js(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const handlers={};
const ctx={handlers,document:{addEventListener(name,listener){handlers[name]=listener;}},URL,URLSearchParams,location:{href:'http://localhost/'},
escape:s=>String(s??'').replaceAll('&','&amp;').replaceAll('"','&quot;').replaceAll('<','&lt;'),
projectApi:p=>p+'&project=test',uiIcon:name=>'<svg data-icon="'+name+'"></svg>'};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
vm.runInContext(`
for(const ext of IMAGE_EXTENSIONS) if(!isImagePath('dir/a.'+ext.toUpperCase())) throw Error(ext);
if(isImagePath('image.png.exe')) throw Error('false positive');
const source={path:'a.JPG',sourceProject:'origin',root:'/before'};
const task={sources:[source],stages:[{evidence:[{path:'a.JPG'},{path:'stage.webp'},{path:'doc.md'}]}]};
const union=taskImageSources(task);
if(union.length!==3 || union[0]!==source || task.sources.length!==1) throw Error('union mutated provenance');
const html=renderImageEvidence(union);
if((html.match(/data-image-path=/g)||[]).length!==2 || !html.includes('/api/evidence?')) throw Error('gallery');
if(!renderImageEvidence([{path:'hub-source/origin/hub-artifact/'+'a'.repeat(64)+'/opaque.bin'}]).includes('/api/artifact?')) throw Error('artifact original');
for(const [path,format,icon] of [['plan.HTML','HTML','fileCode'],['notes.md','Markdown','fileText'],['report.txt','Текст','fileText'],['app.log','Лог','fileText'],['report.pdf','PDF','fileText'],['table.xlsx','XLSX','spreadsheet'],['slides.pptx','PPTX','presentation'],['data.json','JSON','fileJson'],['source.py','PY','fileCode'],['backup.zip','ZIP','archive'],['song.mp3','MP3','audio'],['clip.mp4','MP4','video'],['unknown.xyz','XYZ','file'],['LICENSE','Файл','file']]) {
 const chip=renderImageEvidence([{path,label:'Document'}]);
 if(!chip.includes('data-icon="'+icon+'"') || !chip.includes('class="source-format">'+format+'</span>')) throw Error(path+' format');
}
for(const path of ['dir/a & b.HTML','hub-source/origin/hub-artifact/'+'a'.repeat(64)+'/plan.htm']) {
 const href=sourceUrl(path),params=new URLSearchParams(href.split('?')[1]);
 if(params.get('path')!==path || params.get('preview')!=='html' || params.get('project')!=='test') throw Error('HTML link');
 if(!renderImageEvidence([{path}]).includes('target="_blank"')) throw Error('HTML tab');
}
if(sourceUrl('opaque.bin').includes('preview=')) throw Error('changed download');
if(renderImageEvidence([{path:'doc.md',label:'<script>'}]).includes('<script>')) throw Error('document escaping');
if(!renderImageEvidence([{path:'<bad>.png',label:'<script>'}]).includes('&lt;script>')) throw Error('escaping');
const url=new URLSearchParams(imageUrl('a & b.png','original','archive','p').split('?')[1]);
if(url.get('path')!=='a & b.png'||url.get('mode')!=='archive'||url.get('preview')!=='original'||url.get('project')!=='p') throw Error('url');
const tile={dataset:{imagePath:'missing.png'},querySelector:()=>({hidden:false})};
const img={src:'http://localhost/api/image?path=missing.png&mode=current&preview=thumbnail',matches:s=>s==='.image-tile img',parentElement:tile};
handlers.error({target:img});
if(tile.dataset.imageMode!=='archive'||!img.src.includes('mode=archive')||img.hidden) throw Error('archive fallback');
handlers.error({target:img});
if(!img.hidden) throw Error('archive failure');
`,ctx);
''')

    def test_upload_limit_removal_busy_and_metadata(self):
        self.run_js(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Node {
 constructor(){this.children=[];this.parts={};this.value='';}
 querySelector(s){return this.parts[s] ||= new Node();}
 querySelectorAll(){return [];}
 append(n){this.children.push(n);}
 prepend(n){this.children.unshift(n);}
 remove(){this.removed=true;}
}
const sources=new Node(),rows=new Node(),form=new Node(),dialog=new Node(),panels=[];
form.parts['[data-sources]']=sources;sources.parts['[data-source-rows]']=rows;
dialog.parts.form=form;dialog.addEventListener=(name,fn)=>{dialog.close=fn};dialog.removeEventListener=()=>{};
const added=[];rows.insertAdjacentHTML=(where,html)=>{added.push(JSON.parse(html));rows.lastElementChild=new Node();};
let finish,requests=[],reads=0;
const document={addEventListener(){},createElement(){const n=new Node();panels.push(n);return n;}};
const ctx={document,URLSearchParams,URL:{createObjectURL:()=> 'blob:local',revokeObjectURL(){}},
escape:s=>String(s??''),uiIcon:()=>'',sourceRow:JSON.stringify,
FileReader:class {readAsDataURL(){reads++;this.result='data:image/png;base64,YQ==';this.onload();}},
editorRequest:async(...args)=>{requests.push(args);await new Promise(r=>finish=r);return{source:{path:'uploaded.png',sourceProject:'kept'}};}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const control=ctx.mountImageUploads(dialog,{sources:[],stages:[]},false,'captured');
const panel=sources.children[0],input=panel.querySelector('input'),pending=panel.querySelector('.image-upload-list');
(async()=>{
 input.files=[{name:'big.png',size:20*1024*1024+1},{name:'big.bin',size:20*1024*1024+1}];await input.onchange();
 assert.equal(requests.length,0);assert.equal(reads,0);assert.equal(pending.children.length,2);
 input.files=[{name:'first.png',size:1}];const run=input.onchange();await new Promise(r=>setImmediate(r));
 assert.equal(control.busy(),true);assert.equal(form.querySelector('[type=submit]').disabled,true);
 pending.children.at(-1).querySelector('button').onclick();finish();await run;
 assert.equal(added.length,0);assert.equal(control.busy(),false);
 input.files=[{name:'second.PNG',size:1}];const next=input.onchange();await new Promise(r=>setImmediate(r));finish();await next;
 assert.equal(added[0].sourceProject,'kept');assert.equal(requests[1][0],'/api/v1/artifacts/upload');
 assert.equal(requests[1][1].content,'YQ==');assert.equal(requests[1][2],'captured');
 input.files=[{name:'unknown.bin',size:1}];const binary=input.onchange();await new Promise(r=>setImmediate(r));finish();await binary;
 assert.equal(requests[2][0],'/api/v1/artifacts/upload');assert.equal(requests[2][1].name,'unknown.bin');
 control.setSaving(true);assert.equal(control.busy(),true);assert.equal(sources.disabled,true);
 control.setSaving(false);assert.equal(input.disabled,false);
 input.files=[{name:'closed.png',size:1}];const closing=input.onchange();await new Promise(r=>setImmediate(r));dialog.close();finish();await closing;
 assert.equal(added.length,2);
})().catch(e=>{console.error(e);process.exitCode=1});
''')

    def test_dialog_unsupported_download_and_focus(self):
        self.run_js(r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Node {
 constructor(){this.parts={};this.children=[];this.classList={toggle:()=>true};}
 querySelector(s){return this.parts[s] ||= new Node();}
 setAttribute(k,v){this[k]=v;}
 getAttribute(k){return this[k];}
 append(n){n.parent=this;this.children.push(n);}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
 replaceChildren(){this.children=[];}
 showModal(){this.open=true;}
 close(){this.open=false;this.onclose();}
}
let focused=false,source={available:true,image:{previewAvailable:false}},created=[],resolveSource;
const ctx={document:{activeElement:{isConnected:true,focus(){focused=true}},body:new Node(),addEventListener(){},createElement(){const n=new Node();created.push(n);return n;}},
activeProject:'project',URLSearchParams,uiIcon:()=>'',fetch:()=>new Promise(resolve=>{resolveSource=()=>resolve({ok:true,json:async()=>source});})};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
(async()=>{
 ctx.openImageDialog('photo.heic','archive');
 const d=created[0];assert.equal(d.open,true);
 assert.match(d.querySelector('.image-viewport').children[0].src,/preview=full/);
 assert.match(d.querySelector('[data-download]').href,/mode=archive&preview=original/);
 resolveSource();await new Promise(r=>setImmediate(r));
 assert.match(d.querySelector('.image-status').textContent,/оригинал/);
 assert.equal(d.querySelector('.image-viewport').children.length,0);
 source={available:true,image:{previewAvailable:true}};const loaded=d.querySelector('select').onchange();
 const img=d.querySelector('.image-viewport').children[0];assert.match(img.src,/preview=full/);
 resolveSource();await loaded;
 d.querySelector('[data-zoom]').onclick();await new Promise(r=>setImmediate(r));
 assert.equal(d.querySelector('[data-zoom]')['aria-pressed'],'true');
 assert.match(d.querySelector('.image-viewport').children[0].src,/preview=full/);
 d.querySelector('[data-close]').onclick();assert.equal(focused,true);
})().catch(e=>{console.error(e);process.exitCode=1});
''')

    def test_gallery_navigation_boundaries_metadata_and_stale_loads(self):
        self.run_js(r'''
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
class Node {
 constructor(){
  this.parts={};this.children=[];const classes=new Set();
  this.classList={remove:name=>classes.delete(name),contains:name=>classes.has(name),
   toggle:name=>{if(classes.has(name)){classes.delete(name);return false;}classes.add(name);return true;}};
 }
 querySelector(s){return this.parts[s] ||= new Node();}
 setAttribute(k,v){this[k]=v;}
 append(n){n.parent=this;this.children.push(n);}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this);}
 replaceChildren(){this.children=[];}
 showModal(){this.open=true;}
 close(){this.open=false;this.onclose();}
}
const handlers={},pending=[],created=[];let focused=0;
const artifact='hub-artifact/'+'a'.repeat(64)+'/last.png';
const tiles=[['first.png','current'],['middle.jpg','archive'],['middle.jpg','current'],['notes.md','current'],[artifact,'current']]
 .map(([imagePath,imageMode])=>({dataset:{imagePath,imageMode}}));
const gallery={querySelectorAll:()=>tiles};
const opener=tiles[1];opener.isConnected=true;opener.focus=()=>focused++;
opener.closest=selector=>{assert.equal(selector,'.image-gallery, [data-source-rows]');return gallery;};
const ctx={document:{activeElement:opener,body:new Node(),addEventListener:(name,fn)=>handlers[name]=fn,
 createElement(){const n=new Node();created.push(n);return n;}},activeProject:'captured-project',
 URLSearchParams,uiIcon:name=>'<svg data-icon="'+name+'"></svg>',
 fetch:url=>new Promise(resolve=>pending.push({url,resolve:source=>resolve({ok:true,json:async()=>source})}))};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(path.join(path.dirname(process.argv[1]),'locale-catalog.js'),'utf8'),ctx);
ctx.HubI18n={t:(key,params={})=>ctx.HubLocaleCatalog[key].en.replace(/\{(\w+)\}/g,(_,name)=>params[name])};
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const available={available:true,image:{previewAvailable:true}};
const flush=()=>new Promise(r=>setImmediate(r));
(async()=>{
 handlers.click({target:{closest:()=>opener}});
 const d=created[0],previous=d.querySelector('[data-image-prev]'),next=d.querySelector('[data-image-next]');
 const selector=d.querySelector('select'),viewport=d.querySelector('.image-viewport');
 assert.match(d.innerHTML,/Previous image/);assert.match(d.innerHTML,/Next image/);
 assert.equal(d.querySelector('strong').textContent,'middle.jpg');
 assert.equal(previous.disabled,false);assert.equal(next.disabled,false);
 assert.equal(selector.value,'archive');
 // Navigate while the original metadata request is still pending.
 ctx.activeProject='another-project';const forward=next.onclick();
 assert.equal(d.querySelector('strong').textContent,artifact);
 assert.equal(previous.disabled,false);assert.equal(next.disabled,true);
 assert.equal(selector.value,'current');assert.equal(selector.disabled,true);
 const params=new URLSearchParams(viewport.children[0].src.split('?')[1]);
 assert.equal(params.get('path'),artifact);assert.equal(params.get('project'),'captured-project');
 pending[1].resolve({...available,kind:'artifact'});await forward;
 assert.match(d.querySelector('[data-download]').href,/^\/api\/artifact\?/);
 const provenance=d.querySelector('[data-provenance]').textContent;
 pending[0].resolve({available:false});await flush();
 assert.equal(d.querySelector('[data-provenance]').textContent,provenance);
 assert.equal(viewport.children.length,1,'stale result removed the selected image');
 const count=pending.length;await next.onclick();assert.equal(pending.length,count,'wrapped past last image');
 const back=previous.onclick();assert.equal(d.querySelector('strong').textContent,'middle.jpg');
 assert.equal(selector.value,'archive');assert.equal(selector.disabled,false);
 assert.match(d.querySelector('[data-download]').href,/mode=archive&preview=original/);
 pending.at(-1).resolve(available);await back;
 d.querySelector('[data-zoom]').onclick();assert.equal(viewport.classList.contains('original-size'),true);
 const first=previous.onclick();assert.equal(d.querySelector('strong').textContent,'first.png');
 assert.equal(previous.disabled,true);assert.equal(next.disabled,false);
 assert.equal(viewport.classList.contains('original-size'),false);
 assert.equal(d.querySelector('[data-zoom]')['aria-pressed'],'false');
 pending.at(-1).resolve(available);await first;
 const before=pending.length;await previous.onclick();assert.equal(pending.length,before,'wrapped before first image');
 d.querySelector('[data-close]').onclick();assert.equal(focused,1);
 ctx.openImageDialog('single.png');
 assert.equal(previous.disabled,true);assert.equal(next.disabled,true);
 d.querySelector('[data-close]').onclick();pending.at(-1).resolve(available);await flush();
 assert.equal(viewport.children.length,0,'closed dialog was populated by a late response');
})().catch(e=>{console.error(e);process.exitCode=1});
''')
