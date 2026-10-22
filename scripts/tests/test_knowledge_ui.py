"""Knowledge UI behavior with a Node VM and disposable mocked project APIs."""
from pathlib import Path
import shutil
import subprocess
import unittest

WEB = Path(__file__).resolve().parents[2] / 'tools/project-portal/web'

HARNESS = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const data=new Map(),requests=[],handlers={};let root=null;
const body={innerHTML:''};
const context={revision:7,policy:{audiences:['user','developer'],sections:['Start'],components:[{id:'app',title:'Application',paths:['src/']}]},counts:{document:1,entity:2},jobs:[]};
let responder=async(action,args)=>action==='context'?context:action==='search'?{revision:7,items:[],more:false,next:null}:action==='read'?{id:args.id,kind:'document',title:'A <title>',markdown:'<script>alert(1)</script>',entityRefs:[]}:{};
const ctx={URL,URLSearchParams,Map,Set,JSON,Math,Date,Promise,Blob,AbortController,
 setTimeout,clearTimeout,console,localStorage:{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v)},
 location:{origin:'http://localhost',hash:'#docs'},history:{replaceState(_a,_b,hash){ctx.location.hash=hash;}},
 window:{crypto:{randomUUID:()=>String(requests.length)+'-unique'},confirm:()=>true},
 document:{hidden:false,activeElement:null,querySelector:()=>root,addEventListener:(name,handler)=>handlers[name]=handler},
 fetch:async(url,options={})=>{const u=new URL(url,'http://localhost');const payload=options.body?JSON.parse(options.body):null;
 const args=payload?.args||Object.fromEntries(u.searchParams);const action=payload?.action||u.searchParams.get('action');
 requests.push({url,action,args,options});let result;
 if(action==='source-tree'&&args.mode==='navigation'){
   const pages=await Promise.all([{kind:'view'},{kind:'entity',type:'component'},{kind:'entity',entrypoint:'true'}].map(filter=>responder('search',{...filter,limit:'200'},u.searchParams.get('project'))));
   result={revision:pages[0].revision,items:pages.flatMap(page=>page.items||[]),more:false,next:null};
 }else result=await responder(action,args,u.searchParams.get('project'));
 return {ok:!result?.error,status:result?.error?409:200,json:async()=>result};}};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-canvas.js','utf8'),ctx);
let source=fs.readFileSync(process.argv[1]+'/knowledge.js','utf8');
source=source.replace('window.KnowledgeUI = {page, afterRender, notify};','window.__test={view,refresh,loadItem,resolveDocLinks,graphModel,graph,graphKey,hasDirectedCycle,graphState,nodeLabel,componentLevel,loadComponentLevel,matrix,cyElements,cyLayout,cyStyle,sizeGraph,mountGraph,destroyGraph,captureCamera,savePositions,focusCanvas,openCanvasItem,unmount,catalog,recordGraph,navigateGraph,selectItem,viewport,markdown,action,save,filtered,draw,request,persist,changedFragment,followNavigator,expandCanvas,chooseGraphItem,analysisStatus,loadCatalogTree,navigationPages,revealScope,canvasMatches,chartFilters,applyCanvasSearch,inspectorContent,inspectorItem,readInspectorItem,updateCanvasSelection,updateRoleDescription,canvasState,mounted:()=>mounted}; window.KnowledgeUI = {page, afterRender, notify};');
vm.runInContext(source,ctx);
const ui=ctx.window.KnowledgeUI,t=ctx.window.__test;
function mount(project='a',mode='docs'){
 ctx.location.hash='#'+mode;
 const html=ui.page(mode,{project});
 root={dataset:{kProject:project,kMode:mode},isConnected:true,contains:()=>false,
 querySelector:selector=>selector==='[data-k-body]'?body:null,querySelectorAll:()=>[],
 addEventListener:(name,handler)=>{root[name]=handler;}};
 ui.afterRender({project,projectApi:path=>path+'\x26project=wrong',showError:()=>{}});
 return {html,view:t.view(project,mode),root};
}
const settle=()=>new Promise(resolve=>setTimeout(resolve,10));
'''


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class KnowledgeUiTest(unittest.TestCase):
    def test_subsystem_actions_follow_inspector_content_and_never_enter_header(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/subsystems.js','utf8'),ctx);
const {view:v}=mount('architecture-actions','architecture');await settle();
ctx.window.KnowledgeResearch={actions:()=>'<section data-test-research-actions>Research actions</section>'};
v.filters.inspectorCollapsed=false;v.context=context;v.loading=false;
const subsystem={id:'app',type:'component',kind:'entity',title:'Application',description:'Purpose'};
v.items=[subsystem];v.selected='app';v.drafts.set('app',{item:subsystem,expected:7});
const html=t.inspectorContent(v,subsystem,v.drafts.get('app'));
assert(html.indexOf('data-test-research-actions')>html.indexOf('k-links'));
assert(html.indexOf('data-ui-key="subsystem-actions"')>html.indexOf('data-test-research-actions'));
assert.match(html,/data-subsystem-action="edit" data-subsystem-id="app"/);
assert.doesNotMatch(html,/data-subsystem-action="overview"/);
delete ctx.window.KnowledgeResearch;
t.draw(v);assert.doesNotMatch(body.innerHTML,/subsystem-toolbar|subsystem-manager|data-subsystem-action="toggle"/);
t.unmount();
''')

    def test_project_overview_inspector_has_project_scoped_actions(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/subsystems.js','utf8'),ctx);
const {view:v}=mount('architecture-root-actions','architecture');await settle();
v.filters.inspectorCollapsed=false;v.selected='';v.loading=false;v.context=context;
t.draw(v);
assert.match(body.innerHTML,/subsystem-project/);
for(const action of ['overview','first-level','new'])assert(body.innerHTML.includes('data-subsystem-action="'+action+'"'));
assert.doesNotMatch(body.innerHTML,/data-subsystem-action="edit"|data-subsystem-action="remove"|subsystem-toolbar/);
t.unmount();
''')

    def test_navigator_open_adopts_owner_reset_and_rejects_late_previous_result(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/knowledge-research.js','utf8'),ctx);ctx.window.KnowledgeResearch.mounted=()=>{};
const {view:v}=mount('navigator-open','architecture');await settle();const research=ctx.window.KnowledgeResearch;
const component=id=>({id,kind:'entity',type:'component',title:id}),child=id=>({id:'child:'+id,kind:'entity',type:'class',title:id});
let releaseOld,releaseStart;const held=new Promise(resolve=>releaseOld=resolve),starting=new Promise(resolve=>releaseStart=resolve);
research.state(v).jobs=[{id:'manual',state:'running',query:{intent:'research'}}];
responder=async(action,args)=>{
 if(action==='research-object')return component(args.id);
 if(action==='research'){if(args.query.id==='component:starting')await starting;return {id:args.query.id,query:args.query,state:'queued'};}
 if(action==='job'){if(args.id==='component:slow')await held;return {id:args.id,state:'ready',result:args.id};}
 if(action==='research-result')return {id:args.id,query:{id:args.id},status:'ready',items:[component(args.id),child(args.id)],more:false};
 if(action==='research-capabilities')return {operations:[]};
 throw Error('Unexpected '+action);
};
for(const id of ['component:first','component:second','component:first']){
 await research.open(v,id);assert.equal(v.selected,id);assert.equal(v.researchLoading,false);assert.deepEqual(Array.from(v.researchCanvas.nodes,n=>n.id),[id,'child:'+id]);assert.equal(research.state(v).branches.size,1);
}
const slow=research.open(v,'component:slow');await settle();assert.equal(v.researchLoading,true);
await research.open(v,'component:latest');releaseOld();await slow;
assert.equal(v.selected,'component:latest');assert.equal(v.researchLoading,false);assert.deepEqual(Array.from(v.researchCanvas.nodes,n=>n.id),['component:latest','child:component:latest']);
const opening=research.open(v,'component:starting');await settle();await research.open(v,'component:final');releaseStart();await opening;
assert.equal(v.selected,'component:final');assert.equal(v.researchLoading,false);assert.deepEqual(Array.from(v.researchCanvas.nodes,n=>n.id),['component:final','child:component:final']);
assert.equal(research.state(v).jobs.length,1,'Automatic section loads never enter the user journal');assert.equal(research.state(v).jobs[0].id,'manual');t.unmount();
''')

    def test_route_change_discards_previous_research_canvas_and_scope(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/knowledge-research.js','utf8'),ctx);ctx.window.KnowledgeResearch.mounted=()=>{};
const {view:v}=mount('route-change','architecture');await settle();t.selectItem(v,'class:old');
const old={nodes:[{id:'class:old',kind:'entity',type:'class'}],relations:[]},r=ctx.window.KnowledgeResearch.state(v);v.researchCanvas=old;v.researchLoading=true;r.baseline=old;r.branches.set('old-result',{root:'class:old'});r.dialog={type:'query'};const epoch=r.epoch;
t.selectItem(v,'class:old');assert.equal(v.researchCanvas,old,'Refreshing the current owner retains its explored canvas');
t.selectItem(v,'research:map:new');assert.equal(v.researchCanvas,null);assert.equal(v.researchLoading,false);assert.equal(r.baseline,null);assert.equal(r.branches.size,0);assert.equal(r.dialog,null);assert(r.epoch>epoch,'Late results cannot apply to the new route');t.unmount();
''')

    def test_large_source_navigator_is_retained_during_graph_and_dialog_updates(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/knowledge-research.js','utf8'),ctx);ctx.window.KnowledgeResearch.mounted=()=>{};
const {view:v}=mount('large-navigation','architecture');await settle();v.research.tab='sources';v.filters.followSelection=false;
v.catalogTreeItems=Array.from({length:2000},(_,i)=>({id:'file:'+i,type:'file',source:{path:'src/File'+i+'.java'}}));v.filters.fileTreeExpanded=true;
let renders=0;const fileTree=ctx.window.ArchitectureMap.fileTree;ctx.window.ArchitectureMap.fileTree=(...args)=>{renders++;return fileTree(...args);};
const pane={dataset:{kBrowserMode:'catalog'},querySelector:()=>null,querySelectorAll:()=>[],scrollTop:2000,scrollLeft:0};let navigator=null;
Object.defineProperty(body,'innerHTML',{configurable:true,get(){return this.html||''},set(html){this.html=html;navigator=html.includes('data-k-navigator-slot')?null:pane;}});
const slot={replaceWith(previous){navigator=previous;}};root.querySelector=s=>s==='[data-k-body]'?body:s==='.k-catalog'?navigator:s==='[data-k-navigator-slot]'?slot:null;
t.draw(v);assert.equal(renders,1);assert.equal(navigator,pane);
v.selected='file:999';v.research.dialog={type:'help'};t.draw(v);t.draw(v);assert.equal(renders,1,'Graph selection and dialogs never rebuild 2000 source rows');assert.equal(navigator,pane);assert.equal(pane.scrollTop,2000);
const oldLayout={},nextLayout={},nextMain={};let mainReplacements=0,bodyWrites=0;const oldMain={replaceWith:n=>{assert.equal(n,nextMain);mainReplacements++;}};
body.children=[oldLayout];body.querySelector=()=>null;body.insertBefore=()=>{};Object.defineProperty(body,'innerHTML',{configurable:true,set(){bodyWrites++;throw Error('The retained source tree must stay attached');}});
ctx.document.createElement=()=>({children:[nextLayout],set innerHTML(html){assert.match(html,/data-k-navigator-slot/);},querySelector:s=>s==='.k-layout'?nextLayout:s==='.k-architecture-main'?nextMain:null});
root.querySelector=s=>s==='[data-k-body]'?body:s==='.k-catalog'?pane:s==='.k-layout'?oldLayout:s==='.k-architecture-main'?oldMain:null;
t.draw(v);assert.equal(bodyWrites,0,'No ancestor replacement for an unchanged large tree');assert.equal(mainReplacements,1);assert.equal(renders,1);
delete ctx.document.createElement;root.querySelector=s=>s==='[data-k-body]'?body:s==='.k-catalog'?navigator:s==='[data-k-navigator-slot]'?slot:null;Object.defineProperty(body,'innerHTML',{configurable:true,get(){return this.html||''},set(html){this.html=html;navigator=html.includes('data-k-navigator-slot')?null:pane;}});
v.filters.query='File999';t.draw(v);assert.equal(renders,2,'Actual navigation changes invalidate the retained tree');t.unmount();
''')

    def test_pending_research_never_mounts_intermediate_node(self):
        self.run_node(r'''
const {view:v}=mount('pending-layout','architecture');await settle();v.initialized=true;v.loading=false;v.researchLoading=true;
let mountedNodes=0;ctx.window.cytoscape=()=>{mountedNodes++;throw Error('Intermediate graph must not mount');};
root.querySelector=s=>s==='[data-k-cy]'?{}:s==='[data-k-body]'?body:null;
t.mountGraph(v);assert.equal(mountedNodes,0);t.unmount();
''')

    def test_expand_all_folder_events_coalesce_storage_writes(self):
        self.run_node(r'''
const {view:v,root:r}=mount('folder-events','architecture');await settle();
const timers=new Map();let next=0,writes=0;ctx.setTimeout=fn=>{const id=++next;timers.set(id,fn);return id;};ctx.clearTimeout=id=>timers.delete(id);ctx.localStorage.setItem=()=>writes++;
for(let i=0;i<2000;i++)r.toggle({target:{dataset:{kFileFolder:'src/'+i},open:true,matches:()=>false}});
assert.equal(writes,0,'Opening a large tree does not synchronously persist every folder');assert.equal(timers.size,1);[...timers.values()][0]();assert.equal(writes,1);assert.equal(Object.keys(v.filters.fileFolders).length,2000);t.unmount();
''')

    def test_viewport_frame_and_unchanged_renderer_survive_dialog_and_resource_updates(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/knowledge-research.js','utf8'),ctx);ctx.window.KnowledgeResearch.mounted=()=>{};
const {view:v}=mount('frame','architecture');await settle();
const cy=require(process.argv[1]+'/vendor/cytoscape.js')({headless:true});t.mounted().cy=cy;cy.knowledgeKey=t.graphKey(v);
const child=kind=>({innerHTML:kind,matches:s=>s.split(',').includes(kind)}),toolbar=child('.r-graph-toolbar'),caption=child('.r-canvas-caption'),canvas=child('[data-k-cy]');
const status={hidden:true,textContent:''};let panel;
function makePanel(){return {className:'k-graph-panel r-panel',children:[child('.r-graph-toolbar'),child('.r-canvas-caption'),child('[data-k-cy]')],classList:{toggle(){}},querySelector:s=>s==='.r-graph-toolbar'?toolbar:s==='.r-canvas-caption'?caption:s==='[data-k-cy]'?canvas:s==='[data-r-research-status]'?status:null,replaceChildren(...children){this.children=children;},replaceWith(previous){panel=previous;},getAttribute:()=>null,removeAttribute(){},setAttribute(name,value){this[name]=value;}};}
const frame=makePanel();panel=frame;frame.className='k-graph-panel k-graph-wait';
frame.children=[toolbar,caption,canvas];let removals=0;frame.replaceChildren=(...children)=>{removals++;frame.children=children;};
Object.defineProperty(body,'innerHTML',{configurable:true,get(){return this.html||''},set(html){this.html=html;panel=makePanel();}});
root.querySelector=s=>s==='[data-k-body]'?body:s==='.k-graph-panel'?panel:null;
v.research.dialog={type:'help'};t.draw(v);assert.equal(panel,frame);assert.equal(cy.destroyed(),false);assert.equal(removals,0,'Cytoscape stops its renderer if the same container is removed then reinserted');assert.equal(frame.children[0],toolbar);assert.equal(frame.children[2],canvas);assert.equal(frame.className,'k-graph-panel r-panel','Do not keep the old loading-screen class');
v.loading=true;t.draw(v);assert.equal(panel,frame);assert.equal(cy.destroyed(),false);assert.equal(frame['aria-busy'],'true');assert.match(status.textContent,/Открываем раздел/);
v.loading=false;v.context={...v.context,revision:8};t.draw(v);assert.equal(panel,frame,'Changed content keeps the frame');assert.equal(cy.destroyed(),true,'Changed graph replaces the renderer');assert.equal(frame.children[0],toolbar);assert.notEqual(frame.children[2],canvas);t.unmount();
''')

    def test_follow_selection_reveals_sources_and_subsystems_in_content_scroller(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/knowledge-research.js','utf8'),ctx);ctx.window.KnowledgeResearch.mounted=()=>{};
const {view:v}=mount('follow','architecture');await settle();
const selected={id:'code:class',kind:'entity',type:'class',title:'Example',source:{path:'src/nested/Example.java'}};
v.canvasItem=selected.id;v.canvasInspect=selected;v.canvasSelection=[selected.id];v.catalogTreeItems=[selected];v.research.tab='sources';v.filters.browser='catalog';v.filters.fileFolders={};
let revealed=false,highlight=false,renders=0;const scroller={scrollTop:0,scrollLeft:0,getBoundingClientRect:()=>({top:100,bottom:300})};
const row={dataset:{kSelect:selected.id},classList:{toggle:(name,on)=>highlight=on},getBoundingClientRect:()=>({top:400,bottom:425}),parentElement:null};
const pane={dataset:{kBrowserMode:'catalog'},scrollTop:0,scrollLeft:0,querySelector:s=>s==='.r-tree'?scroller:null,querySelectorAll:()=>revealed?[row]:[],getBoundingClientRect:()=>({top:0,bottom:300})};
Object.defineProperty(pane,'outerHTML',{configurable:true,set:html=>{renders++;revealed=true;assert.match(html,/data-k-file-folder="src\/nested" open/);}});
root.querySelector=s=>s==='[data-k-body]'?body:s==='.k-catalog'?pane:null;
t.followNavigator(v);assert.equal(v.filters.fileFolders['src/nested'],true);assert.equal(renders,1);assert.equal(highlight,true);assert.equal(scroller.scrollTop,125);assert.equal(pane.scrollTop,0,'The pinned header does not scroll');
v.filters.followSelection=false;scroller.scrollTop=0;t.followNavigator(v);assert.equal(scroller.scrollTop,0);
const subsystem={id:'component:child',kind:'entity',type:'component',title:'Child',parent:'component:root'};v.componentItems=[{id:'component:root',type:'component',title:'Root'},subsystem];v.canvasItem=subsystem.id;v.canvasInspect=subsystem;v.canvasSelection=[subsystem.id];v.filters.followSelection=true;v.filters.browser='structure';v.research.tab='structure';pane.dataset.kBrowserMode='structure';v.filters.treeFolders={'component:root':false};row.dataset={rOpen:subsystem.id};row.setAttribute=(name,value)=>{row[name]=value;};row.removeAttribute=name=>delete row[name];
Object.defineProperty(pane,'outerHTML',{configurable:true,set:html=>{renders++;revealed=true;assert.match(html,/r-tree k-architecture-tree/);assert.match(html,/data-k-tree-folder="component:root" open/);}});
t.followNavigator(v);assert.equal(v.filters.treeFolders['component:root'],true);assert.equal(row['aria-current'],'page');assert.equal(scroller.scrollTop,125);t.unmount();
''')

    def test_saved_map_immediately_enters_navigator_without_reloading_canvas(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/knowledge-research.js','utf8'),ctx);ctx.window.KnowledgeResearch.mounted=()=>{};
const {view:v}=mount('saved-map','architecture');await settle();v.scenarios=[{id:'map:old',kind:'view',title:'Existing map'}];
const saved={id:'research:map:new',kind:'view',viewType:'research',title:'New map',nodeIds:['code:a'],orderedEdges:[]};let saves=0;
responder=async(action,args)=>{if(action==='research-save'){saves++;assert.deepEqual(args.nodeIds,['code:a']);return {id:saved.id,revision:8};}if(action==='context')return {...context,revision:8};if(action==='read'){assert.equal(args.id,saved.id);return saved;}throw Error('Unexpected '+action);};
const before=body.innerHTML;await v.__researchHost.saveMap('New map',{nodes:[{id:'code:a',kind:'entity',type:'class',title:'A'}],relations:[]});
assert.equal(saves,1);assert.equal(v.scenarios[0].id,saved.id);assert.equal(v.scenarios[1].id,'map:old');assert.equal(v.context.revision,8);assert.equal(body.innerHTML,before,'Saving updates only navigation');v.research.tab='maps';assert.match(t.catalog(v),/New map/);t.unmount();
''')

    def test_agent_revision_burst_retains_canvas_and_publishes_one_snapshot(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/knowledge-research.js','utf8'),ctx);ctx.window.KnowledgeResearch.mounted=()=>{};
const {view:v}=mount('events','architecture');await settle();
const component={id:'component:root',kind:'entity',type:'component',title:'Root'},old={id:'code:class',kind:'entity',type:'class',title:'Class',component:component.id};
v.selected=component.id;v.loadedSelection=component.id;v.drafts.set(component.id,{item:component,expected:7});v.researchCanvas={nodes:[component,old],relations:[]};v.research={...ctx.window.KnowledgeResearch.state(v),agent:{status:'running',actionId:'current'},baseline:{nodes:[old],relations:[]}};
const cy=require(process.argv[1]+'/vendor/cytoscape.js')({headless:true,elements:[{data:{id:component.id}},{data:{id:old.id}}]});t.mounted().cy=cy;cy.knowledgeKey=t.graphKey(v);body.innerHTML='existing canvas';
const timers=new Map();let next=0;ctx.setTimeout=(fn,delay)=>{const id=++next;timers.set(id,{fn,delay});return id;};ctx.clearTimeout=id=>timers.delete(id);
const before=requests.length;v.context={...v.context};context.revision=10;for(let rev=8;rev<=10;rev++)ui.notify('events',rev);
assert.equal(v.initialized,true);await ui.flushUpdates('events');assert.equal(requests.length,before,'No intermediate reads while agent writes');assert.equal(cy.destroyed(),false);assert.equal(body.innerHTML,'existing canvas');assert.equal(timers.size,1,'Revision bursts have one pending refresh');
let release;const blocked=new Promise(resolve=>release=resolve);let contexts=0;
responder=async(action,args)=>{if(!action)return {items:[]};if(action==='context'){if(++contexts===1)await blocked;return context;}if(action==='read')return args.id===component.id?component:{...old,component:'component:new'};if(action==='search')return {revision:10,items:args.type==='component'?[component,{id:'component:new',kind:'entity',type:'component',title:'New category',parent:component.id}]:[],more:false};if(action==='research-capabilities')return {operations:[]};throw Error('Unexpected '+action);};
v.research.agent.status='completed';const refresh=ui.flushUpdates('events');await settle();assert.equal(cy.destroyed(),false,'Keep old renderer throughout resource loading');assert.equal(body.innerHTML,'existing canvas');release();await refresh;
assert.equal(contexts,2,'One snapshot plus final consistency read');assert.equal(v.context.revision,10);assert.equal(v.pendingKnowledgeRevision,0);assert.equal(cy.destroyed(),true,'Replace renderer once snapshot is ready');assert.equal(v.researchCanvas.nodes.find(n=>n.id===old.id).component,'component:new');assert.equal(v.research.baseline.nodes[0].component,'component:new','Collapse cannot restore old ownership');assert.equal(t.graphModel(v).parents.get(old.id),'component:new');t.unmount();
''')

    def test_research_scope_loading_skips_legacy_neighbourhood_and_reuses_navigation(self):
        self.run_node(r'''
const selected={id:'code:entry',kind:'entity',type:'class',title:'Entry'};let opened=0;
vm.runInContext(fs.readFileSync(process.argv[1]+'/knowledge-research.js','utf8'),ctx);ctx.window.KnowledgeResearch.mounted=()=>{};ctx.window.KnowledgeResearch.open=async(v,id,prepared)=>{assert.equal(id,selected.id);assert.equal(prepared.title,'Entry');opened++;v.researchCanvas={nodes:[prepared],relations:[]};};
responder=async(action,args)=>{if(action==='context')return context;if(action==='read')return selected;if(action==='research-capabilities')return {operations:[]};if(action==='search'){assert.ok(['view','component',undefined].includes(args.type));assert.ok(args.kind==='view'||args.type==='component'||args.entrypoint==='true','The scope must not enumerate legacy code or relationships');return {revision:7,items:[],more:false,next:null};}throw Error('Unexpected '+action);};
ctx.location.hash='#architecture/code%3Aentry';ui.page('architecture',{project:'fast'});
root={dataset:{kProject:'fast',kMode:'architecture'},isConnected:true,contains:()=>false,querySelector:s=>s==='[data-k-body]'?body:null,querySelectorAll:()=>[],addEventListener(){}};
ui.afterRender({project:'fast'});await settle();const v=t.view('fast','architecture');assert.equal(opened,1);assert.equal(v.loading,false);
const navigationRequests=requests.filter(x=>x.action==='source-tree'&&x.args.mode==='navigation').length;assert.equal(navigationRequests,1);await t.refresh(v);assert.equal(requests.filter(x=>x.action==='source-tree'&&x.args.mode==='navigation').length,navigationRequests,'Unchanged navigation indexes are reused');assert.equal(opened,1,'Refresh preserves the current research canvas');
''')

    def test_cached_remount_and_revision_notifications_preserve_fresh_navigation(self):
        self.run_node(r'''
const {view:v}=mount();await settle();v.selected='doc:one';ctx.location.hash='#docs/doc%3Aone';ui.afterRender({project:'a'});await settle();
const reads=requests.filter(x=>x.action==='read').length;
ui.afterRender({project:'a'});await settle();assert.equal(requests.filter(x=>x.action==='read').length,reads);
const contexts=requests.filter(x=>x.action==='context').length;
ui.notify('other',8);ui.notify('a',7);await settle();assert.equal(requests.filter(x=>x.action==='context').length,contexts);
v.context={...v.context};context.revision=8;ui.notify('a',8);await settle();assert.ok(requests.filter(x=>x.action==='context').length>contexts);
assert.equal(v.context.revision,8);
''')

    def run_node(self, code):
        result = subprocess.run(['node', '-e', HARNESS + '\n(async()=>{\n' + code +
                                 '\n})().catch(error=>{console.error(error);process.exitCode=1;});', str(WEB)],
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_role_inspector_is_readable_and_reopens_editor(self):
        self.run_node(r'''
const {view:v}=mount('role','architecture');await settle();
const item={id:'code:role',kind:'entity',type:'class',title:'Role type',description:'A role description that remains readable in the inspector.'};
v.selected=item.id;v.canvasInspect=item;v.drafts.set(item.id,{item:{...item},expected:7,dirty:false});
let html=t.inspectorContent(v,item,v.drafts.get(item.id));
assert.doesNotMatch(html,/data-k-field="description"/);
assert.match(html,/data-k-action="edit-role-description"/);
v.roleExpanded={};const live=t.mounted(),originalRoot=live.root,panel={scrollHeight:100,clientHeight:100,classList:{remove(){}},getBoundingClientRect:()=>({width:220})},more={dataset:{kRoleId:item.id}};live.root={querySelector:selector=>selector==='.k-role-description'?panel:selector==='.k-role-more'?more:null};t.updateRoleDescription(v);assert.equal(more.hidden,true,'Short role text has no expand affordance');panel.scrollHeight=420;panel.clientHeight=100;t.updateRoleDescription(v);assert.equal(more.hidden,false,'Long role text exposes expand affordance');live.root=originalRoot;
await t.action(v,'edit-role-description',{dataset:{kRoleId:item.id}});assert.equal(v.panel,'role-description');t.draw(v);
assert.match(body.innerHTML,/data-k-field="description"/);
assert.match(body.innerHTML,/Изменить роль в проекте/);
await t.action(v,'close-panel',{dataset:{}});assert.equal(v.panel,'');t.draw(v);
assert.doesNotMatch(body.innerHTML,/Изменить роль в проекте/);
''')

    def test_canonical_inspector_data_and_actions_survive_all_graph_projections(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/subsystems.js','utf8'),ctx);
const {view:v}=mount('canonical-selection','architecture');await settle();
v.context=context;v.loading=false;v.filters.inspectorCollapsed=false;
const component={id:'app',kind:'entity',type:'component',title:'Application',description:'Authored subsystem role',documentRefs:['doc:app']};
const symbol={id:'code:type:service',kind:'entity',type:'class',title:'Service',description:'Authored class role',component:'app',source:{path:'src/service.py',line:3}};
v.componentItems=[{id:'app',kind:'entity',type:'component',title:'Application'}];
v.drafts.set(component.id,{item:component,expected:7,dirty:false});
v.drafts.set(symbol.id,{item:symbol,expected:7,dirty:false});
const seen=[];ctx.window.KnowledgeResearch={actions:(_v,item)=>{seen.push(item);return `<button data-test-agent="${item.id}">Describe</button>`;}};
for(const canonical of [component,symbol]){
  const projection={id:canonical.id,kind:'entity',type:canonical.type,title:canonical.title,description:''};
  v.selected=canonical.id;v.researchCanvas={nodes:[projection],relations:[]};
  const navigator=t.inspectorContent(v,canonical,v.drafts.get(canonical.id));
  for(const surface of ['overview','frame','sources']){
    v.selected=surface==='frame'?canonical.id:'';
    const projected=surface==='frame'?{...projection,collapsed:true,memberCount:2}:projection;
    v.researchCanvas={nodes:[projected],relations:[]};
    const html=t.inspectorContent(v,projected);
    assert.match(html,new RegExp(canonical.description));
    assert.match(html,/data-k-action="edit-role-description"/);
    assert.match(html,/data-k-action="history"/);
    assert.equal(seen.at(-1).id,canonical.id);
    assert.equal(seen.at(-1).description,canonical.description);
    if(canonical===component){assert.match(html,/data-subsystem-action="edit" data-subsystem-id="app"/);assert.match(navigator,/data-subsystem-action="edit" data-subsystem-id="app"/);}
    else assert.match(html,/src\/service.py:3/);
    if(surface==='frame')assert.equal(seen.at(-1).collapsed,true,'Layout flags stay local to the canvas');
  }
}
t.unmount();
''')

    def test_canvas_detail_reads_are_revisioned_deduplicated_and_keep_dirty_roles(self):
        self.run_node(r'''
const {view:v}=mount('detail-cache','architecture');await settle();v.context=context;
const projected={id:'app',kind:'entity',type:'component',title:'Application'};
let release,calls=0;responder=async(action,args)=>{assert.equal(action,'research-object');assert.equal(args.id,'app');calls++;return new Promise(resolve=>release=resolve);};
const first=t.readInspectorItem(v,projected),second=t.readInspectorItem(v,projected);
assert.equal(calls,1);release({...projected,description:'Saved role',documentRefs:['doc:app']});
assert.equal((await first).description,'Saved role');assert.equal((await second).description,'Saved role');
await t.readInspectorItem(v,projected);assert.equal(calls,1,'Reuse full details within the same revision');
v.context={...context,revision:8};
const stale=t.readInspectorItem(v,projected);v.context={...context,revision:9};release({...projected,description:'Stale role'});await stale;
assert.equal(v.drafts.get('app').item.description,'Saved role','Late reads cannot publish data from an older revision');
const pending=t.readInspectorItem(v,projected);v.drafts.set('app',{item:{...projected,description:'Unsaved role'},expected:9,dirty:true});release({...projected,description:'Server role'});await pending;
assert.equal(t.inspectorItem(v,projected).description,'Unsaved role');
await t.readInspectorItem(v,projected);assert.equal(calls,3,'Dirty edits never trigger an overwrite');
const group={id:'ui:group',type:'group',provenance:'presentation'};await t.readInspectorItem(v,group);assert.equal(calls,3,'Display categories have no canonical record');
t.unmount();
''')

    def test_pending_canvas_layout_cannot_be_reused_or_cached(self):
        self.run_node(r'''
const {view:v}=mount('pending-layout','architecture');await settle();
const live=t.mounted(),cy=require(process.argv[1]+'/vendor/cytoscape.js')({headless:true,elements:[{data:{id:'a'}}]});live.cy=cy;cy.knowledgeKey='pending';
const identity=cy.knowledgeKey,original=[{id:'old',x:12,y:24}];v.positionCache.set(identity,original);
cy.knowledgePending=true;
const snapshot=t.canvasState(v);
assert.equal(snapshot.layoutPending,true);assert.equal(snapshot.positions.size,0);assert.equal(snapshot.routes,null);
t.savePositions(v,cy);assert.deepEqual(v.positionCache.get(identity),original);
cy.knowledgePending=false;
''')

    def test_real_documentation_module_index_editor_and_scenario_return(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/documentation.js','utf8'),ctx);
responder=async(action,args)=>action==='context'?context:action==='search'?{revision:7,items:[{id:'doc:guide',kind:'document',audience:'developer',section:'Разработка / Сборка',title:'Guide'}],more:false,next:null}: {id:'doc:guide',kind:'document',title:'Guide',audience:'developer',section:'Разработка / Сборка',status:'current',markdown:'Body'};
const {view:v,root:r}=mount('spaces','docs');await settle();assert.equal(v.documentIndex.length,1);assert.match(body.innerHTML,/Разработка приложения/);
v.selected='doc:guide';await t.loadItem(v,v.selected);v.editing=true;t.draw(v);assert.match(body.innerHTML,/Папка/);assert.match(body.innerHTML,/Актуальная/);
assert.match(body.innerHTML,/data-k-field="status"/);assert.doesNotMatch(body.innerHTML,/>current<\/option>/);
v.filters.audience='developer';v.filters.section='Разработка / Сборка';await t.action(v,'new-doc');assert.equal(v.drafts.get(v.selected).item.audience,'developer');assert.equal(v.drafts.get(v.selected).item.section,'Разработка / Сборка');
v.returnArchitecture={project:v.project,selected:'view:scenario'};await t.action(v,'return-architecture');assert.equal(ctx.location.hash,'#architecture/view%3Ascenario');
''')

    def test_architecture_workspace_optional_panels_and_flex_canvas(self):
        self.run_node(r'''
const {view:v,root:r,html}=mount('workspace','architecture');await settle();
assert.match(html,/data-k-workspace="true"/);assert.match(html,/class="k-sr-only">Архитектура/);
assert.match(body.innerHTML,/k-inspector-container is-collapsed/);assert.match(body.innerHTML,/data-k-canvas-selection role="status" hidden><\/p>/);
assert.match(body.innerHTML,/<details class="k-graph-info">/);assert.doesNotMatch(body.innerHTML,/максимум 60/);
assert.equal((body.innerHTML.match(/class="k-info-content"/g)||[]).length,2);
await t.action(v,'toggle-inspector');assert.doesNotMatch(body.innerHTML,/k-inspector-container is-collapsed/);assert.match(body.innerHTML,/Закрыть панель сведений/);
await t.action(v,'toggle-inspector');assert.match(body.innerHTML,/k-inspector-container is-collapsed/);
r.dataset.kWorkspace='true';const container={style:{height:'200px'}};t.sizeGraph(container);assert.equal(container.style.height,'','Workspace height belongs to flex CSS');
''')

    def test_navigator_scroll_survives_selection_redraw_loading_and_root_replacement(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const {view:v,root:r}=mount('navigator-scroll','architecture');await settle();
let pane,maxTop=1000,maxLeft=100;
function scrollPane(mode){let top=0,left=0;return {dataset:{kBrowserMode:mode},get scrollTop(){return top},set scrollTop(value){top=Math.min(maxTop,Math.max(0,value))},get scrollLeft(){return left},set scrollLeft(value){left=Math.min(maxLeft,Math.max(0,value))}};}
Object.defineProperty(body,'innerHTML',{configurable:true,get(){return this.html||''},set(html){this.html=html;const mode=html.match(/data-k-browser-mode="([^"]+)"/);pane=mode?scrollPane(mode[1]):null;}});
function attach(target){target.querySelector=selector=>selector==='[data-k-body]'?body:selector==='.k-catalog'?pane:selector==='[data-k-navigator-slot]'?{replaceWith(previous){pane=previous;}}:null;}
attach(r);t.draw(v);
const click=(target,selector,item)=>target.click({preventDefault(){},target:{closest:s=>s===selector?item:null}});
for(const [mode,top,left] of [['structure',140,11],['graph',260,22],['catalog',380,33]]){
 click(r,'[data-k-browser]',{dataset:{kBrowser:mode}});await settle();
 pane.scrollTop=top;pane.scrollLeft=left;r.scroll({target:pane});
 const item={id:'selected-'+mode,kind:'entity',type:'class',title:mode};responder=async action=>action==='read'?item:action==='context'?context:{revision:7,items:[],more:false};
 click(r,'[data-k-select]',{dataset:{kSelect:item.id}});await settle();
 assert.equal(pane.scrollTop,top,mode+' selection keeps vertical scroll');assert.equal(pane.scrollLeft,left,mode+' selection keeps horizontal scroll');
 t.draw(v);assert.equal(pane.scrollTop,top,mode+' repeated redraw');
}
for(const [mode,top] of [['structure',140],['graph',260],['catalog',380]]){click(r,'[data-k-browser]',{dataset:{kBrowser:mode}});await settle();assert.equal(pane.scrollTop,top,'Each browser restores its own position');}
maxTop=0;maxLeft=0;t.draw(v);assert.equal(pane.scrollTop,0);r.scroll({target:pane});t.draw(v);
maxTop=1000;maxLeft=100;t.draw(v);assert.equal(pane.scrollTop,380,'A temporarily short/loading list must not erase desired position');assert.equal(pane.scrollLeft,33);
// Scroll events save offsets before the framework removes the old root.
pane.scrollTop=420;r.scroll({target:pane});r.isConnected=false;t.unmount();
const replacement={dataset:{kProject:v.project,kMode:'architecture'},isConnected:true,contains:()=>false,querySelectorAll:()=>[],addEventListener(name,handler){this[name]=handler;}};attach(replacement);root=replacement;
ui.afterRender({project:v.project});await settle();assert.equal(pane.scrollTop,420);assert.equal(pane.scrollLeft,33);
pane.scrollTop=70;replacement.scroll({target:pane});t.draw(v);assert.equal(pane.scrollTop,70,'User scrolling replaces the saved desired position');t.unmount();
''')

    def test_fresh_native_cose_component_map_is_not_a_degenerate_column(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const {view:v,root:r}=mount('dense-map','architecture');await settle();
v.filters.graphMode='components';v.selected='';v.componentItems=Array.from({length:6},(_,i)=>({id:'component'+i,kind:'entity',type:'component',title:'Module '+i,parent:null}));
v.selected='view:graph-start';v.drafts.set(v.selected,{item:{id:v.selected,kind:'view',nodeIds:['old'],orderedEdges:['old-edge']}});
v.relations=v.componentItems.flatMap((node,i)=>[1,2,3].map(offset=>({id:'edge'+i+'-'+offset,kind:'relation',from:node.id,to:'component'+(i+offset)%6,type:'depends-on',count:3})));
const options=t.cyLayout(v);assert.equal(options.name,'cose');assert.equal(options.randomize,false);
assert.ok(t.cyElements(v).filter(e=>e.group==='nodes').every(e=>e.data.width===160&&e.data.font===14),'Component cards use modest title sizing');
const container={};r.querySelector=selector=>selector==='[data-k-cy]'?container:selector==='[data-k-body]'?body:null;
const instances=[],layouts=[];ctx.window.cytoscape=options=>{
 assert.equal(options.layout.name,'preset','Constructor must not start force layout before resize');
 const cy=cytoscape({headless:true,styleEnabled:true,elements:JSON.parse(JSON.stringify(options.elements)),style:JSON.parse(JSON.stringify(options.style)),layout:{name:'preset'},minZoom:.01});
 let resized=false;cy.width=()=>resized?707:1;cy.height=()=>resized?240:1;cy.resize=()=>{resized=true;return cy;};
 const nativeLayout=cy.layout.bind(cy);cy.layout=options=>{assert.ok(resized);layouts.push(options);return nativeLayout({...options,boundingBox:options.boundingBox?JSON.parse(JSON.stringify(options.boundingBox)):undefined,positions:options.positions?JSON.parse(JSON.stringify(options.positions)):undefined});};
 const nativeViewport=cy.viewport.bind(cy);cy.viewport=options=>nativeViewport(JSON.parse(JSON.stringify(options)));instances.push(cy);return cy;
};
try{
for(let attempt=0;attempt<3;attempt++){
 v.positionCache.clear();v.cameraInitialized=false;t.draw(v);let cy=instances.at(-1);
 const seed=layouts.findLast(options=>options.name==='grid');assert.equal(seed.boundingBox.w,707);assert.equal(seed.boundingBox.h,240);
 assert.equal(layouts.at(-1).boundingBox.w,707);assert.equal(layouts.at(-1).boundingBox.h,240);
 const world=cy.nodes().boundingBox({includeLabels:false});assert.ok(world.w/world.h>.35&&world.w/world.h<6,'Native force layout must not collapse into a pathological column/row');
 const bounds=cy.nodes().renderedBoundingBox({includeLabels:false});assert.ok(bounds.x1>=31.9&&bounds.x2<=675.1&&bounds.y1>=31.9&&bounds.y2<=208.1);
 assert.ok(cy.zoom()*parseFloat(cy.nodes().first().style('font-size'))>=8,'Dense six-component labels remain at least8 rendered pixels after fit: '+JSON.stringify({world,zoom:cy.zoom()}));
 assert.equal(v.positionCache.get(cy.knowledgeKey).length,6);const saved=JSON.stringify(v.positionCache.get(cy.knowledgeKey));t.draw(v);
 cy=instances.at(-1);assert.equal(layouts.at(-1).name,'preset');assert.equal(JSON.stringify(v.positionCache.get(t.graphKey(v))),saved);
 cy.knowledgeRoutes=new Map([['edge0-1',[{x:0,y:0},{x:20,y:20}]]]);
 await t.action(v,'auto-layout');assert.equal(cy.knowledgeRoutes,null,'A force layout must discard routes computed for an earlier ELK layout');assert.equal(v.routeCache.has(cy.knowledgeKey),false);
 for(let repeat=0;repeat<3;repeat++){await t.action(v,'auto-layout');assert.equal(JSON.stringify(v.positionCache.get(t.graphKey(v))),saved,'Repeated native force layout must reproduce positions');}
}
}finally{t.unmount();for(const cy of instances)cy.destroy();}
''')

    def test_native_force_layout_keeps_rectangular_cards_apart(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const {view:v,root:r}=mount('card-collisions','architecture');await settle();
const container={};r.querySelector=selector=>selector==='[data-k-cy]'?container:selector==='[data-k-body]'?body:null;
let frame={w:707,h:321};const instances=[];
ctx.window.cytoscape=options=>{
 const cy=cytoscape({headless:true,styleEnabled:true,elements:JSON.parse(JSON.stringify(options.elements)),style:JSON.parse(JSON.stringify(options.style)),layout:{name:'preset'},minZoom:.01});
 cy.width=()=>frame.w;cy.height=()=>frame.h;
 const nativeLayout=cy.layout.bind(cy);cy.layout=options=>nativeLayout({...options,boundingBox:options.boundingBox?JSON.parse(JSON.stringify(options.boundingBox)):undefined,positions:options.positions?JSON.parse(JSON.stringify(options.positions)):undefined});
 const nativeViewport=cy.viewport.bind(cy);cy.viewport=options=>nativeViewport(JSON.parse(JSON.stringify(options)));instances.push(cy);return cy;
};
function assertApart(cy,label){
 const nodes=cy.nodes().toArray();
 for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){
  const a=nodes[i].boundingBox({includeLabels:true}),b=nodes[j].boundingBox({includeLabels:true});
  assert.ok(a.x2<=b.x1||b.x2<=a.x1||a.y2<=b.y1||b.y2<=a.y1,label+': overlapping cards '+JSON.stringify({frame,aId:nodes[i].id(),bId:nodes[j].id(),a,b,aPosition:nodes[i].position(),bPosition:nodes[j].position()}));
 }
 const bounds=cy.nodes().renderedBoundingBox();assert.ok(bounds.x1>=31.9&&bounds.y1>=31.9&&bounds.x2<=frame.w-31.9&&bounds.y2<=frame.h-31.9,'Fit must include every card: '+JSON.stringify({label,frame,bounds,zoom:cy.zoom()}));
}
try{
 for(const fixture of ['disconnected-overview','star-neighborhood'])for(frame of [{w:707,h:321},{w:2400,h:900},{w:600,h:950}]){
  v.filters.layout='cose';v.selected=fixture==='disconnected-overview'?'n18':'n0';v.filters.graphMode=fixture==='disconnected-overview'?'overview':'neighborhood';
  v.items=Array.from({length:fixture==='disconnected-overview'?19:42},(_,i)=>({id:'n'+i,kind:'entity',type:fixture==='disconnected-overview'&&i<14?'component':['class','record','file'][i%3],title:'ArchitectureCardWithALongDescriptiveName'+i,component:'app',entrypoint:fixture==='disconnected-overview'&&i>=14&&i<18}));
  v.neighbors=v.items;v.relations=fixture==='disconnected-overview'?[]:v.items.slice(1).map((node,i)=>({id:'e'+i,from:i%2?node.id:'n0',to:i%2?'n0':node.id,type:'uses'}));
  v.drafts.set(v.selected,{item:v.items.find(node=>node.id===v.selected)});t.destroyGraph();v.positionCache.clear();v.cameraInitialized=false;t.draw(v);
  let cy=instances.at(-1);assert.equal(cy.nodes().length,v.items.length);assertApart(cy,fixture+' initial');
  const positions=JSON.stringify(v.positionCache.get(cy.knowledgeKey));
  for(let repeat=0;repeat<2;repeat++){await t.action(v,'auto-layout');assertApart(cy,fixture+' repeat'+repeat);assert.equal(JSON.stringify(v.positionCache.get(cy.knowledgeKey)),positions,'Force layout must remain deterministic');}
  t.draw(v);cy=instances.at(-1);assertApart(cy,fixture+' refresh');assert.equal(JSON.stringify(v.positionCache.get(cy.knowledgeKey)),positions,'Refresh must retain the corrected layout');
 }
}finally{t.unmount();for(const cy of instances)cy.destroy();}
''')

    def test_native_edge_routing_changes_preserve_graph_and_camera(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const {view:v,root:r}=mount('edge-routes','architecture');await settle();
v.filters.graphMode='neighborhood';v.items=[{id:'a',kind:'entity',type:'class',title:'Source'},{id:'b',kind:'entity',type:'interface',title:'Target'}];
v.relations=[{id:'uses',from:'a',to:'b',type:'uses',provenance:'source'},{id:'inherits',from:'a',to:'b',type:'implements',provenance:'source'},{id:'reverse',from:'b',to:'a',type:'reads',provenance:'authored'}];
const container={},instances=[];r.querySelector=selector=>selector==='[data-k-cy]'?container:selector==='[data-k-body]'?body:null;
ctx.window.cytoscape=options=>{
 const cy=cytoscape({headless:true,styleEnabled:true,elements:JSON.parse(JSON.stringify(options.elements)),style:JSON.parse(JSON.stringify(options.style)),layout:{name:'preset'},minZoom:.01});
 cy.width=()=>900;cy.height=()=>600;
 const nativeLayout=cy.layout.bind(cy);cy.layout=options=>nativeLayout({...options,boundingBox:options.boundingBox?JSON.parse(JSON.stringify(options.boundingBox)):undefined,positions:options.positions?JSON.parse(JSON.stringify(options.positions)):undefined});
 const nativeViewport=cy.viewport.bind(cy);cy.viewport=options=>nativeViewport(JSON.parse(JSON.stringify(options)));instances.push(cy);return cy;
};
try{
 t.draw(v);let cy=instances.at(-1);cy.getElementById('a').select();cy.pan({x:71,y:93});cy.zoom(.8);
 const before={positions:JSON.stringify(cy.nodes().map(node=>node.position())),pan:JSON.stringify(cy.pan()),zoom:cy.zoom(),requests:requests.length,sequence:cy.knowledgeLayoutSequence,graphKey:cy.knowledgeKey};
 assert.doesNotMatch(t.graph(v),/data-k-edge-style/);
 assert.equal(v.filters.edgeStyle,undefined);
 assert.ok(cy.edges().every(edge=>edge.style('curve-style')==='round-taxi'));
 t.draw(v);cy=instances.at(-1);
 assert.equal(JSON.stringify(cy.nodes().map(node=>node.position())),before.positions);
 assert.equal(JSON.stringify(cy.pan()),before.pan);assert.equal(cy.zoom(),before.zoom);
 assert.equal(t.view('other-edge-project','architecture').filters.edgeStyle,undefined);
}finally{t.unmount();for(const cy of instances)cy.destroy();}
''')

    def test_native_canvas_selection_focus_automatic_positions_and_camera_scope(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const {view:v,root:r}=mount('interactions','architecture');await settle();
v.items=[{id:'one',kind:'entity',type:'class',title:'First',component:'app',description:'Purpose'},
 {id:'two',kind:'entity',type:'class',title:'Second'}];v.relations=[{id:'edge',from:'one',to:'two',type:'uses',evidence:[{path:'src/example',line:12}]}];
const originalResponder=responder;let finishDetails;
responder=async(action,args,project)=>action==='research-object'?new Promise(resolve=>finishDetails=()=>resolve({...v.items.find(n=>n.id===args.id),description:'Canonical role'})):originalResponder(action,args,project);
v.filters.graphMode='overview';const selection={textContent:''};const container={};
r.querySelector=selector=>selector==='[data-k-cy]'?container:selector==='[data-k-body]'?body:selector==='[data-k-canvas-selection]'?selection:null;
const instances=[];
ctx.window.cytoscape=options=>{const cloneLayout=options=>{const layout={...options};if(layout.boundingBox)layout.boundingBox=JSON.parse(JSON.stringify(layout.boundingBox));if(layout.positions)layout.positions=JSON.parse(JSON.stringify(layout.positions));if(layout.transform){const transform=layout.transform;layout.transform=(node,pos)=>JSON.parse(JSON.stringify(transform(node,pos)));}return layout;};const layout=cloneLayout(options.layout);
 const cy=cytoscape({headless:true,styleEnabled:true,elements:JSON.parse(JSON.stringify(options.elements)),style:JSON.parse(JSON.stringify(options.style)),layout,minZoom:options.minZoom,maxZoom:options.maxZoom,
   autoungrabify:options.autoungrabify,userPanningEnabled:options.userPanningEnabled,boxSelectionEnabled:options.boxSelectionEnabled,selectionType:options.selectionType});
 const nativeViewport=cy.viewport.bind(cy),nativeLayout=cy.layout.bind(cy);cy.viewport=options=>nativeViewport(JSON.parse(JSON.stringify(options)));cy.layout=options=>nativeLayout(cloneLayout(options));
 cy.width=()=>707;cy.height=()=>321;instances.push(cy);return cy;};
try {
t.draw(v);let cy=instances.at(-1),node=cy.getElementById('one');const before=requests.length,scope=v.selected,html=body.innerHTML;
assert.equal(v.positionCache.get(t.graphKey(v)).length,2,'Initial native layout must persist automatic positions');
assert.equal(cy.autoungrabify(),true,'Mouse dragging cannot modify automatic placement');assert.ok(cy.nodes().every(n=>!n.grabbable()),'All nodes and compound groups follow automatic placement');assert.equal(cy.userPanningEnabled(),false,'Left mouse keeps box selection');assert.equal(cy.boxSelectionEnabled(),true);
node.select();node.emit('tap');assert.equal(v.selected,scope);assert.equal(v.filters.graphMode,'overview');assert.equal(requests.length,before+1);assert.equal(requests.at(-1).action,'research-object');assert.equal(body.innerHTML,html);
assert.match(selection.textContent,/First.*Класс.*Application.*Purpose/);
await settle();
cy.getElementById('edge').emit('tap');assert.match(selection.textContent,/src\/example:12/);assert.equal(requests.length,before+1);
finishDetails();await settle();assert.equal(v.canvasInspect.id,'edge','Late canonical details cannot replace a different canvas selection');
cy.getElementById('two').select();await settle();assert.equal(v.canvasSelection.length,2);assert.equal(v.canvasStats.nodeCount,2);assert.equal(v.canvasStats.internalCount,1);assert.match(selection.textContent,/Выбрано: 2/);
await t.action(v,'clear-selection');await settle();assert.equal(v.canvasSelection.length,0);assert.equal(v.canvasStats,null);assert.equal(v.canvasInspect,null);
node.select();cy.getElementById('edge').select();await settle();assert.equal(v.canvasSelection.length,2);assert.equal(v.canvasStats.selectedRelationCount,1);assert.equal(v.canvasStats.nodeCount,1);
await t.action(v,'clear-selection');await settle();
node.position({x:100,y:150});node.emit('dragfree');assert.equal(v.positionCache.get(t.graphKey(v)).find(p=>p.id==='one').x,100);
cy.pan({x:57,y:91});cy.zoom(.9);cy.emit('pan zoom');const cameraKey=v.cameraKey;t.draw(v);
assert.ok(cy.destroyed());cy=instances.at(-1);assert.equal(cy.getElementById('one').position('x'),100);assert.equal(v.cameraKey,cameraKey);
assert.equal(cy.pan('x'),57);assert.equal(cy.zoom(),.9);
cy.getElementById('one').select();await t.action(v,'focus');assert.ok(cy.zoom()<=1.5);
let prevented=false;const focusedRequests=requests.length;cy.zoom(.2);handlers.keydown({key:'а',code:'KeyF',target:{closest:()=>null},preventDefault:()=>prevented=true});assert.ok(prevented);assert.ok(cy.zoom()>.2);assert.equal(requests.length,focusedRequests);assert.equal(v.selected,scope);
prevented=false;handlers.keydown({key:'F',code:'KeyF',target:{isContentEditable:true,closest:()=>null},preventDefault:()=>prevented=true});assert.equal(prevented,false);
await t.action(v,'auto-layout');assert.ok(v.positionCache.has(t.graphKey(v)));
const directedPositions=JSON.stringify(v.positionCache.get(t.graphKey(v)));for(let repeat=0;repeat<3;repeat++){await t.action(v,'auto-layout');assert.equal(JSON.stringify(v.positionCache.get(t.graphKey(v))),directedPositions);}
v.viewport={x:1e8,y:1e8,scale:1};v.cameraKey=t.graphKey(v);t.destroyGraph();v.viewport={x:1e8,y:1e8,scale:1};t.mountGraph(v);
cy=instances.at(-1);assert.ok(Math.abs(cy.pan('x'))<1e6,'A fresh mount may recover an invalid saved camera');
t.destroyGraph();v.viewport={x:1e8,y:1e8,scale:1};t.mountGraph(v,{resetCamera:true,relayout:true,anchor:'file-not-in-symbol-result',camera:{x:1e8,y:1e8,scale:1}});
cy=instances.at(-1);assert.ok(Math.abs(cy.pan('x'))<1e6,'Opening a file without file nodes fits its symbols rather than preserving the previous canvas camera');
const oldKey=t.graphKey(v);v.items.push({id:'third',kind:'entity',type:'interface',title:'Third'});assert.notEqual(t.graphKey(v),oldKey);
t.draw(v);cy=instances.at(-1);cy.getElementById('one').emit('dbltap');assert.equal(v.selected,'one');assert.equal(v.filters.graphMode,'neighborhood');
t.unmount();assert.ok(cy.destroyed());
} finally {t.unmount();for(const instance of instances)instance.destroy();}
''')

    def test_auto_layout_preserves_camera_and_centers_selected_elements(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const {view:v,root:r}=mount('layout-camera','architecture');await settle();
v.filters.graphMode='overview';v.items=[{id:'n1',kind:'entity',type:'class',title:'One'},{id:'n2',kind:'entity',type:'class',title:'Two'},{id:'n3',kind:'entity',type:'class',title:'Three'}];v.relations=[{id:'e12',from:'n1',to:'n2',type:'uses'},{id:'e23',from:'n2',to:'n3',type:'uses'}];
const container={};r.querySelector=selector=>selector==='[data-k-cy]'?container:selector==='[data-k-body]'?body:null;const instances=[];
ctx.window.cytoscape=options=>{const cy=cytoscape({headless:true,styleEnabled:true,elements:JSON.parse(JSON.stringify(options.elements)),style:JSON.parse(JSON.stringify(options.style)),layout:{name:'preset'},minZoom:.01,maxZoom:4,boxSelectionEnabled:options.boxSelectionEnabled,selectionType:options.selectionType});const nativeLayout=cy.layout.bind(cy),nativeViewport=cy.viewport.bind(cy);cy.layout=o=>nativeLayout({...o,boundingBox:o.boundingBox?JSON.parse(JSON.stringify(o.boundingBox)):undefined});cy.viewport=o=>nativeViewport(JSON.parse(JSON.stringify(o)));cy.width=()=>800;cy.height=()=>500;instances.push(cy);return cy;};
try{t.draw(v);let cy=instances.at(-1);cy.pan({x:27,y:41});cy.zoom(.73);cy.getElementById('n1').select();const anchorBefore={...cy.getElementById('n1').renderedPosition()};await t.action(v,'auto-layout');assert.equal(cy.zoom(),.73,'Selected auto-layout preserves zoom');let box=cy.getElementById('n1').renderedBoundingBox({includeLabels:false});assert.ok(Math.abs((box.x1+box.x2)/2-anchorBefore.x)<2&&Math.abs((box.y1+box.y2)/2-anchorBefore.y)<2,'Selected node keeps its screen anchor after layout');
cy.elements().unselect();cy.pan({x:61,y:19});cy.zoom(.81);await t.action(v,'auto-layout');assert.equal(cy.pan('x'),61);assert.equal(cy.pan('y'),19);assert.equal(cy.zoom(),.81,'Unselected auto-layout preserves camera');
cy.getElementById('e12').select();cy.pan({x:0,y:0});cy.zoom(.69);await t.action(v,'auto-layout');assert.equal(cy.zoom(),.69,'Selected edge auto-layout preserves zoom');const edgeBox=cy.getElementById('e12').renderedBoundingBox();assert.ok(Math.abs((edgeBox.x1+edgeBox.x2)/2-400)<2&&Math.abs((edgeBox.y1+edgeBox.y2)/2-250)<2,'Selected edge is centered');
cy.elements().unselect();cy.getElementById('n1').select();cy.getElementById('n3').select();cy.zoom(.42);await t.action(v,'auto-layout');box=cy.elements(':selected').renderedBoundingBox();assert.equal(cy.zoom(),.42);assert.ok(Math.abs((box.x1+box.x2)/2-400)<2&&Math.abs((box.y1+box.y2)/2-250)<2,'Multiple selected nodes are centered together');}
finally{t.unmount();for(const cy of instances)cy.destroy();}
''')

    def test_async_elk_completion_keeps_current_camera_and_rejects_stale_runs(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const {view:v,root:r}=mount('elk-camera','architecture');await settle();v.filters.graphMode='overview';v.filters.layout='elk';v.items=[{id:'a',kind:'entity',type:'class',title:'A'},{id:'b',kind:'entity',type:'class',title:'B'}];v.relations=[{id:'ab',from:'a',to:'b',type:'uses'}];
ctx.window.ELK=function(){};
const container={};r.querySelector=selector=>selector==='[data-k-cy]'?container:selector==='[data-k-body]'?body:null;const instances=[];ctx.window.cytoscape=options=>{const cy=cytoscape({headless:true,styleEnabled:true,elements:JSON.parse(JSON.stringify(options.elements)),style:JSON.parse(JSON.stringify(options.style)),layout:{name:'preset'},minZoom:.01,maxZoom:4});const nativeViewport=cy.viewport.bind(cy);cy.viewport=o=>nativeViewport(JSON.parse(JSON.stringify(o)));cy.width=()=>800;cy.height=()=>500;instances.push(cy);return cy;};
const originalElk=ctx.window.ArchitectureMap.elkLayout,pending=[];ctx.window.ArchitectureMap.elkLayout=(cy,complete,valid)=>new Promise(resolve=>pending.push({cy,complete,valid,resolve}));
try{t.draw(v);let cy=instances.at(-1);assert.equal(pending.length,1);pending[0].complete();cy.pan({x:11,y:17});cy.zoom(.77);await t.action(v,'auto-layout');await t.action(v,'auto-layout');assert.equal(pending.length,3);cy.pan({x:31,y:47});cy.zoom(.63);pending[1].complete();assert.equal(cy.pan('x'),31);assert.equal(cy.pan('y'),47);assert.equal(cy.zoom(),.63,'Stale ELK completion cannot overwrite current camera');pending[2].complete();assert.equal(cy.pan('x'),31);assert.equal(cy.pan('y'),47);assert.equal(cy.zoom(),.63,'Current ELK completion keeps navigation during wait');}
finally{ctx.window.ArchitectureMap.elkLayout=originalElk;t.unmount();for(const cy of instances)cy.destroy();}
''')

    def test_default_elk_routes_survive_drag_and_redraw_with_safe_failure_fallback(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js'),ELK=require(process.argv[1]+'/vendor/elk-api.js'),worker=require(process.argv[1]+'/vendor/elk-worker.min.js');
let elkRuns=0;ctx.window.ELK=function(){const engine=new ELK({workerFactory:()=>new worker.Worker()}),layout=engine.layout.bind(engine);engine.layout=g=>{elkRuns++;return layout(JSON.parse(JSON.stringify(g)))};return engine;};
data.set('knowledge:default-elk:architecture',JSON.stringify({filters:{layout:'cose',edgeStyle:'taxi'}}));
const {view:v,root:r}=mount('default-elk','architecture');await settle();assert.equal(v.filters.layout,'elk','Legacy algorithm choices migrate to ELK');assert.equal(v.filters.edgeStyle,undefined,'Legacy shape selection is removed');
v.items=Array.from({length:4},(_,i)=>({id:'n'+i,kind:'entity',type:'class',title:'Node '+i}));v.relations=[{id:'e01',from:'n0',to:'n1',type:'uses'},{id:'e02',from:'n0',to:'n2',type:'uses'},{id:'e23',from:'n2',to:'n3',type:'imports'}];
const container={},instances=[];r.querySelector=selector=>selector==='[data-k-cy]'?container:selector==='[data-k-body]'?body:null;
ctx.window.cytoscape=options=>{const cy=cytoscape({headless:true,styleEnabled:true,elements:JSON.parse(JSON.stringify(options.elements)),style:JSON.parse(JSON.stringify(options.style)),layout:{name:'preset'},minZoom:.01,maxZoom:4});const nativeLayout=cy.layout.bind(cy),nativeViewport=cy.viewport.bind(cy);cy.layout=o=>nativeLayout({...o,boundingBox:o.boundingBox?JSON.parse(JSON.stringify(o.boundingBox)):undefined,positions:o.positions?JSON.parse(JSON.stringify(o.positions)):undefined});cy.viewport=o=>nativeViewport(JSON.parse(JSON.stringify(o)));cy.width=()=>800;cy.height=()=>500;instances.push(cy);return cy;};
try{
 t.draw(v);let cy=instances.at(-1);for(let i=0;i<50&&!v.routeCache.has(cy.knowledgeKey);i++)await settle();assert.equal(elkRuns,1);assert.equal(cy.knowledgeRoutes.size,3);assert.doesNotMatch(body.innerHTML,/<select data-k-layout\b|<option value="taxi"/);assert.equal(t.cyLayout(v).name,'elk');
 const unchanged=JSON.stringify(cy.knowledgeRoutes.get('e23')),style=cy.getElementById('e23').style('segment-distances'),moved=cy.getElementById('n1'),before={...moved.position()},end={...cy.knowledgeRoutes.get('e01').at(-1)};
 moved.position({x:before.x+40,y:before.y+55});moved.emit('drag');await new Promise(resolve=>setTimeout(resolve,25));assert.equal(JSON.stringify(cy.knowledgeRoutes.get('e23')),unchanged);assert.equal(cy.getElementById('e23').style('segment-distances'),style);assert.equal(cy.knowledgeRoutes.get('e01').at(-1).x,end.x+40);assert.equal(cy.knowledgeRoutes.get('e01').at(-1).y,end.y+55);
 moved.emit('dragfree');const routes=JSON.stringify([...cy.knowledgeRoutes]);cy.pan({x:37,y:61});cy.zoom(.68);t.draw(v);cy=instances.at(-1);assert.equal(elkRuns,1,'Redraw restores routes without running ELK');assert.equal(JSON.stringify([...cy.knowledgeRoutes]),routes);assert.equal(cy.pan('x'),37);assert.equal(cy.zoom(),.68);
 ctx.window.ArchitectureMap.elkLayout=async()=>{throw Error('test unavailable')};cy.getElementById('n0').select();cy.zoom(.61);const anchorBefore={...cy.getElementById('n0').renderedPosition()};await t.action(v,'auto-layout');await settle();assert.equal(cy.zoom(),.61,'Fallback keeps selected zoom');assert.equal(cy.knowledgeRoutes,null);assert.match(v.notice,/резервное размещение/);const position=cy.getElementById('n0').renderedPosition();assert.ok(Math.abs(position.x-anchorBefore.x)<2&&Math.abs(position.y-anchorBefore.y)<2,'Fallback preserves the selected screen anchor');
}finally{t.unmount();for(const cy of instances)cy.destroy();}
''')

    def test_group_route_events_are_coalesced_and_flushed_before_saving(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');const {view:v,root:r}=mount('route-events','architecture');await settle();
v.filters.graphMode='neighborhood';v.componentItems=[{id:'component:group',kind:'entity',type:'component',title:'Group'}];
v.items=[{id:'a',kind:'entity',type:'class',component:'group'},{id:'b',kind:'entity',type:'record',component:'group'},{id:'outside',kind:'entity',type:'enum'}];v.relations=[{id:'ab',from:'a',to:'b',type:'uses'},{id:'out',from:'b',to:'outside',type:'uses'}];
const container={},instances=[];r.querySelector=s=>s==='[data-k-cy]'?container:s==='[data-k-body]'?body:null;
ctx.window.cytoscape=options=>{const cy=cytoscape({headless:true,styleEnabled:true,elements:JSON.parse(JSON.stringify(options.elements)),style:JSON.parse(JSON.stringify(options.style)),layout:{name:'preset'}});const nativeLayout=cy.layout.bind(cy);cy.layout=o=>nativeLayout({...o,boundingBox:o.boundingBox?JSON.parse(JSON.stringify(o.boundingBox)):undefined});cy.width=()=>800;cy.height=()=>500;instances.push(cy);return cy;};
const frames=new Map();let serial=0;ctx.window.requestAnimationFrame=callback=>{frames.set(++serial,callback);return serial};ctx.window.cancelAnimationFrame=id=>frames.delete(id);
try{
t.draw(v);const cy=instances.at(-1),group=cy.getElementById('component:group');assert.equal(group.descendants().length,2);
const calls=[],nativeRoutes=ctx.window.ArchitectureMap.routeEdges;ctx.window.ArchitectureMap.routeEdges=(instance,style,edges)=>{calls.push(edges.map(e=>e.id()).sort().join(','));nativeRoutes(instance,style,edges)};
group.emit('position');cy.getElementById('a').emit('position');cy.getElementById('b').emit('position');assert.equal(calls.length,0,'No partial group routing inside position events');const frame=cy.knowledgeRouteFrame;frames.get(frame)();assert.deepEqual(calls,['ab,out'],'One frame includes descendant incident edges');assert.equal(cy.knowledgeRoutePending,null);
group.emit('position');assert.ok(cy.knowledgeRouteFrame);group.emit('dragfree');assert.deepEqual(calls,['ab,out','ab,out'],'Release synchronously flushes final routes');assert.equal(cy.knowledgeRouteFrame,null);assert.ok(v.positionCache.has(cy.knowledgeKey));
group.emit('position');const pendingFrame=cy.knowledgeRouteFrame;t.unmount();assert.ok(!frames.has(pendingFrame),'Unmount cancels route work');
}finally{t.unmount();for(const cy of instances)cy.destroy();}
''')

    def test_compound_route_lanes_survive_large_and_repeated_group_moves(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const cy=cytoscape({headless:true,styleEnabled:true,elements:[
 {data:{id:'group'}},{data:{id:'left-a',parent:'group'}},{data:{id:'left-b',parent:'group'}},{data:{id:'target'}},
 {data:{id:'fan-a',source:'left-a',target:'target'}},{data:{id:'fan-b',source:'left-b',target:'target'}}
],style:[{selector:'node',style:{width:40,height:30}},{selector:'edge',style:{'curve-style':'round-taxi'}}],layout:{name:'preset'}});
cy.getElementById('left-a').position({x:100,y:100});cy.getElementById('left-b').position({x:100,y:180});cy.getElementById('target').position({x:500,y:140});
cy.knowledgeRoutes=new Map([
 ['fan-a',[{x:120,y:100},{x:220,y:100},{x:220,y:300},{x:480,y:300},{x:480,y:140}]],
 ['fan-b',[{x:120,y:180},{x:280,y:180},{x:280,y:340},{x:480,y:340},{x:480,y:140}]]
]);
try{
const map=ctx.window.ArchitectureMap;map.routeEdges(cy,'round-taxi');
const laneKeys=()=>[...cy.edges()].map(edge=>JSON.stringify(cy.knowledgeRoutes.get(edge.id()).slice(1,3)));
const first=laneKeys();assert.ok(new Set(first).size>=2,'Initial fan-in routes must have distinct lanes');
const translatedBefore=new Map([...cy.knowledgeRoutes].map(([id,points])=>[id,points.map(p=>({...p}))]));
for(const id of ['left-a','left-b','target']){const n=cy.getElementById(id),p=n.position();n.position({x:p.x+80,y:p.y+60});}
map.routeEdges(cy,'round-taxi');
for(const [id,before] of translatedBefore){const after=cy.knowledgeRoutes.get(id);assert.equal(after.length,before.length);assert.ok(after.every((p,i)=>Math.abs(p.x-before[i].x-80)<1e-6&&Math.abs(p.y-before[i].y-60)<1e-6),'Common translation must preserve every ELK bend');}
map.finishRoutes(cy);
for(const id of ['left-a','left-b']){const n=cy.getElementById(id),p=n.position();n.position({x:p.x+700,y:p.y+430});}
map.routeEdges(cy,'round-taxi');map.finishRoutes(cy);
const moved=laneKeys();assert.ok(new Set(moved).size>=2,'Large compound movement must preserve separate trunk lanes');
for(const id of ['left-a','left-b']){const n=cy.getElementById(id),p=n.position();n.position({x:p.x-260,y:p.y+190});}
map.routeEdges(cy,'round-taxi');map.finishRoutes(cy);
const repeated=laneKeys();assert.ok(new Set(repeated).size>=2,'Repeated moves must not collapse fan-in lanes');
}finally{cy.destroy();}
''')

    def test_terminal_route_fallback_keeps_same_endpoint_fan_in_lanes(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const cy=cytoscape({headless:true,styleEnabled:true,elements:[
 {data:{id:'source'}},{data:{id:'target'}},
 {data:{id:'lane-a',source:'source',target:'target'}},{data:{id:'lane-b',source:'source',target:'target'}}
],style:[{selector:'node',style:{width:40,height:30}},{selector:'edge',style:{'curve-style':'round-taxi'}}],layout:{name:'preset'}});
cy.getElementById('source').position({x:100,y:300});cy.getElementById('target').position({x:500,y:300});
cy.knowledgeRoutes=new Map([
 ['lane-a',[{x:120,y:300},{x:200,y:300},{x:200,y:100},{x:400,y:100},{x:400,y:300},{x:480,y:300}]],
 ['lane-b',[{x:120,y:300},{x:200,y:300},{x:200,y:500},{x:400,y:500},{x:400,y:300},{x:480,y:300}]]
]);
try{
const map=ctx.window.ArchitectureMap;map.routeEdges(cy,'round-taxi');map.finishRoutes(cy);
for(const id of ['source','target']){const n=cy.getElementById(id),p=n.position();n.position({x:p.x+80,y:p.y+60});}
map.routeEdges(cy,'round-taxi');map.finishRoutes(cy);
const source=cy.getElementById('source');source.position({x:source.position('x')+700,y:source.position('y')+430});
map.routeEdges(cy,'round-taxi');
const trunkYs=()=>[...cy.edges()].map(edge=>cy.knowledgeRoutes.get(edge.id())[2].y);
assert.equal(new Set(trunkYs()).size,2,'Fallback must retain distinct same-endpoint trunk lanes');
map.finishRoutes(cy);source.position({x:source.position('x')-260,y:source.position('y')+190});
map.routeEdges(cy,'round-taxi');
assert.equal(new Set(trunkYs()).size,2,'Repeated source moves must retain distinct trunk lanes');
}finally{cy.destroy();}
''')

    def test_target_crossing_terminal_knees_preserves_inner_elk_bends(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const cy=cytoscape({headless:true,styleEnabled:true,elements:[
 {data:{id:'source'}},{data:{id:'target'}},
 {data:{id:'upper',source:'source',target:'target'}},{data:{id:'lower',source:'source',target:'target'}}
],style:[{selector:'node',style:{width:40,height:30}},{selector:'edge',style:{'curve-style':'round-taxi'}}],layout:{name:'preset'}});
cy.getElementById('source').position({x:100,y:300});cy.getElementById('target').position({x:500,y:300});
cy.knowledgeRoutes=new Map(['upper','lower'].map((id,i)=>[id,[
 {x:120,y:300},{x:200,y:300},{x:200,y:i?500:100},{x:400,y:i?500:100},{x:400,y:300},{x:480,y:300}
]]));
try{
 const map=ctx.window.ArchitectureMap;map.routeEdges(cy,'round-taxi');map.finishRoutes(cy);
 for(const position of [{x:280,y:200},{x:760,y:700},{x:280,y:200}]){
  cy.getElementById('target').position(position);map.routeEdges(cy,'round-taxi');
  for(const [id,y] of [['upper',100],['lower',500]]){
   const p=cy.knowledgeRoutes.get(id);
   assert.equal(p.length,6,'Endpoint crossing must retain both internal ELK bends');
   assert.ok(p.some((v,i)=>i&&v.y===y&&p[i-1].y===y),'Original inner channel remains');
   assert.equal(Math.abs(p.at(-1).x-p.at(-2).x),80,'Approach length moves with the port instead of becoming a shared long band');
   assert.ok(p.slice(1).every((v,i)=>v.x===p[i].x||v.y===p[i].y));
  }
  map.finishRoutes(cy);
 }
}finally{cy.destroy();}
''')

    def test_compound_target_move_preserves_many_incoming_trunks(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js'),elements=[
 {data:{id:'target-group'}},{data:{id:'target',parent:'target-group'}},{data:{id:'target-sibling',parent:'target-group'}}
],routes=[];
for(let i=0;i<40;i++){
 const id=`source-${i}`,y=40+i*18;elements.push({data:{id}});
 elements.push({data:{id:`incoming-${i}`,source:id,target:'target'}});
 routes.push([`incoming-${i}`,[{x:120,y},{x:280,y},{x:280,y:600+i*18},{x:480,y:600+i*18},{x:480,y:300}]]);
}
const cy=cytoscape({headless:true,styleEnabled:true,elements,style:[{selector:'node',style:{width:40,height:30}},{selector:'edge',style:{'curve-style':'round-taxi'}}],layout:{name:'preset'}});
for(let i=0;i<40;i++)cy.getElementById(`source-${i}`).position({x:100,y:40+i*18});
cy.getElementById('target').position({x:500,y:300});cy.getElementById('target-sibling').position({x:560,y:360});
cy.knowledgeRoutes=new Map(routes);
try{
const map=ctx.window.ArchitectureMap;map.routeEdges(cy,'round-taxi');map.finishRoutes(cy);
const group=cy.getElementById('target-group'),target=cy.getElementById('target'),sibling=cy.getElementById('target-sibling');
const assertRoutes=label=>{
 const trunkYs=[...cy.edges()].map(edge=>cy.knowledgeRoutes.get(edge.id())[2].y);
 assert.ok(new Set(trunkYs).size>=30,label+' preserves most incoming trunk lanes');
 for(const edge of cy.edges()){
  const points=cy.knowledgeRoutes.get(edge.id());assert.ok(points.every(p=>Number.isFinite(p.x)&&Number.isFinite(p.y)),label+' keeps finite routes');
  assert.ok(points.slice(1).every((p,i)=>p.x===points[i].x||p.y===points[i].y),label+' keeps orthogonal routes');
 }
};
const siblingOffset={x:sibling.position('x')-target.position('x'),y:sibling.position('y')-target.position('y')};
// Move the compound target across the retained vertical trunks. This is the
// routeEdges path used by a group drag, rather than a direct terminalRoute call.
for(const position of [{x:280,y:100},{x:760,y:700},{x:280,y:100}]){
 group.position(position);map.routeEdges(cy,'round-taxi');assertRoutes(`Compound move ${position.x},${position.y}`);map.finishRoutes(cy);
 assert.equal(sibling.position('x')-target.position('x'),siblingOffset.x,'Compound move preserves sibling X offset');
 assert.equal(sibling.position('y')-target.position('y'),siblingOffset.y,'Compound move preserves sibling Y offset');
}
}finally{cy.destroy();}
''')

    def test_type_fill_colors_match_legend_and_survive_selection(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js'),types=['class','interface','enum','record','component','file','external'];
const cy=cytoscape({headless:true,styleEnabled:true,elements:types.map(type=>({data:{id:type,type,label:type,font:12,width:195,height:72}})),style:JSON.parse(JSON.stringify(t.cyStyle))});
try{const fills=types.map(type=>cy.getElementById(type).style('background-color'));assert.equal(new Set(fills).size,types.length,'Each type has a distinct fill');cy.zoom(.03);for(const type of types){const n=cy.getElementById(type),fill=n.style('background-color');n.select();n.addClass('active');assert.equal(n.style('background-color'),fill,'Selection retains type color');assert.equal(n.style('background-opacity'),'1');}
const {view:v}=mount('colors','architecture');await settle();const html=t.graph(v);for(const type of types){const rule=t.cyStyle.find(s=>s.selector===`node[type="${type}"]`&&s.style['background-color']);assert.ok(html.includes(`data-k-type="${type}" style="--k-node-fill:${rule.style['background-color']};--k-node-border:${rule.style['border-color']}"`),'Legend uses rendered palette');}}finally{cy.destroy();t.unmount();}
''')

    def test_branch_expansion_pagination_collapse_and_grouping_preserve_camera(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const {view:v,root:r}=mount('branch-camera','architecture');await settle();
v.filters.graphMode='overview';v.filters.groupBy='none';v.items=[{id:'a',kind:'entity',type:'class',title:'A'},{id:'keep',kind:'entity',type:'class',title:'Keep'}];v.relations=[];
const container={},instances=[];r.querySelector=selector=>selector==='[data-k-cy]'?container:selector==='[data-k-body]'?body:null;
ctx.window.cytoscape=options=>{
 const cy=cytoscape({headless:true,styleEnabled:true,elements:JSON.parse(JSON.stringify(options.elements)),style:JSON.parse(JSON.stringify(options.style)),layout:{name:'preset'},minZoom:.01,maxZoom:4});
 const nativeLayout=cy.layout.bind(cy),nativeViewport=cy.viewport.bind(cy);
 cy.layout=o=>nativeLayout({...o,boundingBox:o.boundingBox?JSON.parse(JSON.stringify(o.boundingBox)):undefined,positions:o.positions?JSON.parse(JSON.stringify(o.positions)):undefined});
 cy.viewport=o=>nativeViewport(JSON.parse(JSON.stringify(o)));cy.width=()=>800;cy.height=()=>500;instances.push(cy);return cy;
};
const camera=cy=>({pan:{...cy.pan()},zoom:cy.zoom()}),points=cy=>Object.fromEntries(cy.nodes().map(n=>[n.id(),{...n.position()}]));
const assertPinned=(cy,before,label)=>{for(const id of Object.keys(before)){const n=cy.getElementById(id);assert.ok(n.length&&Number.isFinite(n.position('x'))&&Number.isFinite(n.position('y')),label+' retains '+id);}};
let release,blockInitial=true;responder=async(action,args)=>{
 if(action==='context')return context;
 if(action==='read')return {id:args.id,kind:'entity',type:'class',title:args.id};
 if(args.kind==='relation'&&args.endpoint==='a'&&!args.type){
  if(args.offset==='0'&&blockInitial){blockInitial=false;await new Promise(resolve=>release=resolve);}
  return args.offset==='1'?{revision:7,items:[{id:'ac',kind:'relation',from:'a',to:'c',type:'uses'}],more:false,next:null}:{revision:7,items:[{id:'ab',kind:'relation',from:'a',to:'b',type:'uses'}],more:true,next:1};
 }
 return {revision:7,items:[],more:false,next:null};
};
try{
 t.draw(v);let cy=instances.at(-1);cy.getElementById('a').position({x:100,y:150});cy.getElementById('keep').position({x:600,y:400});cy.getElementById('a').select();await settle();v.canvasItem='a';
 const before=points(cy),oldKey=cy.knowledgeKey;
 const expanding=t.action(v,'expand-direct',{dataset:{kBranchMode:'neighbors'}});await settle();assert.equal(typeof release,'function');
 cy.pan({x:43,y:79});cy.zoom(.58);const latest=camera(cy);release();await expanding;cy=instances.at(-1);
 assert.notEqual(cy.knowledgeKey,oldKey);assert.equal(cy.zoom(),latest.zoom,'Expansion keeps the zoom while compacting');const pinned=cy.getElementById('a').renderedPosition();assert.ok(Math.abs(pinned.x-(before.a.x*latest.zoom+latest.pan.x))<1e-6&&Math.abs(pinned.y-(before.a.y*latest.zoom+latest.pan.y))<1e-6,'Expansion keeps selected screen anchor');assertPinned(cy,before,'Expansion');assert.equal(cy.nodes().length,3);assert.ok(Number.isFinite(cy.getElementById('b').position('x')));
 const expanded=points(cy);await t.action(v,'more-branch');cy=instances.at(-1);assert.equal(cy.nodes().length,4);assert.equal(cy.zoom(),latest.zoom);assertPinned(cy,expanded,'Pagination');
 const completedAnchor=cy.getElementById('a').renderedPosition();await t.action(v,'collapse-branch');cy=instances.at(-1);assert.equal(cy.nodes().length,2);assert.equal(cy.zoom(),latest.zoom);assertPinned(cy,before,'Collapse');assert.ok(cy.getElementById('a').selected());const collapsedAnchor=cy.getElementById('a').renderedPosition();assert.ok(Math.abs(collapsedAnchor.x-completedAnchor.x)<=1&&Math.abs(collapsedAnchor.y-completedAnchor.y)<=1,'Completed collapse keeps the selected screen anchor');
 cy.knowledgePending=true;await t.action(v,'expand-direct',{dataset:{kBranchMode:'neighbors'}});cy=instances.at(-1);const pendingAnchor=cy.getElementById('a').renderedPosition();assert.ok(pendingAnchor.x>1&&pendingAnchor.y>1,'Pending structural redraw keeps the selected anchor visible');
 // Expanding a component turns its card into a compound frame at the old center.
 v.branchMaps?.clear();
 v.items=[{id:'app',kind:'entity',type:'component',title:'App'},{id:'outside',kind:'entity',type:'class',title:'Outside',entrypoint:true}];v.componentItems=[v.items[0]];v.relations=[];v.filters.groupBy='components';t.destroyGraph();v.cameraInitialized=false;t.draw(v);cy=instances.at(-1);
 cy.getElementById('app').position({x:140,y:180});cy.getElementById('outside').position({x:1200,y:800});cy.pan({x:-250,y:61});cy.zoom(.72);cy.getElementById('app').select();await settle();v.canvasItem='app';const groupBefore=points(cy),groupCamera=camera(cy);
 responder=async(action,args)=>action==='context'?context:args.kind==='entity'?{revision:7,items:[{id:'child1',kind:'entity',type:'class',title:'Child 1',component:'app'},{id:'child2',kind:'entity',type:'class',title:'Child 2',component:'app'}],more:false,next:null}:{revision:7,items:[],more:false,next:null};
 await t.action(v,'expand-direct',{dataset:{kBranchMode:'structure'}});cy=instances.at(-1);assert.ok(cy.getElementById('app').isParent());assert.equal(cy.zoom(),groupCamera.zoom);assertPinned(cy,groupBefore,'Compound expansion');
 const grouped=points(cy);r.change({target:{value:'none',matches:selector=>selector==='[data-k-group-by]'}});cy=instances.at(-1);assert.equal(cy.zoom(),groupCamera.zoom);assertPinned(cy,grouped,'Ungrouping');
 r.change({target:{value:'components',matches:selector=>selector==='[data-k-group-by]'}});cy=instances.at(-1);assert.equal(cy.zoom(),groupCamera.zoom);assertPinned(cy,grouped,'Regrouping');
 await t.action(v,'collapse-branch');cy=instances.at(-1);assert.equal(cy.nodes().length,2);assert.equal(cy.zoom(),groupCamera.zoom);assertPinned(cy,groupBefore,'Compound collapse');
}finally{t.unmount();for(const cy of instances)cy.destroy();}
''')

    def test_adaptive_layout_edge_semantics_and_explicit_docs_return(self):
        self.run_node(r'''
const {view:v,root:r}=mount('semantics','architecture');await settle();
v.items=[{id:'a',kind:'entity',type:'class',title:'A'},{id:'b',kind:'entity',type:'interface',title:'B'}];
v.filters.graphMode='neighborhood';v.relations=[{id:'ab',from:'a',to:'b',type:'implements'}];
assert.equal(t.cyLayout(v).name,'breadthfirst');v.relations.push({id:'ba',from:'b',to:'a',type:'uses'});assert.equal(t.cyLayout(v).name,'cose');
v.filters.layout='breadthfirst';assert.equal(t.cyLayout(v).name,'breadthfirst');v.filters.layout='cose';assert.equal(t.cyLayout(v).name,'cose');
assert.ok(t.cyStyle.some(style=>style.selector==='edge'&&style.style.label==='data(countLabel)'));
assert.ok(t.cyStyle.some(style=>style.selector.includes('edge:selected')&&style.style.label==='data(label)'));
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const colorCy=cytoscape({headless:true,styleEnabled:true,elements:[{data:{id:'a',label:'A',font:12,width:195,height:72}},{data:{id:'b',label:'B',font:12,width:195,height:72}},
 ...['implements','contains','depends-on','starts','unknown'].map(type=>({data:{id:type,source:'a',target:'b',type,provenance:'authored',countLabel:'',label:type}}))],style:JSON.parse(JSON.stringify(t.cyStyle))});
try{assert.equal(colorCy.getElementById('implements').style('line-color'),'rgb(94,182,162)');assert.equal(colorCy.getElementById('contains').style('line-color'),'rgb(180,156,222)');assert.equal(colorCy.getElementById('depends-on').style('line-color'),'rgb(110,166,216)');assert.equal(colorCy.getElementById('unknown').style('line-color'),'rgb(215,167,86)');assert.equal(colorCy.getElementById('implements').style('line-style'),'dashed');}finally{colorCy.destroy();}
assert.match(t.graph(v),/data-k-edge="inheritance"/);assert.match(t.graph(v),/F — вписать выбранные узлы/);
v.selected='a';v.viewport={x:12,y:23,scale:.7};v.cameraKey=t.graphKey(v);t.persist(v);
const doc={dataset:{kOpenDoc:'doc:guide'}};r.click({preventDefault(){},target:{closest:selector=>selector==='[data-k-open-doc]'?doc:null}});
assert.equal(ctx.location.hash,'#docs/doc%3Aguide');assert.match(ui.page('docs',{project:'semantics'}),/Вернуться к архитектуре/);
await t.action(t.view('semantics','docs'),'return-architecture');assert.equal(ctx.location.hash,'#architecture/a');assert.equal(v.viewport.x,12);
v.selected='view:scenario';t.persist(v);r.click({preventDefault(){},target:{closest:selector=>selector==='[data-k-open-doc]'?doc:null}});
await t.action(t.view('semantics','docs'),'return-architecture');assert.equal(ctx.location.hash,'#architecture/view%3Ascenario');
assert.doesNotMatch(ui.page('docs',{project:'other-project'}),/Вернуться к архитектуре/);
''')

    def test_scenario_to_component_modes_keeps_level_dependencies(self):
        self.run_node(r'''
const {view:v}=mount('switch-scenario','architecture');await settle();
const components=[{id:'a',kind:'entity',type:'component',title:'Source',parent:null},{id:'b',kind:'entity',type:'component',title:'Target',parent:null}];
const edge={id:'dependency',kind:'relation',type:'depends-on',from:'a',to:'b',count:9};
const scenario={id:'view:old',kind:'view',title:'Old scenario',nodeIds:['old-code'],orderedEdges:['old-start']};
v.selected=scenario.id;v.drafts.set(scenario.id,{item:scenario,dirty:false});
const updatedContext={...context,revision:8};
responder=async(action,args)=>action==='context'?updatedContext:action==='read'?scenario:args.kind==='view'?{revision:8,items:[scenario],more:false}:args.kind==='document'?{revision:8,items:[],more:false}:args.kind==='relation'?{revision:8,items:[edge],more:false}:{revision:8,items:components,total:2,more:false};
for(const mode of ['components','matrix']){
 t.chooseGraphItem(v,'',{graphMode:'components',presentation:mode==='matrix'?'matrix':'map'});await settle();
 assert.equal(v.relations.length,1);assert.equal(v.relations[0].id,'dependency');assert.equal(v.relations[0].count,9);
 assert.equal(t.graphModel(v).relations[0].type,'depends-on');assert.match(t.matrix(v),/9 статических связей/);
 assert.doesNotMatch(body.innerHTML,/aria-label="Порядок сценария"/);
 assert.doesNotMatch(body.innerHTML,/<h2>Old scenario<\/h2>/);
 assert.equal(v.drafts.get(scenario.id).item.title,'Old scenario');
}
assert.equal(requests.some(request=>request.action==='read'&&['old-code','old-start'].includes(request.args.id)),false);
''')

    def test_browser_qa_camera_migration_layout_and_named_links(self):
        self.run_node(r'''
data.set('knowledge:legacy:architecture',JSON.stringify({selected:'view:story',viewport:{x:-1900,y:-2000,scale:.25}}));
const legacy=t.view('legacy','architecture');assert.equal(legacy.cameraInitialized,false);assert.equal(legacy.viewport.x,0);assert.equal(legacy.viewport.scale,1);
legacy.viewport={x:17,y:25,scale:1.7};t.persist(legacy);
const current=JSON.parse(data.get('knowledge:legacy:architecture'));assert.equal(current.cameraEngine,'cytoscape-3.33.1');
data.set('knowledge:native:architecture',JSON.stringify({...current,selected:''}));
const native=t.view('native','architecture');assert.equal(native.cameraInitialized,true);assert.equal(native.viewport.x,17);assert.equal(native.viewport.scale,1.7);
const {view:v}=mount('names','architecture');await settle();
v.selected='view:story';v.drafts.set(v.selected,{item:{id:v.selected,kind:'view',title:'Scenario',documentRefs:['doc:hash']},dirty:false});
v.neighbors=[{id:'code:hash1',kind:'entity',title:'SCMain'},{id:'code:hash2',kind:'entity',title:'GraphModel'}];
v.linkedDocs=[{id:'doc:hash',kind:'document',title:'Architecture guide'}];
v.relations=[{id:'edge:hash',from:'code:hash1',to:'code:hash2',type:'uses'}];v.scenarios=[{id:'view:story',title:'Scenario'}];
t.draw(v);assert.match(body.innerHTML,/>SCMain<\/a>/);assert.match(body.innerHTML,/>GraphModel<\/a>/);assert.match(body.innerHTML,/>Architecture guide<\/a>/);
assert.doesNotMatch(body.innerHTML,/>code:hash[12]<\/a>|>doc:hash<\/a>|>uses · edge:hash/);
assert.match(body.innerHTML,/k-inspector-section/);
assert.ok(body.innerHTML.indexOf('k-graph-panel')<body.innerHTML.indexOf('k-inspector-section'));
assert.doesNotMatch(source,/wheelSensitivity/);
const css=fs.readFileSync(process.argv[1]+'/knowledge.css','utf8');
assert.match(css,/k-inspector-container/);assert.match(css,/overflow:hidden/);
assert.match(css,/k-architecture-main>\.k-component-grid \{ display:block/);
''')

    def test_real_native_fit_frames_all_displayed_chain_nodes(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const elements=Array.from({length:60},(_,i)=>({data:{id:'chain'+i},position:{x:i*1000,y:i*800}}));
const cy=cytoscape({headless:true,styleEnabled:true,minZoom:.01,maxZoom:4,elements,layout:{name:'preset'},style:[{selector:'node',style:{width:195,height:72}}]});
try {
 // Headless has no DOM container: provide the explicit renderer viewport dimensions.
 cy.width=()=>1000;cy.height=()=>700;cy.fit(undefined,32);
 assert.ok(cy.zoom()<.25);assert.ok(cy.zoom()>=.01);
 const box=cy.nodes().renderedBoundingBox({includeLabels:false});
 assert.ok(box.x1>=31.9&&box.y1>=31.9);assert.ok(box.x2<=968.1&&box.y2<=668.1);
}finally{cy.destroy();}
''')

    def test_component_semantic_level_matrix_limits_and_cache(self):
        self.run_node(r'''
const {view:v,root:r}=mount('components','architecture');await settle();
v.componentItems=[{id:'parent',kind:'entity',type:'component',title:'Application',parent:null},
 ...Array.from({length:35},(_,i)=>({id:'c'+i,kind:'entity',type:'component',title:'Module '+i,parent:'parent'})),
 {id:'other',kind:'entity',type:'component',title:'Other root',parent:null}];
v.filters.graphMode='matrix';v.selected='parent';
assert.equal(t.componentLevel(v).length,35);assert.ok(t.componentLevel(v).every(n=>n.parent==='parent'));
const edge={id:'dependency',kind:'relation',type:'depends-on',from:'c0',to:'c1',count:7,provenance:'source',resolution:'aggregate-syntax'};
responder=async(action,args)=>({revision:7,items:args.endpoint==='c0'||args.endpoint==='c1'?[edge]:[],more:args.endpoint==='c2'});
const start=requests.length,result=await t.loadComponentLevel(v);assert.equal(requests.length-start,35);
assert.ok(requests.slice(start).every(q=>q.args.type==='depends-on'&&q.args.endpoint&&q.args.limit==='100'));
assert.equal(result.items.length,1);assert.equal(result.more,true);
await t.loadComponentLevel(v);assert.equal(requests.length-start,35);
v.context={...context,revision:8};await t.loadComponentLevel(v);assert.equal(requests.length-start,70);
v.relations=result.items;v.componentPartial=result.more;
const html=t.matrix(v);assert.match(html,/7 статических связей/);assert.match(html,/Матрица неполная/);
assert.match(html,/>\?<\/td>/);assert.doesNotMatch(html,/Другие|Other root/);
t.recordGraph(v);const before=v.navigation.length;
const cell={dataset:{kMatrixFrom:'c0',kMatrixTo:'c1',kMatrixEdge:'dependency'}};
r.click({preventDefault(){},target:{closest:selector=>selector==='[data-k-matrix-from]'?cell:null}});
assert.equal(v.selected,'c0');assert.equal(v.filters.graphMode,'neighborhood');assert.equal(v.filters.focusTarget,'c1');
assert.equal(v.navigation.length,before+1);
''')

    def test_compact_architecture_tools_and_diagnostics(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const {html,view:v}=mount('compact','architecture');await settle();
assert.match(body.innerHTML,/data-k-action="tools"/);assert.match(body.innerHTML,/data-k-action="diagnostics"/);
assert.doesNotMatch(body.innerHTML,/k-diagnostics|k-capability/);
await t.action(v,'diagnostics');assert.match(body.innerHTML,/role="dialog" aria-modal="true" aria-label="Состояние анализа"/);
await t.action(v,'close-panel');assert.doesNotMatch(body.innerHTML,/role="dialog"/);
await t.action(v,'toggle-list');assert.match(t.catalog(v),/k-collapsed/);
const css=fs.readFileSync(process.argv[1]+'/knowledge.css','utf8');
assert.match(css,/main:has\(.knowledge-root\[data-k-mode="architecture"\]\)\s*\{ max-width:none/);
assert.match(html,/data-k-workspace="true"/);assert.match(body.innerHTML,/k-inspector-container/);assert.match(body.innerHTML,/k-graph-info/);
''')

    def test_visible_canvas_height_and_short_scenario_native_layout(self):
        self.run_node(r'''
const container={style:{},getBoundingClientRect:()=>({top:374.89})};
for(const height of [720,900]){ctx.window.innerHeight=height;t.sizeGraph(container);const size=Number.parseInt(container.style.height);assert.ok(size>=250);assert.ok(374.89+size<=height-24);}
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const {view:v}=mount('short-native','architecture');await settle();
v.selected='view:four';v.filters.graphMode='neighborhood';
v.context={...context,policy:{...context.policy,components:[{id:'parent',title:'Очень длинная область пользовательского приложения'},{id:'leaf',parent:'parent',title:'UI и запуск'}]}};
v.neighbors=Array.from({length:4},(_,i)=>({id:'step'+i,kind:'entity',type:'class',title:['SCMain','ProjectModel','GraphModel','View'][i],component:'leaf',description:'Длинное назначение компонента, которое раньше растягивало узел на девять строк и делало подписи нечитаемыми.'}));
v.relations=Array.from({length:3},(_,i)=>({id:'edge'+i,kind:'relation',from:'step'+i,to:'step'+(i+1),type:'uses'}));
v.drafts.set(v.selected,{item:{kind:'view',nodeIds:v.neighbors.map(n=>n.id),orderedEdges:v.relations.map(r=>r.id)}});
const layout=t.cyLayout(v);assert.equal(layout.spacingFactor,1.6);assert.equal(typeof layout.transform,'function');
const compact=t.cyElements(v).filter(element=>element.group==='nodes');assert.ok(compact.every(element=>element.data.height<=110));assert.ok(compact.every(element=>element.data.label.split('\n').length<=4));assert.ok(compact.every(element=>decodeURIComponent(element.data.metadataImage.split(',').slice(1).join(',')).includes('UI и запуск')));assert.ok(compact.every(element=>!decodeURIComponent(element.data.metadataImage.split(',').slice(1).join(',')).includes('Длинное назначение')&&!decodeURIComponent(element.data.metadataImage.split(',').slice(1).join(',')).includes('Очень длинная')));
const cy=cytoscape({headless:true,styleEnabled:true,minZoom:.01,elements:JSON.parse(JSON.stringify(t.cyElements(v))),style:JSON.parse(JSON.stringify(t.cyStyle))});
try {
cy.width=()=>707;cy.height=()=>321;
cy.layout({...layout,transform:(node,position)=>JSON.parse(JSON.stringify(layout.transform(node,position))),boundingBox:{x1:0,y1:0,w:707,h:321}}).run();cy.fit(undefined,32);
const nodes=cy.nodes();assert.ok(nodes[0].position('x')<nodes[1].position('x'));assert.ok(nodes[1].position('x')<nodes[2].position('x'));
assert.ok(Math.abs(nodes[0].position('y')-nodes[3].position('y'))<1);
assert.ok(cy.zoom()*14>=9,'Four-step labels must remain at least9 rendered pixels after fit');
const bounds=nodes.renderedBoundingBox({includeLabels:false});assert.ok(bounds.x1>=31.9&&bounds.x2<=675.1&&bounds.y1>=31.9&&bounds.y2<=289.1);
}finally{cy.destroy();}
''')

    def test_readable_complete_labels_legend_and_graph_list(self):
        self.run_node(r'''
const {view:v}=mount('labels','architecture');await settle();
const path='src/main/java/same/prefix/VeryLongDistinctiveGraphModelFile.java';
v.items=[{id:'f',kind:'entity',type:'file',title:path,source:{path}},
 {id:'c',kind:'entity',type:'component',title:'Приложение'},
 {id:'i',kind:'entity',type:'interface',title:'IGraphModel'}];
assert.equal(t.nodeLabel(v.items[0]).rows.join(''),'VeryLongDistinctiveGraphModelFile.java');
const wrapped=t.nodeLabel({title:'A deliberately long name with readable words'}).rows;assert(wrapped.length>1&&wrapped.every(row=>row.length<=25));assert.equal(wrapped.join(' '),'A deliberately long name with readable words','Wrapping keeps words intact');
v.filters.graphMode='neighborhood';v.selected='f';v.drafts.set('f',{item:v.items[0]});
v.relations=[{id:'r',from:'f',to:'i',type:'contains',provenance:'authored',evidence:[{path,line:38}]}];
const html=t.graph(v);assert.match(html,/Файл \/ модуль/);assert.match(html,/Интерфейс/);
assert.match(html,/содержит/);assert.match(html,/authored/);assert.match(html,/java:38/);
assert.ok(html.includes(path));assert.match(html,/Легенда графа/);
const elements=t.cyElements(v);assert.ok(elements[0].data.label.replaceAll('\n','').includes('VeryLongDistinctiveGraphModelFile.java'));
assert.match(elements.find(e=>e.data.id==='f').data.metadataImage,/^data:image\/svg\+xml,/);assert(elements.find(e=>e.data.id==='f').data.label.split('\n').every(row=>row.length<=25));
assert.equal(elements.find(e=>e.data.id==='i').data.type,'interface');
let list=t.catalog(v);assert.match(list,/2 элементов на схеме/);assert.doesNotMatch(list,/Приложение/);
v.filters.listMode='catalog';v.total=5973;list=t.catalog(v);
assert.match(list,/Показано 3 из 5973 результатов/);assert.match(list,/Компоненты/);assert.match(list,/Файлы \/ модули/);
assert.doesNotMatch(list,/загруженных страницах|Фильтры применяются к загруженным/);
v.selected='i';v.drafts.set('i',{item:v.items[2]});assert.equal(t.graphModel(v).relations.length,0);
''')

    def test_graph_navigation_restores_state_and_is_project_scoped(self):
        self.run_node(r'''
const {view:v}=mount('navigation','architecture');await settle();
t.recordGraph(v);const initial=v.navigation.length;
t.recordGraph(v);await t.refresh(v);assert.equal(v.navigation.length,initial);
t.recordGraph(v);t.selectItem(v,'view:scenario');v.filters.graphMode='neighborhood';v.filters.component='app';t.recordGraph(v);
v.viewport={x:17,y:28,scale:2};t.viewport(v);
t.recordGraph(v);t.selectItem(v,'entity:class');v.filters.graphMode='inheritance';t.recordGraph(v);
await t.navigateGraph(v,-1);assert.equal(v.selected,'view:scenario');assert.equal(v.filters.component,'app');
assert.equal(v.filters.graphMode,'neighborhood');assert.equal(v.viewport.x,17);assert.equal(v.viewport.scale,2);
await t.navigateGraph(v,1);assert.equal(v.selected,'entity:class');assert.equal(v.filters.graphMode,'inheritance');
assert.match(t.graph(v),/data-k-action="graph-forward"[^>]*disabled/);
await t.navigateGraph(v,-1);t.selectItem(v,'entity:new');t.recordGraph(v);
assert.equal(v.navigationIndex,v.navigation.length-1);assert.equal(v.navigation.some(s=>s.selected==='entity:class'),false);
const b=mount('other-project','architecture');await settle();assert.equal(b.view.navigation.length,1);assert.equal(b.view.selected,'');
assert.equal(v.selected,'entity:new');
''')

    def test_native_camera_boundary_and_teardown(self):
        self.run_node(r'''
const {view:v,root:r}=mount('pan','architecture');await settle();
const container={};r.querySelector=selector=>selector==='[data-k-cy]'?container:selector==='[data-k-body]'?body:null;
let instances=[],disconnected=0;
ctx.window.ResizeObserver=class{constructor(callback){this.callback=callback;}observe(){}disconnect(){disconnected++;}};
ctx.window.cytoscape=options=>{const events={},cy={options,events,p:{...options.pan},z:options.zoom,dead:false,
 pan:()=>cy.p,zoom:()=>cy.z,destroyed:()=>cy.dead,destroy:()=>cy.dead=true,resize:()=>{},width:()=>707,height:()=>240,
 nodes:()=>({length:1,map:()=>[{id:'dummy',x:0,y:0}],renderedBoundingBox:()=>({x1:0,y1:0,x2:20,y2:20})}),
 elements:()=>({sort:()=>({nodes:()=>[]})}),
 layout:options=>{cy.layoutOptions=options;let stop;return {one:(_event,handler)=>cy.finishLayout=stop=handler,run:()=>{if(!holdLayout)stop?.();}};},
 fit:(_elements,padding)=>{cy.padding=padding;cy.p={x:13,y:17};cy.z=1.5;},
 viewport:camera=>{cy.p=camera.pan;cy.z=camera.zoom;events['pan zoom']?.();},
 on:(names,selector,handler)=>events[names]=handler||selector,off:()=>{}};instances.push(cy);return cy;};
let holdLayout=true;t.draw(v);let cy=instances.at(-1);assert.equal(cy.padding,undefined,'Fit must wait for layoutstop');assert.equal(v.cameraInitialized,false);
holdLayout=false;cy.finishLayout();assert.equal(cy.padding,32);assert.equal(cy.options.layout.name,'preset');assert.equal(cy.layoutOptions.name,'grid');
for(const scale of [.5,1,3]){
 const before=requests.length,html=body.innerHTML;cy.p={x:71,y:72};cy.z=scale;cy.events['pan zoom']();
 assert.equal(v.viewport.x,71);assert.equal(v.viewport.y,72);assert.equal(v.viewport.scale,scale);
 assert.equal(requests.length,before);assert.equal(body.innerHTML,html);
 await new Promise(resolve=>setTimeout(resolve,150));const stored=JSON.parse(data.get('knowledge:pan:architecture'));assert.equal(stored.viewport.x,71);
}
assert.equal(r.pointerdown,undefined);assert.equal(r.pointermove,undefined);assert.doesNotMatch(source,/getScreenCTM|data-k-viewport/);assert.match(source,/background-image.*data\(metadataImage\)/);
t.draw(v);assert.equal(cy.dead,true);cy=instances.at(-1);assert.equal(cy.p.x,71);assert.equal(cy.z,3);
await t.action(v,'zoom-out');assert.ok(cy.z<3);await t.action(v,'fit');assert.equal(v.viewport.x,13);assert.equal(cy.padding,32);
assert.match(t.graph(v),/Вписать всё/);
mount('other','docs');assert.equal(cy.dead,true);assert.ok(disconnected>=2);
const css=fs.readFileSync(process.argv[1]+'/knowledge.css','utf8');assert.match(css,/\.k-graph\s*\{[^}]*user-select:none/);
assert.doesNotMatch(css,/\.k-inspector\s*\{[^}]*user-select:none/);
''')

    def test_real_cytoscape_headless_layouts_bounds_and_camera(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');assert.equal(cytoscape.version,'3.33.1');
const {view:v}=mount('real-cy','architecture');await settle();
v.items=Array.from({length:1000},(_,i)=>({id:'n'+i,kind:'entity',type:i===0?'component':'class',title:'Class '+i}));
v.relations=Array.from({length:400},(_,i)=>({id:'r'+i,kind:'relation',from:'n'+i%60,to:'n'+(i+1)%60,type:'uses',provenance:'source'}));
v.filters.graphMode='inheritance';v.relations.forEach(r=>r.type='implements');
// The VM UI and required vendor have distinct Object/Array prototypes.
const cy=cytoscape({headless:true,styleEnabled:true,elements:JSON.parse(JSON.stringify(t.cyElements(v))),style:JSON.parse(JSON.stringify(t.cyStyle))});
try {
assert.equal(cy.nodes().length,60);assert.equal(cy.edges().length,400);
for(const mode of ['overview','inheritance','neighborhood']){
 v.filters.graphMode=mode;v.selected='n0';v.drafts.set('n0',{item:v.items[0]});
 cy.layout({...t.cyLayout(v),boundingBox:{x1:0,y1:0,w:1000,h:800}}).run();
 assert.ok(cy.nodes().every(n=>Number.isFinite(n.position('x'))&&Number.isFinite(n.position('y'))));
}
v.filters.graphMode='neighborhood';v.drafts.set('n0',{item:{...v.items[0],type:'class'}});assert.equal(t.cyLayout(v).name,'cose');
v.drafts.set('n0',{item:{kind:'view'}});assert.equal(t.cyLayout(v).name,'grid','An empty authored view has no edges to direct');
const n=cy.nodes()[0];n.position({x:10,y:20});cy.viewport({pan:{x:100,y:200},zoom:2});
assert.equal(n.renderedPosition('x'),120);assert.equal(n.renderedPosition('y'),240);
cy.panBy({x:30,y:-17});assert.equal(n.renderedPosition('x'),150);assert.equal(n.renderedPosition('y'),223);
t.captureCamera(v,cy);assert.equal(v.viewport.x,130);assert.equal(v.viewport.scale,2);
assert.equal(cy.edges()[0].style('target-arrow-shape'),'triangle');
} finally {cy.destroy();}assert.ok(cy.destroyed());
''')

    def test_revision_conflict_keeps_draft_and_retry_request(self):
        self.run_node(r'''
const {view:v}=mount();await settle();
v.selected='doc:one';v.drafts.set(v.selected,{item:{id:v.selected,kind:'document',title:'Draft',markdown:'unsaved',entityRefs:[]},expected:7,dirty:true});
responder=async(action,args)=>action==='changeset'?{error:'revision_conflict',message:'Refresh before saving'}:action==='context'?{...context,revision:8}:{revision:8,items:[],next:null,more:false};
await t.save(v);
assert.equal(v.drafts.get(v.selected).dirty,true);assert.equal(v.drafts.get(v.selected).item.markdown,'unsaved');
assert.equal(requests.find(r=>r.action==='changeset').args.expected,7);
const originalKey=requests.find(r=>r.action==='changeset').args.key;
await t.save(v);assert.equal(requests.filter(r=>r.action==='changeset').at(-1).args.key,originalKey);
await t.refresh(v);assert.equal(v.drafts.get(v.selected).expected,7);assert.equal(v.context.revision,8);
assert.match(body.innerHTML,/Черновик|черновик/);
''')

    def test_project_race_isolation_and_safe_rendering(self):
        self.run_node(r'''
let release;responder=async(action,args,project)=>project==='a'&&action==='context'?await new Promise(r=>release=r):action==='context'?context:{revision:7,items:[{id:'doc:x',kind:'document',title:'<img onerror=alert(1)>',excerpt:'<script>bad</script>'}],next:null,more:false};
const a=mount('a');const b=mount('b');await settle();release(context);await settle();
assert.equal(a.view.context,null);assert.equal(b.view.context.revision,7);
assert.ok(requests.every(r=>new URL(r.url,'http://localhost').searchParams.get('project')!=='wrong'));
assert.match(body.innerHTML,/&lt;img onerror/);assert.doesNotMatch(body.innerHTML,/<img onerror|<script>bad/);
assert.match(t.markdown(b.view,{markdown:'<script>x</script>'}),/&lt;script&gt;/);
assert.equal(t.view('a','docs').drafts.size,0);
''')

    def test_graph_bounds_inheritance_and_authored_order(self):
        self.run_node(r'''
const {view:v}=mount('a','architecture');await settle();
v.items=Array.from({length:1000},(_,i)=>({id:'entity:'+i,kind:'entity',title:'Entity '+i,type:'class'}));
v.relations=Array.from({length:400},(_,i)=>({id:'r'+i,from:'entity:'+i%60,to:'entity:'+(i+1)%60,type:i%2?'uses':'extends'}));
let model=t.graphModel(v);assert.equal(model.nodes.length,1000);assert.equal(model.relations.length,400);
v.filters.graphMode='inheritance';model=t.graphModel(v);assert.ok(model.relations.every(r=>r.type==='extends'));assert.ok(model.nodes.length<=60);
v.filters.graphMode='neighborhood';v.selected='view:scenario';v.drafts.set(v.selected,{item:{id:v.selected,kind:'view',title:'Scenario',nodeIds:['entity:0','entity:1','entity:2'],orderedEdges:['r1','r0']}});
v.neighbors=v.items.slice(0,3);v.relations=v.relations.slice(0,2);model=t.graphModel(v);
assert.deepEqual(Array.from(model.relations,r=>r.id),['r1','r0']);assert.equal(model.nodes.length,3);
t.draw(v);assert.match(body.innerHTML,/data-k-select="entity:0"/);assert.doesNotMatch(body.innerHTML,/максимум 60/);
''')

    def test_import_review_and_restore_are_new_exact_revision_mutations(self):
        self.run_node(r'''
const {view:v}=mount();await settle();v.panel='import';v.importPaths='docs/one.md\ndocs/two.md';
responder=async(action,args)=>action==='import-preview'?{id:'preview-one',revision:7,items:[{action:'review',item:{id:'doc:one',title:'One'},diff:'-before\n+after'}]}:action==='context'?context:action==='search'?{revision:7,items:[],more:false,next:null}:{revision:8};
await t.action(v,'import-preview');assert.equal(v.importSelections.size,0);assert.match(body.innerHTML,/Применить проверенное обновление/);
v.importSelections.add('doc:one');await t.action(v,'import-apply');
const apply=requests.find(r=>r.action==='import-apply');assert.equal(apply.args.identifier,'preview-one');assert.equal(apply.args.expected,7);assert.deepEqual(Array.from(apply.args.selections),['doc:one']);
v.selected='doc:one';v.historical={revision:3,item:{title:'Old'}};await t.action(v,'restore');
const restore=requests.find(r=>r.action==='restore');assert.equal(restore.args.revision,3);assert.equal(restore.args.expected,7);assert.ok(restore.args.key);
''')

    def test_saved_filters_and_dirty_drafts_survive_remount(self):
        self.run_node(r'''
const a=mount('a');await settle();a.view.filters.query='search';a.view.viewport={x:22,y:13,scale:1.5};a.view.selected='doc:draft';
a.view.drafts.set('doc:draft',{item:{id:'doc:draft',kind:'document',title:'Work',markdown:'Preserved',entityRefs:['entity:one']},expected:7,dirty:true});
t.persist(a.view);mount('b');await settle();const remount=mount('a');await settle();
assert.equal(remount.view.drafts.get('doc:draft').item.markdown,'Preserved');assert.equal(remount.view.filters.query,'search');
assert.equal(remount.view.viewport.scale,1.5);assert.match(body.innerHTML,/#architecture\/entity%3Aone/);
assert.ok(data.has('knowledge:a:docs'));assert.ok(!data.get('knowledge:a:docs').includes('Preserved'));
''')

    def test_job_polling_coalesces_and_pauses_when_hidden(self):
        self.run_node(r'''
const timers=[],cleared=[];
ctx.setTimeout=(callback,ms)=>{timers.push({callback,ms});return timers.length;};ctx.clearTimeout=id=>cleared.push(id);
context.jobs=[{id:'job-one',state:'queued'}];
responder=async(action)=>action==='context'?context:action==='job'?(context.jobs=[{id:'job-one',state:'ready'}],context.jobs[0]):{revision:7,items:[],next:null,more:false};
const {root:r}=mount('a','architecture');await settle();
assert.equal(timers.filter(x=>x.ms===1500).length,1);
ui.afterRender({project:'a'});ui.afterRender({project:'a'});assert.equal(timers.length,1);
ctx.document.hidden=true;handlers.visibilitychange();assert.equal(cleared.at(-1),1);
await timers[0].callback();assert.equal(requests.filter(x=>x.action==='job').length,0);
ctx.document.hidden=false;handlers.visibilitychange();assert.equal(timers.length,2);
await timers[1].callback();assert.equal(requests.filter(x=>x.action==='job').length,1);
assert.equal(timers.length,2);assert.equal(t.view('a','architecture').context.jobs[0].state,'ready');
''')

    def test_debounced_search_and_revision_consistent_pagination(self):
        self.run_node(r'''
const timers=[],cleared=[];ctx.setTimeout=(callback,ms)=>{timers.push({callback,ms});return timers.length;};ctx.clearTimeout=id=>cleared.push(id);
const {view:v,root:r}=mount();await settle();const originalSearches=requests.filter(x=>x.action==='search').length;
for(const text of ['a','ab','abc'])r.input({target:{dataset:{kFilter:'query'},value:text,matches:()=>false}});
assert.equal(requests.filter(x=>x.action==='search').length,originalSearches);assert.equal(timers.filter(x=>x.ms===300).length,3);
timers.at(-1).callback();await settle();assert.equal(requests.filter(x=>x.action==='search').at(-1).args.query,'abc');
v.items=[{id:'doc:first',kind:'document',title:'First'}];v.next=50;v.listRevision=7;
responder=async(action)=>action==='context'?{...context,revision:8}:{revision:8,items:[{id:'doc:new',kind:'document',title:'New'}],next:null,more:false};
await t.refresh(v,true);assert.equal(v.items.length,1);assert.equal(v.items[0].id,'doc:first');assert.match(v.error,/между страницами/);
''')

    def test_editor_focus_and_selection_survive_refresh_draw(self):
        self.run_node(r'''
const {view:v,root:r}=mount();await settle();
v.selected='doc:draft';v.editing=true;v.drafts.set(v.selected,{item:{id:v.selected,kind:'document',title:'Draft',markdown:'abc',entityRefs:[]},expected:7,dirty:true});
let focused=false,selection=null;const field={dataset:{kField:'markdown'},selectionStart:1,selectionEnd:2,type:'textarea',focus:()=>focused=true,setSelectionRange:(a,b)=>selection=[a,b]};
ctx.document.activeElement=field;r.contains=()=>true;r.querySelectorAll=()=>[field];t.draw(v);
assert.equal(focused,true);assert.deepEqual(selection,[1,2]);assert.match(body.innerHTML,/>abc<\/textarea>/);
''')

    def test_download_contract_document_types_and_server_side_filters(self):
        self.run_node(r'''
const anchors=[];ctx.document.createElement=tag=>{assert.equal(tag,'a');const anchor={click(){anchors.push(this);}};return anchor;};
const {view:v,root:r}=mount();await settle();await t.action(v,'new-doc');
assert.equal(v.drafts.get(v.selected).item.type,'explanation');assert.match(body.innerHTML,/tutorial/);
await t.action(v,'export');await t.action(v,'backup');await t.action(v,'export-public');
assert.equal(anchors.length,3);
for(const a of anchors)assert.equal(new URL(a.href,'http://localhost').searchParams.get('project'),'a');
assert.equal(new URL(anchors[0].href,'http://localhost').pathname,'/api/v1/knowledge/download');
assert.equal(new URL(anchors[0].href,'http://localhost').searchParams.get('action'),'export');assert.match(anchors[0].download,/\.zip$/);
assert.equal(new URL(anchors[1].href,'http://localhost').searchParams.get('action'),'backup');assert.match(anchors[1].download,/\.json$/);
assert.equal(new URL(anchors[2].href,'http://localhost').searchParams.get('public'),'true');
r.change({target:{dataset:{kFilter:'type'},value:'reference'}});await settle();assert.equal(requests.filter(x=>x.action==='search'&&x.args.kind==='document').at(-1).args.type,'reference');
const arch=mount('b','architecture');await settle();arch.view.filters.type='class';arch.view.filters.component='app';arch.view.filters.entry='yes';arch.view.filters.graphMode='neighborhood';arch.view.selected='entity:main';
responder=async(action,args)=>action==='context'?context:action==='read'?{id:args.id,kind:'entity',title:'Main',type:'class'}:{revision:7,items:[],more:false,next:null};
await t.refresh(arch.view);
const entity=requests.filter(x=>x.args.kind==='entity'&&x.args.type==='class').at(-1);assert.equal(entity.args.component,'app');assert.equal(entity.args.entrypoint,'true');
assert.ok(requests.some(x=>x.args.kind==='relation'&&x.args.endpoint==='entity:main'));
''')

    def test_corrupt_saved_viewport_cannot_inject_svg_attributes(self):
        self.run_node(r'''
data.set('knowledge:a:architecture',JSON.stringify({viewport:{x:'" onload="bad',y:'invalid',scale:'0) <script>'}}));
const {view:v}=mount('a','architecture');await settle();
assert.equal(v.viewport.x,0);assert.equal(v.viewport.y,0);assert.equal(v.viewport.scale,1);assert.doesNotMatch(body.innerHTML,/onload="bad/);
''')

    def test_preserved_root_deep_link_clears_previous_inspector_state(self):
        self.run_node(r'''
const {view:v}=mount('a','architecture');await settle();
v.selected='entity:old';v.history={items:[{revision:1,reason:'Old item'}]};v.historical={revision:1,item:{title:'Wrong old item'}};v.linkedDocs=[{id:'doc:old',title:'Old doc'}];v.neighbors=[{id:'entity:old',kind:'entity'}];
responder=async(action,args)=>action==='read'?{id:args.id,kind:'entity',type:'class',title:'New selected item'}:action==='context'?context:{revision:7,items:[],more:false,next:null};
ctx.location.hash='#architecture/entity%3Anew';ui.page('architecture',{project:'a'});ui.afterRender({project:'a'});await settle();
assert.equal(v.selected,'entity:new');assert.equal(v.historical,null);assert.equal(v.history,null);assert.equal(v.linkedDocs.length,0);assert.match(body.innerHTML,/New selected item/);assert.doesNotMatch(body.innerHTML,/Wrong old item|Old doc/);
''')

    def test_final_document_statuses_debt_history_basis_and_incomplete_sources(self):
        self.run_node(r'''
const {view:v}=mount();await settle();v.selected='doc:one';v.editing=true;
v.drafts.set(v.selected,{item:{id:v.selected,kind:'document',title:'One',status:'historical',markdown:'text',entityRefs:[],missingAssets:['image.png'],missingLinks:['source<bad>.md']},expected:7,dirty:false});
v.context.publicationPending=2;v.context.reviews=[{task:'task:one',stage:'review',state:'review-needed',reason:'Contract changed'},{task:'resolved',state:'resolved',reason:'Do not show completed debt'}];
v.context.jobs=[{id:'scan',state:'stale'}];v.history={items:[{revision:7,task:'task:one',stage:'review',at:'now',reason:'Edit',codeRevision:{basis:'local-source-scan',fingerprint:'fingerprint<unsafe>',heads:['abc123',null]}},{revision:6,reason:'Legacy',codeRevision:{}}],more:false};
t.draw(v);
const options=body.innerHTML.match(/<select data-k-field="status">([\s\S]*?)<\/select>/)[1];
for(const status of ['draft','current','historical','archived'])assert.ok(options.includes('>'+status+'</option>'));
assert.ok(!options.includes('>review<')&&!options.includes('>published<'));assert.match(options,/selected>historical/);
assert.match(body.innerHTML,/доставки: 2/);assert.match(body.innerHTML,/#tasks\/task%3Aone\/review/);assert.doesNotMatch(body.innerHTML,/Do not show completed debt/);
assert.match(body.innerHTML,/Версия исходного кода неизвестна/);assert.match(body.innerHTML,/fingerprint&lt;unsafe&gt;/);assert.match(body.innerHTML,/корень 2 — неизвестен/);
assert.match(body.innerHTML,/Неполные ссылки на исходники: source&lt;bad&gt;\.md/);assert.match(body.innerHTML,/Не найдены изображения: image\.png/);
assert.doesNotMatch(body.innerHTML,/k-job/,'Code-scanner banners do not belong in documentation reading');
v.panel='import';v.imports={id:'preview',revision:7,items:[{action:'create',item:v.drafts.get(v.selected).item}]};t.draw(v);assert.equal((body.innerHTML.match(/Неполные ссылки на исходники/g)||[]).length,2);
''')

    def test_default_graph_is_coarse_but_empty_metadata_has_bounded_fallback(self):
        self.run_node(r'''
const {view:v}=mount('a','architecture');await settle();
v.items=[{id:'component:app',kind:'entity',title:'Application',type:'component'},
 {id:'file:main',kind:'entity',title:'Main',type:'file',entrypoint:true},
 ...Array.from({length:80},(_,i)=>({id:'class:'+i,kind:'entity',type:'class',title:'Class '+i}))];
v.relations=[{id:'aggregate',type:'depends-on',from:'component:app',to:'file:main'}];
let model=t.graphModel(v);assert.deepEqual(Array.from(model.nodes,x=>x.id),['component:app','file:main']);
v.selected='class:10';model=t.graphModel(v);assert.equal(model.nodes.length,3);assert.ok(model.nodes.some(x=>x.id==='class:10'));
v.selected='';v.items=v.items.slice(2);model=t.graphModel(v);assert.equal(model.nodes.length,80);
v.items=[{id:'component:app',kind:'entity',title:'Application',type:'component'}];await t.refresh(v);
assert.ok(requests.some(x=>x.args.kind==='relation'&&x.args.type==='depends-on'));
''')

    def test_scan_summary_is_current_readable_and_keeps_diagnostics(self):
        self.run_node(r'''
const {view:v}=mount('a','architecture');await settle();
v.context.jobs=[{id:'running',state:'running'},{id:'latest',state:'partial',counts:{files:25,types:12,parsed:2,reused:23},error:'Read <failure>',diagnostics:[{path:'src/file.py',message:'Missing dependency'}],capabilities:{python:['modules','types','declared-inheritance'],java:['files']}},{id:'older',state:'ready',counts:{files:999,types:999,parsed:999,reused:0}}];
await t.action(v,'diagnostics');
assert.equal((body.innerHTML.match(/class="k-job/g)||[]).length,2);
assert.match(body.innerHTML,/файлов: 25/);assert.match(body.innerHTML,/типов: 12/);assert.match(body.innerHTML,/файлов разобрано: 2/);assert.match(body.innerHTML,/файлов без изменений: 23/);
assert.doesNotMatch(body.innerHTML,/999|"files":|"parsed":|"reused":/);assert.match(body.innerHTML,/Read &lt;failure&gt;/);assert.match(body.innerHTML,/Missing dependency/);
assert.match(body.innerHTML,/Python:<\/strong> файлы, классы и объявленные связи типов/);assert.match(body.innerHTML,/Java:<\/strong> инвентаризация файлов/);
v.context.jobs=v.context.jobs.slice(1);t.draw(v);assert.equal((body.innerHTML.match(/class="k-job/g)||[]).length,1);
v.context.jobs=[{id:'stale',state:'stale'}];t.draw(v);assert.match(body.innerHTML,/k-job k-warning/);assert.match(body.innerHTML,/повторите обновление/);
''')

    def test_restore_confirmation_uses_returned_new_revision(self):
        self.run_node(r'''
const {view:v}=mount();await settle();v.selected='doc:one';v.notice='Сохранена версия 5';v.historical={revision:2,item:{title:'Old'}};
responder=async(action,args)=>action==='restore'?{revision:6}:action==='context'?{...context,revision:6}:action==='read'?{id:args.id,kind:'document',title:'Restored',markdown:'text',entityRefs:[]}:{revision:6,items:[],next:null,more:false};
await t.action(v,'restore');assert.equal(v.notice,'Восстановлена новая версия 6');assert.equal(v.context.revision,6);assert.doesNotMatch(body.innerHTML,/Сохранена версия 5/);
''')

    def test_document_link_titles_are_bounded_and_missing_titles_are_explicit(self):
        self.run_node(r'''
const {view:v}=mount();await settle();v.selected='doc:one';const refs=Array.from({length:55},(_,i)=>'entity:'+i);let release;
responder=async(action,args)=>action==='read'&&args.id==='doc:one'?{id:args.id,kind:'document',title:'Doc',markdown:'Text',entityRefs:refs}:action==='read'&&args.id==='entity:0'?await new Promise(r=>release=r):action==='read'&&args.id==='entity:1'?{error:'item_missing',message:'Missing'}:{id:args.id,kind:'entity',title:'Readable <'+args.id+'>'};
const loading=t.loadItem(v,v.selected);await settle();assert.match(body.innerHTML,/название загружается/);
release({id:'entity:0',kind:'entity',title:'Main entry point'});await loading;
assert.equal(requests.filter(r=>r.action==='read'&&String(r.args.id).startsWith('entity:')).length,20);
assert.match(body.innerHTML,/>Main entry point<\/a>/);assert.match(body.innerHTML,/Readable &lt;entity:2&gt;/);
assert.match(body.innerHTML,/entity:1 · элемент недоступен/);assert.doesNotMatch(body.innerHTML,/entity:24|предел 20 ссылок/);
assert.match(body.innerHTML,/20 из 55/);assert.match(body.innerHTML,/Показать все/);
assert.match(body.innerHTML,/#architecture\/entity%3A0/);
let inFlight=0,peak=0;
responder=async(action,args)=>{assert.equal(action,'read');inFlight++;peak=Math.max(peak,inFlight);await settle();inFlight--;return {id:args.id,kind:'entity',title:'Readable <'+args.id+'>'};};
await t.action(v,'doc-links-all');assert.equal(peak,20);assert.equal(requests.filter(r=>r.action==='read'&&String(r.args.id).startsWith('entity:')).length,55);
assert.match(body.innerHTML,/Readable &lt;entity:54&gt;/);assert.match(body.innerHTML,/55 из 55/);assert.match(body.innerHTML,/Свернуть/);
const cached=requests.length;await t.action(v,'doc-links-collapse');assert.match(body.innerHTML,/20 из 55/);assert.doesNotMatch(body.innerHTML,/entity:54/);
await t.action(v,'doc-links-all');assert.equal(requests.length,cached);assert.match(body.innerHTML,/Readable &lt;entity:54&gt;/);
''')

    def test_document_expansion_preserves_editor_and_retries_transient_errors(self):
        self.run_node(r'''
const {view:v,root:r}=mount('doc-expansion');await settle();v.selected='doc:dirty';v.editing=true;
const item={id:v.selected,kind:'document',title:'Unsaved',markdown:'DRAFT_BODY',entityRefs:[...Array.from({length:23},(_,i)=>'entity:'+i),'entity:0','',null]};
v.drafts.set(v.selected,{item,dirty:true,expected:7});
responder=async(action,args)=>({id:args.id,kind:'entity',title:'Object '+args.id});await t.resolveDocLinks(v,item);
const nav={dataset:{kDocLinks:item.id},innerHTML:'',hidden:false,contains:()=>false};
const query=r.querySelector;r.querySelector=selector=>selector==='[data-k-doc-links]'?nav:query(selector);
// Local nav updates must leave the editor DOM, focus and draft untouched.
let redraws=0;const article=body.innerHTML;Object.defineProperty(body,'innerHTML',{configurable:true,get:()=>article,set:()=>redraws++});
let failOnce=true;responder=async(action,args)=>{if(args.id==='entity:21'&&failOnce){failOnce=false;return {error:'server_unavailable',message:'Offline'};}return {id:args.id,kind:'entity',title:'Named <'+args.id+'>'};};
await t.action(v,'doc-links-all');assert.equal(redraws,0);assert.equal(v.drafts.get(v.selected).dirty,true);assert.equal(item.markdown,'DRAFT_BODY');
assert.match(nav.innerHTML,/23 из 23/);assert.match(nav.innerHTML,/название не удалось загрузить/);assert.match(nav.innerHTML,/Повторить загрузку названий/);
const before=requests.length;await t.action(v,'doc-links-retry');assert.equal(requests.length,before+1);assert.match(nav.innerHTML,/Named &lt;entity:21&gt;/);assert.doesNotMatch(nav.innerHTML,/Повторить загрузку/);
await t.action(v,'doc-links-collapse');assert.doesNotMatch(nav.innerHTML,/entity:22/);assert.equal(redraws,0);t.unmount();
''')

    def test_document_link_expansion_stops_after_navigation_and_reference_edits(self):
        self.run_node(r'''
const {view:v}=mount('doc-link-stale');await settle();v.selected='doc:one';
const item={id:v.selected,kind:'document',title:'One',entityRefs:Array.from({length:65},(_,i)=>'old:'+i)};
v.drafts.set(item.id,{item,dirty:true});responder=async(action,args)=>({id:args.id,kind:'entity',title:args.id});await t.resolveDocLinks(v,item);
let releases=[];responder=async(action,args)=>await new Promise(resolve=>releases.push(()=>resolve({id:args.id,kind:'entity',title:'STALE '+args.id})));
const expansion=t.action(v,'doc-links-all');await settle();assert.equal(releases.length,20);
// Even before the input debounce runs, a changed reference set invalidates results.
item.entityRefs=['new:only'];releases.splice(0).forEach(release=>release());await expansion;assert.doesNotMatch(body.innerHTML,/STALE/);
assert.equal(requests.filter(r=>r.args.id==='old:40').length,0);
responder=async(action,args)=>({id:args.id,kind:'entity',title:'New object'});await t.resolveDocLinks(v,item);assert.match(body.innerHTML,/New object/);assert.equal(v.linkedEntities.has('old:20'),false);
item.entityRefs=Array.from({length:65},(_,i)=>'next:'+i);await t.resolveDocLinks(v,item);await t.action(v,'doc-links-collapse');
// Clear the extra labels so a second expansion has an observable pending batch.
for(let i=20;i<65;i++)v.linkedEntities.delete('next:'+i);
releases=[];responder=async(action,args)=>await new Promise(resolve=>releases.push(()=>resolve({id:args.id,kind:'entity',title:'STALE NEXT'})));
const navigating=t.action(v,'doc-links-all');await settle();t.selectItem(v,'doc:two');v.drafts.set(v.selected,{item:{id:v.selected,kind:'document',title:'Two',entityRefs:[]}});t.draw(v);
releases.splice(0).forEach(release=>release());await navigating;assert.match(body.innerHTML,/Two/);assert.doesNotMatch(body.innerHTML,/STALE NEXT/);assert.equal(v.linkedEntities.size,0);t.unmount();
''')

    def test_historical_changed_fragment_additions_deletions_no_change_and_limits(self):
        self.run_node(r'''
let diff=t.changedFragment('start\nold\nend','start\nnew\nextra\nend');
assert.deepEqual(Array.from(diff.removed,x=>x.text),['old']);assert.deepEqual(Array.from(diff.added,x=>x.text),['new','extra']);assert.equal(diff.removed[0].line,2);
diff=t.changedFragment('same','same');assert.equal(diff.unchanged,true);
diff=t.changedFragment('','added');assert.equal(diff.removed.length,0);assert.equal(diff.added[0].text,'added');
diff=t.changedFragment('removed','');assert.equal(diff.added.length,0);assert.equal(diff.removed[0].text,'removed');
diff=t.changedFragment(Array.from({length:250},()=> 'old'+'x'.repeat(700)).join('\n'),Array.from({length:260},()=> 'new'+'x'.repeat(700)).join('\n'));
assert.equal(diff.removed.length,200);assert.equal(diff.added.length,200);assert.equal(diff.omitted,110);assert.equal(diff.trimmed,true);assert.equal(diff.added[0].text.length,501);
''')

    def test_historical_compare_reads_saved_content_and_keeps_dirty_draft_restore(self):
        self.run_node(r'''
const {view:v}=mount();await settle();v.selected='doc:one';v.editing=false;
v.drafts.set(v.selected,{item:{id:v.selected,kind:'document',title:'Doc',markdown:'UNSAVED_DRAFT',entityRefs:[]},expected:7,dirty:true});
v.historical={revision:2,item:{id:v.selected,kind:'document',title:'Old',markdown:'start\nOLD_VALUE\nend'}};
responder=async(action,args)=>{assert.equal(action,'read');assert.equal(args.id,'doc:one');assert.equal(args.revision,undefined);return {id:args.id,kind:'document',markdown:'start\nSAVED_VALUE<script>\nend'};};
await t.action(v,'compare');assert.equal(v.drafts.get(v.selected).item.markdown,'UNSAVED_DRAFT');
assert.equal(v.comparison.diff.removed[0].text,'OLD_VALUE');assert.equal(v.comparison.diff.added[0].text,'SAVED_VALUE<script>');
assert.match(body.innerHTML,/Сравнить с текущей/);assert.match(body.innerHTML,/Восстановить как новую версию/);assert.match(body.innerHTML,/SAVED_VALUE&lt;script&gt;/);assert.doesNotMatch(body.innerHTML,/SAVED_VALUE<script>/);
assert.ok(!v.comparison.diff.added.some(row=>row.text.includes('UNSAVED_DRAFT')));
v.historical.item.markdown='start\nSAVED_VALUE<script>\nend';await t.action(v,'compare');assert.match(body.innerHTML,/Изменений текста нет/);
v.historical.item.markdown='old\n'.repeat(250);responder=async()=>({id:v.selected,kind:'document',markdown:('new'+'x'.repeat(700)+'\n').repeat(260)});await t.action(v,'compare');assert.match(body.innerHTML,/200 строками каждой версии и 500 символами строки/);assert.match(body.innerHTML,/Длинные строки сокращены/);
''')

    def test_inheritance_server_filters_find_interfaces_beyond_many_uses(self):
        self.run_node(r'''
const {view:v}=mount('a','architecture');await settle();v.filters.graphMode='inheritance';v.selected='model:GraphModel';
const uses=Array.from({length:140},(_,i)=>({id:'uses:'+i,kind:'relation',from:v.selected,to:'entity:'+i,type:'uses'}));
const implementations=[{id:'implements:graph',kind:'relation',from:v.selected,to:'interface:IGraphModel',type:'implements'},
 {id:'implements:close',kind:'relation',from:v.selected,to:'interface:AutoCloseable',type:'implements'}];
responder=async(action,args)=> {
 if(action==='context')return context;
 if(action==='read')return {id:args.id,kind:'entity',type:args.id.startsWith('interface:')?'interface':'class',title:args.id.split(':').at(-1)};
 if(args.kind==='entity')return {revision:7,items:[{id:v.selected,kind:'entity',type:'class',title:'GraphModel'}],more:false,next:null};
 if(args.kind==='relation') {
  assert.equal(args.endpoint,'model:GraphModel');assert.equal(args.limit,'100');
  if(args.type==='implements')return args.offset==='100'?{revision:7,items:[implementations[1]],more:false,next:null}:{revision:7,items:[implementations[0],implementations[0]],more:true,next:100};
  if(args.type==='extends')return {revision:7,items:[],more:false,next:null};
  return {revision:7,items:uses.slice(0,100),more:true,next:100};
 }
 return {revision:7,items:[],more:false,next:null};
};
const start=requests.length;await t.refresh(v);
let relationRequests=requests.slice(start).filter(r=>r.args.kind==='relation');
assert.equal(relationRequests.length,3);assert.deepEqual(relationRequests.map(r=>r.args.type).sort(),['extends','implements','implements']);
assert.equal(v.relations.length,2);assert.equal(v.relationsMore,false);assert.equal(t.graphModel(v).nodes.filter(n=>n.type==='interface').length,2);
assert.match(body.innerHTML,/IGraphModel/);assert.match(body.innerHTML,/AutoCloseable/);assert.doesNotMatch(body.innerHTML,/Связи ограничены первой страницей/);
const selectionStart=requests.length;await t.loadItem(v,v.selected);
relationRequests=requests.slice(selectionStart).filter(r=>r.args.kind==='relation');assert.equal(relationRequests.length,3);assert.ok(relationRequests.every(r=>['extends','implements'].includes(r.args.type)));
assert.equal(v.relations.length,2);assert.equal(t.graphModel(v).nodes.filter(n=>n.type==='interface').length,2);
''')

    def test_lazy_source_tree_hydrates_only_open_folder(self):
        self.run_node(r"""
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);const map=ctx.window.ArchitectureMap;
const v={selected:'',canvasItem:'',filters:{fileFolders:{}}};
const items=[{id:'one',type:'class',title:'One',source:{path:'src/<unsafe>/One.java'}},{id:'two',type:'class',title:'Two',source:{path:'src/<unsafe>/Two.java'}},{id:'three',type:'class',title:'Three',source:{path:'src/other/Three.java'}}];
const many=Array.from({length:205},(_,i)=>({id:'many:'+i,type:'class',title:'Many '+i,source:{path:'src/<unsafe>/Many'+String(i).padStart(3,'0')+'.java'}}));items.push(...many);
const html=map.fileTree(v,items,{lazy:true});assert.match(html,/data-r-directory="src"/);assert.doesNotMatch(html,/data-k-select="one"/);
const folder=path=>({dataset:{kFileFolder:path},children:[{tagName:'DIV',innerHTML:'',firstElementChild:{matches:()=>true}}]});
const src=folder('src');assert.equal(map.hydrateFolder(v,src),true);assert.match(src.children[0].innerHTML,/Откройте папку/);
const nested=folder('src/<unsafe>');assert.equal(map.hydrateFolder(v,nested),true);assert.match(nested.children[0].innerHTML,/data-k-file-more="src\/&lt;unsafe&gt;"/);assert.equal((nested.children[0].innerHTML.match(/<details /g)||[]).length,200);assert.doesNotMatch(nested.children[0].innerHTML,/data-k-select="one"/);
const firstPage=nested.children[0].innerHTML;assert.equal(map.hydrateFolder(v,nested,200),true);assert.match(nested.children[0].innerHTML,/Many000\.java/);assert.match(nested.children[0].innerHTML,/One\.java/);assert.doesNotMatch(nested.children[0].innerHTML,/data-k-file-more/);
const one=folder('src/<unsafe>/One.java');assert.equal(map.hydrateFolder(v,one),true);assert.match(one.children[0].innerHTML,/data-k-select="one"/);
v.selected='many:204';const selected=map.fileTree(v,items,{lazy:true});assert.match(selected,/data-k-select="many:204"/);assert.match(selected,/data-k-file-more/);
const all=map.fileTree(v,items,{lazy:true,reveal:true});assert.doesNotMatch(all,/data-k-file-more/);assert.match(all,/data-k-select="one"/);
""")


    def test_navigation_catalog_keeps_graph_history_index(self):
        self.run_node(r"""
const {view:v}=mount('navigation-cache','architecture');await settle();const historyIndex=v.navigationIndex,prior=requests.filter(x=>x.action==='source-tree').length;
responder=async(action,args)=>action==='search'?{revision:8,items:args.type==='component'?[{id:'component:new',kind:'entity',type:'component',title:'New'}]:[],more:false}:action==='context'?{...context,revision:8}:{};
const [first,second]=await Promise.all([t.navigationPages(v,8),t.navigationPages(v,8)]);assert.equal(first,second);assert.equal(requests.filter(x=>x.action==='source-tree').length,prior+1);assert.equal(v.navigationIndex,historyIndex);assert.equal(typeof v.navigationIndex,'number');await t.navigationPages(v,8);assert.equal(requests.filter(x=>x.action==='source-tree').length,prior+1);
""")

    def test_source_tree_catalog_reuses_same_revision_query_identity(self):
        self.run_node(r"""
const {view:v}=mount('source-tree','architecture');await settle();v.context={revision:7};v.filters.query='';v.filters.discoveryScope='project';let calls=0;
responder=async(action,args)=>{if(action==='source-tree'){calls++;assert.equal(args.limit,'5000');return {revision:7,items:[{id:'file:a',kind:'entity',type:'file',title:'a.java',source:{path:'src/a.java'}}],more:false,next:null};}return action==='context'?context:{};};
await Promise.all([t.loadCatalogTree(v),t.loadCatalogTree(v)]);await t.loadCatalogTree(v);assert.equal(calls,1);assert.equal(v.catalogTreeItems.length,1);assert.equal(v.catalogTreeKey,JSON.stringify([7,'','']));
""")

if __name__ == '__main__':
    unittest.main()
