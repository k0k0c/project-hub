"""DOM event contract checks for the task launch dialog."""
from pathlib import Path
import shutil
import subprocess
import unittest

WEB = Path(__file__).resolve().parents[2] / "tools" / "project-portal" / "web"

HARNESS = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
class Node {
  constructor(data={}) { this.dataset=data; this.fields={}; this.listeners={}; this.innerHTML=""; }
  addEventListener(t,f){(this.listeners[t]??=[]).push(f)}
  setAttribute(n,v){this[n]=v}
  contains(n){return false}
  focus(){}
  showModal(){this.open=true}
  close(){this.open=false;for(const f of this.listeners.close||[])f()}
  remove(){this.removed=true}
  querySelector(s) { if(s.includes('[name="mode"]')) return this.fields.mode; const m=s.match(/name="([^"]+)/); return m?this.fields[m[1]]:null; }
  closest(s) { if(s.includes('data-task-launch-history-'))return null; if(s.includes('data-task-launch-open')||s.includes('data-task-launch-close')||s.includes('data-task-launch-retry'))return null; if(s.includes('task-launch-form')) return this.dataset.taskLaunchForm?this:this.form; if(s.includes('data-task-launches')) return this.dataset.taskLaunchForm?this.form:this; return this; }
}
class Root extends Node {
  constructor(){super();this.container=null;this.historyContainer=null;this.dialog=null;this.body={append:n=>{this.dialog=n}};}
  createElement(tag){assert.equal(tag,"dialog");const n=new Node();n.content=new Node();n.querySelector=s=>s==='[data-task-launch-content]'?n.content:null;return n}
  addEventListener(t,f){(this.listeners[t]??=[]).push(f)}
  querySelector(s){if(s==='[data-task-launch-history-view]')return this.historyContainer;return s==='[data-task-launches]'?this.container:this.container&&this.container.querySelector(s)}
  fire(t,target){for(const f of this.listeners[t]||[])f({target,preventDefault(){},stopPropagation(){}})}
}
const tick=async()=>{for(let i=0;i<20;i++)await Promise.resolve()};
function dom(project='p',task='t',stage=null) {
  const root=new Node({project,task,stage}), form=new Node({taskLaunchForm:true}); form.form=root;
  root.form=form; root.fields={route:{value:JSON.stringify(['c1','b1'])},mode:{value:'create'},resume:{value:'r1'},prompt:{value:'Do work'}};
  Object.assign(form,root.fields);
  return {root,form};
}
function browser(responses, locale='ru') {
  const root=new Root(), calls=[],timers=new Map(); let n=0;
  const ctx={console,URL,URLSearchParams,location:{origin:'http://hub.test'},crypto:{randomUUID:()=> '01234567-89ab-4cde-8123-0123456789ab'},
    setTimeout:(f)=>{const id=++n;timers.set(id,f);return id},clearTimeout(id){timers.delete(id)},document:root,
    HubI18n:{locale,t:(x)=>x},fetch:async(url,opt={})=>{calls.push({url,opt});return responses(url,opt)}};
  ctx.window=ctx;vm.createContext(ctx);vm.runInContext(source,ctx,{filename:'task-launches.js'});return {ctx,root,calls,timers};
}
function mount(b,host) {
  b.ctx.TaskLaunchesUI.afterRender(host);
  const path=host.route();if(path[0]!=="tasks")return;
  const stage=b.root.container?.dataset.stage||path[2];
  b.ctx.TaskLaunchesUI.open({id:path[1],title:'Selected task'},stage?{id:stage,title:'Selected stage'}:null,host.project);
}
function response(body,ok=true){return {ok,status:ok?200:409,json:async()=>body}}
'''


@unittest.skipUnless(shutil.which("node"), "Node is required")
class TaskLaunchesUiTests(unittest.TestCase):
    def run_ui(self, code):
        result = subprocess.run(["node", "-e", HARNESS + "\n(async()=>{" + code + "})().catch(e=>{console.error(e);process.exitCode=1})", str(WEB / "task-launches.js")], capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_creator_application_and_workspace_default_keep_create_mode(self):
        self.run_ui(r'''
