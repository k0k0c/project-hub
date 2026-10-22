"""Runtime status UI uses the installed/source contract without navigation."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class RuntimeUiTest(unittest.TestCase):
    def run_js(self, checks):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/runtime-status.js'
        setup = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
let requests=[], intervals=[], cardNode=null, badgeNode={textContent:'',dataset:{}};
const document={getElementById:id=>id==='hub-runtime-settings'?cardNode:id==='hub-server-indicator'?badgeNode:null,addEventListener:(kind,fn)=>{document.handler=fn}};
const ctx={document,console,setInterval:(fn)=>{intervals.push(fn);return fn},fetch:async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>ctx.next}} ,HubI18n:{locale:'ru'}};
ctx.globalThis=ctx;ctx.window=ctx;ctx.HubLiveUI={patch:(node,html)=>{node.html=html}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const tick=async()=>{for(let i=0;i<8;i++)await Promise.resolve()};
(async()=>{
'''
        code = setup + checks + r'''
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run(['node','-e',code,str(source)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,(result.stdout or '')+(result.stderr or ''))

    def test_empty_project_status_is_read_only_in_both_languages(self):
        self.run_js(r'''
ctx.next={mode:'installed',running:true,port:9012,url:'http://127.0.0.1:9012',programPath:'C:/Example/app',dataHome:'C:/ExampleData',tray:{supported:true,required:true,visible:true}};
assert.match(ctx.HubRuntimeUI.card(),/Сервер Project Hub/);
cardNode={html:'',querySelector:()=>null};ctx.HubRuntimeUI.afterRender();await tick();assert.equal(requests.length,1);
assert.match(cardNode.html,/9012/);assert.doesNotMatch(cardNode.html,/checkbox|hub-runtime-tray-toggle/);
assert.equal(badgeNode.dataset.runtimeState,'running');assert.equal(ctx.HubRuntimeUI.current().port,9012);
ctx.HubI18n.locale='en';assert.match(ctx.HubRuntimeUI.card(),/Project Hub server/);assert.match(ctx.HubRuntimeUI.card(),/The icon is shown while the server runs/);
assert.equal(document.handler,undefined);assert.ok(requests.every(r=>!r.options?.method || r.options.method==='GET'));
''')

    def test_development_mode_is_marked_without_navigation(self):
        self.run_js(r'''
ctx.next={mode:'development',running:true,port:8871,url:'http://127.0.0.1:8871',programPath:'/example/source',dataHome:'/example/copy',supervised:false,tray:{supported:true,required:true,visible:false}};
cardNode={html:'',querySelector:()=>null};ctx.HubRuntimeUI.afterRender();await tick();assert.match(cardNode.html,/Тестовый сервер/);assert.match(cardNode.html,/Прямой тестовый запуск/);assert.equal(requests.length,1);
''')

    def test_actual_data_backup_and_program_paths_are_openable(self):
        self.run_js(r'''
ctx.HubLocalFiles={pathLink:(path,kind)=>`<button data-local-open="${kind}" data-path="${path}">${path}</button>`};
ctx.next={mode:'source',running:true,port:9020,url:'http://127.0.0.1:9020',programPath:'C:/Example program',dataHome:'D:/Current data',backupHome:'D:/Data backups',tray:{visible:true}};
cardNode={html:'',querySelector:()=>null};ctx.HubRuntimeUI.afterRender();await tick();
assert.match(cardNode.html,/data-local-open="data" data-path="D:\/Current data"/);
assert.match(cardNode.html,/data-local-open="backups" data-path="D:\/Data backups"/);
assert.match(cardNode.html,/data-local-open="program" data-path="C:\/Example program"/);
assert.doesNotMatch(cardNode.html,/<input/);
''')

    def test_diagnostics_are_read_only_localized_and_escape_incident(self):
        self.run_js(r'''
ctx.next={mode:'source',running:true,port:9020,diagnostics:{enabled:true,directory:'C:/Example/logs',incident:{time:'2026-01-01T12:00:00Z',component:'server',errorMessage:'<script>boom</script>',exitCode:7,operationId:'fixture',phase:'comparing',traceback:'<img src=x onerror=alert(1)>'}},tray:{visible:true}};
cardNode={html:''};ctx.HubRuntimeUI.afterRender();await tick();
assert.match(cardNode.html,/Диагностика сервера/);assert.match(cardNode.html,/Код выхода/);
assert.match(cardNode.html,/Сравнение данных/);
assert.match(cardNode.html,/&lt;script&gt;/);assert.doesNotMatch(cardNode.html,/<script>|<img /);
assert.match(cardNode.html,/href="\/api\/runtime\/diagnostics"/);
ctx.HubI18n.locale='en';assert.match(ctx.HubRuntimeUI.card(),/Server diagnostics/);assert.match(ctx.HubRuntimeUI.card(),/Exit code/);
assert.match(ctx.HubRuntimeUI.card(),/Data comparison/);
assert.ok(requests.every(r=>!r.options?.method || r.options.method==='GET'));
''')

    def test_connection_failure_does_not_keep_claiming_the_server_is_running(self):
        self.run_js(r'''
ctx.next={mode:'source',running:true,port:9020,diagnostics:{enabled:true,directory:'C:/Example/logs'},tray:{visible:true}};
cardNode={html:''};ctx.HubRuntimeUI.afterRender();await tick();
ctx.fetch=async()=>{throw Error('network failure')};await ctx.HubRuntimeUI.refresh();
assert.equal(badgeNode.dataset.runtimeState,'unknown');
assert.match(cardNode.html,/Не удалось получить состояние сервера/);
assert.doesNotMatch(cardNode.html,/>Работает</);
assert.match(cardNode.html,/C:\/Example\/logs/);
''')
