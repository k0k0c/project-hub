"""Global agent-rule editing, acknowledgment and draft preservation."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class AgentInstructionsUiTest(unittest.TestCase):
    def run_js(self, checks):
        web = Path(__file__).resolve().parents[2] / 'tools' / 'project-portal' / 'web'
        setup = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const storage=new Map(),handlers={},requests=[],posts=[];
const backend={text:'Existing additional rules',revision:'rules-r1',workflow:'Original rules <retain>',baseWorkflow:'Base rules <retain>'};
const status={textContent:''},save={disabled:true},cancel={disabled:true};
let current=['settings','agents','rules'];
const ctx={console,URLSearchParams,state:null,activeProject:null,route:()=>current,render(){},
 title:()=>'',uiIcon:()=>'',taskTableColumns:[],
 escape:value=>String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch])),
 sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
 document:{documentElement:{dataset:{hubLocale:'en'}},querySelectorAll:()=>[],addEventListener:(name,handler)=>(handlers[name]??=[]).push(handler),
   getElementById:id=>id==='agent-instructions-status'?status:null,
   querySelector:selector=>selector==='[data-agent-instructions-action="save"]'?save:selector==='[data-agent-instructions-action="cancel"]'?cancel:null},
 navigator:{},fetch:async(url,options={})=>{requests.push({url,options});if(options.method==='POST'){assert.ok(posts.length,'Unexpected rule mutation');const reply=posts.shift();if(reply instanceof Error)throw reply;return {ok:(reply.status||200)<400,status:reply.status||200,json:async()=>reply.body};}return {ok:true,json:async()=>JSON.parse(JSON.stringify(backend))};}};
ctx.window=ctx;vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/locale-catalog.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/i18n.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/settings.js','utf8'),ctx);
const tick=async()=>{for(let i=0;i<16;i++)await Promise.resolve();};
const edit=value=>{const target={value,dataset:{},matches:selector=>selector==='[data-agent-instructions-text]',closest:()=>null};for(const fn of handlers.input||[])fn({target});};
const click=async action=>{const button={dataset:{agentInstructionsAction:action},textContent:'',closest:selector=>selector==='[data-agent-instructions-action]'?button:null};for(const fn of handlers.click||[])await fn({target:button});await tick();return button;};
const postCalls=()=>requests.filter(item=>item.options.method==='POST');
(async()=>{
'''
        code = setup + checks + r'''
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-e', code, str(web)], capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rules_are_global_preserve_original_and_require_client_consent(self):
        self.run_js(r'''
await Promise.all([ctx.loadAgentInstructions(),ctx.loadModernWorkflow()]);
let html=ctx.settingsPage();
assert.match(html,/Original rules &lt;retain&gt;/);assert.match(html,/Base rules &lt;retain&gt;/);
assert.match(html,/Existing additional rules/);assert.match(html,/explicit consent/);
assert.match(html,/exact destination file and scope/);assert.match(html,/does not write client files/);
assert.doesNotMatch(html,/hub-legacy-codex|data-instructions-project|href="#settings\/instructions"/);
assert.ok(requests.every(item=>!item.url.includes('project=')));
ctx.activeProject='selected';ctx.state={settings:{revision:'project-r1',settings:{}}};
html=ctx.settingsPage();assert.doesNotMatch(html,/data-instructions-project|hub-legacy-codex/);
ctx.navigator.clipboard={writeText:async value=>ctx.copied=value};await click('copy');assert.equal(ctx.copied,backend.workflow);
delete ctx.navigator.clipboard;const button=await click('copy');assert.match(button.textContent,/manually/);
''')

    def test_conflicts_and_refresh_preserve_the_draft_and_original_revision(self):
        self.run_js(r'''
await ctx.loadAgentInstructions();edit('Custom </textarea><script>unsafe</script>');
assert.equal(save.disabled,false);assert.equal(cancel.disabled,false);
posts.push({status:409,body:{error:'conflict'}});await ctx.submitAgentInstructions();
assert.equal(JSON.parse(postCalls()[0].options.body).expected,'rules-r1');
backend.text='Changed elsewhere';backend.revision='rules-r2';await ctx.loadAgentInstructions(true);
let html=ctx.settingsPage();assert.match(html,/draft is preserved/);
assert.match(html,/Custom &lt;\/textarea&gt;&lt;script&gt;unsafe&lt;\/script&gt;/);assert.doesNotMatch(html,/<script>/);
assert.equal(JSON.parse(storage.get('project-hub-agent-instructions-draft')).expected,'rules-r1');
await click('cancel');html=ctx.settingsPage();assert.match(html,/Changed elsewhere/);assert.doesNotMatch(html,/Custom &lt;/);
assert.equal(storage.has('project-hub-agent-instructions-draft'),false);
edit('New global additions');posts.push({body:{text:'New global additions',revision:'rules-r3'}});await ctx.submitAgentInstructions();
assert.deepEqual(JSON.parse(postCalls()[1].options.body),{expected:'rules-r2',text:'New global additions'});
assert.match(ctx.settingsPage(),/Additions saved in Hub/);assert.equal(storage.size,0);
''')

    def test_uncertain_acknowledgments_replay_identical_bytes_and_keep_text(self):
        self.run_js(r'''
await ctx.loadAgentInstructions();edit('Keep this draft');
posts.push({body:{text:'Different text',revision:'rules-r2'}});await ctx.submitAgentInstructions();
assert.match(ctx.settingsPage(),/Retry saving/);assert.equal(storage.size,1);
edit('A different write');await ctx.submitAgentInstructions();assert.equal(postCalls().length,1);
posts.push({status:400,body:{error:'replay rejected'}});await click('retry');
assert.match(ctx.settingsPage(),/Retry saving/);assert.equal(postCalls()[0].options.body,postCalls()[1].options.body);
posts.push({body:{text:'Keep this draft',revision:'rules-r2'}});await click('retry');
assert.equal(postCalls()[0].options.body,postCalls()[2].options.body);
assert.doesNotMatch(ctx.settingsPage(),/Retry saving/);assert.equal(storage.size,0);
''')

    def test_oversized_drafts_cannot_save_and_failed_reads_do_not_loop(self):
        self.run_js(r'''
await ctx.loadAgentInstructions();edit('x'.repeat(24001));await ctx.submitAgentInstructions();assert.equal(postCalls().length,0);assert.equal(save.disabled,true);
ctx.fetch=async url=>{requests.push({url});throw Error('offline');};
await ctx.loadAgentInstructions(true);const count=requests.length;await ctx.loadAgentInstructions();await ctx.loadAgentInstructions();assert.equal(requests.length,count);
assert.equal(JSON.parse(storage.get('project-hub-agent-instructions-draft')).text.length,24001);
''')


if __name__ == '__main__':
    unittest.main()
