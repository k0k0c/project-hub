"""Fail-open presentation filtering for attested legacy internal research tasks."""
import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from internal_operations import filter_portal_internal_tasks, research_actors


class ReadOnlyFixtureRegistry:
    def __init__(self, home):
        self.home = Path(home)
        self.database = self.home / 'registry.sqlite3'
        self.coordination_database = self.home / 'coordination' / 'coordination.sqlite3'
        self.coordination_database.parent.mkdir(parents=True)

    @staticmethod
    def _connect(path):
        connection = sqlite3.connect(path, isolation_level=None)
        connection.row_factory = sqlite3.Row
        return closing(connection)

    def connect(self):
        return self._connect(self.database)

    def coordination_connect(self):
        return self._connect(self.coordination_database)


class InternalOperationsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.registry = ReadOnlyFixtureRegistry(self.temporary.name)
        with self.registry.connect() as connection:
            connection.execute('''CREATE TABLE api_agent_runs(
                project TEXT,action_id TEXT,signature TEXT,status TEXT,body TEXT,updated REAL)''')
            connection.execute('''CREATE TABLE client_bindings(
                id TEXT,project TEXT,client TEXT,external_id TEXT)''')
        with self.registry.coordination_connect() as connection:
            connection.executescript('''
                CREATE TABLE work(id TEXT,project TEXT,task TEXT,session TEXT);
                CREATE TABLE work_stage_links(work TEXT,stage TEXT);
                CREATE TABLE work_stages(work TEXT,stage TEXT);
            ''')

    @staticmethod
    def action(action_id, task_id, *, research=True, body_action=None, work=None, stage=None, project='p'):
        expected_stage = 'api-analysis-' + hashlib.sha256(action_id.encode()).hexdigest()[:16]
        body = dict(project=project, actionId=body_action if body_action is not None else action_id,
                    research=research, hostTask=task_id, hostStage=stage if stage is not None else expected_stage,
                    work=work if work is not None else 'work-' + action_id)
        return body, expected_stage

    def add_attestation(self, action_id, task_id, *, linked=True, session=None, legacy_binding=False,
                        research=True, body_action=None, body_project='p', stage=None):
        body, expected_stage = self.action(action_id, task_id, research=research,
                                           body_action=body_action, project=body_project, stage=stage)
        work = body['work']
        from agent_runtime import actor_id
        binding = 'legacy-api-binding-' + action_id
        if session is None:
            principal = binding if legacy_binding else 'hub-research:' + hashlib.sha256('p'.encode()).hexdigest()
            session = actor_id(principal, 'api:' + action_id)
        with self.registry.connect() as connection:
            connection.execute('INSERT INTO api_agent_runs VALUES(?,?,?,?,?,?)',
                               ('p', action_id, 'signature', 'done', json.dumps(body), 1))
            if legacy_binding:
                connection.execute('INSERT INTO client_bindings VALUES(?,?,?,?)',
                                   (binding, 'p', 'hub-api', action_id))
        with self.registry.coordination_connect() as connection:
            connection.execute('INSERT INTO work VALUES(?,?,?,?)',
                               (work, 'p', task_id, session))
            if linked:
                connection.execute('INSERT INTO work_stage_links VALUES(?,?)', (work, expected_stage))
        return body, expected_stage

    @staticmethod
    def task(task_id, title, stage_id):
        return dict(id=task_id, title=title, status='active', stages=[dict(id=stage_id, title='Analysis')])

    def test_only_complete_research_provenance_is_hidden_without_mutating_other_state(self):
        action_id = 'legacy-action-1'
        _, stage = self.add_attestation(action_id, 'generated-task')
        legacy_action = 'legacy-app-action'
        _, legacy_stage = self.add_attestation(legacy_action, 'legacy-generated-task', legacy_binding=True)
        malformed_stage = 'api-analysis-' + hashlib.sha256(b'malformed-action').hexdigest()[:16]
        _, missing_link_stage = self.add_attestation('missing-link-action', 'missing-link-task', linked=False)
        _, mismatched_stage = self.add_attestation('mismatch-action', 'mismatch-task', body_action='different-action')
        _, wrong_session_stage = self.add_attestation('wrong-session-action', 'wrong-session-task', session='manual-session')
        _, raw_session_stage = self.add_attestation('raw-session-action', 'raw-session-task',
                                                    session='api:raw-session-action')

        original = dict(
            revision=42,
            tasks=[self.task('generated-task', f'API research {action_id}', stage),
                   self.task('user-task', f'API research {action_id}', stage),
                   self.task('legacy-generated-task', f'API research {legacy_action}', legacy_stage),
                   self.task('missing-link-task', 'API research missing-link-action', missing_link_stage),
                   self.task('mismatch-task', 'API research mismatch-action', mismatched_stage),
                   self.task('wrong-session-task', 'API research wrong-session-action', wrong_session_stage),
                   self.task('raw-session-task', 'API research raw-session-action', raw_session_stage),
                   self.task('malformed-task', 'API research malformed-action', malformed_stage)],
            mainTask={'task': 'generated-task', 'reason': 'explicit'},
            events=[{'seq': 1}], allEvents=[{'seq': 2}], history={'items': [{'id': 'history'}]},
            task={'id': 'generated-task', 'detailLoaded': True}, resultRef={'id': 'preserved'})

        result = filter_portal_internal_tasks(self.registry, 'p', original)
        ids = {item['id'] for item in result['tasks']}
        self.assertNotIn('generated-task', ids)
        self.assertNotIn('legacy-generated-task', ids, 'legacy hub-api bindings use their derived actor ID')
        self.assertIn('user-task', ids, 'a same-title task without matching provenance stays visible')
        self.assertIn('missing-link-task', ids)
        self.assertIn('mismatch-task', ids)
        self.assertIn('wrong-session-task', ids)
        self.assertIn('raw-session-task', ids, 'raw api: IDs are not Hub actor identities')
        self.assertIn('malformed-task', ids)
        self.assertEqual(result['mainTask'], {'task': None, 'reason': 'none'})
        for key in ('revision', 'events', 'allEvents', 'history', 'task', 'resultRef'):
            self.assertEqual(result[key], original[key], key)
        self.assertEqual(len(original['tasks']), 8, 'the source read-model snapshot remains unchanged')

    def test_unrelated_main_task_is_preserved(self):
        action_id = 'legacy-action-2'
        _, stage = self.add_attestation(action_id, 'generated-task')
        original = dict(tasks=[self.task('generated-task', f'API research {action_id}', stage),
                               self.task('user-task', 'User work', 'stage-user')],
                        mainTask={'task': 'user-task', 'reason': 'explicit'})
        result = filter_portal_internal_tasks(self.registry, 'p', original)
        self.assertEqual(result['mainTask'], original['mainTask'])
        self.assertEqual([item['id'] for item in result['tasks']], ['user-task'])

    def test_missing_provenance_tables_fail_open(self):
        action_id = 'legacy-action-3'
        _, stage = self.add_attestation(action_id, 'generated-task')
        # Removing a provenance table must leave the old task visible.
        with self.registry.coordination_connect() as connection:
            connection.execute('DROP TABLE work_stage_links')
            connection.execute('DROP TABLE work_stages')
        snapshot = dict(tasks=[self.task('generated-task', f'API research {action_id}', stage)])
        self.assertEqual(filter_portal_internal_tasks(self.registry, 'p', snapshot)['tasks'], snapshot['tasks'])
        with self.registry.connect() as connection:
            connection.execute('DROP TABLE api_agent_runs')
        self.assertEqual(filter_portal_internal_tasks(self.registry, 'p', snapshot)['tasks'], snapshot['tasks'])

    def test_chat_service_actors_require_matching_ledger_and_keep_legacy_evidence(self):
        from agent_runtime import actor_id
        _, _ = self.add_attestation('legacy', 'generated', legacy_binding=True)
        principal = 'hub-research:' + hashlib.sha256(b'p').hexdigest()
        with self.registry.connect() as connection:
            for action, body in [('internal', dict(project='p', actionId='internal', research=True)),
                                 ('wrong', dict(project='other', actionId='wrong', research=True))]:
                connection.execute('INSERT INTO api_agent_runs VALUES(?,?,?,?,?,?)',
                                   ('p', action, 'signature', 'done', json.dumps(body), 1))
        actors = research_actors(self.registry, 'p')
        self.assertIn(actor_id('legacy-api-binding-legacy', 'api:legacy'), actors)
        self.assertIn(actor_id(principal, 'api:internal'), actors)
        self.assertNotIn(actor_id(principal, 'api:wrong'), actors)


if __name__ == '__main__':
    unittest.main()
