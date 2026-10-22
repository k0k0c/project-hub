"""Bounded spawn workers with concurrent I/O threads and one shared receiver.

Only the parent listens for HTTP. Workers exchange trusted request packets and
responses over multiprocessing queues; they never accept a socket or replay a
failed request. This executor is specific to the Hub dispatcher.
"""
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
import json
import multiprocessing
import queue
import threading
import time
from collections import deque


def _uses_read_lane(scope, body):
    method = str(scope.get('method', 'GET')).upper()
    if method in ('GET', 'HEAD'):
        return True
    if method != 'POST' or scope.get('path') != '/api/v1/plugin/call':
        return False
    try:
        request = json.loads(body)
    except (TypeError, UnicodeDecodeError, ValueError):
        return False
    if not isinstance(request, dict):
        return False
    tool = request.get('tool')
    if isinstance(tool, str) and tool in {'hub_context', 'hub_notice', 'hub_wait'}:
        return True
    arguments = request.get('arguments')
    return (tool == 'hub_plan' and isinstance(arguments, dict) and
            set(arguments) <= {'task', 'expected'})


def _target_index(identifier, scope, body, process_count):
    """Choose the dedicated mutation process or round-robin read process."""
    if process_count == 1:
        return 0
    if _uses_read_lane(scope, body):
        return 1 + ((identifier - 1) % (process_count - 1))
    return 0


def _needs_publication(scope):
    """Reads whose freshness probe otherwise waits in a request thread."""
    path = scope.get('path', '')
    return path.startswith('/api/') and path not in ('/api/health', '/api/v1/health', '/api/projects')


def worker(home, catalog, port, processes, threads, incoming, outgoing, role='mixed'):
    from runtime_diagnostics import configure, exception, record
    configure('request-worker', role=role, port=port)
    try:
        from portal_asgi import initialize_dispatch, dispatch_process
        initialize_dispatch(home, catalog, port, processes)
    except BaseException as error:
        exception('request.worker_initialization_failed',error,role=role,port=port)
        raise
    # A benchmark or service supervisor can disappear without delivering the
    # sentinel.  Capture the parent handle once; the main-process/thread path
    # has no parent handle and retains its existing queue behavior.
    parent = multiprocessing.parent_process()
    if role not in {'mixed', 'reader', 'writer'}:
        raise ValueError('Invalid dispatch worker role')
    # Multi-process dispatch dedicates process zero to mutations and gives
    # every reader process all of its threads.  The one-process path remains
    # mixed for direct callers and backwards-compatible tests.
    if role == 'reader':
        read_executor = ThreadPoolExecutor(max_workers=max(1, threads),
                                           thread_name_prefix='hub-dispatch-read')
        mutation_executor = read_executor
    elif role == 'writer':
        read_executor = ThreadPoolExecutor(max_workers=1,
                                           thread_name_prefix='hub-dispatch-read')
        mutation_executor = read_executor
    else:
        shared_executor = threads < 2
        read_executor = ThreadPoolExecutor(max_workers=max(1, threads - 1),
                                           thread_name_prefix='hub-dispatch-read')
        mutation_executor = read_executor if shared_executor else ThreadPoolExecutor(
            max_workers=1, thread_name_prefix='hub-dispatch-write')
    parent_lost = False
    def complete(identifier, future):
        try:
            result = future.result()
            outgoing.put((identifier, result, None))
        except BaseException as error:
            from runtime_diagnostics import exception
            exception('request.worker_failed',error,dispatchId=identifier,role=role)
            outgoing.put((identifier, None, str(error)))
    try:
        while True:
            try:
                packet = incoming.get(timeout=.5)
            except queue.Empty:
                if parent is not None and not parent.is_alive():
                    from runtime_diagnostics import record
                    record('request.worker_parent_lost',parentPid=parent.pid,role=role)
                    parent_lost = True
                    break
                continue
            if packet is None:
                break
            identifier, scope, body = packet
            executor = read_executor if role == 'reader' or (
                role != 'writer' and _uses_read_lane(scope, body)) else mutation_executor
            future = executor.submit(dispatch_process, scope, body)
            future.add_done_callback(lambda result, key=identifier: complete(key, result))
    finally:
        if mutation_executor is not read_executor:
            mutation_executor.shutdown(wait=True)
        read_executor.shutdown(wait=True)
        if parent_lost:
            # The response listener is gone, so do not let Queue's feeder
            # finalizer wait forever for a pipe that can no longer drain.
            cancel_join = getattr(outgoing, 'cancel_join_thread', None)
            if cancel_join is not None:
                cancel_join()
            close = getattr(outgoing, 'close', None)
            if close is not None:
                close()


