"""Project-owned completion receipts; Git is a retryable obligation, not a status gate."""
import hashlib
import json
import re
import sqlite3
import threading
from contextlib import closing, contextmanager
from pathlib import Path

from git_integration import (GitIntegrationError, _commit_files, _in_scope, _row_paths,
                             _run, commit_work, decode_snapshot, repository)
from project_settings import read_settings
from version_control import workspace_status
from project_portal import now


_jobs_lock = threading.Lock()
_jobs = {}
_repo_locks = {}


@contextmanager
def _operation_context(identifier):
    try:
        yield
    except (GitIntegrationError, ValueError) as error:
        if hasattr(error, 'reason_code'):
            error.operation_id = identifier
        raise


def _needs_publication(result):
    return result.get('publication', {}).get('status') == 'pending'


def _metadata(result):
    """Keep journal/API receipts bounded; full verified details stay in the registry."""
    value = {k: v for k, v in result.items() if k != 'publication'}
    if len(json.dumps(value)) <= 12000:
        return value

    def compact(item):
        if isinstance(item, list):
            return [compact(v) for v in item]
        if not isinstance(item, dict):
            return item
        output = {}
        for key, entry in item.items():
            if key in ('files', 'scopedFiles', 'changesets') and isinstance(entry, list):
                output[key + 'Count'] = len(entry)
                output[key + 'Sha256'] = hashlib.sha256(json.dumps(entry).encode()).hexdigest()
            elif key == 'commits' and isinstance(entry, list):
                output[key] = [compact({k: v for k, v in commit.items() if k != 'repository'})
                               if isinstance(commit, dict) else commit for commit in entry]
            else:
                output[key] = compact(entry)
        return output

    return dict(compact(value), detailsAvailable=True,
                detailsSha256=hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest())


def schedule_checkpoint(registry, checkpoint, retry=False):
    """Git hooks run outside the portal request and ownership lock."""
    key = (str(registry.home), checkpoint)
    with _jobs_lock:
        if key in _jobs:
            return
        with registry.connect() as c:
            row = c.execute('SELECT result FROM completion_checkpoints WHERE id=?', (checkpoint,)).fetchone()
        if not row:
            return
        saved = json.loads(row['result'])
        if not _needs_publication(saved) and saved['status'] not in (('pending', 'error') if retry else ('pending',)):
            return
        def run():
            try:
                from task_transfer import barrier
                # Let the original journal transaction finish before inspecting it.
                with barrier(registry):
                    pass
                # Separate on-disk lock serializes Git writers across portal processes,
                # while unrelated API and settings requests retain their own lock.
                from project_portal import Store
                with registry.connect() as c:
                    saved = c.execute('SELECT body,result FROM completion_checkpoints WHERE id=?', (checkpoint,)).fetchone()
                if _needs_publication(json.loads(saved['result'])):
                    finish_checkpoint(registry, checkpoint, retry=retry)
                    return
                body = json.loads(saved['body'])
                roots = {w['root'] for w in body['work']} or {body['root']}
                root = sorted(roots)[0]
                info = repository(root)
                common = str(Path(root).resolve())
                if info.get('available'):
                    common = str((Path(root) / _run(root, 'rev-parse', '--git-common-dir')).resolve())
                lock_key = hashlib.sha256(common.casefold().encode()).hexdigest()[:24]
                with _jobs_lock:
                    repo_lock = _repo_locks.setdefault(lock_key, threading.Lock())
                with repo_lock, Store(registry.home, data_dir=registry.home / 'checkpoint-locks' / lock_key).locked():
                    finish_checkpoint(registry, checkpoint, retry=retry)
            except Exception as error:
                with registry.connect() as c:
                    saved = json.loads(c.execute('SELECT result FROM completion_checkpoints WHERE id=?', (checkpoint,)).fetchone()['result'])
                    failure = dict(saved, publication=dict(status='pending', reason=str(error))) if _needs_publication(saved) else dict(status='error', reason=str(error))
                    c.execute('UPDATE completion_checkpoints SET result=? WHERE id=?',
                              (json.dumps(failure), checkpoint))
            finally:
                with _jobs_lock:
                    _jobs.pop(key, None)
        worker = threading.Thread(target=run, name='hub-checkpoint-' + checkpoint[:8], daemon=True)
        _jobs[key] = worker
        worker.start()


def _public(row):
    result = json.loads(row['result'])
    body = json.loads(row['body'])
    value = dict(_metadata(result), id=row['id'], at=row['at'], settingsRevision=body['settingsRevision'])
    if result.get('publication'):
        value['publication'] = result['publication']
    return value


def checkpoint_details(registry, project, checkpoint, section='files', offset=0, limit=50, commit=None):
    if section not in ('files', 'scopedFiles', 'commits', 'changesets') or offset < 0 or not 1 <= limit <= 100:
        raise ValueError('Invalid checkpoint detail pagination')
    with registry.connect() as c:
        row = c.execute('SELECT * FROM completion_checkpoints WHERE id=?', (checkpoint,)).fetchone()
    state = registry.store(project).snapshot()
    if not row or not any(t['id'] == row['task'] and t['originProject'] == row['origin'] for t in state['tasks']):
        raise ValueError('Checkpoint does not belong to selected project')
    result = json.loads(row['result'])
    if commit is not None:
        target = next((v for v in result.get('commits', []) if v.get('sha') == commit), None)
        if target is None or section != 'files':
            raise ValueError('Select files of a verified checkpoint commit')
        values = target.get('files', [])
    elif section == 'scopedFiles':
        values = result.get('reconciliation', {}).get(section, [])
    elif section == 'commits':
        values = [dict(sha=v['sha'], filesCount=len(v.get('files', []))) for v in result.get('commits', [])]
    else:
        values = result.get(section, [])
    page = values[offset:offset + limit]
    # Git paths can be long; pagination is bounded by encoded size as well as count.
    while len(json.dumps(page)) > 16000 and len(page) > 1:
        page.pop()
    end = offset + len(page)
    return dict(checkpoint=_public(row), section=section, items=page, total=len(values),
                next=end if end < len(values) else None)


def resume_pending_checkpoints(registry, tasks):
    """Resume persisted jobs from prepared metadata, without rebuilding views.

    The scheduler freshly checks each identifier and deduplicates active jobs.
    Call after releasing view/SQL contexts: cached answers must retain the same
    recovery behavior as a cold projection.
    """
    pending = set()
    for task in tasks:
        for target in [task, *task.get('stages', [])]:
            checkpoint = target.get('gitCheckpoint')
            if isinstance(checkpoint, dict) and checkpoint.get('status') == 'pending' and checkpoint.get('id'):
                pending.add(checkpoint['id'])
    for checkpoint in sorted(pending):
        schedule_checkpoint(registry, checkpoint)


