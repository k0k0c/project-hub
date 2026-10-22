"""Browser-independent ownership and layout contracts for real research state."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(shutil.which('node'),'Node is required for UI behavior contracts')
class ResearchUiTests(unittest.TestCase):
    def test_architecture_dialog_keeps_draft_while_loading_provider_and_sends_research_operation(self):
        script=r"""
(async()=>{
const fs=require('fs'),vm=require('vm'),assert=require('assert');let infoReady,submitted;
const handlers={},node={id:'a',title:'Alpha',kind:'entity',type:'class'};
const ctx={window:{crypto:{randomUUID:()=> 'research-1'},HubResearchRequests:{
 providers:async()=>({default:'provider-a',items:[{id:'provider-a',name:'Service',model:'model',configured:true}]}),
 providerField:(info,chosen,loading)=>loading?'<p>Loading provider</p>':`<select name="providerId"><option value="provider-a"${chosen==='provider-a'?' selected':''}>Service</option></select>`}},
 console,document:{addEventListener(){}},FormData:class{get(name){return {template:'explain',prompt:'Retained question',detailLevel:'detailed',providerId:'provider-a'}[name]}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);const ui=ctx.window.KnowledgeResearch;
const v={selected:'',project:'p',drafts:new Map([['a',{item:node}]]),filters:{},context:{revision:7}};
const root={querySelector:()=>null,addEventListener:(type,handler)=>handlers[type]=handler};
ui.attach(v,{root:()=>root,active:()=>true,model:()=>({nodes:[node],relations:[]}),draw(){},error:error=>{throw error;},
 agentInfo:async()=>new Promise(resolve=>infoReady=resolve),agent:async payload=>{submitted=payload;return {status:'failed',message:'Stop after recording'};}});
v.selected='a';ui.bind(v,root,{});
const opening=handlers.click({target:{closest:selector=>selector.includes('[data-r-action]')?{dataset:{rAction:'agent',rId:'a',rTemplate:'explain'}}:null},preventDefault(){},stopImmediatePropagation(){}});
await new Promise(resolve=>setImmediate(resolve));handlers.input({target:{name:'prompt',value:'Retained question'}});
infoReady({capabilities:{enabled:false,reason:'Native UI unavailable'},recent:[]});await opening;
const html=ui.auxiliary(v);assert(html.includes('Retained question'));assert(html.includes('value="provider-a" selected'));
assert(!/Native UI|threadId|data-agent-where|data-agent-mode|data-agent-intent/.test(html));
await handlers.submit({target:{matches:selector=>selector.includes('[data-r-agent-form]')},preventDefault(){}});
assert.equal(submitted.operation,'architecture-analyze');assert.equal(submitted.providerId,'provider-a');assert.equal(submitted.id,'a');
assert.equal(submitted.detailLevel,'detailed');assert(!('task' in submitted));assert(!('mode' in submitted));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_duplicate_operations_use_one_action_and_automatic_source(self):
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');let contextNode,submitted;
const context={window:{},console,setTimeout:()=>0,document:{addEventListener(){},createElement:()=>{const node={dataset:{},style:{},offsetWidth:100,setAttribute(){},querySelectorAll:()=>[],querySelector:()=>({focus(){}}),remove(){}};contextNode=node;return node;}},FormData:class{get(name){return {provider:'jdtls',depthPreset:'1',representation:'symbols'}[name];}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);const ui=context.window.KnowledgeResearch,selected={id:'a',kind:'entity',type:'class',title:'Alpha'},v={selected:'a',drafts:new Map([['a',{item:selected}]]),filters:{},context:{revision:1}},handlers={},root={querySelector:()=>null,addEventListener:(name,fn)=>handlers[name]=fn,append(){},getBoundingClientRect:()=>({left:0,top:0,width:800,height:600})};
ui.attach(v,{root:()=>root,model:()=>({nodes:[selected],relations:[]}),active:()=>false,draw(){},request:async(op,args)=>{submitted=args.query;return {id:'job',state:'queued',query:args.query};}});
const caps={operations:['base-types','implementations'].flatMap(id=>[{id,title:id,provider:'catalog',status:'available'},{id,title:id+' · сервер',provider:'jdtls',status:'available'}])};ui.state(v).capabilities.set('a',caps);
const inspector=ui.actions(v,selected);for(const id of ['base-types','implementations'])assert.equal((inspector.match(new RegExp('data-r-operation="'+id+'"','g'))||[]).length,1);
ui.menu(v,selected,10,10);for(const id of ['base-types','implementations'])assert.equal((contextNode.innerHTML.match(new RegExp('data-r-operation="'+id+'"','g'))||[]).length,1);
ui.bind(v,root,{});(async()=>{await handlers.click({target:{closest:s=>s.includes('[data-r-action]')?{dataset:{rAction:'query',rId:'a',rOperation:'base-types',rProvider:'catalog'}}:null},preventDefault(){},stopImmediatePropagation(){}});assert.equal(submitted.provider,'auto');assert.equal(submitted.depth,1);assert.equal(submitted.catalogOnly,undefined);assert.equal(ui.state(v).dialog,null);assert.equal(ui.auxiliary(v),'');})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        run=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)

    def test_actions_start_one_step_with_saved_representation_and_path_is_separate(self):
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={window:{},console,document:{addEventListener(){}},setTimeout(){}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);const ui=context.window.KnowledgeResearch;
const node={id:'a',kind:'entity',type:'class',title:'Alpha'},handlers={},queries=[];
const root={querySelector:()=>null,addEventListener:(name,fn)=>handlers[name]=fn};
const v={selected:'a',drafts:new Map([['a',{item:node}]]),filters:{},architectureSettings:{depth:'all',representation:'symbols-in-files'}};
ui.attach(v,{root:()=>root,model:()=>({nodes:[node],relations:[]}),active:()=>false,draw(){},request:async(op,args)=>{queries.push(args.query);return {id:'job',state:'queued',query:args.query};},error:e=>{throw e;}});ui.bind(v,root,{});
const click=dataset=>handlers.click({target:{closest:s=>s.includes('[data-r-action]')?{dataset}:null},preventDefault(){},stopImmediatePropagation(){}});
(async()=>{
for(const operation of ['definitions','definition','incoming','outgoing','base-types','implementations','incoming-calls','outgoing-calls']){
 await click({rAction:'query',rId:'a',rOperation:operation,rProvider:'catalog'});
 const q=queries.at(-1);assert.equal(q.depth,1);assert.equal(q.provider,'auto');assert.equal(q.representation,'symbols-in-files');assert.equal(q.catalogOnly,undefined);assert.equal(ui.state(v).dialog,null);
}
await click({rAction:'expand',rId:'a',rOperation:'children'});assert.equal(queries.at(-1).depth,1);assert.equal(queries.at(-1).provider,'catalog');assert.equal(queries.at(-1).catalogOnly,true);assert.equal(queries.at(-1).representation,'symbols-in-files');
v.architectureSettings.representation='symbols';await click({rAction:'query',rId:'a',rOperation:'outgoing'});assert.equal(queries.at(-1).representation,'symbols');
v.architectureSettings.representation='files';await click({rAction:'query',rId:'a',rOperation:'outgoing'});assert.equal(queries.at(-1).representation,'symbols-in-files');
ui.state(v).pair={a:node,b:{id:'b'}};await click({rAction:'pair-search'});assert.equal(queries.at(-1).depth,'all');assert.equal(queries.at(-1).operation,'path');assert.equal(queries.at(-1).target,'b');
assert.equal(queries.length,12,'One user action starts exactly one research job');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        run=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)

    def test_open_waits_for_complete_result_before_one_layout(self):
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={window:{},console,setTimeout:fn=>setImmediate(fn)};vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);const ui=context.window.KnowledgeResearch;
const selected={id:'code:class',kind:'entity',type:'class',title:'Example'},v={selected:'old',drafts:new Map(),filters:{},context:{revision:1}};
let release,draws=0,layouts=0;const ready=new Promise(resolve=>release=resolve);
ui.attach(v,{root:()=>null,active:()=>true,setSelected:n=>v.selected=n.id,draw:()=>{draws++;assert.equal(v.researchLoading,true);},redrawLayout:()=>{layouts++;assert.equal(v.researchLoading,false);},record(){},model:()=>v.researchCanvas,error:e=>{throw e;},request:async op=>op==='research'?{id:'job'}:op==='job'?ready.then(()=>({id:'job',state:'done',result:'result'})):{id:'result',query:{id:selected.id,operation:'outgoing'},status:'ready',items:[selected,{id:'neighbor',kind:'entity',type:'class'}],more:false}});
(async()=>{const opening=ui.open(v,selected.id,selected);await new Promise(resolve=>setImmediate(resolve));assert.equal(draws,1);assert.equal(layouts,0);release();await opening;assert.equal(layouts,1);assert.equal(v.researchCanvas.nodes.length,2);})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        run=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)

    def test_shared_expansion_pinned_nodes_initial_collapse_and_scenario(self):
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={window:{},console};vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const ui=context.window.KnowledgeResearch;
const n=id=>({id,kind:'entity',type:'class',title:id}),e=(id,a,b)=>({id,kind:'relation',type:'uses',from:a,to:b});
function view(base){const v={selected:'a',drafts:new Map(),filters:{},context:{revision:1},canvasSelection:[]};let renders=0;
 ui.attach(v,{model:()=>v.researchCanvas||base,redrawLayout:()=>renders++,record:()=>{},error:error=>{throw error;}});return v;}
function result(id,root,nodes,edges=[]){return {id,query:{id:root},nodes:nodes.map(n),relations:edges,status:'ready'};}
let v=view({nodes:[n('a'),n('manual')],relations:[]});
ui.apply(v,result('ab','a',['a','b'],[e('ab','a','b')]));
ui.apply(v,result('bc','b',['b','c'],[e('bc','b','c')]));
const saved=ui.snapshot(v);ui.collapse(v,'a');assert.deepEqual(v.researchCanvas.nodes.map(n=>n.id).sort(),['a','manual']);ui.restore(v,saved);assert.equal(ui.state(v).branches.size,2);ui.collapse(v,'a');assert.deepEqual(v.researchCanvas.nodes.map(n=>n.id).sort(),['a','manual']);
v=view({nodes:[n('a'),n('d')],relations:[]});
ui.apply(v,result('ab','a',['a','b']));ui.apply(v,result('bc','b',['b','c']));ui.apply(v,result('db','d',['d','b']));
ui.collapse(v,'a');assert.deepEqual(v.researchCanvas.nodes.map(n=>n.id).sort(),['a','b','c','d']);
ui.state(v).pinned.add('c');ui.collapse(v,'b');assert(v.researchCanvas.nodes.some(n=>n.id==='c'));
v=view({nodes:[],relations:[]});ui.apply(v,result('initial','a',['a','b']),true);ui.collapse(v,'a');assert.deepEqual(v.researchCanvas.nodes.map(n=>n.id),['a']);
v=view({nodes:[n('a'),n('b'),n('c')],relations:[e('ab','a','b'),e('bc','b','c')]});v.drafts.set('a',{item:{kind:'view'}});
ui.collapse(v,'b');assert.deepEqual(v.researchCanvas.nodes.map(n=>n.id).sort(),['a','b']);
const markup=ui.graph(v,{nodes:[n('a')],relations:[]},true);assert(markup.includes('expand-viewport'));assert(!markup.includes('data-k-group-by'));assert(!markup.includes('k-graph-relations'));
const toolbar=markup.match(/<div class="k-node-actions[^>]*>(.*?)<\/div>/)[1];
assert.equal((toolbar.match(/<button /g)||[]).length,1);assert(toolbar.includes('Действия выбранного узла'));
assert(markup.includes('data-k-action="toggle-list"'));assert(markup.includes('data-r-research-status'));
// The cancelling listener survives graph replacement because it belongs to
// the workspace, and captures before renderer listeners can stop propagation.
const handlers={};context.document={addEventListener:()=>{}};
const workspace={addEventListener:(type,fn,options)=>{handlers[type]={fn,options};}};
ui.bind(v,workspace,{});assert.equal(handlers.contextmenu.options.capture,true);
for(const surface of ['[data-k-cy]','.r-context','[data-k-node-actions]',null]){
 let prevented=false;handlers.contextmenu.fn({target:{closest:selector=>surface&&selector.includes(surface)},preventDefault:()=>{prevented=true;}});
 assert.equal(prevented,!!surface);
}
'''
        run=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)

    def test_auto_result_stays_in_originating_scope_and_history_is_bounded(self):
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const context={window:{},console,setTimeout:fn=>setImmediate(fn),FormData:class{get(name){return {depthPreset:'1',representation:'symbols'}[name];}},document:{addEventListener(){}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);const ui=context.window.KnowledgeResearch;
const n=id=>({id,kind:'entity',type:'class',title:id});
async function launch(changeScope){
 const v={selected:'a',drafts:new Map(),filters:{},context:{revision:1}},handlers={},root={querySelector:()=>null,addEventListener:(event,fn)=>handlers[event]=fn};let renders=0;
 const job={id:'j',kind:'research',state:'queued',query:{id:'a',operation:'outgoing'},object:{id:'a',title:'Alpha'}};
 let releaseResearch,releaseJob;const researchReady=new Promise(resolve=>{releaseResearch=resolve;});const jobReady=new Promise(resolve=>{releaseJob=resolve;});let submitted;
 ui.attach(v,{root:()=>root,model:()=>v.researchCanvas||{nodes:[n('a')],relations:[]},active:()=>true,draw:()=>{},redrawLayout:()=>renders++,record:()=>{},error:e=>{throw e;},request:async (op,args)=>{if(op==='research'){submitted=args.query;return researchReady.then(()=>job);}if(op==='job')return jobReady.then(()=>({...job,state:'done',result:'r'}));return {id:'r',query:job.query,status:'ready',items:[n('a'),n('b')],more:false,next:2};}});
 ui.bind(v,root,{});
 const submit=handlers.click({target:{closest:s=>s.includes('[data-r-action]')?{dataset:{rAction:'query',rId:'a',rOperation:'outgoing',rProvider:'catalog'}}:null},preventDefault(){},stopImmediatePropagation(){}});
 await new Promise(resolve=>setImmediate(resolve));const state=ui.state(v);assert.equal(state.dialog,null);assert.equal(state.currentJob.state,'preparing');assert.equal(submitted.provider,'auto');assert.equal(submitted.catalogOnly,undefined);assert.equal(!!v.researchLoading,false);
 releaseResearch();await submit;assert.equal(state.currentJob.state,'queued');if(changeScope)state.epoch++;
 releaseJob();await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));await new Promise(resolve=>setImmediate(resolve));
 assert.equal(renders,changeScope?0:1);assert.equal(!!v.researchCanvas,!changeScope);
 return v;
}
(async()=>{await launch(false);const v=await launch(true);const r=ui.state(v);r.dialog={type:'jobs',history:{offset:20,more:true,next:40}};r.jobs=Array.from({length:100},(_,i)=>({id:String(i),state:'done',createdAt:'2026-10-07T00:00:00Z',query:{id:'a',operation:'outgoing'},object:{title:'Alpha'}}));
 const html=ui.auxiliary(v);assert.equal((html.match(/class="r-job r-job-analyzer"/g)||[]).length,20);assert(html.includes('Что использует элемент'));assert(html.includes('Alpha'));assert(html.includes('data-r-offset="0"'));assert(html.includes('data-r-offset="40"'));
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        run=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)

    def test_context_menu_hides_node_actions_and_restores_on_close(self):
        script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let contextNode=null,documentKeydown;
const context={window:{},console,document:{addEventListener:(type,fn)=>{if(type==='keydown')documentKeydown=fn;},createElement:()=>{const n={className:'',dataset:{},style:{},offsetWidth:100,setAttribute(){},querySelectorAll:()=>[],querySelector:()=>({focus(){}}),remove:()=>{contextNode=null;}};return n;}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);const ui=context.window.KnowledgeResearch;
const node={id:'a',title:'Alpha',kind:'entity',type:'class'};const v={selected:'a',drafts:new Map([['a',{item:node}]]),filters:{},context:{revision:1},canvasItem:'a'};
const handlers={};const root={append:n=>{contextNode=n;},querySelector:s=>s==='.r-context'?contextNode:null,getBoundingClientRect:()=>({left:0,top:0,width:500,height:400}),addEventListener:(type,fn)=>{handlers[type]=fn;}};
let hidden=false;ui.attach(v,{root:()=>root,active:()=>true,model:()=>({nodes:[node],relations:[]}),setNodeActionsHidden:value=>{hidden=value;}});ui.state(v).capabilities.set('a',{operations:[{id:'children',provider:'catalog',title:'Children'},{id:'definitions',provider:'lsp',title:'Definitions'}]});
ui.bind(v,root,{});ui.menu(v,node,20,20);assert.equal(hidden,true);assert(contextNode);assert.equal(contextNode.dataset.rMenuId,'a');assert(contextNode.innerHTML.includes('data-r-operation="definitions"'),'Server definitions remain in research actions');
handlers.click({target:{closest:()=>null}});assert.equal(ui.state(v).menu,null);assert.equal(hidden,false);assert.equal(contextNode,null);
ui.menu(v,node,20,20);documentKeydown({key:'Escape',defaultPrevented:false,preventDefault(){}});assert.equal(ui.state(v).menu,null);assert.equal(hidden,false);
'''
        run=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)

    def test_agent_submit_closes_dialog_marks_node_and_polls_to_completion(self):
        script=r'''
(async()=>{
const fs=require('fs'),vm=require('vm'),assert=require('assert');let submit,agentCalls=0,polls=0,release;
const timers=[],marks=[];let receipt=null;
const status={hidden:true,textContent:'',dataset:{}};const context={window:{crypto:{randomUUID:()=> 'act-1'}},console,setTimeout:fn=>timers.push(fn),FormData:class{get(k){return k==='template'?'explain':'Goal';}},document:{addEventListener(){}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);const ui=context.window.KnowledgeResearch;
const node={id:'a',title:'Alpha',kind:'entity',type:'class'};const v={selected:'',drafts:new Map([['a',{item:node}]]),filters:{},context:{revision:1},canvasItem:'a'};const root={querySelector:s=>s==='[data-r-agent-status]'||s==='[data-r-research-status]'?status:null,addEventListener:(type,fn)=>{if(type==='submit')submit=fn;}};
ui.attach(v,{root:()=>root,active:()=>true,model:()=>({nodes:[node],relations:[]}),draw(){},markResearch:ids=>marks.push([...ids]),agent:()=>{agentCalls++;return new Promise(r=>release=r);},agentInfo:async()=>{polls++;return {recent:[{actionId:'act-1',status:polls===1?'running':'completed',activity:polls===1?'tools':'completed'}]};}});
v.selected='a';const event={target:{matches:s=>s.includes('[data-r-agent-form]')},preventDefault(){}};
ui.state(v).dialog={type:'agent',id:'a',title:'Alpha',template:'explain'};ui.bind(v,root,{});const first=submit(event);
assert.equal(ui.state(v).dialog,null,'Dialog closes before acknowledgement');assert.match(status.textContent,/Подготовка/);assert(marks.at(-1).includes('a'),'Node marked immediately');
ui.state(v).dialog={type:'agent',id:'a',title:'Alpha',template:'explain'};await submit(event);assert.equal(agentCalls,1,'Active request cannot be duplicated');
release({status:'accepted'});await first;await new Promise(r=>setImmediate(r));assert.match(status.textContent,/Использует инструменты/);assert.equal(ui.state(v).agent.status,'running');await timers.shift()();assert.equal(ui.state(v).agent.status,'completed');assert.equal(marks.at(-1).length,0);assert.match(status.textContent,/Завершено/);
ui.state(v).dialog={type:'agent',id:'a',title:'Alpha',template:'explain'};const second=submit(event);release({status:'failed',error:{message:'Codex unavailable'}});await second;assert.equal(ui.state(v).agent.status,'failed');assert.match(status.textContent,/Не удалось завершить анализ/);assert(!status.textContent.includes('Codex unavailable'));assert(!status.textContent.includes('[object Object]'));assert.equal(marks.at(-1).length,0);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        run=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)

    def test_agent_poll_recovers_missing_receipt_and_ignores_previous_action(self):
        script=r'''
(async()=>{
const fs=require('fs'),vm=require('vm'),assert=require('assert');let submit,polls=0,flushed=0,release;const timers=[];
const status={hidden:true,textContent:'',dataset:{}},ctx={window:{crypto:{randomUUID:()=> 'act-1'},KnowledgeUI:{flushUpdates(){flushed++;}}},console,setTimeout:fn=>timers.push(fn),FormData:class{get(k){return k==='template'?'explain':'Goal';}},document:{addEventListener(){}}};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);const ui=ctx.window.KnowledgeResearch;
const v={project:'p',selected:'',drafts:new Map(),filters:{},context:{revision:1}},root={querySelector:()=>status,addEventListener:(name,fn)=>{if(name==='submit')submit=fn;}};
const host={root:()=>root,active:()=>true,model:()=>({nodes:[],relations:[]}),draw(){},agent:async()=>({status:'accepted'}),agentInfo:async()=>{polls++;return polls===1?{recent:[]}:new Promise(resolve=>release=resolve);}};ui.attach(v,host);ui.bind(v,root,{});ui.state(v).dialog={type:'agent',id:'a',title:'Alpha'};
await submit({target:{matches:s=>s.includes('[data-r-agent-form]')},preventDefault(){}});await new Promise(r=>setImmediate(r));assert.equal(timers.length,1,'Missing receipt must not leave a permanently running status');
const pending=timers.shift()();ui.state(v).agent={id:'b',actionId:'new-action',status:'running'};release({recent:[{actionId:'act-1',status:'completed'}]});await pending;assert.equal(ui.state(v).agent.actionId,'new-action');assert.equal(ui.state(v).agent.status,'running');assert.equal(flushed,0,'Previous action cannot publish the new action result');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        run=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(run.returncode,0,run.stderr)

    def test_agent_payload_uses_architecture_detail_default(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');let submitted;
const context={window:{crypto:{randomUUID:()=> 'a1'}},console,FormData:class{get(k){return {template:'explain',detailLevel:'detailed',prompt:'Goal',providerId:'research-provider'}[k]}},document:{addEventListener(){}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);const ui=context.window.KnowledgeResearch;
const n={id:'a',kind:'entity',type:'class',title:'Alpha'},v={selected:'a',drafts:new Map([['a',{item:n}]]),filters:{},context:{revision:1},architectureSettings:{descriptionDetail:'detailed'}};
let handler;const root={querySelector:()=>null,addEventListener:(type,fn)=>{if(type==='submit')handler=fn}};
ui.attach(v,{root:()=>root,active:()=>true,model:()=>({nodes:[n],relations:[]}),draw(){},markResearch(){},agent:async payload=>{submitted=payload;return {status:'failed',message:'stop'}},agentInfo:async()=>({recent:[]})});
ui.state(v).dialog={type:'agent',id:'a',title:'Alpha',template:'explain'};const event={target:{matches:s=>s.includes('[data-r-agent-form]')},preventDefault(){}};
ui.bind(v,root,{});ui.state(v).dialog={type:'agent',id:'a',title:'Alpha',template:'explain'};
(async()=>{await handler(event);assert.equal(submitted.detailLevel,'detailed');assert.equal(submitted.template,'explain');assert.equal(submitted.operation,'architecture-analyze');assert.equal(submitted.providerId,'research-provider');assert(!('task' in submitted));assert(!('threadId' in submitted));})().catch(e=>{console.error(e);process.exitCode=1;});
"""
        result=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)


    def test_navigator_tree_menu_has_tree_actions_without_graph_collapse(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');let appended;
const context={window:{},console,document:{createElement:()=>({className:'',dataset:{},style:{},setAttribute(){},querySelectorAll:()=>[],querySelector:()=>({focus(){}}),innerHTML:'',})}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);const ui=context.window.KnowledgeResearch;
const node={id:'directory:src',title:'src',type:'directory'};const root={querySelectorAll:()=>[],append:n=>{appended=n},getBoundingClientRect:()=>({left:0,top:0,width:600,height:400})};const v={selected:'',drafts:new Map(),filters:{},context:{revision:1},__researchHost:{root:()=>root,setNodeActionsHidden(){},model:()=>({nodes:[node],relations:[]})}};
ui.attach(v,v.__researchHost);ui.state(v).capabilities.set(node.id,{operations:[]});ui.menu(v,node,10,10,{tree:true,folder:'src'});
assert.match(appended.innerHTML,/tree-expand-branch/);assert.match(appended.innerHTML,/tree-collapse-all/);assert.match(appended.innerHTML,/directory-map/);assert.doesNotMatch(appended.innerHTML,/data-r-action="collapse"/);assert.doesNotMatch(appended.innerHTML,/tree-collapse-graph/);
"""
        result=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_tree_menu_dispatches_project_and_component_actions_without_project_capabilities(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
let menuNode=null,handlers={},capabilityRequests=0;
function element(){return {className:'',dataset:{},style:{},innerHTML:'',offsetWidth:100,setAttribute(){},querySelectorAll:()=>[],querySelector:()=>({focus(){}}),querySelectorAll:()=>[],focus(){},remove(){menuNode=null;}};}
const context={window:{},console,document:{addEventListener(){},createElement:()=>{const n=element();menuNode=n;return n;}}};
vm.createContext(context);
for(const file of ['subsystems.js','knowledge-research.js'])vm.runInContext(fs.readFileSync(process.argv[1]+'/'+file,'utf8'),context);
const ui=context.window.KnowledgeResearch,hub=context.window.HubSubsystems;
const project={id:'project:fixture',type:'project',title:'Fixture'};
const component={id:'component:one',type:'component',kind:'entity',title:'Existing'};
const tree={className:'r-tree'},projectEntry={dataset:{rOpen:''},closest:s=>s==='.r-tree'?tree:s.includes('[data-r-open]')?projectEntry:null,getBoundingClientRect:()=>({left:10,top:20})};
const componentEntry={dataset:{kSelect:component.id},closest:s=>s==='.r-tree'?tree:s.includes('[data-k-select]')?componentEntry:null,getBoundingClientRect:()=>({left:10,top:20})};
const root={addEventListener:(name,fn)=>{(handlers[name]||=[]).push(fn);},append:n=>{menuNode=n;},querySelector:()=>null,getBoundingClientRect:()=>({left:0,top:0,width:800,height:600})};
const v={project:'fixture',selected:'',drafts:new Map(),filters:{},context:{revision:1,policy:{components:[component]}},mode:'architecture',catalogTreeItems:[component]};
const host={root:()=>root,active:()=>true,model:()=>({nodes:[component],relations:[]}),setNodeActionsHidden(){},draw(){},request:async op=>{if(op==='research-capabilities')capabilityRequests++;return {operations:[]};}};
v.__researchHost=host;ui.state(v).capabilities.set(component.id,{operations:[]});ui.bind(v,root,{});
function event(target,key){return {target,key,shiftKey:key==='F10',clientX:40,clientY:50,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;}};}
const projectEvent=event(projectEntry);handlers.contextmenu[0](projectEvent);assert(projectEvent.prevented&&projectEvent.stopped);assert(menuNode.innerHTML.includes('data-subsystem-action="overview"'));assert(menuNode.innerHTML.includes('data-subsystem-action="first-level"'));assert(menuNode.innerHTML.includes('data-subsystem-action="new"'));assert.equal(capabilityRequests,0,'Project menu must not request research capabilities');
const projectKeyboard=event(projectEntry,'ContextMenu');handlers.keydown[0](projectKeyboard);assert(projectKeyboard.prevented&&projectKeyboard.stopped);assert(menuNode.innerHTML.includes('data-subsystem-action="overview"'));
const componentKeyboard=event(componentEntry,'F10');handlers.keydown[0](componentKeyboard);assert(componentKeyboard.prevented&&componentKeyboard.stopped);for(const action of ['edit','new','analyze','remove'])assert(menuNode.innerHTML.includes(`data-subsystem-action="${action}"`));assert.equal(capabilityRequests,0);
"""
        result=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_agent_journal_is_project_wide_and_visually_distinct(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx={window:{},console};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);const ui=ctx.window.KnowledgeResearch;
const v={drafts:new Map(),filters:{},architectureSettings:{agentSummaries:true}};const r=ui.state(v);
 r.jobs=[
  {id:'local',state:'done',object:{title:'Local type'},query:{operation:'symbols'},createdAt:'2026-10-07T00:00:00Z'},
  {id:'limit',state:'error',error:{code:'research_tool_result_limit',message:'API analysis did not complete.'},object:{title:'Limited analysis'},query:{operation:'outgoing'},createdAt:'2026-10-08T00:00:00Z'},
  {id:'network',state:'error',error:{code:'provider_tls',message:'raw TLS detail',resultText:'{"private":"failed JSON"}'},object:{title:'Network failure'},query:{operation:'outgoing'},createdAt:'2026-10-09T00:00:00Z'},
  {id:'unknown',state:'error',error:{code:'sensitive_internal_error',message:'raw English failure',resultText:'{"private":"failed model output"}'},object:{title:'Unknown failure'},query:{operation:'outgoing'},createdAt:'2026-10-10T00:00:00Z'}
 ];
r.dialog={type:'jobs',agents:{items:[{researchTitle:'Different object',researchTemplate:'explain',status:'running',createdAt:1,progressSummary:'Checking collaborators',threadId:'owned-thread'},
 {researchTitle:'Timed out',status:'outcome_unknown',createdAt:2,error:{code:'provider_timeout',message:'API analysis requires review.'}},
  {researchTitle:'Read limit',status:'failed',createdAt:3,error:{code:'loop_limit',message:'API analysis did not complete.'}},
  {researchTitle:'No model',status:'failed',createdAt:4,error:{code:'api_provider_unavailable',message:'Select an API provider'}},
  {researchTitle:'Sign in',status:'failed',createdAt:5,error:{code:'chatgpt_sign_in_required',message:'Sign in required'}},
  {researchTitle:'Network',status:'failed',createdAt:6,error:{code:'provider_timeout',message:'API analysis requires review.'}},
  {researchTitle:'Unknown',status:'failed',createdAt:7,error:{code:'sensitive_internal_error',message:'raw English agent error',resultText:'{"private":"agent output"}'}}],more:true,next:20},history:{offset:0}};
const html=ui.auxiliary(v);assert.match(html,/Different object/);assert.match(html,/r-job-agent/);assert.match(html,/r-job-analyzer/);assert.match(html,/Выполняется/);assert.match(html,/Checking collaborators/);assert.match(html,/agents-page/);assert.match(html,/Описать выбранный элемент/);assert.match(html,/Local type/);
assert.match(html,/Анализ не завершился: объём данных, возвращённых инструментами, превысил допустимый лимит/);assert.doesNotMatch(html,/\[object Object\]|API analysis did not complete/);
 assert.match(html,/Проблема соединения с сервисом модели/);assert.match(html,/Анализ достиг лимита чтений или шагов/);
 assert.match(html,/Не выбрана модель\.[\s\S]*href="#settings\/agents\/models">Выбрать модель/);
 assert.match(html,/Для анализа требуется доступ к модели\.[\s\S]*href="#settings\/agents\/models">Настроить подключение/);
  const networkStart=html.indexOf('<strong>Network</strong>');const networkCard=html.slice(networkStart,html.indexOf('</article>',networkStart));assert(!networkCard.includes('href="#settings/agents/models"'));
  assert.equal((html.match(/href="#settings\/agents\/models"/g)||[]).length,2);
 for(const raw of ['raw TLS detail','raw English failure','raw English agent error','failed JSON','failed model output','agent output','sensitive_internal_error','API analysis requires review'])assert(!html.includes(raw),raw);
 const vStatus={drafts:new Map(),filters:{},research:{statusOwner:'research',currentJob:{state:'failed',error:{code:'provider_tls',message:'raw status error'}},jobs:[]}};
 const status=ui.statusText(vStatus);assert(status.includes('Проблема соединения с сервисом модели'));assert(!status.includes('raw status error'));
 vStatus.research.currentJob={state:'running'};assert(!ui.statusText(vStatus).includes('Не удалось завершить анализ.'));
 vStatus.research.currentJob={state:'done'};assert(!ui.statusText(vStatus).includes('Не удалось завершить анализ.'));
 vStatus.research.statusOwner='agent';vStatus.research.agent={id:'x',title:'Status agent',status:'failed',error:{code:'sensitive_internal_error',message:'raw agent status'}};
 const agentStatus=ui.statusText(vStatus);assert(agentStatus.includes('Не удалось завершить анализ.'));assert(!agentStatus.includes('raw agent status'));
 vStatus.research.agent={id:'x',title:'Status agent',status:'running'};assert(!ui.statusText(vStatus).includes('Не удалось завершить анализ.'));
 vStatus.research.agent={id:'x',title:'Status agent',status:'completed'};assert(!ui.statusText(vStatus).includes('Не удалось завершить анализ.'));
"""
        result=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_map_projection_aggregates_without_mutating_research_facts(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');const ctx={window:{}};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);const ui=ctx.window.ArchitectureMap;
const v={selected:'map',filters:{},context:{revision:1},drafts:new Map(),research:{}};
const nodes=[{id:'iface',kind:'entity',type:'interface',title:'Contract'},{id:'a',kind:'entity',type:'class',title:'A'},{id:'b',kind:'entity',type:'class',title:'B'}],relations=[{id:'ea',from:'a',to:'iface',type:'implements'},{id:'eb',from:'b',to:'iface',type:'implements'}];
const base={nodes,relations,presentationGroups:[{id:'category',title:'Math',nodeIds:['a','b']}]};
const full=ui.model(v,base),projected=ui.project(v,full),group=projected.nodes.find(n=>n.mapGroup);
assert.equal(projected.nodes.length,2);assert.equal(projected.relations.length,1);assert.equal(projected.relations[0].count,2);assert.equal(projected.relations[0].from,group.id);assert.equal(group.memberCount,2);
assert.equal(base.nodes.length,3);assert.equal(base.relations.length,2);assert(!nodes.some(n=>n.component));
v.research.collapsedGroups.delete(group.id);const expanded=ui.project(v,full);assert.equal(expanded.nodes.length,4);assert.equal(expanded.relations.length,2);assert.equal(expanded.parents.get('a'),group.id);
v.research.collapsedGroups.add(group.id);assert.equal(ui.project(v,full).relations[0].count,2);
// A parent category owns direct symbols AND nested categories, with no loss.
base.presentationGroups=[{id:'root',title:'Root',nodeIds:['a']},{id:'child',title:'Child',parent:'root',nodeIds:['b']}];v.research.groupScope=null;
const hierarchy=ui.model(v,base),collapsed=ui.project(v,hierarchy);assert.equal(collapsed.nodes.length,2);assert.equal(collapsed.relations[0].count,2);
const root=collapsed.nodes.find(n=>n.mapGroup);v.research.collapsedGroups.delete(root.id);const oneLevel=ui.project(v,hierarchy);assert(oneLevel.nodes.some(n=>n.id==='a'));assert(!oneLevel.nodes.some(n=>n.id==='b'));assert(oneLevel.nodes.some(n=>n.id.endsWith(':child')));
"""
        result=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/architecture-map.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_project_subsystem_research_actions_open_shared_form_before_dispatch(self):
        script=r"""
(async()=>{
const fs=require('fs'),vm=require('vm'),assert=require('assert');let submit,formValues={},opening,dispatches=[];
const messages={'subsystems.projectOverview':'Project overview','subsystems.overview':'Describe project overview','subsystems.firstLevel':'Describe main subsystems','subsystems.create':'Add subsystem','research.projectScope':'The project overview and its main subsystems.','research.subsystemLimitLabel':'Structure detail','research.subsystemLimitHelp':'A maximum, not a required count.','research.projectDetail':'Description length','research.projectOverviewHelp':'Saved in Project overview; earlier versions remain in history.','research.projectSubsystemsHelp':'First-level subsystems appear in the navigator and map; existing ones are kept.'};
const i18n={t:key=>messages[key]||key,onChange(){}};
const root={addEventListener:(type,handler)=>{if(type==='submit')submit=handler;},querySelector:()=>null,querySelectorAll:()=>[]};
const ctx={console,HubI18n:i18n,document:{addEventListener(){}},FormData:class{get(name){return formValues[name]}},setTimeout:()=>0,window:{HubI18n:i18n,crypto:{randomUUID:()=> 'action-id'},lucide:{icons:{Sparkles:'Sparkles',Plus:'Plus'},createElement:name=>({outerHTML:`<svg data-icon="${name}"></svg>`})},HubResearchRequests:{providers:async()=>({default:'provider-saved',items:[{id:'provider-saved',name:'Saved provider',model:'saved-model'}]}),providerField:(info,chosen)=>`<select name="providerId"><option value="${chosen}" selected>Saved provider</option></select>`}}};
vm.createContext(ctx);for(const file of ['subsystems.js','knowledge-research.js'])vm.runInContext(fs.readFileSync(process.argv[1]+'/'+file,'utf8'),ctx);
const research=ctx.window.KnowledgeResearch,subsystems=ctx.window.HubSubsystems,component={id:'component:existing',type:'component',title:'Existing'},project={id:'fixture',type:'project',title:'Project overview'};
const v={project:'fixture',selected:'',mode:'architecture',context:{revision:9,policy:{components:[component]}},drafts:new Map(),filters:{},architectureSettings:{descriptionDetail:'standard'}};
assert(subsystems.projectInspector(v).includes('subsystems.intro'),'An empty project overview keeps the existing introduction');v.context.projectOverview={id:'project:fixture',title:'Project overview',description:'Summary paragraph\n\n<script>alert(1)</script>'};const overviewHtml=subsystems.projectInspector(v);assert(overviewHtml.includes('Summary paragraph'));assert(overviewHtml.includes('&lt;script&gt;alert(1)&lt;/script&gt;'));assert(!overviewHtml.includes('<script>'));assert(overviewHtml.includes('data-subsystem-action="overview"'));
v.__researchHost={root:()=>root,active:()=>true,draw(){},model:()=>({nodes:[],relations:[]}),facts:()=>({nodes:[],relations:[]}),agentInfo:async()=>({recent:[]}),markResearch(){},agent:async payload=>{dispatches.push(payload);return {status:'failed',error:{code:'api_host_failed'}};}};
research.bind(v,root,{});
const rootActions=subsystems.actions(v,project);assert.equal((rootActions.match(/data-icon="Sparkles"/g)||[]).length,2);assert(rootActions.includes('data-subsystem-action="overview"'));assert(rootActions.includes('data-subsystem-action="first-level"'));assert(rootActions.includes('data-subsystem-action="new"'));assert(rootActions.includes('data-icon="Plus"'));
function click(action){const button={dataset:{subsystemAction:action,subsystemId:''},closest:()=>null,focus(){}};return {type:'click',target:{closest:()=>button},preventDefault(){}};}
async function openRoot(action,template,label){const dispatchCount=dispatches.length;let requested;const host={draw(){},openResearch:options=>{requested=research.openAgentDialog(v,options);return requested;}};assert.equal(subsystems.handle(v,click(action),host),true);assert(requested);await requested;assert.equal(dispatches.length,dispatchCount,'Opening the shared form must not call the model');const html=research.auxiliary(v);assert(html.includes('data-r-agent-form'));assert(html.includes('name="providerId"'));assert(html.includes('name="template" value="'+template+'"'));assert(!html.includes('<select name="template"'),'Root goal is fixed');assert(html.includes(label));assert.equal(research.state(v).dialog.id,'project:fixture');assert.equal(research.state(v).dialog.selected.type,'project');
 formValues={providerId:'provider-saved',template,detailLevel:'detailed',subsystemLimit:'5',prompt:'Use the selected project context'};if(template==='decompose'){assert(html.includes('Structure detail'));assert(html.includes('A maximum, not a required count.'));assert(html.includes('First-level subsystems appear in the navigator and map; existing ones are kept.'));for(const limit of [5,8,10])assert(html.includes('value="'+limit+'"'));assert(!html.includes('name="detailLevel"'));}else{assert(html.includes('Description length'));assert(html.includes('Saved in Project overview; earlier versions remain in history.'));assert(html.includes('name="detailLevel"'));}await submit({target:{matches:selector=>selector.includes('[data-r-agent-form]')},preventDefault(){}});const sent=dispatches.at(-1);assert.equal(sent.id,'project:fixture');assert.equal(sent.template,template);assert.equal(sent.providerId,'provider-saved');assert.equal(sent.prompt,'Use the selected project context');if(template==='decompose'){assert.equal(sent.subsystemLimit,5);assert.equal(sent.detailLevel,undefined);}else assert.equal(sent.detailLevel,'detailed');}
await openRoot('overview','explain','Describe project overview');await openRoot('first-level','decompose','Describe main subsystems');assert.equal(dispatches.length,2);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_project_overview_result_opens_architecture_before_general_result_link(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');let delegated=0;
const ctx={console,window:{HubResearchRequests:{resultLink:()=>{delegated++;return '<a href="delegated">General result</a>';}}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);const ui=ctx.window.KnowledgeResearch,v={project:'sample',drafts:new Map(),filters:{}};
ui.state(v).dialog={type:'jobs',agents:{items:[{resultRef:'knowledge/entity/project:sample',researchTitle:'Overview',createdAt:0},{resultRef:'knowledge/entity/component:sample',researchTitle:'Component',createdAt:0},{status:'failed',researchObjectId:'project:sample',researchTemplate:'explain',researchTitle:'Failed overview',resultText:'PRIVATE FAILED JSON',createdAt:0}]},history:{},loading:false};
const html=ui.auxiliary(v);assert(html.includes('href="/?project=sample#architecture/"'));assert(html.includes('General result'));assert.equal(delegated,1,'Only valid non-root results use the shared result-link helper');assert(!html.includes('PRIVATE FAILED JSON'));assert(html.includes('Описать обзор проекта'));
"""
        result=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_chatgpt_provider_error_is_localized(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert'),ctx={};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
for(const locale of ['ru','en'])assert.equal(typeof ctx.HubLocaleCatalog['provider.chatgptError'][locale],'string');
"""
        result=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/locale-catalog.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_subsystem_actions_and_explicit_canvas_scopes(self):
        script=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');let appended;
const ctx={window:{},document:{createElement:()=>({dataset:{},style:{},setAttribute(){},querySelectorAll:()=>[],querySelector:()=>({focus(){}})})}};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);const ui=ctx.window.KnowledgeResearch;
const sub={id:'component:math',title:'Math',type:'component',kind:'entity'},type={id:'class:a',title:'A',type:'class',kind:'entity'},v={selected:sub.id,drafts:new Map(),filters:{},context:{revision:1}};
const root={querySelector:()=>null,append:n=>appended=n,getBoundingClientRect:()=>({left:0,top:0,width:800,height:700})};ui.attach(v,{root:()=>root,setNodeActionsHidden(){},model:()=>({nodes:[sub,type],relations:[],parents:new Map([[type.id,sub.id]])})});const r=ui.state(v);
r.capabilities.set(sub.id,{operations:[{id:'children',title:'Children',provider:'catalog'},{id:'own-code',title:'Own code',provider:'catalog'},{id:'incoming',title:'Incoming',provider:'catalog'},{id:'outgoing',title:'Outgoing',provider:'catalog'}]});r.capabilities.set(type.id,{operations:[]});
const subsystem=ui.actions(v,sub);assert.match(subsystem,/Структурировать всю подсистему/);for(const action of ['children','own-code','incoming','outgoing'])assert(subsystem.includes(action));assert.match(subsystem,/Свернуть содержимое группы/);
assert.doesNotMatch(ui.actions(v,type),/data-r-template="decompose"/);assert.match(ui.actions(v,{...sub,collapsed:true}),/Раскрыть содержимое группы/);
ui.canvasMenu(v,30,40);assert.match(appended.innerHTML,/structure-canvas/);assert.match(appended.innerHTML,/groups-collapse-all/);assert.equal(r.menu.scope,'canvas');
r.dialog={type:'agent',scopeKind:'canvas',template:'structure-map',model:{nodes:[type],relations:[]},title:'Canvas'};const dialog=ui.auxiliary(v);assert.match(dialog,/Вся текущая карта/);assert.match(dialog,/1 элементов/);assert.doesNotMatch(dialog,/value="decompose"/);
r.collapsedGroups=new Set([sub.id]);r.groupScope=sub.id;const snapshot=ui.snapshot(v);r.collapsedGroups.clear();ui.restore(v,snapshot);assert(r.collapsedGroups.has(sub.id));
"""
        result=subprocess.run([shutil.which('node'),'-e',script,str(ROOT/'tools/project-portal/web/knowledge-research.js')],capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
