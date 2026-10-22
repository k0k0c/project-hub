"""Content-addressed, rebuildable image responses outside project source roots.

Authorization is performed by the caller for every request. Cache identity uses
current original bytes, rather than timestamps or a watcher as a freshness proof.
Atomic files and per-content OS locks deduplicate decoders across server workers.
"""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from importlib.metadata import version, PackageNotFoundError

from request_metrics import measure


class PreparedSources:
    VERSION = 1

    def __init__(self, registry, *, max_bytes=1_073_741_824, max_entries=2048):
        self.registry = registry
        self.home = registry.home / 'prepared-sources'
        self.home.mkdir(exist_ok=True)
        self.guard = threading.Lock()
        self.locks = {}
        self.pending = set()
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.maintenance_pending = False
        self.last_maintenance = float('-inf')
        self.executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix='source-preview')
        try:
            decoder = version('Pillow')
        except PackageNotFoundError:
            decoder = 'native'
        self.encoder = f'preview-{self.VERSION}-pillow-{decoder}'
        with registry.connect() as c:
            c.execute('''CREATE TABLE IF NOT EXISTS prepared_source_images(
                key TEXT PRIMARY KEY, content_hash TEXT NOT NULL,
                size INTEGER NOT NULL, mime TEXT NOT NULL)''')

    @contextmanager
    def locked(self, key):
        with self.guard:
            lock, users = self.locks.get(key, (threading.Lock(), 0))
            self.locks[key] = lock, users + 1
        try:
            with lock:
                from project_portal import Store
                store = Store(self.home, data_dir=self.home)
                # Fixed stripes also bound the number of persistent lock files.
                store.lockfile = self.home / 'locks' / (key[:2] + '.lock')
                with store.locked():
                    yield
        finally:
            with self.guard:
                lock, users = self.locks[key]
                if users == 1:
                    del self.locks[key]
                else:
                    self.locks[key] = lock, users - 1

    def image(self, path, preview, *, if_none_match=None):
        self.maintain()
        from image_sources import _read, read_image
        if preview not in ('thumbnail','full','original'):
            raise ValueError('Unknown image preview mode')
        # Read one bounded original; conversion uses those exact validated bytes.
        with measure('source_read'):
            item = _read(path)
            if item is None:
                raise ValueError('Not a supported image extension')
            original, _ = item
            digest = hashlib.sha256(original).hexdigest()
        key = hashlib.sha256(json.dumps([digest, preview, self.encoder]).encode()).hexdigest()
        filename = self.home / (key + '.blob')
        # Published content is immutable. Warm readers can validate and borrow
        # the same blob concurrently; the OS stripe is only for publication,
        # repair and eviction. An eviction race falls back to the locked path.
        with self.registry.connect() as c:
            row = c.execute('SELECT * FROM prepared_source_images WHERE key=?', (key,)).fetchone()
        if row is not None:
            try:
                with measure('preview_read'):
                    data = filename.read_bytes()
            except FileNotFoundError:
                pass
            else:
                if len(data) == row['size'] and hashlib.sha256(data).hexdigest() == row['content_hash']:
                    etag = '"' + row['content_hash'] + '"'
                    return (b'' if if_none_match == etag else data), row['mime'], etag
        with self.locked(key):
            with self.registry.connect() as c:
                row = c.execute('SELECT * FROM prepared_source_images WHERE key=?', (key,)).fetchone()
            if row is None or not filename.exists():
                with measure('preview_encode'):
                    data, mime = read_image(path, preview, content=original)
                content_hash = hashlib.sha256(data).hexdigest()
                descriptor, temporary = tempfile.mkstemp(dir=self.home, prefix=key + '-', suffix='.tmp')
                try:
                    with os.fdopen(descriptor, 'wb') as output:
                        output.write(data)
                        output.flush()
                        os.fsync(output.fileno())
                    os.replace(temporary, filename)
                finally:
                    Path(temporary).unlink(missing_ok=True)
                with self.registry.connect() as c:
                    c.execute('INSERT OR REPLACE INTO prepared_source_images VALUES(?,?,?,?)',
                              (key, content_hash, len(data), mime))
                row = dict(content_hash=content_hash, size=len(data), mime=mime)
            etag = '"' + row['content_hash'] + '"'
            with measure('preview_read'):
                data = filename.read_bytes()
            if len(data) != row['size'] or hashlib.sha256(data).hexdigest() != row['content_hash']:
                # A damaged derived file is disposable; never serve it as valid.
                filename.unlink(missing_ok=True)
                with self.registry.connect() as c:
                    c.execute('DELETE FROM prepared_source_images WHERE key=?', (key,))
                raise ValueError('Prepared preview is damaged; retry to rebuild')
            if if_none_match == etag:
                return b'', row['mime'], etag
            return data, row['mime'], etag

    def maintain(self):
        with self.guard:
            if self.maintenance_pending or time.monotonic() - self.last_maintenance < 60:
                return
            self.maintenance_pending = True
            self.last_maintenance = time.monotonic()
        def cleanup():
            try:
                self.prune()
            finally:
                with self.guard:
                    self.maintenance_pending = False
        try:
            self.executor.submit(cleanup)
        except RuntimeError:
            with self.guard:
                self.maintenance_pending = False

    def prune(self):
        # Only derived blobs are disposable. Original files, journals and
        # durable write intents are never part of this maintenance operation.
        with self.locked('maintenance'):
            with self.registry.connect() as c:
                rows = c.execute('SELECT key,size FROM prepared_source_images ORDER BY rowid DESC').fetchall()
            retained, total = set(), 0
            for row in rows:
                key, size = row['key'], row['size']
                if len(retained) < self.max_entries and total + size <= self.max_bytes:
                    retained.add(key)
                    total += size
                    continue
                with self.locked(key):
                    (self.home / (key + '.blob')).unlink(missing_ok=True)
                    with self.registry.connect() as c:
                        c.execute('DELETE FROM prepared_source_images WHERE key=?', (key,))
            # A process may have stopped after atomic file publication but
            # before metadata publication. Serialize with its content stripe.
            for filename in self.home.glob('*.blob'):
                key = filename.stem
                if key in retained: continue
                with self.locked(key):
                    with self.registry.connect() as c:
                        known = c.execute('SELECT 1 FROM prepared_source_images WHERE key=?', (key,)).fetchone()
                    if not known: filename.unlink(missing_ok=True)
            for filename in self.home.glob('*.tmp'):
                try:
                    if time.time() - filename.stat().st_mtime > 3600:
                        filename.unlink(missing_ok=True)
                except FileNotFoundError:
                    pass

    def schedule(self, source, relative):
        from image_sources import _EXTENSIONS
        if Path(relative).suffix.lower().lstrip('.') not in _EXTENSIONS:
            return
        identity = source, relative
        with self.guard:
            if identity in self.pending or len(self.pending) >= 128:
                return
            self.pending.add(identity)
        def prepare():
            try:
                store = self.registry.base_store(source)
                path = store.resolve_evidence_path(relative)
                self.image(path, 'thumbnail')
                self.image(path, 'full')
            except (OSError, ValueError, KeyError):
                # Missing sources remain explicit unavailable entries, not errors
                # cached indefinitely. The next registration/request retries.
                pass
            finally:
                with self.guard:
                    self.pending.discard(identity)
        try:
            self.executor.submit(prepare)
        except RuntimeError:
            with self.guard:
                self.pending.discard(identity)

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)