def project_checkpoints(registry, project, tasks, events):
    event_ids = {e['id'] for e in events}
    with registry.connect() as c:
        rows = c.execute('SELECT * FROM completion_checkpoints ORDER BY rowid').fetchall()
    for row in rows:
        task = next((t for t in tasks if t['id'] == row['task'] and t['originProject'] == row['origin']), None)
        if not task or row['event'] not in event_ids:
            continue
        target = next((s for s in task.get('stages', []) if s['id'] == row['stage']), None) if row['stage'] else task
        if target is not None:
            target['gitCheckpoint'] = _public(row)
            if target['gitCheckpoint'].get('sha'):
                target['gitCommit'] = target['gitCheckpoint']
            if target['gitCheckpoint']['status'] == 'pending':
                schedule_checkpoint(registry, row['id'])


def _work_boundary(registry, project, task, stage):
    database = registry.home / 'coordination/coordination.sqlite3'
    if not database.exists():
        return []
    with closing(sqlite3.connect(database)) as c:
        c.row_factory = sqlite3.Row
        rows = c.execute('''SELECT w.*, s.workspace, ws.stage,
            EXISTS(SELECT 1 FROM claims cl WHERE cl.work=w.id AND cl.mode='write') AS has_write FROM work w
            JOIN sessions s ON s.id=w.session LEFT JOIN work_stages ws ON ws.work=w.id
            WHERE w.project=? AND w.task=?
            ORDER BY w.created,w.id''', (project, task)).fetchall()
        result = []
        for row in rows:
            from work_scope import stages_for
            links = stages_for(c, row['id'])
            if (stage and stage not in links) or row['status'] == 'cancelled':
                continue
            snapshot = decode_snapshot(row['git_snapshot'])
            result.append(dict(id=row['id'], status=row['status'], completedAt=row['updated'], root=snapshot.get('root') or row['workspace'],
                               write=bool(row['has_write']), stages=links, snapshot=snapshot))
        return result


def prepare_checkpoint(registry, project, origin, task, payload, retry=False):
    """Persist intent before the journal event; orphan intents cannot execute."""
    with registry.connect() as c:
        old = c.execute('SELECT id FROM completion_checkpoints WHERE project=? AND event=?',
                        (project, payload['id'])).fetchone()
    if old:
        return old['id']
    if retry or payload['kind'] not in ('task.updated', 'stage.updated', 'task.created', 'stage.created'):
        return None
    if payload.get('patch', {}).get('status') != 'done':
        return None
    stage = payload.get('stageId') if payload['kind'].startswith('stage.') else None
    target = next((s for s in (task or {}).get('stages', []) if s['id'] == stage), {}) if stage else task or {}
    if target.get('status') == 'done':
        return None
    settings = read_settings(registry.base_store(project))
    policy = settings['settings']['git']
    enabled = policy['autoCommit'] and policy['commitOn'] in ('stage-and-task', 'stage' if stage else 'task')
    checkpoint = hashlib.sha256((project + ':' + payload['id']).encode()).hexdigest()[:32]
    source_root = registry.base_store(project).root
    body = dict(settingsRevision=settings['revision'], policy=policy, root=str(source_root) if source_root is not None else None,
                title=target.get('title') or payload.get('title') or payload['taskId'],
                work=_work_boundary(registry, project, payload['taskId'], stage) if enabled and source_root is not None else [])
    result = dict(status='pending' if enabled else 'disabled')
    if enabled:
        capability = workspace_status(source_root)
        if capability['status'] != 'detected':
            result = dict(status='unavailable', reasonCode=capability['status'], layer='version_control',
                          reason='Git checkpoints are unavailable for this workspace; Hub completion is saved')
    with registry.connect() as c:
        c.execute('INSERT INTO completion_checkpoints VALUES (?,?,?,?,?,?,?,?,?)',
                  (checkpoint, project, origin, payload['taskId'], stage, payload['id'], now(),
                   json.dumps(body), json.dumps(result)))
    return checkpoint


def _boundary(registry, row, body):
    if body['work'] and not any(w.get('write', True) for w in body['work']):
        return body['root'], None
    # Completed work already covered by an earlier checkpoint must not be committed again.
    consumed = set()
    with registry.connect() as c:
        previous = c.execute('SELECT body,result FROM completion_checkpoints WHERE origin=? AND task=? AND id<>?',
                             (row['origin'], row['task'], row['id'])).fetchall()
    for item in previous:
        if json.loads(item['result'])['status'] in ('committed', 'no_changes'):
            consumed.update(w['id'] for w in json.loads(item['body'])['work'])
    work = [w for w in body['work'] if w['id'] not in consumed and w.get('write', True)]
    for w in work:
        for key in ('contentBoundaryError', 'contentAfterError'):
            if w['snapshot'].get(key):
                error = w['snapshot'][key]
                raise GitIntegrationError(error['reason'], error['reasonCode'], error['layer'])
    if any(w['status'] in ('active', 'waiting') for w in work):
        raise GitIntegrationError('Work is still active; finish the work before retrying its checkpoint', 'work_active', 'coordination')
    roots = {str(Path(w['root']).resolve()) for w in body['work'] if w.get('root') is not None and w.get('write', True) and w['snapshot'].get('resources')}
    if len(roots) > 1:
        raise GitIntegrationError('Work spans multiple checkouts; review and commit them separately')
    root = next(iter(roots), body['root'])
    info = repository(root)
    if not info.get('available'):
        raise GitIntegrationError(info.get('reason') or 'Git repository unavailable')
    scoped = [w for w in work if w['snapshot'].get('available') and w['snapshot'].get('resources')]
    if not scoped:
        covered_paths = sorted({p for w in body['work'] if w['id'] in consumed and w.get('write', True) for p in w['snapshot'].get('resources', [])})
        if covered_paths:
            from git_integration import _status_rows
            if any(_in_scope(p, covered_paths) for item in _status_rows(root) for p in _row_paths(item)):
                raise GitIntegrationError('Previously completed files contain new unreserved changes; review their scope')
            return root, None
        if info.get('dirty'):
            raise GitIntegrationError('No verified file scope for these changes; automatic commit requires a clean work reservation', 'scope_missing', 'attribution')
        return root, None
    paths = sorted({p for w in scoped for p in w['snapshot']['resources']})
    if any(p.startswith('@roots/') for p in paths):
        raise GitIntegrationError('Additional-root reservations require an explicit repository checkpoint review')
    database = registry.home / 'coordination/coordination.sqlite3'
    with closing(sqlite3.connect(database)) as c:
        active = c.execute('''SELECT s.workspace, cl.name, w.git_snapshot FROM work w JOIN sessions s ON s.id=w.session
            JOIN claims cl ON cl.work=w.id WHERE w.status IN ('active','waiting') AND cl.mode='write' ''').fetchall()
    for workspace, path, captured in active:
        workspace = decode_snapshot(captured).get('root') or workspace
        if workspace is not None and Path(workspace).resolve() == Path(root).resolve() and not path.startswith('resource:') and any(
                _in_scope(path, [p]) or _in_scope(p, [path]) for p in paths):
            raise GitIntegrationError('Another active work reservation overlaps this checkpoint; retry after it finishes')
    # Each scope keeps its earliest reservation boundary. Later reservations may
    # legitimately see earlier work dirty, but cannot authorize pre-existing edits.
    dirty = []
    for path in paths:
        first = next(w['snapshot'] for w in scoped if path in w['snapshot']['resources'])
        dirty.extend(r for r in first.get('allDirty', []) if any(_in_scope(p, [path]) for p in _row_paths(r)))
        head = first.get('head')
        if head != info.get('head'):
            if not head:
                raise GitIntegrationError('Initial Git history changed; review the checkpoint manually')
            _run(root, 'merge-base', '--is-ancestor', head, 'HEAD')
            committed = _run(root, 'diff', '--name-only', '--no-renames', '-z', head, 'HEAD').split('\0')
            if any(p and _in_scope(p, [path]) for p in committed):
                raise GitIntegrationError('Reserved files were committed during work; review the checkpoint manually', 'reserved_scope_committed', 'attribution')
    snapshot = dict(available=True, root=info['root'], head=info.get('head'), resources=paths,
                    dirty=dirty, allDirty=dirty, boundaryWorkIds=[w['id'] for w in scoped])
    return root, snapshot


