"""Private concurrent readers remain usable through a held backup snapshot."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_hub_backup as fixtures
from hub_backup import live_snapshot
from backup_session import active, current
from project_registry import ProjectRegistry
from project_portal import PortalServer
from knowledge_store import KnowledgeStore


class BackupReadSessionTests(unittest.TestCase):
    setUp = fixtures.BackupFixture.setUp

    def held_snapshot(self, entered, release):
        with live_snapshot(self.registry):
            entered.set()
            if not release.wait(10):
                raise AssertionError('Reader checks did not release the private snapshot')

    def test_clock_advances_cold_worker_and_read_routes_without_writer_wait(self):
        project = self.ids['one']
        server = PortalServer(('127.0.0.1', 0), registry=self.registry)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        entered, release = threading.Event(), threading.Event()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                operation = pool.submit(self.held_snapshot, entered, release)
                try:
                    self.assertTrue(entered.wait(8))
                    instant = time.time()
                    with patch('read_models.time.time', return_value=instant + 60):
                        started = time.monotonic()
                        # A worker opened after the barrier may only borrow
                        # the proven schema, never run initializer INSERTs.
                        cold = ProjectRegistry(self.registry.home, self.registry.catalog)
                        self.assertIsNotNone(active(cold))
                        self.assertEqual('one-task', cold.read_models.snapshot(
                            cold.store(project), observations=False, task='one-task')['task']['id'])
                        paths = ['/api/tasks/summary', '/api/tasks/detail?task=one-task',
                                 '/api/history', '/api/settings', '/api/checks', '/api/git',
                                 '/api/knowledge?action=context', '/api/knowledge?action=read&id=doc:example']
                        for path in paths:
                            with self.subTest(path=path):
                                status, body = self.request(server, path + ('&' if '?' in path else '?') + 'project=' + project)
                                self.assertEqual(200, status, body)
                        status, body = self.request(server, '/api/v1/backups/status')
                        self.assertEqual(200, status)
                        self.assertTrue(body['writesPaused'])
                        # Source authorization still belongs to the same owner.
                        source, path = cold.read_models.evidence_origin(project, self.artifact)
                        self.assertEqual(project, source.project_id)
                        self.assertEqual(self.artifact, path)
                        status, body = self.request(server, '/api/v1/settings?project=' + project, {'patch': {}})
                        self.assertEqual(423, status, body)
                        self.assertTrue(body['retryable'])
                        self.assertLess(time.monotonic() - started, 3)
                        broker_entry = {'store': cold.store(project), 'diagnostics': {'revision': 7}}
                        with patch.object(server.event_broker.observers, 'submit', side_effect=AssertionError('Host observation write')):
                            server.event_broker.observe(broker_entry)
                        self.assertEqual(7, broker_entry['diagnostics']['revision'])
                finally:
                    release.set()
                operation.result(timeout=8)
            self.assertIsNone(active(self.registry))
            self.registry.store(project).record({'kind': 'task.updated', 'taskId': 'one-task',
                                                'title': 'After backup', 'patch': {'title': 'Fresh'}})
            state = self.registry.read_models.snapshot(self.registry.store(project), observations=False, task='one-task')
            self.assertEqual('Fresh', state['task']['title'])
        finally:
            release.set()
            server.shutdown()
            server.server_close()
            worker.join()

    def test_unleased_marker_and_wrong_generation_grant_no_read_bypass(self):
        marker = self.registry.home / 'runtime/backup/read-session.json'
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(dict(version=1, dataHome=str(self.registry.home.resolve()), generation=-1, views={})))
        self.assertIsNone(current(self.registry))
        entered, release = threading.Event(), threading.Event()
        with ThreadPoolExecutor(max_workers=1) as pool:
            operation = pool.submit(self.held_snapshot, entered, release)
            try:
                self.assertTrue(entered.wait(8))
                value = json.loads(marker.read_text())
                value['generation'] += 1
                marker.write_text(json.dumps(value))
                self.assertIsNone(active(self.registry))
            finally:
                release.set()
            operation.result(timeout=8)

    def test_changes_during_preparation_release_and_retry_before_publication(self):
        project = self.ids['one']
        prepare = self.registry.read_models.prepare_view
        changed = []
        def racing_prepare(store, key, bucket):
            result = prepare(store, key, bucket)
            if store.project_id == project and not changed:
                changed.append(True)
                # Catalog updates use a separate SQLite writer today. A
                # generation check alone does not prove their metadata stable.
                with self.registry.connect() as db:
                    db.execute('UPDATE spaces SET name=? WHERE id=?', ('Renamed', project))
                store.record({'kind': 'task.updated', 'taskId': 'one-task', 'title': 'During preparation',
                              'patch': {'title': 'New snapshot'}})
            return result
        with patch.object(self.registry.read_models, 'prepare_view', side_effect=racing_prepare):
            with live_snapshot(self.registry):
                self.assertIsNotNone(active(self.registry))
                state = self.registry.read_models.snapshot(self.registry.store(project), observations=False)
                self.assertEqual('Renamed', state['project']['name'])
                self.assertEqual('New snapshot', next(t for t in state['tasks'] if t['id'] == 'one-task')['title'])

    @staticmethod
    def request(server, path, body=None):
        client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=2)
        try:
            client.request('POST' if body is not None else 'GET', path,
                           json.dumps(body) if body is not None else None,
                           {'Content-Type': 'application/json'})
            response = client.getresponse()
            return response.status, json.loads(response.read())
        finally:
            client.close()


if __name__ == '__main__':
    unittest.main()
