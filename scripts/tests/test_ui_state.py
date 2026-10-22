"""Run browser-state contracts in a dependency-free Node VM."""
from pathlib import Path
import shutil
import subprocess
import unittest


class UiStateTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_closed_retained_dialog_resets_scroll_and_open_refresh_preserves_it(self):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/ui-state.js'
        code = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const listeners={},frames=[];let callback,options;
const dialog={nodeName:'DIALOG',open:true,dataset:{},className:'task-editor',getAttribute:()=> 'Edit task',closest:()=>dialog,querySelectorAll:()=>[pane]};
const pane={id:'editor-fields',dataset:{},scrollTop:240,scrollLeft:12,closest:()=>dialog};
const document={body:{},querySelectorAll:()=>[dialog],addEventListener:(name,fn)=>listeners[name]=fn};
const ctx={window:{},document,requestAnimationFrame:fn=>frames.push(fn),MutationObserver:class{constructor(fn){callback=fn;}observe(root,value){options=value;}}};
vm.createContext(ctx);const source=fs.readFileSync(process.argv[1],'utf8');vm.runInContext(source.slice(source.indexOf('// Dialog resource updates')),ctx);
const flush=()=>{while(frames.length)frames.shift()();},scroll=ctx.window.HubDialogScroll;
assert.equal(options.attributes,true);assert.ok(options.attributeFilter.includes('open'));
listeners.scroll({target:pane});pane.scrollTop=0;callback([{type:'childList',target:dialog,addedNodes:[],removedNodes:[]}]);flush();assert.equal(pane.scrollTop,240,'same open dialog retains scroll after its content updates');
dialog.open=false;callback([{type:'attributes',attributeName:'open',oldValue:'',target:dialog}]);flush();pane.scrollTop=0;dialog.open=true;callback([{type:'attributes',attributeName:'open',oldValue:null,target:dialog}]);flush();assert.equal(pane.scrollTop,0,'closed DOM dialog must not preserve scroll into another opening');
pane.scrollTop=240;listeners.scroll({target:pane});pane.scrollTop=0;scroll.restore();assert.equal(pane.scrollTop,240,'same user offset may be recorded again after reopening');
// close+reopen in the same mutation batch must also forget the old opening.
pane.scrollTop=0;callback([{type:'attributes',attributeName:'open',oldValue:'',target:dialog},{type:'attributes',attributeName:'open',oldValue:null,target:dialog}]);flush();assert.equal(pane.scrollTop,0);
pane.scrollTop=150;listeners.scroll({target:pane});dialog.open=false;listeners.close({target:dialog});pane.scrollTop=0;dialog.open=true;scroll.restore();assert.equal(pane.scrollTop,0,'native close event also clears retained offsets');
'''
        result = subprocess.run(['node', '-e', code, str(source)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_storage_validation_isolation_and_url_precedence(self):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/ui-state.js'
        code = r'''
const vm = require('node:vm'), fs = require('node:fs'), assert = require('node:assert/strict');
const data = new Map(), listeners = {};
const ctx = {URLSearchParams, location:{search:''}, document:{addEventListener:(n,f)=>listeners[n]=f},
 localStorage:{getItem:k=>data.get(k)||null,setItem:(k,v)=>data.set(k,v)},
 activeProject:'a', taskFilter:'all',taskTypeFilter:'all',taskPriorityFilter:'all',taskSearch:'',taskListSort:'created',taskSort:'created',historyTask:'',historyKind:'',diagnosticSearch:'', route:()=>['tasks']};
