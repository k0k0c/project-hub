import subprocess
import unittest
from pathlib import Path


WEB = Path(__file__).resolve().parents[2] / 'tools' / 'project-portal' / 'web' / 'agent-providers.js'

HARNESS = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
class Field { constructor(name,value=''){this.name=name;this.value=value;this.disabled=false;} getAttribute(k){return k==='name'?this.name:null;} }
class Button { constructor(attrs={}){this.attrs=attrs;} getAttribute(k){return this.attrs[k]||null;} closest(selector){const key=selector.slice(1,-1);return Object.prototype.hasOwnProperty.call(this.attrs,key)?this:null;} }
class Root { constructor(){this.listeners={};this.isConnected=true;this.root=this;this.activeElement=null;this.innerHTML='';} addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);} set innerHTML(value){this.html=value;this.dialog=value.includes('data-provider-dialog')?{open:false,showModal(){this.open=true;}}:null;this.fields={};for(const m of value.matchAll(/<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"/g))this.fields[m[1]]=new Field(m[1],m[2]);for(const m of value.matchAll(/<select[^>]*name="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)){const selected=m[2].match(/<option value="([^"]+)"[^>]*selected/);this.fields[m[1]]=new Field(m[1],selected?selected[1]:'');}this.fields.apiKey??=new Field('apiKey','');} get innerHTML(){return this.html||'';} querySelector(selector){if(selector==='[data-provider-dialog]')return this.dialog;if(selector==='[data-provider-form]')return {matches:s=>s==='[data-provider-form]'};const m=selector.match(/\[name="([^"]+)"\]/);if(m)return this.fields[m[1]]||null;return null;} emit(type,target){return Promise.all((this.listeners[type]||[]).map(fn=>fn({target,currentTarget:this,preventDefault(){}})));} }
const settle=async()=>{for(let i=0;i<16;i++)await Promise.resolve();};
function make(defaultProvider='codex'){const root=new Root(),posts=[],calls=[],keys=[];let n=0;const context={console,crypto:{randomUUID:()=>String(++n).padStart(32,'0')},fetch:async(url,opt={})=>{calls.push({url,opt});if(opt.method==='POST'){const item=posts.shift();if(item instanceof Error)throw item;return {ok:item.status==null||item.status<400,status:item.status||200,json:async()=>item.body};}return {ok:true,status:200,json:async()=>({revision:'r1',default:defaultProvider,items:[{id:'p1',name:'Primary',provider:'responses',model:'model-a'},{id:'p2',name:'Secondary',provider:'anthropic',model:'model-b'}]})};},HubLiveUI:{patch(node,html){node.innerHTML=html;}},HubI18n:{locale:'en',t:key=>{keys.push(key);return key;},onChange(fn){context.lang=fn;}},document:{querySelector:()=>root,documentElement:{dataset:{hubLocale:'en'}}},setTimeout(){return 1;}};context.window=context;vm.createContext(context);vm.runInContext(source,context,{filename:'agent-providers.js'});return {root,context,posts,calls,keys};}
async function main(){const h=make();assert.ok(h.context.HubAgentProvidersUI.card().includes('agent-providers-card'),'card');assert.ok(h.context.HubAgentProvidersUI.card().includes('data-provider-add'),'card-content');assert.ok(!h.context.HubAgentProvidersUI.card().includes('data-provider-form'),'form-is-modal');h.context.HubAgentProvidersUI.afterRender(h.root);await settle();assert.equal(h.calls.filter(c=>!c.opt?.method&&c.url.includes('agent-providers')).length,1,'load');assert.ok(h.keys.every(k=>k.startsWith('provider.')),'keys');await h.root.emit('click',new Button({'data-provider-add':'1'}));assert.ok(h.root.html.includes('data-provider-dialog'));assert.ok((h.root.html.match(/value="(responses|anthropic|gemini|chat)"/g)||[]).length>=4,'four-protocols');assert.doesNotMatch(h.root.html,/data-provider-native|Codex|CLI|командной строки/,'no-native-executor');assert.ok(h.root.html.includes('provider-fields'),'spacing-hooks');assert.equal(h.context.HubAgentProvidersUI.selectedProvider(),'none');h.root.fields.name.value='Draft';h.root.fields.provider.value='responses';h.root.fields.model.value='m';h.root.fields.endpoint.value='';h.root.fields.apiKey.value='SECRET-KEY';await h.root.emit('input',h.root.fields.name);await h.root.emit('input',h.root.fields.apiKey);h.posts.push({body:{saved:true,id:'00000000000000000000000000000001',requestId:'wrong'}});await h.root.emit('submit',h.root.querySelector('[data-provider-form]'));await settle();assert.ok(h.root.html.includes('Retry the last change'),'pending:'+h.root.html);assert.equal(h.calls.filter(c=>c.opt.method==='POST').length,1,'post1');const first=h.calls.find(c=>c.opt.method==='POST').opt.body;const requestId=JSON.parse(first).requestId;h.posts.push({body:{saved:true,id:'00000000000000000000000000000001',requestId}});const retry=new Button({'data-provider-retry':'1'});await h.root.emit('click',retry);await settle();assert.equal(h.calls.filter(c=>c.opt.method==='POST').length,2,'post2');assert.equal(h.calls.filter(c=>c.opt.method==='POST')[1].opt.body,first,'same');assert.equal(h.root.fields.apiKey.value,'','clear');assert.ok(!h.root.html.includes('SECRET-KEY'),'secret');h.posts.push({body:{saved:true,id:'p1',requestId:'00000000000000000000000000000002'}});await h.root.emit('click',new Button({'data-provider-select':'p1'}));await settle();assert.equal(JSON.parse(h.calls.filter(c=>c.opt.method==='POST')[2].opt.body).action,'select','select');await h.root.emit('click',new Button({'data-provider-add':'1'}));h.context.lang();await settle();assert.equal(h.root.fields.name.value,'Draft','draft');assert.equal(h.root.listeners.submit.length,1,'binding');h.context.HubI18n.locale='ru';h.context.lang();assert.ok(h.root.html.includes('Модели для запросов Hub'),'ru');}

