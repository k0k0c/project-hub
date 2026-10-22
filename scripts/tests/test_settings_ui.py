"""Settings UI contracts, executed without a server or project data."""
from pathlib import Path
import shutil
import subprocess
import unittest


class SettingsUiTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_global_agent_connections_tab_works_without_projects(self):
        source=Path(__file__).resolve().parents[2]/'tools/project-portal/web/settings.js'
        code=r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
let current=['settings','agents'];
const ctx={state:null,activeProject:null,route:()=>current,document:{documentElement:{dataset:{hubLocale:'ru'}},querySelectorAll:()=>[],addEventListener(){}},sessionStorage:{getItem:()=>null},escape:s=>String(s??''),title:()=>'',uiIcon:()=>'',taskTableColumns:[],HubConnectionsUI:{page:()=>'<section id="hub-connections-manager">Universal invitation</section>'},HubAgentProvidersUI:{card:()=>'<section data-agent-providers>Global API settings</section>'}};
vm.createContext(ctx);const web=process.argv[1].replace(/settings\.js$/,'');
vm.runInContext(fs.readFileSync(web+'locale-catalog.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(web+'i18n.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
let html=ctx.settingsPage();assert.match(html,/<a href="#settings\/agents" aria-current="page">Агенты и подключения<\/a>/);
const normalizedHeader=value=>value.replace(/ aria-current="page"/g,'').replace(/\s+>/g,'>');
assert.equal(normalizedHeader(ctx.settingsHeader()),normalizedHeader(ctx.settingsHeader('agents')));
assert.equal(normalizedHeader(ctx.settingsHeader()),normalizedHeader(ctx.settingsHeader('architecture')));
assert.ok(html.includes(ctx.settingsHeader('agents')),'agent settings use the shared settings header and tabs');
assert.match(html,/hub-connections-manager/);assert.doesNotMatch(html,/data-agent-providers|hub-modern-instructions/);
current=['settings','agents','models'];html=ctx.settingsPage();assert.match(html,/data-agent-providers/);assert.doesNotMatch(html,/hub-connections-manager|hub-modern-instructions/);
current=['settings','agents','rules'];html=ctx.settingsPage();assert.match(html,/hub-modern-instructions/);assert.doesNotMatch(html,/hub-connections-manager|data-agent-providers/);
current=['settings','agents'];html=ctx.settingsPage();assert.doesNotMatch(html,/data-settings-project|Проект не выбран/);
assert.doesNotMatch(html,/href="#settings\/instructions"|hub-legacy-codex/);assert.equal((html.match(/<a href="#settings(?:\/agents|\/architecture)?"/g)||[]).length,3);assert.match(html,/#settings\/agents\/apps/);assert.match(html,/#settings\/agents\/models/);assert.match(html,/#settings\/agents\/rules/);
ctx.HubI18n.apply('en');html=ctx.settingsPage();assert.match(html,/<h1>Settings<\/h1>/);assert.doesNotMatch(html,/[А-Яа-яЁё]/);
current=['settings'];assert.doesNotMatch(ctx.settingsPage(),/data-agent-providers|hub-connections-manager/,'connections configured in global tab');
ctx.state={settings:{revision:'r1',settings:{git:{autoCommit:true}}}};ctx.activeProject='example';const general=ctx.settingsPage();assert.match(general,/Version control/);assert.doesNotMatch(general,/[А-Яа-яЁё]/);assert.match(general,/setting-git-autoCommit[^>]*checked[^>]*disabled/);assert.equal((general.match(/id="setting-git-autoCommit"/g)||[]).length,1);
current=['settings','instructions'];assert.match(ctx.settingsPage(),/href="#settings\/agents" aria-current="page"/);assert.doesNotMatch(ctx.settingsPage(),/Create an invitation in Projects|Hub instructions and capabilities|hub-legacy-codex/);
'''
        result=subprocess.run(['node','-e',code,str(source)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_empty_project_tabs_and_failed_workflow_do_not_reload_forever(self):
        source=Path(__file__).resolve().parents[2]/'tools/project-portal/web/settings.js'
        code=r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
let current=['settings','architecture'],calls=0;
const ctx={state:null,activeProject:null,
 document:{documentElement:{dataset:{hubLocale:'ru'}},querySelectorAll:()=>[],addEventListener(){},getElementById(){return null}},sessionStorage:{getItem:()=>null},
 escape:s=>String(s??''),title:()=>'',uiIcon:()=>'',route:()=>current,
 fetch:async()=>{calls++;throw Error('offline')},render(){},taskTableColumns:[]};
vm.createContext(ctx);const web=process.argv[1].replace(/settings\.js$/,'');
vm.runInContext(fs.readFileSync(web+'locale-catalog.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(web+'i18n.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
assert.match(ctx.settingsPage(),/Проект не выбран/);
assert.doesNotMatch(ctx.settingsPage(),/setting-architecture-model|Codex/);
ctx.HubI18n.apply('en');assert.match(ctx.settingsPage(),/No project selected/);
assert.doesNotMatch(ctx.settingsPage(),/[А-Яа-яЁё]/);
current=['settings','instructions'];assert.match(ctx.settingsPage(),/Agent work rules/);
assert.doesNotMatch(ctx.settingsPage(),/setting-architecture-model|Codex|[А-Яа-яЁё]/);
(async()=>{await ctx.loadModernWorkflow();await ctx.loadModernWorkflow();assert.equal(calls,1);assert.match(ctx.settingsPage(),/Could not load the instructions/);})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result=subprocess.run(['node','-e',code,str(source)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_overview_epic_visibility(self):
        web = Path(__file__).resolve().parents[2] / 'tools/project-portal/web'
        code = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const ctx={state:{settings:{revision:'one',settings:{}},tasks:[
 {id:'epic',type:'epic',status:'active'}, {id:'task',type:'task',status:'planned'},
 {id:'bug',type:'bug',status:'active'}, {id:'legacy',status:'queued'},
 {id:'closed',type:'epic',status:'done'}],project:{name:'Test'},events:[]},
 activeProject:'one',window:{},document:{addEventListener(){}},sessionStorage:{getItem:()=>null},
 title:()=>'',uiIcon:()=>'',escape:s=>s,taskTableColumns:[],currentWorkSummary:()=>'',taskLink:()=>'',estimate:()=>'',
 taskSort:'created',sortedTasks:t=>t,taskCard:t=>`<article>${t.id}</article>`,eventView:()=>''};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/settings.js','utf8'),ctx);
const app=fs.readFileSync(process.argv[1]+'/app.js','utf8');
vm.runInContext(app.slice(app.indexOf('function overview()'),app.indexOf('function tasksPage()')),ctx);
assert.doesNotMatch(ctx.settingsPage(),/id="setting-tasks-showEpicsOnOverview"[^>]*checked/);
assert.match(ctx.settingsPage(),/Список задач/);
assert.match(ctx.settingsPage(),/Обзор проекта/);assert.match(ctx.settingsPage(),/Блок «Текущие задачи» на главной странице/);
assert.match(ctx.settingsPage(),/id="setting-tasks-showUpcomingOnOverview"[^>]*checked/);
let html=ctx.overview();assert.doesNotMatch(html,/<article>epic<\/article>/);
for(const id of ['task','bug','legacy'])assert.ok(html.includes(`<article>${id}</article>`));
assert.match(html,/class="count">3<\/span>/);
ctx.state.settings={revision:'two',settings:{tasks:{showEpicsOnOverview:true,showUpcomingOnOverview:false}}};
assert.match(ctx.settingsPage(),/id="setting-tasks-showEpicsOnOverview"[^>]*checked/);
assert.doesNotMatch(ctx.settingsPage(),/id="setting-tasks-showUpcomingOnOverview"[^>]*checked/);
html=ctx.overview();assert.match(html,/<article>epic<\/article>/);
assert.match(html,/<article>bug<\/article>/);assert.doesNotMatch(html,/<article>task<\/article>|<article>legacy<\/article>|<article>closed<\/article>/);assert.match(html,/class="count">2<\/span>/);
ctx.state.settings.settings.tasks.showUpcomingOnOverview=true;
html=ctx.overview();assert.match(html,/<article>task<\/article>/);assert.match(html,/<article>legacy<\/article>/);assert.match(html,/class="count">4<\/span>/);
ctx.state.settings.settings.tasks.showEpicsOnOverview=false;
ctx.state.tasks=ctx.state.tasks.filter(t=>t.type==='epic');
html=ctx.overview();assert.match(html,/class="count">0<\/span>/);
assert.doesNotMatch(html,/Все задачи завершены/);
'''
        result = subprocess.run(['node', '-e', code, str(web)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, (result.stdout or '') + (result.stderr or ''))

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_commit_modes_and_compact_audit(self):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/settings.js'
        code = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const ctx={activeProject:'a',state:{settings:{revision:'r1',settings:{}}},
 document:{addEventListener(){}},sessionStorage:{getItem:()=>null},
 escape:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
 title:()=>'',uiIcon:()=>'<svg/>',taskTableColumns:[]};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
for(const mode of ['stage','task','stage-and-task']){
 ctx.state.settings={revision:mode,settings:{git:{commitOn:mode}}};
 const select=ctx.settingsPage().match(/<select id="setting-git-commitOn"[^>]*>(.*?)<\/select>/)[1];
 assert.equal((select.match(/<option /g)||[]).length,3);
 assert.equal((select.match(/ selected/g)||[]).length,1);
 assert.ok(select.includes('value="'+mode+'" selected'));
}
const draft=ctx.settingsDraft();draft.dirty=true;draft.value.git.commitOn='stage';
ctx.state.settings={revision:'new',settings:{git:{commitOn:'task'}}};
assert.match(ctx.settingsPage(),/value="stage" selected/);
ctx.state.settings.history=Array.from({length:12},(_,i)=>({at:'2026-09-19T10:00:00Z',actor:i===11?'person<unsafe>':'actor-'+i,
 sections:['git','viewer'],before:{private:'DO_NOT_RENDER'},after:{private:'DO_NOT_RENDER'}}));
const page=ctx.settingsPage(),audit=page.match(/<ol class="settings-history">(.*?)<\/ol>/)[1];
assert.equal((audit.match(/<li>/g)||[]).length,10);
assert.ok(audit.indexOf('person&lt;unsafe>')<audit.indexOf('actor-10'));
assert.match(audit,/Git, Просмотр документов/);assert.match(audit,/datetime="2026-09-19T10:00:00Z"/);
assert.doesNotMatch(audit,/<pre>|DO_NOT_RENDER|actor-1<\/span>/);
assert.match(ctx.settingsAuditRow({actor:'local-user',sections:['tasks']}),/Пользователь/);
'''
        result = subprocess.run(['node', '-e', code, str(source)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, (result.stdout or '') + (result.stderr or ''))

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_defaults_drafts_conflicts_and_project_isolation(self):
        web = Path(__file__).resolve().parents[2] / 'tools/project-portal/web'
        code = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const data=new Map(), session=new Map(), handlers={}, requests=[];
const storage=m=>({getItem:k=>m.get(k)||null,setItem:(k,v)=>m.set(k,v),removeItem:k=>m.delete(k)});
const ctx={URL,URLSearchParams,Map,console,activeProject:'a',state:{settings:{revision:'r1',settings:{tasks:{sort:'priority',showCompleted:false}}}},
 localStorage:storage(data),sessionStorage:storage(session),location:{search:'',href:'http://localhost/?project=a'},history:{replaceState(){}},
 document:{addEventListener:(n,f)=>(handlers[n]??=[]).push(f),querySelector:()=>null},window:{confirm:()=>true},
 route:()=>['settings'],render(){},escape:s=>String(s??''),title:()=>'',uiIcon:()=>'<svg/>',taskTableColumns:[['title','Title'],['status','Status']],taskFilter:'all',taskTypeFilter:'all',taskPriorityFilter:'all',taskSearch:'',taskListSort:'created',taskSort:'created',historyTask:'',historyKind:'',diagnosticSearch:'',
 fetch:async(url,opts)=>{requests.push({url,body:JSON.parse(opts.body)});return {ok:false,status:409,json:async()=>({error:'conflict'})};}};
vm.createContext(ctx);
for(const name of ['settings.js','ui-state.js'])vm.runInContext(fs.readFileSync(process.argv[1]+'/'+name,'utf8'),ctx);
(async()=>{
 assert.match(ctx.settingsPage(),/data-settings-action="save"/);assert.match(ctx.settingsPage(),/id="setting-viewer-wrapLines"[^>]*checked/);
 ctx.restoreUiState();assert.equal(ctx.taskFilter,'project');assert.equal(ctx.taskListSort,'priority');
 ctx.taskSearch='hello';ctx.saveUiState(['tasks','search']);
 assert.equal(JSON.parse(data.get('project-hub-ui:v1:a')).tasks.status,undefined);
 ctx.taskFilter='all';ctx.saveUiState(['tasks','status']);ctx.restoreUiState();assert.equal(ctx.taskFilter,'all');
 ctx.state.settings.settings.tasks.sort='updated';ctx.restoreUiState();assert.equal(ctx.taskListSort,'updated');assert.equal(ctx.taskSearch,'hello');
 ctx.taskListSort='title';ctx.saveUiState(['tasks','sort']);ctx.state.settings.settings.tasks.sort='created';ctx.restoreUiState();assert.equal(ctx.taskListSort,'title');
 const draft=ctx.settingsDraft();draft.value.git.autoCommit=true;draft.dirty=true;
 ctx.state.settings.revision='r2';assert.equal(ctx.settingsDraft().expected,'r1');
 await ctx.submitSettings();assert.equal(requests.length,1);assert.equal(requests[0].body.expected,'r1');assert.equal(draft.dirty,true);assert.match(draft.message,/Черновик/);
 ctx.activeProject='b';ctx.state.settings={revision:'b1',settings:{}};assert.equal(ctx.settingsDraft().value.git.autoCommit,false);
 ctx.activeProject='a';assert.equal(ctx.settingsDraft().value.git.autoCommit,true);
 data.set('project-hub-ui:v1:b',JSON.stringify({tasks:{sort:'title'}}));data.set('project-hub-task-columns:b','["status"]');data.set('project-hub-task-columns:a','["status"]');
 ctx.resetProjectListPreferences();assert.equal(data.has('project-hub-task-columns:a'),false);assert.equal(data.has('project-hub-task-columns:b'),true);assert.equal(JSON.parse(data.get('project-hub-ui:v1:b')).tasks.sort,'title');
 ctx.fetch=async(url,opts)=>({ok:true,json:async()=>({revision:'r3',settings:{git:{autoCommit:true}}})});
 ctx.state.settings={revision:'r2',settings:{}};await ctx.submitSettings();assert.equal(draft.dirty,false);assert.equal(draft.expected,'r3');assert.equal(ctx.projectSettings().git.autoCommit,true);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-e', code, str(web)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, (result.stdout or '') + (result.stderr or ''))

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_checkpoint_retry_uses_captured_project_and_revision(self):
        app = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/app.js'
        code = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8'), handlers={}, calls=[];
const ctx={URLSearchParams,activeProject:'one',state:{revision:'task-r7'},escape:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),uiIcon:()=>'<svg/>',
 stageGitCommit:target=>'<code>'+ctx.escape(target.gitCommit.sha)+'</code>',
 document:{addEventListener:(n,f)=>handlers[n]=f},render(){},refresh:async()=>{},showError:m=>ctx.error=m,
 fetch:async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return {ok:false,json:async()=>({error:'stale'})};}};
vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('const checkpointRetries'),source.indexOf('function route()')),ctx);
assert.match(ctx.checkpointStatusContents({id:'t',gitCheckpoint:{status:'error',reason:'failed'}}),/data-checkpoint-retry/);
assert.equal(ctx.checkpointStatusContents({id:'t',gitCheckpoint:{status:'committed'}}),'');
const unpublished=ctx.checkpointStatusContents({id:'t',gitCheckpoint:{status:'committed',sha:'abc',publication:{status:'pending',reason:'journal'}}});
assert.match(unpublished,/Commit сохранён/);assert.match(unpublished,/data-checkpoint-retry/);assert.match(unpublished,/journal/);
assert.doesNotMatch(unpublished,/Не удалось создать commit/);
assert.doesNotMatch(ctx.checkpointStatusContents({id:'t',gitCheckpoint:{status:'pending'}}),/data-checkpoint-retry/);
const created=ctx.checkpointStatusContents({id:'t',gitCheckpoint:{status:'error',reasonCode:'coverage_mismatch',reason:'original <detail>',operationId:'operation',layer:'changeset',gitOutcome:{status:'committed',sha:'abcdef'}}});
assert.match(created,/Commit создан; требуется сверка покрытия/);
assert.match(created,/Commit не подтверждает сохранённый результат работы/);
assert.match(created,/original &lt;detail&gt;/);
assert.match(created,/abcdef/);
(async()=>{await handlers.click({target:{closest:selector=>selector==='[data-checkpoint-retry]'?{dataset:{checkpointRetry:'t',checkpointStage:'s'}}:null}});
assert.equal(calls.length,1);assert.equal(calls[0].url,'/api/v1/checkpoints/retry?project=one');
assert.deepEqual(calls[0].body,{task:'t',stage:'s',expected:'task-r7'});assert.equal(ctx.error,'stale');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-e', code, str(app)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, (result.stdout or '') + (result.stderr or ''))

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_checkpoint_reconciliation_validation_errors_and_success(self):
        app = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/app.js'
        code = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8'), handlers={}, calls=[], dialogs=[];
let release, response, renders=0;
function makeDialog(){
 const events={},field=()=>({value:'',disabled:false,focus(){this.focused=true;}});
 const form={elements:{commits:field(),reason:field()}},feedback={textContent:''},submit={},close={};
 const dialog={form,feedback,submit,closeButton:close,events,open:false,setAttribute(){},
  querySelector:s=>({'form':form,'[role="alert"]':feedback,'[type="submit"]':submit,'[data-close]':close})[s],
  addEventListener:(n,f)=>events[n]=f,showModal(){this.open=true;},
  close(){this.open=false;events.close();},remove(){this.removed=true;}};
 dialogs.push(dialog);return dialog;
}
const ctx={URLSearchParams,activeProject:'one',state:{revision:'r7'},escape:s=>String(s??''),uiIcon:()=>'<svg/>',
 document:{addEventListener:(n,f)=>handlers[n]=f,querySelector:()=>dialogs.find(d=>!d.removed),createElement:makeDialog,body:{append(){}}},
 render(){renders++;},fetch:async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return new Promise(resolve=>release=()=>resolve(response));}};
vm.createContext(ctx);vm.runInContext(source.slice(source.indexOf('const checkpointRetries'),source.indexOf('function route()')),ctx);
const send=d=>d.form.onsubmit({preventDefault(){}}),sha='a'.repeat(40),sha64='B'.repeat(64);
(async()=>{
 for(const status of ['pending','committed','disabled','no_changes'])assert.doesNotMatch(ctx.checkpointStatusContents({id:'t',gitCheckpoint:{status}}),/data-checkpoint-reconcile/);
 assert.match(ctx.checkpointStatusContents({id:'t',gitCheckpoint:{status:'error'}}),/data-checkpoint-reconcile/);
 await handlers.click({target:{closest:s=>s==='[data-checkpoint-reconcile]'?{dataset:{checkpointReconcile:'t',checkpointStage:'s'}}:null}});
 const d=dialogs[0];assert.ok(d.open);assert.match(d.innerHTML,/role="alert"/);
 ctx.state.revision='newer';
 for(const value of ['', 'abc', 'g'.repeat(40), 'a'.repeat(41), Array(21).fill(sha).join('\n')]){
  d.form.elements.commits.value=value;await send(d);assert.match(d.feedback.textContent,/SHA/);
 }
 d.form.elements.commits.value=sha+'\n '+sha64;
 for(const reason of ['  ','x'.repeat(1201)]){d.form.elements.reason.value=reason;await send(d);assert.match(d.feedback.textContent,/1200/);}
 assert.equal(calls.length,0);d.form.elements.reason.value=' Reviewed coverage ';
 response={ok:false,json:async()=>({error:'Coverage missing <file>'})};
 let request=send(d);assert.equal(d.submit.disabled,true);assert.equal(d.closeButton.disabled,true);
 let cancelled=false;d.events.cancel({preventDefault(){cancelled=true;}});assert.ok(cancelled);
 await send(d);assert.equal(calls.length,1);
 release();await request;assert.equal(d.open,true);assert.equal(d.feedback.textContent,'Coverage missing <file>');assert.equal(d.submit.disabled,false);
 assert.deepEqual(calls[0],{url:'/api/v1/checkpoints/retry?project=one',body:{task:'t',stage:'s',expected:'r7',commits:[sha,sha64],reason:'Reviewed coverage'}});
 response={ok:true,json:async()=>({revision:'r9',checkpoint:{status:'no_changes'},tasks:[]})};
 request=send(d);assert.equal(ctx.state.revision,'newer');assert.ok(d.open);release();await request;
 assert.equal(ctx.state.revision,'r9');assert.equal(d.open,false);assert.ok(d.removed);assert.ok(renders>0);
 ctx.openCheckpointReconciliation('t');const taskDialog=dialogs[1];taskDialog.form.elements.commits.value=sha;taskDialog.form.elements.reason.value='Task coverage';
 request=send(taskDialog);ctx.activeProject='two';ctx.state={revision:'other-project'};release();await request;
 assert.equal('stage' in calls[2].body,false);assert.equal(ctx.state.revision,'other-project');
 ctx.openCheckpointReconciliation('t');const changed=dialogs[2];changed.form.elements.commits.value=sha;changed.form.elements.reason.value='Reason';ctx.activeProject='three';
 await send(changed);assert.equal(calls.length,3);assert.match(changed.feedback.textContent,/Проект изменён/);
 changed.closeButton.onclick();assert.ok(changed.removed);
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-e', code, str(app)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, (result.stdout or '') + (result.stderr or ''))

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_architecture_tab_saved_representation_and_model_loading(self):
        web = Path(__file__).resolve().parents[2] / 'tools/project-portal/web'
        code = r"""
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
let modelCalls=0;
const ctx={URL,URLSearchParams,Map,console,activeProject:'p',route:()=>['settings','architecture'],
 state:{settings:{revision:'r1',settings:{architecture:{model:'missing-model',depth:37,representation:'symbols-in-files',agentSummaries:false,descriptionDetail:'detailed'},tasks:{sort:'priority'}}}},
 document:{addEventListener(){}},window:{},localStorage:{getItem:()=>null,setItem(){},removeItem(){}},sessionStorage:{getItem:()=>null},history:{replaceState(){}},
 title:()=>'',uiIcon:()=>'',escape:s=>String(s??''),render:()=>{},taskTableColumns:[],
 fetch:()=>{modelCalls++;return Promise.resolve({ok:true,json:async()=>({models:[{id:'codex',displayName:'Codex'}]})})}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1]+'/settings.js','utf8'),ctx);
let html=ctx.settingsPage();assert.doesNotMatch(html,/data-setting="architecture\.model"|data-setting="architecture\.depth"|setting-architecture-custom-depth|architecture-agent-models|Загрузка каталога моделей|Codex/);assert.match(html,/Description detail|Подробность описания/);assert.match(html,/value="detailed" selected/);assert.match(html,/value="symbols-in-files" selected/);assert.doesNotMatch(html,/<option value="files"/);assert.equal(modelCalls,0);assert.equal(ctx.settingsDraft().value.architecture.model,'missing-model');assert.equal(ctx.settingsDraft().value.architecture.depth,37);
"""
        result = subprocess.run(['node','-e',code,str(web)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,(result.stdout or '')+(result.stderr or ''))

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_architecture_representation_saves_and_legacy_depth_draft_does_not_block(self):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/settings.js'
        code = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const handlers={},writes=[],saved={value:{git:{},tasks:{},viewer:{},architecture:{depth:'all',representation:'symbols'}},expected:'r1',dirty:true,customDepth:true,invalidDepth:true};
const ctx={URL,URLSearchParams,Map,console,activeProject:'p',route:()=>['settings','architecture'],
 state:{settings:{revision:'r1',settings:{architecture:{depth:'all'}}}},
 document:{addEventListener:(n,f)=>handlers[n]=f},window:{confirm:()=>true},sessionStorage:{getItem:()=>JSON.stringify(saved),setItem(){},removeItem(){}},
 title:()=>'',uiIcon:()=>'',escape:s=>String(s??''),render(){},restoreUiState(){},taskTableColumns:[],fetch:async()=>({ok:true,json:async()=>({models:[]})})};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
assert.equal(ctx.settingsDraft().invalidDepth,undefined);
assert.doesNotMatch(ctx.settingsPage(),/setting-architecture-depth|custom-depth/);
const choice={dataset:{setting:'architecture.representation'},value:'symbols-in-files',type:'select-one',closest:()=>({})};
handlers.change({target:choice});assert.equal(ctx.settingsDraft().value.architecture.representation,'symbols-in-files');
(async()=>{
ctx.fetch=async(url,options)=>{writes.push(JSON.parse(options.body));return {ok:true,json:async()=>({revision:'r2',settings:writes[0].patch})};};
await ctx.submitSettings();assert.equal(writes.length,1);assert.equal(writes[0].patch.architecture.representation,'symbols-in-files');
assert.equal(writes[0].patch.architecture.depth,'all','legacy API value is preserved; UI research always supplies one step');
assert.equal(ctx.settingsDraft().dirty,false);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run(['node','-e',code,str(source)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,(result.stdout or '')+(result.stderr or ''))

    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_version_control_panel_is_runtime_and_ignores_stale_project_response(self):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/settings.js'
        code = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
let requests=[],resolvers=[];
const ctx={URL,URLSearchParams,Map,console,activeProject:'one',route:()=>['settings'],state:{settings:{revision:'r1',settings:{git:{autoCommit:true}}}},
 document:{addEventListener(){}},sessionStorage:{getItem:()=>null,setItem(){},removeItem(){}},title(){},uiIcon:()=>'',escape:s=>String(s??''),render(){},taskTableColumns:[],
 fetch:url=>{requests.push(url);return new Promise(resolve=>resolvers.push(resolve));}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
assert.match(ctx.settingsPage(),/version-control-settings/);assert.match(ctx.settingsPage(),/setting-git-autoCommit[^>]*disabled/);
ctx.HubVersionControlUI.afterRender();ctx.activeProject='two';ctx.HubVersionControlUI.afterRender();assert.equal(requests.length,2);
resolvers[0]({ok:true,json:async()=>({provider:'git',status:'ready',available:true,workspaceRoot:'one',repositoryRoot:'one',client:{available:true},operations:[]})});
resolvers[1]({ok:true,json:async()=>({provider:null,status:'no_repository',available:false,workspaceRoot:null,repositoryRoot:null,client:{available:true},operations:[]})});
setTimeout(()=>{assert.match(ctx.settingsPage(),/data-version-control-status="no_repository"/);assert.match(ctx.settingsPage(),/setting-git-autoCommit[^>]*checked[^>]*disabled/);},0);
'''
        result = subprocess.run(['node','-e',code,str(source)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,(result.stdout or '')+(result.stderr or ''))
