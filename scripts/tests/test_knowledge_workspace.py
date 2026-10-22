"""Focused contract checks for the architecture workspace controls."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("node"), "Node is required")
class KnowledgeWorkspaceTest(unittest.TestCase):
    def test_clamps_persists_disposes_and_closes_dialogs(self):
        source = Path(__file__).resolve().parents[2] / "tools/project-portal/web/knowledge-workspace.js"
        script = r"""
const vm=require('node:vm'), fs=require('node:fs'), assert=require('node:assert/strict');
const store=new Map(), listeners=new Map();
const document={body:{style:{}},activeElement:null,createElement(){return new El('button')},addEventListener(){},removeEventListener(){}};
class El {
  constructor(name){this.name=name;this.children=[];this.parentNode=null;this.dataset={};this.style={setProperty:(k,v)=>this.style[k]=v};this.handlers={};this.className='';this.disabled=false;}
  addEventListener(n,f){this.handlers[n]=f} removeEventListener(n){delete this.handlers[n]}
  appendChild(x){this.children.push(x);x.parentNode=this;return x}
  insertBefore(x,before){const i=this.children.indexOf(before);if(i<0)this.children.push(x);else this.children.splice(i,0,x);x.parentNode=this;return x}
  remove(){this.parentNode?.children.splice(this.parentNode.children.indexOf(this),1)}
  setAttribute(k,v){this[k]=v} getAttribute(k){return this[k]}
  getBoundingClientRect(){return {width:this.width||800}}
  setPointerCapture(){}
  querySelector(selector){if(selector.includes('[data-k-action="close-panel"]'))return this.closeButton||null;return null}
  querySelectorAll(){return []}
  closest(){return null}
  focus(){document.activeElement=this}
}
const layout=new El('layout'), catalog=new El('catalog'), main=new El('main'), inspector=new El('inspector');
layout.width=900;main.width=700;catalog.width=220;inspector.width=250;layout.appendChild(catalog);main.appendChild(inspector);
layout.querySelector=(q)=>q===':scope > .k-catalog'?catalog:null;main.querySelector=(q)=>q===':scope > .k-inspector-container'?inspector:null;
const root=new El('root');root.querySelector=(q)=>q==='.k-layout'?layout:q==='.k-architecture-main'?main:q==':scope > .k-catalog'?catalog:q==':scope > .k-inspector-container'?inspector:null;
const ctx={window:{},globalThis:{},document,localStorage:{getItem:k=>store.get(k)||null,setItem:(k,v)=>store.set(k,v)},queueMicrotask:f=>f()};ctx.window=ctx;vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
assert.equal(ctx.KnowledgeWorkspace.clampWidth('catalog',50,900,250),145);
assert.equal(ctx.KnowledgeWorkspace.clampWidth('inspector',900,700,220),440);
const v={project:'demo',filters:{query:'keep-me',catalogWidth:220,inspectorWidth:250}};
const cleanup=ctx.KnowledgeWorkspace.mount(root,v);
assert.equal(layout.children.length,2);assert.equal(main.children.length,2);
assert.equal(layout.children[1].getAttribute('role'),'separator');assert.equal(main.children[0].getAttribute('role'),'separator');
layout.children[1].handlers.keydown({key:'ArrowRight',shiftKey:false,preventDefault(){}});
assert.equal(v.filters.query,'keep-me');assert.ok(v.filters.catalogWidth>220);
const persisted=JSON.parse(store.get('knowledge:demo:architecture'));assert.equal(persisted.filters.query,'keep-me');assert.equal(persisted.filters.catalogWidth,v.filters.catalogWidth);
const previous={focus(){this.called=true}};document.activeElement=previous;
const backdrop=new El('backdrop'), dialog=new El('dialog'), close=new El('close');close.click=()=>{close.called=true};dialog.closeButton=close;root.querySelector=(q)=>q.includes('dialog')?dialog:q.includes('backdrop')?backdrop:q==='.k-layout'?layout:q==='.k-architecture-main'?main:q==':scope > .k-catalog'?catalog:q==':scope > .k-inspector-container'?inspector:null;
let suppressed=false;root.handlers.keydown({key:'Escape',preventDefault(){suppressed=true;}});assert.equal(close.called,true);assert.equal(suppressed,true);
cleanup();assert.equal(layout.children.length,1);assert.equal(main.children.length,1);
"""
        result = subprocess.run(["node", "-e", script, str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
