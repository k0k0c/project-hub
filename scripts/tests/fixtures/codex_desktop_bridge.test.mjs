import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import crypto from 'node:crypto';
import {once} from 'node:events';
import {NativeHost, Journal, DesktopControl, HubBindings, serve, canonical, acquireLock} from '../../codex_desktop_bridge.mjs';

const ID = '11111111-1111-4111-8111-111111111111';
function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'hub-bridge-'));
  t.after(() => fs.rmSync(root, {recursive:true, force:true}));
  const events = [];
  const host = {caller:ID, discover:async () => {}, call:async (name, args) => {
    events.push({name, args});
    if (name === 'list_projects') return {projects:[{projectId:'native-project', projectKind:'local', hostId:'local', path:root}]};
    if (name === 'read_thread') return {thread:{id:args.threadId, hostId:'local', cwd:root}};
    if (name === 'list_threads') {
      assert.equal(args.limit,50, 'Codex accepts at most 50 catalogue entries');
      return {threads:[{id:ID, hostId:'local', projectId:'native-project', cwd:root}]};
    }
    if (name === 'create_thread') return {threadId:ID, hostId:'local'};
    if (name === 'send_message_to_thread') return {status:'queued'};
    throw Error('unexpected tool');
  }};
  const filename = path.join(root, 'journal.json');
  const journal = new Journal(filename, 'instance');
  const catalog = {bindings:[{id:'connection',client:'codex',projectBindings:[
    {id:'binding',revision:1,project:'hub-project',status:'active',scope:{root}}]}]};
  const bindings = new HubBindings('http://127.0.0.1:1','connection',{load:async()=>catalog});
  const control = new DesktopControl(host, journal, bindings);
  return {root, events, host, filename, journal, control, bindings, catalog};
}

test('create maps an exact native project, verifies membership and omits model/worktree overrides', async t => {
  const f = fixture(t);
  const result = await f.control.execute('/v1/chats/create', {requestId:'one', workspace:f.root, prompt:'hello'});
  assert.equal(result.id, ID); assert.equal(result.visibility.state, 'verified');
  assert.equal(result.visibility.guiOpened, false);
  assert.deepEqual(f.events.find(e => e.name === 'create_thread').args,
    {prompt:'hello', target:{type:'project', projectId:'native-project', environment:{type:'local'}}});
  assert.equal(result.visibility.method, 'codex_app.list_threads');
  assert.ok(f.events.some(e => e.name === 'list_threads'));
  const disk = fs.readFileSync(f.filename, 'utf8');
  assert.ok(!disk.includes('hello'));
});

test('same request is idempotent across adapter restart; changed payload conflicts', async t => {
  const f = fixture(t), body = {requestId:'one', workspace:f.root, prompt:'hello'};
  await f.control.execute('/v1/chats/create', body);
  const restarted = new DesktopControl(f.host, new Journal(f.filename, 'instance'), f.bindings);
  assert.equal((await restarted.execute('/v1/chats/create', {prompt:body.prompt, workspace:body.workspace, requestId:body.requestId})).id, ID);
  await assert.rejects(restarted.execute('/v1/chats/create', {...body, prompt:'different'}), /request_id_conflict/);
  assert.equal(f.events.filter(e => e.name === 'create_thread').length, 1);
});

test('catalogue refresh is awaited without creating another chat', async t => {
  const f=fixture(t), original=f.host.call; let polls=0;
  f.host.call=async (name,args) => name==='list_threads' && ++polls===1 ? {threads:[]} : original(name,args);
  const control=new DesktopControl(f.host,f.journal,f.bindings,{verificationTimeout:1000,verificationInterval:5});
  const result=await control.execute('/v1/chats/create',{requestId:'delayed',workspace:f.root,prompt:'hello'});
  assert.equal(result.visibility.state,'verified');
  assert.equal(f.events.filter(e=>e.name==='create_thread').length,1);
  assert.equal(polls,2);
});

