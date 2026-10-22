"""Import selection, folder settings and local-action browser contracts."""
from pathlib import Path
import shutil
import subprocess
import unittest


WEB = Path(__file__).resolve().parents[2] / "tools/project-portal/web"


@unittest.skipUnless(shutil.which("node"), "Node is required")
class StorageUiTest(unittest.TestCase):
    def run_js(self, code):
        result = subprocess.run(
            ["node", "-e", code, str(WEB)], capture_output=True,
            text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_add_and_full_restore_share_preview_and_preserve_active_path(self):
        self.run_js(r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const web=process.argv[1],calls=[],events={},timers=[],begins=[];
const root={dataset:{},isConnected:true,html:'',addEventListener:(type,handler)=>events[type]=handler,querySelector:()=>null};
const current=[{id:'conflict',name:'Current version'},{id:'identical',name:'Already here'},{id:'removed',name:'Current only'}];
const source=[{id:'new',name:'New project',tasks:4},{id:'conflict',name:'Source version',tasks:9},{id:'identical',name:'Already here',tasks:2},{id:'same-name',name:'Current only',tasks:3}];
const preview={path:'C:/temporary/source',sourcePath:'C:/Earlier data',revision:'checked-revision',storageSchemas:{registry:2},totalBytes:700,projects:source,copyId:'prepared',comparison:{projects:source.map(p=>({...p,exists:['conflict','identical'].includes(p.id),identical:p.id==='identical'})),currentProjects:current,activeRevision:'active-1',conflicts:[{type:'same-name',id:'same-name',currentId:'removed'}]}};
const catalog={activeHome:'C:/Active data',backupHome:'C:/Data backups',projectCount:3,projects:current,copies:[],jobs:[]};
const ctx={console,Date,Intl,Map,Set,location:{hash:'#projects/data',search:'?project=selected'},activeProject:'selected',
 document:{querySelector:()=>root},crypto:{randomUUID:()=> 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'},
 sessionStorage:{getItem:()=>null,setItem(){}},setTimeout:fn=>{timers.push(fn);return timers.length},clearTimeout(){},
 confirm:()=>true,HubI18n:{locale:'en',t:(key,fallback)=>fallback || key},
 HubLiveUI:{patch:(target,html)=>target.html=html},
 backupStatus:{begin:body=>begins.push(body),acknowledge(){},refresh(){},afterRender(){},operations:()=>[],details:()=>''},
 fetch:async(url,options={})=>{const body=options.body?JSON.parse(options.body):null;calls.push({url,body});return {ok:true,json:async()=>body?{operation:{id:'apply-operation',requestId:body.requestId,action:body.action,status:'succeeded',result:{}}}:catalog};}};
ctx.window=ctx;ctx.globalThis=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(web+'/storage.js','utf8'),ctx);
const tick=async()=>{for(let i=0;i<40;i++)await Promise.resolve()};
const change=(attrs,value,checked)=>events.change({target:{name:attrs.name || '',dataset:attrs.dataset || {},value,checked,hasAttribute:key=>Boolean(attrs[key])}});
const click=action=>events.click({target:{closest:()=>({dataset:{storageAction:action}})}});
(async()=>{
 ctx.HubStorageUI.afterRender(root);await tick();ctx.HubStorageUI.preview(preview);
 assert.match(root.html,/Add projects/);assert.match(root.html,/Restore the entire data store/);assert.match(root.html,/same name and different identifiers/);
 assert.doesNotMatch(root.html,/activate-copy|data-storage-action="activate"|Use this copy|[А-Яа-яЁё]/);
 let summary=ctx.HubStorageUI.summary();assert.deepEqual(Array.from(summary.added,p=>p.id),['new','same-name']);assert.equal(summary.replaced.length,0);
 assert.match(root.html,/backup of current data/);assert.match(root.html,/briefly restarts the server/);
 change({dataset:{storageProject:'same-name'}},'',false);change({dataset:{storageResolution:'conflict'}},'replace');
 change({'data-storage-confirm':true},'',true);click('apply');await tick();
 const add=calls.find(call=>call.body?.action==='apply-import').body;
 assert.equal(add.mode,'add');assert.equal(add.id,'prepared');assert.equal(add.expected,'checked-revision');
 assert.deepEqual(Array.from(add.projects),['new','conflict','identical']);assert.deepEqual(add.resolutions,{conflict:'replace',identical:'skip'});
 assert.equal(add.includeGlobals,false);assert.equal(add.confirmed,true);assert.equal(add.origin.project,'selected');assert.equal(catalog.activeHome,'C:/Active data');
 ctx.HubStorageUI.preview(preview);change({name:'storage-mode'},'replace-all');
 summary=ctx.HubStorageUI.summary();assert.deepEqual(Array.from(summary.removed,p=>p.id),['removed']);
 assert.match(root.html,/Removed from active data/);assert.match(root.html,/Current only/);assert.match(root.html,/Current instructions and settings will be retained/);
 change({'data-storage-globals':true},'',true);assert.match(root.html,/Will be replaced by source instructions and settings/);
 change({'data-storage-confirm':true},'',true);click('apply');await tick();
 const all=calls.filter(call=>call.body?.action==='apply-import').at(-1).body;
 assert.equal(all.mode,'replace-all');assert.equal(all.includeGlobals,true);assert.equal(all.projects.length,4);
 assert.ok(begins.every(body=>body.requestId));assert.ok(calls.every(call=>call.body?.action!=='activate-copy'));
})().catch(error=>{console.error(error);process.exitCode=1});
''')

    def test_background_inspection_and_unknown_outcome_retry_use_one_request(self):
        self.run_js(r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const events={},calls=[],begins=[],uncertain=[],stored=new Map(),root={dataset:{},isConnected:true,addEventListener:(kind,fn)=>events[kind]=fn};
let fail=true;
const ctx={console,Date,Map,Set,location:{hash:'#projects/data',search:''},document:{querySelector:()=>root},
 crypto:{randomUUID:()=> 'abcdefab-cdef-abcd-efab-cdefabcdefab'},setTimeout:()=>1,clearTimeout(){},
 sessionStorage:{getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value)},
 HubLiveUI:{patch:(target,html)=>target.html=html},backupStatus:{begin:body=>begins.push(body),uncertain:body=>uncertain.push(body),acknowledge(){},refresh(){},operations:()=>[],afterRender(){},details:()=>''},
 fetch:async(url,opts={})=>{const body=opts.body?JSON.parse(opts.body):null;calls.push({url,body});if(body && fail)throw TypeError('network');return {ok:true,json:async()=>body?{job:{id:'inspection',requestId:body.requestId,action:body.action,status:'running'}}:{activeHome:'/active',backupHome:'/backups',copies:[],jobs:[]}};}};
ctx.window=ctx;ctx.globalThis=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1]+'/storage.js','utf8'),ctx);
const tick=async()=>{for(let i=0;i<30;i++)await Promise.resolve()};
(async()=>{
 ctx.HubStorageUI.afterRender(root);await tick();events.input({target:{name:'path',value:'C:/Previous Hub'}});
 events.submit({target:{matches:()=>true},preventDefault(){}});await tick();
 const first=calls.find(call=>call.body).body;assert.equal(first.action,'inspect-folder');assert.equal(first.background,true);assert.equal(first.path,'C:/Previous Hub');
 assert.equal(begins.length,1);assert.equal(uncertain.length,1);assert.match(root.html,/data-storage-action="retry"/);assert.ok(stored.get('project-hub-storage-requests').includes(first.requestId));
 fail=false;events.click({target:{closest:()=>({dataset:{storageAction:'retry',requestId:first.requestId}})}});await tick();
 const posts=calls.filter(call=>call.body);assert.equal(posts.length,2);assert.deepEqual(posts[0].body,posts[1].body);
 assert.doesNotMatch(root.html,/data-storage-action="retry"/);
 events.submit({target:{matches:()=>true},preventDefault(){}});await tick();assert.equal(calls.filter(call=>call.body).length,2,'repeated inspection reuses the accepted operation');
})().catch(error=>{console.error(error);process.exitCode=1});
''')

    def test_folder_settings_without_a_project_validate_before_application(self):
        self.run_js(r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const calls=[],events={},begins=[],root={innerHTML:''};
const ctx={console,Date,Map,Set,state:null,activeProject:null,escape:value=>String(value??''),uiIcon:()=>'',title(){},route:()=>['settings'],render(){},taskTableColumns:[],
 document:{addEventListener:(name,fn)=>(events[name]??=[]).push(fn),getElementById:id=>id==='hub-folder-settings'?root:null,querySelectorAll:()=>[]},
 crypto:{randomUUID:()=> 'abcdefab-cdef-abcd-efab-cdefabcdefab'},sessionStorage:{getItem:()=>null},
 HubI18n:{locale:'en',t:(key,fallback)=>typeof fallback==='string'?fallback:key},
 HubLocalFiles:{chooser:(kind,target)=>`<button data-local-folder="${kind}" data-local-target="${target}">Choose folder</button>`,pathLink:(path,kind)=>`<button data-local-open="${kind}">${path||'—'}</button>`},
 backupStatus:{begin:body=>begins.push(body),acknowledge(){},refresh(){},afterRender(){},details:()=>''},
 fetch:async(url,opts={})=>{const body=opts.body?JSON.parse(opts.body):null;calls.push({url,body});return {ok:true,json:async()=>!body?{folderSettings:{available:true,dataHome:'C:/Active',backupHome:'C:/Data backups'}}:body.confirmed?{operation:{id:'move',requestId:body.requestId,status:'queued'}}:{preview:{dataHome:body.dataHome,backupHome:body.backupHome,archives:'remain'}}};},confirm:()=>true};
ctx.window=ctx;ctx.globalThis=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1]+'/settings.js','utf8'),ctx);
(async()=>{
 await ctx.loadStorageFolderSettings();assert.match(ctx.storageFolderSettingsPanel(),/Entire installation/);assert.match(ctx.storageFolderSettingsPanel(),/data-local-folder="data"/);
 vm.runInContext("storageFolderSettings.dataHome='D:/Selected data'; storageFolderSettings.dirty=true",ctx);
 await ctx.submitStorageFolders(false);assert.equal(calls.at(-1).body.confirmed,false);assert.equal(begins.length,0);
 assert.match(ctx.storageFolderSettingsPanel(),/Existing archives remain/);assert.match(ctx.storageFolderSettingsPanel(),/Apply folder changes/);
 await ctx.submitStorageFolders(true);assert.equal(calls.at(-1).body.confirmed,true);assert.equal(begins.length,1);
 assert.equal(calls.at(-1).body.dataHome,'D:/Selected data');assert.equal(calls.at(-1).body.origin.section,'settings');
 assert.doesNotMatch(ctx.storageFolderSettingsPanel(),/data-storage-folders-action="apply"/,'accepted changes cannot be applied twice by repeating the same button');
})().catch(error=>{console.error(error);process.exitCode=1});
''')

    def test_local_picker_cancel_and_paths_with_spaces_and_unicode(self):
        self.run_js(r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const calls=[],responses=[{cancelled:true},{path:'D:/Example files/Данные'},{opened:true},{opened:true}],ctx={console,HubI18n:{locale:'en'},document:{addEventListener(){}},
 fetch:async(url,opts)=>{calls.push({url,body:JSON.parse(opts.body)});return {ok:true,json:async()=>responses.shift()};}};
ctx.window=ctx;ctx.globalThis=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1]+'/local-files.js','utf8'),ctx);
(async()=>{
 assert.equal(await ctx.HubLocalFiles.chooseFolder('import','C:/Earlier data'),null);
 const path=await ctx.HubLocalFiles.chooseFolder('data');assert.equal(path,'D:/Example files/Данные');await ctx.HubLocalFiles.openFolder('data',path);
 await ctx.HubLocalFiles.openFolder('backups','D:/Example files/archive.zip',null,true);
 assert.equal(calls[2].body.path,path);assert.equal(calls[3].body.reveal,true);
 const html=ctx.HubLocalFiles.pathLink('<unsafe>/Folder','workspace',{project:'one'});assert.match(html,/&lt;unsafe&gt;/);assert.match(html,/data-local-copy/);assert.match(html,/data-project="one"/);
})().catch(error=>{console.error(error);process.exitCode=1});
''')
