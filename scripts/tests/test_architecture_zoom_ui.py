"""Focused wheel zoom behavior for the architecture canvas."""
from pathlib import Path
import shutil
import subprocess
import unittest


WEB = Path(__file__).resolve().parents[2] / "tools/project-portal/web"


@unittest.skipUnless(shutil.which("node"), "Node is required")
class ArchitectureZoomUiTest(unittest.TestCase):
    def run_node(self, code):
        script = r"""
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const frames=[],cancelled=new Set(),listeners={};
const win={requestAnimationFrame(fn){const id=frames.length;frames.push(fn);return id;},cancelAnimationFrame(id){cancelled.add(id);},addEventListener(n,f){listeners[n]=f;},removeEventListener(n,f){if(listeners[n]===f)delete listeners[n];}};
const ctx={Math,console,window:win};vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1]+'/architecture-canvas.js','utf8'),ctx);
const canvas=ctx.window.ArchitectureCanvas;
function flush(){const pending=frames.splice(0);for(const [id,fn] of pending.entries())if(!cancelled.has(id))fn();}
function makeCy(){let level=1;const calls=[];return {calls,zoom(v){if(v===undefined)return level;level=v.level;calls.push(v);},minZoom(){return .1;},maxZoom(){return 4;},height(){return 800;},zoomingEnabled(){return true;},on(){},off(){}};}
function makeContainer(){return {ownerDocument:{defaultView:win},style:{},listeners:{},addEventListener(n,f){this.listeners[n]=f;},removeEventListener(n,f){delete this.listeners[n];},getBoundingClientRect(){return {left:10,top:20};}};}
"""
        result = subprocess.run(["node", "-e", script + "\n(async()=>{\n" + code + "\n})().catch(e=>{console.error(e);process.exitCode=1;});", str(WEB)], capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_smooth_coordinate_is_identity_monotonic_and_bounded(self):
        self.run_node(r'''
const z=canvas.wheelZoom;assert.equal(z(1,0),1);assert.equal(z(.4,0),.4);
for(const value of [.01,.1,.35,1,4]){assert.ok(z(value,-100)>=.01);assert.ok(z(value,100)<=4);}
for(const value of [38,39,40,44,45,46]){const a=z(1,-value/1000),b=z(1,-(value+1)/1000);assert.ok(b<a);assert.ok(Math.abs(b-a)<.02);}
let previous=.1;for(let i=0;i<100;i++){const next=z(previous,.01);assert.ok(next>previous);previous=next;}
''')

    def test_delta_modes_and_raf_batch_preserve_total_target_and_anchor(self):
        self.run_node(r'''
const cy=makeCy(),container=makeContainer(),cleanup=canvas.bind(cy,container);const wheel=container.listeners.wheel;
wheel({deltaY:10,deltaMode:0,clientX:110,clientY:220,preventDefault(){},stopImmediatePropagation(){}});
wheel({deltaY:1,deltaMode:1,clientX:130,clientY:240,preventDefault(){},stopImmediatePropagation(){}});
wheel({deltaY:1,deltaMode:2,clientX:150,clientY:260,preventDefault(){},stopImmediatePropagation(){}});assert.equal(cy.calls.length,0);
flush();assert.equal(cy.calls.length,1);assert.deepEqual(JSON.parse(JSON.stringify(cy.calls[0].renderedPosition)),{x:140,y:240});
const expected=canvas.wheelZoom(1,-(10+16+800)/1000);assert.ok(Math.abs(cy.zoom()-expected)<Number.EPSILON*2);
cleanup();
delete win.requestAnimationFrame;const syncCy=makeCy(),syncContainer=makeContainer(),syncCleanup=canvas.bind(syncCy,syncContainer);
syncContainer.listeners.wheel({deltaY:10,deltaMode:0,clientX:0,clientY:0,preventDefault(){},stopImmediatePropagation(){}});
assert.equal(syncCy.calls.length,1,'without RAF wheel zoom remains synchronous');syncCleanup();
''')

    def test_reversal_limits_anchor_and_disposal_cancel_pending_frame(self):
        self.run_node(r'''
const cy=makeCy(),container=makeContainer(),cleanup=canvas.bind(cy,container);const wheel=container.listeners.wheel;
wheel({deltaY:100000,deltaMode:0,clientX:20,clientY:30,preventDefault(){},stopImmediatePropagation(){}});flush();assert.equal(cy.zoom(),.1);wheel({deltaY:-100000,deltaMode:0,clientX:40,clientY:50,preventDefault(){},stopImmediatePropagation(){}});flush();assert.equal(cy.zoom(),4);
wheel({deltaY:1,deltaMode:0,clientX:90,clientY:100,preventDefault(){},stopImmediatePropagation(){}});cleanup();flush();assert.equal(cy.calls.length,2,'dispose cancels pending zoom');assert.equal(Object.keys(container.listeners).length,0);
''')


if __name__ == "__main__":
    unittest.main()