test('unknown creation outcome reserves its request before dispatch and never retries it', async t => {
  const f = fixture(t), original = f.host.call;
  f.host.call = async (name, args) => {
    if (name === 'create_thread') {
      assert.equal(JSON.parse(fs.readFileSync(f.filename)).operations['create:one'].status, 'dispatching');
      throw Error('transport ended after possible creation');
    }
    return original(name, args);
  };
  const body = {requestId:'one', workspace:f.root, prompt:'hello'};
  await assert.rejects(f.control.execute('/v1/chats/create', body));
  const restarted = new DesktopControl(f.host, new Journal(f.filename, 'instance'), f.bindings);
  await assert.rejects(restarted.execute('/v1/chats/create', body), /prior_outcome_requires_reconciliation/);
});

test('send rejects arbitrary chats and a changed native project before sending', async t => {
  const f = fixture(t), body = {requestId:'send', workspace:f.root, prompt:'hello', nativeId:ID};
  await assert.rejects(f.control.execute('/v1/chats/send', body), /chat_not_owned/);
  await f.control.execute('/v1/chats/create', {requestId:'one', workspace:f.root, prompt:'hello'});
  const original = f.host.call;
  f.host.call = async (name, args) => name === 'list_threads' ?
    {threads:[{id:ID, hostId:'local', projectId:'other', cwd:f.root}]} : original(name, args);
  await assert.rejects(f.control.execute('/v1/chats/send', body), /native_chat_not_visible_in_project/);
  assert.ok(!f.events.some(e => e.name === 'send_message_to_thread'));
});

function sourceLaunch(f, requestId='source', prompt='continue source') {
  const launch={requestId,status:'dispatching',targetNativeId:ID,
    dispatchPromptSha256:crypto.createHash('sha256').update(prompt).digest('hex'),
    continuationSource:{kind:'task-chat',nativeId:ID,task:'task',stage:'step'},
    envelope:{connection:'connection',operation:'task-execute',project:'hub-project',bindingId:'binding',bindingRevision:1,
      projectScope:{kind:'workspace',root:f.root},inputs:{task:{id:'task'}},
      resultDestination:{kind:'task-report',project:'hub-project',task:'task',stage:'step'}}};
  f.catalog.bindings[0].launches=[launch];
  return {launch,body:{requestId,workspace:f.root,prompt,nativeId:ID}};
}

test('a saved task continuation can send to its existing source chat without granting arbitrary ownership', async t => {
  const f=fixture(t), {launch,body}=sourceLaunch(f);
  const result=await f.control.execute('/v1/chats/send',body);
  assert.equal(result.id,ID);assert.equal(result.visibility.state,'verified');
  assert.equal(f.journal.data.threads[ID],undefined,'source association is not an unlimited ownership grant');
  launch.status='completed';
  const restarted=new DesktopControl(f.host,new Journal(f.filename,'instance'),f.bindings);
  assert.deepEqual(await restarted.execute('/v1/chats/send',body),result);
  await assert.rejects(restarted.execute('/v1/chats/send',{...body,requestId:'arbitrary'}),/chat_not_owned/);
  const empty=new DesktopControl(f.host,new Journal(path.join(f.root,'empty.json'),'instance'),f.bindings);
  await assert.rejects(empty.execute('/v1/chats/send',body),/chat_not_owned/);
  assert.equal(f.events.filter(e=>e.name==='send_message_to_thread').length,1);
});

test('an older source chat is verified by exact native identity and workspace outside the recent catalogue', async t => {
  const f=fixture(t), {body}=sourceLaunch(f), original=f.host.call;
  f.host.call=async(name,args)=>name==='list_threads'?{threads:[]}:original(name,args);
  const result=await f.control.execute('/v1/chats/send',body);
  assert.equal(result.visibility.method,'codex_app.read_thread+list_threads');
  const reads=f.events.filter(e=>e.name==='read_thread');
  assert.ok(reads.length);assert.ok(reads.every(e=>e.args.threadId===ID&&e.args.includeOutputs===false&&e.args.maxOutputCharsPerItem===0));
  assert.equal(f.events.filter(e=>e.name==='send_message_to_thread').length,1);
});

