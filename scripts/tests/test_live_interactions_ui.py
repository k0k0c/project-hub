"""Live-refresh regressions using real browser code in an isolated Node VM."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class LiveInteractionsUiTest(unittest.TestCase):
    def test_history_pages_reuse_revision_key_and_knowledge_hints_refresh_only_knowledge(self):
        self.run_js(r'''
element('div',{id:'history-list'});element('button',{id:'history-more'});
ctx.location.hash='#history';let reads=0;Object.assign(ctx,{historyTask:'',historyKind:'',historyNext:null,historyData:[],historyLoading:false,
  historyRows:()=>'',replacePreservingScroll(){},showError(message){throw Error(message)},
  get:async()=>{reads++;return {revision:ctx.state.revision,events:[],next:null}},state:{revision:1}});
vm.runInContext(slice('async function loadHistory(', 'function checksPage()'),ctx);
await ctx.loadHistory();await ctx.loadHistory();assert.equal(reads,1);
ctx.state.revision=2;await ctx.loadHistory();assert.equal(reads,2);
ctx.get=async()=>{reads++;return {events:[],next:null}};ctx.state.revision=3;
await ctx.loadHistory();await ctx.loadHistory();assert.equal(reads,3,'legacy history responses use the request revision key');
let knowledge=0,refreshes=0;ctx.window.KnowledgeUI={notify(project,rev){assert.equal(project,'fixture');assert.equal(rev,8);knowledge++}};
ctx.refresh=()=>{refreshes++};ctx.state={revision:2};
vm.runInContext(slice('function refreshFromEvent(', 'async function startProject()'),ctx);
ctx.refreshFromEvent({data:JSON.stringify({revision:2,coordinationRevision:0,titlesRevision:'',settingsRevision:null,relationsRevision:null,knowledgeRevision:8})});
assert.equal(knowledge,1);assert.equal(refreshes,0);
''')

    def test_explicit_project_starts_state_without_waiting_for_catalog(self):
        self.run_js(r'''
const discovery=element('div',{id:'project-discovery'});let resolveCatalog,resolveState,started=0,streams=0;
Object.assign(ctx,{loadProjects:()=>new Promise(resolve=>{resolveCatalog=resolve}),
  restoreUiState(){},refresh:()=>{started++;return new Promise(resolve=>{resolveState=resolve})},
  projectApi:x=>x,setInterval(){},EventSource:class{constructor(){streams++}addEventListener(){}},showError(){}});
vm.runInContext(slice('function refreshFromEvent(', 'document.addEventListener("visibilitychange"'),ctx);
const startup=handlers.DOMContentLoaded.at(-1)();
assert.equal(started,1,'state starts while catalog is unresolved');assert.equal(streams,0);
resolveState();for(let i=0;i<6;i++)await Promise.resolve();
assert.equal(streams,1,'live updates do not wait for catalog');
resolveCatalog(true);await startup;
ctx.activeProject='';let chosen=false;ctx.loadProjects=async()=>{chosen=true;ctx.activeProject='chosen';return true};
ctx.refresh=async()=>{assert.equal(chosen,true);assert.equal(ctx.activeProject,'chosen')};
await handlers.DOMContentLoaded.at(-1)();
ctx.activeProject='fixture';ctx.loadProjects=async()=>{throw Error('catalog offline')};
ctx.refresh=async()=>{};await handlers.DOMContentLoaded.at(-1)();assert.equal(discovery.textContent,'catalog offline');
''')

    def test_closed_event_source_reconnects_once_with_backoff_and_guards_stale_projects(self):
        self.run_js(r'''
let sources=[],connections=[];ctx.restoreUiState=()=>{};ctx.refresh=async()=>{};ctx.projectApi=x=>x;
ctx.setConnection=value=>connections.push(value);
ctx.EventSource=class{static CLOSED=2;constructor(url){this.url=url;this.readyState=0;sources.push(this)}addEventListener(){}close(){this.readyState=2}};
vm.runInContext(slice('let stream;', 'document.addEventListener("visibilitychange"'),ctx);
await ctx.startProject();assert.equal(sources.length,1);const first=sources[0];
first.onerror();assert.equal(timers.size,0,'CONNECTING relies on native EventSource retry');
first.readyState=ctx.EventSource.CLOSED;first.onerror();first.onerror();assert.equal(timers.size,1,'one retry timer');
advance(999);assert.equal(sources.length,1);advance(1);assert.equal(sources.length,2);
const second=sources[1];second.readyState=ctx.EventSource.CLOSED;second.onerror();assert.equal(timers.size,1,'closed retry uses one timer');
advance(1999);assert.equal(sources.length,2);advance(1);assert.equal(sources.length,3,'second retry doubles the delay');
const third=sources[2];third.onopen();assert.deepEqual(connections,[false,false,false,false,true]);
third.readyState=ctx.EventSource.CLOSED;third.onerror();assert.equal(timers.size,1,'recovered stream resets to one timer');
advance(1000);assert.equal(sources.length,4);sources[3].readyState=ctx.EventSource.CLOSED;sources[3].onerror();
advance(2000);assert.equal(sources.length,5);sources[4].readyState=ctx.EventSource.CLOSED;sources[4].onerror();
advance(4000);assert.equal(sources.length,6);sources[5].readyState=ctx.EventSource.CLOSED;sources[5].onerror();
advance(8000);assert.equal(sources.length,7);sources[6].readyState=ctx.EventSource.CLOSED;sources[6].onerror();
advance(9999);assert.equal(sources.length,7,'backoff remains bounded at ten seconds');advance(1);assert.equal(sources.length,8);
ctx.activeProject='other';sources[7].readyState=ctx.EventSource.CLOSED;sources[7].onerror();assert.equal(timers.size,0,'stale project cannot add a timer');
''')

    def test_initial_git_and_state_are_parallel_and_live_refresh_does_not_wait_for_git(self):
        self.run_js(r'''
element('div',{id:'project-name'});element('div',{id:'alert'});element('div',{id:'announcement'});
ctx.location.hash='#git';const reads=new Map();Object.assign(ctx,{state:undefined,loadInFlight:null,refreshAgain:false,revision:-1,
  coordinationRevision:'',historyTask:'',gitGeneration:0,gitData:null,gitError:'',
  get:path=>new Promise(resolve=>reads.set(path,resolve)),restoreUiState(){},setConnection(){},showError(message){throw Error(message)}});
vm.runInContext(slice('async function loadGit()', 'async function pushGit()'),ctx);
const pending=ctx.refresh();assert.deepEqual([...reads.keys()].sort(),['/api/git','/api/tasks/summary']);
reads.get('/api/tasks/summary')({revision:1,project:{name:'Fixture'},tasks:[],events:[]});
await pending;assert.equal(ctx.state.revision,1);assert.equal(ctx.gitData,null);
reads.get('/api/git')({repository:{name:'fresh'}});for(let i=0;i<6;i++)await Promise.resolve();
assert.equal(ctx.gitData.repository.name,'fresh');
ctx.state=undefined;ctx.gitData=null;ctx.showError=()=>{};let resolveState;
ctx.get=path=>path==='/api/git'?Promise.reject(Error('git offline')):new Promise(resolve=>{resolveState=resolve});
const retry=ctx.refresh();for(let i=0;i<6;i++)await Promise.resolve();
assert.match(ctx.gitError,/git offline/);
resolveState({revision:2,project:{name:'Fixture'},tasks:[],events:[]});await retry;
assert.match(ctx.gitError,/git offline/,'early Git failure must remain visible after state arrives');
ctx.state=undefined;ctx.get=path=>new Promise(resolve=>reads.set(path,resolve));
const oldProject=ctx.refresh();ctx.activeProject='other';
reads.get('/api/tasks/summary')({revision:3,project:{name:'Old project'},tasks:[],events:[]});
reads.get('/api/git')({repository:{name:'old'}});await oldProject;for(let i=0;i<6;i++)await Promise.resolve();
assert.equal(ctx.state,undefined);assert.equal(ctx.gitData,null);
''')

    def test_complete_matching_sse_hint_skips_duplicate_but_all_changes_revalidate(self):
        self.run_js(r'''
let reads=0;ctx.refresh=()=>{reads++};
ctx.state={revision:1,coordination:{revision:2,titlesRevision:'titles'},settings:{revision:'settings'},relationsRevision:'relations'};
vm.runInContext(slice('function refreshFromEvent(', 'async function startProject()'),ctx);
const hint={revision:1,coordinationRevision:2,titlesRevision:'titles',settingsRevision:'settings',relationsRevision:'relations'};
ctx.refreshFromEvent({data:JSON.stringify(hint)});assert.equal(reads,0);
for(const key of Object.keys(hint))ctx.refreshFromEvent({data:JSON.stringify({...hint,[key]:'changed'})});
assert.equal(reads,5);
ctx.refreshFromEvent({data:JSON.stringify({revision:1,coordinationRevision:2})});
ctx.refreshFromEvent({data:'broken'});assert.equal(reads,7);
''')

    def test_save_refresh_waits_for_snapshot_requested_during_inflight_read(self):
        self.run_js(r'''
element('div',{id:'project-name'});element('div',{id:'alert'});element('div',{id:'announcement'});
const reads=[];
Object.assign(ctx,{loadInFlight:null,refreshAgain:false,revision:0,coordinationRevision:'',historyTask:'',
  get:()=>new Promise(resolve=>reads.push(resolve)),setConnection(){},showError(message){throw Error(message)}});
vm.runInContext(slice('async function refresh()', 'async function pushGit()'),ctx);
const pending=ctx.refresh();let saved=false;
const afterSave=ctx.refresh().then(()=>{saved=true});
reads.shift()({revision:1,project:{name:'Fixture'},tasks:[],events:[]});
for(let i=0;i<8;i++)await Promise.resolve();
assert.equal(reads.length,1,'one follow-up read is scheduled');
assert.equal(saved,false,'save must not finish against the older in-flight snapshot');
reads.shift()({revision:2,project:{name:'Fixture'},tasks:[],events:[]});
await Promise.all([pending,afterSave]);
assert.equal(saved,true);assert.equal(ctx.state.revision,2);
''')

    def run_js(self, test):
        web = Path(__file__).resolve().parents[2] / 'tools/project-portal/web'
        harness = r'''
const vm = require('node:vm'), fs = require('node:fs'), assert = require('node:assert/strict');
const app = fs.readFileSync(process.argv[1] + '/app.js', 'utf8');
const checks = fs.readFileSync(process.argv[1] + '/checks.js', 'utf8');
function slice(start, end) {
  const a = app.indexOf(start), b = app.indexOf(end, a + start.length);
  assert.ok(a >= 0 && b > a, 'Executable source boundaries: ' + start);
  return app.slice(a, b);
}
const nodes = [], handlers = {}, windowHandlers = {}, frames = [], timers = new Map();
let now = 1000, timerId = 0, paints = [], freshness = 0;
// Only browser selector syntax used by these slices; nodes retain identity on deferral.
function matches(node, selector) {
  return selector.split(',').some(part => {
    const terms = part.trim().split(/\s+(?![^\[]*\])/);
    const simple = terms.pop();
    const tag = simple.match(/^[\w-]+/);
    if (tag && node.tagName !== tag[0].toUpperCase()) return false;
    if (simple.startsWith('#') && node.id !== simple.slice(1)) return false;
    for (const [, key, value] of simple.matchAll(/\[([^=\]]+)(?:=["']?([^"'\]]+)["']?)?\]/g)) {
      if (!(key in node.attrs) || (value !== undefined && node.attrs[key] !== value)) return false;
    }
    if (!terms.length) return true;
    for (let parent = node.parentElement; parent; parent = parent.parentElement) {
      if (matches(parent, terms.join(' '))) return true;
    }
    return false;
  });
}
function element(tag, attrs = {}, parentElement = null) {
  const node = {tagName:tag.toUpperCase(), attrs, parentElement, id:attrs.id || '',
    dataset:{}, scrollTop:0, scrollLeft:0, innerHTML:'',
    matches(selector) { return matches(this, selector); },
    closest(selector) { for (let n = this; n; n = n.parentElement) if (matches(n, selector)) return n; return null; },
    focus() { ctx.document.activeElement = this; }};
  nodes.push(node); return node;
}
const content = element('main', {id:'content'});
element('nav', {id:'navigation'}); element('div', {id:'breadcrumb'});
const body = element('body');
const ctx = {URL, URLSearchParams, Map, Date:class extends Date {static now() {return now;}},
  activeProject:'fixture', location:{hash:'#overview'}, state:{version:1}, navigation:[], icons:{},
  historyGeneration:0, taskTab:'plan',
  document:{activeElement:body, querySelector:s=>nodes.find(n=>matches(n,s)) || null,
    querySelectorAll:s=>nodes.filter(n=>matches(n,s)), getElementById:id=>nodes.find(n=>n.id===id),
    addEventListener:(name, fn)=>{(handlers[name] ||= []).push(fn);}},
  window:{scrollX:11, scrollY:700, scrollTo(p) {this.scrollY=p.top; if(p.left!==undefined)this.scrollX=p.left;},
    addEventListener:(name, fn)=>windowHandlers[name]=fn},
  requestAnimationFrame:fn=>frames.push(fn),
  setTimeout:(fn, delay)=>{timers.set(++timerId, {fn, at:now+delay});return timerId;},
  clearTimeout:id=>timers.delete(id), updateFreshness:()=>freshness++, escape:String, uiIcon:()=>'',
  route:()=>ctx.location.hash.slice(1).split('/').map(decodeURIComponent)};
ctx.$ = s=>ctx.document.querySelector(s);
for (const name of ['overview','taskPage','tasksPage','gitPage','historyPage','checksPage',
  'architecturePage','docsPage','actionsPage','coordinationPage','settingsPage']) {
  ctx[name] = ()=>{paints.push(ctx.state.version);return 'version-' + ctx.state.version;};
}
vm.createContext(ctx);
vm.runInContext(slice('function eventTitle(', 'function eventView('), ctx);
vm.runInContext(slice('function retainTaskDetails(', 'const taskDetailLoader'), ctx);
vm.runInContext(slice('let pendingLiveRender', 'function updateFreshness()'), ctx);
vm.runInContext(slice('window.addEventListener("hashchange"', 'if (route()[0] === "history") historyTask'), ctx);
function fire(name, target=body) {
  for (const fn of handlers[name] || []) fn({target, key:'Tab'});
}
function advance(ms=1000) {
  now += ms;
  for (const [id, timer] of [...timers]) if(timer.at<=now) {timers.delete(id);timer.fn();}
}
function drainFrames() {while(frames.length) frames.shift()();}
function navigate(hash) {
  const oldURL='http://fixture/' + ctx.location.hash;
  ctx.location.hash=hash; windowHandlers.hashchange({oldURL,newURL:'http://fixture/'+hash});
}
(async()=>{
'''
        result = subprocess.run(
            ['node', '-e', harness + test + '\n})().catch(e=>{console.error(e);process.exitCode=1});', str(web)],
            capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_focused_controls_and_editable_form_defer_background(self):
        self.run_js(r'''
for (const [tag, attrs] of [['select',{}],['input',{type:'search'}],['textarea',{}],
  ['div',{contenteditable:'true'}],['div',{role:'combobox'}],['div',{role:'listbox'}],['div',{role:'menu'}]]) {
  const control=element(tag,attrs);ctx.document.activeElement=control;
  assert.equal(ctx.hasLiveInteraction(),true,tag+JSON.stringify(attrs));
  ctx.render({background:true});assert.equal(paints.length,0);
  assert.equal(ctx.document.activeElement,control);
}
assert.ok(freshness>0,'Freshness still updates while painting is deferred');
ctx.document.activeElement=body;ctx.flushLiveRender();assert.deepEqual(paints,[1]);
''')

    def test_mounted_text_fields_allow_live_data_updates_but_native_picker_defers(self):
        self.run_js(r'''
let patches=0;ctx.window.HubLiveUI={patch(node,html){if(node===content)patches++;node.innerHTML=html;}};
const text=element('textarea');ctx.document.activeElement=text;
ctx.render({background:true});assert.deepEqual(paints,[1]);assert.equal(patches,1);assert.equal(ctx.document.activeElement,text);
ctx.state={version:2};ctx.document.activeElement=element('select');ctx.render({background:true});assert.deepEqual(paints,[1]);
ctx.document.activeElement=text;ctx.flushLiveRender();assert.deepEqual(paints,[1,2]);assert.equal(ctx.document.activeElement,text);
''')

    def test_open_parent_menu_survives_search_blur_and_coalesces_latest(self):
        self.run_js(r'''
const trigger=element('button',{'aria-haspopup':'listbox','aria-expanded':'true'});
const search=element('input',{type:'search'}), scroller=element('div');
ctx.document.activeElement=search;ctx.render({background:true});
ctx.document.activeElement=scroller;fire('focusout',search);
for(const version of [2,3,4]) {ctx.state={version};ctx.render({background:true});}
advance();assert.deepEqual(paints,[],'Open picker protects itself after search loses focus');
trigger.attrs['aria-expanded']='false';fire('click',trigger);advance();
assert.deepEqual(paints,[4]);ctx.flushLiveRender();assert.deepEqual(paints,[4]);
''')

    def test_dialog_and_open_details_form_remain_mounted(self):
        self.run_js(r'''
const dialog=element('dialog',{open:''});ctx.render({background:true});assert.deepEqual(paints,[]);
delete dialog.attrs.open;fire('close',dialog);advance();assert.deepEqual(paints,[1]);
const details=element('details',{open:''});element('textarea',{},details);
ctx.state={version:2};ctx.render({background:true});assert.deepEqual(paints,[1]);
delete details.attrs.open;fire('toggle',details);advance();assert.deepEqual(paints,[1,2]);
''')

    def test_explicit_render_bypasses_deferral_and_stale_keys_are_dropped(self):
        self.run_js(r'''
ctx.document.activeElement=element('select');ctx.render({background:true});
ctx.state={version:2};ctx.render();assert.deepEqual(paints,[2]);
ctx.document.activeElement=body;ctx.flushLiveRender();assert.deepEqual(paints,[2]);
for(const change of [()=>ctx.location.hash='#tasks/other',()=>ctx.activeProject='other']) {
  ctx.document.activeElement=element('input');ctx.render({background:true});change();
  ctx.document.activeElement=body;ctx.flushLiveRender();assert.deepEqual(paints,[2]);
}
ctx.document.activeElement=element('input');ctx.render({background:true});
navigate('#overview');assert.deepEqual(paints,[2,2]);
ctx.document.activeElement=body;advance();assert.deepEqual(paints,[2,2]);
''')

    def test_scroll_quiet_period_defers_until_user_stops(self):
        self.run_js(r'''
for(const event of ['wheel','touchmove','pointerdown','pointerup','scroll']) {
  const before=paints.length;fire(event);ctx.render({background:true});
  advance(50);assert.equal(paints.length,before,event);
  fire('scroll');advance(50);assert.equal(paints.length,before,'Continued scrolling');
  advance();assert.equal(paints.length,before+1,event+' settles');
}
''')

    def test_late_animation_frames_do_not_undo_user_scroll_or_new_restore(self):
        self.run_js(r'''
const pane=element('div',{'data-scroll-key':'pane'});pane.dataset.scrollKey='pane';pane.scrollTop=40;
for(const event of ['wheel','touchmove','pointerdown','keydown']) {
  ctx.restoreScrollPositions(ctx.captureScrollPositions());fire(event);
  ctx.window.scrollY=950;pane.scrollTop=90;drainFrames();
  assert.equal(ctx.window.scrollY,950,event);assert.equal(pane.scrollTop,90,event);
}
ctx.window.scrollY=100;const old=ctx.captureScrollPositions();ctx.restoreScrollPositions(old);
ctx.window.scrollY=800;pane.scrollTop=120;ctx.restoreScrollPositions(ctx.captureScrollPositions());
drainFrames();assert.equal(ctx.window.scrollY,800);assert.equal(pane.scrollTop,120);
''')

    def test_same_task_stage_preserves_viewport_other_task_or_page_resets(self):
        self.run_js(r'''
ctx.navigation=[['tasks','Tasks'],['overview','Overview']];
ctx.location.hash='#tasks/task%20one/first';ctx.window.scrollY=720;
navigate('#tasks/task%20one/second');drainFrames();assert.equal(ctx.window.scrollY,720);
navigate('#tasks/task%20one');drainFrames();assert.equal(ctx.window.scrollY,720);
ctx.restoreScrollPositions(ctx.captureScrollPositions());
navigate('#tasks/task-two/stage');drainFrames();assert.equal(ctx.window.scrollY,0);
ctx.window.scrollY=600;navigate('#overview');drainFrames();assert.equal(ctx.window.scrollY,0);
''')

    def test_checks_async_success_and_error_render_as_background(self):
        self.run_js(r'''
ctx.route=()=>['checks'];ctx.state={checks:[],checkCount:0};
const calls=[];ctx.render=options=>calls.push(options);
ctx.fetch=async()=>({ok:true,json:async()=>({runs:[],total:0,next:null})});
vm.runInContext(checks,ctx);await ctx.loadChecks();
assert.ok(calls.length>=2);assert.ok(calls.every(options=>options?.background===true));
calls.length=0;ctx.fetch=async()=>{throw Error('fixture failure');};await ctx.loadChecks();
assert.ok(calls.length);assert.ok(calls.every(options=>options?.background===true));
''')

    def test_refresh_and_git_background_source_contract(self):
        self.run_js(r'''
for(const [start,end] of [['async function refresh()', 'async function pushGit()'],
  ['async function loadGit()', 'async function refresh()']]) {
  const source=slice(start,end), calls=[...source.matchAll(/\brender\s*\(([^)]*)\)/g)];
  assert.ok(calls.length,start+' renders updated state');
  for(const call of calls) assert.match(call[1],/\bbackground\s*:\s*true\b/);
}
''')
