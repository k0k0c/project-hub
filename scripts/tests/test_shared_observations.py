"""Shared display-only diagnostics cache remains bounded and revision-aware."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from concurrent.futures import Future
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from event_broker import EventBroker


class _Registry:
    def __init__(self, root):
        self.home = Path(root)
        self.database = self.home / 'registry.sqlite3'
        catalog = self.home / 'catalog.json'
        catalog.write_text('{}', encoding='utf-8')
        self.catalog = types.SimpleNamespace(path=catalog)

    def connect(self):
        connection = sqlite3.connect(self.database, isolation_level=None, timeout=5)
        connection.row_factory = sqlite3.Row
        return closing(connection)


class SharedObservationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.registry = _Registry(root)
        self.store = types.SimpleNamespace(
            project_id='project-a', registry=self.registry,
            installation_root=root / 'installation', coordination_home=None,
            data=root / 'project')
        self.calls = 0
        self.revision = [0]
        self.call_lock = threading.Lock()

        def diagnostics():
            with self.call_lock:
                self.calls += 1
                call = self.calls
            time.sleep(.05)
            return {'available': True, 'revision': self.revision[0], 'call': call}

        self.store.diagnostics = diagnostics
        self.server = types.SimpleNamespace(stopping=threading.Event())
        self.addCleanup(self.server.stopping.set)

    def _broker(self):
        broker = EventBroker(self.server)
        self.addCleanup(broker.close)
        return broker

    def test_separate_brokers_share_one_compute(self):
        first, second = self._broker(), self._broker()
        barrier = threading.Barrier(2)
        results = []

        def read(broker):
            barrier.wait()
            results.append(broker._shared_diagnostics(self.store))

        workers = [threading.Thread(target=read, args=(broker,)) for broker in (first, second)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(3)
        self.assertEqual(1, self.calls)
        self.assertEqual(results[0], results[1])

    def test_coordination_revision_invalidates_cache(self):
        broker = self._broker()
        with patch.object(broker, 'coordination_revision', side_effect=lambda store: self.revision[0]):
            first = broker._shared_diagnostics(self.store)
            self.revision[0] = 1
            second = broker._shared_diagnostics(self.store)
        self.assertEqual(2, self.calls)
        self.assertEqual(0, first['revision'])
        self.assertEqual(1, second['revision'])

    def test_revision_churn_keeps_one_cache_row_and_lock_directory(self):
        broker = self._broker()
        with patch.object(broker, 'coordination_revision', side_effect=lambda store: self.revision[0]):
            for revision in range(5):
                self.revision[0] = revision
                self.store.diagnostics = lambda revision=revision: {
                    'available': True, 'revision': revision}
                broker._shared_diagnostics(self.store)
        with self.registry.connect() as connection:
            self.assertEqual(1, connection.execute(
                'SELECT count(*) FROM observation_cache WHERE project=?', ('project-a',)).fetchone()[0])
        lock_root = self.registry.home / 'observation-locks'
        self.assertEqual(1, len(list(lock_root.iterdir())))

    def test_revision_change_during_compute_is_not_published(self):
        broker = self._broker()
        with patch.object(broker, 'coordination_revision', side_effect=[0, 1, 1]):
            result = broker._shared_diagnostics(self.store)
        self.assertTrue(result['available'])
        self.assertEqual(1, self.calls)
        with self.registry.connect() as connection:
            table = connection.execute("SELECT 1 FROM sqlite_master WHERE name='observation_cache'").fetchone()
            self.assertTrue(table is None or connection.execute('SELECT count(*) FROM observation_cache').fetchone()[0] == 0)

    def test_expired_and_corrupt_rows_are_cache_misses(self):
        broker = self._broker()
        broker._shared_diagnostics(self.store)
        with self.registry.connect() as connection:
            connection.execute('UPDATE observation_cache SET observed_wall=?', (time.time() - 11,))
        broker._shared_diagnostics(self.store)
        with self.registry.connect() as connection:
            connection.execute('UPDATE observation_cache SET body=?', ('[]',))
        broker._shared_diagnostics(self.store)
        self.assertEqual(3, self.calls)

    def test_diagnostics_cache_is_not_an_authority_for_store_state(self):
        broker = self._broker()
        result = broker._shared_diagnostics(self.store)
        self.assertTrue(result['available'])
        self.assertFalse(hasattr(self.store, 'record'))
        with self.registry.connect() as connection:
            row = connection.execute('SELECT body FROM observation_cache').fetchone()
        self.assertEqual(result, json.loads(row['body']))

    def test_failed_observation_future_is_retried_and_recovers(self):
        broker = self._broker()
        first, second = Future(), Future()
        first.set_exception(TimeoutError('journal busy'))
        second.set_result({'available': True, 'revision': 0, 'call': 2})
        submitted = iter((first, second))

        class Executor:
            def submit(self, callback, store):
                return next(submitted)
            def shutdown(self, **kwargs):
                return None

        broker.observers.shutdown(wait=True, cancel_futures=True)
        broker.observers = Executor()
        entry = {'store': self.store, 'observed': time.monotonic() - 11,
                 'diagnostics': {}}

        broker.observe(entry)
        with self.assertRaisesRegex(TimeoutError, 'journal busy'):
            broker.observe(entry)
        self.assertIsNone(entry.get('observation'))

        broker.observe(entry)
        broker.observe(entry)
        self.assertEqual(entry['diagnostics']['call'], 2)
        self.assertIsNone(entry.get('observation'))


if __name__ == '__main__':
    unittest.main()