test('source continuation rejects a changed target, scope, prompt, operation or task before sending', async t => {
  const changes=[l=>l.targetNativeId='22222222-2222-4222-8222-222222222222',
    l=>l.envelope.connection='other',l=>l.envelope.bindingRevision++,l=>l.envelope.project='other',
    l=>l.continuationSource.task='other',l=>l.continuationSource.stage='other',
    l=>l.envelope.operation='research',l=>l.dispatchPromptSha256='wrong',l=>l.status='cancelled'];
  for(const mutate of changes) {
    const f=fixture(t), {launch,body}=sourceLaunch(f);mutate(launch);
    await assert.rejects(f.control.execute('/v1/chats/send',body),/chat_not_owned/);
    assert.ok(!f.events.some(e=>e.name==='send_message_to_thread'));
  }
  for(const metadata of [{id:ID,hostId:'remote',cwd:'same'}, {id:ID,hostId:'local',cwd:'same',projectId:'other'}]) {
    const f=fixture(t), {body}=sourceLaunch(f), original=f.host.call;
    f.host.call=async(name,args)=>name==='list_threads'?{threads:[]}:name==='read_thread'?
      {thread:{...metadata,cwd:f.root}}:original(name,args);
    await assert.rejects(f.control.execute('/v1/chats/send',body),/native_chat_not_visible_in_project/);
    assert.ok(!f.events.some(e=>e.name==='send_message_to_thread'));
  }
});

test('source authorization is checked again immediately before mutation and unknown sends never replay', async t => {
  const f=fixture(t), {launch,body}=sourceLaunch(f), original=f.host.call;
  f.host.call=async(name,args)=>{if(name==='list_threads')launch.status='cancelled';return original(name,args)};
  await assert.rejects(f.control.execute('/v1/chats/send',body),/chat_not_owned/);
  assert.ok(!f.events.some(e=>e.name==='send_message_to_thread'));
  const g=fixture(t), source=sourceLaunch(g), call=g.host.call;let sends=0;
  g.host.call=async(name,args)=>{if(name==='send_message_to_thread'){sends++;throw Error('reply lost')}return call(name,args)};
  await assert.rejects(g.control.execute('/v1/chats/send',source.body));
  await assert.rejects(g.control.execute('/v1/chats/send',source.body),/prior_outcome_requires_reconciliation/);
  assert.equal(sends,1);
});

test('native project ambiguity and paths without an active Hub binding never create chats', async t => {
  const f = fixture(t);
  await assert.rejects(f.control.execute('/v1/chats/create', {requestId:'one', workspace:os.tmpdir(), prompt:'hello'}), /hub_project_binding_missing/);
  f.host.call = async () => ({projects:[{projectId:'a', projectKind:'local', hostId:'local', path:f.root},
    {projectId:'b', projectKind:'local', hostId:'local', path:f.root}]});
  await assert.rejects(f.control.execute('/v1/chats/create', {requestId:'two', workspace:f.root, prompt:'hello'}), /native_project_ambiguous/);
  assert.ok(!f.events.some(e => e.name === 'create_thread'));
});

test('HTTP requires its own key, exact host, no browser Origin and an allowlisted action', async t => {
  const f = fixture(t), key = 'a'.repeat(48), server = serve(f.control, key);
  await once(server, 'listening'); t.after(() => {server.closeAllConnections(); server.close();});
  const base = `http://127.0.0.1:${server.address().port}`;
  assert.equal((await fetch(base + '/v1/health')).status, 403);
  assert.equal((await fetch(base + '/v1/health', {headers:{Authorization:'Bearer '+key, Origin:base}})).status, 403);
  assert.equal((await fetch(base + '/v1/health', {headers:{Authorization:'Bearer '+key}})).status, 200);
  const response = await fetch(base + '/tools/call', {method:'POST', headers:{Authorization:'Bearer '+key, 'Content-Type':'application/json'}, body:'{}'});
  assert.equal(response.status, 404);
  const invalid = await fetch(base + '/v1/chats/create', {method:'POST', headers:{Authorization:'Bearer '+key,'Content-Type':'application/json'},
    body:JSON.stringify({requestId:'x', workspace:f.root, prompt:'hi', tool:'delete_thread'})});
  assert.equal(invalid.status, 400);
});