vm.createContext(ctx); vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
ctx.taskFilter='active';ctx.taskSearch='needle';ctx.taskListSort='priority';ctx.taskSort='updated';ctx.historyKind='git';ctx.diagnosticSearch='chat';ctx.saveUiState();
ctx.taskFilter='all';ctx.taskSearch='';ctx.restoreUiState();assert.equal(ctx.taskFilter,'active');assert.equal(ctx.taskSearch,'needle');assert.equal(ctx.historyKind,'git');assert.equal(ctx.diagnosticSearch,'chat');
ctx.location.search='?taskSort=title&sort=created-oldest';ctx.restoreUiState();assert.equal(ctx.taskListSort,'title');assert.equal(ctx.taskSort,'created-oldest');
ctx.activeProject='b';ctx.location.search='';ctx.restoreUiState();assert.equal(ctx.taskFilter,'all');assert.equal(ctx.taskSearch,'');assert.equal(ctx.historyKind,'');assert.equal(ctx.diagnosticSearch,'');
data.set('project-hub-ui:v1:b','{bad');ctx.restoreUiState();assert.equal(ctx.taskListSort,'created');
data.set('project-hub-ui:v1:b',JSON.stringify({tasks:{status:'bogus',search:42,sort:[]},history:{kind:'bad'}}));ctx.restoreUiState();assert.equal(ctx.taskFilter,'all');assert.equal(ctx.taskSearch,'');assert.equal(ctx.historyKind,'');
ctx.route=()=>['history','linked-task'];ctx.restoreUiState();assert.equal(ctx.historyTask,'linked-task');
ctx.localStorage={getItem:()=>{throw Error('denied')},setItem:()=>{throw Error('quota')}};ctx.restoreUiState();ctx.saveUiState();
'''
        result = subprocess.run(['node', '-e', code, str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_dialog_scroll_survives_replacement_loading_and_explicit_navigation(self):
        source=Path(__file__).resolve().parents[2]/'tools/project-portal/web/ui-state.js'
        code=r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert');let dialogs=[],mutation,frames=[];const listeners={};
function dialog(key,max=1000){let top=0;const d={dataset:{dialogScrollKey:key},className:'modal',children:[],getAttribute:()=>null,closest:()=>d,querySelectorAll:()=>[],matches:()=>true,get scrollTop(){return top;},set scrollTop(x){top=Math.min(x,max);},scrollLeft:0};return d;}
const document={body:{},querySelectorAll:()=>dialogs,addEventListener:(event,fn)=>listeners[event]=fn};
const ctx={window:{},document,requestAnimationFrame:fn=>frames.push(fn),MutationObserver:class{constructor(fn){mutation=fn;}observe(){}},console};vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const scroll=ctx.window.HubDialogScroll;let old=dialog('journal:0');dialogs=[old];old.scrollTop=640;listeners.scroll({target:old});
// Short loading markup clamps the DOM but must not replace the desired offset.
let loading=dialog('journal:0',40);dialogs=[loading];mutation([{target:loading,addedNodes:[],removedNodes:[]}]);frames.shift()();assert.equal(loading.scrollTop,40);listeners.scroll({target:loading});
let ready=dialog('journal:0');dialogs=[ready];mutation([{target:ready,addedNodes:[],removedNodes:[]}]);frames.shift()();assert.equal(ready.scrollTop,640);
ready.scrollTop=180;listeners.scroll({target:ready});let updated=dialog('journal:0');dialogs=[updated];scroll.restore(document);assert.equal(updated.scrollTop,180);
// A different page, or a closed/reopened dialog, starts at the top.
let next=dialog('journal:20');dialogs=[next];scroll.restore(document);assert.equal(next.scrollTop,0);dialogs=[];scroll.restore(document);dialogs=[dialog('journal:0')];scroll.restore(document);assert.equal(dialogs[0].scrollTop,0);
"""
        result=subprocess.run(['node','-e',code,str(source)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_origin_wide_menu_preference_reload_compact_and_blocked_storage(self):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/ui-state.js'
        code = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const values=new Map([['project-hub-menu:v1','compact']]);
const make=(blocked=false)=>{const root={dataset:{}},docHandlers={},winHandlers={},select={id:'setting-menu-mode',value:''},status={textContent:''};
 const document={documentElement:root,addEventListener:(n,f)=>(docHandlers[n]??=[]).push(f),getElementById:id=>id==='setting-menu-mode'?select:id==='menu-preference-status'?status:null};
 const storage=blocked?{getItem(){throw Error('denied')},setItem(){throw Error('denied')}}:{getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)};
 const ctx={document,localStorage:storage,window:{addEventListener:(n,f)=>(winHandlers[n]??=[]).push(f),matchMedia:()=>({matches:false,addEventListener(){}})},location:{search:''},activeProject:'p',route:()=>['tasks'],console};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);return {ctx,root,docHandlers,winHandlers,select,status};};
let first=make();assert.equal(first.root.dataset.hubMenu,'compact');
values.set('project-hub-menu:v1','auto');let auto=make();assert.equal(auto.root.dataset.hubMenu,'auto');
values.set('project-hub-menu:v1','bogus');let malformed=make();assert.equal(malformed.root.dataset.hubMenu,'auto');
values.set('project-hub-menu:v1','compact');let reload=make();assert.equal(reload.root.dataset.hubMenu,'compact');
const change=first.docHandlers.change.find(fn=>fn);change({target:{id:'setting-menu-mode',value:'auto'}});assert.equal(values.get('project-hub-menu:v1'),'auto');assert.equal(first.root.dataset.hubMenu,'auto');
first.ctx.activeProject='other';assert.equal(values.get('project-hub-menu:v1'),'auto');assert.equal([...values.keys()].some(k=>k.includes('ui:v1')) ,false);
const blocked=make(true);assert.equal(blocked.root.dataset.hubMenu,'auto');
const blockedChange=blocked.docHandlers.change.find(fn=>fn);blockedChange({target:{id:'setting-menu-mode',value:'compact'}});assert.equal(blocked.root.dataset.hubMenu,'compact');assert.match(blocked.status.textContent,/хранилище браузера недоступно/);
const external=make();external.winHandlers.storage.find(fn=>fn)({key:'project-hub-menu:v1',newValue:'compact'});assert.equal(external.root.dataset.hubMenu,'compact');assert.equal(external.select.value,'compact');
external.winHandlers.storage.find(fn=>fn)({key:'project-hub-menu:v1',newValue:'auto'});assert.equal(external.root.dataset.hubMenu,'auto');assert.equal(external.select.value,'auto');
external.winHandlers.storage.find(fn=>fn)({key:'project-hub-menu:v1',newValue:null});assert.equal(external.root.dataset.hubMenu,'auto');
'''
        result = subprocess.run(['node','-e',code,str(source)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,(result.stdout or '')+(result.stderr or ''))