def _exact_context(registry, body):
    """Compose earliest starts and latest completed bytes; originals stay in CAS."""
    from git_changesets import validate_boundary, canonical, digest, ChangesetError
    from knowledge_store import KnowledgeStore
    work = [w for w in body['work'] if w.get('write', True) and w['snapshot'].get('resources')]
    if not work or not any(w['snapshot'].get('contentBoundary') for w in work):
        return None
    if any(not w['snapshot'].get('contentBoundary') for w in work):
        raise ChangesetError('mixed_boundary_versions', 'Legacy and exact reservations require separate reviewed checkpoints')
    stores, pairs = {}, []
    for w in work:
        boundaries = []
        for key in ('contentBoundary', 'contentAfter'):
            ref = w['snapshot'].get(key)
            if (not isinstance(ref, dict) or set(ref) != {'schemaVersion', 'project', 'blob'}
                    or type(ref['schemaVersion']) is not int or ref['schemaVersion'] != 1
                    or not isinstance(ref['project'], str) or not ref['project']):
                raise ChangesetError('boundary_missing', 'The original and completed immutable boundaries are required')
            store = stores.setdefault(ref['project'], KnowledgeStore(registry, ref['project']))
            boundary = validate_boundary(json.loads(store.read_blob(ref['blob'])))
            if boundary['scope'] != sorted(w['snapshot']['resources']) or Path(boundary['root']).resolve() != Path(w['root']).resolve():
                raise ChangesetError('boundary_mismatch', 'The original reservation scope was modified')
            boundaries.append(boundary)
        if boundaries[0]['head'] != w['snapshot']['head']:
            raise ChangesetError('boundary_mismatch', 'The original reservation HEAD was modified')
        pairs.append((w.get('completedAt', 0), boundaries))
    after_order = [pair for _, pair in sorted(pairs, key=lambda entry: entry[0], reverse=True)]
    pairs = [pair for _, pair in pairs]
    template = pairs[0][0]
    if any(any(boundary[key] != template[key] for key in ('repositoryId', 'worktreeId'))
           for pair in pairs for boundary in pair):
        raise ChangesetError('boundary_mismatch', 'Reservations span different repository worktrees')
    scope = sorted({path for pair in pairs for path in pair[0]['scope']})
    def compose(index):
        files, sources = {}, {}
        ordered = pairs if index == 0 else after_order
        refs = [pair[index]['id'] for pair in ordered]
        names = {name for pair in pairs for name in pair[index]['files']}
        for name in names:
            boundary = next(pair[index] for pair in ordered
                            if any(name == path or name.startswith(path + '/') for path in pair[index]['scope']))
            if name in boundary['files']:
                files[name] = boundary['files'][name]
                sources[name] = boundary.get('sourceFiles', boundary['files'])[name]
        value = dict(schemaVersion=1, root=template['root'], repositoryId=template['repositoryId'],
                     worktreeId=template['worktreeId'], head=pairs[0][0]['head'] if index == 0 else after_order[0][1]['head'],
                     scope=scope, files=files, sourceFiles=sources, dirty=any(pair[index]['dirty'] for pair in pairs),
                     indexSha256=digest(canonical(refs)), sourceBoundaries=sorted(set(refs)))
        return validate_boundary(dict(value, id=digest(canonical(value))))
    before, after = compose(0), compose(1)
    destination = next(iter(stores.values()))
    # Cross-project transferred reservations retain their original CAS. Copy only
    # verified bytes when composing an evidence chain, with no alias rewriting.
    for boundary in (before, after):
        for item in [*boundary['files'].values(), *boundary['sourceFiles'].values()]:
            for store in stores.values():
                try:
                    data = store.read_blob(item['blob'])
                except FileNotFoundError:
                    continue
                if len(data) != item['size']:
                    raise ChangesetError('content_corrupt', 'Boundary content size changed')
                destination.blob(data)
                break
            else:
                raise ChangesetError('content_corrupt', 'Original boundary content is unavailable')
        destination.blob(canonical(boundary))
    return destination, before, after


def _completed_boundaries(registry, row, body):
    """Attach the first later completion proof without recapturing any baseline.

    A target can be closed while its work is still active. Its intent retains
    the original before reference; the owning work later supplies the immutable
    after reference. Existing captured after references are never refreshed.
    """
    current = {w['id']: w for w in _work_boundary(registry, row['project'], row['task'], row['stage'])}
    for work in body['work']:
        fresh = current.get(work['id'])
        if not fresh:
            continue
        work['status'] = fresh['status']
        if work['snapshot'].get('contentBoundary') == fresh['snapshot'].get('contentBoundary'):
            for key in ('contentAfter', 'contentAfterError'):
                if key not in work['snapshot'] and key in fresh['snapshot']:
                    work['snapshot'][key] = fresh['snapshot'][key]
                    work['completedAt'] = fresh['completedAt']