async function emptyExecutor(){const h=make('none');h.context.HubAgentProvidersUI.afterRender(h.root);await settle();assert.equal(h.context.HubAgentProvidersUI.selectedProvider(),'none');assert.ok(h.keys.includes('provider.noneHelp'),'disabled state explanation localized');assert.ok(h.root.html.includes('data-provider-executor="none"'));assert.match(h.root.html,/data-provider-select="none"[^>]*disabled/,'none selected');}
async function parentRerenderPreservesDialog(){const h=make('none');h.context.HubAgentProvidersUI.afterRender(h.root);await settle();await h.root.emit('click',new Button({'data-provider-edit':'p1'}));assert.equal(h.root.dialog.open,true);h.root.fields.name.value='Unsaved name';h.root.fields.apiKey.value='UNSAVED-SECRET';await h.root.emit('input',h.root.fields.name);await h.root.emit('input',h.root.fields.apiKey);const gets=h.calls.filter(c=>!c.opt.method).length;h.root.innerHTML=h.context.HubAgentProvidersUI.card();assert.equal(h.root.dialog.open,false,'parent render removes open state');assert.equal(h.root.fields.apiKey.value,'','secret is absent from HTML');h.context.HubAgentProvidersUI.afterRender(h.root);await settle();assert.equal(h.root.dialog.open,true,'same-root afterRender restores modal');assert.equal(h.root.fields.name.value,'Unsaved name');assert.equal(h.root.fields.apiKey.value,'UNSAVED-SECRET');assert.ok(!h.root.html.includes('UNSAVED-SECRET'),'draft secret never serialized into markup');assert.equal(h.calls.filter(c=>!c.opt.method).length,gets,'same-root render does not reload');assert.equal(h.calls.filter(c=>c.opt.method==='POST').length,0);h.context.HubAgentProvidersUI.afterRender(h.root);await settle();assert.equal(h.root.dialog.open,true);assert.equal(h.root.fields.apiKey.value,'UNSAVED-SECRET');assert.equal(h.root.listeners.submit.length,1,'events bound once');}
async function editAndDelete(){const h=make('none');h.context.HubAgentProvidersUI.afterRender(h.root);await settle();assert.ok(h.root.html.includes('<table'));assert.ok(h.root.html.includes('Secondary'));assert.ok(h.root.html.includes('data-provider-edit="p2"'));assert.ok(h.root.html.includes('data-provider-edit="p1"'));assert.ok(h.root.html.includes('data-provider-delete="p1"'));await h.root.emit('click',new Button({'data-provider-edit':'p1'}));assert.equal(h.root.fields.name.value,'Primary');assert.equal(h.root.fields.model.value,'model-a');assert.equal(h.root.fields.apiKey.value,'');assert.ok(h.root.html.includes('Leave blank to keep'));h.root.fields.name.value='Changed';h.posts.push({body:{saved:true,id:'wrong-id',requestId:'00000000000000000000000000000001'}});await h.root.emit('submit',h.root.querySelector('[data-provider-form]'));await settle();const first=h.calls.find(c=>c.opt.method==='POST').opt.body;assert.equal(JSON.parse(first).id,'p1');assert.equal(JSON.parse(first).apiKey,'');assert.ok(h.root.html.includes('Retry the last change'));h.posts.push({body:{saved:true,id:'p1',requestId:JSON.parse(first).requestId}});await h.root.emit('click',new Button({'data-provider-retry':'1'}));await settle();assert.ok(!h.root.html.includes('data-provider-dialog'));await h.root.emit('click',new Button({'data-provider-delete':'p1'}));assert.ok(h.root.html.includes('Delete API service?'));assert.equal(h.calls.filter(c=>c.opt.method==='POST').length,2,'delete waits for confirmation');await h.root.emit('click',new Button({'data-provider-close':'1'}));assert.equal(h.calls.filter(c=>c.opt.method==='POST').length,2,'cancel is read only');await h.root.emit('click',new Button({'data-provider-delete':'p1'}));h.posts.push(new Error('lost delete ACK'));await h.root.emit('click',new Button({'data-provider-confirm-delete':'1'}));await settle();const deletion=h.calls.filter(c=>c.opt.method==='POST')[2].opt.body;assert.equal(JSON.parse(deletion).action,'delete');h.posts.push({body:{saved:true,id:'p1',requestId:JSON.parse(deletion).requestId}});await h.root.emit('click',new Button({'data-provider-retry':'1'}));await settle();assert.equal(h.calls.filter(c=>c.opt.method==='POST')[3].opt.body,deletion);assert.ok(!h.root.html.includes('data-provider-dialog'));}
async function rejectedUncertainRetry(){const h=make('none');h.context.HubAgentProvidersUI.afterRender(h.root);await settle();assert.ok(h.root.html.includes('Across the installation'));assert.ok(h.root.html.includes('Direct API calls to analyze architecture, code, and documents.'));await h.root.emit('click',new Button({'data-provider-add':'1'}));assert.ok(h.root.html.includes('separate from the Hub token'),'API key help belongs to the open service dialog');h.root.fields.name.value='Example';h.root.fields.model.value='Reported model';h.root.fields.apiKey.value='PRIVATE-KEY';h.posts.push(new Error('lost ACK'));await h.root.emit('submit',h.root.querySelector('[data-provider-form]'));await settle();h.posts.push({status:400,body:{error:'rejected replay'}});await h.root.emit('click',new Button({'data-provider-retry':'1'}));await settle();assert.ok(h.root.html.includes('Retry the last change'),'a rejected replay does not confirm the uncertain original write');const posts=h.calls.filter(c=>c.opt.method==='POST');assert.equal(posts[0].opt.body,posts[1].opt.body);}
main().then(emptyExecutor).then(rejectedUncertainRetry).then(editAndDelete).then(parentRerenderPreservesDialog).catch(error=>{console.error(error);process.exitCode=1;});
'''

PROBE_HARNESS = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
class Button { constructor(attrs={}){this.attrs=attrs;} getAttribute(k){return this.attrs[k]||null;} closest(selector){const key=selector.slice(1,-1);return Object.prototype.hasOwnProperty.call(this.attrs,key)?this:null;} }
class Root { constructor(){this.listeners={};this.isConnected=true;this.activeElement=null;this.html='';this.fields={};this.dialog=null;} addEventListener(type,fn){(this.listeners[type]??=[]).push(fn);} set innerHTML(value){this.html=value;this.dialog=value.includes('data-provider-dialog')?{open:false,showModal(){this.open=true;}}:null;this.fields={};for(const m of value.matchAll(/<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"/g))this.fields[m[1]]={name:m[1],value:m[2],getAttribute(k){return k==='name'?this.name:null;}};for(const m of value.matchAll(/<select[^>]*name="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)){const selected=m[2].match(/<option value="([^"]+)"[^>]*selected/);this.fields[m[1]]={name:m[1],value:selected?selected[1]:'',getAttribute(k){return k==='name'?this.name:null;}};}} querySelector(selector){if(selector==='[data-provider-dialog]')return this.dialog;if(selector==='[data-provider-form]')return {matches:s=>s==='[data-provider-form]'};const m=selector.match(/\[name="([^"]+)"\]/);return m?(this.fields[m[1]]||null):null;} emit(type,target){for(const fn of this.listeners[type]||[])fn({target,currentTarget:this,preventDefault(){}});}}
const settle=async()=>{for(let i=0;i<64;i++)await Promise.resolve();};
async function main(){let probeCount=0;const root=new Root(),calls=[],context={console,crypto:{randomUUID:()=> 'a'.repeat(32)},fetch:async(url,opt={})=>{calls.push({url,opt});if(opt.method==='POST'){const body=JSON.parse(opt.body);if(body.action==='save')return {ok:true,status:200,json:async()=>({saved:true,id:body.id||'b'.repeat(32),requestId:body.requestId})};probeCount++;if(probeCount===2)return {ok:true,status:202,json:async()=>({requestId:body.requestId})};return {ok:true,status:202,json:async()=>({requestId:body.requestId,id:body.id,kind:'model-probe',status:'outcome_unknown',model:'m',protocol:'responses',networkMode:'direct',diagnostics:[{requestId:'local',attempt:1,host:'api.example',status:'failed',secret:'LEAK'}]})};}if(url.includes('requestId='))return {ok:true,status:200,json:async()=>({requestId:'a'.repeat(32),id:'p1',kind:'model-probe',status:'outcome_unknown',diagnostics:[]})};return {ok:true,status:200,json:async()=>({revision:'r1',default:'none',items:[{id:'p1',name:'Primary',provider:'responses',model:'m'}]})};},HubLiveUI:{patch:(node,html)=>{node.innerHTML=html;}},HubI18n:{locale:'en',t:key=>key,onChange:fn=>{context.lang=fn;}},document:{querySelector:()=>root,activeElement:null,documentElement:{dataset:{hubLocale:'en'}}},setTimeout:()=>1};context.window=context;vm.createContext(context);vm.runInContext(source,context);context.HubAgentProvidersUI.afterRender(root);await settle();assert.equal(calls.filter(c=>!c.opt.method&&c.url==='/api/v1/agent-providers').length,1,'mount loads catalog once');await root.emit('click',new Button({'data-provider-edit':'p1'}));root.fields.networkMode.value='system';root.emit('change',root.fields.networkMode);root.emit('submit',root.querySelector('[data-provider-form]'));await settle();const save=JSON.parse(calls.find(c=>c.opt.method==='POST').opt.body);assert.equal(save.networkMode,'system','edited system policy is saved');await root.emit('click',new Button({'data-provider-probe':'p1'}));assert.equal(calls.filter(c=>c.opt.method==='POST').length,1,'opening probe only confirms intent');assert(root.html.includes('may incur provider charges'));await root.emit('click',new Button({'data-provider-probe-confirm':'1'}));await settle();assert.equal(calls.filter(c=>c.opt.method==='POST').length,2,'confirm sends one probe');const probe=JSON.parse(calls.filter(c=>c.opt.method==='POST').at(-1).opt.body);assert.deepEqual({action:probe.action,id:probe.id,expected:probe.expected,requestId:probe.requestId},{action:'probe',id:'p1',expected:'r1',requestId:'a'.repeat(32)});await root.emit('click',new Button({'data-provider-probe-refresh':'1'}));await settle();assert.equal(calls.filter(c=>c.opt.method==='POST').length,2,'unknown probe is never auto-repeated');assert.equal(calls.filter(c=>c.url.includes('requestId=')).length,1,'refresh reads durable receipt with GET');assert(!root.html.includes('LEAK'),'unsafe transport fields are not rendered');await root.emit('click',new Button({'data-provider-probe-new':'1'}));await root.emit('click',new Button({'data-provider-probe-confirm':'1'}));await settle();assert.equal(calls.filter(c=>c.opt.method==='POST').length,3,'malformed ack still sends once');assert(root.html.includes('data-provider-probe-refresh'),'malformed ack requires receipt refresh');}
main().catch(error=>{console.error(error);process.exitCode=1;});
'''

