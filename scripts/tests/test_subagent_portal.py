"""Isolated team projection contracts and a disposable browser preview fixture."""
from contextlib import contextmanager, ExitStack
import json
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'tools/project-portal/plugins/project-hub/scripts'))
from project_portal import Store, PortalServer
from hub_core import Hub, HubError

PARENT = '11111111-1111-4111-8111-111111111111'
CHILD = '22222222-2222-4222-8222-222222222222'
DONE = '33333333-3333-4333-8333-333333333333'
UNKNOWN = '44444444-4444-4444-8444-444444444444'


@contextmanager
def fixture():
    with tempfile.TemporaryDirectory(prefix='hub-team-preview-') as temporary, ExitStack() as stack:
        root = Path(temporary) / 'project'
        data = root / 'docs/project-portal'
        data.mkdir(parents=True)
        seed = dict(schemaVersion=1, id='team-test', name='Isolated team preview', tasks=[
            dict(id='task', title='Agent integration fixture', status='active', stages=[
                dict(id='implementation', title='Implementation', status='active', done=[], remaining=['Verify team']),
                dict(id='verification', title='Verification', status='done', done=['Result preserved'], remaining=[])])])
        (data / 'project.json').write_text(json.dumps(seed), encoding='utf-8')
        external_data = Path(temporary) / 'hub-data'
        shutil.copytree(data, external_data)
        hub = Hub(Path(temporary) / 'coordination')
        hub.register(root)
        store = Store(root, data_dir=external_data, coordination_home=hub.home)
        hub.store_factory = lambda project: store
        names = {PARENT:'Primary agent', CHILD:'Portal implementation', DONE:'Catalog verification', UNKNOWN:'Discovered agent'}
        for sid in (PARENT, CHILD, DONE):
            hub.lifecycle(dict(session_id=sid,cwd=str(root),hook_event_name='SessionStart'), 'start-'+sid)
        with hub.connect() as c:
            for sid in (CHILD,DONE):
                c.execute('INSERT INTO session_agents VALUES (?,?,?,?,?)',(sid,PARENT,'/root/'+sid[:4],names[sid],'executor'))
        parent = hub.begin(PARENT,'task','Integrate independent results',['src/core'],stage='implementation')
        child = hub.begin(CHILD,'task','Render real team and results',['src/portal'],stage='implementation')
        done = hub.begin(DONE,'task','Verify catalog identity',['src/catalog'],stage='verification')
        hub.report(DONE,done['work'],done['revision'],'CATALOG-VERIFIED: distinct identities; no inherited task',status='done')
        overlap = hub.begin(CHILD,'task','Waiting for core owner',['src/core'],stage='implementation')
        assert overlap['warning'] == 'resource_overlap'
        with hub.connect() as c:
            c.execute('UPDATE sessions SET seen=1 WHERE id=?',(CHILD,))
        discovered = [dict(id=sid,name=names[sid],cwd=str(root),updated_at=1,kind='agent' if sid==PARENT else 'subagent',
                           **({'parentSession':PARENT,'agentPath':'/root/'+sid[:4]} if sid!=PARENT else {})) for sid in names]
        stack.enter_context(patch('codex_session_catalog.CATALOG.read',return_value=dict(available=True,sessions=discovered,truncated=False)))
        stack.enter_context(patch('project_portal.SESSION_TITLES.get',return_value=names))
        yield store, hub, dict(parent=parent,child=child,done=done,overlap=overlap)


class SubagentPortalTest(unittest.TestCase):
    def test_actual_task_stage_results_and_independent_current_counts(self):
        with fixture() as (store,hub,handles):
            result=store.coordination()
            self.assertTrue(result['available'],result)
            self.assertEqual(result['sessionCount'],4)
            self.assertEqual(len(result['work']),3)
            team=result['team']
            byid={w['id']:w for w in team['work']}
            completed=byid[handles['done']['work']]
            self.assertEqual(completed['stage'],'verification')
            self.assertEqual(completed['task'],'task')
            self.assertIn('CATALOG-VERIFIED',completed['result'])
            self.assertFalse(completed['resourcesHeld'])
            self.assertEqual(completed['resources'][0]['name'],'src/catalog')
            self.assertEqual(byid[handles['child']['work']]['resources'][0]['name'],'src/portal')
            unknown=next(s for s in team['sessions'] if s['id']==UNKNOWN)
            self.assertIsNone(unknown['task'])
            self.assertEqual(unknown['state'],'unknown')
            self.assertEqual(result['attempts'][0]['state'],'overlap')
            self.assertEqual(result['attempts'][0]['blockers'][0]['session'],PARENT)
            page=store.coordination(offset=2,limit=2)
            self.assertEqual(page['sessionCount'],4)
            self.assertEqual(len(page['sessions']),2)
            self.assertEqual(page['team'],team)

    def test_history_metadata_survives_missing_catalog_without_live_claims(self):
        with fixture() as (store,hub,handles):
            team=store.team_projection(hub,'team-test',[])
            child=next(s for s in team['sessions'] if s['id']==DONE)
            self.assertEqual(child['parentSession'],PARENT)
            self.assertEqual(child['kind'],'subagent')
            self.assertTrue(child['historical'])
            self.assertEqual(child['state'],'unknown')
            self.assertNotIn('task',child)

    def test_bounded_active_and_recent_work_are_separate_and_project_scoped(self):
        with fixture() as (store,hub,handles):
            team=store.team_projection(hub,'team-test',[],limit=1)
            self.assertTrue(team['activeMore'])
            self.assertEqual(len(team['work']),2)
            self.assertEqual({w['status'] for w in team['work']},{'active','done'})
            foreign=store.team_projection(hub,'other-project',[])
            self.assertEqual(foreign['work'],[])
            self.assertEqual(foreign['sessions'],[])

    def test_moved_historical_owner_does_not_expose_other_project_work(self):
        with fixture() as (store,hub,handles):
            other=store.root.parent / 'other'
            data=other / 'docs/project-portal'
            data.mkdir(parents=True)
            (data/'project.json').write_text(json.dumps(dict(schemaVersion=1,id='other',name='Other',tasks=[dict(id='foreign-task',title='Foreign',status='active',stages=[])])),encoding='utf-8')
            hub.register(other)
            # Fixture for a reconciled move; the move protocol is tested separately.
            with hub.connect() as c:
                c.execute('UPDATE sessions SET project=?,workspace=? WHERE id=?',('other',str(other),DONE))
            foreign=hub.begin(DONE,'foreign-task','PRIVATE OTHER PROJECT',['other-resource'])
            team=store.team_projection(hub,'team-test',[])
            self.assertIn(handles['done']['work'],[w['id'] for w in team['work']])
            self.assertNotIn(foreign['work'],[w['id'] for w in team['work']])
            self.assertNotIn('PRIVATE OTHER PROJECT',json.dumps(team))
            self.assertEqual(next(s for s in team['sessions'] if s['id']==DONE)['state'],'unknown')


if __name__ == '__main__':
    if '--preview' in sys.argv:
        with fixture() as (store,hub,handles):
            server=PortalServer(('127.0.0.1',0),store)
            print(f'http://127.0.0.1:{server.server_port}/#coordination/{CHILD}',flush=True)
            print(f'Temporary project: {store.root}; coordination: {hub.home}',flush=True)
            try:
                server.serve_forever()
            finally:
                server.server_close()
    else:
        unittest.main()
