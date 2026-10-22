"""Bounded request diagnostics, shared by HTTP, ASGI and storage paths."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache, wraps
import hashlib
from pathlib import Path
import re
import time
import uuid

_current = ContextVar('hub_request_metrics', default=None)


class RequestMetrics:
    def __init__(self, identifier=None):
        self.identifier = (identifier if isinstance(identifier, str) and
                           re.fullmatch(r'[A-Za-z0-9_.-]{1,64}', identifier)
                           else uuid.uuid4().hex)
        self.started = time.perf_counter()
        self.durations = {}
        self.base_paths = {}

    def add(self, name, seconds):
        if re.fullmatch(r'[a-z][a-z0-9_]{0,31}', name):
            self.durations[name] = self.durations.get(name, 0.0) + seconds

    def header(self):
        rows = dict(self.durations, total=time.perf_counter() - self.started)
        return ', '.join(f'{name};dur={seconds * 1000:.2f}'
                         for name, seconds in sorted(rows.items()))

    @contextmanager
    def bind(self):
        token = _current.set(self)
        try:
            yield self
        finally:
            _current.reset(token)


@contextmanager
def measure(name):
    metrics = _current.get()
    if metrics is None:
        yield
        return
    started = time.perf_counter()
    try:
        yield
    finally:
        metrics.add(name, time.perf_counter() - started)


def data_path(path):
    """Resolve an internal Store data directory once per request.

    Managed data directories share the runtime's fixed data home. Project roots
    and evidence containment are always resolved afresh. Files still open and
    verify their current bytes; administrative data-home moves require restart.
    """
    path = Path(path)
    metrics = _current.get()
    if metrics is None or not path.is_absolute():
        return path.resolve()
    if path not in metrics.base_paths:
        if len(metrics.base_paths) >= 128:
            return path.resolve()
        metrics.base_paths[path] = path.resolve()
    return metrics.base_paths[path]


def track_handler(method):
    @wraps(method)
    def tracked(handler, *args, **kwargs):
        handler.metrics = RequestMetrics(handler.headers.get('X-Request-ID'))
        with handler.metrics.bind():
            return method(handler, *args, **kwargs)
    return tracked


def timed(name):
    def decorate(method):
        @wraps(method)
        def tracked(*args, **kwargs):
            with measure(name):
                return method(*args, **kwargs)
        return tracked
    return decorate


@contextmanager
def measured_lock(lock, name='lock'):
    with measure(name + '_wait'):
        lock.acquire()
    try:
        with measure(name + '_hold'):
            yield
    finally:
        lock.release()


@lru_cache(maxsize=4)
def runtime_version(root):
    """Identify the source loaded by this process once, before serving requests."""
    root = Path(root)
    digest = hashlib.sha256()
    for directory in ('scripts', 'tools/project-portal/plugins/project-hub/scripts'):
        for path in sorted((root / directory).glob('*.py')):
            digest.update(path.relative_to(root).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()