LIMIT_HARNESS_BASE = PROBE_HARNESS.replace("status:'outcome_unknown',model:'m',protocol:'responses',networkMode:'direct',diagnostics:[{requestId:'local',attempt:1,host:'api.example',status:'failed',secret:'LEAK'}]", "status:'failed',model:'m',protocol:'responses',networkMode:'direct',diagnostics:[{requestId:'local',attempt:1,host:'api.example',status:'failed',httpStatus:200,category:'quota',providerErrorCode:'subscription_sharing_usage_limit_exceeded'}]")
LIMIT_HARNESS_LIMIT = LIMIT_HARNESS_BASE.replace("await root.emit('click',new Button({'data-provider-probe-confirm':'1'}));await settle();assert.equal(calls.filter(c=>c.opt.method==='POST').length,2,'confirm sends one probe');", "await root.emit('click',new Button({'data-provider-probe-confirm':'1'}));await settle();assert.equal(calls.filter(c=>c.opt.method==='POST').length,2,'confirm sends one probe');assert(root.html.includes('subscription model-use limit was reached'),'subscription limit guidance');")
LIMIT_HARNESS_UNAVAILABLE = LIMIT_HARNESS_BASE.replace('subscription_sharing_usage_limit_exceeded','subscription_sharing_usage_unavailable').replace("await root.emit('click',new Button({'data-provider-probe-confirm':'1'}));await settle();assert.equal(calls.filter(c=>c.opt.method==='POST').length,2,'confirm sends one probe');", "await root.emit('click',new Button({'data-provider-probe-confirm':'1'}));await settle();assert.equal(calls.filter(c=>c.opt.method==='POST').length,2,'confirm sends one probe');assert(root.html.includes('subscription model access is currently unavailable'),'subscription unavailable guidance');")

