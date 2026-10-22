"""Progressive maps and native compound / orthogonal layout regressions."""
from pathlib import Path
import shutil
import subprocess
import unittest

from scripts.tests.test_knowledge_ui import HARNESS, WEB


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class ArchitectureMapUiTest(unittest.TestCase):
    def test_invalid_or_missing_elk_route_has_explicit_diagnostic(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');let mode='missing';
ctx.window.ELK=class{async layout(g){g.width=500;g.height=200;for(const n of g.children){n.x=0;n.y=0;}if(mode==='remote')for(const e of g.edges)e.sections=[{id:'s',startPoint:{x:1,y:1},endPoint:{x:1e8,y:1e8}}];return g;}};
const cy=cytoscape({headless:true,styleEnabled:true,elements:[{data:{id:'a'}},{data:{id:'b'}},{data:{id:'ab',source:'a',target:'b'}}]});
await assert.rejects(()=>map.elkLayout(cy,()=>{},()=>true),/не построен маршрут/);mode='remote';await assert.rejects(()=>map.elkLayout(cy,()=>{},()=>true),/геометрия маршрута/);assert.equal(cy.knowledgeRoutes,undefined);cy.destroy();
''')

    def test_large_actual_elk_ports_remain_on_resized_compound_borders(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js'),ELK=require(process.argv[1]+'/vendor/elk-api.js'),worker=require(process.argv[1]+'/vendor/elk-worker.min.js');
ctx.window.ELK=function(){const engine=new ELK({workerFactory:()=>new worker.Worker()}),layout=engine.layout.bind(engine);engine.layout=g=>layout(JSON.parse(JSON.stringify(g)));return engine;};
for(const count of [16,96,256]){
 const elements=[{data:{id:'root0'}},{data:{id:'root1'}}];
 for(let g=0;g<8;g++)elements.push({data:{id:'g'+g,parent:'root'+(g<4?0:1)}});
 for(let i=0;i<count;i++){elements.push({data:{id:'n'+i,parent:'g'+Math.floor(i/(count/8))}});for(const d of [1,7,count/2+3])elements.push({data:{id:'e'+i+'_'+d,source:'n'+i,target:'n'+((i+d)%count)}});}
 for(let g=0;g<8;g++)elements.push({data:{id:'group'+g,source:'g'+g,target:'g'+((g+3)%8)}});
 const cy=cytoscape({headless:true,styleEnabled:true,elements,layout:{name:'preset'},style:[{selector:'node',style:{width:195,height:90,padding:8}},{selector:':parent',style:{padding:56}},{selector:'edge',style:{'curve-style':'round-taxi'}}]});
 try{
  await map.elkLayout(cy,()=>{},()=>true);map.routeEdges(cy,'round-taxi');
  const check=()=>{for(const edge of cy.edges()){const points=cy.knowledgeRoutes.get(edge.id());assert.ok(points?.length>1,'Missing route '+count+' '+edge.id()+' routes='+cy.knowledgeRoutes.size);for(let i=1;i<points.length;i++){const a=points[i-1],b=points[i];assert.ok(Number.isFinite(b.x)&&Number.isFinite(b.y));assert.ok(Math.abs(a.x-b.x)<1e-7||Math.abs(a.y-b.y)<1e-7,'Nonorthogonal '+count+' '+edge.id()+' '+JSON.stringify(points));}for(const [node,p] of [[edge.source(),points[0]],[edge.target(),points.at(-1)]]){const c=node.position(),w=node.outerWidth()/2,h=node.outerHeight()/2;assert.ok(Math.abs(p.x-c.x)<=w+1e-6&&Math.abs(p.y-c.y)<=h+1e-6,'Outside '+count+' '+edge.id()+' '+node.id()+' '+JSON.stringify({p,c,w,h}));assert.ok(Math.min(Math.abs(Math.abs(p.x-c.x)-w),Math.abs(Math.abs(p.y-c.y)-h))<1e-6,'Actual frame/card border');}}};
  check();const positions=cy.nodes(':childless').map(n=>[n.id(),{...n.position()}]);
  cy.getElementById('n0').position('x',cy.getElementById('n0').position('x')+1000);cy.getElementById('n0').position('y',cy.getElementById('n0').position('y')+800);map.routeEdges(cy,'round-taxi');map.finishRoutes(cy);check();
  cy.batch(()=>positions.forEach(([id,p])=>{cy.getElementById(id).position('x',p.x);cy.getElementById(id).position('y',p.y)}));map.routeEdges(cy,'round-taxi');map.finishRoutes(cy);check();
  cy.nodes(':childless').style('width',260);map.routeEdges(cy,'round-taxi');check();cy.nodes(':childless').style('width',195);map.routeEdges(cy,'round-taxi');check();
 }finally{cy.destroy();}
}
''')
    def run_node(self, code):
        result = subprocess.run(['node', '-e', HARNESS + "\nvm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-map.js','utf8'),ctx);const map=ctx.window.ArchitectureMap;\n(async()=>{\n" + code + '\n})().catch(e=>{console.error(e);process.exitCode=1;});', str(WEB)], capture_output=True, text=True, encoding='utf-8', timeout=45)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_progressive_expansion_shared_neighbors_collapse_and_revision(self):
        self.run_node(r'''
const {view:v}=mount('expand','architecture');await settle();v.filters.graphMode='neighborhood';v.selected='a';v.items=[{id:'a',kind:'entity',type:'class',title:'A'},{id:'keep',kind:'entity',type:'class',title:'Keep'}];v.relations=[];
const entities={a:v.items[0],b:{id:'b',kind:'entity',type:'interface',title:'B'},c:{id:'c',kind:'entity',type:'class',title:'C'},d:{id:'d',kind:'entity',type:'class',title:'D'}};
const edges=[{id:'ab',kind:'relation',from:'a',to:'b',type:'implements',provenance:'static',evidence:[{path:'src/a.java',line:3}]},{id:'ac',kind:'relation',from:'a',to:'c',type:'uses'}, {id:'bd',kind:'relation',from:'b',to:'d',type:'uses'},{id:'cd',kind:'relation',from:'c',to:'d',type:'uses'}];
const api=async(action,args)=>action==='context'?{revision:7}:action==='read'?entities[args.id]:{revision:7,items:edges.filter(e=>(e.from===args.endpoint||e.to===args.endpoint)&&(!args.type||e.type===args.type)),more:false};
const base={nodes:[entities.a],relations:[]};
await map.expand(v,'a','interfaces',api,base);let m=map.model(v,base);assert.deepEqual(Array.from(m.nodes,n=>n.id),['a','b']);assert.equal(m.relations[0].evidence[0].line,3);
await map.expand(v,'a','neighbors',api,m);m=map.model(v,base);assert.equal(m.nodes.length,3);assert.equal(m.relations.length,2);
await map.expand(v,'b','dependencies',api,m);await map.expand(v,'c','dependencies',api,map.model(v,base));m=map.model(v,base);assert.equal(m.nodes.length,4);
map.collapse(v,'b',base);m=map.model(v,base);assert.ok(m.nodes.some(n=>n.id==='d'),'Shared neighbor is retained by C');assert.ok(!m.relations.some(e=>e.id==='bd'));
map.collapse(v,'a',base);assert.equal(map.model(v,base).nodes.length,1);assert.equal(map.branches(v).size,0);
await assert.rejects(()=>map.expand(v,'a','neighbors',async(action,args)=>action==='context'?{revision:8}:api(action,args),base),/обновились|изменилась/);assert.equal(map.branches(v).size,0);
const changing=async(action,args)=>action==='context'?{revision:7}:{revision:args.offset?8:7,items:[],more:true,next:100};
await map.expand(v,'a','neighbors',changing,base);
await assert.rejects(()=>map.expand(v,'a','neighbors',changing,base,true),/обновились/);map.collapse(v,'a',base);
await map.expand(v,'a','neighbors',api,base);v.context.revision=8;assert.equal(map.branches(v).size,0);
assert.equal(map.branches(t.view('other-project','architecture')).size,0);
''')

    def test_progressive_transport_cursor_and_filter_isolation(self):
        self.run_node(r'''
const {view:v}=mount('pages','architecture');await settle();v.selected='a';v.filters.graphMode='neighborhood';const a={id:'a',kind:'entity',type:'class',title:'A'},base={nodes:[a],relations:[]};
const reads=[];let queries=0;const api=async(action,args)=>{if(action==='context')return {revision:7};if(action==='read'){reads.push(args.id);return {id:args.id,kind:'entity',type:'class'};}queries++;return {revision:7,items:Array.from({length:2},(_,i)=>({id:'e'+(args.offset+i),kind:'relation',type:'uses',from:'a',to:'b'+(args.offset+i)})),more:args.offset<4,next:args.offset+2};};
let branch=await map.expand(v,'a','neighbors',api,base);assert.equal(branch.nodes.length,2);assert.equal(queries,1);assert.equal(branch.continuation[0].next,2,'Use actual short transport page cursor');
await map.expand(v,'a','neighbors',api,map.model(v,base));assert.equal(queries,1,'Repeated expansion uses cache');
branch=await map.expand(v,'a','neighbors',api,map.model(v,base),true);assert.equal(branch.nodes.length,4);assert.equal(branch.continuation[0].next,4);
branch=await map.expand(v,'a','neighbors',api,map.model(v,base),true);assert.equal(branch.nodes.length,6);assert.equal(branch.continuation.length,0);assert.equal(new Set(reads).size,reads.length,'Do not read already loaded endpoints');
for(const field of ['entry','audience','section']){v.filters[field]='changed';assert.equal(map.model(v,base).nodes.length,1,field+' must isolate expanded branches');v.filters[field]='';}
''')

    def test_hierarchy_file_tree_types_and_invalid_parent_cycle(self):
        self.run_node(r'''
const {view:v}=mount('tree','architecture');await settle();v.filters.graphMode='neighborhood';
v.componentItems=[{id:'component:app',kind:'entity',type:'component',title:'Application'}, {id:'component:ui',kind:'entity',type:'component',title:'UI',parent:'component:app'}];
const nodes=[{id:'class:a',kind:'entity',type:'class',title:'A <unsafe>',component:'ui',source:{path:'src\\ui\\A.java'}},{id:'interface:b',kind:'entity',type:'interface',title:'B',component:'ui',source:{path:'src/ui/A.java'}},{id:'file:a',kind:'entity',type:'file',title:'src/ui/A.java',source:{path:'src/ui/A.java'}}];
let m=map.model(v,{nodes,relations:[]});assert.equal(m.parents.get('class:a'),'component:ui');assert.equal(m.parents.get('component:ui'),'component:app');
v.filters.groupBy='types';m=map.model(v,{nodes,relations:[]});assert.ok(m.nodes.some(n=>n.type==='group'));assert.equal(m.parents.get(m.parents.get('class:a')),'component:ui');assert.equal(nodes[0].parent,undefined,'Presentation groups do not mutate scanner facts');
let html=map.fileTree(v,nodes);assert.match(html,/data-k-file-folder="src\/ui\/A.java"/);assert.match(html,/A &lt;unsafe&gt;/);assert.equal((html.match(/data-k-select="class:a"/g)||[]).length,1);
v.entryItems=[nodes[0]];v.scenarios=[{id:'view:start',title:'Start'}];html=map.tree(v);assert.match(html,/data-k-tree-id="component:ui"/);assert.match(html,/Точки входа|Сценарии/);assert.doesNotMatch(html,/<unsafe>/);
v.componentItems=[{id:'a',type:'component',parent:'b'},{id:'b',type:'component',parent:'a'}];v.filters.groupBy='components';m=map.model(v,{nodes:v.componentItems,relations:[]});assert.equal(m.parents.size,0,'Malformed parent cycles must never reach Cytoscape');
''')

    def test_canonical_component_leaf_opens_source_types_and_groups_scenarios(self):
        self.run_node(r'''
const {view:v}=mount('leaf','architecture');await settle();v.filters.graphMode='components';v.selected='component:leaf';
v.context=context;v.componentItems=[{id:'component:app',kind:'entity',type:'component',title:'App'}, {id:'component:leaf',kind:'entity',type:'component',title:'Leaf',parent:'component:app'}];
const leaf=v.componentItems[1],member={id:'type:member',kind:'entity',type:'class',title:'Member',component:'component:leaf'},peer={...member,id:'type:peer',title:'Peer'},internal={id:'internal',kind:'relation',from:member.id,to:peer.id,type:'uses',provenance:'static'},external={...internal,id:'external',to:'outside'};
assert.equal(t.componentLevel(v)[0].id,leaf.id,'A leaf must remain a visible expansion root');
const request=async(action,args)=>action==='context'?context:action==='search'?{revision:7,items:args.kind==='entity'&&args.component===leaf.id?[member,peer]:args.endpoint===member.id?[internal,external]:[],more:false}:null;
assert.equal((await map.availability(v,leaf.id,request,{nodes:[leaf],relations:[]})).structure,true);
await map.expand(v,leaf.id,'structure',request,{nodes:[leaf],relations:[]});
assert.ok(map.model(v,{nodes:[leaf],relations:[]}).nodes.some(n=>n.id===member.id),'Canonical component ID must retrieve its types');
assert.equal(map.model(v,{nodes:[leaf],relations:[]}).relations.map(e=>e.id).join(','),'internal','Composition shows real relationships of its visible types and excludes outside endpoints');
v.entryItems=[{id:'entry',title:'Entry',component:leaf.id}];v.scenarios=[{id:'scenario',title:'Save <document>',component:leaf.id}];v.filters.treeFolders={'scenarios:component:app':false};
const html=map.tree(v);assert.ok(html.includes('data-k-tree-folder="entries:component:app"'));assert.ok(html.includes('data-k-tree-folder="scenarios:component:app"><summary>'));assert.ok(html.includes('Save &lt;document&gt;'));
''')

    def test_refresh_opens_explicit_code_context_and_navigation_clears_entry_filter(self):
        self.run_node(r'''
const leaf={id:'component:leaf',kind:'entity',type:'component',title:'Leaf'},member={id:'type:member',kind:'entity',type:'class',title:'Member',component:leaf.id};
responder=async(action,args)=>action==='context'?context:action==='read'?args.id===leaf.id?leaf:member:action==='search'?{revision:7,items:args.type==='component'?[leaf]:args.kind==='entity'&&args.component===leaf.id?[member]:[],more:false,next:null}:{};
const {view:v,root}=mount('leaf-refresh','architecture');await settle();v.selected=leaf.id;v.filters.graphMode='components';v.filters.componentContext='code';await t.refresh(v);
assert.ok(t.graphModel(v).nodes.some(n=>n.id===member.id),'Opening a leaf shows its source composition');
v.filters.entry='yes';root.click({preventDefault(){},target:{closest:selector=>selector==='[data-k-tree-id]'?{dataset:{kTreeId:leaf.id,kTreeMode:'components'}}:null}});assert.equal(v.filters.entry,'');await settle();
root.click({preventDefault(){},target:{closest:selector=>selector==='[data-k-tree-id]'?{dataset:{kTreeId:'',kTreeMode:'overview'}}:null}});await settle();assert.equal(v.filters.graphMode,'components');assert.ok(!requests.some(r=>r.action==='read'&&r.args.id===''),'Project overview must refresh rather than read an empty ID');
''')

    def test_keyboard_folder_selection_and_leaf_arrows(self):
        self.run_node(r'''
const {root}=mount('keyboard-tree','architecture');await settle();let focused='';
const folder={open:false,querySelector:()=>summary};
const row=(id,tag,parent)=>({tagName:tag,parentElement:parent||{tagName:'NAV'},getClientRects:()=>[{}],matches:selector=>tag==='BUTTON',closest:()=>id==='overview'?null:folder,focus:()=>{focused=id;}});
const overview=row('overview','BUTTON'),summary=row('summary','SUMMARY'),button=row('selector','BUTTON',summary),leaf=row('leaf','BUTTON');
const tree={querySelectorAll:()=>[overview,summary,button,leaf]};
const key=(target,value)=>root.keydown({key:value,preventDefault(){},target:{closest:selector=>selector==='.k-architecture-tree'?tree:target}});
key(button,'ArrowDown');assert.equal(focused,'leaf','Folder selection button shares its summary position');
key(button,'ArrowRight');assert.equal(folder.open,true);key(button,'ArrowLeft');assert.equal(folder.open,false);
focused='leaf';key(leaf,'ArrowRight');assert.equal(focused,'leaf');key(leaf,'ArrowLeft');assert.equal(focused,'summary');
''')

    def test_direct_actions_availability_and_file_structure(self):
        self.run_node(r'''
const {view:v}=mount('actions','architecture');await settle();const file={id:'file:a',kind:'entity',type:'file',title:'A.java'},type={id:'type:a',kind:'entity',type:'class',title:'A'},empty={id:'pom',kind:'entity',type:'file',title:'pom.xml'},base={nodes:[file,empty],relations:[]};let queries=0;
const api=async(action,args)=>{if(action==='context')return {revision:7};if(action==='read')return type;queries++;return {revision:7,items:args.endpoint==='file:a'?[{id:'decl',kind:'relation',type:'contains',from:'file:a',to:'type:a'}]:[],more:false};};
let a=await map.availability(v,'pom',api,base);assert.equal(a.structure,false);assert.equal(a.dependencies,false);assert.equal(a.inheritance,false);const count=queries;await map.availability(v,'pom',api,base);assert.equal(count,queries,'Availability shares cached promise');
a=await map.availability(v,'file:a',api,base);assert.equal(a.structure,true);assert.equal(a.neighbors,false);await map.expand(v,'file:a','structure',api,base);const result=map.model(v,base);assert.ok(result.nodes.some(n=>n.id==='type:a'));assert.equal(result.relations[0].type,'contains');
assert.match(t.graph(v),/data-k-action="expand-direct"/);assert.doesNotMatch(t.graph(v),/data-k-expand-mode/);assert.match(t.graph(v),/aria-label="Раскрыть: Интерфейсы"/);
''')

    def test_native_fcose_compound_cards_clearance_and_repeatability(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');ctx.cytoscape=cytoscape;
for(const name of ['layout-base','cose-base','cytoscape-fcose'])vm.runInContext(fs.readFileSync(process.argv[1]+'/vendor/'+name+'.js','utf8'),ctx);
ctx.window.cytoscapeFcose=ctx.cytoscapeFcose;
const {view:v,root:r}=mount('compound','architecture');await settle();v.filters.graphMode='neighborhood';v.selected='a';v.componentItems=[{id:'component:app',kind:'entity',type:'component',title:'Application'},{id:'component:ui',kind:'entity',type:'component',title:'Editor',parent:'component:app'},{id:'component:core',kind:'entity',type:'component',title:'Core',parent:'component:app'}];
v.items=Array.from({length:20},(_,i)=>({id:i?'node'+i:'a',kind:'entity',type:i%3?'class':'interface',title:'RectangularClassName'+i,component:i%2?'ui':'core'}));
v.relations=v.items.slice(1).map((n,i)=>({id:'r'+i,kind:'relation',from:'a',to:n.id,type:'uses'}));v.drafts.set('a',{item:v.items[0]});v.neighbors=v.items.slice(1);
const container={};r.querySelector=s=>s==='[data-k-cy]'?container:s==='[data-k-body]'?body:null;
const instances=[];ctx.window.cytoscape=options=>{const cy=cytoscape({headless:true,styleEnabled:true,elements:JSON.parse(JSON.stringify(options.elements)),style:JSON.parse(JSON.stringify(options.style)),layout:{name:'preset'},minZoom:.01});cy.width=()=>1100;cy.height=()=>750;cy.resize=()=>cy;const native=cy.layout.bind(cy);cy.layout=o=>native({...o,boundingBox:o.boundingBox?JSON.parse(JSON.stringify(o.boundingBox)):undefined,positions:o.positions?JSON.parse(JSON.stringify(o.positions)):undefined});instances.push(cy);return cy;};
try{
t.draw(v);const cy=instances.at(-1);assert.equal(t.cyLayout(v).name,'fcose');assert.equal(cy.nodes(':parent').length,3);
const nodes=cy.nodes(':childless');for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++){const a=nodes[i].boundingBox(),b=nodes[j].boundingBox();assert.ok(a.x2<=b.x1||b.x2<=a.x1||a.y2<=b.y1||b.y2<=a.y1,'Cards overlap '+nodes[i].id()+' / '+nodes[j].id());}
const first=JSON.stringify(v.positionCache.get(cy.knowledgeKey));await t.action(v,'auto-layout');assert.equal(JSON.stringify(v.positionCache.get(cy.knowledgeKey)),first);await t.action(v,'auto-layout');assert.equal(JSON.stringify(v.positionCache.get(cy.knowledgeKey)),first);
}finally{t.unmount();instances.forEach(cy=>cy.destroy());}
''')

    def test_real_elk_layered_layout_routes_and_determinism(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js'),ELK=require(process.argv[1]+'/vendor/elk-api.js'),worker=require(process.argv[1]+'/vendor/elk-worker.min.js');
ctx.window.ELK=function(){const engine=new ELK({workerFactory:()=>new worker.Worker()}),layout=engine.layout.bind(engine);engine.layout=g=>layout(JSON.parse(JSON.stringify(g)));return engine;};
const nodes=Array.from({length:9},(_,i)=>({data:{id:'n'+i,label:'Class '+i,font:12,width:195,height:i%3?72:110}}));
const edges=Array.from({length:8},(_,i)=>({data:{id:'e'+i,source:'n0',target:'n'+(i+1),type:i%2?'imports':'uses',label:'relation',countLabel:''}}));
const cy=cytoscape({headless:true,styleEnabled:true,elements:[...nodes,...edges],style:JSON.parse(JSON.stringify(t.cyStyle)),layout:{name:'preset'}});
try{
let done=0;await map.elkLayout(cy,()=>done++,()=>true);assert.equal(done,1);assert.equal(cy.knowledgeRoutes.size,8);
const pos=JSON.stringify(cy.nodes().map(n=>n.position()));await map.elkLayout(cy,()=>done++,()=>true);assert.equal(JSON.stringify(cy.nodes().map(n=>n.position())),pos);
for(let i=0;i<9;i++)for(let j=i+1;j<9;j++){const a=cy.nodes()[i].boundingBox(),b=cy.nodes()[j].boundingBox();assert.ok(a.x2<=b.x1||b.x2<=a.x1||a.y2<=b.y1||b.y2<=a.y1);}
for(const points of cy.knowledgeRoutes.values())for(let i=1;i<points.length;i++)assert.ok(Math.abs(points[i].x-points[i-1].x)<.01||Math.abs(points[i].y-points[i-1].y)<.01,'ELK route segments are orthogonal');
map.routeEdges(cy,'round-taxi');assert.ok(cy.edges().some(e=>e.style('curve-style')==='round-segments'));assert.notEqual(cy.getElementById('e0').style('line-color'),cy.getElementById('e1').style('line-color'));
const old=cy.knowledgeRoutes;await map.elkLayout(cy,()=>done++,()=>false);assert.equal(done,2);assert.equal(cy.knowledgeRoutes,old,'Stale async layout cannot replace current result');
}finally{cy.destroy();}
''')

    def test_nested_elk_frames_do_not_overlap_unrelated_nodes(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js'),ELK=require(process.argv[1]+'/vendor/elk-api.js'),worker=require(process.argv[1]+'/vendor/elk-worker.min.js');ctx.window.ELK=function(){const e=new ELK({workerFactory:()=>new worker.Worker()}),layout=e.layout.bind(e);e.layout=g=>layout(JSON.parse(JSON.stringify(g)));return e;};
const nodes=[{id:'app',full:'Application',type:'component'},{id:'ui',parent:'app',full:'UI and launch',type:'component'},{id:'core',parent:'app',full:'Core runtime',type:'component'},{id:'shared',full:'Shared formats',type:'component'},{id:'api',parent:'shared',full:'Public interfaces',type:'component'},...Array.from({length:12},(_,i)=>({id:'n'+i,parent:i<4?'ui':i<8?'core':'api',label:'Class '+i,type:'class'}))].map(n=>({data:{label:n.full||n.label,font:12,width:195,height:90,headerOffset:140,...n}}));
const edges=Array.from({length:11},(_,i)=>({data:{id:'e'+i,source:'n0',target:'n'+(i+1),type:'uses',label:'uses',countLabel:''}}));const cy=cytoscape({headless:true,styleEnabled:true,elements:[...nodes,...edges],style:JSON.parse(JSON.stringify(t.cyStyle)),layout:{name:'preset'}});
try{await map.elkLayout(cy,()=>{},()=>true);const first=JSON.stringify(cy.nodes().map(n=>[n.id(),n.position()]));await map.elkLayout(cy,()=>{},()=>true);assert.equal(JSON.stringify(cy.nodes().map(n=>[n.id(),n.position()])),first,'Parent input sizes must not depend on previous layout');
const all=cy.nodes();for(let i=0;i<all.length;i++)for(let j=i+1;j<all.length;j++){const a=all[i],b=all[j];if(a.ancestors().contains(b)||b.ancestors().contains(a))continue;const x=a.boundingBox({includeLabels:false}),y=b.boundingBox({includeLabels:false});assert.ok(x.x2<=y.x1||y.x2<=x.x1||x.y2<=y.y1||y.y2<=x.y1,'Unrelated frames overlap: '+a.id()+' / '+b.id());}
for(const n of cy.nodes(':parent')){const b=n.boundingBox({includeLabels:false});for(const child of n.children()){const c=child.boundingBox({includeLabels:false});assert.ok(c.y1>=b.y1+map.inset-2,'Header reservation '+n.id());assert.ok(c.x1>=b.x1+map.inset-2);}}
for(const edge of cy.edges()){const points=cy.knowledgeRoutes.get(edge.id());assert.ok(points?.length>1);for(const [node,point] of [[edge.source(),points[0]],[edge.target(),points.at(-1)]]){const b=node.boundingBox({includeLabels:false});assert.ok(point.x>=b.x1-2&&point.x<=b.x2+2&&point.y>=b.y1-2&&point.y<=b.y2+2,'ELK endpoint must touch its leaf, not a compound boundary: '+edge.id());}}
map.routeEdges(cy,'round-taxi');assert.ok(cy.edges().every(e=>e.style('edge-distances')==='endpoints'));
}finally{cy.destroy();}
''')

    def test_elk_linked_sections_preserve_complete_route(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
ctx.window.ELK=function(){return {layout:async input=>{assert.equal(input.layoutOptions['elk.json.edgeCoords'],'ROOT');return {id:'architecture-root',width:700,height:400,children:[{id:'a',x:100,y:100,width:210,height:90},{id:'b',x:400,y:200,width:210,height:90}],edges:[{id:'ab',sources:['a'],targets:['b'],sections:[{id:'last',incomingSections:['first'],startPoint:{x:350,y:145},bendPoints:[{x:350,y:245}],endPoint:{x:400,y:245},outgoingShape:'b'},{id:'first',incomingShape:'a',startPoint:{x:310,y:145},endPoint:{x:350,y:145},outgoingSections:['last']}]}]};}};};
const cy=cytoscape({headless:true,styleEnabled:true,elements:[{data:{id:'a',label:'A',font:12,width:195,height:72}},{data:{id:'b',label:'B',font:12,width:195,height:72}},{data:{id:'ab',source:'a',target:'b',type:'uses',countLabel:''}}],style:JSON.parse(JSON.stringify(t.cyStyle)),layout:{name:'preset'}});
try{await map.elkLayout(cy,()=>{},()=>true);assert.equal(JSON.stringify(cy.knowledgeRoutes.get('ab')),JSON.stringify([{x:310,y:145},{x:350,y:145},{x:350,y:245},{x:400,y:245}]));map.routeEdges(cy,'round-taxi');assert.equal(cy.edges()[0].style('edge-distances'),'endpoints');}finally{cy.destroy();}
''')

    def test_canvas_wheel_zoom_is_continuous_adaptive_and_clamped(self):
        self.run_node(r'''
const canvas=ctx.window.ArchitectureCanvas;assert.ok(canvas);
assert.ok(canvas.wheelZoom(.8,.1)>.8);assert.ok(canvas.wheelZoom(2,.1)>2);
assert.ok(Math.abs(canvas.wheelZoom(1,.1)-canvas.wheelZoom(1-.000001,.1))<.00001);
assert.ok(canvas.wheelZoom(2,.1)>2&&canvas.wheelZoom(2,.1)<2*10**.1);
assert.ok((canvas.wheelZoom(.2,.1)-.2)/.2 > (canvas.wheelZoom(2,.1)-2)/2,'Linear low-scale gain is materially larger');
assert.ok(canvas.wheelZoom(.1,-100,.2,3)>=.2);assert.ok(canvas.wheelZoom(3,100,.2,3)<=3);
for(const zoom of [.02,.2,.99,1,1.5,3.9]){const next=canvas.wheelZoom(zoom,.1,.01,4);assert.ok(next>=zoom&&next<=zoom*10**.1+1e-12);}
''')

    def test_canvas_right_button_only_pans_and_native_drag_preserves_routes(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js'),canvas=ctx.window.ArchitectureCanvas;
const cy=cytoscape({headless:true,elements:[{data:{id:'app'}},{data:{id:'ui',parent:'app'}},{data:{id:'first',parent:'ui'}},{data:{id:'second',parent:'app'}},{data:{id:'outside'}},{data:{id:'edge',source:'first',target:'outside'}}],layout:{name:'preset'},style:[{selector:'node',style:{width:40,height:30}}]});
const nativePan=cy.pan.bind(cy);cy.pan=value=>value===undefined?nativePan():nativePan(JSON.parse(JSON.stringify(value)));
for(const [id,x,y] of [['app',100,100],['ui',120,120],['first',140,140],['second',180,180],['outside',300,300]]){const node=cy.getElementById(id);node.position('x',x);node.position('y',y);}
const container={style:{},listeners:{},addEventListener:(n,f)=>container.listeners[n]=f,removeEventListener:(n,f)=>{if(container.listeners[n]===f)delete container.listeners[n]}};cy.getElementById('app').select();cy.getElementById('ui').select();const selectedBefore=cy.nodes(':selected').map(n=>n.id()).sort().join(','),positionsBefore=JSON.stringify(cy.nodes().map(n=>n.position()));const routes=new Map([['edge',[{x:0,y:0}]]]);cy.knowledgeRoutes=routes;cy.zoom(2);let motions=0;
const cleanup=canvas.bind(cy,container,{motion:()=>motions++});const emit=(name,target,x,y)=>target.emit({type:name,originalEvent:{button:2,clientX:x,clientY:y,preventDefault(){}}});
for(const target of [cy.getElementById('app'),cy.getElementById('outside'),cy.getElementById('edge'),cy]){const panBefore={...cy.pan()};emit('cxttapstart',target,10,20);emit('cxtdrag',target,30,50);emit('cxttapend',target,30,50);assert.notDeepEqual(cy.pan(),panBefore,'Right drag pans over every target');assert.equal(cy.nodes(':selected').map(n=>n.id()).sort().join(','),selectedBefore,'Right drag preserves selection');assert.equal(JSON.stringify(cy.nodes().map(n=>n.position())),positionsBefore,'Right drag preserves node positions');assert.equal(cy.knowledgeRoutes,routes,'Right drag preserves routes');}
const node=cy.getElementById('outside'),panAfter={...cy.pan()},motionBefore=motions;emit('cxttapstart',node,10,20);emit('cxttapend',node,10,20);assert.deepEqual(cy.pan(),panAfter,'Right click does not pan');assert.equal(cy.nodes(':selected').map(n=>n.id()).sort().join(','),selectedBefore,'Right click preserves selection');node.emit({type:'tap'});assert.equal(cy.knowledgeRoutes,routes,'A native click does not clear routes');node.emit({type:'drag'});assert.equal(cy.knowledgeRoutes,routes,'A native node drag preserves routes');assert.equal(motions,motionBefore+1);
cleanup();assert.equal(Object.keys(container.listeners).length,0);node.emit('drag');assert.equal(cy.knowledgeRoutes,routes,'Cleanup removes the native drag listener');assert.equal(motions,motionBefore+1);cy.pan=nativePan;cy.destroy();
''')

    def test_route_edges_preserves_unrelated_routes_and_translates_incident_geometry(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');
const nodes=[['a',0,0],['b',100,100],['c',260,100],['d',420,0]].map(([id,x,y])=>({data:{id},position:{x,y}}));
const edges=[['ab','a','b'],['bc','b','c'],['cd','c','d']].map(([id,source,target])=>({data:{id,source,target,type:'uses'}}));
const cy=cytoscape({headless:true,styleEnabled:true,elements:[...nodes,...edges],style:[{selector:'node',style:{width:20,height:20}},{selector:'edge',style:{'curve-style':'bezier'}}],layout:{name:'preset'}});try{const setPos=(id,x,y)=>{const node=cy.getElementById(id);node.position('x',x);node.position('y',y);};const validRoute=points=>{for(let i=0;i<points.length;i++){assert.ok(Number.isFinite(points[i].x)&&Number.isFinite(points[i].y));if(i){assert.ok(points[i].x===points[i-1].x||points[i].y===points[i-1].y);assert.ok(points[i].x!==points[i-1].x||points[i].y!==points[i-1].y);}}for(let i=1;i+1<points.length;i++){const a=points[i-1],b=points[i],c=points[i+1];assert.ok(!(a.x===b.x&&b.x===c.x&&((a.y<b.y&&b.y>c.y)||(a.y>b.y&&b.y<c.y))));assert.ok(!(a.y===b.y&&b.y===c.y&&((a.x<b.x&&b.x>c.x)||(a.x>b.x&&b.x<c.x))));}};
cy.knowledgeRoutes=new Map([
 ['ab',[{x:10,y:0},{x:50,y:0},{x:50,y:100},{x:90,y:100}]],
 ['bc',[{x:110,y:100},{x:180,y:100},{x:180,y:140},{x:250,y:140},{x:250,y:100}]],
 ['cd',[{x:270,y:100},{x:330,y:100},{x:330,y:0},{x:410,y:0}]]
]);
const copyRoutes=()=>new Map([...cy.knowledgeRoutes].map(([id,points])=>[id,JSON.parse(JSON.stringify(points))]));
map.routeEdges(cy,'round-taxi');const initialStyles=new Map(cy.edges().map(edge=>[edge.id(),{curve:edge.style('curve-style'),weights:edge.style('segment-weights'),distances:edge.style('segment-distances')}])) ;
const plain=value=>JSON.parse(JSON.stringify(value));const original=copyRoutes(),delta={x:20,y:30};setPos('a',20,30);
// The route model follows the moved leaf endpoint while preserving its orthogonal bends.
map.routeEdges(cy,'round-taxi',cy.getElementById('a').connectedEdges());
assert.deepEqual(plain(cy.knowledgeRoutes.get('ab')[0]),{x:30,y:30});assert.ok(cy.knowledgeRoutes.get('ab').some(p=>p.x===50&&p.y===100),'Central trunk bend remains where feasible');assert.deepEqual(plain(cy.knowledgeRoutes.get('ab').at(-1)),plain(original.get('ab').at(-1)));assert.deepEqual(plain(cy.knowledgeRoutes.get('bc')),plain(original.get('bc')));assert.deepEqual(plain(cy.knowledgeRoutes.get('cd')),plain(original.get('cd')));for(const points of cy.knowledgeRoutes.values())validRoute(points);
assert.equal(cy.getElementById('cd').style('curve-style'),initialStyles.get('cd').curve);assert.equal(cy.getElementById('cd').style('segment-weights'),initialStyles.get('cd').weights);for(const points of cy.knowledgeRoutes.values())for(let i=1;i<points.length;i++)assert.ok(points[i].x===points[i-1].x||points[i].y===points[i-1].y,'Route remains orthogonal');
setPos('a',0,0);map.routeEdges(cy,'round-taxi',cy.getElementById('a').connectedEdges());assert.deepEqual(plain(cy.knowledgeRoutes.get('ab')),plain(original.get('ab')),'Returning the leaf restores the original path');
setPos('a',20,30);setPos('b',120,130);map.routeEdges(cy,'round-taxi',cy.getElementById('a').connectedEdges().union(cy.getElementById('b').connectedEdges()));assert.deepEqual(plain(cy.knowledgeRoutes.get('ab')),plain(original.get('ab')).map(point=>({x:point.x+delta.x,y:point.y+delta.y})),'Shared source/target motion translates the complete internal route');
}finally{cy.destroy();}
''')

    def test_route_geometry_survives_large_sequential_moves_and_shared_translation(self):
        self.run_node(r'''
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js'),plain=value=>JSON.parse(JSON.stringify(value));
const nodes=[['source',0,0],['mid',160,120],['target',340,0],['other',520,220]].map(([id,x,y])=>({data:{id},position:{x,y}}));
const edges=[['direct','source','target'],['bent','source','mid'],['vertical','source','mid'],['upper','source','target'],['external','mid','other']].map(([id,source,target])=>({data:{id,source,target,type:'uses'}}));
const cy=cytoscape({headless:true,styleEnabled:true,elements:[...nodes,...edges],style:[{selector:'node',style:{width:20,height:20}},{selector:'edge',style:{'curve-style':'bezier'}}],layout:{name:'preset'}});
const setPos=(id,x,y)=>{const node=cy.getElementById(id);node.position('x',x);node.position('y',y);};
const validRoute=points=>{for(let i=0;i<points.length;i++){const p=points[i],a=points[i-1],b=points[i-2];assert.ok(Number.isFinite(p.x)&&Number.isFinite(p.y));if(a){assert.ok(p.x===a.x||p.y===a.y,'Orthogonal segments');assert.ok(p.x!==a.x||p.y!==a.y,'No duplicate knee');}if(b)assert.ok(!(b.x===a.x&&a.x===p.x)&&!(b.y===a.y&&a.y===p.y),'No stale collinear knees or reversals');}};
try{
cy.knowledgeRoutes=new Map([
 ['direct',[{x:10,y:0},{x:330,y:0}]],
 ['bent',[{x:10,y:0},{x:70,y:0},{x:70,y:120},{x:150,y:120}]],
 ['vertical',[{x:0,y:10},{x:0,y:70},{x:160,y:70},{x:160,y:110}]],
 ['upper',[{x:0,y:-10},{x:0,y:-70},{x:340,y:-70},{x:340,y:-10}]],
 ['external',[{x:170,y:120},{x:250,y:120},{x:250,y:220},{x:510,y:220}]]]);
map.routeEdges(cy,'round-taxi');const original=new Map([...cy.knowledgeRoutes].map(([id,points])=>[id,plain(points)])),externalStyle=cy.getElementById('external').style('segment-weights');
const incident=cy.getElementById('source').connectedEdges();
for(const [x,y] of [[260,260],[-240,-180],[0,350],[0,-350],[500,-100],[-350,0],[500,300],[-250,400],[0,0]]){
 setPos('source',x,y);map.routeEdges(cy,'round-taxi',incident);
 for(const edge of incident){const points=plain(cy.knowledgeRoutes.get(edge.id())),old=original.get(edge.id());validRoute(points);assert.deepEqual(points[0],{x:old[0].x+x,y:old[0].y+y});assert.deepEqual(points.at(-1),old.at(-1));
  const dot=(a,b,c,d)=>(b.x-a.x)*(d.x-c.x)+(b.y-a.y)*(d.y-c.y);assert.ok(dot(points[0],points[1],old[0],old[1])>0,'Source departure side');assert.ok(dot(points.at(-1),points.at(-2),old.at(-1),old.at(-2))>0,'Target arrival side');
 }
 assert.deepEqual(plain(cy.knowledgeRoutes.get('external')),original.get('external'));assert.equal(cy.getElementById('external').style('segment-weights'),externalStyle);
}
for(const edge of incident)assert.deepEqual(plain(cy.knowledgeRoutes.get(edge.id())),original.get(edge.id()),'Return restores original route');
const targetEdges=cy.getElementById('target').connectedEdges();
for(const [x,y] of [[-220,400],[800,-350],[-220,-400],[340,0]]){
 setPos('target',x,y);map.routeEdges(cy,'round-taxi',targetEdges);
 for(const edge of targetEdges){const points=plain(cy.knowledgeRoutes.get(edge.id())),old=original.get(edge.id());validRoute(points);assert.deepEqual(points[0],old[0]);assert.deepEqual(points.at(-1),{x:old.at(-1).x+x-340,y:old.at(-1).y+y});}
}
map.finishRoutes(cy,incident);map.finishRoutes(cy,incident);map.routeEdges(cy,'round-taxi',incident);assert.deepEqual(plain(cy.knowledgeRoutes.get('direct')),original.get('direct'),'Repeated finish is stable');
setPos('source',320,0);map.routeEdges(cy,'round-taxi',incident);const direct=cy.getElementById('direct');assert.equal(direct.style('curve-style'),'round-segments','Touching ports retain their orthogonal detour');assert.equal(direct.style('edge-distances'),'node-position');validRoute(cy.knowledgeRoutes.get('direct'));
const degenerate=cytoscape({headless:true,styleEnabled:true,elements:[{data:{id:'s'},position:{x:0,y:0}},{data:{id:'t'},position:{x:0,y:0}},{data:{id:'st',source:'s',target:'t'}}],layout:{name:'preset'}});try{degenerate.knowledgeRoutes=new Map([['st',[{x:0,y:0},{x:30,y:0},{x:30,y:20},{x:0,y:20},{x:0,y:0}]]]);const e=degenerate.edges()[0];e.style({'curve-style':'round-segments','segment-distances':'999','source-endpoint':'300% 300%'});map.routeEdges(degenerate,'round-taxi');assert.equal(e.style('curve-style'),'round-taxi');assert.equal(e.style('source-endpoint'),'outside-to-node');assert.equal(parseFloat(e.style('segment-distances')),0,'Degenerate geometry clears the stale route');}finally{degenerate.destroy();}
setPos('source',0,0);map.routeEdges(cy,'round-taxi',incident);assert.equal(direct.style('curve-style'),'straight');
const delta={x:40,y:-60};setPos('source',delta.x,delta.y);setPos('mid',160+delta.x,120+delta.y);map.routeEdges(cy,'round-taxi',incident.union(cy.getElementById('mid').connectedEdges()));
for(const id of ['bent','vertical'])assert.deepEqual(plain(cy.knowledgeRoutes.get(id)),original.get(id).map(p=>({x:p.x+delta.x,y:p.y+delta.y})),'Internal route translates completely');
assert.deepEqual(plain(cy.knowledgeRoutes.get('external')[0]),{x:170+delta.x,y:120+delta.y});assert.deepEqual(plain(cy.knowledgeRoutes.get('external').at(-1)),original.get('external').at(-1),'External target stays fixed');for(const points of cy.knowledgeRoutes.values())validRoute(points);
}finally{cy.destroy();}
''')

    def test_canvas_selection_stats_expands_nested_groups_and_counts_edges(self):
        self.run_node(r'''
const canvas=ctx.window.ArchitectureCanvas;const model={nodes:[{id:'root',type:'group'},{id:'nested',type:'group'},{id:'a',type:'class',component:'app',entrypoint:true,source:{path:'a'}},{id:'b',type:'interface',component:'app'},{id:'c',type:'class',component:'core'},{id:'outside',type:'file'}],parents:new Map([['nested','root'],['a','nested'],['b','nested'],['c','root']]),relations:[{id:'inside',from:'a',to:'b',type:'uses',count:2},{id:'inside2',from:'b',to:'a',type:'implements'},{id:'out',from:'a',to:'outside',type:'reads'},{id:'in',from:'outside',to:'b',type:'imports'}]};const plain=value=>JSON.parse(JSON.stringify(value));
const stats=canvas.selectionStats(model,['root']);assert.equal([...stats.memberIds].sort().join(','),'a,b,c,nested,root');assert.equal(stats.selectedCount,1);assert.equal(stats.groupCount,2);assert.equal(stats.nodeCount,3);assert.deepEqual(plain(stats.types),{class:2,interface:1});assert.equal(stats.components,2);assert.equal(stats.entrypoints,1);assert.equal(stats.sourceCount,1);assert.equal(stats.internalCount,2);assert.deepEqual(plain(stats.internalTypes),{uses:1,implements:1});assert.equal(stats.incomingCount,1);assert.deepEqual(plain(stats.incomingTypes),{imports:1});assert.equal(stats.outgoingCount,1);assert.deepEqual(plain(stats.outgoingTypes),{reads:1});assert.equal(stats.aggregateCount,2);
const nestedStats=canvas.selectionStats(model,['root','nested','a']);assert.equal(nestedStats.nodeCount,3);assert.equal(nestedStats.internalCount,2);assert.equal(nestedStats.aggregateCount,2);
const edgeOnly=canvas.selectionStats(model,['inside','out']);assert.equal(edgeOnly.selectedCount,2);assert.equal(edgeOnly.selectedRelationCount,2);assert.deepEqual(plain(edgeOnly.selectedRelationTypes),{uses:1,reads:1});assert.equal(edgeOnly.memberIds.length,0);
const mixed=canvas.selectionStats(model,['a','inside']);assert.equal(mixed.nodeCount,1);assert.equal(mixed.selectedRelationCount,1);assert.equal(mixed.internalCount,0);
''')

    def test_canvas_group_labels_hide_offscreen_and_cache_bounds_until_invalidated(self):
        self.run_node(r'''
const canvas=ctx.window.ArchitectureCanvas;let zoom=1,pan={x:0,y:0},bounds=0;const node={id:()=> 'group',data:key=>key==='full'?'Group <title>':null,boundingBox:()=>{bounds++;return {x1:100,y1:100,w:80,h:60}}};const cy={nodes:()=>({map:fn=>[node].map(fn)}),zoom:()=>zoom,pan:()=>pan,width:()=>200,height:()=>150,destroyed:()=>false};const layer={innerHTML:'',children:[]};Object.defineProperty(layer,'children',{get(){return this.innerHTML?Array.from({length:1},()=>({style:{}})):[]}});const labels=canvas.groupLabels(cy,layer,s=>s.replace('<','&lt;'));labels.render();assert.match(layer.innerHTML,/Group &lt;title>/);const first=bounds;pan={x:20,y:10};labels.render();assert.equal(bounds,first,'Panning reuses world bounds');pan={x:-1000,y:0};labels.render();assert.equal(layer.innerHTML,'');zoom=.5;labels.render();assert.equal(layer.innerHTML,'');zoom=1;pan={x:0,y:0};labels.invalidate();labels.render();assert.ok(bounds>first);assert.match(layer.innerHTML,/Group &lt;title>/);
''')

    def test_canvas_menu_binding_closes_other_details_and_cleans_document_listeners(self):
        self.run_node(r'''
const canvas=ctx.window.ArchitectureCanvas,handlers=new Map();const doc={addEventListener:(name,fn,capture)=>handlers.set(name,{fn,capture}),removeEventListener:(name,fn,capture)=>{if(handlers.get(name)?.fn===fn)handlers.delete(name)}};
const target={name:'target'},inside={name:'inside'},otherInside={name:'otherInside'};const detail=(child)=>({open:true,contains:value=>value===child,removeAttribute(name){if(name==='open')this.open=false;}});const own=detail(inside),other=detail(otherInside);const root={ownerDocument:doc,isConnected:true,querySelectorAll:selector=>{assert.equal(selector,'details.k-graph-info[open]');return [own,other].filter(menu=>menu.open);}};const fire=(name,event={})=>handlers.get(name).fn(event);
const cleanup=canvas.bindMenus(root);assert.equal(handlers.size,4);fire('pointerdown',{target});assert.equal(own.open,false);assert.equal(other.open,false,'Viewport pointer closes every open menu');own.open=true;other.open=true;fire('click',{target:inside});assert.equal(own.open,true,'Click inside its menu keeps that menu open');assert.equal(other.open,false,'Click inside one menu closes another');own.open=true;other.open=true;fire('click',{target:otherInside});assert.equal(own.open,false);assert.equal(other.open,true);fire('keydown',{key:'Escape',preventDefault(){this.prevented=true;}});assert.equal(own.open,false);assert.equal(other.open,false);
own.open=true;other.open=true;cleanup();assert.equal(handlers.size,0);assert.equal(own.open,true,'Cleanup removes listeners without changing menu state');
''')

    def test_canvas_menus_fit_visible_window_scroll_resize_and_redraw(self):
        self.run_node(r'''
const canvas=ctx.window.ArchitectureCanvas;
const events=()=>({listeners:new Map(),addEventListener(name,fn,capture){this.listeners.set(name,{fn,capture});},removeEventListener(name,fn){if(this.listeners.get(name)?.fn===fn)this.listeners.delete(name);},fire(name,event={}){this.listeners.get(name)?.fn(event);}});
const viewport=Object.assign(events(),{width:280,height:200,offsetLeft:0,offsetTop:0});
let observe,disconnected=false;const win=Object.assign(events(),{innerWidth:280,innerHeight:200,visualViewport:viewport,MutationObserver:class {constructor(fn){observe=fn;}observe(){}disconnect(){disconnected=true;}}});
const doc=Object.assign(events(),{defaultView:win});let menus=[];
const root=Object.assign(events(),{ownerDocument:doc,isConnected:true,contains:menu=>menus.includes(menu),querySelectorAll:()=>menus.filter(m=>m.open)});
const make=(anchor,height=350)=>{
 const style={};Object.defineProperty(style,'cssText',{get(){return Object.entries(this).map(([key,value])=>key+':'+value).join(';');},set(value){assert.equal(value,'');for(const key of Object.keys(this))delete this[key];}});const panel={style,getBoundingClientRect(){return {width:Math.min(500,parseFloat(style.maxWidth)||500),height:Math.min(height,parseFloat(style.maxHeight)||height)};}};
 const summary={getBoundingClientRect:()=>anchor};
 return {open:false,isConnected:true,panel,summary,matches:selector=>selector==='details.k-graph-info',contains(target){return target===this||target===panel||target===summary;},querySelector:selector=>selector==='summary'?summary:panel,removeAttribute(){this.open=false;}};
};
const a=make({left:10,right:50,top:20,bottom:48}),b=make({left:220,right:260,top:160,bottom:188});menus=[a,b];
const cleanup=canvas.bindMenus(root);
const open=menu=>{menu.open=true;root.fire('toggle',{target:menu});};
open(a);assert.equal(a.panel.style.position,'fixed','Fixed positioning escapes graph overflow');assert.equal(a.panel.style.left,'8px','Wide menu at left edge is clamped');assert.equal(a.panel.style.maxWidth,'264px');assert.equal(a.panel.style.top,'52px');assert.equal(a.panel.style.maxHeight,'140px','Tall content scrolls in available space below');
open(b);assert.equal(a.open,false,'Keyboard/native toggle closes the prior menu');assert.equal(a.panel.style.cssText,'');assert.equal(b.panel.style.left,'8px');assert.equal(b.panel.style.top,'8px','Near bottom edge menu fits above summary');assert.equal(b.panel.style.maxHeight,'148px');
viewport.width=180;viewport.height=160;viewport.offsetLeft=40;viewport.offsetTop=20;viewport.fire('resize');assert.equal(b.panel.style.left,'48px');assert.equal(b.panel.style.maxWidth,'164px');assert.equal(b.panel.style.top,'28px');assert.equal(b.panel.style.maxHeight,'128px','Visual viewport offsets are included');
b.summary.getBoundingClientRect=()=>({left:80,right:110,top:30,bottom:58});doc.fire('scroll');assert.equal(b.panel.style.top,'62px');assert.equal(b.panel.style.maxHeight,'110px','Ancestor scroll refits menu');
viewport.width=400;viewport.height=500;viewport.offsetLeft=0;viewport.offsetTop=0;win.fire('resize');assert.equal(b.panel.style.maxWidth,'384px');assert.equal(b.panel.style.top,'62px');assert.equal(b.panel.style.maxHeight,'430px');
doc.fire('pointerdown',{target:b.panel});assert.equal(b.open,true,'Content interactions keep the open menu');doc.fire('keydown',{key:'Escape',preventDefault(){}});assert.equal(b.open,false);assert.equal(b.panel.style.cssText,'');
open(b);b.isConnected=false;menus=[];observe();assert.equal(b.panel.style.cssText,'','Redraw releases detached panel');
const fresh=make({left:120,right:180,top:10,bottom:38},30);menus=[fresh];open(fresh);assert.equal(fresh.panel.style.top,'42px','Delegated toggle fits newly rendered details');
cleanup();assert.equal(fresh.panel.style.cssText,'');assert.equal(disconnected,true);for(const source of [doc,root,win,viewport])assert.equal(source.listeners.size,0,'Cleanup releases every listener');
const css=fs.readFileSync(process.argv[1]+'/knowledge.css','utf8');assert.match(css,/\.k-graph-info>\.k-info-content \{ position:fixed;[^}]*box-sizing:border-box;[^}]*overflow:auto;/);
''')


if __name__ == '__main__':
    unittest.main()
