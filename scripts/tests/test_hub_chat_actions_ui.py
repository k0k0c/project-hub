"""Historical receipts and dedicated research UI, without task/chat execution."""
from pathlib import Path
import shutil
import subprocess
import unittest

WEB = Path(__file__).resolve().parents[2] / "tools" / "project-portal" / "web"
HARNESS = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const web=process.argv[1];
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function browser(language=null) {
  const calls=[], handlers={}, dialogs=[], timers=[];let uuid=0,repaints=0;
  class Dialog {
    constructor(){this.listeners={};this.innerHTML='';this.open=false;this.removed=false;}
    addEventListener(type,fn){this.listeners[type]=fn;}
    showModal(){this.open=true;}
    close(){this.open=false;this.listeners.close?.();}
    remove(){this.removed=true;}
  }
  const ctx={URLSearchParams,Uint8Array,Date,Math,console,location:{search:'?project=p'},
    crypto:{randomUUID:()=>`research-${++uuid}`},window:null,
    document:{documentElement:{dataset:{hubLocale:language||'ru'}},querySelectorAll:()=>[],
      addEventListener:(type,fn)=>{handlers[type]||=[];handlers[type].push(fn);},
      createElement:()=>{const node=new Dialog();dialogs.push(node);return node;},body:{append(){}}},
    setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},
    FormData:class{constructor(form){this.form=form;}get(name){return this.form.values[name];}},
    addEventListener(){},dispatchEvent(){},CustomEvent:class{constructor(type){this.type=type;}},
    fetch:async(url,options)=>{calls.push({url,options});return ctx.respond(url,options)},
    respond:async(url)=>({ok:true,status:200,json:async()=>url.startsWith('/api/v1/agent-providers')?
      {default:'model-a',items:[{id:'model-a',name:'Example service',model:'example-model',configured:true}]}:{recent:[]}})};
  ctx.window=ctx;vm.createContext(ctx);
  if(language)for(const file of ['locale-catalog.js','i18n.js'])vm.runInContext(fs.readFileSync(web+'/'+file,'utf8'),ctx);
  vm.runInContext(fs.readFileSync(web+'/chat-actions.js','utf8'),ctx);
  const host={project:'p',route:()=>['overview'],render:options=>{assert.equal(options.preserveScroll,true);repaints++;}};
  ctx.ChatActionsUI.afterRender(host);
  return {ctx,api:ctx.ChatActionsUI,research:ctx.HubResearchRequests,calls,handlers,host,dialogs,timers,repaints:()=>repaints};
}
function form(values){return {values,matches:selector=>selector==='[data-research-form]'};}
const values={operation:'documentation-review',providerId:'model-a',prompt:'Review the public guide',detailLevel:'standard'};
"""


@unittest.skipUnless(shutil.which("node"), "Node is required")
class ChatActionsUiTests(unittest.TestCase):
    def run_ui(self, code):
        result = subprocess.run(["node", "-e", HARNESS + "\n(async()=>{\n" + code +
            "\n})().catch(error=>{console.error(error);process.exitCode=1});", str(WEB)],
            capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_task_detail_reads_once_and_refreshes_only_on_request(self):
        self.run_ui(r"""
const b=browser();b.api.afterRender(b.host);assert.equal(b.calls.length,0);
b.host.route=()=>['tasks','t'];b.api.afterRender(b.host);await tick();await tick();
assert.equal(b.calls.length,1);assert.equal(b.calls[0].url,'/api/chat-actions?project=p&task=t');
b.api.afterRender(b.host);await tick();assert.equal(b.calls.length,1);
await b.api.load('p','t',true);assert.equal(b.calls.length,2);
assert(b.calls.every(call=>!call.options?.method));assert.equal(b.timers.length,0);
assert.equal(b.api.launch,undefined);assert.equal(b.api.openDialog,undefined);
""")

    def test_read_only_history_preserves_result_links_and_escapes_errors(self):
        self.run_ui(r"""
const b=browser('en');b.ctx.respond=async()=>({ok:true,json:async()=>({recent:[
  {actionId:'native',stage:'s',status:'completed',threadId:'old',resumeAllowed:true,resultRef:'knowledge/view/map id'},
  {actionId:'api',stage:'other',status:'failed',error:{message:'Failure <script>'}}]})});
