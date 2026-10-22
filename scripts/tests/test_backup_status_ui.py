"""The shared operation banner survives navigation, reload and connection loss."""
from pathlib import Path
import shutil
import subprocess
import unittest


WEB = Path(__file__).resolve().parents[2] / "tools/project-portal/web"


HARNESS = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const web=process.argv[1],responses=[],timers=[],stored=new Map();
const row={id:'snapshot',requestId:'snapshot-request',action:'create',status:'running',phase:'snapshot',createdAt:'2026-10-11T00:00:00Z',elapsed:12,origin:{section:'backups',project:'project with spaces'},progress:{completed:40,total:100,unit:'bytes'}};
const waiting={id:'waiting',requestId:'waiting-request',action:'apply-import',status:'queued',phase:'waiting',waitingFor:'snapshot',origin:{section:'data',project:'source-project'}};
function makeContext(){
 const listeners={},banner={hidden:true,dataset:{},innerHTML:''},mutation={disabled:false,dataset:{},closest:()=>null},detailTargets=[];
 const document={querySelector:selector=>selector==='#backup-status'?banner:null,querySelectorAll:selector=>selector==='[data-operation-details]'?detailTargets:[mutation],addEventListener:(name,fn)=>(listeners[name]??=[]).push(fn)};
 const ctx={console,Map,Set,Date,location:{search:'?project=another',hash:'#settings'},document,
  sessionStorage:{getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value)},
  setTimeout:fn=>{timers.push(fn);return timers.length},clearTimeout(){},
  fetch:async()=>{const value=responses.shift();if(value instanceof Error)throw value;return {ok:true,json:async()=>value || {writesPaused:false,operations:[]}}},
  HubI18n:{locale:'en',t:(key,fallback)=>fallback || key}};
 ctx.window=ctx;ctx.globalThis=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(web+'/backup-status.js','utf8'),ctx);
 return {ctx,listeners,banner,mutation,detailTargets};
}
(async()=>{
 responses.push({writesPaused:true,operations:[row,waiting]});
 const h=makeContext();await h.ctx.backupStatus.refresh();
 assert.equal(h.banner.hidden,false);assert.match(h.banner.innerHTML,/Changes are temporarily paused/);assert.match(h.banner.innerHTML,/&lt;0\.1 \/ &lt;0\.1 KB/);assert.match(h.banner.innerHTML,/12 s/);
 assert.match(h.banner.innerHTML,/\?project=project%20with%20spaces#projects\/backups\/operation\/snapshot/);assert.match(h.banner.innerHTML,/Waiting for another operation/);assert.equal(h.mutation.disabled,true);
 let prevented=false,stopped=false;
 const form={closest:()=>null,getAttribute:()=>null};const event={target:form,preventDefault:()=>prevented=true,stopImmediatePropagation:()=>stopped=true};
 h.listeners.submit[0](event);assert.equal(prevented,true);assert.equal(stopped,true);
 prevented=false;form.getAttribute=()=>'get';h.listeners.submit[0](event);assert.equal(prevented,false);
 const body={action:'inspect-folder',requestId:'same-request',origin:{section:'data',project:'chosen'}};
 h.ctx.backupStatus.begin(body);assert.match(h.banner.innerHTML,/Sending request/);assert.ok(stored.get('project-hub-operation-requests').includes('same-request'));
 h.ctx.backupStatus.uncertain(body);assert.match(h.banner.innerHTML,/Checking status/);
 responses.push(Error('connection lost'));await h.ctx.backupStatus.refresh();assert.equal(h.ctx.backupStatus.isPaused(),true);assert.equal(h.mutation.disabled,true);assert.match(h.banner.innerHTML,/Connection lost/);
 responses.push({writesPaused:true,operations:[{...row,id:'still-running'}, {id:'inspect-result',requestId:'same-request',action:'inspect-folder',status:'succeeded',phase:'complete',origin:body.origin,result:{copyId:'prepared-source',sourcePath:'C:/Earlier data'}}]});
 await h.ctx.backupStatus.refresh();assert.equal(h.ctx.backupStatus.isPaused(),true);assert.doesNotMatch(h.banner.innerHTML,/Connection lost/);assert.equal(h.ctx.backupStatus.operations().filter(item=>item.requestId==='same-request').length,1);
 const details=h.ctx.backupStatus.details('inspect-result');assert.match(details,/prepared-source/);assert.match(details,/earlier|Earlier/);assert.match(details,/available in operation history/);
 let focused=0,scrolled=0;h.detailTargets.push({dataset:{operationDetails:'inspect-result'},closest:()=>null,focus:()=>focused++,scrollIntoView:()=>scrolled++});
 h.ctx.location.hash='#projects/data/operation/inspect-result';h.ctx.backupStatus.afterRender();h.ctx.backupStatus.afterRender();assert.equal(focused,1);assert.equal(scrolled,1);
 responses.push({writesPaused:false,operations:[{...row,status:'failed',finishedAt:new Date().toISOString(),error:'Destination is occupied',recovery:'restored'},{...waiting,status:'succeeded',phase:'complete',finishedAt:new Date().toISOString()}]});await h.ctx.backupStatus.refresh();
 assert.equal(h.ctx.backupStatus.isPaused(),false);assert.equal(h.mutation.disabled,false);assert.match(h.banner.innerHTML,/Destination is occupied/);assert.match(h.ctx.backupStatus.details('snapshot'),/Recovery state: restored/);
 const old={...row,status:'succeeded',finishedAt:new Date(Date.now()-60000).toISOString()};responses.push({writesPaused:false,operations:[old,{...waiting,status:'succeeded',phase:'complete',finishedAt:old.finishedAt}]});await h.ctx.backupStatus.refresh();
 assert.equal(h.banner.hidden,true,'old completed operations belong in history');assert.match(h.ctx.backupStatus.details('snapshot'),/available in operation history/);
 const blocked={...row,id:'recovery',status:'interrupted',blocking:true,finishedAt:old.finishedAt,rollback:'failed',error:'Recovery required'};
 responses.push({writesPaused:true,operations:[blocked]});await h.ctx.backupStatus.refresh();
 assert.equal(h.banner.hidden,false);assert.match(h.banner.innerHTML,/Recovery required/);assert.match(h.banner.innerHTML,/operation\/recovery/);
 assert.match(h.ctx.backupStatus.operationLink({id:'project-update',origin:{section:'projects',project:'example'}}),/#projects\/projects\/operation\/project-update/);
 // A refresh of the page obtains the same operation from the server.
 responses.push({writesPaused:true,operations:[row]});const reloaded=makeContext();await reloaded.ctx.backupStatus.refresh();assert.match(reloaded.banner.innerHTML,/snapshot/);assert.equal(reloaded.ctx.backupStatus.isPaused(),true);
 assert.ok(timers.length>0);
})().catch(error=>{console.error(error);process.exitCode=1});
'''


STATUS_HARNESS = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1]+'/backup-status.js','utf8');
const empty={writesPaused:false,operations:[]};
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
class Element {
 constructor(tag='button',attrs={},parent=null){
  this.tag=tag;this.attrs=attrs;this.parent=parent;this.disabled=false;this.dataset={};
  for(const [key,value] of Object.entries(attrs))if(key.startsWith('data-'))this.dataset[key.slice(5).replace(/-([a-z])/g,(_,letter)=>letter.toUpperCase())]=value;
 }
 matches(selector){return selector.split(',').some(part=>{
  part=part.trim();if(part===this.tag)return true;
  if(part==='form button:not([type])')return this.tag==='button'&&!Object.hasOwn(this.attrs,'type')&&Boolean(this.parent?.closest('form'));
  const typed=part.match(/^(button|input)\[type="([^"]+)"\]$/);if(typed)return this.tag===typed[1]&&this.attrs.type===typed[2];
  const attr=part.match(/^\[([^=\]^]+)(?:(\^?=)"([^"]*)")?\]$/);if(!attr||!Object.hasOwn(this.attrs,attr[1]))return false;
  return !attr[2]||(attr[2]==='^='?String(this.attrs[attr[1]]).startsWith(attr[3]):this.attrs[attr[1]]===attr[3]);
 });}
 closest(selector){for(let element=this;element;element=element.parent)if(element.matches(selector))return element;return null;}
 getAttribute(name){return this.attrs[name]??null;}
}
function makeContext(responses=[empty],stored=new Map(),controls=[]){
 const listeners={},events=[],timers=[],banner={hidden:true,dataset:{},innerHTML:''};
 const mutation=new Element('button',{'type':'button','data-hub-mutation':''});controls.push(mutation);
 const document={querySelector:selector=>selector==='#backup-status'?banner:null,
  querySelectorAll:selector=>selector==='[data-operation-details]'?[]:controls.filter(control=>control.matches(selector)),
  addEventListener:(name,fn,capture)=>(listeners[name]??=[]).push({fn,capture})};
 const ctx={console,Map,Set,Date,document,location:{search:'',hash:'#projects/projects'},
  sessionStorage:{getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value)},
  setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout(){},
  fetch:async()=>{assert.ok(responses.length,'unexpected status request');const data=await responses.shift();if(data instanceof Error)throw data;return {ok:true,json:async()=>data};},
  CustomEvent:class{constructor(type,options){this.type=type;this.detail=options.detail;}},
  dispatchEvent:event=>events.push(event),addEventListener(){},HubI18n:{locale:'en',t:(key,fallback)=>fallback||key}};
 ctx.window=ctx;ctx.globalThis=ctx;vm.createContext(ctx);vm.runInContext(source,ctx);
 return {ctx,api:ctx.backupStatus,responses,stored,controls,mutation,banner,listeners,events};
}
function event(h,name,target,submitter){
 const value={target,submitter,prevented:false,stopped:false,preventDefault(){this.prevented=true;},stopImmediatePropagation(){this.stopped=true;}};
 for(const listener of h.listeners[name]||[]){assert.equal(listener.capture,true,'the guard must run before pane mutation handlers');listener.fn(value);if(value.stopped)break;}
 return value;
}
const body={action:'project-create',requestId:'request-one',origin:{section:'projects'}};
const running={id:'operation-one',requestId:body.requestId,action:body.action,status:'running',phase:'publishing',origin:body.origin};
const done={...running,status:'succeeded',phase:'complete',finishedAt:new Date().toISOString(),result:{project:{id:'new-project'}}};
'''


RACE_TESTS = r'''
(async()=>{
 const old=deferred(),h=makeContext([old.promise]);const pendingPoll=h.api.refresh();
 h.api.begin(body);assert.equal(h.api.isPaused(),true,'begin locks before the POST response');
 h.api.uncertain(body);old.resolve(empty);await pendingPoll;
 assert.equal(h.api.isPaused(),true,'an older GET cannot release an unresolved request');
 assert.equal(h.api.operations()[0].status,'unknown');assert.equal(h.mutation.disabled,true);
 h.responses.push(empty);await h.api.refresh();assert.equal(h.api.isPaused(),true,'a fresh GET without a receipt also leaves the request unresolved');
 h.responses.push({writesPaused:false,operations:[done]});await h.api.refresh();
 assert.equal(h.api.isPaused(),false);assert.equal(h.api.operations()[0].status,'succeeded');assert.equal(JSON.parse(h.stored.get('project-hub-operation-requests')).length,0);

 const accepted=makeContext();await accepted.api.refresh();const late=deferred();accepted.responses.push(late.promise);const latePoll=accepted.api.refresh();
 accepted.api.begin(body);accepted.api.acknowledge({...running,status:'queued',phase:'waiting'},body);accepted.api.acknowledge(running,body);
 late.resolve(empty);await latePoll;
 assert.equal(accepted.api.isPaused(),true,'an older GET cannot erase a queued/running acknowledgement');
 assert.equal(accepted.api.operations()[0].id,running.id);assert.equal(accepted.api.operations()[0].status,'running');
 accepted.responses.push(empty);await accepted.api.refresh();assert.equal(accepted.api.isPaused(),true,'absence is not a terminal result');
 accepted.responses.push({writesPaused:false,operations:[done]});await accepted.api.refresh();
 assert.equal(accepted.api.isPaused(),false);assert.equal(accepted.mutation.disabled,false);
 accepted.api.acknowledge(running,body);accepted.api.begin(body);accepted.api.uncertain(body);
 assert.equal(accepted.api.operations()[0].status,'succeeded','late active acknowledgements do not revive a terminal operation');assert.equal(accepted.api.isPaused(),false);

 const completed=makeContext();await completed.api.refresh();completed.api.begin(body);completed.api.acknowledge(running,body);
 const stale=deferred();completed.responses.push(stale.promise);const stalePoll=completed.api.refresh();
 completed.api.acknowledge(done,body);assert.equal(completed.api.isPaused(),false);
 stale.resolve({writesPaused:true,operations:[running]});await stalePoll;
 assert.equal(completed.api.isPaused(),false,'an older GET cannot restore a completed operation or its old server lock');
 assert.equal(completed.api.operations()[0].status,'succeeded');assert.match(completed.api.details(done.id),/available in operation history/);
 completed.responses.push({writesPaused:false,operations:[running]});await completed.api.refresh();
 assert.equal(completed.api.operations()[0].status,'succeeded','a stale active row cannot reverse confirmed completion');
 const recovery={...done,id:'recovery',requestId:'recovery-request',status:'interrupted',blocking:true,rollback:'failed'};
 completed.responses.push({writesPaused:false,operations:[recovery]});await completed.api.refresh();
 assert.equal(completed.api.isPaused(),true,'blocking recovery keeps the lock even when the server pause field is false');assert.match(completed.api.details('recovery'),/Recovery required; data preserved/);
 completed.responses.push({writesPaused:false,operations:[{...recovery,blocking:false,rollback:'succeeded',recovery:{status:'succeeded',blocking:false}}]});await completed.api.refresh();assert.equal(completed.api.isPaused(),false);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''


RELOAD_TESTS = r'''
(async()=>{
 const stored=new Map([['project-hub-operation-requests',JSON.stringify([{...body,id:body.requestId,status:'requesting',phase:'requesting'}])]]),initial=deferred();
 const h=makeContext([initial.promise],stored);
 assert.equal(h.api.isPaused(),true,'restored unknown requests lock immediately, before the first GET');assert.equal(h.mutation.disabled,true);assert.equal(h.banner.hidden,false);assert.match(h.banner.innerHTML,/Checking status/);
 initial.resolve(empty);await h.api.refresh();assert.equal(h.api.isPaused(),true,'missing server receipt does not clear a restored request');
 h.responses.push(Error('offline'));await h.api.refresh();assert.equal(h.api.isPaused(),true);assert.match(h.banner.innerHTML,/Connection lost/);
 h.responses.push({writesPaused:false,operations:[done]});await h.api.refresh();assert.equal(h.api.isPaused(),false);assert.equal(h.mutation.disabled,false);assert.equal(JSON.parse(stored.get('project-hub-operation-requests')).length,0);
 assert.match(h.api.operationLink(done),/#projects\/projects\/operation\/operation-one/);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''


GUARD_TESTS = r'''
(async()=>{
 const operationForm=new Element('form',{'data-operation-form':''}),readonlyForm=new Element('form',{'data-readonly':'true'}),getForm=new Element('form',{method:'get'});
 const attributes=[{'data-backup-create':''},{'data-backup-restore':'archive'},{'data-backup-delete':'archive'},{'data-backup-upload':''},{'data-backup-retry':''},
  {'data-storage-action':'apply'},{'data-storage-action':'prepare'},{'data-storage-action':'recheck'},{'data-storage-action':'retry'},
  {'data-storage-folders-action':'apply'},{'data-storage-folders-action':'retry'},
  {'data-project-action':'archive'},{'data-project-action':'delete'},{'data-project-action':'recover'},{'data-project-action':'retry'},
  {'data-settings-action':'save'},{'data-settings-action':'reset-git'},{'data-agent-instructions-action':'save'},{'data-hub-instructions-action':'save'}];
 const mutations=attributes.map(attrs=>new Element('button',{type:'button',...attrs},operationForm));
 const submit=new Element('button',{type:'submit'},operationForm),setting=new Element('input',{'data-setting':'git.autoCommit'}),intrinsicallyDisabled=new Element('button',{type:'button','data-backup-create':''});intrinsicallyDisabled.disabled=true;
 const retry=new Element('button',{type:'button','data-project-action':'retry','data-operation-retry':body.requestId});
 const wrongRetry=new Element('button',{type:'button','data-operation-retry':'other-request','data-backup-retry':''});
 const open=new Element('button',{type:'button','data-local-open':'C:/Data'}),picker=new Element('button',{type:'button','data-local-folder':'workspace'}),copy=new Element('button',{type:'button','data-local-copy':'C:/Data'});
 const inspect=new Element('button',{type:'button','data-storage-action':'inspect-copy'}),link=new Element('a',{href:'#settings'}),readSubmit=new Element('button',{type:'submit'},readonlyForm),getSubmit=new Element('button',{type:'submit'},getForm);
 const controls=[...mutations,submit,setting,intrinsicallyDisabled,retry,wrongRetry,open,picker,copy,inspect,link,readSubmit,getSubmit];
 const foreign={...running,id:'foreign-operation',requestId:'foreign-request',origin:{section:'settings'}};
 const h=makeContext([{writesPaused:false,operations:[foreign]}],new Map(),controls);await h.api.refresh();
 assert.equal(h.api.isPaused(),true,'an active operation in another pane locks mutations');
 for(const control of [...mutations,submit,setting,retry,wrongRetry]){
  assert.equal(control.disabled,true,JSON.stringify(control.attrs));const blocked=event(h,'click',control);assert.equal(blocked.prevented,true);assert.equal(blocked.stopped,true);
 }
 assert.equal(event(h,'submit',operationForm).prevented,true,'data-operation-form is not a blanket exemption');
 // Pane code cannot bypass the capture guard by re-enabling its own button.
 mutations[0].disabled=false;assert.equal(event(h,'click',mutations[0]).prevented,true);assert.equal(mutations[0].disabled,true);
 for(const control of [open,picker,copy,inspect,link,readSubmit,getSubmit]){assert.equal(control.disabled,false);assert.equal(event(h,'click',control).prevented,false);}
 assert.equal(event(h,'submit',readonlyForm,readSubmit).prevented,false);assert.equal(event(h,'submit',getForm,getSubmit).prevented,false);
 h.api.begin(body);assert.equal(retry.disabled,true,'requesting is not retryable');h.api.uncertain(body);
 assert.equal(retry.disabled,false,'only the exact unknown request may be retried');assert.equal(event(h,'click',retry).prevented,false);assert.equal(wrongRetry.disabled,true);
 assert.equal(event(h,'submit',operationForm,retry).prevented,false,'an explicitly marked exact retry also works as a submitter');
 h.api.begin(body);assert.equal(retry.disabled,true,'starting a retry immediately blocks duplicate clicks');h.api.acknowledge(done,body);
 assert.equal(retry.disabled,true,'a confirmed operation is not an unknown retry');
 h.responses.push({writesPaused:false,operations:[{...foreign,status:'succeeded',phase:'complete',finishedAt:new Date().toISOString()},done]});await h.api.refresh();
 assert.equal(h.api.isPaused(),false);for(const control of [...mutations,submit,setting,retry,wrongRetry])assert.equal(control.disabled,false);
 assert.equal(intrinsicallyDisabled.disabled,true,'the shared lock must preserve pre-existing disabled state');
})().catch(error=>{console.error(error);process.exitCode=1;});
'''


LIFECYCLE_HARNESS = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1]+'/backup-status.js','utf8');
let now=Date.parse('2026-10-13T10:00:00Z');
class Clock extends Date {constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}}
const iso=()=>new Clock().toISOString();
function make(saved=new Map(),initial=[]){
 const responses=[{writesPaused:false,operations:initial}],timers=new Map(),handlers={},targets=[],historyTargets=[];
 let timerId=0;
 const banner={hidden:true,dataset:{},innerHTML:'',addEventListener:(name,fn)=>handlers[name]=fn,contains:()=>false};
 const document={activeElement:null,querySelector:selector=>selector==='#backup-status'?banner:null,
  querySelectorAll:selector=>selector==='[data-operation-details]'?targets:selector==='[data-operation-history]'?historyTargets:[],addEventListener(){}};
 const ctx={console,Date:Clock,Intl,Map,Set,document,location:{hash:'#projects/backups',search:''},
  HubI18n:{locale:'en',t:(key,fallback)=>fallback},sessionStorage:{getItem:key=>saved.get(key)||null,setItem:(key,value)=>saved.set(key,value)},
  setTimeout:(fn,delay)=>{const id=++timerId;timers.set(id,{fn,at:now+delay});return id;},clearTimeout:id=>timers.delete(id),
  fetch:async()=>({ok:true,json:async()=>responses.shift()||{writesPaused:false,operations:[]}})};
 ctx.window=ctx;vm.createContext(ctx);vm.runInContext(source,ctx);
 const api=ctx.backupStatus;
 return {ctx,api,banner,handlers,targets,saved,responses,async advance(ms){now+=ms;for(const [id,timer]of [...timers])if(timer.at<=now){timers.delete(id);timer.fn();}await Promise.resolve();await Promise.resolve();await api.refresh();}};
}
const running=(id,action='create')=>({id,requestId:id+'-request',action,status:'running',phase:'copying',createdAt:iso(),startedAt:iso(),origin:{section:'backups'}});
'''

FORMATTING_AND_LIFECYCLE = r'''
(async()=>{
 const h=make();await h.api.refresh();
 assert.equal(h.api.formatSize(35481485),'33.8 MB');assert.equal(h.api.formatSize(1024**3),'1 GB');
 assert.equal(h.api.formatSize(1),'<0.1 KB');assert.equal(h.api.formatSize(0),'0 KB');assert.equal(h.api.formatSize(null),'—');
 assert.equal(h.api.duration(110),'1 min 50 s');assert.equal(h.api.duration(3661),'1 h 1 min 1 s');
 h.ctx.HubI18n.locale='ru';assert.equal(h.api.formatSize(35481485),'33,8 МБ');h.ctx.HubI18n.locale='en';
 const upload={...running('upload','upload-start'),phase:'upload',progress:{completed:1024**2,total:2*1024**2,unit:'bytes'}};
 h.api.acknowledge(upload);assert.equal(h.api.dismiss('upload'),false);assert.doesNotMatch(h.banner.innerHTML,/data-operation-dismiss=/);
 assert.equal(h.api.progressText(upload),'1 / 2 MB');assert.equal(h.api.progressText({progress:{completed:2,total:4,unit:'files'}}),'2 / 4 files');
 assert.equal(h.api.progressText({progress:{completed:1,total:1}}),'');
 now+=10000;const done={...upload,status:'succeeded',finishedAt:iso(),progress:{...upload.progress,completed:2*1024**2}};
 h.api.acknowledge(done);const description=h.api.description(h.api.operations()[0]);assert.match(description,/10 s/);assert.doesNotMatch(description,/Transferring file/);
 assert.match(h.banner.innerHTML,/data-operation-dismiss="upload"/);await h.advance(16000);
 assert.equal(h.banner.hidden,true);assert.equal(h.api.description(h.api.operations()[0]),description);assert.match(h.api.history(),/Upload and verify ZIP/);
 const failed=running('failed');h.api.acknowledge(failed);now+=1000;h.api.acknowledge({...failed,status:'failed',finishedAt:iso(),error:'Destination is occupied'});
 await h.advance(60000);assert.equal(h.banner.hidden,false);assert.match(h.banner.innerHTML,/Destination is occupied/);
 assert.equal(h.api.dismiss('failed'),true);assert.equal(h.banner.hidden,true);assert.match(h.api.history(),/Destination is occupied/);
 const reloaded=make(h.saved,h.api.operations());await reloaded.api.refresh();assert.equal(reloaded.banner.hidden,true,'dismissed errors must not return after reload');
 h.api.begin({action:'apply-import',requestId:'unknown'});h.api.uncertain({requestId:'unknown'});assert.equal(h.api.dismiss('unknown'),false);assert.equal(h.api.isPaused(),true);
 const blocked={...running('recovery','apply-import'),status:'interrupted',finishedAt:iso(),blocking:true,rollback:'failed'};h.api.acknowledge(blocked);
 assert.equal(h.api.dismiss('recovery'),false);await h.advance(60000);assert.match(h.banner.innerHTML,/Recovery required/);assert.equal(h.api.isPaused(),true);
})().catch(error=>{console.error(error);process.exitCode=1});
'''

GROUPING_AND_READING = r'''
(async()=>{
 const h=make();await h.api.refresh();h.api.afterRender();
 const upload={...running('archive','upload-start'),phase:'upload',progress:{completed:2048,total:2048,unit:'bytes'},workflowId:'upload:archive'};
 h.api.acknowledge(upload);now+=1000;h.api.acknowledge({...upload,status:'succeeded',finishedAt:iso()});
 const verification={...running('verify','upload-complete'),phase:'verifying',workflowId:'upload:archive',payload:{id:'archive'},progress:{completed:0,total:1}};
 h.api.acknowledge(verification);assert.equal((h.banner.innerHTML.match(/data-operation-status=/g)||[]).length,1);assert.match(h.banner.innerHTML,/Verify|Verifying/);
 assert.equal(h.api.dismiss('verify'),false);assert.equal(h.api.dismiss('archive'),false);
 now+=3000;h.api.acknowledge({...verification,status:'succeeded',finishedAt:iso()});assert.match(h.banner.innerHTML,/ZIP uploaded and verified/);
 assert.equal((h.api.history().match(/<tr data-ui-key="operation-history-/g)||[]).length,1);assert.equal(h.api.operations().length,2,'grouping must preserve both original records');
 assert.match(h.api.details('verify'),/hub-operation-stages/);assert.match(h.api.details('verify'),/2 KB/);
 h.handlers.pointerenter();await h.advance(60000);assert.equal(h.banner.hidden,false,'reading must pause auto dismissal');
 h.handlers.pointerleave();await h.advance(14000);assert.equal(h.banner.hidden,false);await h.advance(2000);assert.equal(h.banner.hidden,true);
 const row=running('details','restore-copy');h.api.acknowledge(row);now+=1000;h.api.acknowledge({...row,status:'succeeded',finishedAt:iso()});
 const target={dataset:{operationDetails:'details',operationTransient:'false'},closest:()=>null};h.targets.push(target);h.api.afterRender();await h.advance(60000);assert.equal(h.banner.hidden,false);
 h.targets.length=0;h.api.afterRender();await h.advance(16000);assert.equal(h.banner.hidden,true);assert.match(h.api.details('details'),/Close details/);assert.equal(h.api.details('details',{transient:true}),'');
 const legacy=make(new Map(),[{...row,status:'succeeded',startedAt:undefined,finishedAt:undefined,elapsed:undefined}]);await legacy.api.refresh();const before=legacy.api.description(legacy.api.operations()[0]);await legacy.advance(60000);assert.equal(legacy.api.description(legacy.api.operations()[0]),before);
 const oldWorkflow=make(new Map(),[{...upload,status:'succeeded',workflowId:undefined,finishedAt:iso()},{...verification,status:'succeeded',workflowId:undefined,payload:undefined,result:{id:upload.id},finishedAt:iso()}]);await oldWorkflow.api.refresh();
 assert.equal((oldWorkflow.api.history().match(/<tr data-ui-key="operation-history-/g)||[]).length,1,'legacy verification result also links its original archive');
})().catch(error=>{console.error(error);process.exitCode=1});
'''

ACTIVITY_LIFECYCLE = r'''
(async()=>{
 const h=make();await h.api.refresh();let refreshed=0;
 const receive=receipt=>h.api.activityFeedback(receipt,'Research status',()=>refreshed++,'project');
 const active=receive({actionId:'research',status:'running'});assert.equal(active.canDismiss,false);assert.equal(h.api.dismissActivity(active.id),false);assert.equal(h.api.isPaused(),false);
 const done=receive({actionId:'research',status:'completed'});assert.equal(done.text,'Research status');await h.advance(16000);
 assert.equal(receive({actionId:'research',status:'completed'}).text,'');assert.ok(refreshed>0);
 const attention=receive({actionId:'attention',status:'needs_attention'});assert.equal(attention.canDismiss,false);await h.advance(60000);assert.equal(receive({actionId:'attention',status:'needs_attention'}).text,'Research status');
 const failed=receive({actionId:'error',status:'failed'});await h.advance(60000);assert.equal(receive({actionId:'error',status:'failed'}).text,'Research status');assert.equal(h.api.dismissActivity(failed.id),true);assert.equal(receive({actionId:'error',status:'failed'}).text,'');
 const partial=receive({id:'partial',state:'done',status:'partial'});await h.advance(60000);assert.equal(receive({id:'partial',state:'done',status:'partial'}).text,'Research status');assert.equal(h.api.dismissActivity(partial.id),true);
})().catch(error=>{console.error(error);process.exitCode=1});
'''

@unittest.skipUnless(shutil.which("node"), "Node is required")
class BackupStatusUiTest(unittest.TestCase):
    def test_operation_banner_and_server_backed_form_guard(self):
        result = subprocess.run(
            ["node", "-e", HARNESS, str(WEB)], capture_output=True,
            text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def run_status_harness(self, scenarios):
        result = subprocess.run(
            ["node", "-e", STATUS_HARNESS + scenarios, str(WEB)],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_status_snapshots_preserve_newer_requests_and_acknowledgements(self):
        self.run_status_harness(RACE_TESTS)

    def test_restored_unknown_request_blocks_before_status_arrives(self):
        self.run_status_harness(RELOAD_TESTS)

    def test_shared_guard_covers_foreign_mutations_and_only_exact_retries(self):
        self.run_status_harness(GUARD_TESTS)

    def test_banner_is_sticky_and_has_one_existing_mount(self):
        css = (WEB / "backups.css").read_text(encoding="utf-8")
        html = (WEB / "index.html").read_text(encoding="utf-8")
        self.assertIn("#backup-status { position:sticky; top:0;", css)
        self.assertEqual(html.count('id="backup-status"'), 1)

    def run_lifecycle(self, scenario):
        result = subprocess.run(["node", "-e", LIFECYCLE_HARNESS + scenario, str(WEB)],
                                capture_output=True, text=True, encoding="utf-8", timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_units_terminal_duration_and_dismissal_survive_refresh(self):
        self.run_lifecycle(FORMATTING_AND_LIFECYCLE)

    def test_workflow_grouping_and_auto_hide_pause_while_reading(self):
        self.run_lifecycle(GROUPING_AND_READING)

    def test_research_feedback_expires_without_hiding_attention_or_errors(self):
        self.run_lifecycle(ACTIVITY_LIFECYCLE)


    def test_import_failure_details_show_choices_paths_and_escape_untrusted_text(self):
        self.run_lifecycle(r'''
(async()=>{
 const h=make();await h.api.refresh();
 const paths=['coordination/migration-roots.json','language-servers.json','ui-preferences.json','<img src=x onerror=alert(1)>',...Array.from({length:25},(_,index)=>'unknown-file-'+index+'.json')];
 const row={...running('failed-import','apply-import'),status:'failed',phase:'comparing',finishedAt:iso(),error:'Generic conflict',
   payload:{mode:'add',projects:['example-one','example-two'],includeGlobals:false},
   errorBody:{error:'storage_import_conflict',conflicts:paths.map(path=>({type:'ambiguous-global-data',area:'file',path}))}};
 h.api.acknowledge(row);
 const details=h.api.details(row.id);
 assert.match(h.banner.innerHTML,/some shared source data could not be classified/);
 for(const path of paths.filter(path=>!path.startsWith('<'))) {assert.ok(details.includes(path));assert.ok(!h.banner.innerHTML.includes(path),'file paths belong in details only');}
 assert.ok(!h.banner.innerHTML.includes('onerror'));
 assert.match(details,/Add projects/);assert.match(details,/example-one, example-two/);assert.match(details,/Keep current/);
 assert.match(details,/Projects were not applied. Active data were preserved/);
 assert.ok(details.includes('&lt;img src=x onerror=alert(1)&gt;'));assert.ok(!details.includes('<img'));
 h.ctx.HubI18n.locale='ru';
 assert.match(h.api.details(row.id),/Что помешало применению данных/);
 assert.match(h.api.details(row.id),/Сохранение действующих/);
 h.api.acknowledge({...row,id:'published-failure',requestId:'published-failure',publication:{state:'published'}});
 assert.ok(!h.api.details('published-failure').includes('Рабочие данные сохранены'));
 h.api.acknowledge({...row,id:'generic-failure',requestId:'generic-failure',errorBody:{},error:'Ordinary error'});
 assert.match(h.api.details('generic-failure'),/Ordinary error/);
 assert.ok(!h.api.details('generic-failure').includes('hub-operation-failure-details'));
})().catch(error=>{console.error(error);process.exitCode=1});
''')


if __name__ == "__main__":
    unittest.main()