CHATGPT_HARNESS = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');const source=fs.readFileSync(process.argv[1],'utf8');
class Button {constructor(attrs={}){this.attrs=attrs;}getAttribute(k){return this.attrs[k]||null;}closest(s){const k=s.slice(1,-1);return Object.prototype.hasOwnProperty.call(this.attrs,k)?this:null;}}
class Root {constructor(){this.listeners={};this.isConnected=true;this.html='';this.fields={};this.dialog=null;}addEventListener(t,f){(this.listeners[t]??=[]).push(f);}set innerHTML(v){this.html=v;this.dialog=v.includes('data-provider-dialog')?{open:false,showModal(){this.open=true;}}:null;this.fields={};for(const m of v.matchAll(/<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"/g))this.fields[m[1]]={name:m[1],value:m[2],getAttribute:k=>k==='name'?m[1]:null};for(const m of v.matchAll(/<select[^>]*name="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)){const s=m[2].match(/<option value="([^"]+)"[^>]*selected/);this.fields[m[1]]={name:m[1],value:s?s[1]:'',getAttribute:k=>k==='name'?m[1]:null};}}querySelector(s){if(s==='[data-provider-dialog]')return this.dialog;if(s==='[data-provider-form]')return {matches:x=>x==='[data-provider-form]'};const m=s.match(/\[name="([^"]+)"\]/);return m?this.fields[m[1]]:null;}emit(t,target){for(const f of this.listeners[t]||[])f({target,preventDefault(){}});}}
const settle=async()=>{for(let i=0;i<64;i++)await Promise.resolve();};
async function main(){let attemptReads=0;const root=new Root(),calls=[],opened=[],timers=[],context={console,crypto:{randomUUID:()=> 'c'.repeat(32)},open:url=>{opened.push(url);return {opener:{},location:{replace:path=>opened.push(path)},close(){}};},setTimeout:f=>{timers.push(f);return timers.length;},clearTimeout(){},fetch:async(url,opt={})=>{calls.push({url,opt});if(opt.method==='POST'){const body=JSON.parse(opt.body);if(body.action==='start')return {ok:true,status:202,json:async()=>({attemptId:'attempt-1',status:'pending',authorizePath:'/auth/chatgpt/authorize?attemptId=attempt-1'})};if(body.action==='cancel')return {ok:true,status:200,json:async()=>({attemptId:body.attemptId,status:'cancelled'})};if(body.action==='models')return {ok:true,status:200,json:async()=>({ok:true})};if(body.action==='logout')return {ok:true,status:200,json:async()=>({ok:true,revocationConfirmed:false})};if(body.action==='save-chatgpt')return {ok:true,status:200,json:async()=>({saved:true,id:body.id||'d'.repeat(32),requestId:body.requestId})};}if(url.includes('attemptId=')){attemptReads++;return {ok:true,status:200,json:async()=>attemptReads===1?{attemptId:'attempt-1',status:'completed',accountId:'acct-2'}:{attemptId:'attempt-1',status:'pending',accountId:'acct-2'}};}if(url.startsWith('/api/chatgpt-auth'))return {ok:true,status:200,json:async()=>({accounts:[{id:'acct-1',label:'Work',email:'same@example.test',status:'plan_disabled',planUsageEnabled:false,models:[]},{id:'acct-2',label:'Personal',email:'same@example.test',status:'connected',planUsageEnabled:true,models:[{slug:'o4-mini',displayName:'o4-mini'}]}]})};return {ok:true,status:200,json:async()=>({revision:'r1',default:'none',items:[]})};},HubLiveUI:{patch:(n,h)=>{n.innerHTML=h;}},HubI18n:{locale:'en',t:k=>k,onChange:fn=>{context.lang=fn;}},document:{querySelector:()=>root,activeElement:null,documentElement:{dataset:{hubLocale:'en'}}}};context.window=context;vm.createContext(context);vm.runInContext(source,context);context.HubAgentProvidersUI.afterRender(root);await settle();assert(root.html.includes('data-chatgpt-new'),'ChatGPT section has sign-in CTA');assert(root.html.includes('API-key connections'),'API section is rendered separately');await root.emit('click',new Button({'data-chatgpt-new':'1'}));assert(root.html.includes('Work'));assert(root.html.includes('Personal'));assert(root.html.includes('Manage model access'),'plan-disabled account offers management link');assert(!root.html.includes('name="apiKey"'),'OAuth form has no API key field');await settle();root.fields.accountId.value='';root.emit('change',root.fields.accountId);await root.emit('click',new Button({'data-chatgpt-start':'1'}));await settle();assert.equal(opened[0],'about:blank');assert.equal(opened[1],'/auth/chatgpt/authorize?attemptId=attempt-1');assert(root.html.includes('data-chatgpt-save'),'completed login offers save');await root.emit('click',new Button({'data-chatgpt-save':'1'}));await settle();const saved=JSON.parse(calls.find(c=>c.opt?.method==='POST'&&JSON.parse(c.opt.body).action==='save-chatgpt').opt.body);assert.deepEqual({action:saved.action,accountId:saved.accountId,model:saved.model,networkMode:saved.networkMode},{action:'save-chatgpt',accountId:'acct-2',model:'o4-mini',networkMode:'direct'});await root.emit('click',new Button({'data-chatgpt-new':'1'}));await settle();root.fields.accountId.value='';root.emit('change',root.fields.accountId);await root.emit('click',new Button({'data-chatgpt-start':'1'}));await settle();assert(root.html.includes('data-chatgpt-cancel'));assert(!root.html.includes('data-chatgpt-cancel disabled'),'pending cancel remains enabled');await root.emit('click',new Button({'data-chatgpt-cancel':'1'}));await settle();assert(calls.some(c=>c.opt?.method==='POST'&&JSON.parse(c.opt.body).action==='cancel'));await root.emit('click',new Button({'data-chatgpt-models':'acct-2'}));await settle();await root.emit('click',new Button({'data-chatgpt-logout':'acct-2'}));await settle();assert(calls.some(c=>c.opt?.method==='POST'&&JSON.parse(c.opt.body).action==='models'));assert(calls.some(c=>c.opt?.method==='POST'&&JSON.parse(c.opt.body).action==='logout'));assert(root.html.includes('remote token revocation was not confirmed'),'unconfirmed logout warning');}
main().catch(error=>{console.error(error);process.exitCode=1;});
'''


AVAILABILITY_HARNESS = PROBE_HARNESS.split('async function main(){',1)[0] + r'''
async function main(){
  const cases=[
    ['credit_balance_exhausted','insufficient_quota','quota','no credits remaining'],
    ['project_spend_limit_exceeded','insufficient_quota','quota','project reached its spend limit'],
    ['organization_spend_limit_exceeded','insufficient_quota','quota','organization reached its spend limit'],
    ['organization_usage_limit_exceeded','insufficient_quota','quota','usage limit assigned'],
    ['insufficient_quota','insufficient_quota','quota','insufficient API quota'],
    ['rate_limit_exceeded','tokens','rate_limit','limited the request rate'],
    ['slow_down','rate_limit_error','rate_limit','limited the request rate'],
    [undefined,undefined,'rate_limit','does not identify the cause']
  ];
  for(const [code,type,category,expected] of cases){
    const root=new Root(),calls=[];let copied='';
    const receipt={requestId:'c'.repeat(32),id:'p1',kind:'model-probe',status:'failed',model:'m',authentication:{method:'api_key',quotaSource:'provider_api'},error:{code:'provider_http_error'},diagnostics:[{httpStatus:429,category,providerErrorCode:code,providerErrorType:type,message:'PRIVATE-BODY'}]};
    const item={id:'p1',name:'Example service',provider:'responses',model:'m',availability:{status:'quota',requestId:receipt.requestId,checkedAt:1234}};
    const context={console,crypto:{randomUUID:()=> 'd'.repeat(32)},navigator:{clipboard:{writeText:async value=>{copied=value;}}},fetch:async(url,opt={})=>{calls.push({url,opt});assert.notEqual(opt.method,'POST','viewing saved checks must not call the model');return {ok:true,status:200,json:async()=>url.includes('requestId=')?receipt:{revision:'r1',default:'p1',items:[item]}};},HubLiveUI:{patch:(node,html)=>{node.innerHTML=html;}},HubI18n:{locale:'en',t:key=>key,onChange:fn=>{context.lang=fn;}},document:{querySelector:()=>root,activeElement:null,documentElement:{dataset:{hubLocale:'en'}}},setTimeout:()=>1};
    context.window=context;vm.createContext(context);vm.runInContext(source,context);context.HubAgentProvidersUI.afterRender(root);await settle();
    assert(root.html.includes('API key access'));assert(root.html.includes('Quota or financial limit exhausted'));assert(root.html.includes('data-provider-check'));
    root.emit('click',new Button({'data-provider-probe':'p1'}));await settle();
    assert.equal(calls.filter(c=>c.url.includes('requestId=')).length,1);assert(root.html.includes(expected),expected);assert(!root.html.includes('PRIVATE-BODY'));
    root.emit('click',new Button({'data-provider-probe-copy':'1'}));await settle();
    const details=JSON.parse(copied);assert.equal(details.authentication.quotaSource,'provider_api');if(code)assert.equal(details.diagnostics[0].providerErrorCode,code);assert(!copied.includes('PRIVATE-BODY'));
    context.HubI18n.locale='ru';context.lang();assert(root.html.includes('Проверка завершилась ошибкой'));
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
'''


CHATGPT_SAVED_HARNESS = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');const source=fs.readFileSync(process.argv[1],'utf8');
class Button{constructor(a={}){this.a=a;}getAttribute(k){return this.a[k]||null;}closest(s){return Object.prototype.hasOwnProperty.call(this.a,s.slice(1,-1))?this:null;}}
class Root{constructor(){this.listeners={};this.isConnected=true;this.html='';this.fields={};this.dialog=null;}addEventListener(t,f){(this.listeners[t]??=[]).push(f);}set innerHTML(v){this.html=v;this.dialog=v.includes('data-provider-dialog')?{open:false,showModal(){this.open=true;}}:null;this.fields={};for(const m of v.matchAll(/<(?:input|select)[^>]*name="([^"]+)"[^>]*?(?:value="([^"]*)")?/g))this.fields[m[1]]={name:m[1],value:m[2]||'',getAttribute:k=>k==='name'?m[1]:null};}querySelector(s){if(s==='[data-provider-dialog]')return this.dialog;const m=s.match(/\[name="([^"]+)"\]/);return m?this.fields[m[1]]:null;}emit(t,x){for(const f of this.listeners[t]||[])f({target:x,preventDefault(){}});}}
const settle=async()=>{for(let i=0;i<64;i++)await Promise.resolve();};
async function main(){let modelsReady=false,modelCalls=0;const root=new Root(),calls=[],ctx={console,crypto:{randomUUID:()=> 'f'.repeat(32)},fetch:async(url,opt={})=>{calls.push({url,opt});if(opt.method==='POST'){const b=JSON.parse(opt.body);if(b.action==='models'){modelCalls++;modelsReady=true;return {ok:true,json:async()=>({ok:true})};}if(b.action==='probe')return {ok:true,json:async()=>({requestId:b.requestId,id:'oauth1',kind:'model-probe',status:'running',model:'m',protocol:'responses',diagnostics:[]})};if(b.action==='delete')return {ok:true,json:async()=>({saved:true,id:'oauth1',requestId:b.requestId})};if(b.action==='save-chatgpt')return {ok:true,json:async()=>({saved:true,id:'new',requestId:b.requestId})};}if(url==='/api/chatgpt-auth')return {ok:true,json:async()=>({accounts:[{id:'acct1',label:'Work',email:'same@test',status:'connected',planUsageEnabled:true,models:modelsReady?[{slug:'m',displayName:'Model'}]:[],modelsError:modelsReady?null:'chatgpt_network_error',modelsDiagnostic:{host:'auth.openai.com',secret:'PRIVATE'}}]})};return {ok:true,json:async()=>({revision:'r1',default:'api1',items:[{id:'api1',name:'API',provider:'responses',model:'api-model'},{id:'oauth1',name:'ChatGPT',provider:'responses',model:'m',authentication:{method:'chatgpt_oauth',accountId:'acct1'}}]})};},HubLiveUI:{patch:(n,h)=>n.innerHTML=h},HubI18n:{locale:'en',t:k=>k,onChange:()=>{}},document:{querySelector:()=>root,activeElement:null,documentElement:{dataset:{hubLocale:'en'}}}};ctx.window=ctx;vm.createContext(ctx);vm.runInContext(source,ctx);ctx.HubAgentProvidersUI.afterRender(root);await settle();assert(root.html.includes('data-provider-probe="oauth1"'));assert(root.html.includes('data-provider-edit="oauth1"'));assert(root.html.includes('data-provider-delete="oauth1"'));assert.equal(calls.filter(c=>c.opt?.method==='POST'&&JSON.parse(c.opt.body).action==='models').length,0,'mount does not refresh models');await root.emit('click',new Button({'data-provider-edit':'oauth1'}));assert(root.html.includes('ChatGPT'));await root.emit('click',new Button({'data-provider-close':'1'}));await root.emit('click',new Button({'data-provider-probe':'oauth1'}));assert(root.html.includes('Plan limits may apply'));await root.emit('click',new Button({'data-provider-probe-confirm':'1'}));await settle();assert(calls.some(c=>c.opt?.method==='POST'&&JSON.parse(c.opt.body).action==='probe'));await root.emit('click',new Button({'data-provider-close':'1'}));await root.emit('click',new Button({'data-provider-new':'1'}));await root.emit('click',new Button({'data-chatgpt-new':'1'}));root.fields.accountId.value='acct1';await root.emit('change',root.fields.accountId);assert(root.html.includes('The model list could not be refreshed'));assert(!root.html.includes('PRIVATE'));await root.emit('click',new Button({'data-chatgpt-models':'acct1'}));await settle();assert.equal(modelCalls,1);assert(root.html.includes('value="m" selected'));assert(root.html.includes('data-chatgpt-save'));await root.emit('click',new Button({'data-provider-close':'1'}));await root.emit('click',new Button({'data-provider-delete':'oauth1'}));assert(root.html.includes('ChatGPT account will remain in saved accounts')); await root.emit('click',new Button({'data-provider-confirm-delete':'1'}));await settle();assert(calls.some(c=>c.opt?.method==='POST'&&JSON.parse(c.opt.body).action==='delete'));}
main().catch(e=>{console.error(e);process.exitCode=1;});
'''

TIMEOUT_HARNESS = PROBE_HARNESS.split('async function main(){',1)[0] + r'''
async function main(){
  for(const afterHeaders of [false,true]){
    const root=new Root(),calls=[];let copied='';
    const diagnostic={category:'timeout',phase:afterHeaders?'read':'unknown',timeoutMs:60000,outcomeUnknown:true,secret:'PRIVATE'};
    if(afterHeaders)diagnostic.httpStatus=200;
    const receipt={requestId:'c'.repeat(32),id:'p1',kind:'model-probe',status:'outcome_unknown',diagnostics:[diagnostic]};
    const context={console,navigator:{clipboard:{writeText:async value=>{copied=value;}}},fetch:async(url,opt={})=>{
      calls.push({url,opt});assert.notEqual(opt.method,'POST','saved timeout must never resend');
      return {ok:true,status:200,json:async()=>url.includes('requestId=')?receipt:{revision:'r1',default:'p1',items:[{id:'p1',name:'Example',model:'m',availability:{status:'outcome_unknown',requestId:receipt.requestId}}]}};
    },HubLiveUI:{patch:(node,html)=>{node.innerHTML=html;}},HubI18n:{locale:'en',t:key=>key,onChange:fn=>{context.lang=fn;}},document:{querySelector:()=>root,activeElement:null,documentElement:{dataset:{hubLocale:'en'}}}};
    context.window=context;vm.createContext(context);vm.runInContext(source,context);
    context.HubAgentProvidersUI.afterRender(root);await settle();
    root.emit('click',new Button({'data-provider-probe':'p1'}));await settle();
    assert(root.html.includes(afterHeaders?'reading did not finish':'cannot distinguish a connection delay'));
    assert(root.html.includes('Network inactivity timeout: 60 s.'));
    assert(root.html.includes('Hub never retries it automatically'));
    root.emit('click',new Button({'data-provider-probe-copy':'1'}));await settle();
    assert.equal(JSON.parse(copied).diagnostics[0].timeoutMs,60000);assert(!copied.includes('PRIVATE'));
    context.HubI18n.locale='ru';context.lang();assert(root.html.includes('Hub не повторяет его автоматически'));
    delete diagnostic.timeoutMs;
    root.emit('click',new Button({'data-provider-probe-refresh':'1'}));await settle();
    assert(!root.html.includes('Лимит ожидания одной сетевой операции:'),'legacy receipt has no invented timeout');
    assert.equal(calls.filter(c=>c.opt.method==='POST').length,0);
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
'''

FORMAT_HARNESS = PROBE_HARNESS.split('async function main(){',1)[0] + r'''
async function main(){
  for(const legacy of [false,true]){
    const root=new Root(),calls=[];let copied='';
    const diagnostic={category:'parse',phase:'parse',parseReason:'sse_content_type',httpStatus:200,outcomeUnknown:true,secret:'PRIVATE',rawBody:'PRIVATE'};
    if(!legacy)Object.assign(diagnostic,{responseMediaType:'text/html',responseContentEncoding:'identity',responseBodyKind:'html-like',responseBytes:123});
    const receipt={requestId:'d'.repeat(32),id:'p1',kind:'model-probe',status:'outcome_unknown',diagnostics:[diagnostic]};
    const context={console,navigator:{clipboard:{writeText:async value=>{copied=value;}}},fetch:async(url,opt={})=>{
      calls.push({url,opt});assert.notEqual(opt.method,'POST','reading a format error never resends');
      return {ok:true,status:200,json:async()=>url.includes('requestId=')?receipt:{revision:'r1',default:'p1',items:[{id:'p1',name:'Example',model:'m',availability:{status:'outcome_unknown',requestId:receipt.requestId}}]}};
    },HubLiveUI:{patch:(node,html)=>{node.innerHTML=html;}},HubI18n:{locale:'en',t:key=>key,onChange:fn=>{context.lang=fn;}},document:{querySelector:()=>root,activeElement:null,documentElement:{dataset:{hubLocale:'en'}}}};
    context.window=context;vm.createContext(context);vm.runInContext(source,context);
    context.HubAgentProvidersUI.afterRender(root);await settle();
    root.emit('click',new Button({'data-provider-probe':'p1'}));await settle();
    assert(root.html.includes('Even HTTP 200 does not confirm successful inference'));
    assert(root.html.includes(legacy?'did not record the actual response format':'Response media type: text/html. Body format hint: HTML-like.'));
    root.emit('click',new Button({'data-provider-probe-copy':'1'}));await settle();
    const safe=JSON.parse(copied).diagnostics[0];assert.equal(safe.parseReason,'sse_content_type');assert(!copied.includes('PRIVATE'));
    if(legacy)assert(!('responseMediaType' in safe));
    else{assert.equal(safe.responseMediaType,'text/html');assert.equal(safe.responseContentEncoding,'identity');assert.equal(safe.responseBodyKind,'html-like');assert.equal(safe.responseBytes,123);}
    context.HubI18n.locale='ru';context.lang();assert(root.html.includes('По одному этому признаку нельзя определить источник ошибки'));
    root.emit('click',new Button({'data-provider-probe-refresh':'1'}));await settle();
    assert.equal(calls.filter(c=>c.opt.method==='POST').length,0);
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
'''

TLS_HARNESS = PROBE_HARNESS.split('async function main(){',1)[0] + r'''
async function main(){
  for(const kind of ['unexpected_eof','certificate_verification','protocol_mismatch','read','legacy']){
    const root=new Root(),calls=[];let copied='';
    const uncertain=!['certificate_verification','legacy'].includes(kind);
    const diagnostic={category:'tls',phase:kind==='read'?'read':uncertain?'unknown':'tls',networkMode:'system',outcomeUnknown:uncertain,secret:'PRIVATE',verify_message:'PRIVATE'};
    if(kind!=='legacy')diagnostic.tlsReason=kind==='read'?'unexpected_eof':kind;
    if(kind==='certificate_verification')diagnostic.tlsVerifyCode=20;
    if(kind==='read')diagnostic.httpStatus=200;
    const receipt={requestId:'e'.repeat(32),id:'p1',kind:'model-probe',status:uncertain?'outcome_unknown':'failed',diagnostics:[diagnostic]};
    const context={console,navigator:{clipboard:{writeText:async value=>{copied=value;}}},fetch:async(url,opt={})=>{
      calls.push({url,opt});assert.notEqual(opt.method,'POST','saved TLS receipts never resend');
      return {ok:true,status:200,json:async()=>url.includes('requestId=')?receipt:{revision:'r1',default:'p1',items:[{id:'p1',name:'Example',model:'m',availability:{requestId:receipt.requestId}}]}};
    },HubLiveUI:{patch:(node,html)=>{node.innerHTML=html;}},HubI18n:{locale:'en',t:key=>key,onChange:fn=>{context.lang=fn;}},document:{querySelector:()=>root,activeElement:null,documentElement:{dataset:{hubLocale:'en'}}}};
    context.window=context;vm.createContext(context);vm.runInContext(source,context);
    context.HubAgentProvidersUI.afterRender(root);await settle();
    root.emit('click',new Button({'data-provider-probe':'p1'}));await settle();
    const expected=kind==='certificate_verification'?'certificate could not be verified':kind==='protocol_mismatch'?'could not be negotiated':kind==='legacy'?'does not identify the specific cause':'closed abruptly';
    assert(root.html.includes(expected));assert(root.html.includes('label alone does not confirm that a proxy exists'));
    assert.equal(root.html.includes('Hub never retries it automatically'),uncertain);
    if(kind==='read')assert(root.html.includes('failure occurred while reading it'));
    root.emit('click',new Button({'data-provider-probe-copy':'1'}));await settle();
    const safe=JSON.parse(copied).diagnostics[0];assert(!copied.includes('PRIVATE'));
    if(kind==='legacy')assert(!('tlsReason' in safe));else assert.equal(safe.tlsReason,diagnostic.tlsReason);
    if(kind==='certificate_verification')assert.equal(safe.tlsVerifyCode,20);
    context.HubI18n.locale='ru';context.lang();assert(root.html.includes('сама надпись не подтверждает наличие прокси'));
    root.emit('click',new Button({'data-provider-probe-refresh':'1'}));await settle();
    assert.equal(calls.filter(c=>c.opt.method==='POST').length,0);
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
'''

OAUTH_TIMEOUT_HARNESS = TIMEOUT_HARNESS.replace(
    "category:'timeout',phase:", "operation:'oauth',oauthAction:'token_refresh',category:'timeout',phase:"
).replace(
    "availability:{status:'outcome_unknown',requestId:receipt.requestId}", "availability:{status:'sign_in_required',requestId:receipt.requestId}"
).replace(
    "status:'outcome_unknown',diagnostics:[diagnostic]", "status:'failed',authentication:{method:'chatgpt_oauth',accountId:'acct1'},diagnostics:[diagnostic]"
).replace(
    "assert(root.html.includes('Hub never retries it automatically'));",
    "assert(root.html.includes('No model request was sent.'));assert(root.html.includes('sign in to ChatGPT again'));assert(root.html.includes('Hub never repeats the refresh automatically'));"
).replace(
    "assert(root.html.includes('Hub не повторяет его автоматически'));",
    "assert(root.html.includes('Запрос к модели не отправлен.'));assert(root.html.includes('Hub не повторяет обновление автоматически'));"
).replace(
    "assert.equal(JSON.parse(copied).diagnostics[0].timeoutMs,60000);",
    "assert.equal(JSON.parse(copied).diagnostics[0].timeoutMs,60000);assert.equal(JSON.parse(copied).diagnostics[0].oauthAction,'token_refresh');"
)

OAUTH_IDENTITY_HARNESS = PROBE_HARNESS.split('async function main(){',1)[0] + r'''
async function main(){
  const root=new Root(),calls=[];
  const receipt={requestId:'f'.repeat(32),id:'p1',kind:'model-probe',status:'failed',
    authentication:{method:'chatgpt_oauth',accountId:'acct1'},diagnostics:[],error:{code:'chatgpt_identity_invalid'}};
  const context={console,fetch:async(url,opt={})=>{calls.push({url,opt});assert.notEqual(opt.method,'POST');return {ok:true,status:200,json:async()=>url.includes('requestId=')?receipt:{revision:'r1',default:'p1',items:[{id:'p1',name:'Example',model:'m',availability:{status:'sign_in_required',requestId:receipt.requestId}}]}};},
    HubLiveUI:{patch:(node,html)=>{node.innerHTML=html;}},HubI18n:{locale:'en',t:key=>key,onChange:fn=>{context.lang=fn;}},document:{querySelector:()=>root,activeElement:null,documentElement:{dataset:{hubLocale:'en'}}}};
  context.window=context;vm.createContext(context);vm.runInContext(source,context);context.HubAgentProvidersUI.afterRender(root);await settle();
  root.emit('click',new Button({'data-provider-probe':'p1'}));await settle();
  assert(root.html.includes('No model request was sent.'));assert(root.html.includes('failed account verification'));assert(root.html.includes('Open Edit'));assert(root.html.includes('Reconnecting MCP or the Codex adapter does not repair model authorization'));
  context.HubI18n.locale='ru';context.lang();assert(root.html.includes('Ответ авторизации ChatGPT не прошёл проверку'));assert(root.html.includes('войдите снова'));
  root.emit('click',new Button({'data-provider-probe-refresh':'1'}));await settle();assert.equal(calls.filter(c=>c.opt.method==='POST').length,0);
}
main().catch(error=>{console.error(error);process.exitCode=1;});
'''

OAUTH_PENDING_HARNESS = PROBE_HARNESS.split('async function main(){',1)[0] + r'''
async function main(){
  const root=new Root(),calls=[];let copied='';
  const receipt={requestId:'f'.repeat(32),id:'p1',kind:'model-probe',status:'failed',
    authentication:{method:'chatgpt_oauth',accountId:'acct1'},error:{code:'chatgpt_refresh_pending'},
    diagnostics:[{operation:'oauth',oauthAction:'identity_validation',identityReason:'signing_key'}]};
  const context={console,navigator:{clipboard:{writeText:async text=>{copied=text;}}},fetch:async(url,opt={})=>{calls.push({url,opt});assert.notEqual(opt.method,'POST');return {ok:true,status:200,json:async()=>url.includes('requestId=')?receipt:{revision:'r1',default:'p1',items:[{id:'p1',name:'Example',model:'m',availability:{status:'auth_pending',requestId:receipt.requestId}}]}};},
    HubLiveUI:{patch:(node,html)=>{node.innerHTML=html;}},HubI18n:{locale:'en',t:key=>key,onChange:fn=>{context.lang=fn;}},document:{querySelector:()=>root,activeElement:null,documentElement:{dataset:{hubLocale:'en'}}}};
  context.window=context;vm.createContext(context);vm.runInContext(source,context);context.HubAgentProvidersUI.afterRender(root);await settle();
  assert(root.html.includes('ChatGPT authorization needs verification'));
  root.emit('click',new Button({'data-provider-probe':'p1'}));await settle();
  assert(root.html.includes('retained the received authorization response'));assert(root.html.includes('without repeating the token exchange'));assert(!root.html.includes('Open Edit for this connection and sign in'));
  root.emit('click',new Button({'data-provider-probe-copy':'1'}));await settle();assert.equal(JSON.parse(copied).diagnostics[0].identityReason,'signing_key');
  context.HubI18n.locale='ru';context.lang();assert(root.html.includes('Hub сохранил полученный ответ авторизации'));assert(root.html.includes('без повторного обмена токенов'));
  assert.equal(calls.filter(c=>c.opt.method==='POST').length,0);
}
main().catch(error=>{console.error(error);process.exitCode=1;});
'''

OAUTH_EDITOR_HARNESS = PROBE_HARNESS.split('async function main(){',1)[0] + r'''
async function main(){
  for(const status of ['refresh_unknown','connected','refresh_pending','signed_out']){
    const root=new Root(),calls=[];
    const account={id:'acct1',label:'Example',status,planUsageEnabled:status==='connected',models:[{slug:'m',displayName:'Model'}]};
    const context={console,crypto:{randomUUID:()=> 'c'.repeat(32)},fetch:async(url,opt={})=>{
      calls.push({url,opt});
      if(opt.method==='POST'){assert.equal(JSON.parse(opt.body).action,'models');account.status='connected';account.planUsageEnabled=true;return {ok:true,status:200,json:async()=>({ok:true})};}
      return {ok:true,status:200,json:async()=>url==='/api/chatgpt-auth'?{accounts:[account]}:{revision:'r1',default:'p1',items:[{id:'p1',name:'Example',model:'m',authentication:{method:'chatgpt_oauth',accountId:'acct1'}}]}};
    },HubLiveUI:{patch:(node,html)=>{node.innerHTML=html;}},HubI18n:{locale:'en',t:key=>key,onChange:()=>{}},document:{querySelector:()=>root,activeElement:null,documentElement:{dataset:{hubLocale:'en'}}}};
    context.window=context;vm.createContext(context);vm.runInContext(source,context);context.HubAgentProvidersUI.afterRender(root);await settle();
    root.emit('click',new Button({'data-provider-edit':'p1'}));await settle();
    assert.equal(root.html.includes('data-chatgpt-save'),status==='connected');
    assert.equal(root.html.includes('data-chatgpt-start'),!['connected','refresh_pending'].includes(status));
    assert(root.html.includes('Authorization status'));
    assert(root.html.includes(status==='connected'?'You do not need to sign in again':status==='refresh_pending'?'sign-in is not verified yet':status==='signed_out'?'you have signed out in Hub':'working authorization is not confirmed'));
    assert(!root.html.includes('role="status"'),'editing must not fabricate a completed sign-in attempt');
    assert.equal(calls.filter(c=>c.opt.method==='POST').length,0);
    if(status==='refresh_pending'){
      assert(root.html.includes('Verify authorization'));
      root.emit('click',new Button({'data-chatgpt-models':'acct1'}));await settle();
      assert(root.html.includes('data-chatgpt-save'));
      assert(!root.html.includes('data-chatgpt-start'));
      assert.equal(calls.filter(c=>c.opt.method==='POST').length,1,'verification resumes without another sign-in');
    }
  }
}
main().catch(error=>{console.error(error);process.exitCode=1;});
'''

ACCOUNT_INTERACTION_HARNESS = PROBE_HARNESS.split('async function main(){',1)[0] + r'''
async function main(){
  let account={id:'acct1',label:'person@example.test',status:'connected',planUsageEnabled:true,models:[{slug:'m',displayName:'Model'}]};
  let items=[{id:'p1',name:'ChatGPT',model:'m',authentication:{method:'chatgpt_oauth',accountId:'acct1'}}];
  const root=new Root(),calls=[],sequence=[];
  const context={console,crypto:{randomUUID:()=> 'a'.repeat(32)},open:url=>{sequence.push('open:'+url);return {opener:{},location:{replace:path=>sequence.push('navigate:'+path)},close:()=>sequence.push('close')};},fetch:async(url,opt={})=>{
    if(opt.method==='POST'){
      const body=JSON.parse(opt.body);calls.push(body);sequence.push('post:'+body.action);
      if(body.action==='delete'){items=[];return {ok:true,json:async()=>({saved:true,id:'p1',requestId:body.requestId})};}
      if(body.action==='logout'){account={...account,status:'signed_out',planUsageEnabled:false};return {ok:true,json:async()=>({ok:true,revocationConfirmed:true})};}
      if(body.action==='forget'){account=null;return {ok:true,json:async()=>({accountId:'acct1',status:'forgotten'})};}
      if(body.action==='start')return {ok:true,json:async()=>({attemptId:'attempt-1',status:'pending',authorizePath:'/auth/chatgpt/authorize?attemptId=attempt-1'})};
    }
    return {ok:true,status:200,json:async()=>url.includes('attemptId=')?{attemptId:'attempt-1',status:'pending',accountId:'acct1'}:url==='/api/chatgpt-auth'?{accounts:account?[account]:[]}:{revision:'r1',default:items.length?'p1':'none',items}};
  },HubLiveUI:{patch:(node,html)=>{node.innerHTML=html;}},HubI18n:{locale:'en',t:key=>key,onChange:()=>{}},document:{querySelector:()=>root,activeElement:null,documentElement:{dataset:{hubLocale:'en'}}},setTimeout:()=>1};
  context.window=context;vm.createContext(context);vm.runInContext(source,context);context.HubAgentProvidersUI.afterRender(root);await settle();
  root.emit('click',new Button({'data-provider-delete':'p1'}));await settle();
  assert(root.html.includes('ChatGPT account will remain in saved accounts'));
  root.emit('click',new Button({'data-provider-confirm-delete':'1'}));await settle();
  assert.equal(calls.filter(c=>c.action==='logout').length,0,'deleting settings does not silently sign out');
  root.emit('click',new Button({'data-chatgpt-new':'1'}));await settle();
  assert(root.html.includes('person@example.test'),'saved account is explicitly shown after deleting connection');
  assert(!root.html.includes('data-chatgpt-connect'),'no misleading account-level sign-in selector');
  assert.equal((root.html.match(/data-chatgpt-start/g)||[]).length,0,'connected account is reused without a new login');assert(root.html.includes('data-chatgpt-save'));assert.equal(root.fields.accountId.value,'acct1');
  assert(root.html.includes('ChatGPT sign-in is stored separately'));
  assert.equal(root.fields.name.value,'ChatGPT','new connection does not inherit an old account label');
  root.emit('click',new Button({'data-chatgpt-forget':'acct1'}));await settle();
  assert(root.html.includes('Remove account from Hub?'));assert.equal(calls.filter(c=>c.action==='forget').length,0);
  root.emit('click',new Button({'data-chatgpt-forget-confirm':'1'}));await settle();
  assert.deepEqual(calls.map(c=>c.action),['delete','logout','forget']);
  assert(!root.html.includes('person@example.test'),'removed profile disappears without page reload');
  assert.equal(root.fields.accountId.value,'');assert(root.html.includes('Select an account first'));
  // Opening the same form re-reads state changed outside it, without reloading the page.
  root.emit('click',new Button({'data-provider-close':'1'}));account={id:'acct1',label:'updated@example.test',status:'signed_out',planUsageEnabled:false,models:[]};
  root.emit('click',new Button({'data-chatgpt-new':'1'}));await settle();
  assert(root.html.includes('updated@example.test'));
  root.fields.accountId.value='acct1';root.emit('change',root.fields.accountId);await settle();
  root.emit('click',new Button({'data-chatgpt-start':'1'}));await settle();
  assert(sequence.indexOf('open:about:blank')<sequence.indexOf('post:start'),'popup is reserved during the click, before awaiting API');
  assert(sequence.includes('navigate:/auth/chatgpt/authorize?attemptId=attempt-1'));
  assert.equal((root.html.match(/data-chatgpt-authorize/g)||[]).length,1,'one fallback authorization link');
  assert.equal(calls.filter(c=>c.action==='start').length,1);
}
main().catch(error=>{console.error(error);process.exitCode=1;});
'''

class AgentProvidersUiTest(unittest.TestCase):
    def test_tls_explanation_safe_subtypes_copy_and_legacy_without_resending(self):
        result = subprocess.run(['node', '-e', TLS_HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_format_error_explanation_safe_copy_and_legacy_receipts_without_resending(self):
        result = subprocess.run(['node', '-e', FORMAT_HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_account_removal_fresh_status_single_login_and_synchronous_popup(self):
        result = subprocess.run(['node', '-e', ACCOUNT_INTERACTION_HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_editor_requires_fresh_sign_in_after_unknown_refresh_without_fake_completion(self):
        result = subprocess.run(['node', '-e', OAUTH_EDITOR_HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_identity_failure_without_transport_details_explains_sign_in_and_never_resends(self):
        result = subprocess.run(['node', '-e', OAUTH_IDENTITY_HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_received_refresh_help_distinguishes_verification_retry_from_sign_in(self):
        result = subprocess.run(['node', '-e', OAUTH_PENDING_HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_oauth_refresh_timeout_explains_no_inference_and_sign_in_without_repeating(self):
        result = subprocess.run(['node', '-e', OAUTH_TIMEOUT_HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_timeout_explanation_safe_copy_and_legacy_receipts_without_resending(self):
        result = subprocess.run(['node', '-e', TIMEOUT_HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_saved_chatgpt_row_actions_model_retry_and_safe_diagnostics(self):
        result = subprocess.run(['node', '-e', CHATGPT_SAVED_HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
    def test_agent_provider_widget_behavior(self):
        result = subprocess.run(['node', '-e', HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_probe_confirmation_network_policy_and_unknown_receipt_contract(self):
        result = subprocess.run(['node', '-e', PROBE_HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_chatgpt_sign_in_accounts_models_and_cancel_contract(self):
        result = subprocess.run(['node', '-e', CHATGPT_HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_chatgpt_subscription_quota_limit_guidance(self):
        result = subprocess.run(['node', '-e', LIMIT_HARNESS_LIMIT, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_chatgpt_subscription_unavailable_guidance(self):
        result = subprocess.run(['node', '-e', LIMIT_HARNESS_UNAVAILABLE, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_persistent_access_status_and_specific_limit_reasons_without_model_calls(self):
        result = subprocess.run(['node', '-e', AVAILABILITY_HARNESS, str(WEB)], capture_output=True, text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
