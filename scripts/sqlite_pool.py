"""Small bounded pool for SQLite connections used by the ASGI service."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import threading
import time


class SQLitePool:
    def __init__(self, path, max_idle=16, max_connections=64, timeout=5, *,
                 foreign_keys=False, existing_only=False):
        if max_idle < 0 or max_connections < 1 or max_idle > max_connections:
            raise ValueError("invalid SQLite pool bounds")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        self.path = Path(path).resolve()
        self.max_idle = int(max_idle)
        self.max_connections = int(max_connections)
        self.timeout = float(timeout)
        self.foreign_keys = bool(foreign_keys)
        self.existing_only = bool(existing_only)
        self._slots = threading.BoundedSemaphore(self.max_connections)
        self._lock = threading.RLock()
        self._idle = []
        self._active = {}
        self._closed = False

    def _identity(self):
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return (stat.st_dev, stat.st_ino)

    @staticmethod
    def _close(connection):
        try:
            connection.close()
        except (OSError, sqlite3.Error):
            pass

    def _purge_idle(self, identity):
        retained = []
        for cached_identity, connection in self._idle:
            if cached_identity == identity and not self._closed:
                retained.append((cached_identity, connection))
            else:
                self._close(connection)
        self._idle = retained

    def _open(self):
        # A replacement between either stat and connect must never silently
        # hand out a handle to the wrong database.
        for _ in range(3):
            before = self._identity()
            try:
                target = self.path.as_uri() + '?mode=rw' if self.existing_only else self.path
                connection = sqlite3.connect(target, uri=self.existing_only, timeout=self.timeout,
                                             isolation_level=None, check_same_thread=False)
            except sqlite3.Error:
                raise
            after = self._identity()
            if after is not None and (before is None or before == after):
                connection.row_factory = sqlite3.Row
                if self.foreign_keys:
                    connection.execute('PRAGMA foreign_keys=ON')
                return after, connection
            self._close(connection)
            time.sleep(0.005)
        raise RuntimeError("SQLite database changed while opening connection")

    @contextmanager
    def connect(self):
        if not self._slots.acquire(timeout=self.timeout):
            raise TimeoutError("SQLite connection pool exhausted")
        connection = None
        identity = None
        try:
            with self._lock:
                if self._closed:
                    raise RuntimeError("SQLite connection pool is closed")
                identity = self._identity()
                self._purge_idle(identity)
                if self._idle:
                    identity, connection = self._idle.pop()
                else:
                    identity, connection = self._open()
                self._active[connection] = identity
            try:
                yield connection
            finally:
                with self._lock:
                    old_identity = self._active.pop(connection, identity)
                    try:
                        if connection.in_transaction:
                            connection.rollback()
                    except sqlite3.Error:
                        pass
                    # Retain the lease's identity, not a fresh one. Every next
                    # checkout validates the database and purges stale handles
                    # before lending them, including replacements during use.
                    if self._closed or len(self._idle) >= self.max_idle:
                        self._close(connection)
                    else:
                        self._idle.append((old_identity, connection))
        finally:
            self._slots.release()

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            idle, self._idle = self._idle, []
            for _, connection in idle:
                self._close(connection)
