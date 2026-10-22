"""Coordination contracts using isolated projects; never touches the live hub."""
import concurrent.futures
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import shutil
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[2] / 'tools/project-portal/plugins/project-hub'
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
sys.path.insert(0, str(PLUGIN / 'scripts'))
from project_portal import Store
from hub_core import Hub, HubError, overlaps
from hub_plugin import Mcp, changed_paths, flush, hook, migration_resource, migration_roots


class CoordinationTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'project'
        data = self.root / 'docs/project-portal'
        data.mkdir(parents=True)
        (data / 'project.json').write_text(json.dumps(dict(schemaVersion=1, id='test', name='Test',
            tasks=[dict(id='task', title='Existing', status='active', stages=[])])), encoding='utf-8')
        self.external_data = Path(self.tmp.name) / 'hub-data'
        shutil.copytree(data, self.external_data)
        self.hub = Hub(Path(self.tmp.name) / 'shared')
        self.hub.register(self.root)
        self.store = Store(self.root, data_dir=self.external_data, coordination_home=self.hub.home)
        self.hub.store_factory = lambda project: self.store
        for sid in ('a', 'b'):
            self.hub.lifecycle(self.event(sid), 'start-' + sid)

    def tearDown(self):
        self.tmp.cleanup()

    def event(self, sid='a', kind='SessionStart'):
        return dict(session_id=sid, cwd=str(self.root), hook_event_name=kind)

    def begin(self, sid='a', path='src/core'):
        return self.hub.begin(sid, 'task', 'Implement', [path])

    def test_same_task_steps_are_independent_and_completion_releases_only_own(self):
        a, b = self.begin(), self.begin('b', 'src/ui')
        self.hub.report('a', a['work'], a['revision'], 'Verified', status='done')
        active = self.hub.overview('test')['work']
        self.assertEqual([w['id'] for w in active], [b['work']])
        self.begin('a', 'src/core')
        overlap = self.begin('a', 'src/ui')
        self.assertEqual(overlap['warning'], 'resource_overlap')
        self.assertGreaterEqual(overlap['conflictCount'], 1)
        retry = self.begin('a', 'src/ui')
        self.assertEqual(retry['work'], overlap['work'])
        self.assertEqual(len(self.hub.overview('test')['work']), 2)

    def test_concurrent_processes_both_get_distinct_advisory_work(self):
        code = ('import sys;sys.path.insert(0,sys.argv[1]);from hub_core import Hub;'
                'h=Hub(sys.argv[2]); print(h.begin(sys.argv[3],"task","race",["src/shared"]))')
        processes = [subprocess.Popen([sys.executable, '-c', code, str(PLUGIN / 'scripts'), str(self.hub.home), sid],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE) for sid in ('a', 'b')]
        codes = []
        for p in processes:
            out, err = p.communicate(timeout=15)
            codes.append(p.returncode)
            self.assertFalse(err, err)
        self.assertEqual(sorted(codes), [0, 0])

    def test_nested_paths_conflict_but_siblings_do_not(self):
        self.begin(path='src/core/Node.java')
        overlap = self.begin('b', 'src/core')
        self.assertEqual(overlap['warning'], 'resource_overlap')
        self.begin('b', 'src/core2')
        self.assertFalse(overlaps('src/a', 'src/abc'))

    def test_conflict_diagnostic_is_durable_and_work_is_still_acquired(self):
        owner = self.begin()
        second = self.begin('b', 'src/core/Node.java')
        self.assertEqual(second['warning'], 'resource_overlap')
        self.assertEqual(second['conflictCount'], 1)
        snapshot = self.hub.overview('test')
        self.assertEqual(len(snapshot['attempts']), 1)
        attempt = snapshot['attempts'][0]
        self.assertEqual(attempt['state'], 'overlap')
        self.assertEqual(attempt['acquired'], second['work'])
        self.assertEqual(attempt['blockers'][0]['id'], owner['work'])
        self.assertEqual(attempt['blockers'][0]['task'], 'task')
        self.assertEqual(len(snapshot['work']), 2)

    def test_diagnostic_schema_upgrade_preserves_claims(self):
        owner = self.begin()
        with self.hub.connect() as c:
            c.execute('DROP TABLE resource_attempts')
        self.hub.setup()
        self.assertEqual(self.hub.overview('test')['work'][0]['id'], owner['work'])
        second = self.begin('b')
        self.assertEqual(second['warning'], 'resource_overlap')
        self.assertEqual(self.hub.overview('test')['attempts'][0]['state'], 'overlap')

    def test_read_claims_coexist_and_exclude_write(self):
        self.hub.begin('a', 'task', 'Read', ['src/core'], mode='read')
        self.hub.begin('b', 'task', 'Read', ['src/core'], mode='read')
        write = self.begin()
        self.assertEqual(write['warning'], 'resource_overlap')

    def test_own_read_to_write_transition_is_advisory_and_keeps_diagnostic(self):
        read = self.hub.begin('a', 'task', 'Read', ['src/core'], mode='read')
        write = self.hub.begin('a', 'task', 'Write', ['src/core'], mode='write')
        self.assertNotEqual(read['work'], write['work'])
        self.assertEqual(write['warning'], 'resource_overlap')
        self.assertGreaterEqual(write['conflictCount'], 1)
        conflict = write['conflicts'][0]
        self.assertEqual(conflict['id'], read['work'])
        self.assertEqual(conflict['session'], 'a')
        self.assertEqual(conflict['status'], 'active')
        self.assertEqual(conflict['name'], 'src/core')
        self.assertEqual(conflict['mode'], 'read')
        self.assertIn('task', conflict)
        self.assertIn('stage', conflict)
        self.assertIn('ownerSeen', conflict)

    def test_broad_overlap_reports_bounded_conflicts_and_succeeds(self):
        owners = [self.begin('a', 'src/' + str(i)) for i in range(12)]
        result = self.hub.begin('b', 'task', 'Broad', ['src'], mode='write')
        self.assertEqual(result['warning'], 'resource_overlap')
        self.assertEqual(result['conflictCount'], len(owners))
        self.assertLessEqual(len(json.dumps(result['conflicts'])), 4500)
        self.assertLessEqual(len(result['conflicts']), result['conflictCount'])
        self.assertEqual(self.hub.overview('test')['work'][-1]['id'], result['work'])

    def test_named_resource_is_shared(self):
        self.begin(path='resource:bitwig-device')
        overlap = self.begin('b', 'resource:bitwig-device')
        self.assertEqual(overlap['warning'], 'resource_overlap')

    def test_other_session_cannot_complete_work(self):
        w = self.begin()
        with self.assertRaises(HubError) as e:
            self.hub.report('b', w['work'], w['revision'], 'Hijacked', status='done')
        self.assertEqual(e.exception.body['error'], 'not_owner')
        self.assertEqual(len(self.hub.overview('test')['work']), 1)

    def test_completed_work_in_another_project_is_not_reused(self):
        first = self.begin()
        self.hub.report('a', first['work'], first['revision'], 'Other project result', status='done')
        other = Path(self.tmp.name) / 'other'
        data = other / 'docs/project-portal'
        data.mkdir(parents=True)
        seed = json.loads((self.root / 'docs/project-portal/project.json').read_text())
        seed['id'] = 'other'
        (data / 'project.json').write_text(json.dumps(seed), encoding='utf-8')
        self.hub.register(other)
        self.hub.lifecycle(dict(session_id='c', cwd=str(other), hook_event_name='SessionStart'), 'start-c')
        second = self.begin('c')
        self.assertEqual(second['status'], 'active')
        self.assertNotEqual(first['work'], second['work'])

    def test_stale_report_does_not_erase_new_result(self):
        w = self.begin()
        self.hub.report('a', w['work'], w['revision'], 'Current')
        with self.assertRaises(HubError):
            self.hub.report('a', w['work'], w['revision'], 'Stale')
        self.assertEqual(self.hub.context('a')['own'][0]['result'], 'Current')

    def test_duplicate_hook_receipt_survives_restart(self):
        first = self.hub.lifecycle(self.event(kind='Stop'), 'stop')
        second = Hub(self.hub.home).lifecycle(self.event(kind='Stop'), 'stop')
        self.assertEqual(first, second)
        with self.assertRaises(HubError):
            self.hub.lifecycle(self.event(kind='Interrupt'), 'stop')

    def test_stop_does_not_finish_work_or_release_reservation(self):
        self.begin()
        self.hub.lifecycle(self.event(kind='Stop'), 'stop')
        overlap = self.begin('b')
        self.assertEqual(overlap['warning'], 'resource_overlap')
        self.assertEqual(self.hub.overview('test')['work'][0]['status'], 'active')

    def test_unrelated_project_is_not_auto_registered(self):
        self.assertIsNone(self.hub.locate(Path(self.tmp.name) / 'other'))
        self.assertEqual(hook(self.hub, dict(session_id='other', cwd=self.tmp.name, hook_event_name='SessionStart')), {})

    def test_worktree_uses_registered_git_common_identity(self):
        with patch('hub_core.git_common', return_value='shared-git'):
            # Register a separate fixture to supply a shared Git directory.
            other = Hub(Path(self.tmp.name) / 'other-db')
            other.register(self.root)
            self.assertEqual(other.locate(self.tmp.name)['id'], 'test')
        with patch('hub_core.git_common', return_value='unrelated-git'):
            self.assertIsNone(other.locate(self.tmp.name))

    def test_legacy_guard_reports_scope_without_denying_edits(self):
        unregistered = self.hub.guard('a', ['src/a.java'])
        self.assertTrue(unregistered['allowed'])
        self.assertEqual(unregistered['warning'], 'unregistered_scope')
        self.begin(path='src')
        self.assertTrue(self.hub.guard('a', ['src/a.java'])['allowed'])
        self.assertTrue(self.hub.guard('b', ['src/a.java'])['allowed'])
        self.assertEqual(self.hub.guard('b', ['src/a.java'])['paths'], ['src/a.java'])

    def test_patch_move_guards_both_paths(self):
        paths = changed_paths(dict(tool_name='apply_patch', tool_input=dict(command='*** Update File: src/a.java\n*** Move to: other/b.java')), self.root)
        self.assertEqual(paths, ['src/a.java', 'other/b.java'])

    def test_scoped_migration_requires_grant_and_exclusive_claim(self):
        target = Path(self.tmp.name) / 'independent'
        target.mkdir()
        grant = dict(schemaVersion=1, grants=[dict(session='a', origin=str(self.root), root=str(target))])
        (self.hub.home / 'migration-roots.json').write_text(json.dumps(grant), encoding='utf-8')
        self.assertEqual(migration_roots(self.hub, 'b', self.root), [])
        self.assertEqual(migration_roots(self.hub, 'a', target), [])
        raw = dict(self.event('a', 'PreToolUse'), tool_name='apply_patch',
                   tool_input=dict(command='*** Add File: ' + str(target / 'file.py')))
        self.assertEqual(hook(self.hub, raw), {})
        key = migration_resource(target)
        self.hub.begin('a', 'task', 'Migration', [key])
        self.assertNotIn('hookSpecificOutput', hook(self.hub, raw))
        overlap = self.hub.begin('b', 'task', 'Concurrent migration', [key])
        self.assertEqual(overlap['warning'], 'resource_overlap')
        # A sibling with the same prefix or a traversal must not inherit the grant.
        for outside in (target.parent / 'independent-other/file.py', target / '../outside.py'):
            with self.assertRaises(HubError):
                changed_paths(dict(tool_name='Write', tool_input=dict(path=str(outside))), self.root,
                              external_roots=[target])
        with self.assertRaises(HubError):
            changed_paths(dict(tool_name='apply_patch', tool_input=dict(command=
                '*** Update File: ' + str(target / 'file.py') + '\n*** Move to: ' + str(target.parent / 'outside.py'))),
                self.root, external_roots=[target])

    def test_migration_resource_conflicts_across_projects(self):
        other = Path(self.tmp.name) / 'other-project'
        data = other / 'docs/project-portal'
        data.mkdir(parents=True)
        (data / 'project.json').write_text(json.dumps(dict(schemaVersion=1, id='other', name='Other',
            tasks=[dict(id='task', title='Migration', status='active', stages=[])])))
        self.hub.register(other)
        self.hub.lifecycle(dict(session_id='other', cwd=str(other), hook_event_name='SessionStart'), 'other-start')
        key = migration_resource(other)
        self.hub.begin('a', 'task', 'Migration', [key])
        overlap = self.hub.begin('other', 'task', 'Competing migration', [key])
        self.assertEqual(overlap['warning'], 'resource_overlap')

    def test_hook_never_saves_prompt_or_tool_output(self):
        hook(self.hub, dict(self.event(), prompt='sensitive-prompt', transcript_path='private-file', tool_input='private-tool'))
        with self.hub.connect() as c:
            payload = '\n'.join(r[0] for r in c.execute('SELECT body FROM events'))
        self.assertNotIn('private', payload)
        self.assertNotIn('sensitive', payload)

    def test_unavailable_database_queues_then_delivers_once(self):
        with patch.object(self.hub, 'lifecycle', side_effect=sqlite3.OperationalError('busy')):
            result = hook(self.hub, self.event(kind='Interrupt'))
        self.assertIn('delayed', result['systemMessage'])
        self.assertEqual(flush(self.hub)['delivered'], 1)
        self.assertEqual(flush(self.hub)['delivered'], 0)

    def test_delta_pages_do_not_skip_events(self):
        cursor = self.hub.context('a')['cursor']
        for i in range(7):
            self.hub.lifecycle(self.event(kind='UserPromptSubmit'), 'prompt-' + str(i))
        ids = []
        while True:
            delta = self.hub.context('a', cursor, 2)
            ids.extend(e['seq'] for e in delta['changes'])
            cursor = delta['cursor']
            if not delta['more']:
                break
        self.assertEqual(len(ids), 7)
        self.assertEqual(len(set(ids)), 7)

    def test_invalid_paths_rejected_without_reservation(self):
        for path in ('../a', '/etc', 'C:/private', 'a/../b', 'a//b'):
            with self.assertRaises(HubError):
                self.begin(path=path)
        self.assertEqual(self.hub.overview('test')['work'], [])

    def test_stdio_mcp_real_process(self):
        env = dict(os.environ, PROJECT_HUB_HOME=str(self.hub.home), PROJECT_HUB_URL='')
        requests = [dict(jsonrpc='2.0', id=1, method='initialize', params=dict(protocolVersion='2025-03-26')),
                    dict(jsonrpc='2.0', method='notifications/initialized'),
                    dict(jsonrpc='2.0', id=2, method='tools/list'),
                    dict(jsonrpc='2.0', id=3, method='tools/call', params=dict(name='hub_context', arguments={}))]
        r = subprocess.run([sys.executable, str(PLUGIN / 'scripts/hub_plugin.py'), 'mcp', '--root', str(self.root), '--session', 'a'],
                           input='\n'.join(json.dumps(q) for q in requests) + '\n', text=True, encoding='utf-8',
                           capture_output=True, env=env, timeout=10)
        self.assertEqual(r.returncode, 0, r.stderr)
        responses = [json.loads(line) for line in r.stdout.splitlines()]
        self.assertEqual([r['id'] for r in responses], [1, 2, 3])
        self.assertFalse(responses[-1]['result']['isError'])
        self.assertEqual({t['name'] for t in responses[1]['result']['tools']}, {'hub_context','hub_task','hub_task_update','hub_task_link','hub_task_close','hub_migration_preview','hub_begin','hub_report','hub_wait','hub_memory','hub_plan','hub_settings','hub_checkpoint','hub_git_batch','hub_check','hub_image','hub_artifact','hub_knowledge','hub_notice','hub_review'})

    def test_report_retry_after_restart_is_idempotent(self):
        w = self.begin()
        first = self.hub.report('a', w['work'], w['revision'], 'Complete', status='done')
        second = Hub(self.hub.home).report('a', w['work'], w['revision'], 'Complete', status='done')
        self.assertEqual(first, second)

    def test_begin_retry_does_not_duplicate_reservations(self):
        first = self.begin()
        self.assertEqual(first, self.begin())
        self.assertEqual(len(self.hub.overview('test')['work']), 1)

    def test_prompt_hook_injects_nonblocking_bookkeeping_guidance(self):
        self.begin('b')
        first = hook(self.hub, self.event(kind='UserPromptSubmit'))
        second = hook(self.hub, self.event(kind='UserPromptSubmit'))
        for result in (first, second):
            text = result['hookSpecificOutput']['additionalContext']
            self.assertIn('reuse the best matching task', text)
            self.assertIn('before substantive work', text)
            self.assertIn('Stop/SessionEnd do not complete work', text)
            self.assertIn('not permission to message other chats', text)
            self.assertLess(len(text), 1000)
            self.assertIn('never blocks work', text)
            self.assertNotIn('technical history', text)

    def test_patch_does_not_access_tracking_or_guards(self):
        payload = dict(self.event(kind='PreToolUse'), tool_name='apply_patch', tool_input=dict(command='*** Add File: a'))
        with patch.object(self.hub, 'locate', side_effect=AssertionError('Must not access Hub')), \
             patch.object(self.hub, 'guard', side_effect=AssertionError('Must not check claims')):
            result = hook(self.hub, payload)
        self.assertEqual(result, {})

    def test_subdirectory_paths_resolve_to_workspace(self):
        paths = changed_paths(dict(tool_name='apply_patch', tool_input=dict(command='*** Update File: a.java')),
                              self.root / 'src', self.root)
        self.assertEqual(paths, ['src/a.java'])

    def test_existing_completion_is_returned_instead_of_duplicate_work(self):
        w = self.begin()
        self.hub.report('a', w['work'], w['revision'], 'Function is implemented', status='done')
        repeated = self.begin('b')
        self.assertEqual(repeated['status'], 'done')
        self.assertIn('Function', repeated['result'])
        self.assertEqual(self.hub.overview('test')['work'], [])

    def test_search_finds_completed_neighbor_by_resource(self):
        w = self.begin()
        self.hub.report('a', w['work'], w['revision'], 'Done', status='done')
        result = self.hub.lookup('b', query='src/core')
        self.assertEqual(result['work'][0]['id'], w['work'])
        self.assertEqual(result['work'][0]['status'], 'done')

    def test_task_tool_uses_existing_writer_and_preserves_history(self):
        result = self.hub.create_task('a', 'New task', ['Scope'], ['Acceptance'])
        retry = self.hub.create_task('a', 'New task', ['Scope'], ['Acceptance'])
        self.assertEqual(result['task'], retry['task'])
        self.assertEqual(result['status'], retry['status'])
        self.assertTrue(retry.get('existing'))
        journal = (self.external_data / 'events.jsonl').read_text(encoding='utf-8')
        self.assertEqual(len(journal.splitlines()), 1)
        self.assertEqual(len(self.hub.store_factory('test').snapshot()['tasks']), 2)

    def test_large_delta_is_bounded_without_skipping_remainder(self):
        cursor = self.hub.context('a')['cursor']
        for i in range(5):
            w = self.begin('b', 'src/file' + str(i))
            self.hub.report('b', w['work'], w['revision'], 'r' * 1500, 'c' * 1000, status='done')
        first = self.hub.context('a', cursor)
        self.assertTrue(first['more'])
        self.assertLess(len(json.dumps(first)), 8000)
        seen = first['changes']
        while first['more']:
            first = self.hub.context('a', first['cursor'])
            seen += first['changes']
        self.assertEqual(len(seen), 10)

    def test_future_schema_rejected_before_creating_tables(self):
        with self.hub.connect() as c:
            c.execute('UPDATE meta SET version=99')
        with self.assertRaises(HubError):
            self.hub.setup()
        with self.hub.connect() as c:
            self.assertEqual(c.execute('SELECT version FROM meta').fetchone()[0], 99)

    def test_packaged_hook_command_runs_on_windows_shell(self):
        config = json.loads((PLUGIN / 'hooks/hooks.json').read_text(encoding='utf-8'))
        command = config['hooks']['SessionStart'][0]['hooks'][0]['command']
        isolated_home = Path(self.tmp.name) / 'no local db'
        env = dict(os.environ, PLUGIN_ROOT=str(PLUGIN), PROJECT_HUB_HOME=str(isolated_home), PROJECT_HUB_URL='')
        proc = subprocess.run(command, shell=True, input=json.dumps(self.event()), text=True, encoding='utf-8',
                              capture_output=True, env=env, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout), {})
        self.assertFalse(isolated_home.exists())


if __name__ == '__main__':
    unittest.main()
