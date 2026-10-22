"""Real isolated journal + coordination DB contracts for model memory."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
sys.path.insert(0,str(ROOT/'tools/project-portal/plugins/project-hub/scripts'))
from project_portal import Store
from hub_core import Hub,HubError
from hub_memory import Memory
from hub_plugin import Mcp

class MemoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)/'project'
        data=self.root/'docs/project-portal'; data.mkdir(parents=True)
        (data/'project.json').write_text(json.dumps(dict(schemaVersion=1,id='memory-test',name='Test',tasks=[dict(id='task',title='Memory',status='active',stages=[],sources=[dict(path='proof.md')])])),encoding='utf-8')
        self.external_data=Path(self.tmp.name)/'hub-data'
        shutil.copytree(data, self.external_data)
        (self.root/'proof.md').write_text('Proof '*2000)
        self.hub=Hub(Path(self.tmp.name)/'shared');self.hub.register(self.root)
        self.store=Store(self.root,data_dir=self.external_data,coordination_home=self.hub.home)
        self.hub.store_factory=lambda project:self.store
        self.hub.ensure_session('a',self.root);self.hub.ensure_session('b',self.root)
        self.m=Memory(self.hub,'a'); self.api=Mcp(self.hub,str(self.root),'a')
    def tearDown(self): self.tmp.cleanup()
    def stage(self): return self.m.plan('task',stage='viewer',title='Viewer',remaining=['Search'])
    def test_blocker_requires_stage_mutation_without_ignored_fields(self):
        self.stage()
        before = self.m.plan('task')['revision']
        for fields in ({}, {'stage':'viewer','primary':False},
                       {'stage':'viewer','estimate':{}},
                       {'stage':'viewer','title':'Decision','decision':'Recorded decision'}):
            with self.subTest(fields=fields), self.assertRaises(HubError):
                self.m.plan('task', blocker=None, expected=before, **fields)
            self.assertEqual(self.m.plan('task')['revision'], before)
    def test_plan_idempotence_and_stale_update(self):
        first=self.stage(); self.assertEqual(first,self.stage())
        self.m.plan('task',title='Decision',decision='Reuse existing ORION result')
        with self.assertRaisesRegex(ValueError,'revision changed'):
            self.m.plan('task',stage='viewer',title='Overwrite',expected=first['revision'])
        self.assertEqual(self.m.stage('task','viewer')['title'],'Viewer')
    def test_create_stage_with_revision_and_retry_after_other_events(self):
        revision=self.m.plan('task')['revision']
        args=dict(stage='review',title='Review',remaining=['Inspect'],expected=revision)
        self.m.plan('task',**args)
        self.m.plan('task',title='Decision',decision='Another event')
        self.m.plan('task',**args)
        tasks,events=self.m.snapshot()
        self.assertEqual(len(tasks[0]['stages']),1)
        self.assertEqual(sum(e['kind']=='stage.created' for e in events),1)
        self.assertFalse(any(e['kind']=='stage.updated' for e in events))
        current=self.m.plan('task')['revision']
        self.m.plan('task',stage='review',title='Reviewed',remaining=[],status='done',expected=current)
        self.assertEqual(self.m.stage('task','review')['status'],'done')
    def test_stale_revision_cannot_create_a_missing_stage(self):
        revision=self.m.plan('task')['revision']
        self.m.plan('task',title='Decision',decision='Newer event')
        with self.assertRaisesRegex(ValueError,'revision changed'):
            self.m.plan('task',stage='review',title='Review',expected=revision)
        self.assertEqual(self.m.plan('task')['task']['stages'],[])
    def test_search_decision_result_and_bounded_evidence(self):
        self.m.plan('task',title='Prior investigation',decision='ORION was verified')
        result=self.m.read(query='ORION')
        self.assertEqual(result['results'][0]['kind'],'decision')
        ref=result['results'][0]['ref']
        self.assertIn('ORION',self.m.read(ref=ref)['text'])
        self.assertEqual(self.m.read(query='ORION',task='other')['results'],[])
        part=self.m.read(ref='source:proof.md'); self.assertEqual(len(part['text']),4000);self.assertIsNotNone(part['next'])
        with self.assertRaises(ValueError): self.m.read(ref='source:../secret')
        self.m.plan('task',title='New investigation',decision='NEBULA verified')
        self.assertTrue(self.m.read(query='NEBULA')['results'])
    def test_source_modes_raw_hash_and_pinned_pages(self):
        import hashlib
        archive = self.m.store.data/'source-archive'
        archive.mkdir()
        (archive/'proof.md').write_bytes(b'\xef\xbb\xbfarchived\r\n')
        current = self.m.read(ref='source:proof.md')
        self.assertEqual(current['source']['kind'], 'current')
        self.assertTrue(current['source']['archiveAvailable'])
        self.assertEqual(len(self.m.read(ref=current['versionRef'], offset=4000)['text']), 4000)
        historical = self.m.read(ref=current['archiveRef'])
        self.assertEqual(historical['text'], 'archived\r\n')
        self.assertEqual(historical['sha256'], hashlib.sha256(b'\xef\xbb\xbfarchived\r\n').hexdigest())
        self.assertIn('Archived snapshot', historical['freshness'])
        (self.root/'proof.md').write_text('updated original')
        self.assertEqual(self.m.read(ref='source:proof.md')['text'], 'updated original')
        with self.assertRaisesRegex(HubError, 'Source version changed'):
            self.m.read(ref=current['versionRef'], offset=4000)
        (self.root/'proof.md').unlink()
        missing = self.m.read(ref='source:proof.md')
        self.assertFalse(missing['source']['available'])
        self.assertEqual(missing['text'], '')
        self.assertEqual(missing['archiveRef'], 'source-archive:proof.md')
        self.assertEqual(self.m.read(ref=historical['versionRef'])['text'], 'archived\r\n')
        with self.assertRaises(ValueError): self.m.read(ref='source-archive:../secret')

    def test_report_projects_results_and_stage_status(self):
        self.stage()
        self.m.store.record(dict(id='legacy-work',taskId='task',kind='work.started',title='Other ongoing work'))
        w=self.api.call('hub_begin',dict(task='task',stage='viewer',title='Implement search',resources=['src']))
        ack=self.api.call('hub_report',dict(work=w['work'],revision=w['revision'],result='Search verified',status='done',stage_status='done'))
        self.assertEqual(ack['planSync'],'saved')
        stage=self.m.stage('task','viewer')
        self.assertEqual(stage['status'],'done');self.assertEqual(stage['remaining'],[])
        self.assertEqual(stage['done'],['Search verified'])
        # The journal keeps unrelated legacy work. Live coordination deliberately
        # omits it from currentWork once it knows this task has no active agent.
        seed, events = self.m.store._load()
        task = next(t for t in self.m.store.project(seed, events) if t['id'] == 'task')
        self.assertEqual(task['currentWork']['eventId'], 'legacy-work')
        self.assertNotIn('currentWork', self.m.plan('task')['task'])
        self.api.call('hub_report',dict(work=w['work'],revision=w['revision'],result='Search verified',status='done',stage_status='done'))
        self.assertEqual(self.m.stage('task','viewer')['done'],['Search verified'])
    def test_outbox_survives_failed_delivery(self):
        self.stage()
        w=self.api.call('hub_begin',dict(task='task',stage='viewer',title='Part',resources=['src']))
        with patch.object(Memory,'flush_reports',side_effect=OSError('offline')):
            ack=self.api.call('hub_report',dict(work=w['work'],revision=w['revision'],result='Saved',status='done'))
        self.assertEqual(ack['planSync'],'pending')
        self.api.call('hub_context',{})
        self.assertEqual(self.m.stage('task','viewer')['done'],['Saved'])
        self.assertEqual(self.m.stage('task','viewer')['status'],'active')
    def test_other_open_work_defers_stage_completion_after_saving_result(self):
        self.stage()
        a=self.api.call('hub_begin',dict(task='task',stage='viewer',title='A',resources=['a']))
        b=self.api.call('hub_begin',dict(task='task',stage='viewer',title='B',resources=['b']))
        ack=self.api.call('hub_report',dict(work=a['work'],revision=a['revision'],result='Done A',status='done',stage_status='done'))
        self.assertEqual(ack['status'],'done')
        deferred=ack['stageCompletionDeferred']
        self.assertEqual(deferred['openWorkCount'],1)
        self.assertEqual([item['id'] for item in deferred['openWork']],[b['work']])
        self.assertIn('remains open',deferred['message'])
        self.assertEqual(self.m.stage('task','viewer')['status'],'active')
        self.assertEqual(self.m.stage('task','viewer')['done'],['Done A'])
        self.assertEqual(self.m.stage('task','viewer')['remaining'],['Search'])
        final=self.api.call('hub_report',dict(work=b['work'],revision=b['revision'],result='Done B',status='done',stage_status='done'))
        self.assertNotIn('stageCompletionDeferred',final)
        self.assertEqual(self.m.stage('task','viewer')['status'],'done')
        self.assertEqual(self.m.stage('task','viewer')['remaining'],[])

if __name__=='__main__': unittest.main()
