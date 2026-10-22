import concurrent.futures
import json
import time
from unittest.mock import patch

from test_manual_editing import ManualApiCase
from stage_operations import manual_operation
from task_transfer import transfer
from hub_core import Hub
from hub_memory import Memory


class StageOperationsTest(ManualApiCase):
    def coordination(self):
        hub = Hub(self.registry.home / 'coordination')
        hub.setup()
        hub.store_factory = self.registry.store
        with hub.connect() as connection:
            connection.execute('INSERT INTO projects VALUES(?,?,NULL)',
                               (self.pid, str(self.registry.store(self.pid).root)))
            connection.execute('INSERT INTO sessions(id,project,workspace,state,seen) VALUES(?,?,?,?,?)',
                               # Deliberately stale: SQL work must block transfer
                               # even when its session has no live activity badge.
                               ('fixture-session', self.pid, str(self.registry.store(self.pid).root), 'active', 1))
        return hub

    def test_active_and_waiting_reports_preserve_both_tasks_and_work(self):
        source, target = self.task(), self.task()
        stage = self.stage(source, evidence=[{'path': 'proof.txt'}], done=['Already published'])
        hub = self.coordination()
        for affected in (source, target):
            for status in ('active', 'waiting'):
                with self.subTest(task=affected, status=status):
                    with hub.connect() as connection:
                        connection.execute('INSERT INTO work(id,project,session,task,title,status,revision,created,updated,result,evidence) VALUES(?,?,?,?,?,?,1,1,1,?,?)',
                                           ('fixture-work', self.pid, 'fixture-session', affected, 'Unpublished work', status,
                                            'Do not lose this result', '["proof.txt"]'))
                        # Match normal coordination writes: publish a revision
                        # so this case cannot reuse the previous case's view.
                        hub.emit(connection, self.pid, 'fixture-session', 'fixture.work_changed', {})
                        original_work = dict(connection.execute('SELECT * FROM work').fetchone())
                    try:
                        before_clock = time.time()
                        before = self.state()
                        journal = self.registry.base_store(self.pid).journal.read_bytes()
                        result = self.mutate('stages/transfer', {'task': source, 'stage': stage, 'target': target}, expected_status=409)
                        self.assertIn('active work', result['error'])
                        # Cross the display clock boundary deliberately; a
                        # refused write must preserve the current case's state.
                        with patch('read_models.time.time', return_value=before_clock + 11):
                            self.assertEqual(self.state()['tasks'], before['tasks'])
                        self.assertEqual(self.registry.base_store(self.pid).journal.read_bytes(), journal)
                        with hub.connect() as connection:
                            self.assertEqual(dict(connection.execute('SELECT * FROM work').fetchone()), original_work)
                    finally:
                        with hub.connect() as connection:
                            connection.execute('DELETE FROM work')
                            hub.emit(connection, self.pid, 'fixture-session', 'fixture.work_changed', {})

    def test_pending_reports_remain_deliverable_after_rejected_transfer(self):
        source, target = self.task(), self.task()
        stage = self.stage(source)
        target_stage = self.stage(target)
        hub = self.coordination()
        pending = []
        for task, stage_id in ((source, stage), (target, target_stage)):
            payload = {'id': 'report-' + task, 'taskId': task, 'stageId': stage_id,
                       'kind': 'stage.updated', 'title': 'Queued result',
                       'patch': {'appendDone': 'Previously unpublished result', 'evidence': [{'path': 'proof.txt'}]}}
            pending.append((payload['id'], self.pid, json.dumps(payload)))
        with hub.connect() as connection:
            connection.executemany('INSERT INTO plan_outbox VALUES(?,?,?)', pending)
        before = self.state()
        journal = self.registry.base_store(self.pid).journal.read_bytes()
        for route, fields in (('transfer', {'target': target}), ('delete', {}), ('unlink', {})):
            result = self.mutate('stages/' + route, {'task': source, 'stage': stage, **fields}, expected_status=409)
            self.assertIn('pending reports', result['error'])
            self.assertEqual(self.registry.base_store(self.pid).journal.read_bytes(), journal)
            self.assertEqual(self.state()['tasks'], before['tasks'])
            with hub.connect() as connection:
                self.assertEqual([tuple(row) for row in connection.execute('SELECT * FROM plan_outbox ORDER BY rowid')], pending)
        Memory(hub, 'fixture-session').flush_reports()
        with hub.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM plan_outbox').fetchone()[0], 0)
        state = self.mutate('stages/transfer', {'task': source, 'stage': stage, 'target': target})
        destination = next(task for task in state['tasks'] if task['id'] == target)
        for row in destination['stages']:
            self.assertEqual(row['done'], ['Previously unpublished result'])
            self.assertEqual(row['evidence'][0]['path'], 'proof.txt')
        self.assertEqual(self.registry.store(self.pid).read_evidence('proof.txt')[0], b'evidence')

    def test_connected_group_moves_atomically_with_dependency_edges(self):
        source, target = self.task(), self.task()
        first = self.stage(source, id='first')
        second = self.stage(source, id='second', dependsOn=[first])
        third = self.stage(source, id='third', dependsOn=[first])
        unrelated = self.stage(source, id='unrelated')
        state = self.mutate('stages/transfer', {'task': source, 'stage': second, 'target': target, 'includeDependencies': True})
        rows = {t['id']: t for t in state['tasks']}
        self.assertEqual([s['id'] for s in rows[source]['stages']], [unrelated])
        self.assertEqual([s['id'] for s in rows[target]['stages']], [first, second, third])
        self.assertEqual(rows[target]['stages'][1]['dependsOn'], [first])
        self.assertEqual(rows[target]['stages'][2]['dependsOn'], [first])
        event = state['allEvents'][-1]
        self.assertEqual(event['stageIds'], [first, second, third])
        state = self.mutate('stages/transfer', {'task': target, 'stage': first, 'target': source, 'includeDependencies': True})
        rows = {t['id']: t for t in state['tasks']}
        self.assertEqual(len(rows[source]['stages']), 4)
        self.assertEqual(rows[target]['stages'], [])
        history = next(s for s in rows[source]['stages'] if s['id'] == second)['history']
        self.assertEqual(len({e['id'] for e in history}), len(history))

    def test_group_collision_rejects_entire_move(self):
        source, target = self.task(), self.task()
        first = self.stage(source, id='first')
        second = self.stage(source, dependsOn=[first])
        self.stage(target, id='first')
        before = self.state()['revision']
        self.mutate('stages/transfer', {'task': source, 'stage': second, 'target': target, 'includeDependencies': True}, expected_status=409)
        self.assertEqual(self.state()['revision'], before)

    def test_transfer_preserves_payload_history_and_old_journal(self):
        source, target = self.task('Source'), self.task('Target')
        stage = self.stage(source, id='stable', done=['Result'], evidence=[{'path': 'proof.txt', 'label': 'Proof'}])
        base = self.registry.base_store(self.pid)
        before = base.journal.read_bytes()
        state = self.mutate('stages/transfer', {'task': source, 'stage': stage, 'target': target})
        tasks = {t['id']: t for t in state['tasks']}
        self.assertEqual(tasks[source]['stages'], [])
        moved = tasks[target]['stages'][0]
        self.assertEqual((moved['id'], moved['done'], moved['evidence'][0]['path']), ('stable', ['Result'], 'proof.txt'))
        self.assertEqual(moved['history'][0]['stageId'], stage)
        self.assertEqual(tasks[source]['archivedStages'][0]['lifecycle']['action'], 'transferred')
        self.assertTrue(base.journal.read_bytes().startswith(before))
        self.mutate('stages/update', {'task': target, 'stage': stage, 'patch': {'summary': 'Still editable'}})
        self.assertEqual(self.registry.store(self.pid).read_evidence('proof.txt')[0], b'evidence')

    def test_delete_unlink_keep_audit_and_reserve_id(self):
        task = self.task()
        for operation in ('delete', 'unlink'):
            stage = self.stage(task)
            state = self.mutate('stages/' + operation, {'task': task, 'stage': stage, 'reason': 'Manual change'})
            row = state['tasks'][0]
            self.assertEqual(row['stages'], [])
            archived = row['archivedStages'][-1]
            self.assertEqual(archived['id'], stage)
            self.assertEqual(archived['lifecycle']['reason'], 'Manual change')
            self.mutate('stages/create', {'task': task, 'stage': {'id': stage, 'title': 'Reuse'}}, expected_status=409)
            restored = self.mutate('stages/restore', {'task': task, 'stage': stage})
            self.assertEqual(restored['tasks'][0]['stages'][-1]['id'], stage)
            self.assertIn('restoredAt', restored['tasks'][0]['archivedStages'][-1]['lifecycle'])
            self.mutate('stages/restore', {'task': task, 'stage': stage}, expected_status=409)
            self.mutate('stages/delete', {'task': task, 'stage': stage})

    def test_dependency_boundary_and_collision_conflict_without_changes(self):
        source, target = self.task(), self.task()
        first = self.stage(source, id='first')
        second = self.stage(source, dependsOn=[first])
        before = self.state()['revision']
        for stage in (first, second):
            for operation in ('delete', 'unlink', 'transfer'):
                fields = {'task': source, 'stage': stage}
                if operation == 'transfer':
                    fields['target'] = target
                self.mutate('stages/' + operation, fields, expected_status=409)
                self.assertEqual(self.state()['revision'], before)
        self.mutate('stages/update', {'task': source, 'stage': second, 'patch': {'dependsOn': []}})
        self.stage(target, id='first')
        self.mutate('stages/transfer', {'task': source, 'stage': first, 'target': target}, expected_status=409)

    def test_failed_replace_leaves_both_tasks_unchanged(self):
        source, target = self.task(), self.task()
        stage = self.stage(source)
        before = self.state()
        with patch('stage_operations.atomic_write', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                manual_operation(self.registry, self.pid, '/api/v1/stages/transfer',
                                 {'task': source, 'stage': stage, 'target': target, 'expected': before['revision']})
        self.assertEqual(self.state()['tasks'], before['tasks'])
        self.assertEqual(self.state()['revision'], before['revision'])

    def test_two_writers_only_one_wins(self):
        source, target = self.task(), self.task()
        stage = self.stage(source)
        expected = self.state()['revision']
        def move(_):
            return self.request('/api/v1/stages/transfer', {'task': source, 'stage': stage, 'target': target, 'expected': expected})[0]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(move, range(2))), [200, 409])

    def test_foreign_origin_transfer_and_active_work(self):
        source, target = self.task(), self.task(project=self.projects['b'])
        stage = self.stage(source)
        transfer(self.registry, self.projects['b'], self.pid, target,
                 expected=self.state(self.projects['b'])['revision'], request='move-foreign-task')
        store = self.registry.store(self.pid)
        store.record({'taskId': source, 'stageId': stage, 'kind': 'work.started', 'title': 'Active work'})
        for route in ('delete', 'unlink'):
            self.mutate('stages/' + route, {'task': source, 'stage': stage}, expected_status=409)
        self.mutate('stages/transfer', {'task': source, 'stage': stage, 'target': target}, expected_status=409)
        store.record({'taskId': source, 'kind': 'work.completed', 'title': 'Checkpoint'})
        state = self.mutate('stages/transfer', {'task': source, 'stage': stage, 'target': target})
        self.assertEqual(next(t for t in state['tasks'] if t['id'] == target)['stages'][0]['id'], stage)