class DispatchExecutor(Executor):
    def __init__(self, home, catalog, port, processes, *, threads=2, pending=128):
        if not 1 <= processes <= 32 or threads < 1 or pending < processes:
            raise ValueError('Invalid dispatch limits')
        self._port = port
        context = multiprocessing.get_context('spawn')
        self._responses = context.Queue(maxsize=pending)
        self._inputs = [context.Queue(maxsize=pending) for _ in range(processes)]
        self._lock = threading.RLock()
        self._closed = False
        self._broken = False
        self._pending = {}
        self._pending_targets = {}
        self._loads = [0] * processes
        self._deferred = deque()
        self._next = 0
        self._limit = pending
        self._processes = {}
        try:
            for index, incoming in enumerate(self._inputs):
                role = ('writer' if processes >= 2 and index == 0 else
                        'reader' if processes >= 2 else 'mixed')
                process = context.Process(target=worker,
                    args=(home, catalog, port, processes,
                          1 if role == 'writer' else threads,
                          incoming, self._responses, role))
                process.start()
                self._processes[process.pid] = process
        except BaseException:
            for process in self._processes.values():
                process.terminate()
                process.join()
            for channel in [*self._inputs, self._responses]:
                channel.cancel_join_thread()
                channel.close()
            raise
        self._receiver = threading.Thread(target=self._receive, name='hub-dispatch-replies', daemon=True)
        self._receiver.start()

    def submit(self, function, scope, body):
        from portal_asgi import dispatch_process
        if function is not dispatch_process:
            raise ValueError('Only Hub request dispatch is supported')
        self._break_if_dead()
        with self._lock:
            if self._broken:
                raise BrokenProcessPool('Hub dispatch worker exited')
            if self._closed:
                raise RuntimeError('Hub dispatch executor is closed')
            if len(self._pending) >= self._limit:
                raise RuntimeError('Hub dispatch queue is full')
            self._next += 1
            identifier = self._next
            future = Future()
            # Submitted packets can already be executing when a browser closes;
            # cancellation must never imply that a mutation was not committed.
            future.set_running_or_notify_cancel()
            self._pending[identifier] = future
            try:
                target = _target_index(identifier, scope, body, len(self._inputs))
                packet = identifier, scope, body
                if target and self._loads[0] and _needs_publication(scope):
                    # Await the writer's publication in the bounded parent
                    # queue, without occupying reader threads with file/lock
                    # probes. A long write cannot starve reads: each packet has
                    # an independent 150ms deadline, then uses normal freshness.
                    self._deferred.append((time.monotonic() + .15, packet))
                else:
                    self._send(packet, target)
            except BaseException:
                self._pending.pop(identifier)
                target = self._pending_targets.pop(identifier, None)
                if target is not None:
                    self._loads[target] -= 1
                raise
            return future

    def _send(self, packet, target=None):
        identifier, scope, body = packet
        if target is None:
            target = _target_index(identifier, scope, body, len(self._inputs))
        if target and len(self._inputs) > 2:
            readers = list(range(target, len(self._inputs))) + list(range(1, target))
            target = min(readers, key=self._loads.__getitem__)
        self._pending_targets[identifier] = target
        self._loads[target] += 1
        try:
            self._inputs[target].put_nowait(packet)
        except BaseException:
            self._pending_targets.pop(identifier, None)
            self._loads[target] -= 1
            raise

    def _flush_deferred(self, *, force=False):
        # Caller owns _lock. Individual failures release their accepted future;
        # successful packets are sent once and never replayed.
        now = time.monotonic()
        while self._deferred and (force or not self._loads[0] or self._deferred[0][0] <= now):
            _, packet = self._deferred.popleft()
            try:
                self._send(packet)
            except BaseException as error:
                future = self._pending.pop(packet[0])
                future.set_exception(error)

    def _break_if_dead(self):
        with self._lock:
            dead = any(p.exitcode is not None and (not self._closed or p.exitcode != 0)
                       for p in self._processes.values())
            if not dead or self._broken:
                return self._broken
            self._broken = True
            from runtime_diagnostics import record
            record('request.worker_exit',workers=[dict(pid=p.pid,exitCode=p.exitcode) for p in self._processes.values() if p.exitcode is not None])
            from runtime_diagnostics import child_exit
            for process in self._processes.values():
                if process.exitcode is not None:
                    child_exit(process,'request-worker',expected=self._closed,port=self._port)
            pending, self._pending = self._pending, {}
            self._pending_targets.clear()
            self._loads = [0] * len(self._inputs)
            self._deferred.clear()
        for future in pending.values():
            future.set_exception(BrokenProcessPool('Hub dispatch worker exited; refresh before retrying'))
        return True

    def _receive(self):
        while True:
            if self._break_if_dead():
                return
            with self._lock:
                self._flush_deferred()
                timeout = .01 if self._deferred else .1
            try:
                identifier, result, error = self._responses.get(timeout=timeout)
            except queue.Empty:
                with self._lock:
                    if self._closed and not self._pending:
                        return
                continue
            except (OSError, EOFError):
                with self._lock:
                    pending, self._pending = self._pending, {}
                    self._pending_targets.clear()
                    self._loads = [0] * len(self._inputs)
                    self._deferred.clear()
                    self._broken = True
                for future in pending.values():
                    future.set_exception(BrokenProcessPool('Hub dispatch response channel closed'))
                return
            with self._lock:
                future = self._pending.pop(identifier, None)
                target = self._pending_targets.pop(identifier, None)
                if target is not None:
                    self._loads[target] -= 1
                self._flush_deferred()
            if future is not None:
                if error is None:
                    future.set_result(result)
                else:
                    future.set_exception(RuntimeError(error))

    def shutdown(self, wait=True, *, cancel_futures=False):
        with self._lock:
            if self._closed:
                already_closed = True
            else:
                already_closed = False
                self._closed = True
            broken = self._broken
            if not broken:
                self._flush_deferred(force=True)
        if not already_closed:
            if broken:
                for process in self._processes.values():
                    if process.is_alive():
                        process.terminate()
            else:
                # FIFO stop follows accepted packets; each worker drains its
                # threads before exit. Accepted mutations are never cancelled.
                for incoming in self._inputs:
                    incoming.put(None)
        if wait:
            for process in self._processes.values():
                process.join()
            self._receiver.join()
            for channel in [*self._inputs, self._responses]:
                if broken:
                    channel.cancel_join_thread()
                channel.close()
                if not broken:
                    channel.join_thread()
        elif not already_closed:
            threading.Thread(target=self.shutdown, kwargs={'wait':True},
                             name='hub-dispatch-cleanup', daemon=True).start()
