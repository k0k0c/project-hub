"""ZIP preparation uses the same active-folder import preview as a folder."""
from pathlib import Path
import shutil
import subprocess
import unittest


WEB = Path(__file__).resolve().parents[2] / "tools/project-portal/web"


@unittest.skipUnless(shutil.which("node"), "Node is required")
class BackupsImportUiTest(unittest.TestCase):
    def test_reload_recovers_prepared_source_and_full_archive_paths(self):
        code = r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const web=process.argv[1],status={textContent:''},events={};
const root={dataset:{},isConnected:true,scrollTop:0,scrollLeft:0,addEventListener:(name,fn)=>events[name]=fn,querySelector:selector=>selector==='[data-backup-status]'?status:null};
const ctx={console,Date,Intl,Set,Map,activeProject:'kept project',location:{hash:'#projects/backups/operation/restored',search:'?project=kept%20project'},
 document:{addEventListener(){},querySelector:()=>root,querySelectorAll:()=>[],documentElement:{dataset:{hubLocale:'en'}}},
 setTimeout:()=>1,clearTimeout(){},escape:value=>String(value??''),uiIcon:()=>'',
 HubLiveUI:{patch:(target,html)=>target.html=html},backupStatus:{acknowledge(){},afterRender(){},details:id=>id==='restored'?`<div data-operation-details="${id}"><a href="?project=kept%20project#projects/data/import/prepared-id">Open import preview</a><p>Active data and the source archive are preserved</p></div>`:`<div data-operation-details="${id}"></div>`,operationLink:row=>`#projects/backups/operation/${row.id}`},
 fetch:async()=>({ok:true,json:async()=>({backupHome:'D:/Data backups',backups:[{id:'zip',name:'example.zip',sha256:'verified-hash',size:100,projects:[{id:'one',name:'One'}]}],restoreCopies:[],jobs:[{id:'restored',action:'restore-copy',status:'succeeded',createdAt:'2026-10-11T01:00:00Z',result:{copyId:'prepared-id',path:'D:/internal-preparation/data',projectCount:1}}]})})};
ctx.window=ctx;ctx.globalThis=ctx;vm.createContext(ctx);
for(const name of ['locale-catalog.js','i18n.js','local-files.js','backups.js'])vm.runInContext(fs.readFileSync(web+'/'+name,'utf8'),ctx);
(async()=>{
 const beforeHash=ctx.location.hash;await ctx.loadBackups(root);const html=root.html;assert.equal(ctx.location.hash,beforeHash);assert.doesNotMatch(html,/last-restored-copy/);
 assert.match(html,/Restore from ZIP/);assert.match(html,/data-local-open="backups"/);assert.match(html,/data-path="D:\/Data backups\/example.zip"/);assert.match(html,/data-reveal="true"/);
 assert.match(html,/\?project=kept%20project#projects\/data\/import\/prepared-id/);assert.match(html,/data-operation-details="restored"/);
 assert.match(html,/Active data and the source archive are preserved/);assert.doesNotMatch(html,/internal-preparation|activate-copy|[А-Яа-яЁё]/);
 const download=html.match(/href="([^\"]*\/api\/v1\/backups\/download[^\"]*)"/);assert.ok(download);assert.match(download[1],/id=zip/);
  ctx.location.hash='#projects/backups';assert.doesNotMatch(ctx.backupsPage({embedded:true}),/data-operation-details="restored"/,'leaving operation route clears its details');
  assert.equal(vm.runInContext('backupSize(1024**3)',ctx),'1 GB');assert.equal(vm.runInContext('backupSize(100)',ctx),'<0.1 KB');
})().catch(error=>{console.error(error);process.exitCode=1});
'''
        result = subprocess.run(
            ["node", "-e", code, str(WEB)], capture_output=True,
            text=True, encoding="utf-8", timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
