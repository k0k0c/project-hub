import queue
import json
from pathlib import Path
import sys
import threading
import types
import unittest
from collections import deque
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from multiprocess_dispatch import DispatchExecutor, _target_index, _uses_read_lane, worker


class DispatchWorkerLaneTests(unittest.TestCase):
    def test_saturated_reader_does_not_queue_new_work_behind_it(self):
        from concurrent.futures import Future
        executor = object.__new__(DispatchExecutor)
        executor._lock = threading.RLock()
        executor._closed = executor._broken = False
        executor._inputs = [queue.Queue() for _ in range(3)]
        executor._processes = {1: types.SimpleNamespace(exitcode=None)}
        executor._pending = {identifier: Future() for identifier in range(1, 5)}
        executor._pending_targets = {identifier: 1 for identifier in range(1, 5)}
        executor._loads = [0, 4, 0]
        executor._deferred = deque()
        executor._next = 4
        executor._limit = 8
        fake_portal = types.SimpleNamespace(dispatch_process=Mock())
        with patch.dict(sys.modules, {'portal_asgi': fake_portal}):
            read = executor.submit(fake_portal.dispatch_process, {'method':'GET'}, b'')
            self.assertTrue(executor._inputs[1].empty(), 'new read queued behind saturated reader')
            self.assertEqual(5, executor._inputs[2].get_nowait()[0])
            write = executor.submit(fake_portal.dispatch_process, {'method':'POST'}, b'{}')
            self.assertEqual(6, executor._inputs[0].get_nowait()[0])
        executor._responses = queue.Queue()
        for identifier in range(1, 7):
            executor._responses.put((identifier, identifier, None))
        executor._closed = True
        executor._receive()
        self.assertEqual(5, read.result())
        self.assertEqual(6, write.result())
        self.assertEqual([0, 0, 0], executor._loads)
        self.assertEqual({}, executor._pending_targets)

    def test_publication_wait_uses_no_reader_slot_and_has_a_deadline(self):
        executor = object.__new__(DispatchExecutor)
        executor._lock = threading.RLock()
        executor._closed = executor._broken = False
        executor._inputs = [queue.Queue() for _ in range(3)]
        executor._processes = {1: types.SimpleNamespace(exitcode=None)}
        executor._pending = {}
        executor._pending_targets = {}
        executor._loads = [0, 0, 0]
        executor._deferred = deque()
        executor._next = 0
        executor._limit = 5
        fake_portal = types.SimpleNamespace(dispatch_process=Mock())
        with patch.dict(sys.modules, {'portal_asgi': fake_portal}), \
                patch('multiprocess_dispatch.time.monotonic', return_value=10):
            write = executor.submit(fake_portal.dispatch_process, {'method':'POST'}, b'{}')
            read = executor.submit(fake_portal.dispatch_process, {'method':'GET','path':'/api/tasks/detail'}, b'')
            health = executor.submit(fake_portal.dispatch_process, {'method':'GET','path':'/api/health'}, b'')
            self.assertEqual([1, 1, 0], executor._loads)
            self.assertEqual(1, len(executor._deferred))
            executor._flush_deferred()
            self.assertEqual(1, len(executor._deferred))
            executor._limit = 3
            with self.assertRaisesRegex(RuntimeError, 'queue is full'):
                executor.submit(fake_portal.dispatch_process, {'method':'GET'}, b'')
        with patch('multiprocess_dispatch.time.monotonic', return_value=10.151):
            executor._flush_deferred()
        self.assertEqual([], list(executor._deferred))
        self.assertEqual([1, 1, 1], executor._loads)
        executor._responses = queue.Queue()
        for identifier in (1, 2, 3):
            executor._responses.put((identifier, identifier, None))
        executor._closed = True
        executor._receive()
        self.assertEqual([1, 2, 3], [item.result() for item in (write, read, health)])
        self.assertEqual([0, 0, 0], executor._loads)

    def test_write_completion_releases_deferred_reads_without_replay(self):
        executor = object.__new__(DispatchExecutor)
        executor._lock = threading.RLock()
        executor._closed = executor._broken = False
        executor._inputs = [queue.Queue() for _ in range(2)]
        executor._processes = {1: types.SimpleNamespace(exitcode=None)}
        executor._pending = {}
        executor._pending_targets = {}
        executor._loads = [0, 0]
        executor._deferred = deque()
        executor._next = 0
        executor._limit = 5
        fake_portal = types.SimpleNamespace(dispatch_process=Mock())
        with patch.dict(sys.modules, {'portal_asgi': fake_portal}), \
                patch('multiprocess_dispatch.time.monotonic', return_value=10):
            write = executor.submit(fake_portal.dispatch_process, {'method':'POST'}, b'{}')
            read = executor.submit(fake_portal.dispatch_process, {'method':'GET','path':'/api/tasks/detail'}, b'')
            self.assertTrue(executor._inputs[1].empty())
            executor._responses = queue.Queue()
            executor._responses.put((1, None, 'failed mutation'))
            executor._responses.put((2, 'read', None))
            executor._closed = True
            executor._receive()
        self.assertEqual(2, executor._inputs[1].get_nowait()[0])
        self.assertTrue(executor._inputs[1].empty())
        with self.assertRaisesRegex(RuntimeError, 'failed mutation'):
            write.result()
        self.assertEqual('read', read.result())
        self.assertEqual([], list(executor._deferred))
        self.assertEqual([0, 0], executor._loads)

    def test_only_verified_hub_plan_posts_use_the_read_lane(self):
        scope = {'method': 'POST', 'path': '/api/v1/plugin/call'}
        pure = json.dumps({'tool': 'hub_plan', 'arguments': {'task': 'task-0', 'expected': 'r'}}).encode()
        stage = json.dumps({'tool': 'hub_plan', 'arguments': {'task': 'task-0', 'appendDone': 'result'}}).encode()
        malformed = b'{not-json'
        self.assertTrue(_uses_read_lane(scope, pure))
        self.assertFalse(_uses_read_lane(scope, stage))
        self.assertFalse(_uses_read_lane(scope, malformed))

    def test_verified_read_only_plugin_calls_and_process_routing(self):
        scope = {'method': 'POST', 'path': '/api/v1/plugin/call'}
        for tool in ('hub_context', 'hub_notice', 'hub_wait'):
            body = json.dumps({'tool': tool, 'arguments': {'task': 'task-0'}}).encode()
            self.assertTrue(_uses_read_lane(scope, body))
            self.assertEqual(_target_index(1, scope, body, 4), 1)
            self.assertEqual(_target_index(2, scope, body, 4), 2)
        write = json.dumps({'tool': 'hub_plan', 'arguments': {'appendDone': 'result'}}).encode()
        self.assertEqual(_target_index(9, scope, write, 4), 0)
        self.assertFalse(_uses_read_lane(scope, json.dumps({'tool': [], 'arguments': {}}).encode()))
        self.assertEqual(_target_index(9, {'method': 'POST', 'path': '/api/v1/events'}, b'{}', 4), 0)
        self.assertEqual(_target_index(9, {'method': 'GET'}, b'', 1), 0)

    def test_mutation_lane_progresses_while_read_slots_are_saturated(self):
        incoming, outgoing = queue.Queue(), queue.Queue()
        reads_started = threading.Event()
        release_reads = threading.Event()
        mutation_done = threading.Event()
        read_count = [0]
        count_lock = threading.Lock()

        def dispatch(scope, body):
            if scope['method'] == 'GET':
                with count_lock:
                    read_count[0] += 1
                    if read_count[0] == 7:
                        reads_started.set()
                self.assertTrue(release_reads.wait(3))
                return 'read'
            mutation_done.set()
            return 'write'

        fake_portal = types.SimpleNamespace(initialize_dispatch=lambda *args: None,
                                             dispatch_process=dispatch)
        with patch.dict(sys.modules, {'portal_asgi': fake_portal}):
            thread = threading.Thread(target=worker,
                                      args=(None, None, 0, 1, 8, incoming, outgoing), daemon=True)
            thread.start()
            for index in range(7):
                incoming.put((index, {'method': 'GET'}, b''))
            self.assertTrue(reads_started.wait(3))
            incoming.put((99, {'method': 'POST'}, b'{}'))
            self.assertTrue(mutation_done.wait(3), 'mutation waited behind saturated read slots')
            release_reads.set()
            incoming.put(None)
            thread.join(3)
        self.assertFalse(thread.is_alive())
        results = [outgoing.get(timeout=1) for _ in range(8)]
        self.assertEqual(1, sum(result[0] == 99 and result[1] == 'write' for result in results))

    def test_worker_exits_when_parent_is_dead_and_queue_stays_empty(self):
        incoming, outgoing = queue.Queue(), Mock()
        fake_portal = types.SimpleNamespace(initialize_dispatch=lambda *args: None,
                                             dispatch_process=lambda *args: None)
        dead_parent = types.SimpleNamespace(pid=12345, is_alive=lambda: False)
        with patch.dict(sys.modules, {'portal_asgi': fake_portal}), \
             patch('multiprocess_dispatch.multiprocessing.parent_process', return_value=dead_parent):
            thread = threading.Thread(target=worker,
                                      args=(None, None, 0, 1, 1, incoming, outgoing), daemon=True)
            thread.start()
            thread.join(2)
        self.assertFalse(thread.is_alive(), 'worker remained blocked after its parent exited')
        outgoing.cancel_join_thread.assert_called_once_with()
        outgoing.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
