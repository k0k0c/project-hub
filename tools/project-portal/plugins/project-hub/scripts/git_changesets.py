"""Immutable content boundaries and many-to-many commit coverage contracts.

This module performs read-only Git operations. Callers supply the existing CAS
and explicit attribution; no task owns a file and no trailer proves coverage.
Legacy checkpoints without these boundaries stay legacy, never inferred safe.
"""
import hashlib
import difflib
import json
import os
import posixpath
from pathlib import Path
import re
import subprocess


class ChangesetError(ValueError):
    def __init__(self, reason_code, message):
        super().__init__(message)
        self.reason_code = reason_code
        self.layer = 'changeset'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':')).encode('ascii')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *arguments, failure='git_read_failed', input_bytes=None, environment=None):
    try:
        env = dict(os.environ, **environment) if environment else None
        result = subprocess.run(['git', '-C', str(root), *arguments], capture_output=True, timeout=30, input=input_bytes, env=env,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ChangesetError('git_read_failed', 'Git content read is unavailable') from error
    if result.returncode:
        raise ChangesetError(failure, result.stderr.decode('utf-8', errors='replace')[:800] or 'Git content check refused')
    return result.stdout


def safe_path(path):
    if not isinstance(path, str) or not path or '\\' in path or ':' in path or path.startswith('/') or any(ord(c) < 32 for c in path) or any(p in ('', '.', '..') for p in path.split('/')):
        raise ChangesetError('invalid_scope', 'Changeset paths must be repository-relative')
    return path


def hash_value(value, *, commit=False):
    return isinstance(value, str) and re.fullmatch(r'[a-f0-9]{40}|[a-f0-9]{64}' if commit else r'[a-f0-9]{64}', value) is not None


def file_record(item):
    if (not isinstance(item, dict) or set(item) != {'blob', 'mode', 'size'} or not hash_value(item.get('blob'))
            or item.get('mode') not in ('100644', '100755') or type(item.get('size')) is not int or item['size'] < 0):
        raise ChangesetError('invalid_blob', 'Invalid immutable file record')


def attribution(associations, actor, confirmation):
    def text(value, limit):
        return isinstance(value, str) and bool(value.strip()) and len(value) <= limit and all(ord(c) >= 32 or c in '\n\r\t' for c in value)
    if not text(actor, 256) or not text(confirmation, 4000):
        raise ChangesetError('attribution_required', 'Record the actor and explicit content attribution')
    if not isinstance(associations, list) or not 1 <= len(associations) <= 100:
        raise ChangesetError('association_required', 'Link the changeset to concrete tasks/stages')
    for link in associations:
        if (not isinstance(link, dict) or not text(link.get('task'), 256)
                or set(link) - {'project', 'task', 'stage'}
                or any(not text(link[key], 256) for key in ('project', 'stage') if key in link)):
            raise ChangesetError('association_required', 'Invalid task/stage association')


def verify_identity(value, reason):
    body = {key: item for key, item in value.items() if key != 'id'}
    try:
        valid = hash_value(value.get('id')) and value['id'] == digest(canonical(body))
    except (TypeError, ValueError, UnicodeError) as error:
        raise ChangesetError(reason, 'Immutable contract cannot be decoded') from error
    if not valid:
        raise ChangesetError(reason, 'The original immutable contract was modified')


def identity(root):
    root = Path(root).resolve()
    lines = git(root, 'rev-parse', '--path-format=absolute', '--show-toplevel', '--git-common-dir', '--git-dir').decode().splitlines()
    if len(lines) != 3:
        raise ChangesetError('identity_unknown', 'Git repository/worktree identity is unavailable')
    top, common, gitdir = [str(Path(line).resolve()) for line in lines]
    normalize = str.casefold if os.name == 'nt' else lambda value: value
    return {'root': top, 'repositoryId': digest(normalize(common).encode()),
            'worktreeId': digest(normalize(gitdir).encode())}


def capture(root, resources, put_blob):
    """Capture before/after bytes, modes and dirty baseline without Git writes."""
    if not isinstance(resources, list) or not 1 <= len(resources) <= 30:
        raise ChangesetError('invalid_scope', 'Select 1–30 explicit paths')
    scope = sorted({safe_path(path) for path in resources})
    context = identity(root)
    root = Path(context['root'])
    head = git(root, 'rev-parse', 'HEAD').decode().strip()
    index = git(root, 'ls-files', '--stage', '-z')
    indexed_modes, indexed_blobs = {}, {}
    for record in index.split(b'\0'):
        if not record:
            continue
        metadata, name = record.split(b'\t', 1)
        mode, oid, stage = metadata.split(b' ')
        indexed_modes[os.fsdecode(name)] = mode.decode() if stage == b'0' else 'unmerged'
        indexed_blobs[os.fsdecode(name)] = oid.decode()
    status = git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
    dirty_paths = set()
    rows = iter(status.split(b'\0'))
    for row in rows:
        if row:
            dirty_paths.add(os.fsdecode(row[3:]))
            if b'R' in row[:2] or b'C' in row[:2]:
                dirty_paths.add(os.fsdecode(next(rows)))
    paths = git(root, '--literal-pathspecs', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', *scope)
    entries, source_files, total = {}, {}, 0
    for raw in sorted(set(path for path in paths.split(b'\0') if path)):
        relative = safe_path(os.fsdecode(raw))
        path = root / relative
        if path.is_symlink() or any(parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction())
                                    for parent in path.parents if parent != root.parent):
            raise ChangesetError('unsupported_input', 'Changesets cannot traverse links')
        if not path.exists():
            continue  # deletion is represented by absence from the after boundary
        if not path.is_file():
            raise ChangesetError('unsupported_input', 'Changesets require ordinary files')
        with path.open('rb') as stream:
            data = stream.read(64 * 1024 * 1024 + 1)
        total += len(data)
        if len(data) > 64 * 1024 * 1024 or total > 256 * 1024 * 1024 or len(entries) >= 10000:
            raise ChangesetError('boundary_too_large', 'Content boundary exceeds its file/byte limits')
        content_hash = put_blob(data)
        if content_hash != digest(data):
            raise ChangesetError('content_store_mismatch', 'CAS did not preserve the exact file bytes')
        mode = indexed_modes.get(relative, '100644') if os.name == 'nt' else ('100755' if path.stat().st_mode & 0o111 else '100644')
        if indexed_modes.get(relative) == 'unmerged' or mode not in ('100644', '100755'):
            raise ChangesetError('unsupported_input', 'Changesets require ordinary resolved files')
        entries[relative] = {'blob': content_hash, 'mode': mode, 'size': len(data)}
        source_files[relative] = dict(entries[relative])
        # Preserve physical bytes while verifying Git's built-in EOL projection.
        # Other clean transforms require an explicit adapter, never inference.
        projection = indexed_blobs.get(relative) if relative not in dirty_paths else None
        if projection is None:
            projection = git(root, 'hash-object', '--path=' + relative, '--stdin', input_bytes=data).decode().strip()
        def object_id(content):
            payload = b'blob ' + str(len(content)).encode() + b'\0' + content
            return (hashlib.sha256(payload) if len(projection) == 64 else hashlib.sha1(payload)).hexdigest()
        normalized = data if object_id(data) == projection else data.replace(b'\r\n', b'\n')
        if object_id(normalized) != projection:
            raise ChangesetError('clean_filter_adapter_required', 'Non-EOL Git clean transforms require an explicit content adapter: ' + relative)
        entries[relative] = dict(blob=put_blob(normalized), mode=mode, size=len(normalized))
        if entries[relative]['blob'] != digest(normalized):
            raise ChangesetError('content_store_mismatch', 'CAS did not preserve Git-normalized bytes')
    if (git(root, 'rev-parse', 'HEAD').decode().strip() != head or git(root, 'ls-files', '--stage', '-z') != index
            or git(root, '--literal-pathspecs', 'ls-files', '--cached', '--others', '--exclude-standard', '-z', '--', *scope) != paths):
        raise ChangesetError('concurrent_git_change', 'Git HEAD/index changed while capturing the boundary')
    # A second byte read catches concurrent edits without rewriting the baseline.
    if any(not (root / name).is_file() or digest((root / name).read_bytes()) != item['blob'] for name, item in source_files.items()):
        raise ChangesetError('concurrent_source_change', 'Files changed while capturing the boundary')
    value = dict(context, schemaVersion=1, head=head, scope=scope, files=entries, sourceFiles=source_files,
                 indexSha256=digest(index), dirty=bool(status))
    return dict(value, id=digest(canonical(value)))


def tree_files(root, commit, scope, put_blob):
    # Bound Windows argv length. A broader metadata query is filtered back to
    # the exact scope before any blob is read or unsupported entry is inspected.
    query_scope = scope
    if sum(len(path) + 4 for path in scope) > 8000:
        common = posixpath.commonpath(scope)
        query_scope = [common] if common else []
    records = git(root, '--literal-pathspecs', 'ls-tree', '-r', '-z', '--full-tree', commit, '--', *query_scope)
    entries, index = [], []
    for record in records.split(b'\0'):
        if not record:
            continue
        metadata, name = record.split(b'\t', 1)
        mode, kind, oid = metadata.split(b' ')
        relative = safe_path(os.fsdecode(name))
        if not any(relative == path or relative.startswith(path + '/') for path in scope):
            continue
        if mode not in (b'100644', b'100755') or kind != b'blob':
            raise ChangesetError('unsupported_input', 'Commit boundary requires ordinary files')
        entries.append((relative, mode, oid))
        index.append(mode + b' ' + oid + b' 0\t' + name + b'\0')
    return read_many_blobs(root, entries, put_blob), digest(b''.join(index))


def read_many_blobs(root, entries, put_blob, environment=None):
    # One process for arbitrarily many files, including opaque binary blobs.
    raw = git(root, 'cat-file', '--batch', input_bytes=b''.join(oid + b'\n' for _, _, oid in entries), environment=environment) if entries else b''
    files, offset = {}, 0
    for relative, mode, oid in entries:
        end = raw.find(b'\n', offset)
        header = raw[offset:end].split()
        if end < 0 or len(header) != 3 or header[:2] != [oid, b'blob'] or not header[2].isdigit():
            raise ChangesetError('git_read_failed', 'Git batch blob response is invalid')
        size = int(header[2])
        data = raw[end + 1:end + 1 + size]
        offset = end + size + 2
        if len(data) != size or raw[offset - 1:offset] != b'\n':
            raise ChangesetError('git_read_failed', 'Git batch blob response is incomplete')
        identifier = put_blob(data)
        if identifier != digest(data):
            raise ChangesetError('content_store_mismatch', 'CAS did not preserve committed bytes')
        files[relative] = dict(blob=identifier, mode=mode.decode(), size=len(data))
    if offset != len(raw):
        raise ChangesetError('git_read_failed', 'Git batch blob response has unexpected bytes')
    return files


def index_files(root, scope, environment=None):
    """The exact candidate Git will commit, including its normal file filters."""
    raw = git(root, 'ls-files', '--stage', '-z', environment=environment)
    entries = []
    for record in raw.split(b'\0'):
        if not record:
            continue
        metadata, name = record.split(b'\t', 1)
        relative = safe_path(os.fsdecode(name))
        if not any(relative == path or relative.startswith(path + '/') for path in scope):
            continue
        mode, oid, stage = metadata.split(b' ')
        if stage != b'0' or mode not in (b'100644', b'100755'):
            raise ChangesetError('unsupported_input', 'Candidate index requires ordinary resolved files')
        entries.append((relative, mode, oid))
    return read_many_blobs(root, entries, digest, environment)


def at_commit(root, commit, before, put_blob):
    """Read a committed tree in the source worktree's immutable scope."""
    validate_boundary(before)
    context = identity(root)
    if context['repositoryId'] != before['repositoryId']:
        raise ChangesetError('repository_mismatch', 'Commit tree belongs to another repository')
    if not hash_value(commit, commit=True):
        raise ChangesetError('invalid_commit', 'Use a full commit object ID')
    if git(root, 'cat-file', '-t', commit).strip() != b'commit':
        raise ChangesetError('invalid_commit', 'Object is not a commit')
    files, index_hash = tree_files(root, commit, before['scope'], put_blob)
    value = dict(schemaVersion=1, root=before['root'], repositoryId=before['repositoryId'],
                 worktreeId=before['worktreeId'], head=commit, scope=before['scope'], files=files,
                 indexSha256=index_hash, dirty=False, source='commit-tree')
    return dict(value, id=digest(canonical(value)))


def validate_boundary(boundary):
    if not isinstance(boundary, dict) or type(boundary.get('schemaVersion')) is not int or boundary['schemaVersion'] != 1 or not isinstance(boundary.get('files'), dict):
        raise ChangesetError('boundary_missing', 'An immutable content boundary is required')
    if (any(not hash_value(boundary.get(key)) for key in ('repositoryId', 'worktreeId', 'indexSha256'))
            or not hash_value(boundary.get('head'), commit=True) or type(boundary.get('dirty')) is not bool
            or not isinstance(boundary.get('root'), str) or not boundary['root']
            or not isinstance(boundary.get('scope'), list) or not 1 <= len(boundary['scope']) <= 30):
        raise ChangesetError('invalid_boundary', 'Incomplete repository boundary metadata')
    scope = [safe_path(path) for path in boundary['scope']]
    if scope != sorted(set(scope)):
        raise ChangesetError('invalid_scope', 'Boundary scope must be ordered and unique')
    for name, item in boundary['files'].items():
        safe_path(name)
        if not any(name == path or name.startswith(path + '/') for path in scope):
            raise ChangesetError('invalid_scope', 'File is outside the attributed boundary scope')
        file_record(item)
    if 'sourceFiles' in boundary:
        if not isinstance(boundary['sourceFiles'], dict) or set(boundary['sourceFiles']) != set(boundary['files']):
            raise ChangesetError('invalid_boundary', 'Physical source records must match the boundary paths')
        for record in boundary['sourceFiles'].values():
            file_record(record)
    verify_identity(boundary, 'boundary_changed')
    return boundary


def create(before, after, associations, *, actor, confirmation):
    before, after = validate_boundary(before), validate_boundary(after)
    if any(before.get(key) != after.get(key) for key in ('repositoryId', 'worktreeId', 'scope')):
        raise ChangesetError('boundary_mismatch', 'Changeset boundaries belong to different worktrees or scopes')
    attribution(associations, actor, confirmation)
    changes = [{'path': name, 'before': before['files'].get(name), 'after': after['files'].get(name)}
               for name in sorted(before['files'].keys() | after['files'].keys())
               if before['files'].get(name) != after['files'].get(name)]
    if not changes:
        raise ChangesetError('no_changes', 'Boundaries contain no attributed changes')
    value = dict(schemaVersion=1, repositoryId=before['repositoryId'], worktreeId=before['worktreeId'],
                 baseHead=before['head'], beforeBoundary=before['id'], afterBoundary=after['id'],
                 changes=changes, associations=associations, actor=actor, confirmation=confirmation)
    return dict(value, id=digest(canonical(value)))


def validate_changeset(changeset):
    if not isinstance(changeset, dict) or type(changeset.get('schemaVersion')) is not int or changeset['schemaVersion'] != 1:
        raise ChangesetError('invalid_changeset', 'A versioned immutable changeset is required')
    if (any(not hash_value(changeset.get(key)) for key in ('repositoryId', 'worktreeId', 'beforeBoundary', 'afterBoundary'))
            or not hash_value(changeset.get('baseHead'), commit=True)
            or not isinstance(changeset.get('changes'), list) or not changeset['changes']):
        raise ChangesetError('invalid_changeset', 'Incomplete changeset content metadata')
    attribution(changeset.get('associations'), changeset.get('actor'), changeset.get('confirmation'))
    paths = []
    for change in changeset['changes']:
        if not isinstance(change, dict) or set(change) != {'path', 'before', 'after'}:
            raise ChangesetError('invalid_changeset', 'Invalid before/after content change')
        paths.append(safe_path(change['path']))
        for key in ('before', 'after'):
            if change[key] is not None:
                file_record(change[key])
        if change['before'] == change['after']:
            raise ChangesetError('invalid_changeset', 'Changeset must contain an actual content or mode change')
    if paths != sorted(set(paths)):
        raise ChangesetError('invalid_changeset', 'Changeset paths must be ordered and unique')
    verify_identity(changeset, 'changeset_changed')
    return changeset


def content(read_blob, record, reason):
    try:
        data = read_blob(record['blob'])
    except (OSError, KeyError, ValueError) as error:
        raise ChangesetError(reason, 'Immutable file bytes are unavailable') from error
    if not isinstance(data, bytes) or len(data) != record['size'] or digest(data) != record['blob']:
        raise ChangesetError(reason, 'Immutable file bytes failed integrity validation')
    return data


def verify_coverage(root, changeset, commit, read_blob):
    """Verify full before/after content and ancestry; never filenames alone.

    Intersecting hunks in a larger final blob require a reviewed patch coverage
    adapter. This exact-blob verifier refuses that case instead of guessing.
    """
    validate_changeset(changeset)
    context = identity(root)
    if context['repositoryId'] != changeset['repositoryId']:
        raise ChangesetError('repository_mismatch', 'Commit belongs to another repository')
    if not isinstance(commit, str) or not re.fullmatch(r'[a-fA-F0-9]{40}|[a-fA-F0-9]{64}', commit):
        raise ChangesetError('invalid_commit', 'Use a full commit object ID')
    commit = commit.lower()
    git(root, 'merge-base', '--is-ancestor', changeset['baseHead'], commit, failure='base_ancestry_mismatch')
    git(root, 'merge-base', '--is-ancestor', commit, 'HEAD', failure='commit_ancestry_mismatch')
    parents = git(root, 'rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
    if len(parents) != 1:
        raise ChangesetError('coverage_review_required', 'Exact coverage requires a non-merge commit with one parent')
    scope = [change['path'] for change in changeset['changes']]
    committed, _ = tree_files(root, commit, scope, digest)
    parent, _ = tree_files(root, parents[0], scope, digest)
    for change in changeset['changes']:
        name = safe_path(change['path'])
        after = change['after']
        if after is not None:
            content(read_blob, after, 'content_corrupt')
        if committed.get(name) != after:
            raise ChangesetError('coverage_mismatch', 'Commit does not contain the attributed bytes and mode: ' + name)
        # Dirty baseline bytes are evidence of the starting state, not changes
        # attributed to this work. They stay in the immutable CAS/boundary.
        before = change['before']
        if before is not None:
            content(read_blob, before, 'baseline_corrupt')
        if parent.get(name) != before:
            raise ChangesetError('baseline_not_in_commit_parent', 'Dirty or intervening bytes require content review: ' + name)
    value = dict(schemaVersion=1, changeset=changeset['id'], commit=commit,
                 repositoryId=context['repositoryId'], worktreeId=changeset['worktreeId'],
                 beforeBoundary=changeset['beforeBoundary'], afterBoundary=changeset['afterBoundary'],
                 associations=changeset['associations'],
                 verification='exact-content-and-ancestry')
    return dict(value, id=digest(canonical(value)))


def _parallel_text(before, edges, read_blob, put_blob):
    """Compose reviewed disjoint line edits; ambiguous overlaps stay conflicts."""
    if before is None or any(edge['after'] is None for edge in edges):
        raise ChangesetError('batch_conflict', 'Concurrent creation/deletion requires an explicit resolved changeset')
    original = content(read_blob, before, 'baseline_corrupt')
    versions = [content(read_blob, edge['after'], 'content_corrupt') for edge in edges]
    try:
        for data in [original, *versions]:
            data.decode('utf-8')
            if b'\0' in data or len(data) > 1024 * 1024 or len(data.splitlines()) > 2000:
                raise ValueError('text adapter bounds')
    except (UnicodeError, ValueError) as error:
        raise ChangesetError('batch_conflict', 'Distinct binary or large-file changes require a resolved changeset') from error
    lines = original.splitlines(keepends=True)
    edits, proofs, modes = [], {}, {edge['after']['mode'] for edge in edges if edge['after']['mode'] != before['mode']}
    if len(modes) > 1:
        raise ChangesetError('batch_conflict', 'Concurrent mode changes conflict')
    for edge, data in zip(edges, versions):
        replacement = data.splitlines(keepends=True)
        hunks = []
        for tag, start, end, first, last in difflib.SequenceMatcher(None, lines, replacement, autojunk=False).get_opcodes():
            if tag == 'equal':
                continue
            new = replacement[first:last]
            edit = (start, end, new)
            for a, b, old in edits:
                if edit == (a, b, old):
                    break
                overlap = max(start, a) < min(end, b)
                if start == end:
                    overlap = a <= start <= b
                if a == b:
                    overlap = start <= a <= end
                if overlap:
                    raise ChangesetError('batch_conflict', 'Reviewed text hunks overlap; supply a resolved changeset')
            else:
                edits.append(edit)
            hunks.append(dict(start=start, end=end, replacementSha256=digest(b''.join(new))))
        proofs[edge['changeset']] = hunks
    merged = list(lines)
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        merged[start:end] = replacement
    data = b''.join(merged)
    identifier = put_blob(data)
    if identifier != digest(data):
        raise ChangesetError('content_store_mismatch', 'CAS did not preserve merged bytes')
    return dict(blob=identifier, mode=next(iter(modes), before['mode']), size=len(data)), proofs


def compose_batch(before, changesets, read_blob, put_blob, *, actor, confirmation):
    """Build a content candidate from explicit changesets in any linked worktree.

    Original dirty bytes can participate only through a complete reviewed chain
    starting at the integration parent. No scope or baseline is rewritten.
    """
    validate_boundary(before)
    if not isinstance(changesets, list) or not 1 <= len(changesets) <= 100:
        raise ChangesetError('invalid_batch', 'Select 1–100 immutable changesets')
    changesets = sorted([validate_changeset(item) for item in changesets], key=lambda item: item['id'])
    if len({item['id'] for item in changesets}) != len(changesets):
        raise ChangesetError('invalid_batch', 'A changeset can occur only once in a reviewed batch')
    links = sorted({canonical(link) for item in changesets for link in item['associations']})
    associations = [json.loads(link) for link in links]
    attribution(associations, actor, confirmation)
    pending = {}
    for item in changesets:
        if item['repositoryId'] != before['repositoryId']:
            raise ChangesetError('repository_mismatch', 'Batch changesets belong to different repositories')
        for change in item['changes']:
            if not any(change['path'] == path or change['path'].startswith(path + '/') for path in before['scope']):
                raise ChangesetError('invalid_scope', 'Changeset is outside the reviewed candidate scope')
            for key in ('before', 'after'):
                if change[key] is not None:
                    content(read_blob, change[key], 'content_corrupt')
            pending.setdefault(change['path'], []).append(dict(change, changeset=item['id']))
    files, steps = dict(before['files']), []
    for name, edges in sorted(pending.items()):
        current = files.get(name)
        while edges:
            matches = [edge for edge in edges if edge['before'] == current]
            if not matches:
                raise ChangesetError('batch_baseline_unknown', 'Unattributed starting bytes remain in the reviewed batch: ' + name)
            unique = {canonical(edge['after']) for edge in matches}
            if len(unique) == 1:
                after, proofs, method = matches[0]['after'], {}, 'exact-content-chain'
            else:
                after, proofs = _parallel_text(current, matches, read_blob, put_blob)
                method = 'reviewed-disjoint-text-hunks'
            steps.append(dict(path=name, before=current, after=after, method=method,
                              members=[dict(changeset=edge['changeset'], hunks=proofs.get(edge['changeset'], [])) for edge in matches]))
            edges = [edge for edge in edges if edge not in matches]
            current = after
        if current is None:
            files.pop(name, None)
        else:
            files[name] = current
    if files == before['files']:
        raise ChangesetError('no_changes', 'Reviewed batch has no net candidate changes')
    final = dict(schemaVersion=1, root=before['root'], repositoryId=before['repositoryId'],
                 worktreeId=before['worktreeId'], head=before['head'], scope=before['scope'], files=files,
                 indexSha256=before['indexSha256'], dirty=False, source='reviewed-batch',
                 sourceBoundaries=sorted({item['afterBoundary'] for item in changesets}))
    final = dict(final, id=digest(canonical(final)))
    validate_boundary(final)
    before_blob, after_blob = put_blob(canonical(before)), put_blob(canonical(final))
    if before_blob != digest(canonical(before)) or after_blob != digest(canonical(final)):
        raise ChangesetError('content_store_mismatch', 'CAS did not preserve batch boundary evidence')
    value = dict(schemaVersion=1, kind='reviewed-git-batch', repositoryId=before['repositoryId'],
                 worktreeId=before['worktreeId'], head=before['head'], scope=before['scope'],
                 beforeBlob=before_blob, afterBlob=after_blob,
                 changesets=changesets, steps=steps, associations=associations, actor=actor, confirmation=confirmation)
    return dict(value, id=digest(canonical(value)))


def validate_batch(batch, read_blob, put_blob):
    if (not isinstance(batch, dict) or batch.get('kind') != 'reviewed-git-batch'
            or type(batch.get('schemaVersion')) is not int or batch['schemaVersion'] != 1
            or not hash_value(batch.get('beforeBlob')) or not hash_value(batch.get('afterBlob'))):
        raise ChangesetError('invalid_batch', 'A reviewed immutable batch is required')
    verify_identity(batch, 'batch_changed')
    try:
        before = validate_boundary(json.loads(read_blob(batch['beforeBlob'])))
        after = validate_boundary(json.loads(read_blob(batch['afterBlob'])))
        rebuilt = compose_batch(before, batch['changesets'], read_blob, put_blob,
                                actor=batch['actor'], confirmation=batch['confirmation'])
    except (KeyError, OSError, TypeError, json.JSONDecodeError) as error:
        raise ChangesetError('invalid_batch', 'Batch evidence is unavailable or incomplete') from error
    if rebuilt != batch:
        raise ChangesetError('batch_changed', 'Candidate/coverage differs from the reviewed changesets')
    return before, after


def verify_batch_coverage(root, batch, commit, read_blob, put_blob):
    """Verify one reviewed candidate and credit every original contribution."""
    before, after = validate_batch(batch, read_blob, put_blob)
    if identity(root)['repositoryId'] != batch['repositoryId'] or not hash_value(commit, commit=True):
        raise ChangesetError('repository_mismatch', 'Batch commit repository/identity is invalid')
    parents = git(root, 'rev-list', '--parents', '-n', '1', commit).decode().split()[1:]
    if parents != [batch['head']]:
        raise ChangesetError('batch_parent_changed', 'Commit parent differs from the reviewed integration HEAD')
    git(root, 'merge-base', '--is-ancestor', commit, 'HEAD', failure='commit_ancestry_mismatch')
    for item in batch['changesets']:
        git(root, 'merge-base', '--is-ancestor', item['baseHead'], commit, failure='base_ancestry_mismatch')
    parent, _ = tree_files(root, parents[0], before['scope'], put_blob)
    committed, _ = tree_files(root, commit, before['scope'], put_blob)
    if parent != before['files'] or committed != after['files']:
        raise ChangesetError('coverage_mismatch', 'Commit does not preserve the exact reviewed before/after bytes and modes')
    value = dict(schemaVersion=1, batch=batch['id'], commit=commit, repositoryId=batch['repositoryId'],
                 changesets=[item['id'] for item in batch['changesets']], associations=batch['associations'],
                 verification='reviewed-batch-content-and-ancestry')
    return dict(value, id=digest(canonical(value)))
