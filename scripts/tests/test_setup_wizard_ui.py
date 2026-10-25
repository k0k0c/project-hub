"""Exercise the actual wizard against isolated REST fixtures, without user data."""
from pathlib import Path
import shutil
import subprocess
import unittest

WEB = Path(__file__).resolve().parents[2] / 'tools/project-portal/web'
HARNESS = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const copy=value=>JSON.parse(JSON.stringify(value));
const source=fs.readFileSync(process.argv[2]+'/setup-wizard.js','utf8');
function backend(p={}) {
  return {state:{schemaVersion:1,revision:0,progress:{started:false,completed:false,step:'welcome',application:'codex',...p},invitation:null},
    connections:{bindings:[]},providers:{revision:'r0',default:'none',items:[]},accounts:[],projects:[],receipts:{},attempt:null,
    calls:[],acks:new Map(),lost:null,creates:0,invites:0,probes:0,providerSaves:0};
}
function create(b=backend()) {
  let serial=0,dialog,langChange;
  const popup=[],copied=[],listeners={};
  const decode=s=>s.replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
  class Element {
    constructor(attrs='',tag='button',body='') {
      this.tagName=tag.toUpperCase();this.dataset={};this.events={};this.attrs={};this.open=false;
      for(const m of attrs.matchAll(/([\w-]+)(?:="([^"]*)")?/g))this.attrs[m[1]]=decode(m[2]||'');
      for(const [k,v]of Object.entries(this.attrs))if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v;
      this.disabled='disabled'in this.attrs;this.value=this.attrs.value||'';
      if(tag==='select'){const options=[...body.matchAll(/<option value="([^"]*)"([^>]*)>/g)];this.value=decode((options.find(m=>/selected/.test(m[2]))||options[0]||['',''])[1]);}
    }
    set innerHTML(html){this.html=html;this.nodes=[];for(const m of html.matchAll(/<(button|input|select|a)\b([^>]*)(?:>([\s\S]*?)<\/\1>|\/?>)/g))this.nodes.push(new Element(m[2],m[1],m[3]||''));}
    get innerHTML(){return this.html||'';}
    querySelector(selector){return this.nodes?.find(node=>node.matches(selector))||null;}
    matches(selector){const m=selector.match(/^\[([^=\]]+)(?:="([^"]*)")?\]$/);return !!m&&m[1]in this.attrs&&(m[2]===undefined||this.attrs[m[1]]===m[2]);}
    closest(selector){return this.matches(selector)?this:null;}
    addEventListener(name,fn){this.events[name]=fn;}
    setAttribute(k,v){this.attrs[k]=v;}
    showModal(){this.open=true;}
    close(){this.open=false;}
  }
  const focus={focus(){focus.restored=true;}},classes=new Set();
  const document={activeElement:focus,documentElement:{classList:{add:v=>classes.add(v),remove:v=>classes.delete(v)}},
    addEventListener:(k,v)=>listeners[k]=v,querySelectorAll:()=>[],createElement:()=>dialog=new Element(),body:{appendChild(){}}};
  async function fetch(url,options={}) {
    const body=options.body?JSON.parse(options.body):null;b.calls.push({url,body,raw:options.body});
    let value,status=200;
    if(!body) {
      if(url==='/api/setup-wizard')value={...b.state,autoEligible:!b.state.progress.started};
      else if(url==='/api/connections')value=b.connections;
      else if(url==='/api/agent-providers')value=b.providers;
      else if(url.startsWith('/api/agent-providers?'))value=b.receipts[new URL(url,'http://localhost').searchParams.get('requestId')]||{};
      else if(url==='/api/chatgpt-auth')value={accounts:b.accounts};
      else if(url.startsWith('/api/chatgpt-auth?')){value={...b.attempt};delete value.authorizePath;}
      else if(url==='/api/projects')value={projects:b.projects};
      else throw Error('Unexpected GET '+url);
    } else if(url==='/api/v1/setup-wizard') {
      if(body.expected!==b.state.revision){status=409;value={error:'revision_conflict'};}
      else {
        if(body.action==='claim'){b.state.progress.started=true;b.state.revision++;}
        else {Object.assign(b.state.progress,body.patch,{started:true});b.state.revision++;}
        value={...b.state,autoEligible:false,...(body.action==='claim'?{claimed:true}:{})};
      }
    } else {
      const key=url+':'+body.requestId;
      if(body.requestId&&b.acks.has(key))value=b.acks.get(key);
      else if(url==='/api/v1/connections'&&['invite','reconnect'].includes(body.action)) {
        b.invites++;value={id:'invite-'+b.invites,url:'http://127.0.0.1:8769/connect/private-invite',expires:4000000000};
        b.state.invitation={id:value.id,state:'pending',connectionId:null};
      } else if(url==='/api/v1/connections'&&body.action==='test'){value={id:body.id,tests:[]};}
      else if(url==='/api/v1/projects') {b.creates++;const project={id:'project-'+b.creates,name:body.name,roots:body.roots};b.projects.push(project);value={project};}
      else if(url==='/api/v1/chatgpt-auth') {
        if(body.action==='start')value=b.attempt={attemptId:body.requestId,status:'pending',authorizePath:b.badAuthPath||'/auth/chatgpt/authorize?attemptId='+body.requestId};
        else if(body.action==='models')value={models:[]};
        else throw Error('Unexpected auth action');
      } else if(url==='/api/v1/agent-providers') {
        if(['save','save-chatgpt'].includes(body.action)) {
          b.providerSaves++;const item={id:'provider-'+b.providerSaves,name:body.name,provider:body.provider||'chatgpt',model:body.model,availability:{status:'not_checked'},
            ...(body.action==='save-chatgpt'?{authentication:{method:'chatgpt_oauth',accountId:body.accountId}}:{})};
          b.providers.items.push(item);b.providers.default=item.id;b.providers.revision='r'+b.providerSaves;
          value={saved:true,id:item.id,requestId:body.requestId};
        } else if(body.action==='select'){b.providers.default=body.id;value={saved:true,id:body.id,requestId:body.requestId};}
        else if(body.action==='probe'){b.probes++;value={id:body.id,requestId:body.requestId,kind:'model-probe',status:'completed'};b.receipts[body.requestId]=value;b.providers.items.find(i=>i.id===body.id).availability={status:'available',requestId:body.requestId};}
        else throw Error('Unexpected provider action');
      } else throw Error('Unexpected POST '+url);
      if(body.requestId)b.acks.set(key,copy(value));
      if(b.lost===body.action){b.lost=null;throw Error('Lost acknowledgement');}
    }
    return {ok:status<400,status,json:async()=>copy(value)};
  }
  const context={document,fetch,URL,crypto:{randomUUID:()=>String(++serial).padStart(32,'0')},HubI18n:{locale:'en',onChange:fn=>langChange=fn},
    location:{origin:'http://127.0.0.1:8769',pathname:'/',hash:'#projects'},navigator:{clipboard:{writeText:async s=>copied.push(s)}},
    open:(url,target)=>{const p={url,target,closed:false,location:{replace(v){p.url=v;}},close(){p.closed=true;}};popup.push(p);return p;},
    setTimeout:()=>1,clearTimeout(){},addEventListener(){},dispatchEvent(){},console};
  context.window=context;vm.createContext(context);vm.runInContext(source,context);
  const api=context.HubSetupWizardUI;
  return {b,api,context,popup,copied,focus,classes,get dialog(){return dialog;},get html(){return dialog?.innerHTML||'';},
    async mount(){await api.init();},async open(){await api.open();},
    async action(action){const node=dialog.querySelector('[data-setup-action="'+action+'"]');assert(node,'Missing action '+action);assert(!node.disabled,'Disabled action '+action);await dialog.events.click({target:node});},
    async step(step){const node=dialog.querySelector('[data-setup-step="'+step+'"]');assert(node&&!node.disabled,'Step unavailable '+step);await dialog.events.click({target:node});},
    async app(value){const node=dialog.querySelector('[data-setup-application="'+value+'"]');await dialog.events.click({target:node});},
    async field(name,value){const node=dialog.querySelector('[data-setup-field="'+name+'"]');assert(node,'Missing field '+name);node.value=value;dialog.events.input({target:node});await dialog.events.change({target:node});},
    locale(value){context.HubI18n.locale=value;langChange();},posts(action){return b.calls.filter(c=>c.body&&(!action||c.body.action===action));}};
}
function bound(b,client='codex') {
  b.projects.push({id:'bound-project',name:'Example project'});
  const row={id:'connection-bound',client,profile:{persistentInstructions:{status:'saved',loadVerified:false}},capabilities:{mcp:{state:'verified'}},features:{callback:{state:'not_reported'}},
    controlStatus:{canTest:false},projectBindings:[{id:'binding-bound',project:'bound-project',status:'active'}]};
  b.connections.bindings.push(row);b.state.invitation={id:b.state.progress.invitationId,state:'used',connectionId:row.id};return row;
}
async function firstOpenAndResume() {
  const h=create();await h.mount();assert(h.dialog.open);assert.equal(h.posts('claim').length,1);assert(h.classes.has('setup-wizard-open'));
  await h.action('next');assert.equal(h.b.state.progress.step,'app');await h.action('close');assert(!h.dialog.open);assert(h.focus.restored);
  const reloaded=create(h.b);await reloaded.mount();assert(!reloaded.dialog);assert.equal(reloaded.posts('claim').length,1,'auto opens once per installation');
  await reloaded.open();assert.equal(h.b.state.progress.step,'app');assert(reloaded.html.includes('Which application'));
  reloaded.dialog.events.cancel({preventDefault(){}});assert(!reloaded.dialog.open);
  h.b.state.progress.completed=true;h.b.state.progress.step='finish';await reloaded.open();assert.equal(h.b.state.progress.step,'welcome');
  assert(reloaded.api.entry().includes('data-setup-open'));
}
async function invitationAndProjectCorrelation() {
  const h=create();await h.mount();await h.action('next');await h.app('other');assert(h.html.includes('HTTP MCP'));assert(!h.html.includes('Cursor'));
  await h.action('next');await h.action('invite');await h.action('copy-invite');assert(h.copied[0].includes('/connect/private-invite'));assert(h.copied[0].includes('intended')||h.copied[0].includes('chat’s project'));
  assert(!JSON.stringify(h.b.state.progress).includes('private-invite'));
  h.b.connections.bindings.push({id:'unrelated',client:'codex',project:'wrong-project',capabilities:{mcp:{state:'verified'}}});h.b.projects.push({id:'wrong-project',name:'Other project'});
  await h.api.refresh();await h.action('next');assert(h.html.includes('Not identified'));assert.equal(h.b.state.progress.projectId,'');
  const row=bound(h.b,'other');await h.api.refresh();assert.equal(h.b.state.progress.projectId,'bound-project');assert(h.html.includes('Manual creation will be skipped'));
  await h.action('next');await h.action('skip');await h.action('skip');assert.equal(h.b.state.progress.step,'finish');assert.equal(h.b.creates,0);
  assert(!h.dialog.querySelector('[data-setup-step="control"]')||h.dialog.querySelector('[data-setup-step="control"]').disabled);
  await h.action('next');assert(h.b.state.progress.completed);await h.open();assert(h.html.includes('What would you like'));
  await h.action('add-app');assert.equal(h.b.state.progress.connectionId,'');assert.equal(h.b.connections.bindings.length,2);assert.equal(h.b.projects.length,2);
  await h.action('next');await h.action('invite');assert.equal(h.b.invites,2);assert.equal(row.id,'connection-bound');
}
async function manualProjectWithoutMcp() {
  const h=create();await h.mount();await h.action('standalone');await h.field('manualProjectName','Research example');await h.field('root','C:/example/research');await h.action('close');
  const resumed=create(h.b);await resumed.mount();await resumed.open();assert.equal(resumed.dialog.querySelector('[data-setup-field="root"]').value,'C:/example/research');
  await resumed.field('root','');await resumed.action('create-project');
  assert.equal(h.b.creates,1);assert.deepEqual(h.b.projects[0].roots,[]);assert(resumed.html.includes('There is no need to create it again'));assert.equal(h.b.state.progress.projectId,'project-1');
  await resumed.action('next');assert.equal(h.b.state.progress.step,'chatgpt');assert.equal(h.b.invites,0);
}
async function switchingApplicationStartsAFreshInvitation() {
  const h=create();await h.mount();await h.action('next');await h.action('next');await h.action('invite');
  await h.action('back');await h.app('other');await h.action('next');
  assert(!h.dialog.querySelector('[data-setup-action="copy-invite"]'),'a previous application link cannot strand the new selection');
  await h.action('invite');assert.equal(h.b.invites,2);assert(h.b.state.progress.invitationId);
}
async function apiSaveRetryAndExplicitProbe() {
  const b=backend({started:true,step:'api'}),h=create(b);await h.mount();await h.open();await h.field('model','example-model');await h.action('next');
  assert.equal(b.state.progress.step,'api-key');await h.field('apiKey','PRIVATE-API-KEY');b.lost='save';await h.action('save-api');
  assert(h.html.includes('Retry the same request'));await h.action('close');await h.open();await h.action('retry');
  const saves=h.posts('save').filter(c=>c.url==='/api/v1/agent-providers');assert.equal(saves.length,2);assert.equal(saves[0].raw,saves[1].raw);assert.equal(b.providerSaves,1);
  assert(!h.html.includes('PRIVATE-API-KEY'));assert(!JSON.stringify(b.state).includes('PRIVATE-API-KEY'));assert.equal(b.probes,0);
  assert(h.html.includes('Saved · not checked'));await h.action('probe');assert.equal(b.probes,1);assert(h.html.includes('Response received'));
  const item=b.providers.items[0];item.availability={status:'outcome_unknown',requestId:b.state.progress.probeRequestId};b.receipts[b.state.progress.probeRequestId].status='outcome_unknown';
  const reloaded=create(b);await reloaded.mount();await reloaded.open();assert(reloaded.html.includes('Refresh request status'));assert(!reloaded.dialog.querySelector('[data-setup-action="probe"]'));
  await reloaded.action('probe-status');assert.equal(b.probes,1);
}
async function oauthSeparateTabAndControlSupport() {
  const b=backend({started:true,step:'chatgpt'}),h=create(b);await h.mount();await h.open();await h.action('sign-in');assert.equal(h.popup[0].target,'_blank');
  assert(h.popup[0].url.startsWith('/auth/chatgpt/authorize?'));assert.equal(h.context.location.hash,'#projects');assert(h.html.includes('target="_blank"'));
  await h.api.refresh();assert(h.html.includes('href="/auth/chatgpt/authorize?attemptId='),'authorization link survives status reads without authorizePath');
  b.accounts.push({id:'account1',label:'Example account',status:'connected',planUsageEnabled:true,models:[{slug:'example-model',display_name:'Example model'}]});
  b.attempt.status='completed';b.attempt.accountId='account1';await h.api.refresh();await h.action('save-oauth');assert.equal(b.providerSaves,1);assert.equal(b.probes,0);
  assert.equal(h.posts('save-chatgpt')[0].body.accountId,'account1');assert(!JSON.stringify(b.state).includes('authorizePath'));
  const row=bound(b,'other');b.state.progress.step='control';b.state.progress.connectionId=row.id;b.state.invitation=null;row.controlStatus.canTest=true;
  await h.api.refresh();assert(h.html.includes('not supported'));assert(!h.dialog.querySelector('[data-setup-action="control-test"]'));
  row.client='codex';row.control={hasCredential:true};await h.api.refresh();assert(h.html.includes('creates a separate chat'));assert.equal(h.posts('test').length,0);
  await h.action('control-test');assert.deepEqual(h.posts('test')[0].body,{action:'test',id:row.id,bindingId:'binding-bound'});
  row.revoked=true;b.state.progress.step='verify';await h.api.refresh();await h.action('recover');assert.equal(h.posts('reconnect')[0].body.id,row.id);
  assert.equal(b.connections.bindings.length,1,'recovery keeps the existing connection');
}
async function safeLinksAndLocalization() {
  const h=create();await h.mount();
  for(const locale of ['ru','en']) {h.locale(locale);for(const step of ['welcome','app','invite','verify','chatgpt','api','control','projects','finish']) {
    h.b.state.progress.step=step;await h.api.refresh();const links=[...h.html.matchAll(/<a\b([^>]*)>/g)];assert(links.length,'Help link on '+step);
    for(const [,attrs]of links){assert(attrs.includes('target="_blank"'));assert(attrs.includes('rel="noopener noreferrer"'));}
    if(locale==='en')assert(!/[А-Яа-яЁё]/.test(h.html),'English copy on '+step);
  }}
  h.context.navigator.clipboard.writeText=async()=>{throw Error('clipboard unavailable');};h.b.state.progress.step='verify';bound(h.b);await h.api.refresh();await h.action('fresh-chat');assert(h.html.includes('setup-copy-text'));await h.action('back');assert(!h.html.includes('setup-copy-text'));
}
(async()=>{await firstOpenAndResume();await invitationAndProjectCorrelation();await manualProjectWithoutMcp();await switchingApplicationStartsAFreshInvitation();await apiSaveRetryAndExplicitProbe();await oauthSeparateTabAndControlSupport();await safeLinksAndLocalization();})().catch(error=>{console.error(error);process.exitCode=1;});
'''


class SetupWizardUiTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required')
    def test_wizard_behaviors(self):
        result = subprocess.run(['node', '-', str(WEB)], input=HARNESS,
                                capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_loaded_assets_and_compact_dialog_contract(self):
        index = (WEB / 'index.html').read_text(encoding='utf-8')
        css = (WEB / 'setup-wizard.css').read_text(encoding='utf-8')
        self.assertIn('/setup-wizard.js', index)
        self.assertIn('/setup-wizard.css', index)
        self.assertIn('grid-template-rows:', css)
        self.assertNotRegex(css, r'overflow(?:-y)?\s*:\s*(?:auto|scroll)')


if __name__ == '__main__':
    unittest.main()
