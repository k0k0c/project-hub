"""Exercise the standalone classic script against the actual app helpers in Node."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "tools/project-portal/web"


@unittest.skipUnless(shutil.which("node"), "Node is required for UI tests")
class TaskTableTests(unittest.TestCase):
    def run_js(self, assertions, with_filters=False):
        app = (WEB / "app.js").read_text(encoding="utf-8")
        helpers = app[:app.index("document.addEventListener('click'")]
        helpers += app[app.index("function estimate("):app.index("function currentWorkSummary(")]
        if with_filters:
            helpers += app[app.index("function tasksPage()"):app.index("function taskSearchCorpus(")]
        script = """
const assert = require('node:assert/strict');
const vm = require('node:vm');
const handlers = {}, storage = new Map();
const document = {addEventListener: (name, fn) => handlers[name] = fn,
  createElementNS: () => ({setAttribute(){},appendChild(){},outerHTML:'<svg class="ui-icon"></svg>'}),
  querySelector: () => null, querySelectorAll: () => [], activeElement: null};
const sandbox = {URL, URLSearchParams, document, handlers, window: {},
 taskResults:()=>'<table>updated</table>', compareTasks:()=>0,
 replacePreservingScroll:(selector,html)=>{sandbox.lastReplacement = {selector,html};},
 location: {search: '?project=one', hash: '#tasks', origin:'http://localhost', href:'http://localhost/#tasks'},
 localStorage: {getItem:key => storage.get(key), setItem:(key,value) => storage.set(key,value)}, assert};
vm.createContext(sandbox);
"""
        script += "vm.runInContext(" + json.dumps((WEB / "vendor/lucide.js").read_text(encoding="utf-8")) + ", sandbox);\n"
        script += "vm.runInContext(" + json.dumps(helpers) + ", sandbox);\n"
        script += "vm.runInContext(" + json.dumps((WEB / "task-table.js").read_text(encoding="utf-8")) + ", sandbox);\n"
        script += """
vm.runInContext(`state = {project:{baselineAt:'2026-01-01'}, mainTask:{task:'root'}};
function entry(id, parentTask = null) {return {task:{id, parentTask, title:id,
 summary:'Summary <unsafe>', type:'task', status:'active', stages:[]}, fields:[]};}
`, sandbox);
"""
        script += "vm.runInContext(" + json.dumps(assertions) + ", sandbox);"
        result = subprocess.run(["node", "-"], input=script, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_hierarchy_collapse_filter_and_cycles(self):
        self.run_js("""
const entries = [entry('root'),entry('child','root'),entry('grand','child')];
let html = renderTaskTable(entries, [], () => '');
assert.match(html, /data-tree-task="child" data-tree-depth="1" >/);
assert.match(html, /data-tree-task="grand" data-tree-depth="2" hidden/);
treeExpanded.delete('root'); window.saveTaskTreeState();
html = renderTaskTable(entries, [], () => '');
assert.match(html, /data-tree-task="child" data-tree-depth="1" hidden/);
assert.match(renderTaskTable([entries[1]],[],()=>''), /data-tree-task="child" data-tree-depth="0" >/);
html = renderTaskTable([entry('a','b'),entry('b','a')], [], () => '');
assert.equal((html.match(/data-tree-task=/g)||[]).length, 2);
assert.match(html, /data-tree-toggle=/);
""")

    def test_all_task_status_filters_match_badges_and_select_exact_status(self):
        self.run_js(r"""
const statuses = ['planned','active','queued','blocked','done','cancelled'];
state.tasks = statuses.map(id => ({...entry(id).task, status:id}));
for (const id of statuses) {
 taskFilter = id;
 const page = tasksPage();
 const filter = page.match(/<select id="task-status-filter"[^>]*>(.*?)<\/select>/)[1];
 assert.ok(filter.includes(`<option value="${id}" selected>${labels[id]}</option>`), id);
 assert.ok(status(id).includes(labels[id]), id);
 const result = taskResults();
 assert.match(result, /Найдено задач: 1\./);
 assert.ok(result.includes(`data-tree-task="${id}"`), id);
 for (const other of statuses.filter(value => value !== id)) assert.ok(!result.includes(`data-tree-task="${other}"`));
}
taskFilter = 'all';
assert.match(taskResults(), /Найдено задач: 6\./);
assert.ok(tasksPage().includes('>Предстоит</option>'));
assert.ok(tasksPage().includes('>Есть препятствие</option>'));
""", with_filters=True)

    def test_complete_metadata_and_escaping(self):
        self.run_js("""
