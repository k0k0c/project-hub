"""Checks UI behavior in an isolated JS context, without a server or Hub data."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node is required')
class ChecksUiTest(unittest.TestCase):
    def run_js(self, test):
        source = Path(__file__).resolve().parents[2] / 'tools/project-portal/web/checks.js'
        harness = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const handlers={},requests=[];
const ctx={URLSearchParams,activeProject:'owner',
 state:{checks:[],checkCount:0,tasks:[{id:'task',title:'Task',stages:[{id:'stage',title:'Stage'}]}],project:{checks:[]}},
 document:{addEventListener:(name,handler)=>handlers[name]=handler},
 escape:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;'),
 title:()=>'',uiIcon:()=>'<svg/>',status:s=>`<span class="tag ${s}">${s}</span>`,date:s=>s,
 taskLink:(t,s)=>'#tasks/'+encodeURIComponent(t.id)+(s?'/'+encodeURIComponent(s):''),
 evidence:s=>(s||[]).map(x=>'<a href="/api/evidence?path='+encodeURIComponent(x.path)+'">log</a>').join(''),
 route:()=>['checks'],render(){},fetch:async url=>{requests.push(url);return {ok:true,json:async()=>({runs:[],total:0,next:null})}}};
vm.createContext(ctx);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
(async()=>{
'''
        result = subprocess.run(['node', '-e', harness + test + '\n})().catch(e=>{console.error(e);process.exitCode=1});', str(source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_all_pages_filters_and_statuses(self):
        self.run_js(r'''
const all=Array.from({length:121},(_,i)=>({runId:'run-'+i,kind:'check.passed',profile:i===120?'old-profile':'current',taskId:i===120?'old-task':'task'}));
ctx.fetch=async url=>{requests.push(url);const offset=Number(new URLSearchParams(url.split('?')[1]).get('offset'));
 return {ok:true,json:async()=>({runs:all.slice(offset,offset+50),total:121,next:offset+50<121?offset+50:null,revision:1})};};
await ctx.loadChecks();
const view=ctx.checksView();assert.equal(view.runs.length,121);assert.equal(view.total,121);
assert.deepEqual(requests.map(u=>new URLSearchParams(u.split('?')[1]).get('offset')),['0','50','100']);
assert.ok(requests.every(u=>u.includes('project=owner')&&u.includes('limit=50')));
view.filters.profile='old-profile';assert.equal(ctx.filteredCheckRuns(view)[0].runId,'run-120');
view.filters.task='old-task';assert.equal(ctx.filteredCheckRuns(view).length,1);
view.filters.status='failed';assert.equal(ctx.filteredCheckRuns(view).length,0);
for(const s of ['passed','failed','interrupted','unknown'])assert.equal(ctx.checkRunStatus({kind:'check.'+s}),s);
assert.equal(ctx.checkRunStatus({kind:'check.started'}),'running');
assert.equal(ctx.checkRunStatus({kind:'future'}),'unknown');
assert.equal(ctx.checkRunStatus({status:'interrupted',kind:'check.started'}),'interrupted');
assert.equal(ctx.checkRuns([{runId:'x',kind:'check.started'},{runId:'x',kind:'check.failed'}])[0].kind,'check.failed');
assert.equal(ctx.checkRuns([{runId:'x',originProject:'a'},{runId:'x',originProject:'b'}]).length,2);
''')

    def test_project_names_and_missing_catalog_entries(self):
        self.run_js(r'''
ctx.projectNames=new Map([['origin','Original project'],['owner','Project Hub'],['launch','<Launch>']]);
const row=ctx.checkRunRow({originProject:'origin',ownerProject:'owner',launchProject:'launch'},0);
assert.match(row,/<dd title="origin">Original project<\/dd>/);
assert.match(row,/<dd title="owner">Project Hub<\/dd>/);
assert.match(row,/<dd title="launch">&lt;Launch><\/dd>/);
assert.match(ctx.checkRunRow({originProject:'missing'},0),/<dd title="missing">Проект недоступен<\/dd>/);
assert.match(ctx.checkRunRow({},0),/<dd title="">—<\/dd>/);
ctx.projectNames.set('origin','Renamed');
assert.match(ctx.checkRunRow({originProject:'origin'},0),/>Renamed<\/dd>/);
''')

    def test_details_escaping_provenance_and_baseline(self):
        self.run_js(r'''
const run={runId:'<script>',title:'Publication regression',profile:'<img>',taskId:'task',stageId:'stage',kind:'check.passed',
 command:['node','<unsafe>'],scope:['a','b'],revision:{sha:'<sha>',dirty:true},exitCode:0,
 originProject:'origin',ownerProject:'owner',launchProject:'owner',startedAt:'2026-09-19T12:00:00Z',finishedAt:'2026-09-19T12:01:05Z',
 evidence:[{label:'log',path:'.local/checks/run.log'}]};
const row=ctx.checkRunRow(run,0);
assert.match(row,/<strong>Publication regression<\/strong>/);
assert.match(row,/checks-profile.*&lt;img>/);
assert.doesNotMatch(row,/<script>|<img>|<unsafe>|<sha>/);assert.match(row,/&lt;unsafe>/);
assert.match(row,/#tasks\/task\/stage/);assert.match(row,/Task \/ Stage/);
assert.match(row,/1 мин 5 с/);assert.match(row,/origin/);assert.match(row,/owner/);
const corrected=ctx.checkRunRow({...run,status:'failed',kind:'check.corrected',correction:{reason:'Wrong <result>',expectedEvent:'old-event'}},0);
assert.equal(ctx.checkRunStatus({status:'failed',kind:'check.corrected'}),'failed');
assert.match(corrected,/Причина исправления/);assert.match(corrected,/Wrong &lt;result>/);assert.match(corrected,/old-event/);
assert.doesNotMatch(row,/Историческая запись/);assert.match(ctx.checkRunRow({...run,legacy:true},0),/Историческая запись/);
assert.match(row,/api\/evidence\?path=.local%2Fchecks%2Frun.log/);
assert.match(ctx.checkTaskLink({...run,ownerProject:'other'}),/\?project=other#tasks/);
const correctedClock={...run,at:'2026-09-20T04:05:06Z',startedAt:null,durationMs:null,kind:'check.corrected',status:'passed',
 correction:{reason:'Launch clock unknown',expectedEvent:'wrong-launch'}};
assert.equal(ctx.checkTime(correctedClock.startedAt),'<span>—</span>');
assert.equal(ctx.checkDuration(correctedClock),'—');
const clockRow=ctx.checkRunRow(correctedClock,0);
assert.match(clockRow,/Launch clock unknown/);
assert.doesNotMatch(clockRow,/1970|1 мин 5 с|12:00:00|04:05:06/);
assert.equal(ctx.checkDuration({durationMs:0}),'0 с');assert.equal(ctx.checkDuration({durationMs:-1}),'—');
assert.match(ctx.checkTime('invalid'),/—/);
ctx.state.project.checks=[{title:'Historical baseline',status:'passed',detail:'Old evidence'}];
await ctx.loadChecks();const page=ctx.renderChecksPage();
assert.match(page,/Historical baseline/);assert.match(page,/Old evidence/);assert.match(page,/data-checks-filter="task"/);
assert.doesNotMatch(page,/автоматически/);
''')

    def test_errors_retry_stale_requests_and_project_isolation(self):
        self.run_js(r'''
ctx.fetch=async()=>({ok:false});await ctx.loadChecks();assert.ok(ctx.checksView().error);assert.equal(ctx.checksView().loading,false);
ctx.fetch=async()=>({ok:true,json:async()=>({runs:[],total:5,next:0})});await ctx.loadChecks();assert.ok(ctx.checksView().error);
let page=0;ctx.fetch=async()=>({ok:true,json:async()=>++page===1?{runs:[{runId:'first'}],total:2,next:1,revision:1}:{runs:[{runId:'second'}],total:2,next:null,revision:2}});
await ctx.loadChecks();assert.match(ctx.checksView().error,/История изменилась/);assert.equal(ctx.checksView().runs.length,1);
let release;ctx.fetch=()=>new Promise(resolve=>release=resolve);const pending=ctx.loadChecks();
ctx.fetch=async()=>({ok:true,json:async()=>({runs:[{runId:'fresh'}],total:1,next:null})});
await ctx.loadChecks();release({ok:true,json:async()=>({runs:[{runId:'stale'}],total:1,next:null})});await pending;
assert.equal(ctx.checksView().runs[0].runId,'fresh');assert.equal(ctx.checksView().error,'');
ctx.checksView().filters.profile='owner-filter';ctx.activeProject='other';
assert.equal(ctx.checksView().runs.length,0);assert.equal(ctx.checksView().filters.profile,'');
await ctx.loadChecks();ctx.activeProject='owner';assert.equal(ctx.checksView().filters.profile,'owner-filter');
''')


if __name__ == '__main__':
    unittest.main()
