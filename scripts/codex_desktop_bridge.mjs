/** Experimental, session-scoped adapter to the running Codex app tools host.
 * The pipe and caller identity must be inherited from Codex. Never discover
 * private pipes, attach to stdio, modify Codex storage, or expose arbitrary tools.
 */
import net from 'node:net';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';

const LIMIT = 2 * 1024 * 1024;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
const stable = value => object(value) ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) :
  Array.isArray(value) ? value.map(stable) : value;
export class BridgeError extends Error {
  constructor(code, status = 409) { super(code); this.code = code; this.status = status; }
}
function text(value, max = 128) {
  if (typeof value !== 'string' || !value.trim() || value.length > max) throw new BridgeError('invalid_request', 400);
  return value;
}
function fields(value, allowed, required = allowed) {
  if (!object(value) || Object.keys(value).some(key => !allowed.includes(key)) || required.some(key => !(key in value))) {
    throw new BridgeError('invalid_request', 400);
  }
}
export function canonical(root) {
  const real = fs.realpathSync(text(root, 4096));
  if (!fs.statSync(real).isDirectory()) throw new BridgeError('workspace_unavailable');
  return process.platform === 'win32' ? real.toLowerCase() : real;
}

export class NativeHost {
  constructor(pipe, caller, {timeout = 9000} = {}) {
    if (!UUID.test(caller || '') || !pipe) throw new BridgeError('codex_environment_required');
    this.pipe = pipe; this.caller = caller; this.timeout = timeout;
    this.next = 0; this.pending = new Map(); this.buffer = Buffer.alloc(0);
    this.socket = null; this.connecting = null; this.tools = null;
  }
  async connect() {
    if (this.socket && !this.socket.destroyed) return;
    if (this.connecting) return this.connecting;
    this.connecting = new Promise((resolve, reject) => {
      const socket = net.createConnection(this.pipe);
      const timer = setTimeout(() => socket.destroy(new Error('timeout')), this.timeout);
      socket.once('error', () => reject(new BridgeError('codex_host_unavailable', 503)));
      socket.once('connect', () => {clearTimeout(timer); this.socket = socket; resolve();});
      socket.on('data', data => {if (this.socket === socket) this.receive(data);});
      socket.on('error', () => {if (this.socket === socket) this.disconnected();});
      socket.on('close', () => {clearTimeout(timer); if (this.socket === socket) this.disconnected();});
    }).finally(() => {this.connecting = null;});
    return this.connecting;
  }
  disconnected() {
    const connected = !!this.socket;
    this.socket = null; this.buffer = Buffer.alloc(0); this.tools = null;
    for (const item of this.pending.values()) {clearTimeout(item.timer); item.reject(new BridgeError('codex_outcome_unknown', 503));}
    this.pending.clear();
    if (connected) this.onUnavailable?.();
  }
  receive(data) {
    this.buffer = Buffer.concat([this.buffer, data]);
    while (this.buffer.length >= 4) {
      const length = this.buffer.readUInt32LE(0);
      if (length > LIMIT) {this.close(); return;}
      if (this.buffer.length < length + 4) return;
      let reply;
      try {reply = JSON.parse(this.buffer.subarray(4, length + 4).toString('utf8'));}
      catch {this.close(); return;}
      this.buffer = this.buffer.subarray(length + 4);
      const item = this.pending.get(reply.id);
      if (!item) continue;
      this.pending.delete(reply.id); clearTimeout(item.timer);
      if (reply.error || !('result' in reply)) item.reject(new BridgeError('codex_host_rejected'));
      else item.resolve(reply.result);
    }
  }
  async request(method, params) {
    await this.connect();
    const id = ++this.next;
    const payload = Buffer.from(JSON.stringify({jsonrpc:'2.0', id, method, params}));
    if (payload.length > LIMIT) throw new BridgeError('request_too_large', 413);
    const header = Buffer.alloc(4); header.writeUInt32LE(payload.length);
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id); reject(new BridgeError('codex_outcome_unknown', 504));
      }, this.timeout);
      this.pending.set(id, {resolve, reject, timer});
      this.socket.write(Buffer.concat([header, payload]), error => {
        if (error) this.disconnected();
      });
    });
  }
  async discover() {
    const result = await this.request('tools/list', {threadStartKind:'all'});
    const required = {list_projects:[], list_threads:[], read_thread:['threadId'],
      create_thread:['prompt','target'], send_message_to_thread:['threadId','prompt']};
    for (const [name, params] of Object.entries(required)) {
      const tool = result.tools?.find(item => item.name === name && item.namespace === 'codex_app');
      if (!tool || params.some(key => !tool.inputSchema?.properties?.[key])) throw new BridgeError('codex_protocol_changed', 503);
    }
    this.tools = new Set(Object.keys(required));
  }
  async call(name, args) {
    if (!this.tools) await this.discover();
    if (!this.tools.has(name)) throw new BridgeError('tool_not_allowed', 403);
    const value = await this.request('tools/call', {namespace:'codex_app', tool:name, arguments:args,
      callerSource:'codex', threadId:this.caller, callId:'hub-bridge-' + crypto.randomUUID(),
      turnId:'hub-bridge-' + crypto.randomUUID()});
    if (value.success !== true) throw new BridgeError(name + '_rejected');
    for (const item of value.contentItems || []) {
      if (item.type !== 'inputText') continue;
      try {const parsed = JSON.parse(item.text); if (object(parsed)) return parsed;} catch {}
    }
    throw new BridgeError('codex_protocol_changed', 503);
  }
  async project(workspace) {
    // list_projects is a presentation projection: some Codex versions omit a
    // project when optional Git metadata fails. Actual thread membership is
    // independent evidence of the native project, including non-Git folders.
    let listing;
    try { listing = await this.call('list_projects', {}); } catch { listing = {projects:[]}; }
    let matches = (listing.projects || []).filter(item => {
      if (item.projectKind !== 'local' || item.hostId !== 'local' || !item.path) return false;
      try {return canonical(item.path) === workspace;} catch {return false;}
    });
    if (!matches.length) {
      try {
        const threads = await this.call('list_threads', {limit:50});
        const ids = new Set();
        for (const item of [...(threads.threads || []), ...(threads.pinnedThreads || [])]) {
          if (item.hostId !== 'local' || !item.projectId || !item.cwd) continue;
          try {if (canonical(item.cwd) === workspace) ids.add(text(item.projectId));} catch {}
        }
        matches = [...ids].map(projectId => ({projectId}));
      } catch (error) {
        if (['codex_host_unavailable','codex_host_rejected','codex_outcome_unknown','codex_protocol_changed'].includes(error.code)) throw error;
        throw new BridgeError('native_catalog_unavailable', 503);
      }
    }
    if (!matches.length) throw new BridgeError('native_catalog_unavailable', 409);
    if (matches.length !== 1) throw new BridgeError('native_project_ambiguous', 409);
    return text(matches[0].projectId);
  }
  close() {this.socket?.destroy(); this.disconnected();}
}

