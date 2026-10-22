import json
import concurrent.futures
import http.client
import threading
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_registry import ProjectRegistry,CodexProjects
from task_transfer import transfer
from project_portal import PortalServer


class TransferTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        catalog=self.base/'catalog.json'
        catalog.write_text(json.dumps({'local-projects':{k:dict(id=k,name=k,rootPaths=[str(self.base/k)]) for k in ('a','b','c')}}))
        self.registry=ProjectRegistry(self.base/'data',CodexProjects(catalog))
        self.ids={p['name']:p['id'] for p in self.registry.list()['projects']}
        self.source=self.registry.store(self.ids['a']);self.source.root.mkdir()
        (self.source.root/'proof.md').write_text('original-proof')
        self.source.record(dict(kind='task.created',taskId='task',title='Task',patch=dict(title='Task',status='planned',stages=[],sources=[dict(path='proof.md')])) )
        self.source.record(dict(kind='note',taskId='task',title='Research preserved'))

    def tearDown(self):self.tmp.cleanup()

    def move(self,source='a',target='b',request='move'):
        preview=transfer(self.registry,self.ids[source],self.ids[target],'task',preview=True)
        result=transfer(self.registry,self.ids[source],self.ids[target],'task',preview['revision'],request)
        return preview,result

    def test_archived_source_survives_removal_without_bypassing_registration(self):
        archive=self.source.data/'source-archive'
        archive.mkdir()
        (archive/'proof.md').write_text('preserved original')
        (archive/'unregistered.md').write_text('not evidence')
        (self.source.root/'proof.md').unlink()
        self.move()
        target=self.registry.store(self.ids['b'])
        visible=target.snapshot()['tasks'][0]['sources'][0]['path']
        with self.assertRaises(FileNotFoundError):target.evidence(visible)
        self.assertEqual(target.evidence(visible, 'archive'),b'preserved original')
        with self.assertRaises(ValueError):target.evidence('hub-source/'+self.ids['a']+'/unregistered.md')
        with self.assertRaises(ValueError):self.source.resolve_evidence_path('../outside.md')

    def test_new_evidence_after_move_uses_current_project_root(self):
        self.move()
        target=self.registry.store(self.ids['b'])
        target.root.mkdir()
        (target.root/'new-proof.md').write_text('new owner evidence')
        target.record(dict(kind='note',taskId='task',title='New evidence',evidence=[dict(path='new-proof.md')]))
        self.assertEqual(target.evidence('new-proof.md'),b'new owner evidence')
        self.move(source='b',target='c',request='move-again')
        third=self.registry.store(self.ids['c'])
        self.assertEqual(third.evidence('hub-source/'+self.ids['b']+'/new-proof.md'),b'new owner evidence')

    def test_note_rejects_unregistered_foreign_source_provenance(self):
        foreign = self.registry.base_store(self.ids['c'])
        foreign.root.mkdir()
        (foreign.root/'proof.md').write_text('unrelated project proof')
        revision = self.source.snapshot()['revision']
        with self.assertRaises(ValueError):
            self.source.record(dict(kind='note',taskId='task',title='Foreign evidence',
                                    evidence=[dict(path='proof.md',sourceProject=self.ids['c'])]))
        self.assertEqual(self.source.snapshot()['revision'], revision)

    def test_note_rejects_malformed_source_provenance_without_appending(self):
        revision = self.source.snapshot()['revision']
        for source in (None, 123, [], {}, '', 'missing-project'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.source.record(dict(kind='note',taskId='task',title='Malformed evidence',
                                        evidence=[dict(path='proof.md',sourceProject=source)]))
            self.assertEqual(self.source.snapshot()['revision'], revision)

    def test_history_identity_links_and_evidence_survive_roundtrip(self):
        journal=self.source.journal.read_bytes()
        preview,result=self.move()
        self.assertEqual(self.source.snapshot()['tasks'],[])
        target=self.registry.store(self.ids['b']);task=target.snapshot()['tasks'][0]
        self.assertEqual(task['uid'],result['uid'])
        self.assertIn('Research preserved',[e['title'] for e in target.history()['events']])
        self.assertEqual(target.evidence(task['sources'][0]['path']),b'original-proof')
        with self.assertRaises(ValueError):self.source.evidence('proof.md')
        self.assertEqual(self.source.snapshot()['redirects']['task']['project'],self.ids['b'])
        self.assertEqual(self.source.journal.read_bytes(),journal)
        ordered=[e['title'] for e in reversed(target.history()['events'])]
        self.assertLess(ordered.index('Task'),ordered.index('Research preserved'))
        self.assertEqual(transfer(self.registry,self.ids['a'],self.ids['b'],'task',preview['revision'],'move'),result)
        with self.assertRaises(ValueError):self.source.record(dict(kind='note',taskId='task',title='Stale write'))
        target.record(dict(kind='note',taskId='task',title='Continued in target'))
        self.move('b','c','second')
        third=self.registry.store(self.ids['c'])
        self.assertEqual(sum(e['kind']=='task.transferred' for e in third.history()['events']),2)
        self.move('c','a','return')
        self.assertEqual(self.source.snapshot()['tasks'][0]['uid'],result['uid'])

    def test_history_uses_lightweight_event_projection(self):
        view=self.registry.store(self.ids['a'])
        with patch.object(view, 'snapshot', side_effect=AssertionError('full snapshot is not needed')):
            history=view.history()
        self.assertEqual([event['title'] for event in history['events']], ['Research preserved', 'Task'])

    def test_review_owner_hierarchy_accepts_destination_parent_and_rejects_cycle(self):
        self.move()
        target = self.registry.store(self.ids['b'])
        target.record(dict(kind='task.created', taskId='parent', title='Parent',
                           patch=dict(title='Parent', status='active', type='epic', stages=[])))
        target.record(dict(kind='task.updated', taskId='task', title='Set parent',
                           patch=dict(parentTask='parent')))
        tasks = {task['id']: task for task in target.snapshot()['tasks']}
        self.assertEqual(tasks['task']['parentTask'], 'parent')
        self.assertEqual(tasks['parent']['children'], ['task'])
        self.assertEqual(tasks['parent']['completion']['incompleteChildren'], ['task'])
        target.record(dict(kind='task.updated', taskId='task', title='Make epic', patch=dict(type='epic')))
        journal = target.journal.read_bytes()
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            target.record(dict(kind='task.updated', taskId='parent', title='Cycle',
                               patch=dict(parentTask='task')))
        self.assertEqual(target.journal.read_bytes(), journal)
        target.record(dict(kind='task.updated', taskId='task', title='Continue', patch=dict(summary='ok')))

    def test_checkpoint_publication_uses_current_owner_tree_without_git_retry(self):
        from completion_policy import finish_checkpoint
        self.source.record(dict(kind='stage.created', taskId='task', stageId='stage',
                                title='Completed', patch=dict(title='Completed', status='done')))
        with self.registry.connect() as connection:
            saved = dict(connection.execute('SELECT * FROM completion_checkpoints WHERE task=?', ('task',)).fetchone())
        self.move()
        target = self.registry.store(self.ids['b'])
        target.record(dict(kind='task.created', taskId='parent', title='Destination parent',
                           patch=dict(title='Destination parent', type='epic', status='active', stages=[])))
        target.record(dict(kind='task.updated', taskId='task', title='Attach moved task',
                           patch=dict(parentTask='parent')))
        # Simulate the persisted outcome of a completed Git operation whose
        # journal acknowledgement failed. Retry must publish this exact outcome.
        outcome = dict(status='committed', sha='a' * 40, files=['proof.md'],
                       publication=dict(status='pending', reason='Old hierarchy unavailable'))
        with self.registry.connect() as connection:
            connection.execute('UPDATE completion_checkpoints SET result=? WHERE id=?',
                               (json.dumps(outcome), saved['id']))
        before = self.registry.base_store(self.ids['a']).journal.read_bytes()
        with patch('completion_policy.commit_work', side_effect=AssertionError('Git must not rerun')), \
             patch('completion_policy.repository', side_effect=AssertionError('Git must not run')):
            result = finish_checkpoint(self.registry, saved['id'], retry=True)
            again = finish_checkpoint(self.registry, saved['id'], retry=True)
        self.assertEqual(result['sha'], 'a' * 40)
        self.assertNotIn('publication', result)
        self.assertEqual(result, again)
        after = self.registry.base_store(self.ids['a']).journal.read_bytes()
        self.assertTrue(after.startswith(before))
        task = next(t for t in target.memory_snapshot()['tasks'] if t['id'] == 'task')
        self.assertEqual(task['parentTask'], 'parent')
        self.assertEqual(task['stages'][0]['gitCheckpoint']['sha'], 'a' * 40)
        with self.registry.connect() as connection:
            row = connection.execute('SELECT body FROM completion_checkpoints WHERE id=?', (saved['id'],)).fetchone()
        self.assertEqual(row['body'], saved['body'])

    def test_review_transfer_requires_explicit_structural_unlink(self):
        self.source.record(dict(kind='task.created', taskId='parent', title='Parent',
                                patch=dict(title='Parent', status='active', type='epic', stages=[])))
        self.source.record(dict(kind='task.updated', taskId='task', title='Attach',
                                patch=dict(parentTask='parent')))
        for task_id in ('task', 'parent'):
            with self.assertRaisesRegex(ValueError, 'Unlink'):
                transfer(self.registry, self.ids['a'], self.ids['b'], task_id, preview=True)
        self.source.record(dict(kind='task.updated', taskId='task', title='Detach', patch=dict(parentTask=None)))
        self.move()
        self.assertEqual(self.source.snapshot()['tasks'][0]['children'], [])
        target = self.registry.store(self.ids['b'])
        self.assertIsNone(target.snapshot()['tasks'][0]['parentTask'])
        with self.assertRaisesRegex(ValueError, 'Unknown task parent'):
            target.record(dict(kind='task.updated', taskId='task', title='Foreign parent',
                               patch=dict(parentTask='parent')))
        self.assertIn('Attach', [event['title'] for event in target.snapshot()['allEvents']])

    def test_review_legacy_transfer_recomputes_filtered_hierarchy(self):
        self.source.record(dict(kind='task.created', taskId='parent', title='Parent',
                                patch=dict(title='Parent', status='active', type='epic', stages=[])))
        self.source.record(dict(kind='task.updated', taskId='task', title='Attach',
                                patch=dict(parentTask='parent', priority='critical')))
        self.source.record(dict(kind='stage.created', taskId='task', stageId='stage', title='Stage',
                                patch=dict(title='Stage', status='planned')))
        self.source.snapshot()
        with self.registry.connect() as connection:
            connection.execute('UPDATE task_owners SET owner=? WHERE origin=? AND task=?',
                               (self.ids['b'], self.ids['a'], 'task'))
        parent = self.source.snapshot()['tasks'][0]
        self.assertEqual(parent['children'], [])
        self.assertEqual(parent['progressAggregate']['total'], 0)
        self.assertEqual(parent['completion']['incompleteChildren'], [])
        self.assertIsNone(parent['maxDescendantPriority'])
        moved = self.registry.store(self.ids['b']).snapshot()['tasks'][0]
        self.assertIsNone(moved['parentTask'])
        self.assertEqual(moved['progressAggregate']['total'], 1)
        with self.assertRaisesRegex(ValueError, 'Unlink historical'):
            self.move('b', 'a', 'legacy-return')
        with self.assertRaisesRegex(ValueError, 'Unlink historical'):
            transfer(self.registry, self.ids['a'], self.ids['b'], 'parent', preview=True)
        target = self.registry.store(self.ids['b'])
        target.record(dict(kind='task.updated', taskId='task', title='Clear legacy parent',
                           patch=dict(parentTask=None)))
        self.move('b', 'a', 'legacy-return')
        returned = {task['id']: task for task in self.source.snapshot()['tasks']}
        self.assertIsNone(returned['task']['parentTask'])
        self.assertEqual(returned['parent']['children'], [])

    def test_review_stage_commit_materializes_without_git_and_survives_transfer(self):
        self.source.record(dict(kind='stage.created', taskId='task', stageId='stage', title='Stage',
                                patch=dict(title='Stage', status='done')))
        with patch('project_portal.git_history', side_effect=AssertionError('Git discovery under barrier')):
            self.source.record(dict(kind='stage.updated', taskId='task', stageId='stage', title='Commit',
                                    patch=dict(gitCommit=dict(status='committed', sha='a' * 40,
                                                              message='Stage commit', files=['a.txt']))))
            history = self.source.history(kind='git.commit')['events']
            self.assertEqual(len(history), 1)
            event_id = history[0]['id']
            self.assertEqual(len(self.source.history(kind='git.commit')['events']), 1)
            self.move()
            target = self.registry.store(self.ids['b'])
            self.assertEqual(target.history(kind='git.commit')['events'][0]['id'], event_id)
            self.assertEqual(len([e for e in target.snapshot()['allEvents'] if e['kind'] == 'git.commit']), 1)

    def test_review_project_push_is_local_idempotent_and_revision_checked(self):
        state = self.source.snapshot()
        payload = dict(id='push-event', kind='git.push', taskId='__project__', title='Push',
                       git=dict(commits=[], branch='main'))
        self.source.record(payload, expected_revision=state['revision'])
        self.source.record(payload, expected_revision=state['revision'])
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.source.record(dict(payload, id='stale-push'), expected_revision=state['revision'])
        self.move()
        self.assertEqual(len(self.source.history(kind='git.push')['events']), 1)
        self.assertEqual(len([e for e in self.source.snapshot()['allEvents'] if e['kind'] == 'git.push']), 1)
        self.assertEqual(self.registry.store(self.ids['b']).history(kind='git.push')['events'], [])
        with self.assertRaises(ValueError):
            self.source.record(dict(kind='note', taskId='__project__', title='Invalid marker'))

    def test_review_projections_sort_utc_instants_with_stable_ties(self):
        for timestamp, title in [('2026-09-15T03:00:00+03:00', 'Earlier'),
                                 ('2026-09-15T01:00:00Z', 'Later'),
                                 ('2026-09-14T20:00:00-04:00', 'Same instant')]:
            with patch('project_portal.now', return_value=timestamp):
                self.source.record(dict(kind='note', taskId='task', title=title))
        expected = ['Later', 'Same instant', 'Earlier']
        history = self.source.history(kind='note')['events']
        history = [event for event in history if event['title'] != 'Research preserved']
        self.assertEqual([event['title'] for event in history], expected)
        snapshot = self.source.snapshot()
        projected = [event for event in reversed(snapshot['allEvents']) if event['title'] in expected]
        self.assertEqual([(event['id'], event['seq']) for event in projected],
                         [(event['id'], event['seq']) for event in history])
        again = self.source.history(kind='note')['events']
        self.assertEqual([event['id'] for event in again if event['title'] in expected],
                         [event['id'] for event in history])

    def test_stale_preview_and_collision_fail_without_move(self):
        preview=transfer(self.registry,self.ids['a'],self.ids['b'],'task',preview=True)
        self.source.record(dict(kind='note',taskId='task',title='Changed'))
        with self.assertRaisesRegex(ValueError,'changed'):
            transfer(self.registry,self.ids['a'],self.ids['b'],'task',preview['revision'],'move')
        self.registry.store(self.ids['b']).record(dict(kind='task.created',taskId='task',title='Other',patch=dict(title='Other',status='planned',stages=[])))
        with self.assertRaisesRegex(ValueError,'already'):self.move()
        self.assertEqual(len(self.source.snapshot()['tasks']),1)

    def test_unfinished_work_blocks_transfer(self):
        self.source.record(dict(kind='work.started',taskId='task',title='Running'))
        with self.assertRaisesRegex(ValueError,'unfinished'):self.move()

    def test_active_coordination_blocks_then_preserves_session_association(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tools/project-portal/plugins/project-hub/scripts'))
        from hub_core import Hub
        hub=Hub(self.registry.home/'coordination');hub.setup()
        with closing(sqlite3.connect(hub.db,isolation_level=None)) as c:
            c.execute("INSERT INTO work(id,project,session,task,title,status,revision,created,updated) VALUES('work',?,'chat','task','Step','active',1,1,1)",(self.ids['a'],))
        with self.assertRaisesRegex(ValueError,'active work'):self.move()
        with closing(sqlite3.connect(hub.db,isolation_level=None)) as c:c.execute("UPDATE work SET status='done'")
        self.move()
        task=self.registry.store(self.ids['b']).snapshot()['tasks'][0]
        self.assertEqual(task['participatingSessions'],['chat'])

    def test_two_competing_transfers_have_one_winner(self):
        preview=transfer(self.registry,self.ids['a'],self.ids['b'],'task',preview=True)
        def attempt(target):
            try:
                transfer(self.registry,self.ids['a'],self.ids[target],'task',preview['revision'],target)
                return True
            except ValueError:return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(attempt,['b','c'])),1)
        self.assertEqual(sum(len(self.registry.store(self.ids[p]).snapshot()['tasks']) for p in ('a','b','c')),1)

    def test_failed_audit_insert_rolls_back_ownership(self):
        preview=transfer(self.registry,self.ids['a'],self.ids['b'],'task',preview=True)
        with self.registry.connect() as c:
            c.execute("CREATE TRIGGER fail_transfer BEFORE INSERT ON task_transfers BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            transfer(self.registry,self.ids['a'],self.ids['b'],'task',preview['revision'],'failed')
        self.assertEqual(len(self.source.snapshot()['tasks']),1)
        self.assertEqual(self.registry.store(self.ids['b']).snapshot()['tasks'],[])

    def test_reserved_prefix_cannot_grant_foreign_file_access(self):
        other=self.registry.store(self.ids['b']);other.root.mkdir()
        (other.root/'secret.txt').write_text('not evidence')
        forged='hub-source/'+self.ids['b']+'/secret.txt'
        self.source.record(dict(kind='note',taskId='task',title='Literal relative path',evidence=[dict(path=forged)]))
        with self.assertRaises(FileNotFoundError):self.source.evidence(forged)

    def test_transfer_http_requires_local_origin_and_json(self):
        server=PortalServer(('127.0.0.1',0),registry=self.registry)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            body=json.dumps(dict(source=self.ids['a'],target=self.ids['b'],task='task'))
            for headers,expected in (({'Content-Type':'application/json','Origin':'https://other.example'},403),
                                     ({'Content-Type':'text/plain'},415),({'Content-Type':'application/json'},200)):
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port)
                connection.request('POST','/api/v1/tasks/transfer/preview',body,headers)
                response=connection.getresponse();self.assertEqual(response.status,expected)
                response.read();connection.close()
        finally:server.shutdown();server.server_close();worker.join()