test('native transport correlates fragmented frames and refuses unlisted tools', async t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'hub-pipe-'));
  const address = process.platform === 'win32' ? '\\\\.\\pipe\\hub-bridge-test-' + crypto.randomUUID() : path.join(directory,'test.sock');
  const frame = value => {const b=Buffer.from(JSON.stringify(value)), h=Buffer.alloc(4); h.writeUInt32LE(b.length); return Buffer.concat([h,b]);};
  let socket;
  const server = net.createServer(peer => {socket=peer; peer.once('data', () => {
    const b=frame({id:1,jsonrpc:'2.0',result:{answer:42}}); peer.write(b.subarray(0,3)); setImmediate(()=>peer.write(b.subarray(3)));
  });});
  server.listen(address); await once(server,'listening');
  const host = new NativeHost(address, ID);
  t.after(() => {host.close(); socket?.destroy(); server.close(); fs.rmSync(directory,{recursive:true,force:true});});
  assert.equal((await host.request('tools/list', {})).answer,42);
  host.tools = new Set(['list_projects']);
  await assert.rejects(host.call('delete_thread', {}), /tool_not_allowed/);
});

test('a different app/caller instance cannot reuse an ownership journal', t => {
  const f = fixture(t); f.journal.save();
  assert.throws(() => new Journal(f.filename, 'another-instance'), /bridge_instance_changed/);
  assert.equal(canonical(f.root), process.platform === 'win32' ? fs.realpathSync(f.root).toLowerCase() : fs.realpathSync(f.root));
});

test('single-writer lock publishes a complete PID and never replaces an owner', t => {
  const f = fixture(t), filename=path.join(f.root,'journal.lock');
  acquireLock(filename);
  const content=fs.readFileSync(filename,'utf8');
  assert.equal(JSON.parse(content).pid, process.pid);
  assert.throws(() => acquireLock(filename), {code:'EEXIST'});
  assert.equal(fs.readFileSync(filename,'utf8'),content);
});

test('two allowed projects route independently and cannot exchange owned chats', async t => {
  const f=fixture(t), second=path.join(f.root,'second'); fs.mkdirSync(second);
  const otherId='22222222-2222-4222-8222-222222222222', chats=[];
  f.host.call=async (name,args) => {
    f.events.push({name,args});
    if(name==='list_projects') return {projects:[
      {projectId:'first',projectKind:'local',hostId:'local',path:f.root},
      {projectId:'second',projectKind:'local',hostId:'local',path:second}]};
    if(name==='create_thread') {
      const first=args.target.projectId==='first', id=first?ID:otherId;
      chats.push({id,hostId:'local',projectId:args.target.projectId,cwd:first?f.root:second});
      return {threadId:id,hostId:'local'};
    }
    if(name==='list_threads') return {threads:chats};
    if(name==='send_message_to_thread') return {status:'queued'};
    throw Error('unexpected tool');
  };
  f.catalog.bindings[0].projectBindings.push({id:'binding-second',revision:1,project:'hub-second',status:'active',scope:{root:second}});
  const control=new DesktopControl(f.host,f.journal,f.bindings);
  for(const [workspace,requestId] of [[f.root,'first'],[second,'second']]) {
    const result=await control.execute('/v1/chats/create',{workspace,requestId,prompt:'hello'});
    assert.equal(result.visibility.workspace,canonical(workspace));
    assert.equal(result.visibility.projectId,requestId);
  }
  await assert.rejects(control.execute('/v1/chats/send',{workspace:second,requestId:'wrong',nativeId:ID,prompt:'wrong project'}),/chat_not_owned/);
  for(const [workspace,nativeId] of [[f.root,ID],[second,otherId]])
    await control.execute('/v1/chats/send',{workspace,nativeId,requestId:'send-'+nativeId,prompt:'continue'});
  assert.deepEqual(f.events.filter(e=>e.name==='send_message_to_thread').map(e=>e.args.threadId),[ID,otherId]);
  assert.equal(f.events.filter(e=>e.name==='create_thread').length,2);
});

