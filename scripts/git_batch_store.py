"""Registered immutable batch evidence in the existing knowledge CAS."""
import json
import os
import tempfile

from git_changesets import ChangesetError, digest, hash_value, validate_batch


def _directory(store):
    directory = store.data / 'git-batches'
    if directory.is_symlink() or (hasattr(directory, 'is_junction') and directory.is_junction()):
        raise ChangesetError('batch_registry_invalid', 'Batch registry cannot traverse links')
    if directory.exists() and not directory.is_dir():
        raise ChangesetError('batch_registry_invalid', 'Batch registry must be a directory')
    return directory


def inspect(data, read_blob):
    def existing(content):
        identifier = digest(content)
        if read_blob(identifier) != content:
            raise ChangesetError('content_corrupt', 'Registered batch evidence changed')
        return identifier
    batch = json.loads(data)
    validate_batch(batch, read_blob, existing)
    return batch


def register(store, identifier):
    if not hash_value(identifier):
        raise ChangesetError('invalid_batch', 'Use an immutable batch blob reference')
    inspect(store.read_blob(identifier), store.read_blob)
    directory = _directory(store)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / identifier
    if target.is_symlink():
        raise ChangesetError('batch_registry_invalid', 'Batch registry cannot traverse links')
    expected = (identifier + '\n').encode('ascii')
    descriptor, temporary = tempfile.mkstemp(prefix='.git-batch-', dir=store.data)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(expected)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            pass
    finally:
        os.unlink(temporary)
    if not target.is_file() or target.read_bytes() != expected:
        raise ChangesetError('batch_registry_invalid', 'Batch registry marker failed integrity validation')


def load(store, identifier):
    if not hash_value(identifier):
        raise ChangesetError('invalid_batch', 'Use an immutable registered batch reference')
    target = _directory(store) / identifier
    if target.is_symlink() or not target.is_file() or target.read_bytes() != (identifier + '\n').encode('ascii'):
        raise ChangesetError('batch_unregistered', 'Batch was not prepared by this project')
    return inspect(store.read_blob(identifier), store.read_blob)


def manifest(store):
    identifiers = []
    for path in sorted(_directory(store).glob('*')):
        if not hash_value(path.name) or not path.is_file() or path.is_symlink():
            raise ChangesetError('batch_registry_invalid', 'Batch registry contains an invalid marker')
        load(store, path.name)
        identifiers.append(path.name)
    return identifiers
