"""Subsystem editor VM contracts, without browser, model calls or live data."""
import subprocess
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/subsystems.js'
HARNESS = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let sequence=0;
const context={crypto:{randomUUID:()=>`fixture-${++sequence}`},
 HubI18n:{t:k=>k,error:e=>e.message},confirm:()=>{throw Error('Global confirmation is forbidden');}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const ui=context.HubSubsystems;
const wait=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
function fixture(){
 const v={mode:'architecture',project:'fixture-project',context:{revision:7,policy:{components:[{id:'component:one',title:'Existing',paths:['src/'],description:'Authored description'}]}}};
 const calls=[],agents=[],research=[],acks=[];
 const host={draws:0,refreshes:0,draw(){this.draws++;},async refresh(){this.refreshes++;v.context={...v.context,revision:v.context.revision+1};},
  async request(action,body,write){calls.push({action,body,serialized:JSON.stringify(body),write});
   if(action==='subsystem-plan')return {request:{expected:body.expected,key:body.key,operations:[{op:'put',id:body.identifier,patch:body.patch}]}};
   const ack=acks.shift();if(ack instanceof Error)throw ack;return ack||{accepted:true};},
  async agent(body){agents.push(body);const ack=acks.shift();if(ack instanceof Error)throw ack;return ack||{accepted:true};},
  openResearch(options){research.push(options);return Promise.resolve(options);}};
 const click=(action,id='')=>ui.handle(v,{type:'click',target:{closest:()=>({dataset:{subsystemAction:action,subsystemId:id}})},preventDefault(){}},host);
 const submit=()=>ui.handle(v,{type:'submit',target:{matches:s=>s==='[data-subsystem-form]'},preventDefault(){}},host);
 const input=(name,value)=>ui.input(v,{target:{name,value}});
 return {v,host,calls,agents,research,acks,click,submit,input};
}
async function actions(){
 const f=fixture(),project=ui.project(f.v),projectHtml=ui.actions(f.v,project),component=f.v.context.policy.components[0],componentHtml=ui.actions(f.v,component);
 assert.equal(typeof ui.toolbar,'undefined');
 for(const action of ['overview','first-level','new'])assert(projectHtml.includes(`data-subsystem-action="${action}"`));
 for(const action of ['edit','new','analyze','remove'])assert(componentHtml.includes(`data-subsystem-action="${action}"`));
 for(const action of ['overview','first-level'])assert(!componentHtml.includes(`data-subsystem-action="${action}"`));
 assert.doesNotMatch(projectHtml,/data-subsystem-action="edit"/);
}
async function editorScopes(){
 const f=fixture();f.v.context.policy.components.push(
  {id:'component:child',title:'Child',parent:'component:one'},
  {id:'component:grandchild',title:'Grandchild',parent:'component:child'},
  {id:'component:sibling',title:'Sibling'});
 f.click('new','component:one');assert.equal(f.v.subsystemEditor.draft.parent,'component:one');
 const childHtml=ui.dialogContent(f.v);assert.match(childHtml,/option value="component:one" selected/);
 const g=fixture();g.v.context.policy.components.push(
  {id:'component:child',title:'Child',parent:'component:one'},
  {id:'component:grandchild',title:'Grandchild',parent:'component:child'},
  {id:'component:sibling',title:'Sibling'});
 g.click('edit','component:one');const html=ui.dialogContent(g.v);
 assert.doesNotMatch(html,/value="component:one"/);assert.doesNotMatch(html,/value="component:child"/);assert.doesNotMatch(html,/value="component:grandchild"/);
 assert.match(html,/value="component:sibling"/);
}
async function save(){
 const f=fixture();f.click('new');const draft=f.v.subsystemEditor.draft;assert.equal(draft.expected,7);assert.equal(draft.action,'create');
 f.input('subsystemTitle','New subsystem');f.input('subsystemParent','component:one');f.input('subsystemPaths',' src/new/ \n\n assets/');f.input('subsystemDescription','New authored text');
 f.v.context.revision=9;
 // Submit has button=false; it must reach save without a TypeError.
 assert.equal(f.submit(),true);assert.equal(f.v.subsystemEditor.busy,true);await wait();
 assert.equal(f.calls.length,2);const plan=f.calls[0];assert.equal(plan.action,'subsystem-plan');assert.equal(plan.body.operation,'create');assert.equal(plan.body.expected,7);assert.equal(plan.body.identifier,draft.id);assert.equal(plan.write,true);
 assert.equal(plan.body.patch.title,'New subsystem');assert.equal(plan.body.patch.parent,'component:one');assert.equal(JSON.stringify(plan.body.patch.paths),'["src/new/","assets/"]');assert.equal(plan.body.patch.description,'New authored text');
 assert.equal(f.calls[1].action,'changeset');assert.equal(f.calls[1].body.expected,7);assert.equal(f.v.subsystemEditor.busy,false);assert.equal(f.v.subsystemEditor.pending,null);assert.equal(f.v.subsystemEditor.draft,null);assert.equal(f.host.refreshes,1);
 const g=fixture();g.click('edit','component:one');g.input('subsystemTitle','Renamed');g.submit();await wait();
 assert.equal(g.calls[0].body.operation,'update');assert.equal(g.calls[0].body.patch.title,'Renamed');assert.equal(Object.hasOwn(g.calls[0].body.patch,'description'),false);assert.equal(g.v.context.policy.components[0].description,'Authored description');
 g.click('edit','component:one');g.input('subsystemDescription','Edited description');g.submit();await wait();assert.equal(g.calls[2].body.patch.description,'Edited description');
}
async function retry(){
 const f=fixture();f.click('new');f.input('subsystemTitle','Draft');f.acks.push(Error('Lost acknowledgement'));f.submit();await wait();
 assert.equal(f.v.subsystemEditor.busy,false);const pending=f.v.subsystemEditor.pending,exact=JSON.stringify(pending);assert.ok(pending);assert.match(ui.dialogContent(f.v),/data-subsystem-action="retry"/);
 const count=f.calls.length;f.click('new');f.click('cancel');f.click('overview');assert.equal(f.calls.length,count);assert.equal(f.research.length,0,'Pending manual save blocks root research actions');assert.equal(f.v.subsystemEditor.draft.title,'Draft');assert.equal(f.v.subsystemEditor.confirm,null);assert.equal(JSON.stringify(pending),exact);
 f.v.context.revision=99;f.input('subsystemTitle','Changed local draft');
 // While an exact receipt is outstanding, submit is not an implicit retry.
 f.submit();await wait();assert.equal(f.calls.length,count);
 f.click('retry');await wait();assert.equal(f.calls.length,count+1);assert.strictEqual(f.calls.at(-1).body,pending);assert.equal(f.calls.at(-1).serialized,exact);assert.equal(f.v.subsystemEditor.pending,null);assert.equal(f.v.subsystemEditor.busy,false);
 const resumed=fixture();resumed.click('new');resumed.input('subsystemTitle','Keep this request');resumed.acks.push(Error('Lost acknowledgement'));resumed.submit();await wait();
 const receipt=resumed.v.subsystemEditor.pending,receiptText=JSON.stringify(receipt);assert.ok(receipt);
 resumed.v.subsystemEditor.open=false;resumed.click('resume');assert.equal(resumed.v.subsystemEditor.open,true);
 assert.equal(JSON.stringify(resumed.v.subsystemEditor.pending),receiptText);assert.match(ui.dialogContent(resumed.v),/data-subsystem-action="retry"/);
 const g=fixture();g.click('new');g.acks.push(Object.assign(Error('Revision conflict'),{status:409}));g.submit();await wait();assert.equal(g.v.subsystemEditor.pending,null);assert.equal(g.v.subsystemEditor.busy,false);assert.ok(g.v.subsystemEditor.draft);assert.equal(g.v.subsystemEditor.message,'Revision conflict');
 g.v.context.revision=8;g.submit();await wait();assert.equal(g.calls[2].action,'subsystem-plan');assert.notEqual(g.calls[0].body.key,g.calls[2].body.key);
}
async function nativeMount(){
 const nodes=[];let patched=0;
 const ctx=context,oldDocument=ctx.document,oldLive=ctx.HubLiveUI;
 ctx.document={activeElement:{isConnected:true,focus(){this.focused=true;}},body:{append(node){nodes.push(node);}},createElement(type){assert.equal(type,'dialog');const node={innerHTML:'',listeners:{},dataset:{},className:'',setAttribute(){},addEventListener(name,fn){this.listeners[name]=fn;},showModal(){this.opened=true;},remove(){this.removed=true;},querySelectorAll(){return [];}};return node;}};
 ctx.HubLiveUI={patch(node,html,options){patched++;assert.equal(options.preserveInputs,false);node.innerHTML=html;}};
 try {const f=fixture();f.click('new');ui.mount(f.v,f.host);assert.equal(nodes.length,1);const node=nodes[0];assert.equal(node.opened,true);f.v.subsystemEditor.message='Updated status';ui.mount(f.v,f.host);assert.equal(patched,1);assert.match(node.innerHTML,/Updated status/);f.v.subsystemEditor.open=false;ui.mount(f.v,f.host);assert.equal(node.removed,true);} finally {ctx.document=oldDocument;ctx.HubLiveUI=oldLive;}
}
async function confirmations(){
 for(const [action,template] of [['overview','explain'],['first-level','decompose']]){
  const f=fixture();f.click(action);assert.equal(f.v.subsystemEditor.confirm,null,'Root research does not use the manual-change confirmation');assert.equal(f.calls.length,0);assert.equal(f.agents.length,0);assert.equal(f.research.length,1);
  const options=f.research[0];assert.equal(options.id,'project:fixture-project');assert.equal(options.template,template);assert.equal(options.title,'subsystems.projectOverview');assert.equal(options.selected.type,'project');assert.equal(options.selected.id,'project:fixture-project');
 }
 const f=fixture();f.click('remove','component:one');assert.equal(f.v.subsystemEditor.confirm.action,'remove');assert.equal(f.v.subsystemEditor.confirm.expected,7);assert.equal(f.calls.length,0);assert.equal(f.research.length,0);assert.match(ui.dialogContent(f.v),/removeConfirm/);assert.doesNotMatch(ui.dialogContent(f.v),/analysisConfirm/);
 f.click('cancel-confirm');assert.equal(f.v.subsystemEditor.confirm,null);assert.equal(f.calls.length,0);f.click('remove','component:one');f.v.context.revision=8;f.click('confirm');await wait();assert.equal(f.v.subsystemEditor.busy,false);assert.equal(f.v.subsystemEditor.confirm,null);assert.equal(f.calls[0].body.operation,'remove');assert.equal(f.calls[0].body.expected,7);assert.equal(f.calls[0].body.identifier,'component:one');assert.equal(f.research.length,0);
}
({actions,editorScopes,nativeMount,save,retry,confirmations}[process.argv[2]])().catch(e=>{console.error(e);process.exitCode=1});
"""


class SubsystemsUiTest(unittest.TestCase):
    def check_contract(self, scenario):
        result = subprocess.run(['node', '-e', HARNESS, str(WEB), scenario], capture_output=True,
                                text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_project_and_component_actions_are_scoped(self):
        self.check_contract('actions')

    def test_child_prefills_parent_and_edit_excludes_descendants(self):
        self.check_contract('editorScopes')

    def test_native_dialog_mount_patches_and_disposes(self):
        self.check_contract('nativeMount')

    def test_create_submit_and_authored_description_preservation(self):
        self.check_contract('save')

    def test_pending_receipt_blocks_actions_and_retries_exact_request(self):
        self.check_contract('retry')

    def test_dialog_confirmations_and_busy_cleanup(self):
        self.check_contract('confirmations')


if __name__ == '__main__':
    unittest.main()
