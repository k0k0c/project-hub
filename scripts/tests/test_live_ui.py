"""Exercise mounted DOM updates, independent of page-specific draft models."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class LiveUiTests(unittest.TestCase):
    def test_mounted_controls_selection_scroll_and_explicit_values(self):
        web = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/live-ui.js'
        code = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
let nextTree,root,frames=[],events={},selected;
class Node {
 constructor(tag,attrs={},children=[]) {this.nodeName=tag.toUpperCase();this.nodeType=tag==='#text'?3:1;this.nodeValue=attrs.text||null;this.attrs={...attrs};delete this.attrs.text;this.childNodes=[];this.parentNode=null;this.scrollTop=0;this.scrollLeft=0;this.value=attrs.value||'';this.type=attrs.type||'text';this.checked=!!attrs.checked;this.open=!!attrs.open;this.selectionStart=0;this.selectionEnd=0;this.selectionDirection='none';for(const n of children)this.insertBefore(n,null);}
 get firstChild(){return this.childNodes[0]||null;} get nextSibling(){if(!this.parentNode)return null;return this.parentNode.childNodes[this.parentNode.childNodes.indexOf(this)+1]||null;}
 get isConnected(){return root?.contains(this)||this===document.body;}
 get attributes(){return Object.entries(this.attrs).map(([name,value])=>({name,value:String(value)}));}
 get disabled(){return this.hasAttribute('disabled');}
 hasAttribute(k){return Object.hasOwn(this.attrs,k);}getAttribute(k){return this.hasAttribute(k)?String(this.attrs[k]):null;}setAttribute(k,v){this.attrs[k]=v;}removeAttribute(k){delete this.attrs[k];}
 contains(n){return n===this||this.childNodes.some(c=>c.contains(n));}
 matches(selector){return selector.split(',').some(s=>{const m=s.match(/^(\w+)(?:\[type="([^"]+)"\])?$/);return m&&m[1].toUpperCase()===this.nodeName&&(!m[2]||this.type===m[2]);});}
 querySelectorAll(){return this.childNodes.flatMap(n=>[...(n.nodeType===1?[n]:[]),...n.querySelectorAll('*')]);}
 insertBefore(n,before){if(n.parentNode)n.remove();const index=before?this.childNodes.indexOf(before):this.childNodes.length;this.childNodes.splice(index,0,n);n.parentNode=this;return n;}
 remove(){if(this.parentNode){this.parentNode.childNodes.splice(this.parentNode.childNodes.indexOf(this),1);this.parentNode=null;}}
 cloneNode(deep){return new Node(this.nodeName,{...this.attrs,...(this.nodeType===3?{text:this.nodeValue}:{})},deep?this.childNodes.map(c=>c.cloneNode(true)):[]);}
 focus(){document.activeElement=this;}setSelectionRange(a,b,d){this.selectionStart=a;this.selectionEnd=b;this.selectionDirection=d;}
}
const document={body:new Node('body'),activeElement:null,addEventListener:(n,f)=>events[n]=f,createElement:tag=>{
 assert.equal(tag,'template');return {set innerHTML(value){this.content=nextTree;}};}};
const window={scrollY:410,scrollX:8,getSelection:()=>selected,scrollTo:p=>{window.scrollY=p.top;window.scrollX=p.left;}};
const ctx={window,document,requestAnimationFrame:f=>frames.push(f)};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const text=new Node('#text',{text:'Evidence remains visible'}),answer=new Node('textarea',{name:'answer',value:'original'}),file=new Node('input',{name:'archive',type:'file'});
file.files=[{name:'example.zip'}];answer.value='unsaved answer';answer.setSelectionRange(2,9,'backward');
const form=new Node('form',{'data-agent-answer':'operation'},[answer,file]),pane=new Node('section',{'data-scroll-key':'inspector'},[form,text]);
root=new Node('main',{id:'content'},[pane]);pane.scrollTop=600;pane.scrollLeft=35;document.activeElement=answer;
selected={rangeCount:1,isCollapsed:false,anchorNode:text,focusNode:text,anchorOffset:2,focusOffset:8,setBaseAndExtent(a,x,b,y){this.anchorNode=a;this.anchorOffset=x;this.focusNode=b;this.focusOffset=y;}};
nextTree=new Node('fragment',{},[new Node('p',{},[new Node('#text',{text:'Updated status'})]),new Node('section',{'data-scroll-key':'inspector'},[new Node('form',{'data-agent-answer':'operation'},[new Node('textarea',{name:'answer',value:'server default'}),new Node('input',{name:'archive',type:'file'})]),new Node('#text',{text:'Evidence remains visible'})])]);
ctx.window.HubLiveUI.patch(root,'updated');while(frames.length)frames.shift()();
assert.equal(root.childNodes[1],pane);assert.equal(pane.firstChild,form);assert.equal(form.firstChild,answer);assert.equal(answer.value,'unsaved answer');assert.equal(document.activeElement,answer);
assert.deepEqual([answer.selectionStart,answer.selectionEnd,answer.selectionDirection],[2,9,'backward']);assert.equal(form.childNodes[1],file);assert.equal(file.files[0].name,'example.zip');
assert.deepEqual([pane.scrollTop,pane.scrollLeft,window.scrollY,window.scrollX],[600,35,410,8]);assert.equal(selected.anchorNode,text);assert.equal(selected.anchorOffset,2);assert.equal(selected.focusOffset,8);
// Foreground saves use the authoritative draft value without remounting fields.
ctx.window.HubLiveUI.patch(root,'saved',{preserveInputs:false});assert.equal(answer.value,'server default');assert.equal(document.activeElement,answer);
// A user scroll between painting and a delayed restoration wins over the snapshot.
events.wheel();pane.scrollTop=125;window.scrollY=75;while(frames.length)frames.shift()();assert.equal(pane.scrollTop,125);assert.equal(window.scrollY,75);
// Explicit navigation can omit state restoration and start a different page.
selected=null;document.activeElement=document.body;nextTree=new Node('fragment',{},[new Node('section',{id:'different'})]);
ctx.window.HubLiveUI.patch(root,'navigate',{preserveState:false,preserveInputs:false});assert.equal(root.firstChild.getAttribute('id'),'different');assert.equal(document.activeElement,document.body);
'''
        result = subprocess.run(['node','-e',code,str(web)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__ == '__main__':
    unittest.main()
