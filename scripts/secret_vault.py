"""Installation-owned credentials outside portable Hub data and program files."""
import base64
import ctypes
import json
import os
from pathlib import Path

from hub_launcher import external_path
from hub_lifecycle import atomic_json, control_directory, file_lock


def private_home(registry):
    control = control_directory()
    return external_path((control.parent.parent if control else registry.home.parent) / 'private')


def _protect(data, decrypt=False):
    if os.name != 'nt':
        return data
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    blob_ptr = ctypes.POINTER(Blob)
    crypt32.CryptProtectData.argtypes = [
        blob_ptr, wintypes.LPCWSTR, blob_ptr, ctypes.c_void_p,
        ctypes.c_void_p, wintypes.DWORD, blob_ptr,
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        blob_ptr, ctypes.POINTER(wintypes.LPWSTR), blob_ptr,
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, blob_ptr,
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL

    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    if decrypt:
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)
        )
    else:
        ok = crypt32.CryptProtectData(
            ctypes.byref(source), 'Project Hub', None, None, None, 1, ctypes.byref(target)
        )
    if not ok:
        raise ValueError('Private credential storage is unavailable')
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        if target.pbData:
            kernel32.LocalFree(target.pbData)


def read(registry):
    path = external_path(private_home(registry) / 'provider-credentials.json')
    if not path.exists():
        return {}
    with path.open('rb') as stream:
        raw = stream.read(128_001)
    if len(raw)>128_000:
        raise ValueError('Private credential storage exceeds the supported size')
    try:
        value = json.loads(raw)
    except (TypeError, ValueError, UnicodeError):
        raise ValueError('Private credential storage is invalid') from None
    if not isinstance(value, dict):
        raise ValueError('Private credential storage is invalid')
    expected='windows-dpapi' if os.name=='nt' else 'private-file'
    if value.get('version')!=1 or value.get('protection')!=expected:
        raise ValueError('Private credentials require the original user environment')
    try:
        encrypted = base64.b64decode(value['content'], validate=True)
        result = json.loads(_protect(encrypted, True))
    except (KeyError, TypeError, ValueError, UnicodeError):
        raise ValueError('Private credential storage is invalid') from None
    if not isinstance(result,dict):
        raise ValueError('Private credential storage is invalid')
    return result


def save(registry, identifier, key):
    if not isinstance(key,str) or not 1<=len(key)<=4096 or any(ord(c)<33 for c in key):
        raise ValueError('Supply a nonempty API key without whitespace')
    home=private_home(registry)
    with file_lock(home / 'provider-credentials.lock',timeout=2):
        value=read(registry)
        value[identifier]=key
        raw=json.dumps(value).encode()
        content=base64.b64encode(_protect(raw)).decode('ascii')
        path=home / 'provider-credentials.json'
        atomic_json(path,dict(version=1,protection='windows-dpapi' if os.name=='nt' else 'private-file',content=content))
        os.chmod(path,0o600)


def get(registry, identifier):
    key=read(registry).get(identifier)
    if not key:
        raise ValueError('API key is unavailable in this installation')
    return key
