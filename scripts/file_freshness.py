"""Verified file-change identities for bounded journal digest reuse.

Open every file with read permission. NTFS ChangeTime (not creation time)
detects restored LastWriteTime; POSIX ctime detects restored mtime. Unsupported
Windows filesystems fall back to hashing on every read. No watcher is a proof.
"""
import hashlib
import os
import threading
from collections import OrderedDict

if os.name == 'nt':
    import ctypes
    import msvcrt
    class BasicInfo(ctypes.Structure):
        _fields_ = [(name, ctypes.c_int64) for name in ('creation', 'access', 'write', 'change')] + [('attributes', ctypes.c_uint32)]
    _get = ctypes.WinDLL('kernel32', use_last_error=True).GetFileInformationByHandleEx
    _get.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
    _get.restype = ctypes.c_int


def token(stream):
    stat = os.fstat(stream.fileno())
    change = stat.st_ctime_ns
    if os.name == 'nt':
        info = BasicInfo()
        if not _get(msvcrt.get_osfhandle(stream.fileno()), 0, ctypes.byref(info), ctypes.sizeof(info)) or not info.change:
            return None
        change = info.change
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, change


class FileDigests:
    def __init__(self):
        self.lock = threading.Lock()
        self.entries = OrderedDict()

    def reuse(self, path, *, missing=False, proven=None):
        """Freshly open a known version without hashing an intervening write.

        A miss grants no freshness: callers must recheck publication or use
        digest(). This avoids hashing a successor journal against an old SQL
        snapshot while a managed append is being published.
        """
        try:
            with path.open('rb') as stream:
                identity = token(stream)
                with self.lock:
                    prior = self.entries.get(path)
                if identity is not None and proven is not None and tuple(proven[0]) == identity:
                    return True, proven[1]
                if identity is not None and prior is not None and prior[0] == identity:
                    return True, prior[1]
                return False, None
        except FileNotFoundError:
            if missing:
                return True, None
            raise

    def digest(self, path, *, missing=False, proven=None):
        for attempt in range(3):
            try:
                with path.open('rb') as stream:
                    before = token(stream)
                    with self.lock:
                        prior = self.entries.get(path)
                    if before is not None and proven is not None and tuple(proven[0]) == before:
                        return proven[1]  # SQL proof published with its exact index head.
                    if before is not None and prior is not None and prior[0] == before:
                        return prior[1]
                    value = hashlib.sha256(stream.read()).digest()
                    after = token(stream)
                with path.open('rb') as current:
                    current_token = token(current)
                if before is not None and before == after == current_token:
                    with self.lock:
                        self.entries[path] = before, value
                        self.entries.move_to_end(path)
                        while len(self.entries) > 256:
                            self.entries.popitem(last=False)
                    return value
                if before is None:
                    return value  # No metadata reuse on unsupported filesystems.
            except FileNotFoundError:
                if missing:
                    return None
                raise
        raise ValueError('File changed during digest verification; retry the read')
