import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_registry import ProjectRegistry, CodexProjects
from project_portal import PortalServer
from task_transfer import transfer
from plugin_api import call, HubError
from hub_http import Client
from hub_plugin import Mcp


class PluginApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.base=Path(self.tmp.name)
        for name in ('a','b'):(self.base/name).mkdir()
        catalog=self.base/'catalog.json'
        catalog.write_text(json.dumps({'local-projects':{k:dict(id=k,name=k,rootPaths=[str(self.base/k)]) for k in ('a','b')}}))
        self.registry=ProjectRegistry(self.base/'data',CodexProjects(catalog))
        self.ids={p['name']:p['id'] for p in self.registry.list()['projects']}
        self.server=PortalServer(('127.0.0.1',0),registry=self.registry)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.client=Client('http://127.0.0.1:'+str(self.server.server_port))

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()

    def invoke(self,project,tool,**args):
        return self.client.call(self.base/project,'session-'+project,tool,args)

    def test_registered_plan_read_does_not_take_the_writer_barrier(self):
        self.invoke('a', 'hub_context')
        task = self.invoke('a', 'hub_task', title='Parallel plan', scope=['API'], acceptance=['Readable'])['task']
        self.invoke('a', 'hub_plan', task=task)
        body = dict(cwd=str(self.base/'a'), session='session-a', tool='hub_plan', arguments=dict(task=task))
        with patch('plugin_api.barrier', side_effect=AssertionError('pure read took writer barrier')), \
                patch('plugin_api.ServerHub.transaction', side_effect=AssertionError('pure read reserved a SQLite writer')), \
                patch('hub_plugin.flush', side_effect=AssertionError('pure read flushed lifecycle outbox')), \
                patch('hub_memory.Memory.flush_reports', side_effect=AssertionError('pure read flushed plan outbox')):
            result = call(self.registry, body)
        self.assertEqual(task, result['task']['id'])

    def test_registered_plan_checks_git_boundary_once_per_api_call(self):
        self.invoke('a', 'hub_context')
        task = self.invoke('a', 'hub_task', title='Git cache plan', scope=['API'], acceptance=['Readable'])['task']
        from plugin_api import git_common
        with patch('plugin_api.git_common', wraps=git_common) as checked:
            first = self.invoke('a', 'hub_plan', task=task)
            second = self.invoke('a', 'hub_plan', task=task)
        self.assertEqual(task, first['task']['id'])
        self.assertEqual(task, second['task']['id'])
        self.assertEqual(2, checked.call_count)

    def test_warm_context_uses_indexed_links_without_full_inventory(self):
        self.invoke('a', 'hub_context')
        task = self.invoke('a', 'hub_task', title='Indexed context', scope=['API'], acceptance=['Linked'])['task']
        self.invoke('a', 'hub_plan', task=task, stage='api', title='API work', remaining=['Link'])
        work = self.invoke('a', 'hub_begin', task=task, stage='api', title='Implement', resources=['resource:api'])
        self.invoke('a', 'hub_context')
        with patch('task_transfer.inventory', side_effect=AssertionError('warm context performed full inventory')):
            context = self.invoke('a', 'hub_context')
        self.assertTrue(any(item.get('task') == task for item in context.get('taskLinks', [])))
        self.assertTrue(any(item.get('id') == work['work'] for item in context.get('own', [])))

    def test_full_mcp_transfer_and_old_owner_rejection(self):
        context=self.invoke('a','hub_context')
        self.assertEqual(context['project'],self.ids['a'])
        task=self.invoke('a','hub_task',title='Portable task',scope=['API'],acceptance=['Tested'])['task']
        self.invoke('a','hub_plan',task=task,stage='api',title='API',remaining=['Verify'])
        work=self.invoke('a','hub_begin',task=task,stage='api',title='Implement',resources=['src'])
        with self.assertRaisesRegex(ValueError,'active work'):
            transfer(self.registry,self.ids['a'],self.ids['b'],task,preview=True)
        report=self.invoke('a','hub_report',work=work['work'],revision=work['revision'],result='Verified',status='done')
        self.assertEqual(report['planSync'],'saved')
        preview=transfer(self.registry,self.ids['a'],self.ids['b'],task,preview=True)
        transfer(self.registry,self.ids['a'],self.ids['b'],task,preview['revision'],'move')
        with self.assertRaises(HubError):self.invoke('a','hub_begin',task=task,title='Stale',resources=['src'])
        with self.assertRaises(HubError):self.invoke('a','hub_plan',task=task,stage='api',title='Stale')
        plan=self.invoke('b','hub_plan',task=task)
        self.assertIsInstance(plan['revision'],str)
        self.invoke('b','hub_plan',task=task,stage='api',title='Continue',expected=plan['revision'])
        self.invoke('b','hub_plan',task=task,stage='api',title='Continue',expected=plan['revision'])
        memory=self.invoke('b','hub_memory',task=task,query='Verified')
        self.assertTrue(memory['results'])
        self.assertFalse((self.base/'a/docs').exists())
        self.assertFalse((self.base/'b/docs').exists())

    def test_stage_completion_creates_scoped_local_commit(self):
        root = self.base / 'a'
        subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True)
        subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'hub@example.test'], check=True)
        subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Project Hub Test'], check=True)
        (root / 'feature.txt').write_text('before\n', encoding='utf-8')
        subprocess.run(['git', '-C', str(root), 'add', 'feature.txt'], check=True)
        subprocess.run(['git', '-C', str(root), 'commit', '-q', '-m', 'Initial'], check=True)
        settings = self.invoke('a', 'hub_settings')
        self.invoke('a', 'hub_settings', patch={'git': {'autoCommit': True, 'commitOn': 'stage'}},
                    expected=settings['revision'])
        task = self.invoke('a', 'hub_task', title='Commit task', scope=['feature.txt'], acceptance=['Committed'])['task']
        self.invoke('a', 'hub_plan', task=task, stage='implementation', title='Implementation', remaining=['Change'])
        work = self.invoke('a', 'hub_begin', task=task, stage='implementation', title='Implement', resources=['feature.txt'])
        (root / 'feature.txt').write_text('after\n', encoding='utf-8')
        report = self.invoke('a', 'hub_report', work=work['work'], revision=work['revision'], result='Implemented', status='done', stage_status='done')
        self.assertEqual(report['planSync'], 'saved')
        deadline = time.monotonic() + 10
        while True:
            stage = next(s for s in self.registry.store(self.ids['a']).snapshot()['tasks'][0]['stages'] if s['id'] == 'implementation')
            checkpoint = stage.get('gitCheckpoint', {})
            if checkpoint and checkpoint['status'] != 'pending':
                break
            if time.monotonic() >= deadline:
                self.fail('Checkpoint did not settle within 10s: ' + repr(stage))
            time.sleep(.05)
        self.assertEqual(stage['status'], 'done')
        self.assertEqual(checkpoint['status'], 'committed', checkpoint)
        self.assertEqual(stage['gitCommit']['status'], 'committed')
        self.assertTrue(stage['gitCommit']['sha'])
        message = subprocess.run(['git', '-C', str(root), 'log', '-1', '--format=%B'], check=True, capture_output=True, text=True).stdout
        self.assertIn('Project-Hub-Task: ' + task, message)

    def test_stale_close_cannot_commit_before_revision_validation(self):
        task = self.invoke('a', 'hub_task', title='Close revision', scope=['API'], acceptance=['Safe'])['task']
        self.invoke('a', 'hub_plan', task=task, stage='only', title='Done', status='done')
        stale = self.invoke('a', 'hub_plan', task=task)['revision']
        store = self.registry.store(self.ids['a'])
        store.record(dict(taskId=task, kind='note', title='Concurrent change'))
        before = store.snapshot()['revision']
        with patch('hub_core.Hub._commit_single_stage') as commit:
            with self.assertRaises(HubError):
                self.invoke('a', 'hub_task_close', task=task, expected=stale, mode='auto')
            commit.assert_not_called()
        self.assertEqual(store.snapshot()['revision'], before)

    def test_session_cannot_change_project(self):
        self.invoke('a','hub_context')
        with self.assertRaises(HubError):self.client.call(self.base/'b','session-a','hub_context',{})

    def test_documented_review_lifecycle_publishes_plan_result_and_sources(self):
        task=self.invoke('a','hub_task',title='Review',scope=['Inspect'],acceptance=['Report attached'])['task']
        plan=self.invoke('a','hub_plan',task=task)
        args=dict(task=task,stage='review',title='Review',remaining=['Inspect'],expected=plan['revision'])
        self.invoke('a','hub_plan',**args)
        self.invoke('a','hub_plan',**args)
        plan=self.invoke('a','hub_plan',task=task)
        self.assertEqual(len(plan['task']['stages']),1)
        with self.assertRaises(HubError):
            self.invoke('a','hub_plan',task=task,stage='stale',title='Stale',expected=args['expected'])
        work=self.invoke('a','hub_begin',task=task,stage='review',title='Inspect',
                         mode='read',resources=['resource:review'])
        (self.base/'a'/'review.md').write_text('# Review\nVerified result.',encoding='utf-8')
        sources=[{'label':'Review report','path':'review.md'}]
        plan=self.invoke('a','hub_plan',task=task)
        self.invoke('a','hub_task_update',task=task,expected=plan['revision'],patch={'sources':sources})
        report=self.invoke('a','hub_report',work=work['work'],revision=work['revision'],
                           result='Verified result',status='done',stage_status='done',evidence=['review.md'])
        self.assertEqual(report['planSync'],'saved')
        published=self.invoke('a','hub_plan',task=task)
        self.assertEqual(published['task']['sources'],sources)
        self.assertEqual(published['task']['stages'][0]['done'],['Verified result'])
        self.assertEqual(published['task']['stages'][0]['status'],'done')
        source=self.invoke('a','hub_memory',ref='source:review.md')
        self.assertIn('Verified result.',source['text'])
        self.assertTrue(source['source']['available'])
        closed=self.invoke('a','hub_task_close',task=task,expected=published['revision'],mode='auto')
        self.assertEqual(closed['status'],'done')
        state=self.registry.store(self.ids['a']).snapshot()
        self.assertEqual(state['tasks'][0]['sources'],sources)
        self.assertTrue(any(e.get('evidence')==[{'path':'review.md','label':'review.md'}]
                            for e in state['allEvents']))

    def test_task_taxonomy_and_nested_links_roundtrip(self):
        epic = self.invoke('a','hub_task',title='Architecture',scope=['Design'],acceptance=['Reviewed'],type='epic',priority='major')['task']
        child = self.invoke('a','hub_task',title='Graph task',scope=['Code'],acceptance=['Tested'],type='task',parentTask=epic)['task']
        state = self.invoke('a','hub_plan',task=epic)
        revision = state['revision']
        self.invoke('a','hub_task_update',task=child,patch={'type':'bug','priority':'critical'},expected=revision)
        state = self.invoke('a','hub_plan',task=epic)
        self.invoke('a','hub_task_link',task=epic,target=child,type='related',expected=state['revision'])
        state = self.invoke('a','hub_plan',task=epic)
        rows = {row['id']: row for row in self.registry.store(self.ids['a']).snapshot()['tasks']}
        self.assertEqual(rows[child]['parentTask'], epic)
        self.assertEqual(rows[child]['type'], 'bug')
        self.assertEqual(rows[child]['priority'], 'critical')
        self.assertEqual(rows[epic]['children'], [child])
        self.assertEqual(rows[epic]['links'][0]['target'], child)

    def test_epic_reports_maximum_priority_of_unfinished_descendants(self):
        epic = self.invoke('a', 'hub_task', title='Priority epic', scope=['Priority'], acceptance=['Reviewed'], type='epic', priority='minor')['task']
        blocker = self.invoke('a', 'hub_task', title='Blocker child', scope=['Priority'], acceptance=['Fixed'], priority='blocker', parentTask=epic)['task']
        critical = self.invoke('a', 'hub_task', title='Critical child', scope=['Priority'], acceptance=['Fixed'], priority='critical', parentTask=epic)['task']
        rows = {row['id']: row for row in self.registry.store(self.ids['a']).snapshot()['tasks']}
        self.assertEqual(rows[epic]['maxDescendantPriority'], 'blocker')
        revision = self.registry.store(self.ids['a']).snapshot()['revision']
        self.invoke('a', 'hub_task_update', task=blocker, patch={'status': 'done'}, expected=revision)
        rows = {row['id']: row for row in self.registry.store(self.ids['a']).snapshot()['tasks']}
        self.assertEqual(rows[epic]['maxDescendantPriority'], 'critical')
        revision = self.registry.store(self.ids['a']).snapshot()['revision']
        self.invoke('a', 'hub_task_update', task=critical, patch={'status': 'cancelled'}, expected=revision)
        rows = {row['id']: row for row in self.registry.store(self.ids['a']).snapshot()['tasks']}
        self.assertIsNone(rows[epic]['maxDescendantPriority'])

    def test_hierarchy_reparenting_rejects_cycles_and_epic_under_task(self):
        ordinary = self.invoke('a', 'hub_task', title='Ordinary parent', scope=['Tree'], acceptance=['Valid'])['task']
        epic = self.invoke('a', 'hub_task', title='Epic parent', scope=['Tree'], acceptance=['Valid'], type='epic')['task']
        child = self.invoke('a', 'hub_task', title='Movable child', scope=['Tree'], acceptance=['Valid'], parentTask=epic)['task']
        revision = self.registry.store(self.ids['a']).snapshot()['revision']
        with self.assertRaises(HubError):
            self.invoke('a', 'hub_task_update', task=epic, patch={'parentTask': ordinary}, expected=revision)
        with self.assertRaises(HubError):
            self.invoke('a', 'hub_task_update', task=epic, patch={'parentTask': child}, expected=revision)
        second_epic = self.invoke('a', 'hub_task', title='Second epic', scope=['Tree'], acceptance=['Valid'], type='epic')['task']
        revision = self.registry.store(self.ids['a']).snapshot()['revision']
        self.invoke('a', 'hub_task_update', task=child, patch={'parentTask': second_epic}, expected=revision)
        row = next(item for item in self.registry.store(self.ids['a']).snapshot()['tasks'] if item['id'] == child)
        self.assertEqual(row['parentTask'], second_epic)

    def test_cross_project_link_keeps_target_project_and_revision_conflicts(self):
        source = self.invoke('a', 'hub_task', title='Source', scope=['Link'], acceptance=['Linked'])['task']
        target = self.invoke('b', 'hub_task', title='Target', scope=['Link'], acceptance=['Linked'])['task']
        revision = self.registry.store(self.ids['a']).snapshot()['revision']
        self.client.call(self.base/'a', 'session-a', 'hub_task_link', {'task': source, 'target': target, 'project': self.ids['b'], 'type': 'related', 'expected': revision})
        source_row = next(row for row in self.registry.store(self.ids['a']).snapshot()['tasks'] if row['id'] == source)
        self.assertEqual(source_row['links'][0]['project'], self.ids['b'])
        after = self.registry.store(self.ids['a']).snapshot()['revision']
        self.assertNotEqual(after, revision)
        with self.assertRaises(HubError) as caught:
            self.invoke('a', 'hub_task_update', task=source, patch={'priority': 'major'}, expected=revision)
        self.assertIn('refresh before writing', caught.exception.body['error'])

    def test_epic_close_supports_manual_warning_and_automatic_completion(self):
        epic = self.invoke('a', 'hub_task', title='Manual epic', scope=['Close'], acceptance=['Closed'], type='epic')['task']
        child = self.invoke('a', 'hub_task', title='Open child', scope=['Close'], acceptance=['Done'], parentTask=epic)['task']
        revision = self.registry.store(self.ids['a']).snapshot()['revision']
        with self.assertRaises(HubError) as caught:
            self.invoke('a', 'hub_task_close', task=epic, expected=revision, mode='auto')
        self.assertIn('incomplete', caught.exception.body.get('error', '').lower())
        manual = self.invoke('a', 'hub_task_close', task=epic, expected=revision, mode='manual', reason='User chose to close')
        self.assertEqual(manual['status'], 'done')
        self.assertIn(child, manual['warning'])

        epic2 = self.invoke('a', 'hub_task', title='Automatic epic', scope=['Close'], acceptance=['Closed'], type='epic')['task']
        child2 = self.invoke('a', 'hub_task', title='Finished child', scope=['Close'], acceptance=['Done'], parentTask=epic2)['task']
        revision = self.registry.store(self.ids['a']).snapshot()['revision']
        self.invoke('a', 'hub_task_update', task=child2, patch={'status': 'done'}, expected=revision)
        revision = self.registry.store(self.ids['a']).snapshot()['revision']
        automatic = self.invoke('a', 'hub_task_close', task=epic2, expected=revision, mode='auto')
        self.assertEqual((automatic['status'], automatic['warning']), ('done', []))

    def test_cancelled_task_remains_in_history_instead_of_being_deleted(self):
        task = self.invoke('a', 'hub_task', title='Cancelled task', scope=['Archive'], acceptance=['Retained'])['task']
        revision = self.registry.store(self.ids['a']).snapshot()['revision']
        self.invoke('a', 'hub_task_update', task=task, patch={'status': 'cancelled'}, expected=revision)
        rows = self.registry.store(self.ids['a']).snapshot()['tasks']
        self.assertEqual(next(row for row in rows if row['id'] == task)['status'], 'cancelled')

    def test_migration_preview_is_read_only_before_classification(self):
        task = self.invoke('a', 'hub_task', title='Legacy task', scope=['Review'], acceptance=['Classified'])['task']
        store = self.registry.store(self.ids['a'])
        before = store.snapshot()['revision']
        preview = self.invoke('a', 'hub_migration_preview')
        row = next(item for item in preview['tasks'] if item['task'] == task)
        self.assertEqual(row['type'], 'task')
        self.assertIsNone(row['priority'])
        self.assertTrue(row['needsReview'])
        self.assertEqual(preview['writes'], 0)
        self.assertEqual(store.snapshot()['revision'], before)
        self.invoke('a', 'hub_task_update', task=task, patch={'type': 'bug', 'priority': 'minor'}, expected=before)
        classified = self.invoke('a', 'hub_migration_preview')
        row = next(item for item in classified['tasks'] if item['task'] == task)
        self.assertEqual((row['type'], row['priority'], row['needsReview']), ('bug', 'minor', False))
        self.assertEqual(classified['writes'], 0)

    def test_migration_preview_preserves_classification_from_task_creation(self):
        created = self.invoke('a', 'hub_task', title='Classified task', scope=['Build'], acceptance=['Verified'], type='bug', priority='critical', weight=3)['task']
        preview = self.invoke('a', 'hub_migration_preview')
        row = next(item for item in preview['tasks'] if item['task'] == created)
        self.assertEqual((row['type'], row['priority'], row['weight'], row['needsReview']), ('bug', 'critical', 3, False))

    def test_hooks_never_block_unreserved_paths_or_send_file_contents(self):
        event=dict(cwd=str(self.base/'a'),session_id='session-a',hook_event_name='SessionStart')
        self.assertIn('additionalContext',self.client.hook(event)['hookSpecificOutput'])
        task=self.invoke('a','hub_task',title='Hook test',scope=['src'],acceptance=['Guard'])['task']
        self.invoke('a','hub_begin',task=task,title='Reserve',resources=['src'])
        edit=dict(event,hook_event_name='PreToolUse',tool_name='apply_patch',
                  tool_input={'patch':'*** Begin Patch\n*** Update File: src/file.py\n+private-content\n*** End Patch'},prompt='private-prompt')
        self.assertNotEqual(self.client.hook(edit).get('hookSpecificOutput',{}).get('permissionDecision'),'deny')
        edit['tool_input']['patch']='*** Update File: other/file.py\n+private-content'
        self.assertEqual(self.client.hook(edit), {})
        from plugin_api import ServerHub
        with ServerHub(self.registry).connect() as c:
            for row in c.execute('SELECT body FROM events'):
                self.assertNotIn('private-content',row[0]);self.assertNotIn('private-prompt',row[0])

    def test_pending_report_prevents_transfer(self):
        task=self.invoke('a','hub_task',title='Pending',scope=['API'],acceptance=['Delivered'])['task']
        from plugin_api import ServerHub
        with ServerHub(self.registry).connect() as c:
            c.execute('INSERT INTO plan_outbox VALUES(?,?,?)',('pending',self.ids['a'],json.dumps({'taskId':task})))
        with self.assertRaisesRegex(ValueError,'pending reports'):
            transfer(self.registry,self.ids['a'],self.ids['b'],task,preview=True)

    def test_transport_does_not_follow_remote_urls_or_fallback(self):
        with self.assertRaises(ValueError):Client('https://example.com')
        client=Client('http://127.0.0.1:1')
        with self.assertRaises(HubError) as caught:client.call(self.base/'a','s','hub_context',{})
        self.assertEqual(caught.exception.body['error'],'server_unavailable')
        mcp=Mcp(None,self.base/'a','session-a',client=self.client)
        self.assertEqual(mcp.call('hub_context',{})['project'],self.ids['a'])


