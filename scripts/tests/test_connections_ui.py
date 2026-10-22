import subprocess
import unittest
from pathlib import Path


WEB = Path(__file__).resolve().parents[2] / 'tools' / 'project-portal' / 'web' / 'connections.js'

HARNESS = r"""
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(process.argv[2], 'utf8');
class Node {
  constructor(root, kind='node', value='') { this.root=root; this.kind=kind; this.value=value; this.dataset={}; this.hidden=false; this.listeners={}; this.checked=false; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  matches(selector) { if(selector==='[data-connection-control-form]')return this.kind==='control-form';return selector.includes('connection-form') ? this.kind==='form' : selector.includes('connection-kind') ? this.kind==='radio' : false; }
  closest(selector) { if(selector==='[data-connection-control-form]'&&this.form)return this.form;return selector === '[data-connection-'+this.kind+']' ? this : null; }
  focus() { this.root.activeElement=this; }
  select() { this.selected=true; }
}
class Root extends Node {
  constructor() {
    super(null,'root'); this.root=this; this.isConnected=true; this.form=new Node(this,'form'); this.form.values={project:'p1'};
    this.url=new Node(this,'url'); this.projectChoice=null; this.radios=[new Node(this,'radio','existing'),new Node(this,'radio','new')];
    this.newHelp=new Node(this); this.existing=new Node(this);
  }
  set innerHTML(value) {
    this.html=value; const match=value.match(/data-connection-url value="([^"]*)"/); this.url.value=match ? match[1] : '';
    this.controlForms=new Map();
    const project=value.match(/<select[^>]*data-connection-project-binding="([^"]+)"[^>]*>([\s\S]*?)<\/select>/);
    if(project){const choice=new Node(this,'project-binding');choice.dataset.connectionProjectBinding=project[1];const selected=project[2].match(/<option value="([^"]+)"[^>]*selected/),first=project[2].match(/<option value="([^"]*)"/);choice.value=selected?selected[1]:first?first[1]:'';this.projectChoice=choice;}
    for(const item of value.matchAll(/<form data-connection-control-form="([^"]+)">([\s\S]*?)<\/form>/g)) {
      const form=new Node(this,'control-form');form.dataset.connectionControlForm=item[1];form.fields={};
      for(const input of item[2].matchAll(/<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"/g)){const field=new Node(this,'control-field',input[2]);field.name=input[1];field.form=form;form.fields[field.name]=field;}
      const selected=item[2].match(/<option value="([^"]+)" selected/);const protocol=new Node(this,'control-field',selected?selected[1]:'mcp-http');protocol.name='protocol';protocol.form=form;form.fields.protocol=protocol;
      form.querySelector=selector=>form.fields[selector.match(/name="([^"]+)"/)?.[1]]||null;
      this.controlForms.set(item[1],form);
    }
  }
  get innerHTML() { return this.html || ''; }
  querySelector(selector) { const control=selector.match(/data-connection-control-form="([^"]+)"/);if(control)return this.controlForms.get(control[1]);if(selector.includes('connection-project-binding')) return this.projectChoice;if(selector.includes('connection-form')) return this.form; if(selector.includes('connection-url')) return this.url; return null; }
  querySelectorAll(selector) { if(selector==='[data-connection-control-form]')return [...this.controlForms.values()];if(selector.includes('connection-kind')) return this.radios; if(selector.includes('connection-new')) return [this.newHelp]; if(selector.includes('connection-existing')) return [this.existing]; return []; }
  emit(type,target) { return Promise.all((this.listeners[type] || []).map(fn => fn({target,currentTarget:this,preventDefault(){}}))); }
}
const settle = async () => { for(let i=0;i<12;i++) await Promise.resolve(); };
function create() {
  const root=new Root(), calls=[], posts=[], historyReplies=[], timers=[], patches=[], keys=[];
  const inventory={bindings:[{id:'b1',project:null,scope:'global',client:'unknown-host',external_id:'ext',metadata:{model:'Client model',chat:'<Client chat>'},activity:{state:'recent-request',lastRequest:2000000000,runningVerified:false},revoked:false,token:'INVENTORY-SECRET'},{id:'b2',project:'p1',project_name:'Legacy example',scope:'project',client:'legacy-host',activity:{state:'unknown'},revoked:false}],invitations:[{id:'i-old',project:'p1',expires:2000000000,token:'INVITE-SECRET',url:'PRIVATE-URL'}]};
  let uuid=0;
  const context = {
    console, FormData:function(form){this.get=name=>form.values[name];},
    fetch:async (url,options={}) => {
      calls.push({url,options});
      if(options.method==='POST') {
        assert.ok(posts.length,'unexpected POST');
        const reply=posts.shift(); if(reply instanceof Error) throw reply; if(typeof reply.apply==='function')reply.apply();
        return {ok:reply.status==null || reply.status<400,status:reply.status || 200,json:async()=>{if(reply.invalidJson) throw Error('invalid JSON');return reply.body;}};
      }
      if(url.includes('/connection-tests?')) {
        if(historyReplies.length){const reply=historyReplies.shift();if(reply instanceof Error)throw reply;return {ok:true,status:200,json:async()=>reply};}
        const params=new URL(url,'http://example.test').searchParams,id=params.get('id'),row=inventory.bindings.find(item=>item.id===id);
        const all=row.testHistory||row.tests||[],limit=Number(params.get('limit')),offset=Math.min(Number(params.get('offset')),Math.max(0,Math.ceil(all.length/limit)-1)*limit);
        const counts={passed:0,configuration:0,failed:0,timeout:0,cancelled:0,running:0};
        for(const test of all){const state=test.state;counts[['passed','verified'].includes(state)?'passed':state==='configuration_required'?'configuration':['timeout','timed_out'].includes(state)?'timeout':state==='cancelled'?'cancelled':['running','awaiting_reply'].includes(state)?'running':'failed']++;}
        return {ok:true,status:200,json:async()=>({connection:id,tests:all.slice(offset,offset+limit),total:all.length,offset,limit,counts})};
      }
      return {ok:true,status:200,json:async()=>url.includes('/projects') ? {projects:[{id:'p1',name:'Example'}]} : inventory};
    },
    setTimeout(fn){timers.push(fn);return timers.length;}, document:{querySelector:()=>root,documentElement:{dataset:{hubLocale:'en'}}},
    navigator:{clipboard:{writeText:async value=>{context.copied=value;}}}, confirm:()=>true,
    crypto:{randomUUID:()=>String(++uuid).padStart(32,'0')},
    HubLiveUI:{patch(node,html,options){patches.push(options);const oldUrl=node.url.value,oldForms=node.controlForms;node.innerHTML=html;if(options.preserveInputs){node.url.value=oldUrl;for(const [id,form] of oldForms||[]){const next=node.controlForms.get(id);if(next)for(const key of ['protocol','endpoint','apiKey'])next.fields[key].value=form.fields[key].value;}}}},
    HubNativeChats:{link:resource=>resource.openUri?'<a data-native-chat>Existing native chat</a>':''},
    HubI18n:{locale:'en',t:key=>{keys.push(key);return key;},onChange(fn){context.languageChange=fn;}},
    addEventListener(){}, window:null
  };
  context.window=context; vm.createContext(context); vm.runInContext(source,context,{filename:'connections.js'});
  const click=async(kind,id)=>{const node=new Node(root,kind);if(kind==='revoke')node.dataset.connectionRevoke=id || 'b1';if(kind==='reconnect')node.dataset.connectionReconnect=id||'b1';if(kind==='test')node.dataset.connectionTest=id||'b1';if(kind==='open')node.dataset.connectionOpen=id||'b1';if(kind==='tab')node.dataset.connectionTab=id||'details';if(kind==='history-page')node.dataset.connectionHistoryPage=id;await root.emit('click',node);await settle();};
  const mount=async()=>{context.HubConnectionsUI.afterRender(root);await settle();};
  const open=async(id='b1',tab='access')=>{await click('open',id);await click('tab',tab);};
  const submit=async()=>{await root.emit('submit',root.form);await settle();};
  const mode=async value=>{await root.emit('change',root.radios.find(n=>n.value===value));await settle();};
  const postCalls=()=>calls.filter(c=>c.options.method==='POST');
  return {root,context,calls,posts,historyReplies,timers,patches,keys,click,mount,open,submit,mode,postCalls,inventory};
}
const validInvite={id:'i1',project:null,token:'RESPONSE-SECRET',expires:2000000000,url:'http://127.0.0.1/connect/secret'};

async function invitationContract() {
  const h=create(),connection=h.inventory.bindings[0];connection.profile={host:'example',persistentInstructions:{revision:'bundle-1',status:'saved',destination:'C:\\Users\\Sample\\AGENTS.md',manifestPath:'C:\\private\\manifest.json'}};connection.instructionsCurrent=true;
  const initial=h.context.HubConnectionsUI.page();assert.ok(initial.includes('Loading connections'));assert.ok(!initial.includes('No registered connections'));
  await h.mount();
  assert.ok(h.root.html.includes('Applications'),'missing EN fallback');
  assert.ok(h.root.html.includes('connection-catalog'));assert.ok(!h.root.html.includes('data-connection-control-form'),'catalog expanded client configuration');
  assert.ok(h.keys.every(key=>key.startsWith('connections.')),'canonical key namespace');
  assert.ok(h.patches.length && h.patches.every(o=>o.preserveInputs===true),'all rendering preserves inputs');
  for(const field of ['name','roots','client','externalId','project','connection-kind']) assert.ok(!h.root.html.includes('name="'+field+'"'),'enrollment or project field leaked into invitation form');
  assert.ok(h.calls.every(c=>!c.url.includes('/projects')),'invitation depends on projects');
  for(const secret of ['INVENTORY-SECRET','INVITE-SECRET','PRIVATE-URL']) assert.ok(!h.root.html.includes(secret),'inventory secret leaked');
  assert.ok(h.root.html.includes('Registration records granted access'));
  assert.ok(h.root.html.includes('Recent Hub request'));
  await h.open();
  assert.ok(h.root.html.includes('id="connection-tab-access" aria-selected="true"'),'legacy status route should land on Hub access');
  assert.ok(h.root.html.includes('Access granted'));
  assert.ok(h.root.html.includes('Bound projects: 0'));
  assert.ok(h.root.html.includes('A request with valid access was received'));
  assert.ok(!h.root.html.includes('data-connection-control-form') && !h.root.html.includes('data-connection-test='),'incoming tab contains client-control actions');
  assert.ok(h.root.html.includes('Rule installation status'));
  assert.ok(h.root.html.includes('The client reported saving the rules'));
  assert.ok(h.root.html.includes('Reported: rules match the current version'));
  assert.ok(h.root.html.includes('#settings/agents/rules'));
  await h.click('tab','diagnostics');
  assert.ok(h.root.html.includes('Client model'));
  assert.ok(h.root.html.includes('Raw application profile'));
  assert.ok(!h.root.html.includes('manifest.json') && !h.root.html.includes('C:\\'),'rule receipt exposed a path');
  assert.ok(!h.root.html.includes('connection-control-form'),'diagnostics contains editable client control settings');
  assert.ok(h.root.html.includes('&lt;Client chat&gt;') && !h.root.html.includes('<Client chat>'));
  h.root.form.values.project='p1';
  h.posts.push({body:validInvite});await h.submit();
  const payload=JSON.parse(h.postCalls()[0].options.body);
  assert.deepEqual(Object.keys(payload).sort(),['action','requestId']);
  assert.equal(payload.action,'invite');
  assert.ok(!h.root.html.includes('RESPONSE-SECRET'),'raw response credential retained in UI');
  assert.ok(h.root.html.includes('only with the intended agent'));
  await h.click('copy');assert.equal(h.context.copied,validInvite.url);assert.ok(h.root.html.includes('Link copied'));
  delete h.context.navigator.clipboard;await h.click('copy');
  assert.ok(h.root.url.selected && h.root.activeElement===h.root.url,'clipboard fallback must select URL');
  assert.ok(h.root.html.includes('Copy it manually.') && !h.root.html.includes('Link copied'),'false clipboard success');
  h.posts.push({body:{...validInvite,id:'i2',url:'http://127.0.0.1/connect/new-secret'}});await h.submit();
  assert.equal(h.root.url.value,'http://127.0.0.1/connect/new-secret','live input preservation retained an old invitation URL');
  h.context.HubI18n.locale='ru';h.context.languageChange();assert.ok(h.root.html.includes('Диагностика'));
}
async function namedConnectionsRemainSeparate() {
  const h=create();h.inventory.bindings[0].client='codex';
  h.inventory.bindings.push({id:'b3',project:null,scope:'global',client:'cursor',activity:{state:'unknown'},revoked:false},{id:'b4',project:null,scope:'global',client:'claude-code',activity:{state:'unknown'},revoked:false},{id:'b5',project:null,scope:'global',client:'codex',metadata:{label:'A different Codex connection'},activity:{state:'unknown'},revoked:false});
  await h.mount();
  assert.ok(h.root.html.includes('>Codex<') && h.root.html.includes('>Cursor<') && h.root.html.includes('>Claude Code<'),'known client identifiers need readable names');
  assert.equal((h.root.html.match(/data-connection-id=/g)||[]).length,5,'separate connection IDs were merged by application name');
  assert.equal((h.root.html.match(/data-connection-open="b[15]"/g)||[]).length,2,'same-application connections must keep separate detail routes');
}
async function uncertainReplies() {
  for(const reply of [new TypeError('lost ACK'),{status:503,body:{error:'server failed'}},{body:{}},{invalidJson:true},{body:null},{body:{id:'i1',url:'x'}},{body:{id:'i1',url:'x',expires:'bad'}}]) {
    const h=create();await h.mount();
    h.posts.push(reply);await h.submit();
    assert.equal(h.postCalls().length,1,'uncertain mutation auto-retried');
    assert.ok(h.root.html.includes('Retry the last change'),'no manual retry');
    h.root.form.values.project='another-project';
    await h.submit();await h.click('revoke');
    assert.equal(h.postCalls().length,1,'pending request allowed a different mutation');
    await h.click('refresh');assert.ok(h.root.html.includes('Retry the last change'),'readback without ACK cleared uncertainty');
    h.posts.push({status:400,body:{error:'rejected replay'}});await h.click('retry');
    assert.ok(h.root.html.includes('Retry the last change'),'failed replay incorrectly confirmed an earlier uncertain change');
    h.posts.push({body:validInvite});await h.click('retry');
    assert.equal(h.postCalls().length,3);
    assert.equal(h.postCalls()[0].options.body,h.postCalls()[1].options.body,'retry changed payload or requestId');
    assert.equal(h.postCalls()[0].options.body,h.postCalls()[2].options.body,'second retry changed payload or requestId');
    assert.ok(!h.root.html.includes('Retry the last change'),'confirmed retry remained pending');
    h.posts.push({body:{...validInvite,id:'i2'}});await h.submit();
    assert.ok(!Object.prototype.hasOwnProperty.call(JSON.parse(h.postCalls()[3].options.body),'project'));
  }
}
async function revokeAndRemount() {
  const h=create();await h.mount();
  h.posts.push({body:{id:'b1',revoked:false}});await h.click('revoke');
  assert.ok(h.root.html.includes('Retry the last change'),'invalid revoke ACK accepted');
  await h.submit();assert.equal(h.postCalls().length,1);
  h.posts.push({body:{id:'different',revoked:true}});await h.click('retry');
  assert.ok(h.root.html.includes('Retry the last change'),'wrong revoke ID accepted');
  h.posts.push({body:{id:'b1',revoked:true}});await h.click('retry');
  assert.ok(!h.root.html.includes('Retry the last change'),'valid revoke ACK rejected');
  assert.equal(h.postCalls()[0].options.body,h.postCalls()[1].options.body);
  const second=new Root();h.context.HubConnectionsUI.afterRender(second);await settle();
  assert.equal(second.listeners.submit.length,1,'second root has no submit listener');
  assert.equal(second.listeners.click.length,1,'second root has no click listener');
  assert.equal(second.listeners.change.length,1,'control drafts keep select changes');assert.ok(!second.html.includes('name="project"'),'invitation must not have a project selector');
  h.context.HubConnectionsUI.afterRender(second);
  assert.equal(second.listeners.submit.length,1,'duplicate root binding');
  h.posts.push({body:validInvite});await second.emit('submit',second.form);await settle();
  assert.equal(h.postCalls().length,4,'second root submission ignored');
  assert.equal(JSON.parse(h.postCalls()[3].options.body).project,undefined);
}
async function globalInvitationIgnoresLegacyPageScope() {
  const h=create();
  h.context.HubConnectionsUI.page({project:'p1'});await h.mount();
  assert.ok(!h.root.html.includes('name="project"'),'fixed project displayed a scope selector');
  h.root.form.values.project='different';
  h.posts.push({body:{...validInvite,project:'p1'}});await h.submit();
  assert.equal(JSON.parse(h.postCalls()[0].options.body).project,undefined);
  assert.ok(h.root.html.includes('unknown-host') && h.root.html.includes('legacy-host'),'global inventory filtered by a project');
}
async function noProjectsNeeded() { const h=create();h.inventory.bindings=[];await h.mount();assert.ok(h.root.html.includes('before adding projects'));h.posts.push({body:validInvite});await h.submit();assert.equal(h.postCalls().length,1);assert.equal(JSON.parse(h.postCalls()[0].options.body).action,'invite'); }
async function reconnectPreservesHistoryAndRequiresTheCorrectBindingAck() {
  const h=create(),row=h.inventory.bindings[0];row.revoked=true;row.nativeChat={client:'example-client',nativeId:'chat-1',openUri:'example://chat/1'};
  await h.mount();await h.open('b1','access');assert.ok(h.root.html.includes('Disconnect') || h.root.html.includes('Reconnect'));assert.ok(h.root.html.includes('data-connection-reconnect="b1"'));
  await h.click('tab','diagnostics');assert.ok(h.root.html.includes('Existing native chat'));assert.ok(h.root.html.includes('&lt;Client chat&gt;'));
  h.posts.push({body:{...validInvite,reconnect:'other'}});await h.click('reconnect');
  assert.ok(h.root.html.includes('Retry the last change'));await h.submit();assert.equal(h.postCalls().length,1);
  h.posts.push({body:{...validInvite,reconnect:'b1'}});await h.click('retry');
  const request=JSON.parse(h.postCalls()[0].options.body);assert.equal(request.action,'reconnect');assert.equal(request.id,'b1');assert.ok(request.requestId);assert.equal(request.project,undefined);
  assert.equal(h.postCalls()[0].options.body,h.postCalls()[1].options.body);
  assert.ok(h.root.html.includes('Reconnection invitation'));assert.ok(h.root.html.includes('restores the same connection'));
}
async function capabilityTestsShowReportedSupportProgressAndTimeouts() {
  const h=create(),row=h.inventory.bindings[0];row.capabilities={openChat:{state:'declared',message:'Client assertion'},mcp:{state:'verified',message:'Hub received an authenticated tool request'}};row.tests=[];
  row.features={openChat:{state:'source_available',support:'declared'},createChat:{state:'not_configured',support:'declared',verification:{state:'verified'}},sendMessage:{state:'not_reported',support:'not_reported'},callback:{state:'not_reported',support:'not_reported'}};
  row.profile={capabilities:{openChat:{uriTemplate:'example://chat/{id}'},createChat:{tool:'create_conversation'}},control:{protocol:'mcp-http',endpoint:'http://127.0.0.1:9100/client'}};
  await h.mount();await h.open('b1','control');assert.ok(h.root.html.includes('Application chats'));assert.ok(h.root.html.includes('Project bindings'));
  assert.ok(h.root.html.includes('Control interface not provided') || h.root.html.includes('Settings need to be saved'));
  assert.equal((h.root.html.match(/data-connection-feature=/g)||[]).length,4,'the control page renders one feature card per feature');
  assert.ok(h.root.html.includes('Control interface not provided') || h.root.html.includes('Settings need to be saved'));
  assert.ok(!h.root.html.includes('data-connection-test='),'reported support must not substitute for saved control settings');
  row.control={...row.profile.control,hasCredential:true};await h.click('refresh');
  assert.ok(h.root.html.includes('The test creates a separate chat and sends a diagnostic message'),'testing consequences must precede an explicit action');
  assert.ok(h.root.html.includes('Create a test chat and check the exchange'));
  assert.equal(h.postCalls().length,0,'rendering must not run capability tests');
  row.profile.control.protocol='http-json';row.profile.capabilities.createChat={path:'/chats'};row.control.protocol='http-json';await h.click('refresh');
  assert.ok(h.root.html.includes('data-connection-test="b1"'),'matching HTTP JSON path enables the explicit exchange test');
  const running=[{id:'openChat',state:'awaiting_reply',startedAt:Date.now()/1000,deadline:Date.now()/1000+20,message:'Waiting for client'}];
  h.posts.push({body:{id:'b1',capabilities:row.capabilities,tests:running,profileRevision:'profile-1'},apply(){row.tests=running;}});await h.click('test');
  assert.deepEqual(JSON.parse(h.postCalls()[0].options.body),{action:'test',id:'b1'});
  assert.ok(!h.root.html.includes('data-connection-test-result'),'control view must not duplicate test history');
  await h.click('tab','diagnostics');
  assert.ok(h.root.html.includes('Waiting for a client response'));assert.ok(h.root.html.includes('Running: 1'));assert.ok(h.root.html.includes('Waiting for a response until'));
  assert.ok(h.root.html.includes('<strong>Exchange test attempt</strong>'),'test run IDs are not displayed as capability names');
  await h.click('test');assert.equal(h.postCalls().length,1,'an active probe must not be launched twice');
  row.tests=[{id:'openChat',state:'timeout',startedAt:Date.now()/1000-20,finishedAt:Date.now()/1000,deadline:Date.now()/1000-1,message:'No client response'}];
  row.capabilities.openChat.state='unknown';await h.click('refresh');
  assert.ok(h.root.html.includes('Timed out'));assert.ok(h.root.html.includes('No reply: 1'));assert.ok(h.root.html.includes('Finished:'));assert.ok(!h.root.html.includes('data-connection-feature='));
  row.tests=[{id:'sendMessage',state:'configuration_required',finishedAt:Date.now()/1000,message:'configuration_required'}];await h.click('refresh');
  assert.ok(h.root.html.includes('Setup required: 1'));assert.ok(!h.root.html.includes('Completed 1 of 1'));
  assert.ok(!h.root.html.includes('data-connection-feature='));assert.ok(h.root.html.includes('Raw application profile'));
  row.features.createChat={state:'stale',support:'declared',verification:{state:'verified',message:'Hub received an authenticated tool request'}};await h.click('tab','control');
  assert.ok(h.root.html.includes('Settings changed'),'stale server projection must override raw verified capability evidence');
  assert.ok(!h.root.html.includes('Result source: configured-interface test'),'stale results must not look current');
  row.features.createChat={state:'verified',support:'declared',verification:{state:'verified'}};row.features.sendMessage={state:'verified',support:'declared',verification:{state:'verified'}};await h.click('refresh');
  assert.equal((h.root.html.match(/Result source: configured-interface test/g)||[]).length,2,'verified create/send results come from the configured-interface test');
  h.context.HubI18n.locale='ru';h.context.languageChange();assert.equal((h.root.html.match(/Источник результата: проверка настроенного интерфейса/g)||[]).length,2);h.context.HubI18n.locale='en';h.context.languageChange();
  row.control=null;row.features.createChat={state:'not_configured',support:'declared',verification:{state:'verified'}};await h.click('refresh');
  assert.ok(h.root.html.includes('Settings need to be saved'),'configuration state must override raw verified capability evidence');
  row.nativeChat={client:'example-client',nativeId:'chat-1',openUri:'https://example.test/chats/chat-1'};row.profile={capabilities:{openChat:{uriTemplate:'https://example.test/chats/{nativeId}'}}};row.features={openChat:{state:'source_available',support:'not_reported'},createChat:{state:'not_reported'},sendMessage:{state:'not_reported'},callback:{state:'not_reported'}};await h.click('refresh');
  assert.ok(h.root.html.includes('Source link available'),'open-only source links work without control');assert.ok(!h.root.html.includes('data-connection-test='));
}
async function clientControlIsExplicitAndKeepsItsCredentialSeparate() {
  const h=create(),row=h.inventory.bindings[0];row.profile={control:{protocol:'mcp-http',endpoint:'http://127.0.0.1:9100/client',apiKey:'GET-PRIVATE-KEY'},capabilities:{createChat:{tool:'create_conversation'}}};
  await h.mount();await h.open('b1','control');assert.equal(h.postCalls().length,0);assert.ok(!h.root.html.includes('GET-PRIVATE-KEY'));
  assert.ok(h.root.html.includes('Control interface not provided') || h.root.html.includes('Settings need to be saved'));
  assert.ok(!h.root.html.includes('data-connection-test='),'probing without confirmed control settings should be unavailable');assert.ok(h.root.html.includes('Exchange testing requires a matching configured interface'));
  row.control={protocol:'mcp-http',endpoint:'http://127.0.0.1:9100/saved',hasCredential:true};
  await h.click('refresh');
  assert.ok(!h.root.html.includes('data-connection-test='),'mismatched configured and reported endpoints must not enable a pointless probe');
  row.profile.control.endpoint=row.control.endpoint;await h.click('refresh');
  assert.ok(h.root.html.includes('data-connection-test='),'matching confirmed settings should enable probing');
  assert.ok(!h.root.html.includes('Address reported by the application'),'matching addresses should not be repeated above the form');
  assert.ok(!h.root.html.includes('<details class="connection-control"'),'main control settings must be visible without expansion');
  assert.ok(h.root.html.includes('Obtain this key from the application itself'),'separate-key instructions stay next to the visible settings');
  assert.ok(h.root.html.includes('Ready to test'),'a saved control endpoint must remain ready for an explicit test');assert.ok(!h.root.html.includes('Confirmed: the API returned a new chat ID.'),'saving an endpoint must not verify chat creation');
  let form=h.root.controlForms.get('b1');assert.equal(form.fields.endpoint.value,row.control.endpoint,'saved endpoint should take precedence over the client-reported preview');
  form.fields.protocol.value='http-json';form.fields.apiKey.value='CLIENT-CONTROL-KEY';await h.root.emit('change',form.fields.protocol);await h.root.emit('input',form.fields.apiKey);
  await h.click('refresh');form=h.root.controlForms.get('b1');assert.equal(form.fields.apiKey.value,'CLIENT-CONTROL-KEY');assert.equal(form.fields.protocol.value,'http-json');assert.ok(/data-connection-test="b1"[^>]*disabled/.test(h.root.html),'dirty control fields guard testing');
  h.posts.push({body:{saved:true,id:'wrong'}});await h.root.emit('submit',form);await settle();
  assert.ok(h.root.html.includes('Retry the last change'));const payload=JSON.parse(h.postCalls()[0].options.body);
  assert.equal(payload.action,'configure-control');assert.equal(payload.id,'b1');assert.equal(payload.apiKey,'CLIENT-CONTROL-KEY');assert.equal(payload.protocol,'http-json');assert.ok(payload.requestId);assert.equal(payload.project,undefined);
  h.posts.push({body:{saved:true,id:'b1'},apply(){row.control={protocol:'http-json',endpoint:'http://127.0.0.1:9100/saved',hasCredential:true};}});await h.click('retry');
  assert.equal(h.postCalls()[0].options.body,h.postCalls()[1].options.body);assert.equal(h.root.controlForms.get('b1').fields.apiKey.value,'');assert.ok(!h.root.html.includes('CLIENT-CONTROL-KEY'));
  assert.ok(h.root.html.includes('Settings saved. Run a test separately.'));assert.equal(h.root.controlForms.get('b1').fields.endpoint.value,'http://127.0.0.1:9100/saved','successful save should retain the configured endpoint');
  assert.equal(h.root.controlForms.get('b1').fields.apiKey.value,'');assert.equal(h.root.controlForms.get('b1').fields.protocol.value,'http-json');assert.equal(h.postCalls().length,2,'saving and retrying must not post a capability test');
}
async function applicationProofDoesNotDependOnTestProject() {
  const h=create(),row=h.inventory.bindings[0];
  row.profile={control:{protocol:'http-json',endpoint:'http://127.0.0.1:9100'},capabilities:{createChat:{path:'/create',projectRouting:true}}};row.control={...row.profile.control};
  row.projectBindings=[{id:'a',project:'project-a',status:'active',scope:{root:'C:/example/a'}},{id:'b',project:'project-b',status:'active',scope:{root:'C:/example/b'}}];
  row.features=Object.fromEntries(['createChat','sendMessage','callback'].map(id=>[id,{state:'verified'}]));
  row.projectVerifications={a:{features:{createChat:{state:'failed'}}},b:{features:{createChat:{state:'ready'}}}};
  row.tests=[{id:'a-running',state:'awaiting_reply',current:true,projectBinding:{bindingId:'a',project:'project-a',scope:{root:'C:/example/a'}}}];
  await h.mount();await h.open('b1','control');
  const featureCards=()=>h.root.html.match(/<section class="connection-section connection-feature"[\s\S]*?<\/section>/g);
  const originalCards=featureCards();
  assert.equal(originalCards.length,4);
  assert(h.root.html.includes('Confirmed: the API returned a new chat ID.'));
  assert(h.root.html.includes('Where to create the test chat'));
  assert(h.root.html.includes('The result applies to this application'));
  h.root.projectChoice.value='b';await h.root.emit('change',h.root.projectChoice);await settle();
  assert.deepEqual(featureCards(),originalCards,'changing the test destination must not change application feature cards');
  assert(!/data-connection-test="b1" disabled/.test(h.root.html),'project A must not block project B');
  h.posts.push({body:{id:'b1',tests:row.tests}});await h.click('test');assert.equal(h.postCalls().length,1);assert.equal(JSON.parse(h.postCalls()[0].options.body).bindingId,'b');
  h.root.projectChoice.value='a';await h.root.emit('change',h.root.projectChoice);await settle();
  assert.deepEqual(featureCards(),originalCards);
  assert(h.root.html.includes('Confirmed: the API returned a new chat ID.'));await h.click('test');assert.equal(h.postCalls().length,1,'the same active project probe stays blocked');
  row.features.createChat={state:'failed'};await h.click('refresh');
  const failedCards=featureCards();assert.notDeepEqual(failedCards,originalCards);
  h.root.projectChoice.value='b';await h.root.emit('change',h.root.projectChoice);await settle();
  assert.deepEqual(featureCards(),failedCards,'a failed application result must also stay independent of the selected project');
  await h.click('tab','diagnostics');assert(h.root.html.includes('project-a'));assert(h.root.html.includes('C:/example/a'));
}
async function historyUsesBoundedServerPagesAndKeepsEachApplicationSeparate() {
  const h=create(),row=h.inventory.bindings[0];
  row.testHistory=Array.from({length:1003},(_,index)=>({id:'attempt-'+index,state:index%2?'failed':'passed',startedAt:2000000000-index,finishedAt:2000000001-index,current:true,projectBinding:{project:'p1',scope:{root:'C:/example'}}}));
  row.tests=row.testHistory.slice(0,8);
  await h.mount();await h.open('b1','access');
  assert(h.root.html.includes('does not depend on its selected model'));
  await h.click('tab','control');
  assert(h.root.html.includes('This version includes a local adapter for Codex'));
  assert(h.root.html.includes('Hub does not yet include a chat-control adapter for this application'));
  assert(!h.root.html.includes('data-connection-feature='),'unsupported clients have no placeholder feature statuses');
  assert(!h.root.html.includes('data-connection-test='),'an invitation alone does not supply chat control for another application');
  await h.click('tab','diagnostics');
  assert(h.root.html.includes('Showing 1–20 of 1003'));assert(h.root.html.includes('Page 1 of 51'));
  assert.equal((h.root.html.match(/data-connection-test-result=/g)||[]).length,20);
  assert(!h.root.html.includes('data-connection-test-result="attempt-20"'));
  assert(h.root.html.includes('<table class="connection-test-table">'));
  assert(h.root.html.includes('Passed: 502')&&h.root.html.includes('Failed: 501'),'summary covers all pages');
  await h.click('history-page','next');
  assert(h.root.html.includes('Showing 21–40 of 1003'));
  assert(!h.root.html.includes('data-connection-test-result="attempt-0"'));
  assert(h.root.html.includes('data-connection-test-result="attempt-20"'));
  h.historyReplies.push(Error('network unavailable'));await h.click('history-page','next');
  assert(h.root.html.includes('Could not load this history page.'));
  assert(h.root.html.includes('Showing 21–40 of 1003'),'keep the last readable page after a failed load');
  await h.click('history-retry');assert(h.root.html.includes('Showing 41–60 of 1003'),'retry the failed page');
  await h.click('refresh');assert(h.root.html.includes('Showing 41–60 of 1003'),'live refresh retains the page');
  await h.click('history-page','previous');assert(h.root.html.includes('Showing 21–40 of 1003'));
  const other=h.inventory.bindings[1];other.tests=[{id:'other-only',state:'passed'}];
  h.historyReplies.push({connection:'b1',tests:[{id:'wrong-application'}],offset:0,limit:20,total:1});
  await h.open('b2','diagnostics');assert(h.root.html.includes('Could not load this history page.'));
  assert(!h.root.html.includes('wrong-application')&&!h.root.html.includes('attempt-20'));
  await h.click('history-retry');assert(h.root.html.includes('other-only')&&!h.root.html.includes('attempt-20'));
  other.tests=[];await h.click('refresh');assert(!h.root.html.includes('connection-test-history'),'an unsupported client with no attempts needs no chat-test journal');
  await h.open('b1','diagnostics');assert(h.root.html.includes('Showing 21–40 of 1003'),'application pages are independent');
  assert.equal(h.postCalls().length,0,'reading and paging history cannot launch a test');
}
async function projectBindingSelectionIsExplicit() {
  const h=create(),row=h.inventory.bindings[0];
  row.profile={control:{protocol:'http-json',endpoint:'http://127.0.0.1:9100/client'},capabilities:{createChat:{path:'/create',projectRouting:true}}};
  row.control={protocol:'http-json',endpoint:'http://127.0.0.1:9100/client',hasCredential:true};
  row.projectBindings=[{id:'pb-ready',project:'p1',status:'active'},{id:'pb-revoked',project:'p2',status:'revoked'}];
  await h.mount();await h.open('b1','control');
  assert.ok(h.root.html.includes('data-connection-project-binding="b1"'),'routing exposes an explicit project selector');
  assert.ok(h.root.html.includes('pb-ready')&&!h.root.html.includes('pb-revoked'),'only active bindings are selectable');
  assert.ok(/data-connection-test="b1"[^>]*disabled/.test(h.root.html),'routing requires an explicit project selection');
  h.root.projectChoice.value='pb-ready';await h.root.emit('change',h.root.projectChoice);assert.ok(!/data-connection-test="b1"[^>]*disabled/.test(h.root.html),'selecting a binding enables the exchange test');h.posts.push({body:{id:'b1',capabilities:{},tests:[]}});await h.click('test');
  assert.equal(JSON.parse(h.postCalls()[0].options.body).bindingId,'pb-ready');
  row.profile.control.protocol='mcp-http';row.profile.capabilities.createChat={tool:'codex-desktop-bridge.createChat',projectRouting:true};row.control.protocol='mcp-http';await h.click('refresh');
  h.context.HubI18n.locale='ru';h.context.languageChange();assert.ok(h.root.html.includes('В этой версии готовый локальный адаптер доступен для Codex'));
}
async function structuredTestErrorsAreSafeAndVisible() {
  const h=create(),row=h.inventory.bindings[0];
  row.profile={control:{protocol:'http-json',endpoint:'http://127.0.0.1:9100'},capabilities:{createChat:{path:'/create'}}};
  row.control={protocol:'http-json',endpoint:'http://127.0.0.1:9100',hasCredential:true};
  row.testHistory=[{id:'old-finished-late',state:'failed',startedAt:1999999990,finishedAt:2000000100,error:{code:'control_timeout',phase:'connect'}},{id:'failed-1',state:'failed',startedAt:2000000000,finishedAt:2000000001,error:{code:'control_timeout',phase:'send',httpStatus:504,outcomeUnknown:true},projectBinding:{project:'example-project'}}];row.tests=row.testHistory;
  await h.mount();await h.open('b1','control');
  assert(h.root.html.includes('The application did not respond in time'),'latest structured reason is shown beside exchange test');
  assert(h.root.html.includes('sending the message')&&h.root.html.includes('HTTP status: 504'),'structured phase and HTTP status are shown');
  assert(h.root.html.includes('The chat or message may already exist'),'unknown outcome guidance is shown');
  assert(h.root.html.includes('Inspect the journal and the application chat')&&!h.root.html.includes('repeat the same request'),'unknown outcome guidance does not promise same-request replay');
  await h.click('tab','diagnostics');assert(h.root.html.includes('The application did not respond in time'),'history exposes the same structured reason');
  row.tests=[{id:'unsafe',state:'failed',error:{code:'made_up_code',phase:'send',message:'<script>alert(1)</script>'}}];row.testHistory=row.tests;await h.click('refresh');
  assert(h.root.html.includes('The exchange test could not be completed.'),'unknown error uses safe generic text');
  assert(!h.root.html.includes('made_up_code')&&!h.root.html.includes('<script>'),'unknown code and remote message are suppressed');
}
(async()=>{await invitationContract();await namedConnectionsRemainSeparate();await uncertainReplies();await revokeAndRemount();await globalInvitationIgnoresLegacyPageScope();await noProjectsNeeded();await reconnectPreservesHistoryAndRequiresTheCorrectBindingAck();await capabilityTestsShowReportedSupportProgressAndTimeouts();await clientControlIsExplicitAndKeepsItsCredentialSeparate();await projectBindingSelectionIsExplicit();await applicationProofDoesNotDependOnTestProject();await historyUsesBoundedServerPagesAndKeepsEachApplicationSeparate();await structuredTestErrorsAreSafeAndVisible();})().catch(error=>{console.error(error);process.exitCode=1;});
"""


class ConnectionsUiTest(unittest.TestCase):
    def test_connections_widget_behavior(self):
        result = subprocess.run(
            ['node', '-', str(WEB)], input=HARNESS,
            capture_output=True, text=True, timeout=30, encoding='utf-8',
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
