"""Focused browser-contract checks for the standalone Projects manager."""
import subprocess
import unittest
from pathlib import Path


WEB = Path(__file__).resolve().parents[2] / "tools/project-portal/web/projects.js"

HARNESS = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(process.argv[1], 'utf8');
class Root {
  constructor() { this.dataset = {}; this.listeners = {}; this.isConnected = true; this.html = ''; }
  set innerHTML(value) { this.html = value; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  emit(type, event) { return Promise.all((this.listeners[type] || []).map(fn => fn(event))); }
}
function form(kind, values, projectId = '') {
  return {dataset:{projectForm:kind, projectId}, elements:{namedItem:name => ({value:values[name] || ''})}, closest(selector){ return selector.includes('data-project-form') ? this : null; }};
}
function harness(responses, language='ru') {
  const root = new Root(), calls = [], timers = new Set();
  let nextTimer = 1;
  const schedule = (fn, delay) => { const id = nextTimer++; timers.add({id, fn, delay}); return id; };
  const cancel = id => { for (const timer of timers) if (timer.id === id) timers.delete(timer); };
  const fetch = async (url, options = {}) => {
    calls.push({url, options, body: options.body ? JSON.parse(options.body) : null});
    const next = responses.shift();
    if (next instanceof Error) throw next;
    if (next && next.__response) return next.__response;
    return {ok:true, status:200, async json(){return next;}};
  };
  const context = {console, fetch, setTimeout:schedule, clearTimeout:cancel, CustomEvent:class{constructor(type,init){this.type=type;this.detail=init.detail;}}, dispatchEvent(){}, crypto:{randomUUID:()=> '01234567-89ab-cdef-0123-456789abcdef'},
    document:{querySelector:()=>root}, window:{}, globalThis:{}};
  context.window = context; context.globalThis = context;
  vm.createContext(context);
  if (language==='en') {
    vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
    context.HubI18n={locale:'en',t(key, fallback){return context.HubLocaleCatalog[key]?.en || (typeof fallback==='string'?fallback:key);}};
  }
  vm.runInContext(source, context, {filename:'projects.js'});
  return {context, root, calls, async poll(){const timer=[...timers][0];if(timer){timers.delete(timer);await timer.fn();}}, stop(){timers.clear();}};
}
async function flush() { for (let index = 0; index < 12; index++) await Promise.resolve(); }
async function recoveredCatalogClearsOnlyItsConnectionError() {
  const catalog={schemaVersion:2,projects:[{id:'restored',name:'Restored project',roots:[],revision:1}],discovery:{}};
  const h=harness([Error('Temporary connection loss'),catalog],'en');
  h.context.HubProjectsUI.afterRender(h.root);await flush();
  assert.match(h.root.html,/Temporary connection loss/);
  await h.poll();await flush();
  assert.match(h.root.html,/Restored project/);
  assert.doesNotMatch(h.root.html,/Temporary connection loss/,'successful background reload clears the lost-connection notice');
  h.stop();
  const validation=harness([catalog,catalog],'en');
  validation.context.HubProjectsUI.afterRender(validation.root);await flush();
  await validation.root.emit('submit',{target:form('create',{name:''}),preventDefault(){}});await flush();
  assert.match(validation.root.html,/Enter a project name/);
  await validation.poll();await flush();
  assert.match(validation.root.html,/Enter a project name/,'background reads must retain form validation errors');
  validation.stop();
}
async function pageStructureAndProjectDialog() {
  const h=harness([{schemaVersion:2,projects:[{id:'example',name:'Example',roots:[],revision:1}],discovery:{}}],'en');
  const page=h.context.HubProjectsUI.page();
  assert.equal((page.match(/role="tab"/g)||[]).length,3);
  assert.match(page,/Hub data/);assert.match(page,/Backups/);
  assert.match(page,/href="#settings\/agents"/);
  assert.doesNotMatch(page,/data-project-invite|data-agent-providers|hub-connections-manager/);
  assert.equal((page.match(/<h1/g)||[]).length,1);
  assert.doesNotMatch(page,/data-project-form="create"/);
  h.context.HubProjectsUI.afterRender(h.root);await flush();
  await h.root.emit('click',{target:{dataset:{projectAction:'configure',projectId:'example'},closest(){return this;}}});await flush();
  assert.match(h.root.html,/<dialog/);assert.doesNotMatch(h.root.html,/data-project-dialog-tab="agents"|hub-connections-manager/);
  assert.equal((h.root.html.match(/data-project-dialog-tab=/g)||[]).length,2);
  assert.match(h.root.html,/Code folders/);assert.doesNotMatch(h.root.html,/[А-Яа-яЁё]/);
  h.stop();
}
async function createUsesContract() {
  const h = harness([{schemaVersion:2, projects:[], discovery:{}}, {project:{id:'p1',name:'Alpha',roots:[],revision:1}} , {schemaVersion:2, projects:[{id:'p1',name:'Alpha',roots:[],revision:1}],discovery:{}}]);
  h.context.HubProjectsUI.afterRender(h.root); await flush();
  await h.root.emit('submit', {target:form('create',{name:'Alpha',root:''}), preventDefault(){}});
  const call = h.calls.find(item => item.body?.action === 'create');
  assert.equal(call.body.name, 'Alpha'); assert.deepEqual(call.body.roots, []);
  assert.match(call.body.requestId, /^[0-9a-f]{32}$/);
  h.stop();
}
async function schemaOneDisablesManagement() {
  const h = harness([{schemaVersion:1, projects:[{id:'old',name:'Legacy',roots:[],revision:1}],discovery:{}}]);
  h.context.HubProjectsUI.afterRender(h.root); await flush();
  assert.match(h.root.html, /Управление отключено/);
  assert.match(h.root.html, /disabled/);
  h.stop();
}
async function retryKeepsRequestId() {
  const h = harness([{schemaVersion:2, projects:[], discovery:{}}, new Error('network'), {project:{id:'p2',name:'Beta',roots:[],revision:1}}, {schemaVersion:2,projects:[],discovery:{}}]);
  h.context.HubProjectsUI.afterRender(h.root); await flush();
  await h.root.emit('submit', {target:form('create',{name:'Beta'}), preventDefault(){}});
  const posts = h.calls.filter(item => item.body?.action === 'create');
  assert.equal(posts.length, 2); assert.equal(posts[0].body.requestId, posts[1].body.requestId);
  h.stop();
}
async function unknownOutcomeOffersSameMutationForManualRetry() {
  const h = harness([{schemaVersion:2, projects:[], discovery:{}}, new Error('network 1'), new Error('network 2'),
    {project:{id:'p3',name:'Gamma',roots:[],revision:1}}, {schemaVersion:2,projects:[],discovery:{}}]);
  h.context.HubProjectsUI.afterRender(h.root); await flush();
  await h.root.emit('submit', {target:form('create',{name:'Gamma'}), preventDefault(){}});
  assert.match(h.root.html, /Повторить последнее изменение/);
  const firstPosts = h.calls.filter(item => item.body?.action === 'create');
  const retryButton = {dataset:{projectAction:'retry'}, closest(){return this;}};
  await h.root.emit('click', {target:retryButton}); await flush();
  const posts = h.calls.filter(item => item.body?.action === 'create');
  assert.equal(posts.length, 3); assert.equal(posts[0].body.requestId, posts[1].body.requestId); assert.equal(posts[1].body.requestId, posts[2].body.requestId);
  h.stop();
}
async function malformedAndServerFailureRemainRetryable() {
  const bad = {__response:{ok:true,status:200,async json(){throw Error('bad json');}}};
  const h = harness([{schemaVersion:2,projects:[],discovery:{}}, bad, {__response:{ok:false,status:503,async json(){return {error:'busy'};}}}]);
  h.context.HubProjectsUI.afterRender(h.root); await flush();
  await h.root.emit('submit', {target:form('create',{name:'Delta'}), preventDefault(){}});
  assert.match(h.root.html, /Повторить последнее изменение/);
  const retryButton = {dataset:{projectAction:'retry'}, closest(){return this;}};
  await h.root.emit('click', {target:retryButton}); await flush();
  assert.equal(h.calls.filter(item => item.body?.action === 'create').length, 2);
  h.stop();
}
async function renameUsesRevisionCapturedBeforeBackgroundRefresh() {
  const h = harness([{schemaVersion:2,projects:[{id:'p4',name:'Before',roots:[],revision:1}],discovery:{}},
    {schemaVersion:2,projects:[{id:'p4',name:'Server change',roots:[],revision:2}],discovery:{}},
    {project:{id:'p4',name:'Renamed',roots:[],revision:3}}, {schemaVersion:2,projects:[],discovery:{}}]);
  h.context.HubProjectsUI.afterRender(h.root); await flush();
  const rename = form('rename',{name:'Renamed'},'p4'); rename.dataset.projectRevision='1';
  const refresh = {dataset:{projectAction:'refresh'}, closest(){return this;}};
  await h.root.emit('click', {target:refresh}); await flush();
  await h.root.emit('submit', {target:rename, preventDefault(){}});
  const update = h.calls.find(item => item.body?.action === 'update');
  assert.equal(update.body.expected, 1); h.stop();
}
async function malformedProjectReceiptKeepsDraftAndExactRetry() {
  for (const project of [{}, {id:'unexpected',name:'My draft',roots:[],revision:2}, {id:'p6',name:'My draft',roots:[],revision:'2'}]) {
    const h = harness([{schemaVersion:2,projects:[{id:'p6',name:'Before',roots:[],revision:1}],discovery:{}},
      {project}, {project:{id:'p6',name:'My draft',roots:[],revision:2}},
      {schemaVersion:2,projects:[{id:'p6',name:'My draft',roots:[],revision:2}],discovery:{}}]);
    h.context.HubProjectsUI.afterRender(h.root); await flush();
    const rename=form('rename',{name:'My draft'},'p6');rename.dataset.projectRevision='1';
    await h.root.emit('submit',{target:rename,preventDefault(){}});await flush();
    assert.match(h.root.html,/value="My draft"/);assert.match(h.root.html,/Повторить последнее изменение/);
    await h.root.emit('click',{target:{dataset:{projectAction:'retry'},closest(){return this;}}});await flush();
    const posts=h.calls.filter(item=>item.body?.action==='update');
    assert.equal(posts.length,2);assert.deepEqual(posts[0].body,posts[1].body);
    assert.doesNotMatch(h.root.html,/Повторить последнее изменение/);h.stop();
  }
}
async function confirmedConflictCanBeReviewedAndRetried() {
  const h = harness([{schemaVersion:2,projects:[{id:'p5',name:'Before',roots:[],revision:1}],discovery:{}},
    {__response:{ok:false,status:409,async json(){return {code:'project_revision_conflict'};}}},
    {schemaVersion:2,projects:[{id:'p5',name:'Server change',roots:[],revision:2}],discovery:{}},
    {project:{id:'p5',name:'My draft',roots:[],revision:3}}, {schemaVersion:2,projects:[],discovery:{}}]);
  h.context.HubProjectsUI.afterRender(h.root); await flush();
  const first = form('rename',{name:'My draft'},'p5'); first.dataset.projectRevision='1';
  await h.root.emit('submit', {target:first,preventDefault(){}}); await flush();
  const refresh = {dataset:{projectAction:'refresh'},closest(){return this;}};
  await h.root.emit('click',{target:refresh}); await flush();
  assert.match(h.root.html,/data-project-revision="2"/); assert.match(h.root.html,/value="My draft"/);
  const retry = form('rename',{name:'My draft'},'p5'); retry.dataset.projectRevision='2';
  await h.root.emit('submit',{target:retry,preventDefault(){}}); await flush();
  const posts = h.calls.filter(item => item.body?.action === 'update');
  assert.equal(posts[0].body.expected,1); assert.equal(posts[1].body.expected,2); h.stop();
}
function asynchronousHarness(server, session = new Map()) {
  let root = new Root();
  const banner = {dataset:{},hidden:true,html:'',set innerHTML(value){this.html=value;}}, calls = [], timers = new Set(), listeners = {};
  const panes = ['projects','data','backups'].map(projectPane=>({dataset:{projectPane},hidden:projectPane!=='data'}));
  const shell = {listeners:{},addEventListener(type,fn){this.listeners[type]=fn;},querySelectorAll(selector){return selector==='[data-project-pane]' ? panes : [];}};
  const document = {activeElement:null,querySelector(selector){return selector==='#backup-status' ? banner : selector==='#projects-admin' ? shell : selector==='#projects-manager' ? root : null;},
    querySelectorAll(selector){return selector==='[data-operation-details]' ? root.details || [] : [];},addEventListener(){}};
  function mount() {
    root = new Root();
    Object.defineProperty(root,'innerHTML',{set(value){this.html=value;this.details=[...value.matchAll(/data-operation-details="([^"]+)"/g)].map(match=>({dataset:{operationDetails:match[1]},innerHTML:'',closest(){return null;},focus(){this.focused=true;},scrollIntoView(){this.scrolled=true;}}));}});
    return root;
  }
  mount();
  server.requestNumber ||= 0;
  const context = {console,document,location:{hash:'#projects/projects',search:''},
    setTimeout(fn,delay){const timer={fn,delay};timers.add(timer);return timer;},clearTimeout(timer){timers.delete(timer);},
    CustomEvent:class{constructor(type,init){this.type=type;this.detail=init.detail;}},
    addEventListener(type,fn){(listeners[type] ||= []).push(fn);},dispatchEvent(event){for(const fn of listeners[event.type] || [])fn(event);},
    sessionStorage:{getItem:key=>session.get(key) || null,setItem:(key,value)=>session.set(key,value),removeItem:key=>session.delete(key)},
    crypto:{randomUUID:()=> (++server.requestNumber).toString(16).padStart(32,'0')},
    async fetch(url,options={}){
      const body=options.body ? JSON.parse(options.body) : null;calls.push({url,body});
      let value;
      if(url==='/api/v1/backups/status')value={writesPaused:server.writesPaused,operations:server.operations};
      else if(url==='/api/v1/projects?includeDeleted=true')value={schemaVersion:2,projects:server.projects,discovery:{}};
      else if(url==='/api/v1/projects' && body)value=await server.post(body);
      else throw Error(`Unexpected endpoint: ${url}`);
      return {ok:true,status:body?202:200,json:async()=>JSON.parse(JSON.stringify(value))};
    }};
  context.window=context;context.globalThis=context;vm.createContext(context);
  vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
  context.HubI18n={locale:'en',t(key,fallback){return context.HubLocaleCatalog[key]?.en || (typeof fallback==='string'?fallback:key);}};
  vm.runInContext(fs.readFileSync(process.argv[3],'utf8'),context,{filename:'backup-status.js'});
  vm.runInContext(source,context,{filename:'projects.js'});
  return {context,banner,calls,panes,session,get root(){return root;},mount,stop(){timers.clear();}};
}
async function sharedOperationsRecoverRetryAndTerminalResults() {
  const identifier='a'.repeat(32), updateIdentifier='b'.repeat(32), session=new Map();
  const server={projects:[],operations:[],writesPaused:false,attempts:0,async post(body){
    if(body.action==='create' && ++this.attempts<3)throw Error('Connection unavailable');
    const operation={id:body.action==='create'?identifier:updateIdentifier,requestId:body.requestId,
      action:`project-${body.action}`,status:'queued',phase:'waiting',origin:body.origin,createdAt:new Date().toISOString()};
    this.operations=[operation];this.writesPaused=true;return {operation};
  }};
  const h=asynchronousHarness(server,session);
  h.context.HubProjectsUI.afterRender(h.root);await flush();
  await h.root.emit('submit',{target:form('create',{name:'Gamma',root:'/workspace/example'}),preventDefault(){}});await flush();
  assert.match(h.banner.html,/Create project/);assert.match(h.banner.html,/Checking status/);
  assert.match(h.root.html,/Repeat last change/);assert.doesNotMatch(h.root.html,/[А-Яа-яЁё]/);
  assert.ok(session.has('project-hub-project-mutation'));
  const retry={dataset:{projectAction:'retry'},closest(){return this;}};
  await h.root.emit('click',{target:retry});await flush();
  const posts=h.calls.filter(call=>call.body);
  assert.equal(posts.length,3);assert.deepEqual(posts[0].body,posts[1].body);assert.deepEqual(posts[1].body,posts[2].body);
  assert.equal(posts[0].body.background,true);assert.deepEqual(posts[0].body.origin,{section:'projects'});
  assert.deepEqual(posts[0].body.roots,['/workspace/example']);
  assert.match(h.banner.html,new RegExp(`#projects/projects/operation/${identifier}`));
  assert.match(h.banner.html,/Queued/);assert.equal(h.context.backupStatus.isPaused(),true);
  assert.doesNotMatch(h.root.html,/data-project-action="retry"/);
  assert.equal(JSON.parse(session.get('project-hub-project-mutation')).operationId,identifier);
  assert.equal(h.calls.filter(call=>call.url.startsWith('/api/v1/projects?')).length,1,'acceptance must return without waiting locally for a terminal result');
  assert.ok(!h.calls.some(call=>call.url.includes('/storage/operations')));

  h.context.location.hash=`#projects/projects/operation/${identifier}`;
  h.mount();h.context.HubProjectsUI.afterRender(h.root);await flush();
  assert.match(h.root.html,new RegExp(`data-operation-details="${identifier}"`));
  assert.equal(h.panes.find(pane=>pane.dataset.projectPane==='projects').hidden,false);
  assert.equal(h.panes.find(pane=>pane.dataset.projectPane==='data').hidden,true);
  h.root.isConnected=false;h.stop();

  // A new page restores the pending receipt and draft without resubmitting.
  const restored=asynchronousHarness(server,session);
  restored.context.location.hash=`#projects/projects/operation/${identifier}`;
  restored.context.HubProjectsUI.afterRender(restored.root);await flush();
  assert.equal(restored.calls.filter(call=>call.body).length,0);
  assert.match(restored.root.html,new RegExp(`data-operation-details="${identifier}"`));
  assert.equal(JSON.parse(session.get('project-hub-project-mutation')).draft.name,'Gamma');
  server.projects=[{id:'p8',name:'Gamma',roots:['/workspace/example'],revision:1}];
  server.operations[0]={...server.operations[0],status:'succeeded',phase:'ready',result:{project:server.projects[0]},finishedAt:new Date().toISOString()};server.writesPaused=false;
  const beforeTerminal=restored.calls.filter(call=>call.url.startsWith('/api/v1/projects?')).length;
  await restored.context.backupStatus.refresh();await flush();
  assert.equal(restored.calls.filter(call=>call.url.startsWith('/api/v1/projects?')).length,beforeTerminal+1);
  assert.match(restored.root.html,/Gamma/);assert.match(restored.banner.html,/Project created/);
  assert.equal(session.has('project-hub-project-mutation'),false);
  const afterTerminal=restored.calls.length;
  await restored.context.backupStatus.refresh();await flush();
  assert.equal(restored.calls.slice(afterTerminal).filter(call=>call.url.startsWith('/api/v1/projects?')).length,0,'repeat status snapshots must not keep reloading the catalogue');

  const rename=form('rename',{name:'My draft'},'p8');rename.dataset.projectRevision='1';
  await restored.root.emit('submit',{target:rename,preventDefault(){}});await flush();
  const update=restored.calls.find(call=>call.body?.action==='update');
  assert.equal(update.body.background,true);assert.deepEqual(update.body.origin,{section:'projects',project:'p8'});
  server.projects=[{id:'p8',name:'Server change',roots:['/workspace/example'],revision:2}];
  server.operations[0]={...server.operations[0],status:'failed',phase:'ready',error:'Revision changed',errorBody:{code:'project_revision_conflict'},finishedAt:new Date().toISOString()};server.writesPaused=false;
  await restored.context.backupStatus.refresh();await flush();
  assert.match(restored.root.html,/value="My draft"/);assert.match(restored.root.html,/changed in another client/);
  assert.doesNotMatch(restored.root.html,/data-project-action="retry"/);assert.equal(session.has('project-hub-project-mutation'),false);
  await restored.root.emit('click',{target:{dataset:{projectAction:'refresh'},closest(){return this;}}});await flush();
  assert.match(restored.root.html,/data-project-revision="2"/);assert.match(restored.root.html,/value="My draft"/);
  assert.doesNotMatch(restored.root.html,/[А-Яа-яЁё]/);restored.stop();
}
async function statusCompletionWinsOverALateLostPostResponse() {
  let rejectPost;
  const server={projects:[],operations:[],writesPaused:false,async post(body){
    this.operations=[{id:'c'.repeat(32),requestId:body.requestId,action:'project-create',status:'running',phase:'importing',origin:body.origin,createdAt:new Date().toISOString()}];
    this.writesPaused=true;return new Promise((resolve,reject)=>{rejectPost=reject;});
  }};
  const h=asynchronousHarness(server);
  h.context.HubProjectsUI.afterRender(h.root);await flush();
  const submission=h.root.emit('submit',{target:form('create',{name:'Completed first'}),preventDefault(){}});await flush();
  server.projects=[{id:'p9',name:'Completed first',roots:[],revision:1}];
  server.operations[0]={...server.operations[0],status:'succeeded',phase:'ready',result:{project:server.projects[0]},finishedAt:new Date().toISOString()};server.writesPaused=false;
  await h.context.backupStatus.refresh();await flush();
  rejectPost(Error('Late connection loss'));await submission;await flush();
  assert.equal(h.calls.filter(call=>call.body).length,1,'a confirmed terminal result must prevent a late network error from retrying or reviving the request');
  assert.equal(h.session.has('project-hub-project-mutation'),false);
  assert.match(h.root.html,/Project created/);assert.doesNotMatch(h.root.html,/data-project-action="retry"|Late connection loss/);
  assert.match(h.banner.html,/Project created/);h.stop();
}
(async()=>{await recoveredCatalogClearsOnlyItsConnectionError(); await pageStructureAndProjectDialog(); await createUsesContract(); await schemaOneDisablesManagement(); await retryKeepsRequestId(); await unknownOutcomeOffersSameMutationForManualRetry(); await malformedAndServerFailureRemainRetryable(); await renameUsesRevisionCapturedBeforeBackgroundRefresh(); await malformedProjectReceiptKeepsDraftAndExactRetry(); await confirmedConflictCanBeReviewedAndRetried(); await sharedOperationsRecoverRetryAndTerminalResults(); await statusCompletionWinsOverALateLostPostResponse();})().catch(error=>{console.error(error);process.exitCode=1;});
'''


class ProjectsUiTest(unittest.TestCase):
    def test_projects_manager_contract(self):
        result = subprocess.run(["node", "-e", HARNESS, str(WEB),str(WEB.parent/'locale-catalog.js'),str(WEB.parent/'backup-status.js')], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
