"""Workspaces admission, retry and draft preservation in the browser module."""
import subprocess
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[2] / 'tools' / 'project-portal' / 'web' / 'workspaces.js'
HARNESS = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8'),requests=[],posts=[];
class Root {
 constructor(id){this.dataset={codeWorkspaces:id};this.open=false;this.body={innerHTML:''};this.listeners={};}
 matches(s){return s==='[data-code-workspaces]';}
 querySelector(){return this.body;}
 addEventListener(type,cb){(this.listeners[type]??=[]).push(cb);}
 fire(type,target=this){for(const cb of this.listeners[type]||[])cb({target,preventDefault(){}});}
}
const root=new Root('p1'),other=new Root('p2');
let revision=1,management=true;
const context={console,TypeError,crypto:{randomUUID:()=> '12345678-1234-1234-1234-123456789abc'},
 HubI18n:{t:k=>k,error:e=>e.message||e},HubLiveUI:{patch:(n,h)=>n.innerHTML=h},
 document:{querySelectorAll:()=>[root,other]},fetch:async(url,opt={})=>{
 requests.push({url,body:opt.body});
 if(opt.method==='POST'){const ack=posts.shift();if(ack instanceof Error)throw ack;return {ok:ack.status!==409,status:ack.status||200,json:async()=>ack};}
 return {ok:true,json:async()=>({project:url.endsWith('p2')?'p2':'p1',revision,management,items:[{id:'w1',kind:'local',descriptor:{root:'/old'},enabled:true,capabilities:{source:true,git:{state:'detected'},lsp:{state:'not-checked'}}}]})};
}};
vm.createContext(context);vm.runInContext(source,context);
const wait=async()=>{for(let i=0;i<30;i++)await Promise.resolve();};
const button=action=>({closest:()=>({dataset:{workspaceAction:action,workspaceId:'w1'}})});
function form(mode,rootValue){return {dataset:{workspaceForm:mode,workspaceId:mode==='relocate'?'w1':undefined},matches:()=>true,elements:{namedItem:()=>({value:rootValue})}};}
async function main(){
 context.HubWorkspacesUI.afterRender();context.HubWorkspacesUI.afterRender();
 assert.equal(root.listeners.submit.length,1);assert.equal(other.listeners.submit.length,1);
 root.open=true;root.fire('toggle');await wait();
 const f=form('relocate','/draft');root.fire('input',{name:'workspaceRoot',value:'/draft',closest:()=>f});
 const before=context.HubWorkspacesUI.card({id:'p1'});assert.ok(before.includes('/draft')&&before.includes('open'));
 posts.push({project:'wrong',revision:2,workspace:{id:'w1'},roots:[]});root.fire('submit',f);await wait();
 assert.ok(root.body.innerHTML.includes('workspaces.retry'));
 const first=requests.find(r=>r.body).body;root.fire('submit',form('add','/another'));await wait();
 assert.equal(requests.filter(r=>r.body).length,1);
 root.fire('click',button('refresh'));await wait();assert.ok(root.body.innerHTML.includes('/draft'));
 posts.push({project:'p1',revision:2,workspace:{id:'w1'},roots:['/draft']});revision=2;
 root.fire('click',button('retry'));await wait();
 assert.equal(requests.filter(r=>r.body).length,2);assert.equal(requests.filter(r=>r.body)[1].body,first);
 assert.ok(!root.body.innerHTML.includes('workspaces.retry'));
 management=false;root.fire('click',button('refresh'));await wait();
 root.fire('submit',form('add','/blocked'));await wait();assert.equal(requests.filter(r=>r.body).length,2);
 assert.ok(root.body.innerHTML.includes('workspaces.readOnly'));
}
main().catch(error=>{console.error(error);process.exitCode=1});
"""

class WorkspacesUiTest(unittest.TestCase):
    def test_widget_contract(self):
        result = subprocess.run(['node','-e',HARNESS,str(WEB)], capture_output=True,
                                text=True, timeout=30, encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr)

if __name__ == '__main__': unittest.main()