test('catalogue timeout preserves the created identity without creating or sending twice', async t => {
  const f=fixture(t), original=f.host.call;
  f.host.call=async (name,args) => name==='list_threads'?{threads:[]}:original(name,args);
  const control=new DesktopControl(f.host,f.journal,f.bindings,{verificationTimeout:15,verificationInterval:2});
  const body={requestId:'invisible',workspace:f.root,prompt:'hello'};
  await assert.rejects(control.execute('/v1/chats/create',body),/native_chat_not_visible_in_project/);
  const record=JSON.parse(fs.readFileSync(f.filename)).operations['create:invisible'];
  assert.equal(record.nativeId,ID); assert.equal(record.status,'outcome_unknown');
  await assert.rejects(control.execute('/v1/chats/create',body),/prior_outcome_requires_reconciliation/);
  assert.equal(f.events.filter(e=>e.name==='create_thread').length,1);
  assert.equal(f.events.filter(e=>e.name==='send_message_to_thread').length,0);
});

test('native timeout ignores a late reply and pipe closure rejects pending calls', async t => {
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'hub-timeout-'));
  const address=process.platform==='win32'?'\\\\.\\pipe\\hub-timeout-'+crypto.randomUUID():path.join(directory,'test.sock');
  let peer; const server=net.createServer(socket=>{peer=socket;socket.on('data',()=>{});});
  server.listen(address); await once(server,'listening');
  const host=new NativeHost(address,ID,{timeout:30});
  t.after(()=>{host.close();peer?.destroy();server.close();fs.rmSync(directory,{recursive:true,force:true});});
  await assert.rejects(host.request('tools/list',{}),error=>error.code==='codex_outcome_unknown'&&error.status===504);
  assert.equal(host.pending.size,0);
  const data=Buffer.from(JSON.stringify({id:1,result:{late:true}})), header=Buffer.alloc(4);header.writeUInt32LE(data.length);
  peer.write(Buffer.concat([header,data]));
  let unavailable=0;host.onUnavailable=()=>unavailable++;
  const pending=host.request('tools/list',{}), rejected=assert.rejects(pending,/codex_outcome_unknown/);
  await new Promise(resolve=>setImmediate(resolve));peer.destroy();await rejected;
  assert.equal(host.pending.size,0);assert.equal(unavailable,1);
});

test('binding additions and revocation take effect without adapter restart or folder grants', async t => {
  const f=fixture(t), second=path.join(f.root,'plain-folder'); fs.mkdirSync(second);
  const original=f.host.call;
  f.host.call=async(name,args)=>name==='list_projects'?{projects:[
    {projectId:'native-project',projectKind:'local',hostId:'local',path:second,isGitRepository:false}]}:
    name==='list_threads'?{threads:[{id:ID,projectId:'native-project',hostId:'local',cwd:second}]}:original(name,args);
  const body={requestId:'plain',workspace:second,prompt:'hello'};
  await assert.rejects(f.control.execute('/v1/chats/create',body),/hub_project_binding_missing/);
  const binding={id:'second',revision:1,project:'plain',status:'active',scope:{root:second}};
  f.catalog.bindings[0].projectBindings.push(binding);
  assert.equal((await f.control.execute('/v1/chats/create',body)).visibility.workspace,canonical(second));
  binding.status='unbound';
  await assert.rejects(f.control.execute('/v1/chats/send',{workspace:second,nativeId:ID,requestId:'after-unbind',prompt:'stop'}),/hub_project_binding_missing/);
  assert.equal(f.events.filter(x=>x.name==='create_thread').length,1);
  assert.ok(!f.events.some(x=>x.name==='send_message_to_thread'));
});