const row = entry('root');
Object.assign(row.task, {title:'<img onerror="bad">', type:'epic',priority:'minor',maxDescendantPriority:'blocker',
 children:['child'], stages:[{title:'Stage',status:'done'}],progressAggregate:{done:3,total:4,percent:75},
 estimate:{percentLow:20,percentHigh:40,hoursLow:0,hoursHigh:2},updatedAt:'2026-02-01'});
const html = renderTaskTable([row], [], () => '');
for (const text of ['Epic','Minor','Потомки: Blocker','3 / 4','75%','20','40','2 ч','data-primary-task',
 'data-copy-default','2026-02-01','2026-01-01','agent-activity','stage-strip','&lt;img','&lt;unsafe&gt;']) assert.ok(html.includes(text),text);
assert.ok(!html.includes('<img'));
assert.match(renderTaskTable([entry('unknown')],[],()=>''), /Время —/);
row.task.createdAt = 'invalid';
assert.doesNotThrow(() => renderTaskTable([row], [], () => ''));
""")

    def test_blockers_distinguish_action_without_assuming_user_answer(self):
        self.run_js("""
const task = {...entry('blocked').task, status:'blocked', summary:'Old reason', remaining:['Repair the record']};
assert.ok(!taskStatus(task).includes('Нужен ответ'));
assert.match(blockerDetail(task), /Old reason/);
assert.match(blockerDetail(task), /Repair the record/);
for (const kind of ['technical','user_input','administrative']) {
 task.blocker = {kind, reason:'<bad>', action:'Inspect & repair'};
 const html = blockerDetail(task);
 assert.ok(html.includes(blockerLabels[kind]));
 assert.match(html, /&lt;bad&gt;/);
 assert.match(html, /Inspect &amp; repair/);
 assert.ok(taskStatus(task).includes(blockerLabels[kind]));
}
task.status = 'done';
assert.equal(blockerDetail(task), '');
assert.ok(!taskStatus(task).includes('Проблема учёта'));
""")

    def test_completed_task_shows_separate_git_obligations(self):
        self.run_js("""
const row = entry('completed');
Object.assign(row.task, {status:'done', gitCheckpoint:{status:'error',reason:'index.lock <busy>'},
 stages:[{id:'s',status:'done',gitCheckpoint:{status:'error',reason:'Dirty before work'}}]});
let html = renderTaskTable([row], [], () => '');
assert.match(html, /Завершено/);
assert.match(html, /Git: 2/);
assert.match(html, /index.lock &lt;busy&gt;/);
assert.match(html, /task-git-obligation/);
row.task.gitCheckpoint = {status:'committed'};
row.task.stages[0].gitCheckpoint = {status:'pending'};
html = renderTaskTable([row], [], () => '');
assert.match(html, /Git: 1/);
row.task.stages[0].gitCheckpoint = {status:'no_changes'};
html = renderTaskTable([row], [], () => '');
assert.ok(!html.includes('task-git-obligation'));
""")

    def test_shared_batch_obligations_are_grouped_with_localized_reason(self):
        self.run_js("""
const row = entry('shared');
const checkpoint = {status:'committed',batchId:'same-batch',publication:{status:'pending',reasonCode:'journal_publication_failed',reason:'original <diagnostic>'}};
row.task.gitCheckpoint = {...checkpoint,id:'task-operation'};
row.task.stages = [{id:'s',gitCheckpoint:{...checkpoint,id:'stage-operation'}}];
const html = renderTaskTable([row], [], () => '');
assert.match(html,/Git: 1/);
assert.match(html,/2 обязательств, 1 групп/);
assert.match(html,/требуется повторить публикацию в Hub/);
assert.equal(row.task.stages[0].gitCheckpoint.id,'stage-operation');
assert.equal(row.task.gitCheckpoint.id,'task-operation');
""")

    def test_project_scoped_columns_and_invalid_storage(self):
        self.run_js("""
