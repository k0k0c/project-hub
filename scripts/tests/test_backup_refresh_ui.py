import subprocess
import textwrap
import unittest
from pathlib import Path


WEB = Path(__file__).resolve().parents[2] / "tools/project-portal/web/backups.js"


HARNESS = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const source = fs.readFileSync(process.argv[1], 'utf8');

class Element {
  constructor(name, root) { this.name = name; this.root = root; this.dataset = {}; this.files = []; this.listeners = {}; this.id = ''; this.scrollTop = 0; this.scrollLeft = 0; this.selectionStart = 0; this.selectionEnd = 0; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  matches(selector) { return selector.includes('data-backup-' + this.name); }
  closest(selector) { return this.matches(selector) ? this : null; }
  focus() { this.root.document.activeElement = this; }
  setSelectionRange(start, end, direction) { this.selectionStart = start; this.selectionEnd = end; this.selectionDirection = direction; }
  replaceWith(node) { this.root.controls.file = node; node.root = this.root; }
}
class Root extends Element {
  constructor(document) { super('root', null); this.root = this; this.document = document; this.isConnected = true; this.controls = {}; this.html = ''; this.scrollTop = 0; this.scrollLeft = 0; }
  contains(node) { return node?.root === this; }
  set innerHTML(value) {
    this.html = value;
    const file = new Element('file', this), old = this.controls.file;
    if (old?.files?.length) file.files = [];
    this.controls = {status:new Element('status', this), progress:new Element('progress', this), file, create:new Element('create', this), upload:new Element('upload', this)};
    const ids = [...value.matchAll(/data-backup-restore="([^"]+)"/g)].map(match => match[1]);
    this.controls.restore = ids.map(id => { const item = new Element('restore', this); item.dataset.backupRestore = id; return item; });
  }
  get innerHTML() { return this.html; }
  querySelector(selector) {
    if (selector === '[data-backup-status]') return this.controls.status;
    if (selector === '[data-backup-progress]') return this.controls.progress;
    if (selector === '[data-backup-file]') return this.controls.file;
    if (selector === '[data-backup-create]') return this.controls.create;
    if (selector === '[data-backup-upload]') return this.controls.upload;
    if (selector === '#backups-page') return this;
    return this.controls.restore?.[0] || null;
  }
  querySelectorAll(selector) { return selector.includes('data-backup-restore') ? (this.controls.restore || []) : [this.controls.create]; }
  addEventListener(type, fn) { (this.listeners[type] ||= []).push(fn); }
  async emit(type, target) { for (const fn of this.listeners[type] || []) await fn({target, currentTarget:this}); }
}

const document = {activeElement:null, querySelector:() => null};
const root = new Root(document), responses = [{backups:[], restoreCopies:[], jobs:[{id:'j1', action:'create', status:'running', progress:{completed:1,total:2}}]}, {job:{id:'j1', action:'create', status:'succeeded', progress:{completed:2,total:2}}}];
const fetch = async () => ({ok:true, async json() { return responses.shift() || {}; }});
const context = {console, fetch, Date, Intl, URLSearchParams, encodeURIComponent, setTimeout, clearTimeout, document, scrollX:0, scrollY:0, scrollTo:(x,y) => { context.scrollX=x; context.scrollY=y; }, window:{confirm:() => true}, uiIcon:() => '', escape:value => String(value)};
vm.createContext(context); vm.runInContext(source, context, {filename:'backups.js'});

(async () => {
  await context.window.bindBackups(root);
  const file = root.controls.file; const uploaded = {name:'keep.zip', size:1}; file.files = [uploaded];
  await root.emit('change', file); document.activeElement = file; root.scrollTop = 137; root.scrollLeft = 9;
  await context.pollBackupJob({id:'j1', action:'create', status:'running', progress:{completed:1,total:2}}, root);
  assert.strictEqual(root.controls.file, file, 'polling must retain the actual file input node');
  assert.deepStrictEqual(root.controls.file.files, [uploaded], 'polling must retain the selected FileList');
  assert.strictEqual(document.activeElement, file, 'polling must restore focus');
  assert.strictEqual(root.scrollTop, 137, 'polling must preserve vertical scroll');
  assert.strictEqual(root.scrollLeft, 9, 'polling must preserve horizontal scroll');
})().catch(error => { console.error(error); process.exitCode = 1; });
'''


class BackupRefreshUiTest(unittest.TestCase):
    def test_polling_preserves_upload_control_and_view_state(self):
        result = subprocess.run(
            ["node", "-e", HARNESS, str(WEB)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