test('Git metadata failure uses actual native project membership without trusting repository ownership', async t => {
  const f=fixture(t), original=f.host.call;
  f.host.call=async(name,args)=>{
    if(name==='list_projects') throw Error('Git is absent or optional metadata failed');
    return original(name,args);
  };
  const result=await f.control.execute('/v1/chats/create',{requestId:'no-git',workspace:f.root,prompt:'hello'});
  assert.equal(result.visibility.projectId,'native-project');
  assert.ok(!fs.existsSync(path.join(f.root,'.git')));
  assert.equal(f.events.filter(x=>x.name==='create_thread').length,1);
});

test('an unavailable native catalog is not reported as an absent project or guessed by name', async t => {
  const f=fixture(t);
  f.host.call=async(name)=>name==='list_projects'?{projects:[]}:{threads:[]};
  await assert.rejects(f.control.execute('/v1/chats/create',{requestId:'unknown',workspace:f.root,prompt:'hello'}),/native_catalog_unavailable/);
  assert.equal(Object.keys(f.journal.data.operations).length,0);
});

test('a changed binding is rechecked immediately before native mutation', async t => {
  const f=fixture(t), original=f.host.call;
  f.host.call=async(name,args)=>{
    const result=await original(name,args);
    if(name==='list_projects') f.catalog.bindings[0].projectBindings[0].revision++;
    return result;
  };
  await assert.rejects(f.control.execute('/v1/chats/create',{requestId:'changed',workspace:f.root,prompt:'hello'}),/hub_project_binding_changed/);
  assert.ok(!f.events.some(x=>x.name==='create_thread'));
});

test('Hub outage, revoked connection and ambiguous bindings fail closed before native calls', async t => {
  const f=fixture(t);
  f.bindings.load=async()=>{throw Error('offline');};
  await assert.rejects(f.control.execute('/v1/chats/create',{requestId:'offline',workspace:f.root,prompt:'hello'}),/hub_bindings_unavailable/);
  f.bindings.load=async()=>f.catalog;
  f.catalog.bindings[0].revoked=true;
  await assert.rejects(f.control.execute('/v1/chats/create',{requestId:'revoked',workspace:f.root,prompt:'hello'}),/hub_bindings_unavailable/);
  f.catalog.bindings[0].revoked=false;
  f.catalog.bindings[0].projectBindings.push({...f.catalog.bindings[0].projectBindings[0],id:'duplicate'});
  await assert.rejects(f.control.execute('/v1/chats/create',{requestId:'duplicate',workspace:f.root,prompt:'hello'}),/hub_project_binding_ambiguous/);
  assert.equal(f.events.length,0);
});

test('a legacy chat without Hub binding provenance cannot cross a later rebind', async t => {
  const f=fixture(t);
  f.journal.data.threads[ID]={root:canonical(f.root),projectId:'native-project'};
  f.catalog.bindings[0].projectBindings[0].project='another-hub-project';
  f.catalog.bindings[0].projectBindings[0].revision=2;
  await assert.rejects(f.control.execute('/v1/chats/send',{requestId:'legacy',workspace:f.root,nativeId:ID,prompt:'stop'}),/chat_not_owned/);
  assert.ok(!f.events.some(x=>x.name==='send_message_to_thread'));
});

test('cached creation cannot be reassigned by reusing its request after a Hub rebind', async t => {
  const f=fixture(t), body={requestId:'cached',workspace:f.root,prompt:'hello'};
  await f.control.execute('/v1/chats/create',body);
  f.catalog.bindings[0].projectBindings[0].project='another-hub-project';
  f.catalog.bindings[0].projectBindings[0].revision++;
  await assert.rejects(f.control.execute('/v1/chats/create',body),/request_id_conflict/);
  assert.equal(f.events.filter(x=>x.name==='create_thread').length,1);
});