def _exact_coverage(registry, row, body, root, commits, actor, confirmation, context=None):
    from git_changesets import at_commit, create, verify_coverage, canonical, digest, ChangesetError
    context = context or _exact_context(registry, body)
    if context is None:
        return dict(verification='legacy-scope-and-trailers')
    store, before, expected = context
    previous, changesets, scoped = before, [], set()
    for sha in commits:
        after = at_commit(root, sha, before, store.blob)
        store.blob(canonical(after))
        if previous['files'] != after['files']:
            # A shared work boundary is committed once, with every captured
            # stage membership retained in the immutable coverage proof.
            stage_ids = {stage for work in body['work'] for stage in work.get('stages',
                         [row['stage']] if row['stage'] else [])}
            links = [dict(project=row['project'], task=row['task'], stage=stage)
                     for stage in sorted(stage_ids)] or [dict(project=row['project'], task=row['task'])]
            change = create(previous, after, links, actor=actor, confirmation=confirmation)
            coverage = verify_coverage(root, change, sha, store.read_blob)
            changesets.append(dict(id=change['id'], blob=store.blob(canonical(change)), project=store.project,
                                   coverage=coverage))
            scoped.update(item['path'] for item in change['changes'])
        previous = after
    if previous['files'] != expected['files']:
        raise ChangesetError('coverage_mismatch', 'Commit tree does not match the immutable completed work bytes')
    if not changesets:
        raise ChangesetError('no_changes', 'Commits contain no changes attributed to this work')
    return dict(verification='exact-content-and-ancestry', changesets=changesets, scopedFiles=sorted(scoped),
                workCoverage=[dict(work=work['id'], stages=work.get('stages', [row['stage']] if row['stage'] else []),
                                   changesets=[item['id'] for item in changesets]) for work in body['work']],
                batchId=digest(canonical([before['repositoryId'], commits])),
                beforeBoundary=before['id'], afterBoundary=expected['id'])


def _covered_commits(registry, row, body):
    work_ids = {w['id'] for w in body['work']}
    commits = {}
    with registry.connect() as c:
        rows = c.execute('SELECT body,result FROM completion_checkpoints WHERE origin=? AND task=? AND id<>?',
                         (row['origin'], row['task'], row['id'])).fetchall()
    for previous in rows:
        result = json.loads(previous['result'])
        if result.get('sha') and work_ids.intersection(w['id'] for w in json.loads(previous['body'])['work']):
            commits[result['sha']] = result
    return list(commits.values())


def finish_checkpoint(registry, checkpoint, retry=False):
    with registry.connect() as c:
        row = c.execute('SELECT * FROM completion_checkpoints WHERE id=?', (checkpoint,)).fetchone()
    if not row:
        raise ValueError('Unknown checkpoint')
    result, body = json.loads(row['result']), json.loads(row['body'])
    if _needs_publication(result):
        return _save_result(registry, row, body, result)
    if result['status'] not in ('pending', 'error') or (result['status'] == 'error' and not retry):
        return _public(row)
    base = registry.base_store(row['origin'])
    with base.locked():
        seed, events = base._load()
    if not any(e['id'] == row['event'] for e in events):
        return _public(row)
    created = None
    prepared_ids = result.get('preparedWorkIds')
    try:
        # Refresh lifecycle only, never the original captured file boundary.
        _completed_boundaries(registry, row, body)
        projected = base.project(seed, events, hierarchy=False)
        target = next((t for t in projected if t['id'] == row['task']), None)
        if row['stage'] and target:
            target = next((s for s in target['stages'] if s['id'] == row['stage']), None)
        if not target or target.get('status') != 'done':
            raise GitIntegrationError('Completion was reopened or removed; no automatic commit attempted')
        roots = {w['root'] for w in body['work']} or {body['root']}
        recovered = []
        for root in roots:
            info = repository(root)
            if not info.get('available') or not info.get('head'):
                continue
            matches = _run(root, 'log', '--all', '--reflog', '--max-count=3', '--format=%H', '--fixed-strings', '--grep=Project-Hub-Checkpoint: ' + checkpoint).splitlines()
            for sha in dict.fromkeys(matches):
                message = _run(root, 'show', '-s', '--format=%B', sha)
                if ('Project-Hub-Checkpoint: ' + checkpoint) in message.splitlines():
                    _run(root, 'merge-base', '--is-ancestor', sha, 'HEAD')
                    files = _commit_files(root, sha)
                    paths = sorted({p for w in body['work'] for p in w['snapshot'].get('resources', [])})
                    if not files or any(not _in_scope(p, paths) for p in files):
                        raise GitIntegrationError('Recovered commit contains files outside the reserved scope; review required')
                    for path in paths:
                        first = next(w['snapshot'] for w in body['work'] if path in w['snapshot'].get('resources', []))
                        if any(p in files for item in first.get('allDirty', []) for p in _row_paths(item)):
                            raise GitIntegrationError('Recovered commit overlaps pre-existing edits; review required')
                    recovered.append(dict(status='committed', sha=sha, shortSha=sha[:10], repository=str(root),
                                          files=files, recovered=True))
        if len(recovered) > 1:
            raise GitIntegrationError('Multiple commits match this checkpoint; manual review required')
        if recovered:
            result = recovered[0]
            created = result
            exact_body = dict(body, work=[work for work in body['work'] if work['id'] in prepared_ids]) if prepared_ids is not None else body
            result.update(_exact_coverage(registry, row, exact_body, result['repository'], [result['sha']],
                                         'project-git-policy', 'Recovery of the original policy-authorized checkpoint'))
        else:
            root, snapshot = _boundary(registry, row, body)
            exact_body = dict(body, work=[w for w in body['work'] if w['id'] in snapshot.get('boundaryWorkIds', [])]) if snapshot else body
            context = _exact_context(registry, exact_body) if snapshot else None
            if context is not None:
                from git_changesets import at_commit, capture, ChangesetError
                store, before, after = context
                parent = at_commit(root, snapshot['head'], before, store.blob)
                if before['files'] != parent['files']:
                    raise ChangesetError('baseline_not_in_commit_parent', 'Original bytes differ from Git parent; explicit content review is required')
                candidate = capture(root, before['scope'], store.blob)
                if candidate['files'] != after['files'] or candidate['sourceFiles'] != after['sourceFiles']:
                    raise ChangesetError('completed_bytes_changed', 'Reserved files changed after the completed work boundary')
            if snapshot:
                prepared_ids = snapshot.get('boundaryWorkIds', [])
                with registry.connect() as c:
                    c.execute('UPDATE completion_checkpoints SET result=? WHERE id=?',
                              (json.dumps(dict(status='pending', preparedWorkIds=prepared_ids)), checkpoint))
            result = commit_work(root, snapshot, row['task'], row['stage'],
                                 body['work'][-1]['id'] if body['work'] else checkpoint,
                                 body['title'], checkpoint=checkpoint,
                                 check_context=dict(project=row['project'], url=registry.check_url)
                                 if getattr(registry, 'check_url', None) else None,
                                 expected_content=context[2]['files'] if context is not None else None) if snapshot else dict(status='no_changes', repository=str(root))
            if result['status'] == 'committed':
                created = result.copy()
                result.update(_exact_coverage(registry, row, exact_body, root, [result['sha']],
                    'project-git-policy', 'Automatic checkpoint authorized by captured project Git policy ' + body['settingsRevision'], context))
            if result['status'] == 'no_changes':
                covered = _covered_commits(registry, row, body)
                if len(covered) == 1:
                    result = dict(covered[0], reused=True)
                elif covered:
                    result['commits'] = covered
            if result['status'] == 'unavailable':
                result = dict(status='error', reason=result.get('reason', 'Git unavailable'))
    except (GitIntegrationError, OSError, ValueError, sqlite3.Error) as error:
        result = dict(status='error', reason=str(error), reasonCode=getattr(error, 'reason_code',
                      'filesystem_permission_denied' if isinstance(error, PermissionError) else 'checkpoint_failed'),
                      layer=getattr(error, 'layer', 'native_permissions' if isinstance(error, PermissionError) else 'checkpoint'))
        if created:
            result['gitOutcome'] = dict(status='committed', sha=created['sha'], repository=created['repository'])
    if prepared_ids is not None:
        result['preparedWorkIds'] = prepared_ids
    return _save_result(registry, row, body, result)


