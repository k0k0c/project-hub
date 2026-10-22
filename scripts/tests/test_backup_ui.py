import subprocess
import textwrap
import unittest
from pathlib import Path


WEB = Path(__file__).resolve().parents[2] / "tools/project-portal/web/backups.js"


HARNESS = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(process.argv[1], 'utf8');

class Element {
  constructor(name, root) { this.name = name; this.root = root; this.disabled = false; this.hidden = false; this.value = ''; this.dataset = {}; this.files = []; this.listeners = {}; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  matches(selector) { return selector.includes('data-backup-' + this.name); }
  closest(selector) { return this.matches(selector) ? this : null; }
  dispatch(type, extra = {}) { for (const fn of this.listeners[type] || []) fn({target: this, currentTarget: this, ...extra}); }
}
class Root extends Element {
  constructor() { super('root', null); this.root = this; this.dataset = {}; this.html = ''; this.controls = {}; }
  set innerHTML(value) {
    this.html = value; this.controls = {};
    for (const name of ['status', 'progress', 'file', 'create', 'upload', 'retry']) this.controls[name] = new Element(name, this);
    const ids = [...value.matchAll(/data-backup-restore="([^"]+)"/g)].map(match => match[1]);
    this.controls.restore = ids.map(id => { const item = new Element('restore', this); item.dataset.backupRestore = id; return item; });
    this.controls.progress.max = 100;
  }
  get innerHTML() { return this.html; }
  querySelector(selector) {
    if (selector === '[data-backup-status]') return this.controls.status;
    if (selector === '[data-backup-progress]') return this.controls.progress;
    if (selector === '[data-backup-file]') return this.controls.file;
    if (selector === '[data-backup-create]') return this.controls.create;
    if (selector === '[data-backup-upload]') return this.controls.upload;
    if (selector === '[data-backup-retry]') return this.controls.retry;
    if (selector === '#backups-page') return this;
    if (selector.startsWith('[data-backup-restore')) return this.controls.restore[0] || null;
    return null;
  }
  querySelectorAll(selector) {
    if (selector.includes('data-backup-restore')) return this.controls.restore;
    return [this.controls.create].filter(Boolean);
  }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  emit(type, target) { return Promise.all((this.listeners[type] || []).map(fn => fn({target, currentTarget: this}))); }
}

function makeContext(responses) {
  const root = new Root(), calls = [], starts = [], acknowledgements=[], uncertainties=[];
  const response = body => ({ok: true, async json() { return body; }});
  const fetch = async (url, options = {}) => {
    calls.push({url, options, body: options.body ? JSON.parse(options.body) : null});
    const next = responses.shift();
    if (next instanceof Error) return {ok: false, status:500, async json() { return {error: next.message}; }};
    return response((typeof next === 'function' ? next(calls.at(-1)) : next) || {});
  };
  const context = {
    console, fetch, btoa: value => Buffer.from(value, 'binary').toString('base64'),
    Uint8Array, Date, Intl, URLSearchParams, encodeURIComponent, setTimeout,
    window: {confirm: () => true}, location: {hash: ''}, document: {querySelector: () => root}, clearTimeout,
    escape: value => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char])),
    uiIcon: () => '',
    backupStatus:{begin:body=>starts.push(body),acknowledge:(row,body)=>acknowledgements.push({row,body}),
      operationLink:row=>`#projects/backups/operation/${encodeURIComponent(row.id)}`,
      afterRender(){},refresh(){},uncertain:body=>uncertainties.push(body),reject(){}},
  };
  context.window.backupsPage = undefined;
  vm.createContext(context); vm.runInContext(source, context, {filename: 'backups.js'});
  return {context, root, calls, starts, acknowledgements, uncertainties};
}

async function emptyCatalogLoadsOnce() {
  const h = makeContext([{scope:'all-projects', backups:[], restoreCopies:[]}]);
  await h.context.window.bindBackups(h.root); await h.context.window.bindBackups(h.root);
  assert.equal(h.calls.filter(call => call.options.method === undefined).length, 1);
}

async function historicalUploadDoesNotReplaceCatalog() {
  const h = makeContext([{backups:[{id:'real',name:'project-hub-backup-e5943526301f.zip',size:354814185,projects:[]}], restoreCopies:[], jobs:[{id:'old-upload',action:'upload-complete',status:'succeeded',result:{id:'old',preview:{name:'stale-upload-name',totalBytes:1200000000,projects:[]}}},{id:'deleted',action:'delete-archive',status:'succeeded',result:{id:'real'}}]}]);
  await h.context.window.bindBackups(h.root);
  assert.match(h.root.html,/project-hub-backup-e5943526301f\.zip/);
  assert.doesNotMatch(h.root.html,/stale-upload-name/);
}

