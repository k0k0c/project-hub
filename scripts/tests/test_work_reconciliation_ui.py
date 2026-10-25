"""Dialog confirmation, frozen retries and CAS refusal in a small DOM harness."""
from pathlib import Path
import shutil
import subprocess
import unittest

WEB = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/work-reconciliation.js'


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class WorkReconciliationUiTests(unittest.TestCase):
    def test_active_confirmation_exact_retry_and_visible_observation(self):
        code = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const controls=Object.fromEntries(['work','status','reason','result','interrupt'].map(k=>[k,{value:k==='work'?'0':'',checked:false,disabled:false}]));
const form={elements:controls,querySelectorAll:()=>Object.values(controls)};
const nodes=Object.fromEntries(['[role="alert"]','[type="submit"]','[data-close]','[data-reload]','[data-more]','[data-active]','[data-previous]'].map(k=>[k,{hidden:false,disabled:false,textContent:'',after(node){this.afterNode=node;}}]));
const events={};let closed=false,posts=[],fail=true,conflict=false;
const dialog={isConnected:true,setAttribute(){},style:{},querySelector:s=>s==='form'?form:nodes[s],
 showModal(){},close(){closed=true;events.close?.();},remove(){this.isConnected=false;},addEventListener:(n,f)=>events[n]=f};
const work={id:'work-id',session:'old-owner',status:'active',revision:5,title:'Example',result:'Original result',checkpoint:'Original next step',evidence:['archive/proof.txt']};
const ctx={URL,URLSearchParams,console,CustomEvent:class{},location:{href:'http://localhost/?project=example'},
 document:{querySelector:()=>null,createElement:n=>n==='dialog'?dialog:{style:{}},body:{append(){}},addEventListener(){}},
 window:{dispatchEvent(){}},fetch:async(path,options)=>{
  if(!options?.body)return {ok:true,json:async()=>({work:[work],more:false,next:1})};
  posts.push(options.body);if(fail){fail=false;throw new Error('Lost reply');}
  return conflict?{ok:false,status:409,json:async()=>({error:'revision_conflict',message:'Changed'})}:{ok:true,json:async()=>({planSync:'saved'})};
 }};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
(async()=>{
 assert.match(ctx.window.WorkReconciliationUI.render({id:'<unsafe>'},'example'),/&lt;unsafe&gt;/);
 await ctx.window.WorkReconciliationUI.open('example','task');
 assert.match(nodes['[data-previous]'].afterNode.textContent,/work-id.*old-owner.*5.*Original next step.*archive\/proof.txt/);
 controls.reason.value='Coordinated cancellation';controls.result.value='Cancelled';
 const submit=()=>form.onsubmit({preventDefault(){}});
 await submit();assert.equal(posts.length,0);assert.match(nodes['[role="alert"]'].textContent,/подтвердите/);
 controls.interrupt.checked=true;await submit();assert.equal(posts.length,1);assert.equal(closed,false);
 assert.ok(Object.values(controls).every(c=>c.disabled));
 await submit();assert.equal(posts[0],posts[1]);assert.equal(closed,true);
 closed=false;dialog.isConnected=true;conflict=true;
 await ctx.window.WorkReconciliationUI.open('example','task');
 controls.reason.value='New decision';controls.result.value='Cancelled';controls.interrupt.checked=true;
 await submit();assert.equal(nodes['[type="submit"]'].disabled,true);
 const count=posts.length;await submit();assert.equal(posts.length,count);
 await nodes['[data-reload]'].onclick();assert.ok(Object.values(controls).every(c=>!c.disabled));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-e', code, str(WEB)], capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