def _save_result(registry, row, body, result):
    checkpoint = row['id']
    base = registry.base_store(row['origin'])
    from task_transfer import barrier
    with barrier(registry):
        result = dict({k: v for k, v in result.items() if k != 'publication'}, operationId=checkpoint)
        metadata = dict(_metadata(result), id=checkpoint, at=row['at'], settingsRevision=body['settingsRevision'])
        patch = dict(gitCheckpoint=metadata)
        if result.get('sha'):
            patch['gitCommit'] = metadata
        digest = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()[:16]
        event = dict(id='checkpoint-' + checkpoint + '-' + digest, taskId=row['task'],
                     kind='stage.updated' if row['stage'] else 'task.updated',
                     title='Git checkpoint: ' + result['status'], patch=patch)
        if row['stage']:
            event['stageId'] = row['stage']
        # Persist the verified Git outcome before publication, so a failed journal
        # write never loses a created commit or requires rerunning Git on retry.
        with registry.connect() as c:
            c.execute('UPDATE completion_checkpoints SET result=? WHERE id=?',
                      (json.dumps(dict(result, publication=dict(status='pending'))), checkpoint))
        try:
            # Metadata belongs to the original journal, but hierarchy belongs
            # to the task's current owner. A transferred task can acquire a
            # destination-only parent; validating the origin's obsolete tree
            # would strand an already verified Git outcome on every retry.
            with registry.connect() as c:
                owner = c.execute('SELECT owner FROM task_owners WHERE origin=? AND task=?',
                                  (row['origin'], row['task'])).fetchone()
            if owner is None:
                raise ValueError('Checkpoint task ownership is unavailable')
            view = registry.store(owner['owner'])
            state = view.memory_snapshot()
            if not any(t['id'] == row['task'] and t['originProject'] == row['origin']
                       for t in state['tasks']):
                raise ValueError('Checkpoint task ownership changed')
            base.record(event, hierarchy_tasks=state['tasks'])
        except Exception as error:
            with registry.connect() as c:
                c.execute('UPDATE completion_checkpoints SET result=? WHERE id=?',
                          (json.dumps(dict(result, publication=dict(status='pending', reason=str(error), reasonCode='journal_publication_failed', layer='publication'))), checkpoint))
                row = c.execute('SELECT * FROM completion_checkpoints WHERE id=?', (checkpoint,)).fetchone()
            return _public(row)
        with registry.connect() as c:
            c.execute('UPDATE completion_checkpoints SET result=? WHERE id=?', (json.dumps(result), checkpoint))
            row = c.execute('SELECT * FROM completion_checkpoints WHERE id=?', (checkpoint,)).fetchone()
    return _public(row)


