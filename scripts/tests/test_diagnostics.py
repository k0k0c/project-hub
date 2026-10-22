"""Compact diagnostics never expand detailed coordination records."""
from contextlib import closing, contextmanager
import json
import sqlite3
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from test_subagent_portal import fixture, Hub, Store, PortalServer, PARENT, CHILD, UNKNOWN
from codex_session_catalog import SessionCatalog


class DiagnosticsTest(unittest.TestCase):
    def test_snapshot_does_not_read_work_results_claims_or_attempts(self):
        with fixture() as (store, hub, handles):
            queries = []
            connect = Hub.connect

            @contextmanager
            def traced(instance):
                with connect(instance) as connection:
                    connection.set_trace_callback(queries.append)
                    yield connection

            with patch.object(Hub, 'connect', traced), patch.object(Hub, 'overview', side_effect=AssertionError('archive accessed')), patch.object(Store, 'team_projection', side_effect=AssertionError('team accessed')):
                result = store.snapshot()['coordination']
            self.assertTrue(result['available'], result)
            self.assertFalse({'work', 'team', 'attempts', 'claims'} & result.keys())
            self.assertNotIn('CATALOG-VERIFIED', json.dumps(result))
            statements = '\n'.join(queries).lower()
            self.assertNotIn('from claims', statements)
            self.assertNotIn('from resource_attempts', statements)
            self.assertNotIn('w.*', statements)
            self.assertNotIn('select * from work', statements)
            sessions = {s['id']: s for s in result['sessions']}
            self.assertEqual(sessions[PARENT]['childCount'], 3)
            self.assertEqual(sessions[CHILD]['parentSession'], PARENT)
            self.assertEqual(sessions[UNKNOWN]['state'], 'unknown')
            self.assertEqual(sessions[UNKNOWN]['integration'], 'discovered')
            self.assertNotIn('activeWork', sessions[PARENT])

    def test_bound_and_revision_are_stable(self):
        with fixture() as (store, hub, handles):
            first = store.diagnostics(limit=2)
            second = store.diagnostics(limit=2)
            self.assertEqual(first, second)
            self.assertEqual(len(first['sessions']), 2)
            self.assertEqual(first['sessionCount'], 4)
            self.assertTrue(first['more'])

    def test_temporary_catalog_excludes_other_projects(self):
        with fixture() as (store, hub, handles):
            other = store.root.parent / 'other'
            data = other / 'docs/project-portal'
            data.mkdir(parents=True)
            (data / 'project.json').write_text(json.dumps(dict(schemaVersion=1, id='other', name='Other', tasks=[])), encoding='utf-8')
            hub.register(other)
            hub.lifecycle(dict(session_id='foreign-session', cwd=str(other), hook_event_name='SessionStart'), 'foreign-start')
            database = store.root.parent / 'catalog.sqlite'
            with closing(sqlite3.connect(database)) as connection:
                connection.execute('CREATE TABLE threads(id TEXT,name TEXT,cwd TEXT,updated_at INTEGER,archived INTEGER,source TEXT)')
                connection.executemany('INSERT INTO threads VALUES (?,?,?,?,?,?)', [
                    ('local-discovered', 'Local', str(store.root), 1, 0, 'vscode'),
                    ('foreign-discovered', 'Foreign', str(other), 2, 0, 'vscode')])
                connection.commit()
            with patch('codex_session_catalog.CATALOG', SessionCatalog(database, ttl=0)):
                result = store.diagnostics()
            self.assertTrue(result['available'], result)
            ids = {s['id'] for s in result['sessions']}
            self.assertIn('local-discovered', ids)
            self.assertNotIn('foreign-session', ids)
            self.assertNotIn('foreign-discovered', ids)

    def test_failure_does_not_hide_task_journal(self):
        with fixture() as (store, hub, handles), patch.object(Hub, 'locate', side_effect=RuntimeError('offline')):
            result = store.snapshot()
            self.assertFalse(result['coordination']['available'])
            self.assertEqual(result['tasks'][0]['id'], 'task')

    def test_http_summary_and_on_demand_archive(self):
        with fixture() as (store, hub, handles):
            server = PortalServer(('127.0.0.1', 0), store)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                def read(route):
                    with urlopen(f'http://127.0.0.1:{server.server_port}{route}') as response:
                        return json.load(response)
                self.assertNotIn('work', read('/api/diagnostics'))
                self.assertIn('work', read('/api/diagnostics/archive'))
                self.assertIn('work', read('/api/coordination'))
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
