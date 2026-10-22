"""Exercise task form serialization with isolated DOM doubles."""
from pathlib import Path
import shutil
import subprocess
import unittest


class TaskEditorTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_old_save_and_reload_cannot_close_reopened_editor_or_replace_draft(self):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/task-editor.js'
        code = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const dialogs=[],requests=[],reloads=[];
class Dialog {
 constructor(){this.open=false;}
 setAttribute(){} addEventListener(){}
 set innerHTML(html){const title=html.match(/name="title"[^>]*value="([^"]*)"/);const values={title:title?.[1]||'',summary:'',status:'planned',type:'task',priority:'',parentTask:'',weight:'',scope:'',acceptance:'',deferred:'',confidence:'',note:'',percentLow:'',percentHigh:'',hoursLow:'',hoursHigh:''};
  const submit={disabled:false},error={hidden:true,textContent:''};this.reload={};this.form={values,submit,error,querySelector:s=>s==='[type=submit]'?submit:error,querySelectorAll:()=>[]};}
 querySelector(s){return s==='form'?this.form:s==='[data-editor-reload]'?this.reload:{};}
 showModal(){this.open=true;} close(){this.open=false;}
}
const ctx={URL,document:{body:{append(){}},createElement(){const dialog=new Dialog();dialogs.push(dialog);return dialog;},addEventListener(){}},
 location:{origin:'http://fixture',hash:'#tasks/a'},activeProject:'fixture',state:{revision:1,tasks:[{id:'a',title:'Task A',stages:[]},{id:'b',title:'Task B',stages:[]}]},
 escape:s=>String(s??''),labels:{planned:'Planned'},uiIcon:()=>'',FormData:class{constructor(form){this.values={...form.values};}get(k){return this.values[k]??'';}getAll(){return[];}},taskLink:t=>'#tasks/'+t.id,confirm:()=>true,refresh:async()=>{}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
ctx.editorRequest=(path,body)=>new Promise((resolve,reject)=>requests.push({path,body,resolve,reject}));
const dialog=dialogs[0],submit=form=>form.onsubmit({currentTarget:form,preventDefault(){}});
(async()=>{
 ctx.openTaskEditor('a');const old=dialog.form;old.values.title='Saved A';const pending=submit(old);assert.equal(requests.length,1);
 dialog.close();ctx.openTaskEditor('b');const newer=dialog.form;newer.values.title='Unsaved B';requests.shift().resolve({});await pending;
 assert.equal(dialog.open,true,'old success cannot close another editor');assert.strictEqual(dialog.form,newer);assert.equal(newer.values.title,'Unsaved B');assert.equal(newer.submit.disabled,false);assert.equal(ctx.location.hash,'#tasks/a');
 dialog.close();ctx.openTaskEditor('a');dialog.form.values.title='Failed A';const failed=submit(dialog.form);dialog.close();ctx.openTaskEditor('b');dialog.form.values.title='Still unsaved B';requests.shift().reject(Error('Old request failure'));await failed;
 assert.equal(dialog.open,true);assert.equal(dialog.form.values.title,'Still unsaved B');assert.equal(dialog.form.error.hidden,true,'old failure cannot publish an error to another opening');
 // A refresh started by the old Reload button must not replace the next editor.
 dialog.close();ctx.openTaskEditor('a');ctx.refresh=()=>new Promise(resolve=>reloads.push(resolve));const loading=dialog.reload.onclick();assert.equal(reloads.length,1);
 dialog.close();ctx.openTaskEditor('b');const latest=dialog.form;latest.values.title='Latest B draft';reloads.shift()();await loading;
 assert.equal(dialog.open,true);assert.strictEqual(dialog.form,latest);assert.equal(latest.values.title,'Latest B draft');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run(['node', '-e', code, str(source)], capture_output=True,
                                text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_edit_submit_preserves_sources_and_uses_captured_revision(self):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/task-editor.js'
        code = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const form={querySelector:s=>({disabled:false,hidden:true}),querySelectorAll:s=>s==='[data-source-row]'?[{dataset:{original:JSON.stringify({path:'file.md',label:'Original',sourceProject:'origin',root:'/old'})},querySelector:s=>({value:s==='[data-source-label]'?'Edited':'file.md'})}]:[]};
const dialogs=[]; const document={body:{append(){}},createElement:()=>{const d={setAttribute(){},addEventListener(){},querySelector:s=>s==='form'?form:{},showModal(){this.open=true},close(){this.open=false}};dialogs.push(d);return d;},addEventListener(){}};
const values={title:' Edited task ',summary:'Summary',status:'active',scope:' A\n\n B ',acceptance:'Check',deferred:'',type:'bug',priority:'major',parentTask:'',weight:'',percentLow:'20',percentHigh:'40',hoursLow:'1',hoursHigh:'3',confidence:'low',note:'Because'};
const requests=[];const ctx={document,URL,location:{origin:'http://fixture'},activeProject:'project',state:{revision:'original',tasks:[{id:'t',title:'Task',status:'active',stages:[],sources:[{path:'file.md'}]}]},escape:s=>String(s??'').replaceAll('"','&quot;'),labels:{planned:'Plan',active:'Active',done:'Done'},uiIcon:()=>'',FormData:class{get(k){return values[k]??''}getAll(){return[]}},refresh:async()=>{},taskLink:t=>'#tasks/'+t.id};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
ctx.editorRequest=async(path,body,project)=>{requests.push({path,body,project});return{}};
ctx.openTaskEditor('t');ctx.state.revision='newer';
(async()=>{
await form.onsubmit({preventDefault(){},currentTarget:form});
const r=requests[0];assert.equal(r.path,'/api/v1/tasks/update');assert.equal(r.body.expected,'original');assert.equal(r.body.patch.title,'Edited task');assert.deepEqual([...r.body.patch.scope],['A','B']);assert.equal(r.body.patch.sources[0].sourceProject,'origin');assert.equal(r.body.patch.sources[0].label,'Edited');assert.equal('weight' in r.body.patch,false);assert.equal(r.body.patch.estimate.percentHigh,40);
ctx.state.tasks[0]={...r.body.patch,id:'t',title:'Task',status:'active',stages:[],estimate:{...r.body.patch.estimate,updatedAt:'2026-09-20T01:00:00Z',updatedBy:'server'}};
ctx.openTaskEditor('t');await form.onsubmit({preventDefault(){},currentTarget:form});
assert.deepEqual(Object.keys(requests[1].body.patch),['title'],'title-only edit must omit unchanged estimate and its server metadata');
ctx.openTaskEditor('t');ctx.editorRequest=async()=>{throw Error('stale revision')};await form.onsubmit({preventDefault(){},currentTarget:form});assert.equal(dialogs[0].open,true);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result = subprocess.run(['node', '-e', code, str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_conflict_rebase_preserves_other_edits_and_never_retries_unknown_outcome(self):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/task-editor.js'
        code = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const document={body:{append(){}},createElement:()=>({addEventListener(){}}),addEventListener(){}};
const ctx={document,URL,location:{origin:'http://fixture'}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const original={id:'task',title:'Before',summary:'Original'},body={task:'task',patch:{title:'After'},expected:1};
let requests=[],fresh={revision:2,tasks:[{...original,summary:'Other edit'}]};
ctx.fetch=async url=>{assert.equal(url.searchParams.get('project'),'project');return{ok:true,json:async()=>fresh}};
function failOnce(status){requests=[];ctx.editorRequest=async(path,payload)=>{requests.push(payload);if(requests.length===1)throw Object.assign(Error('failure'),{status});return{saved:true}};}
(async()=>{
failOnce(409);assert.equal((await ctx.saveEditorPatch('/update',body,'project',original)).saved,true);
assert.equal(requests.length,2);assert.equal(requests[1].expected,2);assert.deepEqual(requests[1].patch,{title:'After'});
fresh.tasks[0].title='Concurrent title';failOnce(409);
await assert.rejects(()=>ctx.saveEditorPatch('/update',body,'project',original),/Черновик/);assert.equal(requests.length,1);
fresh.tasks=[];failOnce(409);await assert.rejects(()=>ctx.saveEditorPatch('/update',body,'project',original),/Черновик/);
failOnce(undefined);await assert.rejects(()=>ctx.saveEditorPatch('/update',body,'project',original),/failure/);assert.equal(requests.length,1);
fresh={revision:3,tasks:[{id:'task',stages:[{id:'stage',title:'Before',summary:'Other edit'}]}]};failOnce(409);
await ctx.saveEditorPatch('/stage',{...body,stage:'stage'},'project',original);assert.equal(requests[1].expected,3);
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result = subprocess.run(['node', '-e', code, str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
