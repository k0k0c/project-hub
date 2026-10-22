"""Batch UI requires a current concrete preview before crediting coverage."""
from pathlib import Path
import shutil
import subprocess
import unittest


class BatchUiTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_preview_confirmation_input_invalidation_and_original_versions(self):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/app.js'
        code = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const sha='a'.repeat(40),id='b'.repeat(64),blob='c'.repeat(64),change='d'.repeat(64),before='e'.repeat(64),after='f'.repeat(64);
const calls=[],field=value=>({value,disabled:false}),checkbox={value:'0',checked:true},commit=field(sha),reason=field('Reviewed ownership');
const feedback={textContent:''},adopt={disabled:true},close={},submit={},more={hidden:true},steps={html:'',insertAdjacentHTML(_,html){this.html+=html;}};
const review={innerHTML:'',querySelector:s=>s==='[data-steps]'?steps:more},events={},formEvents={};
const form={elements:{commit,reason},addEventListener:(n,f)=>formEvents[n]=f,
 querySelectorAll:s=>s==='[name="target"]:checked'?[checkbox]:[checkbox,commit,reason,adopt,close,submit,more]};
const dialog={setAttribute(){},addEventListener:(n,f)=>events[n]=f,showModal(){this.open=true;},close(){this.open=false;events.close();},remove(){this.removed=true;},
 querySelector:s=>({'form':form,'[role="alert"]':feedback,'[data-review]':review,'[data-adopt]':adopt,'[data-close]':close})[s]};
let failure=false,refreshes=0;
const ctx={URLSearchParams,Map,activeProject:'one',state:{revision:'r1',tasks:[{id:'task',title:'Task <unsafe>',status:'active',stages:[
 {id:'stage',title:'Stage',status:'done',gitCheckpoint:{id:'original',status:'error'}}]}]},
 escape:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),uiIcon:()=>'',
 document:{querySelector:()=>null,createElement:()=>dialog,body:{append(){}}},refresh:async()=>{refreshes++;},
 fetch:async(url,options)=>{
  const body=options?JSON.parse(options.body):null;calls.push({url,body});
  if(body){
   if(body.action==='reconcile')return {ok:!failure,json:async()=>failure?{error:'raw diagnostic',reasonCode:'batch_revision_changed'}:{checkpoints:[]}};
   return {ok:true,json:async()=>({ready:true,revision:'preview-r',batchId:id,batchBlob:blob,head:sha,targets:[{id:'original'}],changesetCount:1,pathsCount:1})};
  }
  const section=new URLSearchParams(url.split('?')[1]).get('section');
  return {ok:true,json:async()=>section==='changesets'?{items:[{id:change,associations:[{task:'task',stage:'stage'}]}],next:null}:
    {items:[{path:'unsafe<name>.txt',method:'exact-content-chain',before:{mode:'100644',size:1,blob:before},after:{mode:'100644',size:2,blob:after},members:[{changeset:change,hunksCount:0}]}],next:null}};
 }};
vm.createContext(ctx);
const source=fs.readFileSync(process.argv[1],'utf8');
vm.runInContext(source.slice(source.indexOf('function checkpointReason'),source.indexOf('function checkpointStatus')),ctx);
vm.runInContext(source.slice(source.indexOf('function batchTargets'),source.indexOf('function openCheckpointReconciliation')),ctx);
(async()=>{
 ctx.openCheckpointBatch('task','stage');assert.ok(dialog.open);assert.ok(adopt.disabled);
 assert.match(dialog.innerHTML,/Task &lt;unsafe>/);assert.match(dialog.innerHTML,/original/);
 await adopt.onclick();assert.equal(calls.length,0);
 await form.onsubmit({preventDefault(){}});assert.equal(adopt.disabled,false);
 assert.match(steps.html,/Task &lt;unsafe>/);assert.match(steps.html,/unsafe&lt;name>/);
 assert.match(steps.html,/version=e{64}/);assert.match(steps.html,/version=f{64}/);
 assert.match(steps.html,/changeset=d{64}/);assert.doesNotMatch(steps.html,/<name>/);
 ctx.state.revision='newer';failure=true;await adopt.onclick();
 assert.equal(calls.at(-1).body.expected,'preview-r');assert.equal(calls.at(-1).body.confirmed,id);
 assert.equal(adopt.disabled,true);assert.match(feedback.textContent,/Проект изменился/);assert.equal(feedback.title,'raw diagnostic');assert.ok(dialog.open);
 failure=false;await form.onsubmit({preventDefault(){}});assert.equal(adopt.disabled,false);
 formEvents.input();assert.equal(adopt.disabled,true);let count=calls.length;await adopt.onclick();assert.equal(calls.length,count);
 await form.onsubmit({preventDefault(){}});ctx.activeProject='other';count=calls.length;
 await adopt.onclick();assert.equal(calls.length,count);assert.match(feedback.textContent,/Проект изменился/);
 ctx.activeProject='one';await adopt.onclick();assert.equal(refreshes,1);assert.ok(dialog.removed);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-e', code, str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
