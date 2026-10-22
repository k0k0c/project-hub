"""Cross-journal redo and evidence provenance against disposable registries."""
import concurrent.futures
import json
from pathlib import Path
import sqlite3
from unittest.mock import patch

from test_manual_editing import ManualApiCase
from project_registry import ProjectRegistry
from stage_operations import manual_operation
from task_transfer import transfer
from hub_core import Hub


class StageTransferRecoveryTest(ManualApiCase):
    def pair(self, group=False):
        origin = self.projects['b']
        source = self.task('Migrated source', origin)
        (self.registry.store(origin).root / 'proof.txt').write_text('Foreign proof')
        result = self.mutate('stages/create', {'task': source, 'stage': {
            'id': 'stable', 'title': 'Existing result', 'done': ['Preserve result'],
            'evidence': [{'path': 'proof.txt', 'label': 'Original proof'}]}}, origin)
        stage = result['createdStage']
        if group:
            self.mutate('stages/create', {'task': source, 'stage': {
                'id': 'dependent', 'title': 'Dependent', 'dependsOn': [stage]}}, origin)
        transfer(self.registry, origin, self.pid, source,
                 expected=self.state(origin)['revision'], request='migrate-' + source)
        target = self.task('Local destination')
        return source, target, stage

    def body(self, source, target, stage, **extra):
        return {'task': source, 'target': target, 'stage': stage,
                'expected': self.state()['revision'], **extra}

    def interrupt(self, point, body):
        def crash(at):
            if at == point:
                raise RuntimeError('Simulated process exit at ' + point)
        with patch('stage_operations._transfer_checkpoint', side_effect=crash):
            with self.assertRaisesRegex(RuntimeError, 'Simulated process exit'):
                manual_operation(self.registry, self.pid, '/api/v1/stages/transfer', body)

    def restart(self):
        self.registry = ProjectRegistry(self.registry.home, self.registry.catalog)
        self.server.registry = self.registry

    def pending(self):
        with self.registry.connect() as connection:
            return [dict(row) for row in connection.execute("SELECT * FROM stage_transactions WHERE state='pending'")]

    def test_restart_redoes_each_interruption_once(self):
        for point in ('after_intent', 'after_first_write', 'after_second_write'):
            with self.subTest(point=point):
                source, target, stage = self.pair(group=True)
                self.interrupt(point, self.body(source, target, stage, includeDependencies=True))
                pending = self.pending()
                self.assertEqual(len(pending), 1)
                transaction = json.loads(pending[0]['body'])
                materialized = []
                for entry in transaction['journals']:
                    path = self.registry.base_store(entry['project']).journal
                    events = [json.loads(line) for line in path.read_text().splitlines()]
                    materialized.append(sum(event['id'] == entry['event']['id'] for event in events))
                self.assertEqual(materialized, {'after_intent': [0, 0], 'after_first_write': [1, 0],
                                                'after_second_write': [1, 1]}[point])
                self.restart()
                state = self.state()
                tasks = {task['id']: task for task in state['tasks']}
                self.assertEqual(tasks[source]['stages'], [])
                self.assertEqual([s['id'] for s in tasks[target]['stages']], ['stable', 'dependent'])
                self.assertEqual(tasks[target]['stages'][1]['dependsOn'], ['stable'])
                self.assertEqual(tasks[target]['stages'][0]['done'], ['Preserve result'])
                self.assertEqual(self.pending(), [])
                self.assertEqual(self.state()['revision'], state['revision'])
                self.restart()
                self.assertEqual(self.state()['revision'], state['revision'])
                for entry in transaction['journals']:
                    path = self.registry.base_store(entry['project']).journal
                    events = [json.loads(line) for line in path.read_text().splitlines()]
                    self.assertEqual(sum(event['id'] == entry['event']['id'] for event in events), 1)

    def test_divergent_journal_blocks_recovery_without_overwrite(self):
        source, target, stage = self.pair()
        self.interrupt('after_first_write', self.body(source, target, stage))
        transaction = json.loads(self.pending()[0]['body'])
        paths = [self.registry.base_store(entry['project']).journal for entry in transaction['journals']]
        paths[1].write_bytes(paths[1].read_bytes() + b'foreign concurrent change\n')
        before = [path.read_bytes() for path in paths]
        self.restart()
        with self.assertRaisesRegex(ValueError, 'journal diverged'):
            self.state()
        self.assertEqual([path.read_bytes() for path in paths], before)
        self.assertEqual(len(self.pending()), 1)
        with self.assertRaisesRegex(ValueError, 'journal diverged'):
            self.registry.base_store(self.pid).record({'taskId': target, 'kind': 'note', 'title': 'Blocked write'})
        self.assertEqual([path.read_bytes() for path in paths], before)

    def test_baseline_divergence_is_detected_before_first_write(self):
        source, target, stage = self.pair()
        self.interrupt('after_intent', self.body(source, target, stage))
        transaction = json.loads(self.pending()[0]['body'])
        stores = [self.registry.base_store(entry['project']) for entry in transaction['journals']]
        before = [store.journal.read_bytes() for store in stores]
        seed = stores[1].data / 'project.json'
        payload = json.loads(seed.read_text())
        payload['name'] = 'Unexpected baseline edit'
        seed.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, 'baseline changed'):
            self.state()
        self.assertEqual([store.journal.read_bytes() for store in stores], before)

    def test_direct_base_writer_recovers_before_editing_destination(self):
        source, target, stage = self.pair()
        self.interrupt('after_first_write', self.body(source, target, stage))
        self.registry.base_store(self.pid).record({'taskId': target, 'stageId': stage,
            'kind': 'stage.updated', 'title': 'After recovery', 'patch': {'summary': 'New edit'}})
        row = next(t for t in self.state()['tasks'] if t['id'] == target)
        self.assertEqual(row['stages'][0]['summary'], 'New edit')
        self.assertEqual(self.pending(), [])

    def test_foreign_evidence_roundtrip_after_third_project_move(self):
        source, target, stage = self.pair(group=True)
        state = self.mutate('stages/transfer', {'task': source, 'target': target, 'stage': stage, 'includeDependencies': True})
        moved = next(t for t in state['tasks'] if t['id'] == target)['stages'][0]
        path = 'hub-source/' + self.projects['b'] + '/proof.txt'
        self.assertEqual(moved['evidence'][0]['path'], path)
        self.assertEqual(self.registry.store(self.pid).read_evidence(path)[0], b'Foreign proof')
        self.assertTrue(any(e['kind'] == 'stage.created' for e in moved['history']))
        catalog = self.registry.catalog.path
        data = json.loads(catalog.read_text())
        root = Path(self.temp.name) / 'third'
        root.mkdir()
        data['local-projects']['third'] = {'id': 'third', 'name': 'Third', 'rootPaths': [str(root)]}
        catalog.write_text(json.dumps(data))
        third = next(p['id'] for p in self.registry.list()['projects'] if p['codex_id'] == 'third')
        transfer(self.registry, self.pid, third, target, expected=self.state()['revision'], request='third-move')
        evidence = next(t for t in self.state(third)['tasks'] if t['id'] == target)['stages'][0]['evidence']
        evidence[0]['label'] = 'Changed label'
        state = self.mutate('stages/update', {'task': target, 'stage': stage, 'patch': {'evidence': evidence}}, third)
        self.assertEqual(state['tasks'][0]['stages'][0]['evidence'][0]['path'], path)
        sources = [dict(evidence[0], label='Task source')]
        state = self.mutate('tasks/update', {'task': target, 'patch': {'sources': sources}}, third)
        self.assertEqual(state['tasks'][0]['sources'][0]['path'], path)
        self.assertEqual(self.registry.store(third).read_evidence(path)[0], b'Foreign proof')
        (root / 'new.txt').write_text('Current project proof')
        state = self.mutate('stages/update', {'task': target, 'stage': stage, 'patch': {
            'evidence': [*evidence, {'path': 'new.txt', 'label': 'New'}]}}, third)
        self.assertEqual(state['tasks'][0]['stages'][0]['evidence'][1]['sourceProject'], third)
        self.assertEqual(self.registry.store(third).read_evidence('new.txt')[0], b'Current project proof')
        self.mutate('stages/update', {'task': target, 'stage': stage, 'patch': {'evidence': [
            {'path': 'hub-source/' + self.projects['b'] + '/unregistered.txt'}]}}, third, expected_status=409)

    def test_validation_and_stale_revision_leave_no_intent(self):
        source, target, stage = self.pair(group=True)
        self.mutate('stages/transfer', {'task': source, 'target': target, 'stage': stage}, expected_status=409)
        self.stage(target, id='dependent')
        self.mutate('stages/transfer', {'task': source, 'target': target, 'stage': stage, 'includeDependencies': True}, expected_status=409)
        stale = self.body(source, target, stage, includeDependencies=True)
        self.registry.store(self.pid).record({'taskId': target, 'kind': 'note', 'title': 'Concurrent edit'})
        status, _ = self.request('/api/v1/stages/transfer', stale)
        self.assertEqual(status, 409)
        with self.registry.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM stage_transactions').fetchone()[0], 0)

    def test_competing_cross_origin_transfers_have_one_winner(self):
        source, target, stage = self.pair()
        body = self.body(source, target, stage)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _: self.request('/api/v1/stages/transfer', body)[0], range(2)))
        self.assertEqual(sorted(statuses), [200, 409])

    def test_archived_id_conflicts_but_proven_round_trip_preserves_identity(self):
        source, target, stage = self.pair()
        unrelated = self.stage(target, id=stage)
        self.mutate('stages/delete', {'task': target, 'stage': unrelated})
        before = self.state()['revision']
        result = self.mutate('stages/transfer', {'task': source, 'target': target, 'stage': stage}, expected_status=409)
        self.assertIn('archive history', result['error'])
        self.assertEqual(self.state()['revision'], before)
        with self.registry.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM stage_transactions').fetchone()[0], 0)
        destination = self.task('Clean target')
        self.mutate('stages/transfer', {'task': source, 'target': destination, 'stage': stage})
        state = self.mutate('stages/transfer', {'task': destination, 'target': source, 'stage': stage})
        restored = next(t for t in state['tasks'] if t['id'] == source)['stages'][0]
        self.assertEqual(restored['done'], ['Preserve result'])
        self.assertEqual(len(restored['transfers']), 2)
        self.assertEqual(restored['evidence'][0]['path'], 'hub-source/' + self.projects['b'] + '/proof.txt')

    def test_intent_commit_failure_does_not_touch_either_journal(self):
        source, target, stage = self.pair()
        body = self.body(source, target, stage)
        paths = [self.registry.base_store(pid).journal for pid in (self.pid, self.projects['b'])]
        before = [path.read_bytes() for path in paths]
        with self.registry.connect() as connection:
            connection.execute("CREATE TRIGGER fail_stage_intent BEFORE INSERT ON stage_transactions BEGIN SELECT RAISE(ABORT,'intent failed'); END")
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'intent failed'):
            manual_operation(self.registry, self.pid, '/api/v1/stages/transfer', body)
        self.assertEqual([path.read_bytes() for path in paths], before)
        self.assertEqual(self.pending(), [])

    def test_cross_origin_work_and_outbox_block_before_intent(self):
        source, target, stage = self.pair()
        hub = Hub(self.registry.home / 'coordination')
        hub.setup()
        with hub.connect() as connection:
            for pid in (self.pid, self.projects['b']):
                root = str(self.registry.store(pid).root)
                connection.execute('INSERT INTO projects VALUES(?,?,NULL)', (pid, root))
                connection.execute('INSERT INTO sessions(id,project,workspace,state,seen) VALUES(?,?,?,?,1)',
                                   ('fixture-' + pid, pid, root, 'active'))
        paths = [self.registry.base_store(pid).journal for pid in (self.pid, self.projects['b'])]
        before = [path.read_bytes() for path in paths]
        for task, pid in ((source, self.projects['b']), (target, self.pid)):
            for status in ('active', 'waiting'):
                with hub.connect() as connection:
                    connection.execute('INSERT INTO work(id,project,session,task,title,status,revision,created,updated,result) VALUES(?,?,?,?,?,?,1,1,1,?)',
                                       ('reserved', pid, 'fixture-' + pid, task, 'Work', status, 'Preserved result'))
                result = self.mutate('stages/transfer', {'task': source, 'target': target, 'stage': stage}, expected_status=409)
                self.assertIn('active work', result['error'])
                with hub.connect() as connection:
                    self.assertEqual(connection.execute('SELECT result FROM work').fetchone()[0], 'Preserved result')
                    connection.execute('DELETE FROM work')
            payload = json.dumps({'taskId': task, 'kind': 'note', 'title': 'Unpublished report'})
            with hub.connect() as connection:
                connection.execute('INSERT INTO plan_outbox VALUES(?,?,?)', ('report', pid, payload))
            result = self.mutate('stages/transfer', {'task': source, 'target': target, 'stage': stage}, expected_status=409)
            self.assertIn('pending reports', result['error'])
            with hub.connect() as connection:
                self.assertEqual(connection.execute('SELECT payload FROM plan_outbox').fetchone()[0], payload)
                connection.execute('DELETE FROM plan_outbox')
        self.assertEqual([path.read_bytes() for path in paths], before)
        with self.registry.connect() as connection:
            self.assertEqual(connection.execute('SELECT count(*) FROM stage_transactions').fetchone()[0], 0)
