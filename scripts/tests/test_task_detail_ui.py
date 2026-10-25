"""Focused contract checks for lazy task detail hydration."""
from pathlib import Path
import subprocess
import unittest


WEB = Path(__file__).resolve().parents[2] / "tools/project-portal/web/app.js"


class TaskDetailUiTests(unittest.TestCase):
    def test_only_actual_commits_appear_in_task_and_stage_without_duplicates(self):
        script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(process.argv[1],'utf8');
const ctx={escape:String,activeProject:'example',uiIcon:()=>''};
vm.runInNewContext(source.slice(source.indexOf('function stageGitCommit('),source.indexOf('const checkpointRetries')),ctx);
for(const status of ['pending','unavailable','no_changes','disabled','error']) {
 assert.equal(ctx.gitCommits({gitCommit:{status},gitCheckpoint:{status}}),'');
}
const sha='a'.repeat(40),other='b'.repeat(40),commit={status:'committed',sha};
assert.equal(ctx.stageGitCommit({gitCommit:{status:'committed'}}),'');
const task={gitCommit:commit,gitCheckpoint:{status:'no_changes',commits:[commit,{status:'committed',sha:other}],gitOutcome:commit}};
const html=ctx.gitCommits(task);assert.equal(html.split('>'+sha+'</code>').length-1,1);assert.match(html,new RegExp(other));
assert.equal(ctx.gitCommits(task,{}),'','a stage cannot inherit the task commit');
assert.match(ctx.gitCommits({gitCheckpoint:commit}),new RegExp(sha));
"""
        result = subprocess.run(['node','-e',script,str(WEB)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_task_activity_renders_after_following_chat_task_link(self):
        script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(process.argv[1],'utf8');
const start=source.indexOf('function taskStatus('),end=source.indexOf('const taskLink',start);
const ctx={planStatus:()=>'<span>Active task</span>',escape:String,uiIcon:()=>'<svg/>'};
vm.runInNewContext(source.slice(start,end),ctx);
for(const state of ['active','idle','unknown','waiting']) {
  const html=ctx.taskStatus({id:'task',currentWorks:[],agentActivity:{state}});
  assert.match(html,new RegExp('agent-activity '+state));assert.doesNotMatch(html,/undefined|<time/);
  assert.match(html,/<button type="button" class="agent-activity/);
  assert.match(html,/data-task-launch-open="task" data-stage-id="" aria-haspopup="dialog"/);
}
assert.match(ctx.taskStatus({id:'task',currentWorks:[{session:'one'}]}),/agent-activity active/);
assert.match(ctx.taskStatus({id:'task',currentWorks:[]},{id:'step'},true),/data-task-launch-open="task" data-stage-id="step"/);
assert(!source.includes('TaskLaunchesUI?.render('),'launch form must only render inside the dialog');
"""
        result = subprocess.run(['node','-e',script,str(WEB)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_refresh_keeps_details_until_new_revision_arrives_without_resurrecting_deleted_stages(self):
        script = r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(process.argv[1],'utf8'),start=source.indexOf('function retainTaskDetails('),end=source.indexOf('const taskDetailLoader',start);
const ctx={};vm.runInNewContext(source.slice(start,end),ctx);
const previous={revision:1,tasks:[{id:'task',detailLoaded:true,summary:'Full description',sources:['proof'],stages:[{id:'one',done:['Proof'],title:'Old'},{id:'removed'}]}]};
const next={revision:2,tasks:[{id:'task',detailLoaded:false,stages:[{id:'one',title:'Updated'},{id:'added',title:'New'}]}]};
ctx.retainTaskDetails(previous,next);
assert.equal(next.tasks[0].summary,'Full description');assert.equal(next.tasks[0].detailLoaded,false);
assert.equal(next.tasks[0].detailCached,true);assert.equal(next.tasks[0].stages[0].done[0],'Proof');
assert.equal(next.tasks[0].stages[0].title,'Updated');assert.deepEqual(next.tasks[0].stages.map(s=>s.id),['one','added']);
const again={revision:3,tasks:[{id:'task',detailLoaded:false,stages:[{id:'one'}]}]};
ctx.retainTaskDetails(next,again);assert.equal(again.tasks[0].summary,'Full description');
assert.equal(again.tasks[0].detailLoaded,false,'multiple rapid refreshes must not discard cached content');
const same={revision:3,tasks:[{id:'task',detailLoaded:false,stages:[{id:'one'}]}]};
ctx.retainTaskDetails(again,same);assert.equal(same.tasks[0].detailLoaded,false,'unresolved detail must still load at the same revision');
"""
        result = subprocess.run(['node','-e',script,str(WEB)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_loader_deduplicates_guards_stale_context_and_retries_errors(self):
        script = r"""
const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const source=fs.readFileSync(process.argv[1],'utf8');
const start=source.indexOf('function createTaskDetailLoader');
const end=source.indexOf('\nconst taskDetailLoader',start);
const ctx={}; vm.runInNewContext(source.slice(start,end)+'\nthis.createTaskDetailLoader=createTaskDetailLoader;',ctx);
let context={project:'one',task:'task',revision:7}, calls=0, applied=[], errors=[];
const pending=[];
const loader=ctx.createTaskDetailLoader({
  fetcher:async (...args)=>{calls++;return new Promise((resolve,reject)=>pending.push({args,resolve,reject}));},
  getContext:()=>context,
  onSuccess:(task,...args)=>applied.push({task,args}),
  onError:(error,...args)=>errors.push({error,args}),
});
(async()=>{
  const first=loader.load('one','task',7), second=loader.load('one','task',7);
  assert.strictEqual(first,second); assert.equal(calls,1);
  pending.shift().resolve({revision:7,task:{id:'task',detail:'full'}}); await first;
  assert.equal(applied.length,1);
  context={project:'two',task:'task',revision:7};
  const stale=loader.load('one','task',7); await Promise.resolve(); assert.equal(calls,2);
  pending.shift().resolve({revision:7,task:{id:'task',detail:'stale'}}); await stale;
  assert.equal(applied.length,1,'stale project response is ignored');
  context={project:'one',task:'task',revision:8};
  const staleRevision=loader.load('one','task',7); await Promise.resolve(); pending.shift().resolve({revision:7,task:{id:'task',detail:'old'}}); await staleRevision;
  assert.equal(applied.length,1,'stale revision response is ignored');
  context={project:'one',task:'broken',revision:9};
  const failed=loader.load('one','broken',9); await Promise.resolve(); pending.shift().reject(new Error('temporary')); await assert.rejects(failed,/temporary/);
  assert.equal(errors.length,1); assert.ok(loader.error('one','broken',9)); assert.equal(loader.load('one','broken',9),null,'failure does not auto-retry');
  loader.retry('one','broken',9); const retry=loader.load('one','broken',9); await Promise.resolve(); assert.equal(calls,5); pending.shift().resolve({revision:9,task:{id:'broken',detail:'recovered'}}); await retry;
  assert.equal(applied.length,2);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result = subprocess.run(["node", "-e", script, str(WEB)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
