"""Focused tests for the compound-edge SVG routing contract."""
from pathlib import Path
import shutil
import subprocess
import unittest


WEB = Path(__file__).resolve().parents[2] / 'tools/project-portal/web'


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class ArchitectureRoutingUiTest(unittest.TestCase):
    def test_topology_ports_are_deterministic_and_cleanup_restores_native_edges(self):
        code = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
class El {constructor(tag){this.tagName=tag;this.children=[];this.style={};this.dataset={};this.listeners={};this.ownerDocument=doc;}get firstChild(){return this.children[0]}setAttribute(k,v){this[k]=String(v)}append(...xs){this.children.push(...xs)}appendChild(x){this.children.push(x)}removeChild(x){this.children.splice(this.children.indexOf(x),1)}remove(){this.removed=true}addEventListener(k,v){this.listeners[k]=v}}
const doc={createElementNS(_ns,tag){return new El(tag)}};
const node=(id,b,parent)=>({id:()=>id,length:1,boundingBox:()=>b,ancestors:()=>({contains:n=>n===parent}),position:()=>({x:(b.x1+b.x2)/2,y:(b.y1+b.y2)/2}),outerWidth:()=>b.x2-b.x1,outerHeight:()=>b.y2-b.y1});
const parent=node('parent',{x1:0,y1:0,x2:200,y2:160},null),child=node('child',{x1:50,y1:50,x2:100,y2:100},parent),other=node('other',{x1:300,y1:40,x2:380,y2:100},null);
const mk=(id,s,t,type)=>({id:()=>id,source:()=>s,target:()=>t,selected:()=>false,data:k=>k==='type'?type:'',style(k,v){if(v!==undefined)this[k]=v;return this[k]||1}});
const special=mk('special',parent,child,'contains'),self=mk('self',child,child,'uses'),ordinary=mk('ordinary',child,other,'uses');
const events=new Map(),camera={x:0,y:0,z:1},cy={edges:()=>[ordinary,special,self],on:(name,fn)=>events.set(name,fn),off:(name)=>events.delete(name),pan:()=>({x:camera.x,y:camera.y}),zoom:()=>camera.z};
const ctx={window:{},document:doc,setTimeout,clearTimeout,requestAnimationFrame:fn=>fn};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-routing.js','utf8'),ctx);
const cytoscape=require(process.argv[1]+'/vendor/cytoscape.js');const real=cytoscape({headless:true,elements:[{data:{id:'p'}},{data:{id:'c',parent:'p'}},{data:{id:'e',source:'p',target:'c'}}]});assert.equal(ctx.window.ArchitectureRouting.special(real.getElementById('e')),true);real.destroy();
assert.equal(ctx.window.ArchitectureRouting.special(special),true);assert.equal(ctx.window.ArchitectureRouting.special(self),true);assert.equal(ctx.window.ArchitectureRouting.special(ordinary),false);
const container={ownerDocument:doc,style:{},appendChild(x){this.children=(this.children||[]).concat(x)}};
const selected=[];const dispose=ctx.window.ArchitectureRouting.mount(cy,container,{select:e=>selected.push(e.id())});assert.equal(container.children.length,1);const svg=container.children[0],layer=svg.children[0];assert.equal(layer.children.length,2);assert.equal(special.opacity,0);assert.equal(self.opacity,0);assert.match(layer.children[0].children[0].d,/^M/);
const first=layer.children.map(g=>g.children[0].d);dispose.render();assert.deepEqual(layer.children.map(g=>g.children[0].d),first,'stable sorted model geometry');camera.z=.2;camera.x=42;dispose.render();assert.deepEqual(layer.children.map(g=>g.children[0].d),first,'Zoom changes only the transform');assert.match(layer.transform,/translate\(42 0\) scale\(0.2\)/);layer.children[0].children[2].listeners.click({stopPropagation(){}});assert.equal(selected.length,1);dispose();assert.equal(special.opacity,1);assert.equal(self.opacity,1);
for(const count of [16,96,256]){
 const elements=[{data:{id:'root'}}];for(let i=0;i<count;i++)elements.push({data:{id:'leaf'+i,parent:'root'},position:{x:i%16*220,y:Math.floor(i/16)*160}},{data:{id:'edge'+i,source:'root',target:'leaf'+i}});
 elements.push({data:{id:'reverse',source:'leaf0',target:'root'}});
 const fixture=cytoscape({headless:true,styleEnabled:true,elements,layout:{name:'preset'},style:[{selector:'node',style:{width:160,height:70}},{selector:':parent',style:{padding:56}}]});
 const target={ownerDocument:doc,style:{},appendChild(x){this.svg=x}};const cleanup=ctx.window.ArchitectureRouting.mount(fixture,target),groups=()=>target.svg.children[0].children;
 assert.equal(groups().length,count+1);
 const paths=()=>groups().map(g=>[g.dataset.edgeId,g.children[0].d]);const stable=JSON.stringify(paths());
 for(const group of groups()){const edge=fixture.getElementById(group.dataset.edgeId),values=group.children[0].d.match(/-?\d+(?:\.\d+)?(?:e[+-]?\d+)?/gi).map(Number),s=edge.source().boundingBox({includeLabels:false,includeOverlays:false}),t=edge.target().boundingBox({includeLabels:false,includeOverlays:false});assert.ok(values.every(Number.isFinite));assert.equal(values[1],s.y1);assert.equal(values[7],t.y1);assert.ok(values[0]>=s.x1&&values[0]<=s.x2);assert.ok(values[6]>=t.x1&&values[6]<=t.x2);const min=Math.min(values[1],values[7]),max=Math.max(values[1],values[7]);assert.ok(values[3]>=min&&values[3]<=max&&values[5]>=min&&values[5]<=max,'No cubic overshoot');}
 fixture.zoom(.1);fixture.pan({x:100,y:-30});cleanup.render();assert.equal(JSON.stringify(paths()),stable);
 fixture.add([{data:{id:'loop-a',source:'leaf0',target:'leaf0'}},{data:{id:'loop-b',source:'leaf0',target:'leaf0'}}]);cleanup.render();const loops=paths().filter(([id])=>id.startsWith('loop-'));assert.equal(loops.length,2);assert.notEqual(loops[0][1],loops[1][1],'Parallel loops have distinct bounded ports');cleanup();fixture.destroy();
}
'''
        result = subprocess.run(['node', '-e', code, str(WEB)], cwd=WEB, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