def _reconcile(registry, checkpoint, commits, reason, actor):
    with registry.connect() as c:
        row = c.execute('SELECT * FROM completion_checkpoints WHERE id=?', (checkpoint,)).fetchone()
    old, body = json.loads(row['result']), json.loads(row['body'])
    previous = old.get('reconciliation', {})
    if old['status'] == 'committed' and previous.get('commits') == commits and previous.get('reason') == reason:
        return _save_result(registry, row, body, old) if _needs_publication(old) else _public(row)
    if old['status'] != 'error':
        raise ValueError('Only an error checkpoint can be reconciled; completed adoption must match exactly')
    with _jobs_lock:
        if (str(registry.home), checkpoint) in _jobs:
            raise ValueError('Checkpoint worker is still running; retry after it finishes')
    _completed_boundaries(registry, row, body)
    work = [w for w in body['work'] if w.get('write', True)]
    if any(w['status'] in ('active', 'waiting') for w in work):
        raise ValueError('Work is still active; finish the work before reconciliation')
    if not work or any(not w['snapshot'].get('available') or not w['snapshot'].get('resources') for w in work):
        raise ValueError('Reconciliation requires the original verified file scope')
    roots = {str(Path(w['root']).resolve()) for w in work}
    if len(roots) != 1:
        raise ValueError('Work spans multiple checkouts; review them separately')
    root = next(iter(roots))
    head = _run(root, 'rev-parse', '--verify', 'HEAD')
    paths = sorted({p for w in work for p in w['snapshot']['resources']})
    if any(p.startswith('@roots/') for p in paths):
        raise ValueError('Additional-root reservations cannot be reconciled here')
    details = {}
    context = _exact_context(registry, body)
    for index, sha in enumerate(commits):
        if _run(root, 'cat-file', '-t', sha) != 'commit':
            raise ValueError('Every SHA must identify a commit')
        _run(root, 'merge-base', '--is-ancestor', sha, head)
        if index:
            _run(root, 'merge-base', '--is-ancestor', commits[index - 1], sha)
        parents = _run(root, 'show', '-s', '--format=%P', sha).split()
        if len(parents) != 1:
            raise ValueError('Reconciliation requires non-merge commits with a parent')
        # Legacy manual commits separate Hub metadata with blank lines, so Git's
        # final-paragraph trailer parser misses them. Match exact metadata lines.
        message = _run(root, 'show', '-s', '--format=%B', sha)
        trailers = [line.partition(':')[2].strip() for line in message.splitlines()
                    if re.match(r'^Project-Hub-Task\s*:', line, re.I)]
        if context is None and trailers != [row['task']]:
            raise ValueError('Every commit must have exactly one matching Project-Hub-Task trailer')
        files = [p for p in _run(root, 'diff-tree', '--no-commit-id', '--name-only', '-z', '--no-renames', '-r', sha).split('\0') if p]
        details[sha] = dict(sha=sha, shortSha=sha[:10], files=files, repository=root)
    if context is not None:
        evidence = _exact_coverage(registry, row, body, root, commits, actor, reason, context)
        if _run(root, 'rev-parse', '--verify', 'HEAD') != head:
            raise ValueError('Git HEAD changed during reconciliation; retry after review')
        result = dict(status='committed', **details[commits[-1]], commits=list(details.values()),
                      reconciled=True, **evidence, reconciliation=dict(commits=commits, reason=reason, actor=actor,
                        verifiedAt=now(), head=head, scopedFiles=evidence['scopedFiles'], previousResult=old))
        return _save_result(registry, row, body, result)
    scoped_files = set()
    # Verify historical coverage up to the explicit tip, not the current checkout.
    # Later edits and the index are deliberately neither inspected nor changed.
    boundaries = {path: next(w['snapshot'] for w in work if path in w['snapshot']['resources']) for path in paths}
    histories = {}
    for base in dict.fromkeys(first.get('head') for first in boundaries.values()):
        if not base:
            raise ValueError('Original Git HEAD is unavailable; reconciliation requires review')
        _run(root, 'merge-base', '--is-ancestor', base, commits[-1])
        group = [path for path, first in boundaries.items() if first.get('head') == base]
        history = _run(root, 'rev-list', '--full-history', base + '..' + commits[-1], '--',
                       *(':(literal)' + path for path in group)).splitlines()
        if any(sha not in details for sha in history):
            raise ValueError('Supplied commits do not cover all scoped history since the original reservation')
        histories[base] = history
    for path, first in boundaries.items():
        history = histories[first['head']]
        changed = {p for sha in history for p in details[sha]['files'] if _in_scope(p, [path])}
        dirty = {p for item in first.get('allDirty', []) for p in _row_paths(item) if _in_scope(p, [path])}
        if any(not any(_in_scope(p, [d]) for p in changed) for d in dirty):
            raise ValueError('Original dirty paths are not covered by the supplied commits')
        scoped_files.update(changed)
    if not scoped_files:
        raise ValueError('Supplied commits contain no changes in the original scope')
    if _run(root, 'rev-parse', '--verify', 'HEAD') != head:
        raise ValueError('Git HEAD changed during reconciliation; retry after review')
    result = dict(status='committed', **details[commits[-1]], commits=list(details.values()),
                  reconciled=True, verification='legacy-scope-and-trailers', reconciliation=dict(commits=commits, reason=reason, actor=actor,
                    verifiedAt=now(), head=head, scopedFiles=sorted(scoped_files), previousResult=old))
    return _save_result(registry, row, body, result)


def retry_checkpoint(registry, project, task, expected, stage=None, commits=None, reason=None, actor='local-user'):
    if commits is not None or reason is not None:
        if (not isinstance(commits, list) or not 1 <= len(commits) <= 20
                or any(not isinstance(sha, str) or not re.fullmatch(r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})', sha) for sha in commits)
                or len({sha.lower() for sha in commits}) != len(commits)
                or not isinstance(reason, str) or not reason.strip() or len(reason) > 1200):
            raise ValueError('Use 1-20 unique full commit SHAs, oldest first, and a nonblank reason up to 1200 characters')
        commits = [sha.lower() for sha in commits]
    from task_transfer import barrier
    with barrier(registry):
        store = registry.store(project)
        state = store.snapshot()
        if expected != state['revision']:
            raise ValueError('Task changed; refresh before retrying')
        target = next((t for t in state['tasks'] if t['id'] == task), None)
        if stage and target:
            target = next((s for s in target['stages'] if s['id'] == stage), None)
        if not target or not target.get('gitCheckpoint'):
            raise ValueError('No checkpoint for this task or stage')
        receipt = target['gitCheckpoint']
        adoption = receipt.get('reconciliation', {})
        metadata_retry = _needs_publication(receipt) and (commits is None or (
            receipt.get('status') == 'committed' and adoption.get('commits') == commits
            and adoption.get('reason') == reason))
        if target.get('status') != 'done' and not metadata_retry:
            raise ValueError('Complete the task or stage before retrying its checkpoint')
        checkpoint = target['gitCheckpoint']['id']
        if commits is not None:
            with _operation_context(checkpoint):
                result = _reconcile(registry, checkpoint, commits, reason, actor)
            return dict(checkpoint=result, **store.snapshot())
        with registry.connect() as c:
            row = c.execute('SELECT result FROM completion_checkpoints WHERE id=?', (checkpoint,)).fetchone()
            saved = json.loads(row['result'])
            if saved['status'] == 'error' and not _needs_publication(saved):
                c.execute('UPDATE completion_checkpoints SET result=? WHERE id=?', (json.dumps(dict(saved, status='pending')), checkpoint))
        schedule_checkpoint(registry, checkpoint, retry=True)
        return dict(checkpoint=dict(target['gitCheckpoint'], status='pending') if target['gitCheckpoint']['status'] in ('error', 'pending')
                    else target['gitCheckpoint'], **store.snapshot())


