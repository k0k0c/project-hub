"""Atomic architecture navigation, discovery, and optional follow-selection."""
import shutil
import unittest
import test_knowledge_ui as _knowledge_ui


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class ArchitectureNavigationUiTest(unittest.TestCase):
    run_node = _knowledge_ui.KnowledgeUiTest.run_node

    def test_matrix_pair_keeps_dependencies_instead_of_opening_leaf_code(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const nodes=['a','b','c'].map(id=>({id,kind:'entity',type:'component',title:id})),edges=[{id:'ab',kind:'relation',from:'a',to:'b',type:'depends-on',count:2},{id:'ac',kind:'relation',from:'a',to:'c',type:'depends-on',count:3}];
responder=async(action,args)=>action==='context'?context:action==='read'?nodes.find(n=>n.id===args.id):action==='search'?{revision:7,items:args.type==='component'?nodes:args.kind==='relation'&&args.endpoint==='a'?edges:[],more:false}:{};
const {view:v}=mount('matrix-pair','architecture');await settle();t.chooseGraphItem(v,'a',{graphMode:'neighborhood',focusTarget:'b',focusRelation:'ab'});await settle();const model=t.graphModel(v);assert.equal(v.scopedCode,null);assert.equal(model.nodes.map(n=>n.id).sort().join(','),'a,b');assert.equal(model.relations.map(e=>e.id).join(','),'ab');assert.match(body.innerHTML,/Зависимости: a → b/);t.unmount();
''')

    def test_scope_reveal_preserves_unrelated_folders(self):
        self.run_node(r'''
const {view:v}=mount('scope-reveal','architecture');await settle();v.componentItems=[{id:'root',type:'component'},{id:'parent',type:'component',parent:'root'},{id:'leaf',type:'component',parent:'parent'}];v.selected='leaf';v.drafts.set('leaf',{item:v.componentItems[2]});v.filters.treeFolders={root:false,parent:false,other:false};t.revealScope(v);assert.equal(v.filters.treeFolders.root,true);assert.equal(v.filters.treeFolders.parent,true);assert.equal(v.filters.treeFolders.other,false);
v.selected='class';v.drafts.set('class',{item:{id:'class',type:'class',source:{path:'src/main/F.java'}}});v.filters.fileFolders={src:false,'src/main':false,'src/main/F.java':false,other:false};t.revealScope(v);assert.equal(v.filters.fileFolders['src/main/F.java'],true);assert.equal(v.filters.fileFolders.other,false);t.unmount();
''')

    def test_canvas_search_reveals_matches_inside_closed_source_folders(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const {view:v}=mount('search-reveal','architecture');await settle();v.filters.fileFolders={src:false,'src/api':false,'src/api/I.java':false};v.filters.canvasQuery='IAppSettings';v.items=[{id:'i',kind:'entity',type:'interface',title:'IAppSettings',source:{path:'src/api/I.java'}}];v.neighbors=v.items;v.selected='i';v.drafts.set('i',{item:v.items[0]});v.filters.graphMode='neighborhood';const before=JSON.stringify(v.filters.fileFolders);const html=t.graph(v);assert.match(html,/data-k-file-folder="src\/api\/I.java" open/);assert.match(html,/data-k-file-folder="src\/api" open/);assert.equal(JSON.stringify(v.filters.fileFolders),before);t.unmount();
''')

    def test_direction_filters_reset_and_canvas_search_are_local(self):
        self.run_node(r'''
const {view:v}=mount('local-controls','architecture');await settle();const nodes=[{id:'a',kind:'entity',type:'class',title:'Alpha'},{id:'b',kind:'entity',type:'class',title:'Beta'},{id:'c',kind:'entity',type:'class',title:'Gamma'}];v.selected='a';v.items=nodes;v.neighbors=nodes;v.filters.graphMode='neighborhood';v.drafts.set('a',{item:nodes[0]});v.relations=[{id:'ab',from:'a',to:'b',type:'uses'},{id:'ca',from:'c',to:'a',type:'uses'}];v.filters.edgeDirection='incoming';v.filters.edgeAnchor='a';assert.deepEqual(t.graphModel(v).relations.map(e=>e.id),['ca']);const before=requests.length;await t.action(v,'reset-filters');assert.equal(t.graphModel(v).relations.length,2);assert.equal(requests.length,before);assert.equal(v.selected,'a');
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js'),cy=cytoscape({headless:true,elements:nodes.map(n=>({data:n}))});cy.getElementById('a').select();const camera=JSON.stringify(cy.pan()),selection=cy.nodes(':selected').map(n=>n.id()).join();v.filters.canvasQuery='beta';t.applyCanvasSearch(v,cy);assert.equal(cy.nodes('.k-find-match').map(n=>n.id()).join(),'b');assert.equal(JSON.stringify(cy.pan()),camera);assert.equal(cy.nodes(':selected').map(n=>n.id()).join(),selection);assert.equal(requests.length,before);cy.destroy();
v.filters.graphMode='components';v.scopedCode=null;assert.doesNotMatch(t.chartFilters(v),/data-k-visible-type/);t.unmount();
''')

    def test_matrix_omits_supporting_frames_and_aggregates_parallel_facts(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const {view:v}=mount('matrix-participants','architecture');await settle();v.selected='p';v.filters.graphMode='components';v.filters.componentContext='subsystems';
v.componentItems=[{id:'p',kind:'entity',type:'component',title:'Frame'},{id:'a',kind:'entity',type:'component',title:'A',parent:'p'},{id:'b',kind:'entity',type:'component',title:'B',parent:'p'}];
v.relations=[{id:'ab1',kind:'relation',type:'depends-on',from:'a',to:'b',count:2},{id:'ab2',kind:'relation',type:'depends-on',from:'a',to:'b',count:3}];
const model=t.graphModel(v);assert.equal(model.nodes.length,3);const html=t.matrix(v);assert.match(html,/5 статических связей/);assert.doesNotMatch(html,/data-k-select="p"/);assert.match(html,/data-k-select="a"/);t.unmount();
''')

    def test_first_leaf_opens_bounded_code_and_more_extends_the_same_scope(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const leaf={id:'component:leaf',kind:'entity',type:'component',title:'Leaf'},nodes=Array.from({length:85},(_,i)=>({id:'type:'+i,kind:'entity',type:'class',title:'Type '+i,component:leaf.id}));
responder=async(action,args)=>action==='context'?context:action==='read'?leaf:action==='search'?args.type==='component'?{revision:7,items:[leaf],more:false}:args.component===leaf.id?{revision:7,items:nodes.slice(args.offset||0,(args.offset||0)+args.limit),more:(args.offset||0)+args.limit<nodes.length,next:(args.offset||0)+args.limit}:{revision:7,items:[],more:false}:{};
const {view:v}=mount('bounded-leaf','architecture');await settle();t.chooseGraphItem(v,leaf.id,{graphMode:'components'});await settle();
assert.equal(v.filters.componentContext,'code');assert.equal(v.scopedCode.nodes.length,50);assert.equal(v.componentPartial,true);assert.match(body.innerHTML,/data-k-action="more-code"/);assert.doesNotMatch(body.innerHTML,/data-k-presentation/);
await t.action(v,'more-code');assert.equal(v.selected,leaf.id);assert.equal(v.scopedCode.nodes.length,85);assert.equal(v.componentPartial,false);assert.doesNotMatch(body.innerHTML,/data-k-action="more-code"/);t.unmount();
''')

    def test_scan_has_visible_queue_and_running_status_without_redrawing_graph(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const timers=[];ctx.setTimeout=(callback,ms)=>{timers.push({callback,ms});return timers.length};ctx.clearTimeout=()=>{};
const {view:v,root:r}=mount('scan-feedback','architecture');await settle();const status={innerHTML:''};
r.querySelector=s=>s==='[data-k-body]'?body:s==='[data-k-analysis-status]'?status:null;
responder=async(action)=>action==='context'?context:action==='scan'?{id:'scan-job',state:'queued'}:action==='job'?{id:'scan-job',state:'running'}:{revision:7,items:[],more:false,next:null};
await t.action(v,'scan');assert.match(status.innerHTML,/ожидает запуска/);await t.action(v,'scan');assert.equal(requests.filter(x=>x.action==='scan').length,1);
const before=body.innerHTML,nav=JSON.stringify(v.navigation),camera=JSON.stringify(v.viewport);
await timers.find(timer=>timer.ms===1500).callback();assert.match(status.innerHTML,/выполняется/);assert.equal(body.innerHTML,before,'Polling only updates status');assert.equal(JSON.stringify(v.navigation),nav);assert.equal(JSON.stringify(v.viewport),camera);
context.jobs=[];v.context.jobs=[];t.unmount();
''')

    def test_latest_scope_publishes_only_complete_snapshot(self):
        self.run_node(r'''
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);
const {view:v}=mount('atomic','architecture');await settle();let release;
responder=async(action,args)=>{
 if(action==='context')return context;
 if(action==='read'){if(args.id==='old')await new Promise(resolve=>release=resolve);return {id:args.id,kind:'entity',type:'class',title:args.id};}
 return {revision:7,items:args.kind==='relation'&&args.endpoint==='new'?[{id:'new-edge',kind:'relation',from:'new',to:'peer',type:'uses'}]:[],more:false,next:null};
};
t.chooseGraphItem(v,'old');await settle();assert.equal(typeof release,'function');assert.match(body.innerHTML,/Подготавливаем выбранный раздел/);
t.chooseGraphItem(v,'new');await settle();assert.equal(v.loadedSelection,'new');assert.equal(v.relations[0].id,'new-edge');
release();await settle();assert.equal(v.selected,'new');assert.equal(v.loadedSelection,'new');assert.equal(v.relations[0].id,'new-edge');assert.equal(v.loading,false);assert.equal(v.error,'');
assert.match(body.innerHTML,/class="k-info-content k-participants-tree"/,'Participants use the existing viewport-safe popup placement');
assert.doesNotMatch(body.innerHTML,/data-k-filter="graphMode"|data-k-filter="component"|data-k-filter="entry"|data-k-edge-style/);
const before=JSON.stringify(t.graphModel(v));v.filters.presentation='matrix';t.draw(v);assert.equal(JSON.stringify(t.graphModel(v)),before,'Matrix uses precisely the same facts');
t.unmount();
''')

    def test_snapshot_revision_failure_never_publishes_partial_facts(self):
        self.run_node(r'''