/** The current Hub binding is the authority; no separately saved folder grants. */
export class HubBindings {
  constructor(base, connection, {load} = {}) {
    const url = new URL(base);
    if (url.protocol !== 'http:' || url.hostname !== '127.0.0.1' || !url.port ||
        url.username || url.password || url.search || url.hash || !['','/'].includes(url.pathname)) {
      throw new BridgeError('invalid_hub_address', 400);
    }
    this.base = url.origin; this.connection = text(connection);
    this.load = load || (() => new Promise((resolve, reject) => {
      const request = http.get(this.base + '/api/connections', {headers:{Accept:'application/json'}}, response => {
        if (response.statusCode !== 200) {response.resume(); reject(new BridgeError('hub_bindings_unavailable', 503)); return;}
        const chunks = []; let size = 0;
        response.on('data', chunk => {
          size += chunk.length;
          if (size > LIMIT) {response.destroy(); reject(new BridgeError('hub_bindings_unavailable', 503));}
          else chunks.push(chunk);
        });
        response.on('error', () => reject(new BridgeError('hub_bindings_unavailable', 503)));
        response.on('end', () => {try {resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')));} catch {reject(new BridgeError('hub_bindings_unavailable', 503));}});
      });
      request.setTimeout(3000, () => request.destroy());
      request.on('error', () => reject(new BridgeError('hub_bindings_unavailable', 503)));
    }));
  }
  async connectionRecord() {
    let catalog;
    try {catalog = await this.load();} catch {throw new BridgeError('hub_bindings_unavailable', 503);}
    if (!Array.isArray(catalog?.bindings)) throw new BridgeError('hub_bindings_unavailable', 503);
    const connections = catalog.bindings.filter(item => item?.id === this.connection);
    if (connections?.length !== 1 || connections[0].revoked || connections[0].client !== 'codex' ||
        !Array.isArray(connections[0].projectBindings)) throw new BridgeError('hub_bindings_unavailable', 503);
    return connections[0];
  }
  async list() {
    return (await this.connectionRecord()).projectBindings.filter(item => item.status === 'active' && !item.pendingRelocation);
  }
  async authorizeContinuation(args, project, replay = false) {
    const connection = await this.connectionRecord();
    const launch = connection.launches?.find(item => item.requestId === args.requestId);
    const envelope = launch?.envelope, source = launch?.continuationSource;
    if (!launch || (launch.status !== 'dispatching' && !replay) ||
        ['routing_conflict','cancelled'].includes(launch.status) ||
        launch.dispatchPromptSha256 !== hash(args.prompt) ||
        launch.targetNativeId !== args.nativeId || source?.kind !== 'task-chat' || source.nativeId !== args.nativeId ||
        envelope?.connection !== this.connection || envelope.operation !== 'task-execute' ||
        envelope.project !== project.hubProject || envelope.bindingId !== project.bindingId ||
        envelope.bindingRevision !== project.bindingRevision || !['workspace','project'].includes(envelope.projectScope?.kind) ||
        !envelope.projectScope.root || canonical(envelope.projectScope.root) !== project.root ||
        (envelope.projectScope.nativeRef || null) !== (project.nativeRef || null) ||
        !source.task || envelope.inputs?.task?.id !== source.task ||
        envelope.resultDestination?.kind !== 'task-report' || envelope.resultDestination.project !== project.hubProject ||
        envelope.resultDestination.task !== source.task || (envelope.resultDestination.stage || null) !== (source.stage || null)) {
      throw new BridgeError('chat_not_owned', 403);
    }
  }
  async resolve(workspace) {
    let root;
    try {root = canonical(workspace);} catch {throw new BridgeError('hub_project_binding_missing', 403);}
    const matches = (await this.list()).filter(item => {
      try {return item.scope?.root && canonical(item.scope.root) === root;} catch {return false;}
    });
    if (!matches.length) throw new BridgeError('hub_project_binding_missing', 403);
    if (matches.length !== 1) throw new BridgeError('hub_project_binding_ambiguous', 409);
    const binding = matches[0];
    if (!Number.isInteger(binding.revision) || binding.revision < 1) throw new BridgeError('hub_bindings_unavailable', 503);
    return {root, bindingId:text(binding.id), bindingRevision:binding.revision,
      hubProject:text(binding.project), ...(binding.scope.nativeRef ? {nativeRef:text(binding.scope.nativeRef, 256)} : {})};
  }
  async validate(context) {
    const current = await this.resolve(context.root);
    if (JSON.stringify(stable(current)) !== JSON.stringify(stable(Object.fromEntries(
      Object.entries(context).filter(([key]) => key !== 'projectId'))))) throw new BridgeError('hub_project_binding_changed', 409);
  }
}

/** Reservation is durable before mutation. Unknown outcomes never replay. */
export class Journal {
  constructor(filename, instance) {
    this.filename = filename;
    this.data = fs.existsSync(filename) ? JSON.parse(fs.readFileSync(filename, 'utf8')) :
      {version:1, instance, operations:{}, threads:{}};
    if (this.data.version !== 1 || this.data.instance !== instance || !object(this.data.operations) || !object(this.data.threads)) {
      throw new BridgeError('bridge_instance_changed');
    }
    this.inflight = new Map();
  }
  save() {
    fs.mkdirSync(path.dirname(this.filename), {recursive:true});
    const temporary = this.filename + '.' + crypto.randomUUID() + '.tmp';
    const fd = fs.openSync(temporary, 'wx', 0o600);
    try {fs.writeFileSync(fd, JSON.stringify(this.data)); fs.fsyncSync(fd);} finally {fs.closeSync(fd);}
    fs.renameSync(temporary, this.filename);
  }
  async run(kind, args, action) {
    text(args.requestId); if (!/^[A-Za-z0-9_.:-]+$/.test(args.requestId)) throw new BridgeError('invalid_request', 400);
    const key = kind + ':' + args.requestId, fingerprint = hash(JSON.stringify(stable(args)));
    const prior = this.data.operations[key];
    if (prior) {
      if (prior.fingerprint !== fingerprint) throw new BridgeError('request_id_conflict');
      if (this.inflight.has(key)) return this.inflight.get(key);
      if (prior.status === 'done') return prior.result;
      throw new BridgeError('prior_outcome_requires_reconciliation');
    }
    if (Object.keys(this.data.operations).length >= 10000) throw new BridgeError('bridge_journal_full');
    this.data.operations[key] = {fingerprint, status:'dispatching', at:Date.now()}; this.save();
    const operation = (async () => {
      try {
        const result = await action(this.data.operations[key]);
        this.data.operations[key] = {fingerprint, status:'done', result, at:Date.now()}; this.save();
        return result;
      } catch (error) {
        Object.assign(this.data.operations[key], {status:'outcome_unknown',
          error:error instanceof BridgeError ? error.code : 'bridge_unavailable'});
        this.save(); throw error;
      }
    })();
    this.inflight.set(key, operation);
    try {return await operation;} finally {this.inflight.delete(key);}
  }
}

export function acquireLock(filename) {
  // Publish a complete PID record exclusively; a crash cannot leave an empty
  // lock which the setup process cannot safely reconcile.
  const temporary = filename + '.' + crypto.randomUUID() + '.tmp';
  const fd = fs.openSync(temporary, 'wx', 0o600);
  try {fs.writeFileSync(fd, JSON.stringify({pid:process.pid})); fs.fsyncSync(fd);}
  finally {fs.closeSync(fd);}
  try {fs.linkSync(temporary, filename);} finally {fs.unlinkSync(temporary);}
}

export class DesktopControl {
  constructor(host, journal, bindings, {verificationTimeout = 18000, verificationInterval = 500} = {}) {
    this.host = host; this.journal = journal; this.bindings = bindings;
    this.verificationTimeout = verificationTimeout; this.verificationInterval = verificationInterval;
    if (!bindings || typeof bindings.resolve !== 'function') throw new BridgeError('hub_bindings_required');
    this.serial = Promise.resolve();
  }
  async ready() {
    await this.host.discover();
    const own = await this.host.call('read_thread', {threadId:this.host.caller, turnLimit:1, includeOutputs:false, maxOutputCharsPerItem:0});
    if (own.thread?.id !== this.host.caller || own.thread?.hostId !== 'local') throw new BridgeError('local_codex_caller_required');
    const projects = await this.bindings.list();
    return {status:'ready', experimental:true, callerNativeId:this.host.caller,
      instance:this.journal.data.instance, projectRouting:'hub-project-bindings',
      projectBindings:projects.map(item => ({id:item.id, revision:item.revision, project:item.project, scope:item.scope}))};
  }
  async project(workspace) {
    const context = await this.bindings.resolve(workspace);
    const projectId = await NativeHost.prototype.project.call(this.host, context.root);
    if (context.nativeRef && context.nativeRef !== projectId) throw new BridgeError('native_project_ambiguous', 409);
    await this.bindings.validate(context);
    return {...context, projectId};
  }
  async verify(nativeId, project, existing = false) {
    if (!UUID.test(nativeId || '')) throw new BridgeError('invalid_native_id', 400);
    // A new chat can be visible before its transcript/rollout becomes readable.
    // The app's own catalogue independently proves its presence and project;
    // requiring read_thread here would turn that normal state into a failure.
    const deadline = Date.now() + this.verificationTimeout;
    do {
      const listing = await this.host.call('list_threads', {limit:50});
      const found = [...(listing.threads || []), ...(listing.pinnedThreads || [])].find(item => item.id === nativeId && item.hostId === 'local');
      if (found?.projectId && found?.cwd) {
        if (found.projectId !== project.projectId || canonical(found.cwd) !== project.root) throw new BridgeError('native_chat_not_visible_in_project');
        await this.bindings.validate(project);
        return {state:'verified', nativeId, projectId:project.projectId, workspace:project.root,
          method:'codex_app.list_threads', verifiedAt:new Date().toISOString(), guiOpened:false};
      }
      if (existing) {
        // Source chats can be older than the recent catalogue. Read the exact
        // requested identity; never search rollouts or guess by title.
        const {thread} = await this.host.call('read_thread', {threadId:nativeId, turnLimit:1,
          includeOutputs:false, maxOutputCharsPerItem:0});
        if (thread?.id !== nativeId || thread.hostId !== 'local' || !thread.cwd ||
            canonical(thread.cwd) !== project.root || thread.projectId && thread.projectId !== project.projectId) {
          throw new BridgeError('native_chat_not_visible_in_project');
        }
        await this.bindings.validate(project);
        return {state:'verified', nativeId, projectId:project.projectId, workspace:project.root,
          method:'codex_app.read_thread+list_threads', verifiedAt:new Date().toISOString(), guiOpened:false};
      }
      if (Date.now() >= deadline) break;
      await new Promise(resolve => setTimeout(resolve, Math.min(this.verificationInterval, deadline - Date.now())));
    } while (Date.now() <= deadline);
    throw new BridgeError('native_chat_not_visible_in_project');
  }
  async perform(route, args) {
    if (route === '/v1/chats/verify') {
      fields(args, ['nativeId','workspace']);
      const project = await this.project(args.workspace);
      if (!this.owns(args.nativeId, project)) throw new BridgeError('chat_not_owned', 403);
      return this.verify(args.nativeId, project);
    }
    const create = route === '/v1/chats/create';
    if (!create && route !== '/v1/chats/send') throw new BridgeError('route_not_found', 404);
    fields(args, create ? ['requestId','workspace','prompt','title'] : ['requestId','workspace','prompt','nativeId'],
      create ? ['requestId','workspace','prompt'] : ['requestId','workspace','prompt','nativeId']);
    text(args.prompt, 64000); if (args.title !== undefined) text(args.title, 200);
    const project = await this.project(args.workspace);
    const related = !create && !this.owns(args.nativeId, project);
    const authorize = () => this.bindings.authorizeContinuation(args, project,
      this.journal.data.operations['send:' + args.requestId]?.status === 'done');
    if (related) await authorize();
    // A cached success belongs to the original Hub authority as well as the
    // request payload. Rebinding the same folder cannot reuse an old chat.
    return this.journal.run(create ? 'create' : 'send', {...args, projectBinding:project}, async record => {
      let nativeId = args.nativeId;
      await this.bindings.validate(project);
      if (create) {
        const result = await this.host.call('create_thread', {prompt:args.prompt,
          ...(args.title ? {title:args.title} : {}), target:{type:'project', projectId:project.projectId, environment:{type:'local'}}});
        nativeId = result.threadId;
        if (!UUID.test(nativeId || '') || result.hostId !== 'local') throw new BridgeError('codex_creation_outcome_unknown');
        record.nativeId = nativeId;
        this.journal.data.threads[nativeId] = project; this.journal.save();
      } else {
        await this.verify(nativeId, project, related);
        await this.bindings.validate(project);
        if (related) await authorize();
        await this.host.call('send_message_to_thread', {threadId:nativeId, hostId:'local', prompt:args.prompt});
      }
      const visibility = await this.verify(nativeId, project, related);
      return {id:nativeId, url:'codex://threads/' + nativeId, status:create ? 'created' : 'accepted', visibility,
        experimental:true};
    });
  }
  execute(route, args) {
    // Serialize native mutations so two HTTP requests cannot race ownership checks.
    const job = this.serial.then(() => this.perform(route, args));
    this.serial = job.catch(() => {}); return job;
  }
  owns(nativeId, project) {
    const owner = this.journal.data.threads[nativeId];
    return owner?.root === project.root && owner.projectId === project.projectId &&
      owner.bindingId === project.bindingId && owner.bindingRevision === project.bindingRevision && owner.hubProject === project.hubProject;
  }
}

export function serve(control, credential, port = 0) {
  if (typeof credential !== 'string' || credential.length < 32) throw new BridgeError('bridge_key_required');
  const server = http.createServer(async (request, response) => {
    const reply = (status, body) => {
      response.writeHead(status, {'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});
      response.end(JSON.stringify(body));
    };
    try {
      if (request.headers.origin || request.headers.host !== `127.0.0.1:${server.address().port}` ||
          !crypto.timingSafeEqual(Buffer.from(hash(request.headers.authorization || '')), Buffer.from(hash('Bearer ' + credential)))) {
        return reply(403, {error:'bridge_access_denied'});
      }
      if (request.method === 'GET' && request.url === '/v1/health') return reply(200, await control.ready());
      if (request.method !== 'POST') return reply(405, {error:'method_not_allowed'});
      if (request.headers['content-type']?.split(';')[0] !== 'application/json') return reply(415, {error:'json_required'});
      let total = 0, chunks = [];
      for await (const chunk of request) {
        total += chunk.length; if (total > 131072) throw new BridgeError('request_too_large', 413); chunks.push(chunk);
      }
      let args; try {args = JSON.parse(Buffer.concat(chunks).toString('utf8'));} catch {throw new BridgeError('invalid_json', 400);}
      reply(200, await control.execute(request.url, args));
    } catch (error) {
      // No upstream errors, prompts, pipe paths or credentials cross the boundary.
      reply(error instanceof BridgeError ? error.status : 503, {error:error instanceof BridgeError ? error.code : 'bridge_unavailable'});
    }
  });
  server.requestTimeout = 15000; server.headersTimeout = 5000;
  server.maxConnections = 16; server.listen(port, '127.0.0.1');
  return server;
}

async function main() {
  const argv = process.argv.slice(2); let state, hub, connection;
  for (let i = 0; i < argv.length; i += 2) {
    if (argv[i] === '--state') state = argv[i+1];
    else if (argv[i] === '--hub-url') hub = argv[i+1];
    else if (argv[i] === '--connection') connection = argv[i+1];
    else throw new BridgeError('invalid_startup_arguments');
  }
  if (!state) throw new BridgeError('state_file_required');
  fs.mkdirSync(path.dirname(state), {recursive:true});
  // Refuse concurrent writers and stale locks after a crash. Reconciliation is
  // explicit; never discard durable unknown outcomes just to restart.
  const lock = state + '.lock';
  acquireLock(lock);
  process.once('exit', () => {try {fs.unlinkSync(lock);} catch {}});
  const pipe = process.env.CODEX_APP_TOOLS_PIPE_PATH, caller = process.env.CODEX_THREAD_ID;
  const host = new NativeHost(pipe, caller);
  const instance = hash(String(pipe) + '\n' + String(caller));
  const control = new DesktopControl(host, new Journal(state, instance), new HubBindings(hub, connection));
  await control.ready();
  const server = serve(control, process.env.PROJECT_HUB_CODEX_BRIDGE_KEY);
  server.once('listening', () => process.stdout.write(JSON.stringify({endpoint:`http://127.0.0.1:${server.address().port}`,
    pid:process.pid, instance, callerNativeId:caller, experimental:true}) + '\n'));
  let closing = false;
  const close = () => {
    if (closing) return; closing = true; host.onUnavailable = null;
    host.close(); server.close(); server.closeIdleConnections?.();
  };
  host.onUnavailable = close;
  process.once('SIGTERM', close); process.once('SIGINT', close);
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => {process.stderr.write('Codex Desktop bridge: ' + (error instanceof BridgeError ? error.code : 'startup_failed') + '\n'); process.exit(1);});
}