localStorage.setItem('project-hub-task-columns:one','["summary","title","bad",4]');
let html = renderTaskTable([entry('root')], [], () => '');
assert.match(html, /data-task-cell="summary" hidden/);
assert.ok(!html.includes('data-task-cell="title" hidden'));
activeProject = 'two';
localStorage.setItem('project-hub-task-columns:two','{bad');
assert.ok(renderTaskTable([entry('root')],[],()=> '').includes('data-task-cell="summary" hidden'));
activeProject = 'three';
localStorage.getItem = () => {throw Error('denied');};
assert.doesNotThrow(() => renderTaskTable([entry('root')],[],()=>''));
assert.doesNotThrow(() => renderTaskColumnMenu());
""")

    def test_search_context_and_poll_menu_state(self):
        self.run_js("""
const row = entry('root'); row.fields = [{text:'match',label:'Scope',stage:'s'}];
const html = renderTaskTable([row], ['match'], field => {
 assert.equal(field.task.id,'root'); assert.equal(field.stage,'s'); return '<li>matched</li>';
});
assert.ok(html.includes('<li>matched</li>'));
renderTaskColumnMenu(); taskColumnMenuOpen = true;
assert.match(renderTaskColumnMenu(), /data-task-column-menu open/);
assert.match(renderTaskColumnMenu(), /data-task-column="title" checked disabled/);
""")

    def test_compact_defaults_and_explicit_preferences(self):
        self.run_js("""
let html = renderTaskTable([entry('root')], [], () => '');
assert.match(html, /data-task-cell="summary" hidden/);
assert.match(html, /data-task-cell="children" hidden/);
assert.match(html, /agent-activity unknown icon-only/);
assert.ok(html.includes('root\\nSummary &lt;unsafe&gt;'));
for (const id of ['status','progress','estimate','created','updated','actions']) {
 assert.ok(!html.includes(`data-task-cell="${id}" hidden`));
}
activeProject = 'explicit';
localStorage.setItem('project-hub-task-columns:explicit','[]');
html = renderTaskTable([entry('root')], [], () => '');
assert.ok(!html.includes('data-task-cell="summary" hidden'));
assert.ok(!html.includes('data-task-cell="children" hidden'));
""")

    def test_menu_change_keyboard_and_restore(self):
        self.run_js("""
renderTaskColumnMenu();
taskTableHidden = new Set();
const input = {dataset:{taskColumn:'summary'},checked:false};
const target = {closest: () => input};
handlers.change({target});
assert.equal(lastReplacement.selector,'#task-results');
assert.equal(lastReplacement.html,'<table>updated</table>');
assert.equal(localStorage.getItem('project-hub-task-columns:one'),'["summary"]');
input.checked = true; handlers.change({target});
assert.equal(localStorage.getItem('project-hub-task-columns:one'),'[]');
let focused = false;
const menu = {open:true,querySelector:()=>({focus:()=>{focused=true;}})};
handlers.keydown({target:{closest:()=>menu},key:'Escape',preventDefault:()=>{}});
assert.equal(menu.open,false); assert.equal(focused,true);
assert.equal(taskColumnMenuOpen,false);
let selected = -1;
menu.querySelectorAll = () => [0,1,2].map(index => ({focus:()=>{selected=index;}}));
document.activeElement = null;
handlers.keydown({target:{closest:()=>menu},key:'ArrowUp',preventDefault:()=>{}});
assert.equal(selected,2); assert.equal(menu.open,true);
handlers.keydown({target:{closest:()=>menu},key:'Home',preventDefault:()=>{}});
assert.equal(selected,0);
handlers.keydown({target:{closest:()=>menu},key:'End',preventDefault:()=>{}});
assert.equal(selected,2);
""")
        self.run_js("""
renderTaskColumnMenu();
const menu = {open:true,contains:()=>true,querySelector:()=>({focus:()=>{}})};
document.querySelector = selector => selector.includes('menu') ? menu : {scrollLeft:45};
document.activeElement = {dataset:{taskColumn:'summary'}};
const snapshot = captureTaskTableUi();
assert.equal(snapshot.focus,'summary'); assert.equal(snapshot.scroll,45);
menu.open = false; restoreTaskTableUi(snapshot); assert.equal(menu.open,true);
activeProject = 'other'; menu.open = false; restoreTaskTableUi(snapshot); assert.equal(menu.open,false);
""")


if __name__ == "__main__":
    unittest.main()