def checkpoint_batch(registry, project, targets, expected, reason, *, action='preview', commit=None,
                     confirmed=None, actor='local-user', root=None):
    """Review/credit a shared candidate; every Git operation here is read-only.

    Preview preserves original checkpoint IDs and results. CAS retains the full
    review. Publication retries keep the already verified Git outcome separately.
    """
    from git_changesets import (ChangesetError, hash_value, identity, at_commit, create, compose_batch,
                                verify_batch_coverage, canonical, digest)
    from knowledge_store import KnowledgeStore
    from task_transfer import barrier
    if (action not in ('preview', 'reconcile') or not isinstance(targets, list) or not 1 <= len(targets) <= 20
            or any(not isinstance(item, dict) or set(item) - {'task', 'stage'}
                   or not isinstance(item.get('task'), str) or not item['task']
                   or ('stage' in item and (not isinstance(item['stage'], str) or not item['stage'])) for item in targets)
            or len({canonical(item) for item in targets}) != len(targets)
            or not isinstance(reason, str) or not reason.strip() or len(reason) > 1200
            or (commit is not None and not hash_value(commit, commit=True))
            or (action == 'reconcile' and (commit is None or not hash_value(confirmed)))):
        raise ChangesetError('invalid_batch', 'Use 1–20 distinct task/stage targets, a reason and an exact preview confirmation for reconciliation')
    operation = 'batch-' + digest(canonical(dict(project=project, targets=targets, expected=expected,
                                                reason=reason, commit=commit, actor=actor)))
    with barrier(registry), _operation_context(confirmed or operation):
        state = registry.store(project).snapshot()
        if state['revision'] != expected:
            raise ChangesetError('batch_revision_changed', 'Project changed; refresh the reviewed batch')
        rows, contexts, issues = [], [], []
        for selection in targets:
            task = next((item for item in state['tasks'] if item['id'] == selection['task']), None)
            target = next((item for item in task['stages'] if item['id'] == selection['stage']), None) if task and 'stage' in selection else task
            if not target or not target.get('gitCheckpoint'):
                raise ChangesetError('batch_target_unfinished', 'Every batch target must be completed with a checkpoint obligation')
            checkpoint = target['gitCheckpoint']['id']
            with _jobs_lock:
                if (str(registry.home), checkpoint) in _jobs:
                    raise ChangesetError('batch_worker_active', 'Wait for checkpoint workers before preparing the reviewed batch')
            with registry.connect() as c:
                row = c.execute('SELECT * FROM completion_checkpoints WHERE id=?', (checkpoint,)).fetchone()
            if not row:
                raise ChangesetError('boundary_missing', 'Original checkpoint intent is unavailable')
            old, body = json.loads(row['result']), json.loads(row['body'])
            replay = (action == 'reconcile' and old.get('batchId') == confirmed and old.get('sha') == commit
                      and old.get('reconciliation', {}).get('reason') == reason
                      and old.get('reconciliation', {}).get('actor') == actor)
            if target.get('status') != 'done' and not (replay and _needs_publication(old)):
                raise ChangesetError('batch_target_unfinished', 'Complete targets before reviewing a batch')
            if old['status'] not in ('error', 'committed'):
                raise ChangesetError('batch_worker_active', 'Only settled checkpoint obligations can enter a batch')
            _completed_boundaries(registry, row, body)
            rows.append((row, body, old))
            if replay:
                continue
            if any(work['status'] in ('active', 'waiting') for work in body['work'] if work.get('write', True)):
                raise ChangesetError('work_active', 'Finish original work before preparing a batch')
            context = _exact_context(registry, body)
            if context is None:
                scope = sorted({path for work in body['work'] for path in work['snapshot'].get('resources', [])})
                issues.append(dict(checkpoint=checkpoint, **selection, reasonCode='legacy_boundary_unproven',
                    layer='attribution', scopeCount=len(scope), scopeSha256=digest(canonical(scope)),
                    previousStatus=old['status'], expectedAction='Review legacy history separately; original content attribution is unavailable'))
            else:
                contexts.append(context)
        if action == 'reconcile' and all(old.get('batchId') == confirmed and old.get('sha') == commit
                and old.get('reconciliation', {}).get('reason') == reason
                and old.get('reconciliation', {}).get('actor') == actor for _, _, old in rows):
            published = [_save_result(registry, row, body, old) if _needs_publication(old) else _public(row) for row, body, old in rows]
            return dict(revision=registry.store(project).snapshot()['revision'], ready=True, batchId=confirmed,
                        batchBlob=rows[0][2]['batchBlob'], checkpoints=published, gitWrites=False, publicationRetry=True)
        if len(contexts) != len(rows) and not issues:
            raise ChangesetError('batch_adoption_conflict', 'Select the complete original reviewed batch when retrying publication')
        if issues:
            if action == 'reconcile':
                raise ChangesetError('legacy_boundary_unproven', 'Legacy obligations cannot be credited through inferred batch content')
            return dict(revision=state['revision'], ready=False, issues=issues, targets=targets, gitWrites=False)
        if len({row['id'] for row, _, _ in rows}) != len(rows):
            raise ChangesetError('invalid_batch', 'Targets refer to the same original checkpoint')
        destination = KnowledgeStore(registry, project)
        changes, scopes = [], set()
        for (row, body, old), (store, before, after) in zip(rows, contexts):
            scopes.update(before['scope'])
            for boundary in (before, after):
                for record in boundary['files'].values():
                    destination.blob(store.read_blob(record['blob']))
                destination.blob(canonical(boundary))
            link = dict(project=project, task=row['task'])
            if row['stage']:
                link['stage'] = row['stage']
            changes.append(create(before, after, [link], actor=actor, confirmation=reason))
        integration_root = root or registry.store(project).root
        context = identity(integration_root)
        if len(scopes) > 30:
            raise ChangesetError('invalid_scope', 'Split batches with more than 30 explicit paths')
        head = _run(integration_root, 'rev-parse', '--verify', 'HEAD')
        parent = head
        if commit is not None:
            parents = _run(integration_root, 'show', '-s', '--format=%P', commit).split()
            if len(parents) != 1:
                raise ChangesetError('coverage_review_required', 'Review one non-merge candidate commit at a time')
            parent = parents[0]
        template = dict(schemaVersion=1, **context, head=parent, scope=sorted(scopes), files={},
                        indexSha256=digest(b''), dirty=False)
        template['id'] = digest(canonical(template))
        before = at_commit(integration_root, parent, template, destination.blob)
        for change in changes:
            _run(integration_root, 'merge-base', '--is-ancestor', change['baseHead'], parent)
        batch = compose_batch(before, changes, destination.read_blob, destination.blob, actor=actor, confirmation=reason)
        blob = destination.blob(canonical(batch))
        coverage = verify_batch_coverage(integration_root, batch, commit, destination.read_blob, destination.blob) if commit else None
        if _run(integration_root, 'rev-parse', '--verify', 'HEAD') != head:
            raise ChangesetError('head_changed', 'Integration HEAD changed during batch review')
        from git_batch_store import register
        register(destination, blob)
        original = [dict(id=row['id'], task=row['task'], stage=row['stage'], previousResult={
            key: old[key] for key in ('status', 'reasonCode', 'layer', 'sha', 'batchId', 'verification') if key in old}) for row, _, old in rows]
        preview = dict(revision=state['revision'], ready=True, batchId=batch['id'], batchBlob=blob, batchProject=project,
                       repositoryId=batch['repositoryId'], worktreeId=batch['worktreeId'], head=parent,
                       targets=original, associations=batch['associations'], changesetCount=len(changes),
                       pathsCount=len({step['path'] for step in batch['steps']}), stepsCount=len(batch['steps']),
                       coverage=coverage, reason=reason, actor=actor, gitWrites=False)
        if commit is None:
            preview['nativeCommit'] = dict(root=str(integration_root), cas=str(destination.data),
                batchBlob=blob, confirmed=batch['id'], entryPoint='client_entry.py git-batch')
        if action == 'preview':
            return preview
        if confirmed != batch['id']:
            raise ChangesetError('batch_preview_changed', 'Confirm the exact candidate shown in the latest preview')
        for row, _, old in rows:
            if old['status'] == 'committed' and old.get('batchId') != batch['id']:
                raise ChangesetError('batch_adoption_conflict', 'A completed checkpoint already has different verified coverage')
        files = _commit_files(integration_root, commit)
        saved = []
        for (row, body, old), change in zip(rows, changes):
            if old['status'] == 'committed':
                result = old
            else:
                scoped = [item['path'] for item in change['changes']]
                result = dict(status='committed', sha=commit, shortSha=commit[:10], repository=str(integration_root),
                    files=files, commits=[dict(sha=commit, shortSha=commit[:10], files=files, repository=str(integration_root))],
                    reconciled=True, verification=coverage['verification'], batchId=batch['id'], batchBlob=blob, batchProject=project,
                    scopedFiles=scoped, changesets=[dict(id=change['id'], blob=destination.blob(canonical(change)), project=project, coverage=coverage)],
                    reconciliation=dict(commits=[commit], reason=reason, actor=actor, verifiedAt=now(), head=head,
                        scopedFiles=scoped, previousResult=old), publication=dict(status='pending'))
            saved.append((row, body, result))
        # Store the verified outcome for every target before publishing any journal.
        # Partial/lost acknowledgements can only retry this immutable metadata.
        with registry.connect() as c:
            for row, _, result in saved:
                c.execute('UPDATE completion_checkpoints SET result=? WHERE id=?', (json.dumps(result), row['id']))
        published = [_save_result(registry, row, body, result) for row, body, result in saved]
        return dict(preview, revision=registry.store(project).snapshot()['revision'], checkpoints=published)


