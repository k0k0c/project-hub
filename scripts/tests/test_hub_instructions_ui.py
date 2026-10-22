"""Legacy instruction registry compatibility and global settings routes in an isolated VM."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class HubInstructionsUiTest(unittest.TestCase):
    def run_js(self, checks):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/settings.js'
        setup = r'''
const vm=require('node:vm'), fs=require('node:fs'), assert=require('node:assert/strict');
const saved=new Map(), handlers={}, requests=[];
const envelope=(revision='r1',initialized=true)=>({schemaVersion:1,revision,initialized,restoreAllowed:true,nativeDiscovery:true,
 package:{name:'Project Hub',version:'1'},digest:'abc',path:'user/skill/SKILL.md',scope:'codex-user',
 rules:[{id:'core',title:'Core',kind:'mandatory',source:'plugin',default:'<core>',effective:'<core>',editable:false},
 {id:'userInstructions',title:'User',kind:'editable',source:'user/skill/SKILL.md',default:'Default',effective:'User text',editable:true,maxLength:24000}],
 architecture:[{id:'local',title:'Local',description:'Local files'}],skills:[{id:'hub',title:'Hub',description:'Native skill'}],
 tools:[{name:'hub_one',description:'One',group:'MCP'},{name:'hub_two',description:'Two',group:'MCP'}],
 scripts:[{name:'script.py',description:'Helper',runtime:'python',settings:[{name:'HOME',description:'Path'}]}],
 hooks:[{event:'PreToolUse',description:'Observation',requiredFor:['writes'],command:'echo <unsafe>',commandWindows:'echo "windows"',timeout:20,matcher:'*',state:'declared',observed:null}],
 extensions:[{id:'proposal',title:'Proposed',description:'Future',status:'proposed'}],history:[],delivery:{description:'Native skill'}});
const status={textContent:'',focus(){}}, save={disabled:true}, cancel={disabled:true};
let renders=0, currentRoute=['settings'];
function context(){
 const ctx={URLSearchParams,console,Intl,Date,activeProject:'a',state:{settings:{revision:'general-r1',settings:{}}},
  route:()=>currentRoute,render(){renders++;ctx.settingsPage();},
  title:()=>'',uiIcon:()=>'',taskTableColumns:[],
  escape:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;').replaceAll("'",'&#39;'),
  sessionStorage:{getItem:k=>saved.get(k)||null,setItem:(k,v)=>saved.set(k,v),removeItem:k=>saved.delete(k)},
  document:{addEventListener:(name,handler)=>(handlers[name]??=[]).push(handler),getElementById:()=>status,
    querySelector:s=>s.includes('"save"')?save:cancel},window:{confirm:()=>true},navigator:{},
  fetch:async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>envelope()};}};
 vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);return ctx;
}
let ctx=context();
const tick=async()=>{for(let i=0;i<10;i++)await Promise.resolve();};
const edit=(value)=>{const input={dataset:{hubInstructionBlock:'userInstructions'},value,closest:()=>({})};
 for(const fn of handlers.input||[])fn({target:input});};
(async()=>{
'''
        code = setup + checks + r'''
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-e', code, str(source)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, (result.stdout or '') + (result.stderr or ''))

    def test_lazy_inventory_escaping_and_uninitialized_read(self):
        self.run_js(r'''
assert.doesNotMatch(ctx.settingsPage(),/href="#settings\/instructions"/);
assert.equal(requests.length,0,'general settings must not fetch instructions');
	currentRoute=['settings','instructions'];
ctx.hubInstructionsPage();ctx.hubInstructionsPage();await tick();
assert.equal(requests.length,1,'one lazy request including render after completion');
const html=ctx.hubInstructionsPage();
assert.match(html,/Правила работы/);assert.match(html,/&lt;core&gt;/);
currentRoute=['settings','instructions','personal'];let personal=ctx.hubInstructionsPage();
assert.match(personal,/Ваши инструкции/);assert.match(personal,/во всех проектах, добавленных в Project Hub/);assert.match(personal,/Редактировать мои инструкции/);
assert.doesNotMatch(personal,/maxlength="24000"/);
const editButton={closest:selector=>selector.includes('hub-instructions-action')?{dataset:{hubInstructionsAction:'edit'}}:null};
for(const fn of handlers.click||[])await fn({target:editButton});
assert.match(ctx.hubInstructionsPage(),/id="hub-personal-editor"[^>]*maxlength="24000"/);
for(const fn of handlers.click||[])await fn({target:{closest:selector=>selector.includes('hub-instructions-action')?{dataset:{hubInstructionsAction:'read'}}:null}});
assert.doesNotMatch(ctx.hubInstructionsPage(),/id="hub-personal-editor"/);
ctx.window.marked={parse:source=>'<p>'+source+'</p><script>bad()</script>'};
ctx.window.DOMPurify={sanitize:html=>html.replace('<script>bad()</script>','')};
ctx.window.marked.parse=()=>'<h1>Title</h1><h2>Section</h2>';
assert.match(ctx.hubInstructionMarkdown('safe'),/<h4>Title<\/h4><h5>Section<\/h5>/);
assert.match(ctx.hubInstructionMarkdown('safe'),/class="hub-markdown"/);assert.doesNotMatch(ctx.hubInstructionMarkdown('safe'),/<script>/);
delete ctx.window.marked;delete ctx.window.DOMPurify;assert.match(ctx.hubInstructionMarkdown('<unsafe>'),/<pre>&lt;unsafe&gt;<\/pre>/);
for (const [topic, phrase] of [['architecture','Архитектура Hub'],['capabilities','Возможности агента и MCP'],['scripts','Скрипты'],['hooks','Обработчики событий'],['extensions','Расширения'],['history','История изменений']]) {
 currentRoute=['settings','instructions',topic];const topicHtml=ctx.hubInstructionsPage();assert.match(topicHtml,new RegExp(phrase));
}
currentRoute=['settings','instructions','personal'];
ctx.fetch=async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>{const data=envelope('missing-v1',false);
 data.rules[1].effective='</textarea><script>alert(1)</script>';return data;}};};
await ctx.loadHubInstructions();const uninitialized=ctx.hubInstructionsPage();
assert.match(uninitialized,/data-hub-instructions-action="save" disabled/);
assert.match(uninitialized,/data-hub-instructions-action="reset-userInstructions" >Создать мои инструкции/);
assert.doesNotMatch(uninitialized,/data-hub-instructions-action="reset-all"/);
assert.match(uninitialized,/&lt;\/textarea&gt;&lt;script&gt;/);
assert.doesNotMatch(uninitialized,/<script>|<textarea[^>]+data-hub-instruction-block[^>]*>.*<\/textarea><script>/);
const before=requests.length;await ctx.submitHubInstructions();assert.equal(requests.length,before);
ctx.fetch=async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>envelope('initialized-v1')};};
await ctx.submitHubInstructions('userInstructions');
assert.deepEqual(JSON.parse(requests.at(-1).options.body),{expected:'missing-v1',reset:'userInstructions'});
assert.equal(ctx.hubInstructionEntry().envelope.initialized,true);
edit('New instructions');assert.equal(save.disabled,false);
ctx.fetch=async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>{
 const data=envelope('missing-v1',false);data.restoreAllowed=false;data.nativeDiscovery=false;data.scope='unconfigured';return data;
}};};
await ctx.loadHubInstructions();const unconfigured=ctx.hubInstructionsPage();
assert.match(unconfigured,/data-hub-instructions-action="reset-userInstructions" disabled/);
assert.doesNotMatch(unconfigured,/data-hub-instructions-action="reset-all"/);
assert.match(unconfigured,/пользовательскую инструкцию прежнего подключения через плагин/);
assert.match(unconfigured,/<section class="card" id="hub-native-workflow"/);
assert.match(unconfigured,/<details class="card" data-key="hub-legacy-codex">/);
assert.ok(unconfigured.indexOf('hub-native-workflow')<unconfigured.indexOf('hub-legacy-codex'));
assert.doesNotMatch(unconfigured,/<details[^>]*data-key="hub-legacy-codex"[^>]*\bopen\b/);
assert.doesNotMatch(unconfigured,/Область: USER Codex|Пользовательский skill Codex · все проекты пользователя/);
const unconfiguredRequests=requests.length;await ctx.submitHubInstructions('all');assert.equal(requests.length,unconfiguredRequests);
await ctx.submitHubInstructions('userInstructions');assert.equal(requests.length,unconfiguredRequests);
''')

    def test_global_rules_replace_legacy_panels_and_keep_original_text(self):
        self.run_js(r'''
currentRoute=['settings','agents','rules'];
ctx.HubConnectionsUI={page:()=>'<section data-global-connections></section>'};
ctx.HubAgentProvidersUI={card:()=>'<section data-model-providers></section>'};
let html=ctx.settingsPage();
assert.match(html,/id="hub-modern-instructions"/);
assert.doesNotMatch(html,/hub-legacy-codex|href="#settings\/instructions"/);
assert.equal(requests.length,0,'global rules load after the panel mounts');
const original='Original workflow <keep this text>';
ctx.document.querySelectorAll=()=>[];
ctx.document.getElementById=id=>id==='hub-modern-instructions'?{}:null;
ctx.fetch=async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>({workflow:original,text:'Existing custom rules',revision:'global-r1'})};};
ctx.window.HubSettingsUI.afterRender();await tick();
assert.equal(requests.length,2);
assert.ok(requests.every(item=>!item.url.includes('/api/v1/instructions')));
html=ctx.settingsPage();assert.match(html,/<pre>Original workflow &lt;keep this text&gt;<\/pre>/);
assert.match(html,/Existing custom rules/);
currentRoute=['settings','instructions','personal'];
html=ctx.settingsPage();assert.match(html,/hub-modern-instructions/);assert.doesNotMatch(html,/data-global-connections|hub-legacy-codex/);
ctx.state=null;ctx.activeProject='';
html=ctx.settingsPage();assert.match(html,/hub-modern-instructions/);assert.doesNotMatch(html,/data-global-connections|data-model-providers/);
assert.doesNotMatch(html,/data-instructions-project/);
''')

    def test_legacy_block_link_uses_localized_heading_and_preserves_instruction(self):
        self.run_js(r'''
vm.runInContext(fs.readFileSync(require('node:path').join(require('node:path').dirname(process.argv[1]),'locale-catalog.js'),'utf8'),ctx);
let language='en';ctx.HubI18n={t(key,values={}){const message=ctx.HubLocaleCatalog[key]?.[language];return message?.replace(/\{([^}]+)\}/g,(_,name)=>String(values[name]??''));}};
const data=envelope();data.rules[0].title='Встроенные инструкции агента';data.rules[0].effective='Авторский текст <без перевода>';
ctx.fetch=async()=>({ok:true,json:async()=>data});currentRoute=['settings','instructions','rules'];await ctx.loadHubInstructions();
let html=ctx.hubInstructionsPage();assert.match(html,/aria-label="Link to block Full built-in instruction text"/);
assert.doesNotMatch(html,/Link to block Встроенные/);assert.match(html,/Авторский текст &lt;без перевода&gt;/);
language='ru';html=ctx.hubInstructionsPage();assert.match(html,/aria-label="Ссылка на блок Полный текст встроенной инструкции"/);
assert.equal(ctx.hubInstructionEntry().envelope.rules[0].effective,data.rules[0].effective);
''')

    def test_conflicts_preserve_draft_on_reload_and_reset_uses_latest_defaults(self):
        self.run_js(r'''
	currentRoute=['settings','instructions','personal'];await ctx.loadHubInstructions();
edit('Custom </textarea>');assert.equal(save.disabled,false);
const draft=ctx.hubInstructionEntry();assert.equal(draft.patch.userInstructions,'Custom </textarea>');
ctx.fetch=async(url,options)=>{requests.push({url,options});return {ok:false,status:409,json:async()=>({error:'conflict'})};};
await ctx.submitHubInstructions();assert.equal(draft.expected,'r1');assert.match(draft.message,/Черновик сохранён/);
assert.equal(JSON.parse(requests.at(-1).options.body).patch.userInstructions,'Custom </textarea>');
ctx.fetch=async()=>({ok:true,json:async()=>envelope('r2')});await ctx.loadHubInstructions();
assert.equal(draft.expected,'r1');assert.equal(draft.patch.userInstructions,'Custom </textarea>');
assert.match(ctx.hubInstructionsPage(),/<pre>Custom &lt;\/textarea&gt;<\/pre>/);
for(const key of Object.keys(handlers))delete handlers[key];ctx=context();
await ctx.loadHubInstructions();assert.equal(ctx.hubInstructionEntry().patch.userInstructions,'Custom </textarea>');
assert.equal(ctx.hubInstructionEntry().expected,'r1','session reload must retain conflict base');
ctx.fetch=async(url,options)=>{requests.push({url,options});const data=envelope('r3');data.rules[1].default='New default';data.rules[1].effective='Custom </textarea>';data.rules[1].defaultChanged=true;return {ok:true,json:async()=>data};};
await ctx.loadHubInstructions();assert.match(ctx.hubInstructionsPage(),/Ваши инструкции сохранены/);
const cancelTarget={closest:selector=>selector.includes('copy')?null:{dataset:{hubInstructionsAction:'cancel'}}};
for(const fn of handlers.click)await fn({target:cancelTarget});
assert.equal(Object.keys(ctx.hubInstructionEntry().patch).length,0);assert.equal(ctx.hubInstructionEntry().expected,'r3');
ctx.fetch=async(url,options)=>{requests.push({url,options});const data=envelope('r4');data.rules[1].default='New default';data.rules[1].effective='New default';return {ok:true,json:async()=>data};};
await ctx.submitHubInstructions('userInstructions');
assert.deepEqual(JSON.parse(requests.at(-1).options.body),{expected:'r3',reset:'userInstructions'});
assert.match(ctx.hubInstructionsPage(),/<pre>New default<\/pre>/);assert.equal(saved.size,0);
edit('x'.repeat(24001));const before=requests.length;await ctx.submitHubInstructions();assert.equal(requests.length,before);assert.equal(save.disabled,true);
''')

    def test_stale_project_response_general_drafts_and_clipboard_fallback(self):
        self.run_js(r'''
const general=ctx.settingsDraft();general.dirty=true;general.value.git.autoCommit=true;
currentRoute=['settings','instructions'];let resolve;
ctx.fetch=()=>new Promise(done=>{resolve=done});const pending=ctx.loadHubInstructions();
ctx.activeProject='b';resolve({ok:true,json:async()=>envelope('a1')});await pending;
assert.equal(renders,0,'old project response must not rerender new project');
assert.equal(ctx.hubInstructionEntry().envelope,null);
ctx.fetch=async()=>({ok:true,json:async()=>envelope('b1')});await ctx.loadHubInstructions();
assert.equal(ctx.hubInstructionEntry().expected,'b1');
ctx.activeProject='a';currentRoute=['settings'];assert.equal(ctx.settingsDraft(),general);assert.equal(ctx.settingsDraft().value.git.autoCommit,true);
let focused=0,selected=0;const field={value:'echo <unsafe>',focus(){focused++;},select(){selected++;}};
const button={closest:()=>({querySelector:()=>field}),textContent:''};
const event={target:{closest:selector=>selector.includes('copy')?button:null}};
for(const fn of handlers.click)await fn(event);
assert.equal(focused,1);assert.equal(selected,1);assert.match(button.textContent,/вручную/);
let copied;ctx.navigator.clipboard={writeText:async value=>{copied=value;}};
for(const fn of handlers.click)await fn(event);
assert.equal(copied,'echo <unsafe>');assert.equal(selected,1);assert.equal(button.textContent,'Скопировано');
''')

    def test_hook_recovery_json_copy_uses_exact_configuration_and_safe_fallback(self):
        self.run_js(r'''
currentRoute=['settings','instructions','hooks'];
const data=envelope();
data.hookRecovery={hooks:{SessionStart:[{hooks:[{type:'command',
 command:'"C:\\Program Files\\Python\\python.exe" "C:\\Hub\\client_entry.py" hook',timeout:20}]}],
 PreToolUse:[{matcher:'apply_patch',hooks:[{type:'command',command:'echo </textarea><script>unsafe</script>',timeout:10}]}]}};
ctx.fetch=async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>data};};
await ctx.loadHubInstructions();
const html=ctx.hubInstructionsPage(),recovery=html.match(/<details class="hub-hook-recovery">(.*?)<\/details>/s)[1];
assert.match(recovery,/Скопировать JSON hooks/);
assert.match(recovery,/Импорт JSON и подтверждение доверия к hooks выполняет пользователь в Codex/);
assert.match(recovery,/Портал не изменяет существующие или чужие hooks/);
assert.match(recovery,/&lt;\/textarea&gt;&lt;script&gt;/);assert.doesNotMatch(recovery,/<script>/);
assert.ok((html.match(/data-hub-copy-command/g)||[]).length>=3,'existing individual command buttons survive');
const escaped=recovery.match(/<textarea[^>]*>(.*?)<\/textarea>/s)[1];
const value=escaped.replaceAll('&quot;','"').replaceAll('&#39;',"'").replaceAll('&lt;','<').replaceAll('&gt;','>').replaceAll('&amp;','&');
assert.deepEqual(JSON.parse(value),data.hookRecovery);
let focused=0,selected=0,copied;
const field={value,focus(){focused++;},select(){selected++;}};
const button={closest:()=>({querySelector:()=>field}),textContent:'Скопировать JSON hooks'};
const event={target:{closest:selector=>selector.includes('copy')?button:null}};
const before=requests.length;
ctx.navigator.clipboard={writeText:async text=>{copied=text;}};
for(const fn of handlers.click)await fn(event);
assert.equal(copied,JSON.stringify(data.hookRecovery,null,2));assert.equal(button.textContent,'Скопировано');
ctx.navigator.clipboard.writeText=async()=>{throw Error('Clipboard permission unavailable');};
for(const fn of handlers.click)await fn(event);
assert.equal(focused,1);assert.equal(selected,1);assert.match(button.textContent,/вручную/);
assert.equal(requests.length,before,'copying JSON performs no server or configuration writes');
delete data.hookRecovery;assert.doesNotMatch(ctx.hubInstructionsPage(),/data-hub-copy-hooks/);
''')

    def test_optional_notice_hook_is_separate_manual_copy_without_writes(self):
        self.run_js(r'''
	currentRoute=['settings','instructions','hooks'];
const data=envelope();
data.hookRecovery={hooks:{SessionStart:[{hooks:[{type:'command',command:'required startup',timeout:20}]}]}};
data.optionalHookRecovery={description:'One bounded wait <=45s per user turn. Codex delivers on the next safe model request, not an idle wakeup.',
 hooks:{UserPromptSubmit:[{hooks:[{type:'command',command:'python "C:/Hub/client_entry.py" notice wait',
 commandWindows:'"C:\\Python\\python.exe" "C:\\Hub\\client_entry.py" notice wait',timeout:50,async:true}]}]}};
ctx.fetch=async(url,options)=>{requests.push({url,options});return {ok:true,json:async()=>data};};
await ctx.loadHubInstructions();
const html=ctx.hubInstructionsPage();
const mandatory=html.match(/<details class="hub-hook-recovery">(.*?)<\/details>/s)[1];
const optional=html.match(/<article class="hub-instruction-card hub-hook-optional">(.*?)<\/article>/s)[1];
assert.match(optional,/Дополнительное ожидание уведомлений/);
assert.match(optional,/Портал не включает его автоматически/);
assert.match(optional,/не заменяя всю конфигурацию/);
assert.match(optional,/Обработчик не возобновляет бездействующий чат/);
assert.match(optional,/справка не проверяет разрешение на запуск/);
assert.match(optional,/wait &lt;=45s/);
assert.doesNotMatch(mandatory,/UserPromptSubmit|notice wait/);
const escaped=optional.match(/<textarea[^>]*>(.*?)<\/textarea>/s)[1];
const value=escaped.replaceAll('&quot;','"').replaceAll('&#39;',"'").replaceAll('&lt;','<').replaceAll('&gt;','>').replaceAll('&amp;','&');
assert.deepEqual(JSON.parse(value),{hooks:data.optionalHookRecovery.hooks});
assert.equal(JSON.parse(value).hooks.UserPromptSubmit[0].hooks[0].async,true);
let copied;const field={value};
const button={closest:()=>({querySelector:()=>field}),textContent:''};
const event={target:{closest:selector=>selector.includes('copy')?button:null}};
ctx.navigator.clipboard={writeText:async text=>{copied=text;}};
const before=requests.length;for(const fn of handlers.click)await fn(event);
assert.deepEqual(JSON.parse(copied),{hooks:data.optionalHookRecovery.hooks});
assert.equal(requests.length,before,'optional hook copy never installs or changes configuration');
delete data.optionalHookRecovery;assert.doesNotMatch(ctx.hubInstructionsPage(),/data-hub-copy-optional-hooks/);
''')

    def test_reading_has_one_copy_and_history_explains_its_scope(self):
        self.run_js(r'''
currentRoute=['settings','instructions','rules'];
await ctx.loadHubInstructions();
let html=ctx.hubInstructionsPage();
assert.equal((html.match(/&lt;core&gt;/g)||[]).length,1);
assert.doesNotMatch(html,/Источник и полный оригинал|Сведения о комплекте|Digest:/);
currentRoute=['settings','instructions','personal'];html=ctx.hubInstructionsPage();
assert.equal((html.match(/User text/g)||[]).length,1);
assert.match(html,/Начальный шаблон для восстановления/);
const data=ctx.hubInstructionEntry().envelope;data.rules[1].effective='Default';
assert.doesNotMatch(ctx.hubInstructionsPage(),/Начальный шаблон для восстановления/);
currentRoute=['settings','instructions','history'];
assert.match(ctx.hubInstructionsPage(),/Вы ещё не сохраняли изменения/);
data.history=[{at:'2026-10-07T10:00:00Z',actor:'local-user',blocks:['userInstructions']}];
html=ctx.hubInstructionsPage();assert.match(html,/Изменены ваши инструкции/);assert.match(html,/Пользователь/);
assert.match(html,/Обновления плагина и изменения задач сюда не входят/);
assert.doesNotMatch(html,/userInstructions/);
''')

    def test_native_local_scope_does_not_claim_user_scope_or_runtime_discovery(self):
        self.run_js(r'''
	currentRoute=['settings','instructions','personal'];
const data=envelope();data.scope='native-local';data.path='C:/Repo/.agents/skills/project-hub-user/SKILL.md';
ctx.fetch=async()=>({ok:true,json:async()=>data});
await ctx.loadHubInstructions();const local=ctx.hubInstructionsPage();
assert.match(local,/К каким чатам они применяются, зависит от расположения файла в Codex/);
assert.match(local,/не гарантирует чтение каждым новым чатом/);
assert.doesNotMatch(local,/USER|все проекты пользователя/);
data.scope='codex-user';await ctx.loadHubInstructions();const user=ctx.hubInstructionsPage();
assert.match(user,/не принадлежат отдельному проекту/);assert.match(user,/во всех проектах, добавленных в Project Hub/);
assert.match(user,/не гарантирует чтение каждым новым чатом/);
''')


if __name__ == '__main__':
    unittest.main()