const b=browser(async()=>response({project:'p',task:'t',preferredRoute:{connection:'creator',bindingId:'right'},routes:[
  {connection:'other',bindingId:'other',application:'Other app',canCreate:true},
  {connection:'creator',bindingId:'wrong',application:'Creator app',workspace:'Other workspace',canCreate:true},
  {connection:'creator',bindingId:'right',application:'Creator app',workspace:'Original workspace',canCreate:true,canContinue:true}],launches:[],
  chats:[{nativeId:'existing',connection:'creator',bindingId:'right',task:'t',scope:'task',canContinue:true}]}));
mount(b,{project:'p',route:()=>['tasks','t']});await tick();const html=b.ctx.TaskLaunchesUI.render({id:'t'},null,'p');
assert(html.includes('value="creator" selected>Creator app'));assert(html.includes('selected>Original workspace'));
assert(html.includes('value="create" checked'));assert(!html.includes('name="resume"'),'chat picker only belongs to continue mode');
assert(!html.includes('type="submit" disabled'));
''')

    def test_single_application_selects_automatically_and_hides_unique_workspace(self):
        self.run_ui(r'''
const b=browser(async()=>response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',application:'App',workspace:'Private workspace',canCreate:true}],launches:[]}));
mount(b,{project:'p',route:()=>['tasks','t']});await tick();const html=b.ctx.TaskLaunchesUI.render({id:'t'},null,'p');
assert(html.includes('value="c1" selected>App'));assert(html.includes('type="hidden" name="route"'));
assert(!html.includes('Private workspace'));assert(!html.includes('<select name="route"'));assert(!html.includes('type="submit" disabled'));
''')

    def test_ambiguous_workspaces_require_choice_without_losing_creator_application(self):
        self.run_ui(r'''
let body;const b=browser(async(url,opt)=>{
 if(opt.method==='POST'){body=JSON.parse(opt.body);return response({requestId:body.request.requestId,status:'accepted',envelope:{connection:'c1',project:'p',bindingId:'b2',resultDestination:{stage:null},inputs:{task:{id:'t'}}}})}
 return response({project:'p',task:'t',preferredRoute:{connection:'c1'},routes:[{connection:'c1',bindingId:'b1',application:'App',workspace:'First',canCreate:true},{connection:'c1',bindingId:'b2',application:'App',workspace:'Second',canCreate:true}],launches:[]});
});
mount(b,{project:'p',route:()=>['tasks','t']});await tick();let html=b.ctx.TaskLaunchesUI.render({id:'t'},null,'p');
assert(html.includes('value="c1" selected>App'));assert(html.includes('<select name="route"'));assert(html.includes('type="submit" disabled'));
const d=dom();b.root.container=d.root;d.root.fields.route.value=JSON.stringify(['c1','b2']);b.root.fire('change',d.root);
b.root.fire('submit',d.form);await tick();assert.equal(body.request.bindingId,'b2');
''')

    def test_manual_application_choice_survives_polling_with_creator_default(self):
        self.run_ui(r'''
const b=browser(async()=>response({project:'p',task:'t',preferredRoute:{connection:'creator',bindingId:'b2'},routes:[
 {connection:'c1',bindingId:'b1',application:'Chosen app',canCreate:true},{connection:'creator',bindingId:'b2',application:'Creator app',canCreate:true}],launches:[{status:'awaiting_ack'}]}));
mount(b,{project:'p',route:()=>['tasks','t']});await tick();const d=dom();b.root.container=d.root;
d.root.fields.application={value:'c1'};b.root.fire('change',d.root);
assert(b.ctx.TaskLaunchesUI.render({id:'t'},null,'p').includes('value="c1" selected>Chosen app'));
const [timer,run]=b.timers.entries().next().value;b.timers.delete(timer);run();await tick();
assert(b.ctx.TaskLaunchesUI.render({id:'t'},null,'p').includes('value="c1" selected>Chosen app'));
''')

    def test_launch_history_loads_only_in_task_chats_and_stops_after_exit(self):
        self.run_ui(r'''
const b=browser(async()=>response({project:'p',task:'t',routes:[],launches:[{status:'accepted',stage:'step',result:{summary:'Saved report'}}]}));
const task={id:'t',stages:[{id:'step',title:'Selected stage'}]},host={project:'p',route:()=>['tasks','t'],state:{tasks:[task]}};
b.ctx.TaskLaunchesUI.afterRender(host);await tick();assert.equal(b.calls.length,0);
b.root.historyContainer=new Node({project:'p',task:'t'});b.ctx.TaskLaunchesUI.afterRender(host);await tick();
assert.equal(b.calls.length,1);assert(b.root.historyContainer.innerHTML.includes('Saved report'));assert(b.root.historyContainer.innerHTML.includes('Selected stage'));
assert(b.timers.size>0);b.root.historyContainer=null;b.ctx.TaskLaunchesUI.afterRender(host);assert.equal(b.timers.size,0);
''')

    def test_modal_has_no_history_and_closing_it_keeps_visible_chat_history_polling(self):
        self.run_ui(r'''
const b=browser(async()=>response({project:'p',task:'t',routes:[],launches:[{status:'accepted',result:{summary:'Historical report'}}]}));
const task={id:'t'},host={project:'p',route:()=>['tasks','t'],state:{tasks:[task]}};
b.root.historyContainer=new Node({project:'p',task:'t'});b.ctx.TaskLaunchesUI.afterRender(host);await tick();
b.ctx.TaskLaunchesUI.open(task);await tick();const html=b.ctx.TaskLaunchesUI.render(task,null,'p');
assert(!html.includes('Historical report'));assert(!html.includes('task-launch-history'));assert(!html.includes('Запусков пока нет'));
b.root.dialog.close();assert(b.timers.size>0,'visible history must keep receiving launch updates');
''')

    def test_status_buttons_open_correct_scope_on_every_task_surface_without_dispatch(self):
        self.run_ui(r'''
for(const path of [['overview'],['tasks'],['tasks','t','selected-stage']]) {
  const b=browser(async()=>response({project:'p',task:'t',routes:[],launches:[]}));
  const task={id:'t',title:'Task title',stages:[{id:'step',title:'Stage title',status:'active'}]};
  const host={project:'p',route:()=>path,state:{tasks:[task]},render(){throw Error('Opening must not rerender or navigate the page')}};
  b.ctx.TaskLaunchesUI.afterRender(host);await tick();
  assert.equal(b.calls.length,0,'page rendering must not load launch details');assert.equal(b.root.dialog,null);
  for(const stageId of ['', 'step']) {
    const button={dataset:{taskLaunchOpen:'t',stageId},closest:s=>s==='[data-task-launch-open]'?button:null};
    b.root.fire('click',button);await tick();
    assert(b.root.dialog.open);assert.equal(b.root.dialog['aria-label'],stageId?'Запустить этап':'Запустить задачу');
    assert(b.root.dialog.content.innerHTML.includes(stageId?'Stage title':'Task title'));
    assert(b.root.dialog.content.innerHTML.includes(`data-stage="${stageId}"`));
    assert(!b.calls.some(x=>x.opt.method==='POST'),'opening must not execute a launch');
    b.root.dialog.close();
  }
}
''')

    def test_task_launch_reads_current_plan_and_excludes_completed_and_cancelled_stages(self):
        self.run_ui(r'''
for(const mode of ['create','continue']) {
  let body;const b=browser(async(url,opt)=>{
    if(opt.method==='POST'){body=JSON.parse(opt.body);return response({requestId:body.request.requestId,status:'awaiting_ack',envelope:{connection:'c1',project:'p',bindingId:'b1',resultDestination:{stage:null},inputs:{task:{id:'t'}}}})}
    return response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',canCreate:true,canContinue:true}],launches:[],chats:[{nativeId:'task-chat',connection:'c1',bindingId:'b1',task:'t',scope:'task',canContinue:true}]});
  });
  const host={project:'p',route:()=>['overview']};b.ctx.TaskLaunchesUI.afterRender(host);
  b.ctx.TaskLaunchesUI.open({id:'t',stages:[{id:'finished',status:'done'},{id:'cancelled',status:'cancelled'},{id:'next',status:'planned'},{id:'working',status:'active'}]});await tick();
  const d=dom();b.root.container=d.root;d.form.mode.value=mode;d.form.resume.value='task-chat';b.root.fire('submit',d.form);await tick();
  assert(body);assert(!('stage' in body.request));assert(body.request.prompt.includes('hub_plan'));assert(body.request.prompt.includes('done и cancelled'));assert(body.request.prompt.endsWith('Do work'));
  assert.equal(body.request.nativeId,mode==='continue'?'task-chat':undefined);
}
''')

    def test_terminal_task_launch_is_disabled_and_history_is_separate(self):
        self.run_ui(r'''
const b=browser(async()=>response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',canCreate:true}],launches:[]}));
const d=dom();b.root.container=d.root;mount(b,{project:'p',route:()=>['tasks','t']});await tick();b.root.fire('change',d.root);
for(const stages of [[{status:'done'}],[{status:'done'},{status:'cancelled'}]]) {
  const html=b.ctx.TaskLaunchesUI.render({id:'t',stages},null,'p');assert(html.includes('type="submit" disabled'));assert(!html.includes('task-launch-history'));assert(b.ctx.TaskLaunchesUI.renderHistory({id:'t'},'p').includes('task-launch-history'));
}
assert(!b.ctx.TaskLaunchesUI.render({id:'t',stages:[{status:'active'}]},null,'p').includes('type="submit" disabled'));
''')

    def test_task_instruction_reserves_room_for_scope_within_api_limit(self):
        self.run_ui(r'''
let body;const b=browser(async(url,opt)=>{
  if(opt.method==='POST'){body=JSON.parse(opt.body);return response({requestId:body.request.requestId,status:'awaiting_ack',envelope:{connection:'c1',project:'p',bindingId:'b1',resultDestination:{stage:null},inputs:{task:{id:'t'}}}})}
  return response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',canCreate:true}],launches:[]});
});
mount(b,{project:'p',route:()=>['tasks','t']});await tick();const d=dom();b.root.container=d.root;
const html=b.ctx.TaskLaunchesUI.render({id:'t'},null,'p'),limit=Number(html.match(/maxlength="(\d+)"/)[1]);assert(limit>0&&limit<6000);
d.form.prompt.value='x'.repeat(limit);b.root.fire('submit',d.form);await tick();assert.equal(body.request.prompt.length,6000);
''')

    def test_close_stops_polling_and_preserves_draft_on_reopen(self):
        self.run_ui(r'''
const b=browser(async()=>response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',canCreate:true}],launches:[{status:'awaiting_ack'}]}));
const host={project:'p',route:()=>['overview']};b.ctx.TaskLaunchesUI.afterRender(host);b.ctx.TaskLaunchesUI.open({id:'t'});await tick();
const d=dom();b.root.container=d.root;d.form.prompt.value='Saved instruction';b.root.fire('input',d.root);assert(b.timers.size>0);
b.root.dialog.close();assert.equal(b.timers.size,0);b.root.container=null;b.ctx.TaskLaunchesUI.open({id:'t'});await tick();
assert(b.root.dialog.content.innerHTML.includes('Saved instruction'));
''')

    def test_submit_dispatches_typed_create_payload_from_real_form_event(self):
        self.run_ui(r'''
let posts=[];const b=browser(async(url,opt)=>{if(opt.method==='POST'){posts.push(JSON.parse(opt.body));return response({requestId:'0123456789ab4cde81230123456789ab',status:'awaiting_ack',envelope:{connection:'c1',project:'p',bindingId:'b1',resultDestination:{stage:'step'},inputs:{task:{id:'t'}}}})}return response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',application:'App',canCreate:true,canContinue:false}],launches:[]})});
const host={project:'p',route:()=>['tasks','t','step'],render(){},renderEvidence(){return ''}};mount(b,host);await tick();const d=dom('p','t','step');b.root.container=d.root;b.root.fire('change',d.root);b.root.fire('submit',d.form);await tick();assert.equal(posts.length,1);assert.deepEqual(posts[0].request,{requestId:'0123456789ab4cde81230123456789ab',bindingId:'b1',operation:'task-execute',task:'t',stage:'step',prompt:'Do work'});assert.equal(posts[0].id,'c1');
''')

    def test_continue_requires_same_route_binding_and_stage_and_sends_native_id(self):
        self.run_ui(r'''
let body;const b=browser(async(url,opt)=>{if(opt.method==='POST'){body=JSON.parse(opt.body);return response({requestId:body.request.requestId,status:'awaiting_ack',envelope:{connection:'c1',project:'p',bindingId:'b1',resultDestination:{stage:'step'},inputs:{task:{id:'t'}}}})}return response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',canCreate:false,canContinue:true}],launches:[{requestId:'r1',nativeId:'native-1',connection:'c1',bindingId:'b1',stage:'step',canContinue:true,status:'completed'},{requestId:'same-chat-again',nativeId:'native-1',connection:'c1',bindingId:'b1',stage:'step',canContinue:true,status:'completed'}]})});
const host={project:'p',route:()=>['tasks','t','step'],render(){}};mount(b,host);await tick();const d=dom('p','t','step');d.root.fields.mode.value='continue';d.root.fields.resume.value='native-1';b.root.container=d.root;b.root.fire('change',d.root);const html=b.ctx.TaskLaunchesUI.render({id:'t'},{id:'step'},'p');assert(!html.includes('value="same-chat-again"'),'one chat must have one continuation option');b.root.fire('submit',d.form);await tick();assert.equal(body.request.nativeId,'native-1');assert.equal(body.request.bindingId,'b1');assert.equal(body.request.stage,'step');
''')

    def test_related_chat_candidates_support_continue_without_a_historical_launch(self):
        self.run_ui(r'''
let body;const b=browser(async(url,opt)=>{if(opt.method==='POST'){body=JSON.parse(opt.body);return response({requestId:body.request.requestId,status:'awaiting_ack',envelope:{connection:'c1',project:'p',bindingId:'b1',resultDestination:{stage:'step'},inputs:{task:{id:'t'}}}})}return response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',canCreate:false,canContinue:true}],launches:[],chats:[{id:'stable-1',nativeId:'native-related',connection:'c1',bindingId:'b1',title:'Related work chat',task:'t',stage:null,scope:'task',canContinue:true,origin:'related'}]})});
const host={project:'p',route:()=>['tasks','t','step'],render(){}};mount(b,host);await tick();const d=dom('p','t','step');d.root.fields.mode.value='continue';d.root.fields.resume.value='native-related';b.root.container=d.root;b.root.fire('change',d.root);const html=b.ctx.TaskLaunchesUI.render({id:'t'},{id:'step'},'p');assert(html.includes('Related work chat'));assert(html.includes('value="native-related"'));b.root.fire('submit',d.form);await tick();assert.equal(body.request.nativeId,'native-related');assert.equal(body.request.stage,'step');
''')

    def test_chat_candidates_filter_scope_route_stage_and_dedupe_native_id(self):
        self.run_ui(r'''
let body;const b=browser(async(url,opt)=>{if(opt.method==='POST'){body=JSON.parse(opt.body);return response({requestId:body.request.requestId,status:'awaiting_ack',envelope:{connection:'c1',project:'p',bindingId:'b1',resultDestination:{stage:'step'},inputs:{task:{id:'t'}}}})}return response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',canCreate:false,canContinue:true},{connection:'other',bindingId:'b2',canCreate:false,canContinue:true}],launches:[],chats:[
{id:'task',nativeId:'same',connection:'c1',bindingId:'b1',title:'Task chat',task:'t',stage:null,scope:'task',canContinue:true,origin:'related'},
{id:'stage',nativeId:'same',connection:'c1',bindingId:'b1',title:'Duplicate stage chat',task:'t',stage:'step',scope:'stage',canContinue:true,origin:'launch'},
{id:'other-stage',nativeId:'wrong-stage',connection:'c1',bindingId:'b1',title:'Wrong stage',task:'t',stage:'other',scope:'stage',canContinue:true,origin:'related'},
{id:'wrong-route',nativeId:'wrong-route',connection:'other',bindingId:'b2',title:'Other route',task:'t',stage:null,scope:'task',canContinue:true,origin:'related'}]})});
const host={project:'p',route:()=>['tasks','t','step'],render(){}};mount(b,host);await tick();const d=dom('p','t','step');d.root.fields.mode.value='continue';d.root.fields.resume.value='same';b.root.container=d.root;b.root.fire('change',d.root);const html=b.ctx.TaskLaunchesUI.render({id:'t'},{id:'step'},'p');assert(html.includes('Task chat'));assert(!html.includes('Duplicate stage chat'));assert(!html.includes('Wrong stage'));assert(!html.includes('Other route'));b.root.fire('submit',d.form);await tick();assert.equal(body.request.nativeId,'same');
''')

    def test_source_chat_title_survives_an_earlier_launch_for_the_same_native_chat(self):
        self.run_ui(r'''
const b=browser(async()=>response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',canCreate:true,canContinue:true}],launches:[],chats:[
{id:'launch',nativeId:'source-native',connection:'c1',bindingId:'b1',task:'t',stage:'step',scope:'stage',canContinue:true,origin:'launch'},
{id:'source',nativeId:'source-native',connection:'c1',bindingId:'b1',title:'Task creation chat',task:'t',stage:null,scope:'task',canContinue:true,origin:'related'}]}));
const d=dom('p','t','step');b.root.container=d.root;const host={project:'p',route:()=>['tasks','t'],render(){}};
mount(b,host);await tick();b.root.fire('change',d.root);
d.root.fields.mode.value='continue';b.root.fire('change',d.root);
const html=b.ctx.TaskLaunchesUI.render({id:'t'},{id:'step'},'p');
assert(html.includes('>Task creation chat</option>'));assert(!html.includes('>source-native</option>'));
''')

    def test_displayed_default_stage_loads_routes_and_submits_its_own_context(self):
        self.run_ui(r'''
for(const path of [['tasks','t'],['tasks','t','removed-stage']]) {
  for(const mode of ['create','continue']) {
    const posts=[], stage='default-stage';
    const b=browser(async(url,opt)=>{
      if(opt.method==='POST') {
        const q=JSON.parse(opt.body);posts.push(q);
        return response({requestId:q.request.requestId,status:'awaiting_ack',envelope:{connection:'c1',project:'p',bindingId:'b1',resultDestination:{stage},inputs:{task:{id:'t'}}}});
      }
      return response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',application:'Desktop',workspace:'Workspace',canCreate:true,canContinue:true}],launches:[{requestId:'r1',nativeId:'default-chat',connection:'c1',bindingId:'b1',stage,canContinue:true,status:'completed'}]});
    });
    const d=dom('p','t',stage);b.root.container=d.root;
    const host={project:'p',route:()=>path,render(){}};
    mount(b,host);await tick();
    let html=b.ctx.TaskLaunchesUI.render({id:'t'},{id:stage},'p');
    assert(html.includes('value="c1" selected>Desktop'),'routes must load for the displayed stage');
    d.root.fields.prompt.value='Instruction for the displayed stage';
    d.root.fields.mode.value=mode;if(mode==='continue')d.root.fields.resume.value='default-chat';b.root.fire('input',d.root);b.root.fire('change',d.root);
    html=b.ctx.TaskLaunchesUI.render({id:'t'},{id:stage},'p');
    assert(!html.includes('type="submit" disabled'));
    if(mode==='continue')assert(html.includes('value="continue" checked'));
    b.root.fire('submit',d.form);await tick();
    assert.equal(posts.length,1);assert.equal(posts[0].request.stage,stage);
    assert.equal(posts[0].request.prompt,'Instruction for the displayed stage');
    assert.equal(posts[0].request.nativeId,mode==='continue'?'default-chat':undefined);
  }
}
''')

    def test_default_stage_mount_discards_the_earlier_task_level_load(self):
        self.run_ui(r'''
let resolveOld,gets=0;
const b=browser(async()=>{
  if(++gets===1)return new Promise(resolve=>{resolveOld=resolve});
  return response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',application:'Current desktop',canCreate:true}],launches:[]});
});
const host={project:'p',route:()=>['tasks','t'],render(){}};
mount(b,host);await tick();
const d=dom('p','t','default-stage');b.root.container=d.root;
mount(b,host);await tick();assert.equal(gets,2);
resolveOld(response({project:'p',task:'t',routes:[],launches:[]}));await tick();
const html=b.ctx.TaskLaunchesUI.render({id:'t'},{id:'default-stage'},'p');
assert(html.includes('Current desktop'));assert(!html.includes('Нет доступных приложений'));
''')

    def test_wrong_ack_has_one_manual_exact_retry_and_no_automatic_mutation(self):
        self.run_ui(r'''
let posts=0,bodies=[];const b=browser(async(url,opt)=>{if(opt.method==='POST'){posts++;bodies.push(opt.body);const q=JSON.parse(opt.body);return response({requestId:q.request.requestId,status:'awaiting_ack',envelope:{connection:posts===1?'WRONG':'c1',project:'p',bindingId:'b1',resultDestination:{stage:null},inputs:{task:{id:'t'}}}})}return response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',canCreate:true}],launches:[]})});
const host={project:'p',route:()=>['tasks','t'],render(){}};mount(b,host);await tick();const d=dom();b.root.container=d.root;b.root.fire('submit',d.form);await tick();assert.equal(posts,1);d.form.prompt.value='A different instruction';b.root.fire('submit',d.form);await tick();assert.equal(posts,1,'uncertain request must block a new mutation');assert(b.ctx.TaskLaunchesUI.render({id:'t'},null,'p').includes('data-task-launch-retry'));
const retry={closest:sel=>sel.includes('data-task-launch-retry')?retry:sel.includes('data-task-launches')?d.root:null};b.root.fire('click',retry);await tick();assert.equal(posts,2);assert.equal(bodies[0],bodies[1]);

''')

    def test_known_predispatch_rejection_allows_fixing_the_form_without_exact_retry(self):
        self.run_ui(r'''
let posts=0;const b=browser(async(url,opt)=>{if(opt.method==='POST'){posts++;return response({error:'project_launcher_unavailable',message:'Configure application control first'},false)}return response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',canCreate:true}],launches:[]})});
const host={project:'p',route:()=>['tasks','t'],render(){}};mount(b,host);await tick();const d=dom();b.root.container=d.root;b.root.fire('submit',d.form);await tick();let html=b.ctx.TaskLaunchesUI.render({id:'t'},null,'p');assert(html.includes('Configure application control first'));assert(!html.includes('data-task-launch-retry'));b.root.fire('submit',d.form);await tick();assert.equal(posts,2,'a rejected precondition is not an uncertain native mutation');
''')

    def test_stored_unknown_dispatch_blocks_new_mutations_but_keeps_polling_for_ack(self):
        self.run_ui(r'''
let posts=0;const b=browser(async(url,opt)=>{if(opt.method==='POST')posts++;return response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',canCreate:true}],launches:[{requestId:'unknown',connection:'c1',bindingId:'b1',status:'dispatch_unknown',stage:null}]})});const host={project:'p',route:()=>['tasks','t'],render(){}};mount(b,host);await tick();const d=dom();b.root.container=d.root;b.root.fire('change',d.root);const html=b.ctx.TaskLaunchesUI.render({id:'t'},null,'p');assert(html.includes('Результат отправки неизвестен'));assert(html.includes('type="submit" disabled'));b.root.fire('submit',d.form);await tick();assert.equal(posts,0);assert(b.timers.size>0,'a late correlated ACK can still resolve the unknown dispatch');
''')

    def test_polling_stops_on_route_exit_and_stale_load_cannot_replace_acceptance(self):
        self.run_ui(r'''
let pendingGets=[],gets=0;const b=browser((url,opt)=>{if(opt.method==='POST'){const q=JSON.parse(opt.body);return Promise.resolve(response({requestId:q.request.requestId,status:'accepted',envelope:{connection:'c1',project:'p',bindingId:'b1',resultDestination:{stage:null},inputs:{task:{id:'t'}}}}))}if(++gets===1)return Promise.resolve(response({project:'p',task:'t',routes:[{connection:'c1',bindingId:'b1',canCreate:true}],launches:[{requestId:'old',status:'awaiting_ack'}]}));return new Promise(r=>{pendingGets.push(r)})});
let current=['tasks','t'];const host={project:'p',route:()=>current,render(){}};mount(b,host);await tick();assert(b.timers.size>0,'awaiting_ack must poll');const [timer,run]=b.timers.entries().next().value;b.timers.delete(timer);run();await tick();assert.equal(gets,2);
const d=dom();b.root.container=d.root;b.root.fire('submit',d.form);await tick();pendingGets[0](response({project:'p',task:'t',routes:[],launches:[]}));await tick();assert(b.ctx.TaskLaunchesUI.render({id:'t'},null,'p').includes('Принято'),'pre-POST GET must not erase the accepted launch');assert(b.timers.size>0);current=['overview'];mount(b,host);assert.equal(b.timers.size,0,'route exit must clear polling');

''')

    def test_render_locales_native_link_and_evidence_renderer(self):
        self.run_ui(r'''
const b=browser(async()=>response({project:'p',task:'t',routes:[],launches:[{status:'completed',createdAt:1,apiAcceptedAt:2,acknowledgedAt:3,finishedAt:4,sourceUri:'codex://threads/01234567-89ab-7cde-8123-0123456789ab',result:{summary:'<unsafe>',evidence:['docs/result.md']}}]}),'ru');const host={project:'p',route:()=>['tasks','t'],render(){},renderEvidence:(items)=>'<aside>'+items.map(x=>x.path).join(',')+'</aside>'};mount(b,host);await tick();let html=b.ctx.TaskLaunchesUI.renderHistory({id:'t'},'p');assert(html.includes('Результат сохранён'));assert(html.includes('&lt;unsafe&gt;'));assert(html.includes('<aside>docs/result.md</aside>'));assert(html.includes('codex://threads/01234567-89ab-7cde-8123-0123456789ab'));assert.equal(b.ctx.TaskLaunchesUI.safeLink('javascript:alert(1)'),'');assert.equal(b.ctx.TaskLaunchesUI.safeLink('https://user:secret@example.test/'),'');b.ctx.HubI18n.locale='en';html=b.ctx.TaskLaunchesUI.renderHistory({id:'t'},'p');assert(html.includes('Agent acknowledged the assignment'));assert(html.includes('Result saved'));

''')


if __name__ == "__main__":
    unittest.main()
