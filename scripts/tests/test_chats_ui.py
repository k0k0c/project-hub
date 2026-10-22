"""Focused browser contracts for the chats history and task tab."""
from pathlib import Path
import shutil
import subprocess
import unittest

WEB = Path(__file__).resolve().parents[2] / "tools/project-portal/web/app.js"

HARNESS = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(process.argv[1],'utf8');
const start=source.indexOf('function diagnosticAge('), end=source.indexOf('function archiveView(');
const ctx={URLSearchParams,Set,Promise,Date,JSON,Math,console,activeProject:'owner',taskTab:'chats',diagnosticSearch:'',
 state:{tasks:[]},location:{hash:'#coordination'},route:()=>['coordination'],render(){},
 escape:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;'),
 date:s=>s,taskLink:(t,stage)=>'#tasks/'+encodeURIComponent(t.id)+(stage?'/'+encodeURIComponent(stage):''),uiIcon:()=>'<svg/>',agentName:s=>s.title||s.id,codexSessionLink:(resource,label)=>resource?.openUri?`<a data-session="${resource.nativeId}" href="${resource.openUri}">${label}</a>`:`<strong>${label}</strong>`,
 title:()=>'',clock:()=>'',connected:true,replacePreservingScroll(){},get:async()=>({sessions:[],next:null,warnings:[],discovery:{available:true}})};
vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
const namesStart=source.indexOf('function chatText('),namesEnd=source.indexOf('function gitCommitLine(',namesStart);
vm.runInContext(source.slice(namesStart,namesEnd),ctx);
const coordStart=source.indexOf('function coordinationPage('),coordEnd=source.indexOf('async function loadDiagnosticArchive(',coordStart);
vm.runInContext(source.slice(coordStart,coordEnd),ctx);
ctx.__setChats=(key,data)=>vm.runInContext(`chatsViewKey=${JSON.stringify(key)};chatsData=${JSON.stringify(data)};`,ctx);
ctx.__setTab=value=>vm.runInContext(`taskTab=${JSON.stringify(value)};`,ctx);
ctx.__chatState=()=>vm.runInContext('chatsData',ctx);
'''


@unittest.skipUnless(shutil.which("node"), "Node is required")
class ChatsUiTest(unittest.TestCase):
    def run_node(self, code):
        result = subprocess.run(["node", "-e", HARNESS + "\n(async()=>{" + code +
                                "})().catch(e=>{console.error(e);process.exitCode=1});", str(WEB)],
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_parent_link_and_task_links_preserve_chat_structure(self):
        self.run_node(r'''