async function uploadUsesBoundedChunksAndCompletes() {
  const h = makeContext([{backups:[], restoreCopies:[], jobs:[]}, {id:'u1', offset:0}, {id:'u1', offset:524288}, {id:'u1', offset:614400}, {job:{id:'j1', action:'upload-complete', status:'queued', progress:{completed:0,total:1}}}, {job:{id:'j1', action:'upload-complete', status:'succeeded', result:{id:'u1', sha256:'abc', preview:{createdAt:'2026-01-01T00:00:00Z', projects:[]}}}}, {backups:[{id:'u1', name:'archive.zip', sha256:'abc', projects:[]}], restoreCopies:[], jobs:[]}]);
  await h.context.window.bindBackups(h.root);
  const bytes = 614400, file = {name:'archive.zip', size:bytes, slice(start, end) { return {async arrayBuffer() { return new Uint8Array(end - start).buffer; }}; }};
  h.root.controls.file.files = [file]; await h.root.emit('change', h.root.controls.file); await h.root.emit('click', h.root.controls.upload);
  const actions = h.calls.map(call => call.body?.action).filter(Boolean);
  assert.deepEqual(actions, ['upload-start', 'upload-chunk', 'upload-chunk', 'upload-complete']);
  const background = h.calls.find(call => call.body?.action === 'upload-complete');
  assert.equal(background.body.background, true); assert.equal(typeof background.body.requestId, 'string');
  assert.equal(background.body.origin.section,'backups');
  assert.equal(h.starts[0].action,'upload-start');assert.equal(h.starts[1].action,'upload-complete');
  assert.ok(h.acknowledgements.some(item=>item.row.action==='upload-start' && item.row.progress.completed===bytes));
  assert.equal(h.calls.some(call => String(call.url).includes('?job=j1')), true);
  const chunks = h.calls.filter(call => call.body?.action === 'upload-chunk').map(call => call.body.data);
  assert.equal(chunks.length, 2); assert.ok(Buffer.from(chunks[0], 'base64').length <= 512 * 1024); assert.ok(Buffer.from(chunks[1], 'base64').length <= 512 * 1024);
  assert.equal(h.root.html.includes('archive.zip'), true);
}

async function failedUploadAbortsAndPreservesError() {
  const h = makeContext([{backups:[], restoreCopies:[]}, {id:'u2', offset:0}, new Error('chunk failed'), new Error('abort failed')]);
  await h.context.window.bindBackups(h.root);
  const file = {name:'broken.zip', size:3, slice() { return {async arrayBuffer() { return new Uint8Array([1,2,3]).buffer; }}; }};
  h.root.controls.file.files = [file]; await h.root.emit('change', h.root.controls.file); await h.root.emit('click', h.root.controls.upload);
  assert.equal(h.calls.at(-1).body.action, 'upload-abort'); assert.equal(h.root.controls.status.textContent, 'chunk failed');
}

async function unknownCompletionKeepsTheUploadAndExactRetry() {
  let completionRequestId;
  const h=makeContext([{backups:[],restoreCopies:[],jobs:[]},{id:'u4',offset:0},{id:'u4',offset:3},
    call=>{completionRequestId=call.body.requestId;return {job:{id:'j4',action:'upload-complete',requestId:completionRequestId}};},
    call=>({job:{id:'j4',action:'upload-complete',requestId:call.body.requestId,status:'queued'}}),
    ()=>({job:{id:'j4',action:'upload-complete',requestId:completionRequestId,status:'succeeded',result:{id:'u4',sha256:'verified',preview:{createdAt:'2026-01-01T00:00:00Z',projects:[]}}}}),
    {backups:[{id:'u4',name:'retry.zip',sha256:'verified',projects:[]}],restoreCopies:[],jobs:[]}]);
  await h.context.window.bindBackups(h.root);
  const file={name:'retry.zip',size:3,slice(){return {async arrayBuffer(){return new Uint8Array([1,2,3]).buffer;}};}};
  h.root.controls.file.files=[file];await h.root.emit('change',h.root.controls.file);await h.root.emit('click',h.root.controls.upload);
  assert.deepEqual(h.calls.map(call=>call.body?.action).filter(Boolean),['upload-start','upload-chunk','upload-complete']);
  assert.match(h.root.controls.status.textContent,/Сервер не подтвердил операцию/);
  assert.equal(h.root.controls.retry.hidden,false);
  assert.equal(h.uncertainties.at(-1).requestId,completionRequestId);
  await h.root.emit('click',h.root.controls.retry);
  const completions=h.calls.filter(call=>call.body?.action==='upload-complete');
  assert.equal(completions.length,2);assert.deepEqual(completions[0].body,completions[1].body);
  assert.equal(h.calls.some(call=>call.body?.action==='upload-abort'),false);
  assert.ok(h.acknowledgements.some(item=>item.row.id==='j4' && item.row.status==='succeeded'));
  assert.equal(h.root.controls.retry.hidden,true);
}

