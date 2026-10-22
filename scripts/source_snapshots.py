"""Preserve project-relative evidence when working records leave a checkout."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import zipfile
import zlib

from hub_backup import safe_name

MAX_EXPANDED = 20 * 1024**2
CATALOG = 'source-file-aliases.json'


def _catalog(store):
    path = store.data / CATALOG
    if not path.exists():
        return {'schemaVersion': 1, 'files': {}}
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schemaVersion') != 1 or not isinstance(value.get('files'), dict):
        raise ValueError('Invalid source snapshot catalog')
    for name, entry in value['files'].items():
        safe_name(name)
        if (not isinstance(entry, dict) or not isinstance(entry.get('snapshot'), str)
                or not entry['snapshot'].startswith('hub-artifact/')
                or not isinstance(entry.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', entry['sha256'])
                or type(entry.get('size')) is not int or not 0 <= entry['size'] <= MAX_EXPANDED):
            raise ValueError('Invalid source snapshot entry')
    return value


def entry_for(store, name):
    return _catalog(store)['files'].get(name)


def _archive(store, reference):
    from artifact_store import resolve
    _, content = resolve(store, reference)
    archive = None
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        infos = archive.infolist()
        if sum(info.file_size for info in infos) > MAX_EXPANDED or len(infos) > 10000:
            raise ValueError('Source snapshot exceeds supported limits')
        names = [safe_name(info.filename) for info in infos]
        if len(set(name.casefold() for name in names)) != len(names):
            raise ValueError('Ambiguous source snapshot paths')
        if any(info.flag_bits & 1 or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED) for info in infos):
            raise ValueError('Unsupported source snapshot encoding')
        manifest = json.loads(archive.read('archive-manifest.json'))
        if (not isinstance(manifest, dict) or manifest.get('kind') not in ('hub-source-snapshot', 'hub-development-materials')
                or not isinstance(manifest.get('files'), dict)):
            raise ValueError('Invalid source snapshot manifest')
        return archive, manifest
    except (zipfile.BadZipFile, KeyError, UnicodeError, json.JSONDecodeError, zlib.error) as error:
        if archive:
            archive.close()
        raise ValueError('Damaged source snapshot') from error
    except Exception:
        if archive:
            archive.close()
        raise


def register(store, reference, files):
    """Register immutable archive versions; current checkout reads stay separate."""
    from project_portal import atomic_write
    if not isinstance(reference, str) or not reference.startswith('hub-artifact/'):
        raise ValueError('Use an uploaded immutable source snapshot')
    if (not isinstance(files, list) or not 1 <= len(files) <= 200
            or not all(isinstance(name, str) for name in files) or len(set(files)) != len(files)):
        raise ValueError('Select 1..200 unique source paths')
    additions = {}
    with _archive(store, reference)[0] as archive:
        manifest = json.loads(archive.read('archive-manifest.json'))
        for name in files:
            safe_name(name)
            if set(Path(name).parts) & {'.git', '.codex', '.agents'}:
                raise ValueError('Protected source snapshot path')
            checksum = manifest['files'].get(name)
            content = archive.read(name)
            if not isinstance(checksum, str) or hashlib.sha256(content).hexdigest() != checksum:
                raise ValueError('Source snapshot checksum mismatch')
            source = (store.root / name).resolve()
            if not source.is_relative_to(store.root):
                raise ValueError('Source path escapes project root')
            if source.exists() and (not source.is_file() or source.read_bytes() != content):
                raise ValueError('Source changed after snapshot: ' + name)
            additions[name] = {'snapshot': reference, 'sha256': checksum, 'size': len(content)}
    with store.locked():
        value = _catalog(store)
        for name, entry in additions.items():
            if name in value['files'] and value['files'][name] != entry:
                raise ValueError('Source path already has a different immutable fallback')
        value['files'].update(additions)
        atomic_write(store.data / CATALOG, json.dumps(value, ensure_ascii=False))
    return {'registered': len(additions)}


def materialize(store, name):
    entry = entry_for(store, name)
    if entry is None:
        return None
    destination = store.data / 'source-snapshots' / entry['sha256'] / Path(name).name
    if destination.resolve() != destination.absolute():
        raise ValueError('Source snapshot cache must not traverse links')
    if destination.is_file():
        content = destination.read_bytes()
        if len(content) == entry['size'] and hashlib.sha256(content).hexdigest() == entry['sha256']:
            return destination
    with _archive(store, entry['snapshot'])[0] as archive:
        content = archive.read(name)
    if len(content) != entry['size'] or hashlib.sha256(content).hexdigest() != entry['sha256']:
        raise ValueError('Source snapshot checksum mismatch')
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=destination.name + '.', dir=destination.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination
