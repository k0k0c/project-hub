"""Rehearse this repository's local separation using a verified, immutable backup.

Creates only a new trial directory. Does not switch the working server or Codex.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import threading
from urllib.request import urlopen

from backup_project_hub import verify
from project_registry import ProjectRegistry, CodexProjects
from project_portal import PortalServer
from task_transfer import transfer

HUB_TASKS = ['project-hub', 'hub-parallel-chat-verification', 'hub-evolution-planning',
             'hub-integration', 'hub-e2e-desktop-20260912', 'hub-cd34ef91802df52e']


def trial(snapshot, destination, live_catalog=False):
    snapshot, destination = Path(snapshot).resolve(), Path(destination).resolve()
    verified = verify(snapshot)
    if destination.exists() or destination.is_relative_to(snapshot):
        raise ValueError('Use a new trial directory outside the backup')
    destination.mkdir(parents=True)
    manifest = json.loads((snapshot/'manifest.json').read_text(encoding='utf-8'))
    source_root = Path(manifest['sourceRoot'])
    hub_root = Path(__file__).resolve().parents[1]
    catalog = destination/'trial-catalog.json'
    catalog.write_text(json.dumps({'local-projects':{
        'trial-sync':dict(id='trial-sync', name='Example Project',rootPaths=[str(source_root)]),
        'trial-hub':dict(id='trial-hub', name='Project Hub',rootPaths=[str(hub_root)])}}),encoding='utf-8')
    registry = ProjectRegistry(destination/'data',CodexProjects() if live_catalog else CodexProjects(catalog))
    registry.refresh()
    source = json.loads((snapshot/'project-data/project.json').read_text(encoding='utf-8-sig'))['id']
    target = 'project-hub'
    source_codex, target_codex='trial-sync','trial-hub'
    if live_catalog:
        from project_resolution import resolve_project
        projects=registry.list()['projects']
        def owner(root):
            match=resolve_project(projects,root)
            if not match or Path(match[0]['roots'][0]).resolve()!=root:
                raise ValueError('Expected a primary project root')
            return match[0]['codex_id']
        source_codex,target_codex=owner(source_root),owner(hub_root)
    # Preserve the existing Hub project ID so historical coordination keeps its identity.
    with registry.connect() as db:
        db.execute('UPDATE spaces SET id=? WHERE codex_id=?',(source,source_codex))
        db.execute('UPDATE spaces SET id=? WHERE codex_id=?',(target,target_codex))
    data = registry.base_store(source).data
    shutil.copytree(snapshot/'project-data',data,dirs_exist_ok=True)
    coordination = registry.home/'coordination/coordination.sqlite3'
    coordination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(snapshot/'coordination.sqlite3',coordination)
    from plugin_api import ServerHub
    ServerHub(registry)
    rebound=[]
    if live_catalog:
        from project_resolution import assignment_for
        metadata=registry.catalog.read()
        assignment_for(metadata,'')
        with sqlite3.connect(coordination) as db:
            db.execute('INSERT OR IGNORE INTO projects(id,root,git_common) VALUES(?,?,?)',(target,str(hub_root),None))
            for sid,row in metadata.get('assignments',{}).items():
                if row.get('projectKind')!='local' or assignment_for(metadata,sid)!=target_codex:continue
                old=db.execute('SELECT project FROM sessions WHERE id=?',(sid,)).fetchone()
                if old and old[0]==source:
                    if db.execute("SELECT 1 FROM work WHERE session=? AND status IN ('active','waiting')",(sid,)).fetchone():
                        raise ValueError('Moved chat still has active work')
                    db.execute('UPDATE sessions SET project=?,workspace=? WHERE id=?',(target,str(hub_root),sid))
                    rebound.append(sid)
    original = registry.store(source).snapshot()
    originals = {t['id']:t for t in original['tasks']}
    if set(originals) != set(HUB_TASKS+['architecture-refactor']):
        raise ValueError('Task inventory changed; review the separation map')
    journal = data/'events.jsonl'
    digest = lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    before = digest(journal)
    moved, blocked = [], []
    for task in HUB_TASKS:
        try:
            preview=transfer(registry,source,target,task,preview=True)
            result=transfer(registry,source,target,task,preview['revision'],'trial-'+task,actor='local-separation-trial')
            moved.append(result['task'])
        except ValueError as error:
            blocked.append(dict(task=task,reason=str(error)))
    after = registry.store(source).snapshot()
    hub = registry.store(target).snapshot()
    for task in hub['tasks']:
        old=originals[task['id']]
        assert task['uid']==old['uid'] and task['status']==old['status']
        assert task['participatingSessions']==old['participatingSessions']
        assert [(s['id'],s['status']) for s in task['stages']]==[(s['id'],s['status']) for s in old['stages']]
        assert after['redirects'][task['id']]['uid']==task['uid']
    assert digest(journal)==before, 'Source journal was changed'
    assert next(t for t in after['tasks'] if t['id']=='architecture-refactor')['uid']==originals['architecture-refactor']['uid']
    server=PortalServer(('127.0.0.1',0),registry=registry)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        url='http://127.0.0.1:'+str(server.server_port)
        def get(path):
            with urlopen(url+path,timeout=5) as response:return json.load(response)
        api_source=get('/api/state?project='+source)
        api_hub=get('/api/state?project='+target)
        assert {t['id'] for t in api_source['tasks']}=={t['id'] for t in after['tasks']}
        assert {t['id'] for t in api_hub['tasks']}==set(moved)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    with sqlite3.connect(coordination) as db:
        integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
    assert integrity=='ok'
    result=dict(snapshot=str(snapshot),backup=verified,moved=moved,blocked=blocked,
                retained=[t['id'] for t in after['tasks']],journalUnchanged=True,
                coordinationIntegrity=integrity,httpVerified=True,chatsMoved=False,
                productionChanged=False,trialServerStopped=not thread.is_alive(),reboundSessions=rebound,liveCatalog=live_catalog)
    (destination/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--destination',type=Path,required=True)
    parser.add_argument('--live-catalog',action='store_true',help='Stage this local cutover using current Codex assignments; does not switch the server')
    args=parser.parse_args()
    result=trial(args.snapshot,args.destination,args.live_catalog)
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(bool(result['blocked']))