const parent={id:'parent',title:'Parent',openSession:'parent',nativeChat:{client:'codex',nativeId:'11111111-1111-4111-8111-111111111111',openUri:'codex://threads/11111111-1111-4111-8111-111111111111'}}, child={id:'child',parentSession:'parent',title:'Child',taskLinks:[{id:'a',title:'Alpha'},{id:'b',title:'Beta'}],stageLinks:[{task:'a',stage:'review',title:'Review'}]};
assert.match(ctx.chatCodexLink(child,[parent,child]),/data-session="11111111-1111-4111-8111-111111111111"/);assert.match(ctx.chatCodexLink(child,[parent,child]),/Open parent chat in Codex|Открыть родительский чат в Codex/);
const html=ctx.diagnosticChat(child,[parent,child]);assert.match(html,/Alpha/);assert.match(html,/Beta/);assert.match(html,/Открыть родительский чат в Codex/);
assert.match(html,/#tasks\/a\/review/);
''')

    def test_chat_details_group_task_stages_and_show_last_observation(self):
        self.run_node(r'''
const row={id:'root',title:'Planning conversation',seen:1750000000,lastActivityAt:1760000000,taskLinks:[{id:'task-a',title:'Example task'}],stageLinks:[{task:'task-a',stage:'review',title:'Review'}],nativeChat:{client:'claude-code',openUri:'https://example.test/chat'}};
const html=ctx.diagnosticChat(row,[row]);
assert.match(html,/Planning conversation/);assert.match(html,/Claude Code/);assert.match(html,/<time datetime=/);
assert.match(html,new RegExp('datetime=\"'+new Date(1760000000*1000).toISOString()+'\"'));
assert.equal((html.match(/href="#tasks\/task-a"/g)||[]).length,1);assert.match(html,/#tasks\/task-a\/review/);
assert.match(html,/not current execution|Текущее выполнение не подтверждено/);
''')

    def test_chat_open_action_explains_missing_link_and_never_uses_actor_id(self):
        self.run_node(r'''
const row={id:'11111111-1111-4111-8111-111111111111',title:'Useful title'};
const html=ctx.diagnosticChat(row,[row]);
assert.doesNotMatch(html,/href=|codex:\/\//);assert.match(html,/did not provide a link|не предоставило ссылку/);
''')

    def test_unreported_sessions_are_not_presented_as_named_chats(self):
        self.run_node(r'''
const row={id:'actor',chatIdentity:'unreported',title:'Internal actor id',agentPath:'agents/worker'};
assert.equal(ctx.agentName(row),'Сеанс без данных чата');
const html=ctx.diagnosticChat(row,[row]);
assert.match(html,/Сеанс без данных чата/);assert.match(html,/Приложение ещё не сообщило название или адрес/);
''')

    def test_coordination_uses_one_searchable_paginated_chat_list(self):
        self.run_node(r'''
ctx.archiveView=()=>'';ctx.state.coordination={available:true,discovery:{available:true}};
ctx.__setChats('["owner",null,""]',{sessions:[{id:'root',title:'Planning conversation'}],next:25,warnings:[],discovery:{available:true}});
const html=ctx.coordinationPage();
assert.equal((html.match(/class="diagnostic-section chat-history"/g)||[]).length,1);
assert.match(html,/id="diagnostic-search"/);assert.match(html,/data-chats-more/);
assert.doesNotMatch(html,/Recent chats|Full chat history|Недавние чаты|Вся история чатов/);
assert.equal((html.match(/data-key="chat-root"/g)||[]).length,1);
''')

    def test_unknown_actor_uuid_never_creates_a_native_link(self):
        self.run_node(r'''
const row={id:'11111111-1111-4111-8111-111111111111',title:'Reported actor'};
assert.doesNotMatch(ctx.chatCodexLink(row,[row]),/href=|codex:\/\//);
''')

    def test_explicit_empty_task_links_do_not_use_stale_session_task(self):
        self.run_node(r'''
ctx.state.tasks=[{id:'stale',title:'Unrelated task'}];
const html=ctx.diagnosticChat({id:'root',title:'Chat',task:'stale',taskLinks:[]},[]);
assert.doesNotMatch(html,/Unrelated task|href="#tasks\/stale"/);
''')

    def test_native_chat_helper_rejects_private_credentials_in_source_links(self):
        code = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const ctx={URL,URLSearchParams,window:{}};vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const helper=ctx.window.HubNativeChats;
const source='https://example.test/chat?id=resource#messages';
assert.equal(helper.uri({openUri:source}),source);
for(const suffix of ['?access_token=private','?api%5Fkey=private','#access_token=private',
  '#chat?client_secret=private','?X-Amz-Signature=private']) {
  assert.equal(helper.link({openUri:'https://example.test/chat'+suffix},'Chat'),'');
}
assert.equal(helper.uri({openUri:'javascript:alert(1)'}),null);
'''
        result = subprocess.run(['node', '-e', code, str(WEB.with_name('native-chats.js'))],
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_history_view_renders_roots_once_and_exposes_more_page(self):
        self.run_node(r'''
ctx.__setChats('["owner",null,""]',{sessions:[
 {id:'root',title:'Root',taskLinks:[{id:'a',title:'Alpha'}]},
 {id:'child',title:'Child',parentSession:'root',contextOnly:true}],next:25,warnings:[]});
const html=ctx.chatsHistoryView();assert.equal((html.match(/data-key="chat-root"/g)||[]).length,1);assert.match(html,/data-key="chat-child"/);assert.match(html,/data-chats-more/);
''')

    def test_task_tab_is_scoped_and_empty_state_explains_missing_links(self):
        self.run_node(r'''
ctx.__setChats('["owner","task-a",""]',{task:'task-a',sessions:[],next:null,warnings:[]});
ctx.route=()=>['tasks','task-a'];ctx.__setTab('chats');const html=ctx.taskChats({id:'task-a',title:'Alpha'});
assert.match(html,/Чаты задачи/);assert.match(html,/Сохраненных связей с чатами пока нет/);assert.match(html,/data-chats-retry/);
''')

    def test_load_chats_discards_response_after_context_changes(self):
        self.run_node(r'''
const releases=[];ctx.route=()=>['coordination'];ctx.get=()=>new Promise(resolve=>releases.push(resolve));
const pending=ctx.loadChats();await Promise.resolve();ctx.route=()=>['tasks','task-b'];ctx.__setTab('chats');const fresh=ctx.loadChats();await Promise.resolve();
releases[0]({sessions:[{id:'stale'}],next:null,warnings:[],discovery:{available:true}});
releases[1]({sessions:[{id:'fresh'}],next:null,warnings:[],discovery:{available:true}});
await Promise.all([pending,fresh]);assert.equal(ctx.__chatState().sessions.map(s=>s.id).join(','),'fresh');
''')


if __name__ == "__main__":
    unittest.main()