await b.api.load('p','t');const html=b.api.render({id:'t'},null,'p');
assert(html.includes('Request history'));assert(html.includes('#architecture/map%20id'));
assert(html.includes('Failure &lt;script&gt;'));assert(!/data-chat-action=["']/.test(html));assert(!html.includes('data-agent-dialog'));
const stage=b.api.render({id:'t'},{id:'s'},'p');assert(!stage.includes('Failure'));
assert(!/threadId|resume|new chat|native UI/i.test(html));
""")

    def test_transport_diagnostics_are_optional_safe_and_copyable(self):
        self.run_ui(r"""
const b=browser('en');let copied='';b.ctx.navigator={clipboard:{writeText:value=>{copied=value;}}};
b.ctx.respond=async()=>({ok:true,json:async()=>({recent:[{actionId:'a1',provider:'provider-a',model:'model-a',contextDigest:'digest',status:'failed',resultText:'PRIVATE PROMPT',diagnostics:[{requestId:'local',attempt:1,scheme:'https',host:'api.example',status:'failed',secret:'PRIVATE SECRET',rawErrorBody:'PRIVATE BODY'}]}]})});
await b.api.load('p','t');const html=b.api.render({id:'t'},null,'p');assert(html.includes('receipt-diagnostics'));assert(html.includes('api.example'));assert(!html.includes('PRIVATE SECRET'));assert(!html.includes('PRIVATE BODY'));assert(!html.includes('PRIVATE PROMPT'));
 b.host.route=()=>['tasks','t'];const target={closest:selector=>selector==='[data-chat-refresh]'?null:{dataset:{copyDiagnostics:'a1'}}};b.handlers.click[0]({target});await tick();const copiedBody=JSON.parse(copied);assert.equal(copiedBody.receipt.actionId,'a1');assert.equal(copiedBody.receipt.provider,'provider-a');assert.equal(copiedBody.receipt.model,'model-a');assert.equal(copiedBody.receipt.contextDigest,'digest');assert.equal(copiedBody.diagnostics[0].host,'api.example');assert(!copied.includes('PRIVATE SECRET'));assert(!copied.includes('rawErrorBody'));
let posted; b.ctx.respond=async(url,options)=>{if(options?.method==='POST'){posted=JSON.parse(options.body);return {ok:true,json:async()=>({actionId:posted.actionId,status:'completed',provider:'provider-a',model:'model-a',contextDigest:'digest',diagnostics:[{requestId:'local',category:'transport',httpStatus:200,upstreamRequestId:'up-1',secret:'PRIVATE SECOND SECRET'}]})};}if(url.startsWith('/api/v1/agent-providers'))return {ok:true,json:async()=>({default:'model-a',items:[{id:'model-a',name:'Service',model:'model-a',configured:true}]})};return {ok:true,json:async()=>({recent:[]})};};
await b.research.openDocumentation({project:'p',objectId:'guide',revision:1,title:'Guide'});await tick();const researchDialog=b.dialogs.at(-1);await researchDialog.listeners.submit({target:form(values),preventDefault(){}});await tick();assert(researchDialog.innerHTML.includes('receipt-diagnostics'));assert(researchDialog.innerHTML.includes('up-1'));assert(!researchDialog.innerHTML.includes('PRIVATE SECOND SECRET'));
""")

    def test_project_activity_is_information_and_deduplicates_sessions(self):
        self.run_ui(r"""
const b=browser('en');const html=b.api.projectControl({tasks:[
 {status:'active',agentSessions:{active:['a','a'],waiting:['a','b'],unknown:['a','c']}},
 {status:'planned',agentSessions:{active:['a'],waiting:['b'],unknown:['c']}},
 {status:'done',agentSessions:{active:['ignored']}}]},'p');
assert(html.startsWith('<span'));assert(!/<button|<a|tabindex|data-agent-dialog/.test(html));
assert(html.includes('1 chats working'));assert(html.includes('1 waiting'));assert(html.includes('1 unknown'));
assert.equal(b.calls.length,0);
""")

    def test_task_activity_and_estimates_have_no_execution_triggers_in_each_language(self):
        self.run_ui(r"""
const b=browser('ru'),g=b.ctx,source=fs.readFileSync(web+'/app.js','utf8');
g.escape=value=>String(value??'').replaceAll('<','&lt;').replaceAll('>','&gt;');g.uiIcon=()=>'';g.planStatus=()=>'<span>Active</span>';g.date=value=>value;
const code=source.slice(source.indexOf('function taskStatus('),source.indexOf('const taskLink'))+
 source.slice(source.indexOf('function estimate('),source.indexOf('function currentWorkSummary'));
vm.runInContext(code,g);
for(const language of ['ru','en']){
 g.HubI18n.apply(language);const task={id:'task',status:'active',agentActivity:{state:'active'},currentWorks:[{session:'a'}],estimate:{percentLow:20,percentHigh:40,hoursLow:1,hoursHigh:2,note:'Evidence <note>'}};
 for(const markup of [g.taskStatus(task),g.estimate(task),g.estimate(task,true)]){
  assert(!/<button|data-agent-dialog|data-agent-intent|tabindex/.test(markup));assert(!markup.includes('<note>'));
 }
}
""")

    def test_provider_choices_are_scoped_research_controls(self):
        self.run_ui(r"""
const b=browser('en');b.ctx.respond=async()=>({ok:true,json:async()=>({default:'model-a',items:[
 {id:'model-a',name:'Service <one>',model:'model <id>',capabilities:{hubResult:true},authentication:{method:'api_key'}},
 {id:'plan',name:'ChatGPT',model:'plan-model',capabilities:{hubResult:true},authentication:{method:'chatgpt_oauth',status:'connected',planUsageEnabled:true}},
 {id:'legacy',name:'Legacy service',model:'legacy-model',configured:true},
 {id:'missing',configured:false},{id:'unsupported',capabilities:{hubResult:false}},{id:'codex',configured:true}]})});
const info=await b.research.providers();assert.deepEqual(Array.from(info.items,item=>item.id),['model-a','plan','legacy']);
const markup=b.research.providerField(info);assert(markup.includes('Service &lt;one&gt;'));assert(markup.includes('model &lt;id&gt;'));
assert(markup.includes('ChatGPT'));assert(markup.includes('plan-model'));assert(markup.includes('value="plan"'));
assert(markup.includes('value="model-a" selected'));assert(!/thread|task|native|mode=/.test(markup));
const empty=b.research.providerField({items:[]});assert(empty.includes('#settings/agents'));
for(const payload of [{task:'t',actionId:'a'},{action:'new',actionId:'a',research:{operation:'review',objectId:'task'}},
 {action:'new',actionId:'a',research:{operation:'architecture-analyze',task:'t'}}]){
 await assert.rejects(b.research.post('p',payload));
}
assert.equal(b.calls.length,1);
""")

    def test_current_research_receipt_keeps_safe_tls_and_format_diagnostics(self):
        self.run_ui(r"""
const b=browser('en');b.ctx.respond=async(url,options)=>{
 if(options?.method==='POST')return {ok:true,json:async()=>({actionId:JSON.parse(options.body).actionId,status:'outcome_unknown',diagnostics:[
  {category:'tls',phase:'unknown',tlsReason:'unexpected_eof',timeoutMs:20000,outcomeUnknown:true,secret:'PRIVATE TLS'},
  {category:'parse',parseReason:'sse_no_terminal',responseMediaType:'missing',responseContentEncoding:'missing',responseBodyKind:'event-stream-like',responseBytes:100,rawErrorBody:'PRIVATE BODY'}]})};
 if(url.startsWith('/api/v1/agent-providers'))return {ok:true,json:async()=>({default:'plan',items:[{id:'plan',name:'ChatGPT',model:'plan-model',capabilities:{hubResult:true}}]})};
 return {ok:true,json:async()=>({recent:[]})};
};
await b.research.openDocumentation({project:'p',objectId:'guide',revision:1,title:'Guide'});await tick();
const dialog=b.dialogs.at(-1);assert(dialog.innerHTML.includes('ChatGPT'));
await dialog.listeners.submit({target:form({...values,providerId:'plan'}),preventDefault(){}});await tick();
assert(dialog.innerHTML.includes('unexpected_eof'));assert(dialog.innerHTML.includes('20000'));
assert(dialog.innerHTML.includes('sse_no_terminal'));assert(dialog.innerHTML.includes('event-stream-like'));
assert(!dialog.innerHTML.includes('PRIVATE TLS'));assert(!dialog.innerHTML.includes('PRIVATE BODY'));
assert.equal(b.calls.filter(call=>call.options?.method==='POST').length,1);
""")

    def test_documentation_submit_is_one_scoped_request_and_has_cancellation(self):
        self.run_ui(r"""
const b=browser('en');await b.research.openDocumentation({project:'p',objectId:'guide',revision:3,title:'Guide'});await tick();
const dialog=b.dialogs.at(-1);assert(dialog.innerHTML.includes('Documentation research'));
assert(!/data-agent-where|data-agent-mode|threadId|task=/.test(dialog.innerHTML));
let release;b.ctx.respond=async(url,options)=>{if(options?.method==='POST')return new Promise(resolve=>{release=()=>resolve({ok:true,status:202,json:async()=>({actionId:JSON.parse(options.body).actionId,status:'accepted',transport:'api'})});});return {ok:true,json:async()=>({recent:[]})};};
const event={target:form(values),preventDefault(){}};const first=dialog.listeners.submit(event);const second=dialog.listeners.submit(event);await tick();
const posts=b.calls.filter(call=>call.options?.method==='POST');assert.equal(posts.length,1);
const payload=JSON.parse(posts[0].options.body);assert.deepEqual(Object.keys(payload).sort(),['action','actionId','research']);
assert.equal(payload.action,'new');assert.equal(payload.research.operation,'documentation-review');assert.equal(payload.research.providerId,'model-a');assert.equal(payload.research.revision,3);assert.equal(payload.research.objectId,'guide');
assert(!('task' in payload));assert(!('mode' in payload));assert(!('threadId' in payload));
release();await first;await second;assert(dialog.innerHTML.includes('data-research-cancel'));
b.ctx.respond=async(url,options)=>({ok:true,json:async()=>({actionId:JSON.parse(options.body).actionId,status:'interrupted',transport:'api'})});
await dialog.listeners.click({target:{closest:s=>s==='[data-research-cancel]'?{}:null}});
const cancelled=JSON.parse(b.calls.at(-1).options.body);assert.deepEqual(cancelled,{action:'cancel',actionId:payload.actionId});
assert(dialog.innerHTML.includes('Interrupted'));
""")

    def test_unknown_outcome_and_draft_survive_background_updates_and_reopening(self):
        self.run_ui(r"""
const b=browser('en');await b.research.openDocumentation({project:'p',objectId:'guide',revision:1,title:'Guide'});await tick();
let dialog=b.dialogs.at(-1);dialog.listeners.input({target:{name:'prompt',value:'Unsaved <draft>'}});
b.api.afterRender(b.host);assert.equal(b.dialogs.at(-1),dialog);assert(dialog.open);
b.ctx.respond=async(url,options)=>{if(options?.method==='POST')throw Error('connection lost');return {ok:true,json:async()=>({recent:[]})};};
await dialog.listeners.submit({target:form({...values,prompt:'Unsaved <draft>'}),preventDefault(){}});
assert(dialog.innerHTML.includes('Outcome unknown'));assert(dialog.innerHTML.includes('Unsaved &lt;draft&gt;'));
await dialog.listeners.submit({target:form(values),preventDefault(){}});assert.equal(b.calls.filter(call=>call.options?.method==='POST').length,1);
dialog.close();b.ctx.respond=async(url)=>({ok:true,json:async()=>url.startsWith('/api/v1/agent-providers')?{default:'model-a',items:[{id:'model-a',configured:true,name:'Service',model:'model'}]}:{recent:[]}});
await b.research.openDocumentation({project:'p',objectId:'guide',revision:2,title:'Guide'});await tick();dialog=b.dialogs.at(-1);
assert(dialog.innerHTML.includes('Unsaved &lt;draft&gt;'));assert(dialog.innerHTML.includes('Outcome unknown'));
assert.equal(b.calls.filter(call=>call.options?.method==='POST').length,1);
""")


if __name__ == '__main__':
    unittest.main()
