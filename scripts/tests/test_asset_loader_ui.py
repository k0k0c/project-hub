"""Focused contract checks for lazy architecture asset loading."""
from pathlib import Path
import subprocess
import unittest


WEB = Path(__file__).resolve().parents[2] / "tools/project-portal/web"


class AssetLoaderUiTests(unittest.TestCase):
    def test_architecture_assets_load_in_order_deduplicate_and_retry(self):
        source = (WEB / "asset-loader.js").read_text(encoding="utf-8")
        script = r"""
const assert=require('node:assert/strict'), vm=require('node:vm');
const appended=[], attempts=new Map();
const document={head:{appendChild(node){appended.push(node);const n=attempts.get(node.src)||0;attempts.set(node.src,n+1);setImmediate(()=>{if(node.src.endsWith('cose-base.js')&&n===0) node.onerror(); else node.onload();});}},createElement(){return {remove(){}};}};
const location={origin:'http://localhost',href:'http://localhost/'};
const ctx={window:null,document,location,URL,Promise,setImmediate};ctx.window=ctx;
vm.runInNewContext(process.argv[1],ctx);
(async()=>{
  const first=ctx.HubAssets.ensureArchitecture(), second=ctx.HubAssets.ensureArchitecture();
  assert.strictEqual(first,second,'concurrent calls share one promise');
  await assert.rejects(first,/cose-base/);
  assert.deepEqual(appended.map(x=>new URL(x.src).pathname),['/vendor/cytoscape.js','/vendor/layout-base.js','/vendor/cose-base.js']);
  await ctx.HubAssets.ensureArchitecture();
  assert.ok(appended.every(x=>new URL(x.src).origin==='http://localhost'),'all assets stay same-origin');
  assert.deepEqual(appended.map(x=>new URL(x.src).pathname),['/vendor/cytoscape.js','/vendor/layout-base.js','/vendor/cose-base.js','/vendor/cose-base.js','/vendor/cytoscape-fcose.js','/vendor/elk-api.js','/architecture-map.js','/architecture-routing.js','/architecture-canvas.js']);
  const loadedCount=appended.length;
  await ctx.HubAssets.ensureArchitecture();
  assert.equal(appended.length,loadedCount,'successful calls do not append scripts again');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result = subprocess.run(["node", "-e", script, str(source)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