def _registered_batch(registry, project, blob):
    from git_batch_store import load
    from knowledge_store import KnowledgeStore
    from git_changesets import ChangesetError
    tasks = registry.store(project).memory_snapshot()['tasks']
    visible = {(task['originProject'], task['id']) for task in tasks}
    with registry.connect() as c:
        rows = c.execute("SELECT origin,task,result FROM completion_checkpoints WHERE json_extract(result,'$.batchBlob')=?", (blob,)).fetchall()
    references = [json.loads(row['result']) for row in rows if (row['origin'], row['task']) in visible]
    origins = {reference.get('batchProject', project) for reference in references}
    if len(origins) > 1 or any(not isinstance(origin, str) for origin in origins):
        raise ChangesetError('batch_reference_invalid', 'Historical batch references disagree on their source project')
    origin = next(iter(origins)) if origins else project
    store = KnowledgeStore(registry, origin)
    batch = load(store, blob)
    if references and not any(link.get('project') == origin and any(
            row['task'] == link['task'] and (row['origin'], row['task']) in visible for row in rows)
            for link in batch['associations']):
        raise ChangesetError('batch_reference_invalid', 'Historical batch source does not match its original task associations')
    if not references and not any(link.get('project') == project and any(task['id'] == link['task'] for task in tasks)
                                  for link in batch['associations']):
        raise ChangesetError('batch_reference_missing', 'Batch is not associated with a visible task/checkpoint')
    return store, batch


def batch_details(registry, project, blob, section='steps', offset=0, limit=25):
    from git_changesets import hash_value
    if not hash_value(blob) or section not in ('steps', 'changesets', 'files', 'changes', 'hunks') or type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Invalid reviewed batch pagination')
    store, batch = _registered_batch(registry, project, blob)
    after = json.loads(store.read_blob(batch['afterBlob']))
    if section == 'files':
        values = [dict(path=name, **record) for name, record in sorted(after['files'].items())]
    elif section == 'changesets':
        values = [dict({key: value for key, value in item.items() if key != 'changes'}, changesCount=len(item['changes'])) for item in batch['changesets']]
    elif section == 'changes':
        values = [dict(changeset=item['id'], **change) for item in batch['changesets'] for change in item['changes']]
    elif section == 'hunks':
        values = [dict(path=step['path'], changeset=member['changeset'], **hunk)
                  for step in batch['steps'] for member in step['members'] for hunk in member['hunks']]
    else:
        values = [dict({key: value for key, value in step.items() if key != 'members'},
                       members=[dict(changeset=member['changeset'], hunksCount=len(member['hunks'])) for member in step['members']]) for step in batch['steps']]
    page = values[offset:offset + limit]
    while len(json.dumps(page)) > 16000 and len(page) > 1:
        page.pop()
    end = offset + len(page)
    return dict(batchId=batch['id'], batchBlob=blob, section=section, items=page, total=len(values),
                next=end if end < len(values) else None)


def batch_content(registry, project, blob, path, side='after', changeset=None, version=None):
    from git_changesets import hash_value, safe_path, content
    if not hash_value(blob) or side not in ('before', 'after') or (changeset is not None and not hash_value(changeset)) or (version is not None and not hash_value(version)):
        raise ValueError('Select an immutable reviewed batch version')
    safe_path(path)
    store, batch = _registered_batch(registry, project, blob)
    before, after = [json.loads(store.read_blob(batch[key])) for key in ('beforeBlob', 'afterBlob')]
    if changeset is None:
        record = (before if side == 'before' else after)['files'].get(path)
        if version is not None:
            record = next((step[side] for step in batch['steps'] if step['path'] == path and step[side]
                           and step[side]['blob'] == version), None)
    else:
        item = next((item for item in batch['changesets'] if item['id'] == changeset), {})
        change = next((item for item in item.get('changes', []) if item['path'] == path), {})
        record = change.get(side)
        if version is not None and record and record['blob'] != version:
            raise ValueError('Version is not part of the selected changeset')
    if record is None:
        raise ValueError('This file version is absent from the selected changeset')
    return dict(data=content(store.read_blob, record, 'content_corrupt'), name=path.rsplit('/', 1)[-1], sha256=record['blob'])