async function acceptedVerificationFailureDoesNotAbortTransferredFiles() {
  const h=makeContext([{backups:[],restoreCopies:[],jobs:[]},{id:'u5',offset:0},{id:'u5',offset:3},
    {job:{id:'j5',action:'upload-complete',status:'queued'}},
    {job:{id:'j5',action:'upload-complete',status:'failed',error:'Archive verification failed'}}]);
  await h.context.window.bindBackups(h.root);
  const file={name:'rejected.zip',size:3,slice(){return {async arrayBuffer(){return new Uint8Array([1,2,3]).buffer;}};}};
  h.root.controls.file.files=[file];await h.root.emit('change',h.root.controls.file);await h.root.emit('click',h.root.controls.upload);
  assert.deepEqual(h.calls.map(call=>call.body?.action).filter(Boolean),['upload-start','upload-chunk','upload-complete']);
  assert.equal(h.root.controls.status.textContent,'Archive verification failed');
  assert.ok(h.acknowledgements.some(item=>item.row.id==='j5' && item.row.status==='failed'));
  assert.ok(h.acknowledgements.some(item=>item.row.action==='upload-start' && item.row.status==='succeeded'));
  assert.equal(h.acknowledgements.some(item=>item.row.action==='upload-start' && item.row.status==='failed'),false);
}

async function progressFollowsRemountedRoute() {
  const running = {id:'j3', action:'create', status:'running', phase:'snapshot', progress:{completed:1,total:10}};
  const h = makeContext([{backups:[], restoreCopies:[], jobs:[running]}, {job:{...running, progress:{completed:6,total:10}}}, {job:{...running,status:'succeeded',result:{}}}]);
  await h.context.window.bindBackups(h.root);
  h.root.isConnected = false;
  const reopened = new Root();
  await h.context.window.bindBackups(reopened);
  await h.context.pollBackupJob(running, h.root);
  assert.ok(reopened.html.includes('6 из 10'));
  assert.ok(!h.root.html.includes('6 из 10'));
  // Finish the fixture operation so its real timer does not keep Node alive.
  await h.context.pollBackupJob(running, reopened);
}

async function restoreResultSurvivesRender() {
  const h = makeContext([{backups:[{id:'b1', name:'one', sha256:'hash', projects:[]}], restoreCopies:[], jobs:[]}, {job:{id:'j2', action:'restore-copy', status:'queued', progress:{completed:0,total:1}}}, {job:{id:'j2', action:'restore-copy', status:'succeeded', result:{path:'C:/internal-preparation', copyId:'prepared-source',projectCount:1, active:false}}}, {backups:[{id:'b1', name:'one', sha256:'hash', projects:[]}], restoreCopies:[{path:'C:/internal-preparation', projectCount:1, active:false}], jobs:[]}]);
  await h.context.window.bindBackups(h.root); await h.root.emit('click', h.root.controls.restore[0]);
  assert.equal(h.calls.find(call=>call.body?.action==='restore-copy').body.confirmed,true);
  assert.ok(h.context.location.hash.includes('projects/data/import/prepared-source')); assert.ok(!h.root.html.includes('data-project-tab="data"'));
  assert.ok(!h.root.html.includes('C:/internal-preparation'),'Temporary preparation is not offered as another active store');
  assert.ok(!h.root.html.includes('ZIP подготовлен к импорту'));
  assert.ok(!h.root.html.includes('backup-restore-copies'), 'Prepared storage has one location in Hub data');
}

(async () => { await emptyCatalogLoadsOnce(); await historicalUploadDoesNotReplaceCatalog(); await uploadUsesBoundedChunksAndCompletes(); await failedUploadAbortsAndPreservesError(); await unknownCompletionKeepsTheUploadAndExactRetry(); await acceptedVerificationFailureDoesNotAbortTransferredFiles(); await restoreResultSurvivesRender(); await progressFollowsRemountedRoute(); })().catch(error => { console.error(error); process.exitCode = 1; });
'''


class BackupUiTest(unittest.TestCase):
    def test_backup_behavior_with_minimal_browser_harness(self):
        result = subprocess.run(
            ["node", "-e", HARNESS, str(WEB)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