const {view:v}=mount('revision-failure','architecture');await settle();
const original=JSON.stringify(v.items);responder=async(action,args)=>action==='context'?{...context,revision:8}:action==='search'?{revision:7,items:[{id:'partial',kind:'entity',type:'class'}],more:false,next:null}:{};
await t.refresh(v);assert.equal(JSON.stringify(v.items),original);assert.equal(v.initialized,false);assert.equal(v.loading,false);assert.match(v.error,/Каталог изменился|изменились|разных версий/);assert.doesNotMatch(body.innerHTML,/data-k-cy role/);t.unmount();
''')

    def test_follow_reveals_exact_row_without_graph_camera_focus_or_history_change(self):
        self.run_node(r'''
const {view:v,root:r}=mount('follow','architecture');await settle();
let focused=0;const pane={scrollTop:120,scrollLeft:0,dataset:{kBrowserMode:'catalog'},getBoundingClientRect:()=>({top:100,bottom:300})};
const folder={tagName:'DETAILS',dataset:{kFileFolder:'src/main'},open:false,parentElement:pane};
const classes=new Set(),row={dataset:{kSelect:'exact'},parentElement:folder,classList:{toggle:(name,on)=>on?classes.add(name):classes.delete(name)},getBoundingClientRect:()=>({top:330,bottom:360}),focus:()=>focused++};
const status={textContent:''};pane.querySelectorAll=()=>[row];pane.querySelector=s=>s==='[data-k-follow-status]'?status:null;
r.querySelector=s=>s==='[data-k-body]'?body:s==='.k-catalog'?pane:null;
v.canvasSelection=['exact'];v.canvasItem='exact';v.canvasInspect={id:'exact',kind:'entity',type:'class',source:{path:'src/main/F.java'}};
const before={camera:JSON.stringify(v.viewport),history:JSON.stringify(v.navigation),requests:requests.length,html:body.innerHTML};
for(const mode of ['catalog','graph']){v.filters.browser=mode;pane.dataset.kBrowserMode=mode;folder.open=false;pane.scrollTop=120;v.filters.followSelection=false;t.followNavigator(v);assert.equal(folder.open,false);assert.equal(pane.scrollTop,120);v.filters.followSelection=true;t.followNavigator(v);assert.equal(folder.open,true);assert.equal(pane.scrollTop,180);assert.ok(classes.has('selected'));}
assert.equal(focused,0);assert.equal(JSON.stringify(v.viewport),before.camera);assert.equal(JSON.stringify(v.navigation),before.history);assert.equal(requests.length,before.requests);assert.equal(body.innerHTML,before.html);
v.canvasItem='missing';v.canvasSelection=['missing'];t.followNavigator(v);assert.match(status.textContent,/отсутствует/);t.unmount();
''')