class StandalonePluginApiTest(unittest.TestCase):
    def test_native_plugin_uses_registered_roots_without_a_client_catalog(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base/'code'
            root.mkdir()
            registry = ProjectRegistry(base/'data', standalone=True)
            project = registry.create('Example project', [str(root)])['id']
            server = PortalServer(('127.0.0.1', 0), registry=registry)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                client = Client('http://127.0.0.1:' + str(server.server_port))
                with patch('codex_session_catalog.SessionCatalog.describe',
                           side_effect=AssertionError('Standalone Hub must not read native metadata')):
                    first = client.call(root, 'standalone-session', 'hub_context', {})
                    second = client.call(root, 'standalone-session', 'hub_context', {})
                    task = client.call(root, 'standalone-session', 'hub_task',
                                       dict(title='Inspect registered project', scope=['Inspect'],
                                            acceptance=['Recorded']))['task']
                    plan = client.call(root, 'standalone-session', 'hub_plan', dict(task=task))
                self.assertEqual(first['project'], project)
                self.assertEqual(second['project'], project)
                self.assertEqual(Path(first['workspace']['primaryRoot']), root.resolve())
                self.assertEqual(plan['task']['id'], task)
                with registry.coordination_connect() as connection:
                    row = connection.execute('SELECT project FROM sessions WHERE id=?',
                                             ('standalone-session',)).fetchone()
                self.assertEqual(row['project'], project)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__=='__main__':unittest.main()
