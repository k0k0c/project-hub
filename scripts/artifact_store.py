"""Opaque immutable task artifacts in the existing Hub content-addressed store.

References identify exact descriptor versions. Roles describe use; they never
change validation selection. Originals in a checkout keep their own paths.
"""
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

MAX_BYTES = 20 * 1024 * 1024
ROLES = {'evidence', 'deliverable', 'product-input', 'test-fixture'}
HASH = re.compile(r'[a-f0-9]{64}\Z')


def safe_name(name):
    if (not isinstance(name, str) or not name or len(name) > 255
            or name in ('.', '..') or name.rstrip(' .') != name
            or any(c in name for c in '/\\:<>"|?*') or any(ord(c) < 32 for c in name)
            or name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                                             *('COM' + str(i) for i in range(1, 10)),
                                             *('LPT' + str(i) for i in range(1, 10))}):
        raise ValueError('Artifact name must be a safe basename')
    return name


def cas(store):
    from knowledge_store import KnowledgeStore
    knowledge = KnowledgeStore(store.registry, store.project_id)
    if any(knowledge.data.resolve().is_relative_to(root) for root in knowledge.roots):
        raise ValueError('Artifact storage must be outside product source roots')
    return knowledge


def parse(reference):
    if not isinstance(reference, str):
        raise ValueError('Invalid artifact reference')
    parts = reference.split('/')
    if len(parts) != 3 or parts[0] != 'hub-artifact' or not HASH.fullmatch(parts[1]):
        raise ValueError('Invalid artifact reference')
    safe_name(parts[2])
    return parts[1], parts[2]


def inspect_descriptor(data, name=None):
    item = json.loads(data)
    if (not isinstance(item, dict) or type(item.get('schemaVersion')) is not int or item['schemaVersion'] != 1
            or item.get('kind') != 'artifact-descriptor'
            or not isinstance(item.get('artifactId'), str) or not 1 <= len(item['artifactId']) <= 160
            or any(ord(c) < 32 for c in item['artifactId'])
            or not isinstance(item.get('contentHash'), str) or not HASH.fullmatch(item['contentHash'])
            or item.get('version') != item['contentHash'] or type(item.get('size')) is not int
            or not 0 <= item['size'] <= MAX_BYTES
            or not isinstance(item.get('roles'), list) or any(not isinstance(role, str) or role not in ROLES for role in item['roles'])
            or not isinstance(item.get('provenance'), str) or not 1 <= len(item['provenance']) <= 1000
            or (item.get('previous') is not None and (not isinstance(item['previous'], str) or not HASH.fullmatch(item['previous'])))):
        raise ValueError('Invalid artifact descriptor')
    safe_name(item.get('name'))
    if 'originalName' in item:
        safe_name(item['originalName'])
    if name is not None and item['name'] != name:
        raise ValueError('Artifact name does not match immutable descriptor')
    return item


def register_descriptor(knowledge, identifier):
    """Distinguish Hub descriptors from arbitrary uploaded JSON in the same CAS."""
    if not isinstance(identifier, str) or not HASH.fullmatch(identifier):
        raise ValueError('Invalid artifact descriptor hash')
    inspect_descriptor(knowledge.read_blob(identifier))
    root = knowledge.data.resolve()
    directory = root / 'artifact-descriptors'
    if directory.is_symlink() or (hasattr(directory, 'is_junction') and directory.is_junction()):
        raise ValueError('Artifact descriptor registry must not traverse links')
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / identifier
    if target.is_symlink():
        raise ValueError('Artifact descriptor registry must not traverse links')
    expected = (identifier + '\n').encode('ascii')
    descriptor, temporary = tempfile.mkstemp(prefix='.artifact-descriptor-', dir=root)
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
        raise ValueError('Artifact descriptor registry failed integrity validation')


def descriptor_manifest(knowledge):
    directory = knowledge.data / 'artifact-descriptors'
    if directory.is_symlink() or (hasattr(directory, 'is_junction') and directory.is_junction()):
        raise ValueError('Artifact descriptor registry must not traverse links')
    identifiers = []
    for path in sorted(directory.glob('*')):
        if (path.is_symlink() or not path.is_file() or not HASH.fullmatch(path.name)
                or path.read_bytes() != (path.name + '\n').encode('ascii')):
            raise ValueError('Artifact descriptor registry failed integrity validation')
        identifiers.append(path.name)
    return identifiers


def resolve(store, reference):
    identifier, name = parse(reference)
    knowledge = cas(store)
    item = inspect_descriptor(knowledge.read_blob(identifier), name)
    content = knowledge.read_blob(item['contentHash'])
    if len(content) != item['size']:
        raise ValueError('Artifact size does not match immutable descriptor')
    return item, content


def publish(store, name, content, *, roles=None, provenance='uploaded', previous=None, artifact_id=None):
    safe_name(name)
    if not isinstance(content, bytes) or len(content) > MAX_BYTES:
        raise ValueError('Artifact exceeds 20 MiB')
    roles = ['evidence'] if roles is None else roles
    if not isinstance(roles, list) or any(not isinstance(role, str) or role not in ROLES for role in roles):
        raise ValueError('Invalid artifact roles')
    from image_sources import normalized_image_name
    original_name = name
    name = safe_name(normalized_image_name(name, content))
    knowledge = cas(store)
    content_hash = hashlib.sha256(content).hexdigest()
    previous_hash = None
    requested_id = artifact_id
    artifact_id = content_hash if artifact_id is None else artifact_id
    if previous is not None:
        # Version chaining requires an already registered source, not knowledge
        # of an arbitrary descriptor hash from another task or project.
        origin, relative = store.evidence_origin(previous)
        old, _ = resolve(origin, relative)
        previous_hash, _ = parse(relative)
        artifact_id = old['artifactId']
        if requested_id is not None and requested_id != artifact_id:
            raise ValueError('Artifact version must preserve its stable ID')
        # Keep a continued version self-contained after a task transfer. Exact
        # ancestor descriptors/bytes are copied, never their original aliases
        # or journal history. CAS deduplicates versions already present here.
        prior_store = cas(origin)
        cursor, seen = previous_hash, set()
        while cursor is not None:
            if cursor in seen or len(seen) >= 1000:
                raise ValueError('Invalid or oversized artifact version history')
            seen.add(cursor)
            encoded_prior = prior_store.read_blob(cursor)
            prior = inspect_descriptor(encoded_prior)
            prior_content = prior_store.read_blob(prior['contentHash'])
            if prior['artifactId'] != artifact_id or len(prior_content) != prior['size']:
                raise ValueError('Invalid artifact version ancestry')
            knowledge.blob(prior_content)
            knowledge.blob(encoded_prior)
            register_descriptor(knowledge, cursor)
            cursor = prior.get('previous')
    item = dict(schemaVersion=1, kind='artifact-descriptor', artifactId=artifact_id, version=content_hash,
                contentHash=content_hash, size=len(content), name=name,
                provenance=provenance, roles=sorted(set(roles)), previous=previous_hash)
    if name != original_name:
        item['originalName'] = original_name
    encoded = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    inspect_descriptor(encoded)
    knowledge.blob(content)
    descriptor_hash = knowledge.blob(encoded)
    register_descriptor(knowledge, descriptor_hash)
    reference = f'hub-artifact/{descriptor_hash}/{name}'
    return {'source': {'path': reference, 'label': name}, 'artifact': item,
            'descriptorHash': descriptor_hash}


def upload(store, name, encoded, **options):
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_BYTES + 2) // 3):
        raise ValueError('Invalid or oversized base64 artifact')
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise ValueError('Invalid base64 artifact') from error
    return publish(store, name, content, **options)


def materialize(store, reference):
    """Immutable suffix-preserving adapter for existing local preview readers."""
    identifier, name = parse(reference)
    item, content = resolve(store, reference)
    knowledge = cas(store)
    root = knowledge.data.resolve()
    directory = root
    for component in ('artifacts', identifier):
        directory = directory / component
        if directory.is_symlink() or (hasattr(directory, 'is_junction') and directory.is_junction()):
            raise ValueError('Artifact storage must not traverse links')
        directory.mkdir(parents=True, exist_ok=True)
        if not directory.resolve().is_relative_to(root):
            raise ValueError('Artifact storage escapes its data root')
    target = directory / name
    if target.is_symlink():
        raise ValueError('Artifact original must not be a link')
    if not target.exists():
        descriptor, temporary = tempfile.mkstemp(prefix='.artifact-', dir=directory)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass
        finally:
            os.unlink(temporary)
    if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != item['contentHash']:
        raise ValueError('Artifact original failed integrity validation')
    return target
