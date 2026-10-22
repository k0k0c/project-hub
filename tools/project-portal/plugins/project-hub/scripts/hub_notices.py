"""Advisory parallel-work facts and a durable queue in Hub's coordination DB.

Declared unfinished work is not proof that an agent is currently running. Queue
cursors belong to this module, independently of context/journal consumption.
"""
from __future__ import annotations

import hashlib
import json
import math
import threading
import time

from hub_core import HubError, canonical, compact, overlaps


PAGE_SIZE = 8
MAX_OWN_WORK = 32
MAX_FOREIGN_WORK = 128
MAX_RECIPIENTS = 64
MAX_RESOLUTIONS = 256
MAX_RESPONSE_BYTES = 3000
MAX_QUEUE_BYTES = 16000
FRESH_SECONDS = 300
_conditions = {}
_conditions_lock = threading.Lock()


def _condition(hub):
    key = canonical(hub.home)
    with _conditions_lock:
        return _conditions.setdefault(key, threading.Condition())


def _schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS parallel_notices (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        session TEXT NOT NULL REFERENCES sessions(id), project TEXT NOT NULL,
        fingerprint TEXT NOT NULL, foreign_work TEXT NOT NULL REFERENCES work(id),
        kind TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL,
        closed INTEGER NOT NULL DEFAULT 0,
        semantic TEXT NOT NULL DEFAULT '',
        UNIQUE(session, project, fingerprint))''')
    columns = {row['name'] for row in c.execute('PRAGMA table_info(parallel_notices)')}
    if 'semantic' not in columns:
        c.execute("ALTER TABLE parallel_notices ADD COLUMN semantic TEXT NOT NULL DEFAULT ''")
        c.execute("UPDATE parallel_notices SET semantic=fingerprint WHERE semantic=''")
    c.execute('''CREATE INDEX IF NOT EXISTS parallel_notice_recipient
        ON parallel_notices(session,project,seq)''')
    c.execute('''CREATE INDEX IF NOT EXISTS parallel_notice_open
        ON parallel_notices(session,project,closed,foreign_work)''')
    c.execute('''CREATE INDEX IF NOT EXISTS parallel_notice_latest
        ON parallel_notices(session,project,foreign_work,kind,seq)''')


def setup(hub):
    """Add the queue to the existing schema; no independent storage is created."""
    with hub.transaction() as c:
        _schema(c)


def _hash(value):
    return hashlib.sha256(compact(value).encode('utf-8')).hexdigest()


def _work(c, project, session, own):
    limit = MAX_OWN_WORK if own else MAX_FOREIGN_WORK
    rows = list(c.execute('''SELECT w.id,w.task,w.session,w.status,w.title,
        s.seen AS ownerSeen,s.state AS ownerState,ws.stage
        FROM work w JOIN sessions s ON s.id=w.session
        LEFT JOIN work_stages ws ON ws.work=w.id
        WHERE w.project=? AND w.session ''' + ('=' if own else '<>') + ''' ?
        AND w.status IN ('active','waiting') ORDER BY w.created,w.id LIMIT ?''',
        (project, session, limit + 1)))
    result = []
    for row in rows[:limit]:
        item = dict(row)
        from work_scope import describe
        describe(c, item)
        # begin enforces 30 claims / 6000 characters per work. Keep a defensive
        # cap for imported historical entries, too.
        claims = list(c.execute('SELECT name,mode FROM claims WHERE work=? ORDER BY name LIMIT 31', (row['id'],)))
        item['resources'] = [dict(claim) for claim in claims[:30]]
        item['resourcesMore'] = len(claims) > 30
        item['resourceCount'] = c.execute('SELECT COUNT(*) FROM claims WHERE work=?', (row['id'],)).fetchone()[0]
        result.append(item)
    return result, len(rows) > limit


def _index(resources, write_only=False):
    exact, ancestors = set(), {}
    for resource in resources:
        if write_only and resource['mode'] != 'write':
            continue
        name = resource['name']
        exact.add(name)
        if not name.startswith('resource:'):
            parts = name.split('/')
            for i in range(1, len(parts)):
                ancestors.setdefault('/'.join(parts[:i]), name)
    return exact, ancestors


def _indexed_overlap(index, name):
    exact, ancestors = index
    if name in exact:
        return overlaps(name, name)
    if name in ancestors:
        return overlaps(ancestors[name], name)
    if name.startswith('resource:'):
        return False
    parts = name.split('/')
    return any(prefix in exact and overlaps(prefix, name)
               for prefix in ('/'.join(parts[:i]) for i in range(1, len(parts))))


def _fact(own, foreign, session, now, dependencies=None):
    targets, relevant = [], set()
    same_task = False
    dependency = False
    for target in own:
        same = target['task'] == foreign['task']
        linked = dependencies is not None and (
            foreign['task'] in dependencies.get(target['task'], ()) or
            target['task'] in dependencies.get(foreign['task'], ()))
        matches = {right['name'] for right in foreign['resources']
                   if _indexed_overlap(target['_all'] if right['mode'] == 'write' else target['_write'], right['name'])}
        if same or linked or matches:
            targets.append(target['id'])
            same_task = same_task or same
            dependency = dependency or linked
            relevant.update(matches)
    if not targets:
        return None
    age = max(0, now - foreign['ownerSeen'])
    fresh = age <= FRESH_SECONDS
    return dict(targetSession=session, targetWork=targets[0], targetWorks=targets,
                task=foreign['task'], stage=foreign['stage'], session=foreign['session'],
                work=foreign['id'], title=foreign['title'], status=foreign['status'],
                currentStatus=foreign['status'], observedAt=now,
                resources=foreign['resources'], relevantResources=sorted(relevant),
                resourceCount=foreign['resourceCount'],
                resourcesMore=foreign['resourcesMore'],
                reason=('same_task_and_resource_overlap' if same_task and relevant else
                        'same_task' if same_task else 'task_dependency_and_resource_overlap' if dependency and relevant else
                        'task_dependency' if dependency else 'resource_overlap'),
                ownerSeen=foreign['ownerSeen'], ownerState=foreign['ownerState'],
                freshness=dict(state='fresh' if fresh else 'stale', ageSeconds=round(age, 3)),
                activity='declared-unfinished' if fresh else 'unknown',
                runningVerified=False, kind='relevant')


def _scope(own):
    # Report text, revision, checkpoints and owner liveness never cause queue
    # duplication. Scope and status changes do cause a new notification.
    return _hash(sorted((item['id'], item['task'], item['stage'], item['status'],
                         [(r['name'], r['mode']) for r in item['resources']]) for item in own))


def _bytes(value):
    return len(compact(value).encode('utf-8'))


def _compact_fact(fact, budget):
    """Exact resource subsets, never partial names; full data has a work ref."""
    result = {key: fact[key] for key in (
        'id', 'targetSession', 'targetWork', 'task', 'stage', 'session', 'work',
        'status', 'currentStatus', 'observedAt', 'reason', 'ownerSeen', 'freshness', 'activity', 'runningVerified',
        'kind', 'resolves') if key in fact}
    result.update(workRef='work:' + fact['work'], resources=[], relevantResources=[], targetWorks=[],
                  resourceCount=fact.get('resourceCount', len(fact.get('resources', []))),
                  relevantResourceCount=fact.get('relevantResourceCount', len(fact.get('relevantResources', []))),
                  targetWorkCount=fact.get('targetWorkCount', len(fact.get('targetWorks', []))),
                  resourcesMore=False, relevantResourcesMore=False, targetWorksMore=False, detailsMore=False)
    if _bytes(result) > budget:
        # Extremely long actor/task identifiers can exceed a small context
        # allocation even with no resources. Explicitly refer to full details.
        return {key: result[key] for key in (
            'id', 'work', 'workRef', 'kind', 'status', 'currentStatus', 'observedAt', 'activity',
            'runningVerified', 'resources', 'relevantResources',
            'targetWorks', 'resourceCount', 'relevantResourceCount', 'targetWorkCount') if key in result} | dict(
                resourcesMore=result['resourceCount'] > 0,
                relevantResourcesMore=result['relevantResourceCount'] > 0,
                targetWorksMore=result['targetWorkCount'] > 0,
                detailsMore=True, fieldsMore=True)
    limit = 30 if budget > MAX_RESPONSE_BYTES else 3
    for field, values in (('targetWorks', fact.get('targetWorks', [])), ('resources', fact.get('resources', [])),
                          ('relevantResources', fact.get('relevantResources', []))):
        for value in values[:limit]:
            result[field].append(value)
            if _bytes(result) > budget:
                result[field].pop()
    result['resourcesMore'] = fact.get('resourcesMore', False) or len(result['resources']) < result['resourceCount']
    result['relevantResourcesMore'] = len(result['relevantResources']) < result['relevantResourceCount']
    result['targetWorksMore'] = len(result['targetWorks']) < result['targetWorkCount']
    result['detailsMore'] = result['resourcesMore'] or result['relevantResourcesMore'] or result['targetWorksMore']
    return result


def _budget(max_bytes):
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1024:
        raise HubError('invalid_argument', 'max_bytes must be an integer of at least 1024')
    return min(max_bytes, MAX_RESPONSE_BYTES)


def _response(facts, project, coverage, after, max_bytes, pending_more=False):
    result = dict(notices=[], cursor=after, project=project, coverage=coverage,
                  more=False, moreCursor=None, queueMore=False)
    for fact in facts[:PAGE_SIZE]:
        remaining = max_bytes - _bytes(result) - 80
        if remaining < 180:
            break
        short = _compact_fact(fact, remaining)
        candidate = dict(result, notices=result['notices'] + [short], cursor=fact.get('id', after))
        if _bytes(candidate) + 40 > max_bytes:
            break
        result = candidate
    result['queueMore'] = pending_more or len(result['notices']) < len(facts)
    result['more'] = result['queueMore'] or any(item.get('detailsMore') for item in result['notices'])
    result['moreCursor'] = result['cursor'] if result['more'] else None
    return result


def _enqueue(c, session, project, fingerprint, fact, now):
    latest = c.execute('''SELECT seq,semantic,created FROM parallel_notices
        WHERE session=? AND project=? AND foreign_work=? AND kind=? ORDER BY seq DESC LIMIT 1''',
        (session, project, fact['work'], fact['kind'])).fetchone()
    if latest and latest['semantic'] == fingerprint:
        fact['observedAt'] = latest['created']
        return latest['seq'], False
    semantic = fingerprint
    fingerprint = _hash([semantic, latest['seq'] if latest else 0])
    fact['observedAt'] = now
    fact = _compact_fact(fact, MAX_QUEUE_BYTES)
    inserted = c.execute('''INSERT OR IGNORE INTO parallel_notices
        (session,project,fingerprint,foreign_work,kind,payload,created,semantic)
        VALUES (?,?,?,?,?,?,?,?)''',
        (session, project, fingerprint, fact['work'], fact['kind'], compact(fact), now, semantic)).rowcount
    row = c.execute('SELECT seq FROM parallel_notices WHERE session=? AND project=? AND fingerprint=?',
                    (session, project, fingerprint)).fetchone()
    return row['seq'], bool(inserted)


def _refresh(c, hub, session, enqueue, dependencies=None):
    bound = hub.session(c, session)
    project = bound['project']
    own, own_more = _work(c, project, session, True)
    for item in own:
        item['_all'] = _index(item['resources'])
        item['_write'] = _index(item['resources'], write_only=True)
    foreign, foreign_more = _work(c, project, session, False) if own else ([], False)
    now = time.time()
    scope = _scope(own)
    facts, changed = [], False
    for item in foreign:
        fact = _fact(own, item, session, now, dependencies)
        if fact is None:
            continue
        if enqueue:
            fingerprint = _hash(['relevant', item['id'], item['status'], item['task'], item['stage'],
                                 [(r['name'], r['mode']) for r in item['resources']], scope,
                                 fact['reason'], fact['targetWorks']])
            seq, inserted = _enqueue(c, session, project, fingerprint, fact, now)
            fact['id'] = seq
            changed = changed or inserted
        facts.append(fact)
    resolutions_more = False
    if enqueue:
        # Closed work is absent from current facts, but a previously relevant
        # notice receives a durable resolution exactly once. Claims/history stay.
        prior = list(c.execute('''SELECT n.seq,n.fingerprint,n.payload,w.status
            FROM parallel_notices n JOIN work w ON w.id=n.foreign_work
            WHERE n.session=? AND n.project=? AND n.kind='relevant' AND n.closed=0
            AND w.status IN ('done','cancelled') AND n.seq=(
                SELECT MAX(latest.seq) FROM parallel_notices latest
                WHERE latest.session=n.session AND latest.project=n.project
                AND latest.foreign_work=n.foreign_work AND latest.kind='relevant' AND latest.closed=0)
            ORDER BY n.seq LIMIT ?''',
            (session, project, MAX_RESOLUTIONS + 1)))
        resolutions_more = len(prior) > MAX_RESOLUTIONS
        for row in prior[:MAX_RESOLUTIONS]:
            fact = json.loads(row['payload'])
            fact.update(kind='resolved', status=row['status'], currentStatus=row['status'], activity='closed',
                        reason='work_closed', resolves=row['seq'])
            fingerprint = _hash(['resolved', fact['work'], row['status']])
            _, inserted = _enqueue(c, session, project, fingerprint, fact, now)
            changed = changed or inserted
            c.execute('''UPDATE parallel_notices SET closed=1
                WHERE session=? AND project=? AND foreign_work=? AND kind='relevant' ''',
                (session, project, fact['work']))
    facts.sort(key=lambda fact: (fact.get('id', 0), fact['work']))
    coverage = dict(ownWorkLimit=MAX_OWN_WORK, foreignWorkLimit=MAX_FOREIGN_WORK,
                    ownMore=own_more, foreignMore=foreign_more,
                    resourcesMore=any(item['resourcesMore'] for item in own + foreign),
                    resolutionsMore=resolutions_more, facts=len(facts),
                    dependencyCoverage='declared' if dependencies is not None else 'unknown',
                    description='Declared unfinished work only; agent execution is not verified.')
    return project, facts, changed, coverage


def notices(hub, session, enqueue=True, max_bytes=MAX_RESPONSE_BYTES, dependencies=None):
    """Current declared relevant work; GET facts can opt out of queue writes."""
    max_bytes = _budget(max_bytes)
    with (hub.transaction() if enqueue else hub.connect()) as c:
        if enqueue:
            _schema(c)
        else:
            c.execute('BEGIN')
        project, facts, changed, coverage = _refresh(c, hub, session, enqueue, dependencies)
    if changed:
        with _condition(hub):
            _condition(hub).notify_all()
    return _response(facts, project, coverage, 0, max_bytes)


def refresh_all(hub, dependency_maps=None, project=None):
    """After committed changes: <=64 recipients, 32 own / 128 foreign work each.

    Resource prefix indexes bound relevance to 32*128*30 short path lookups per
    recipient instead of an additional 30-claim quadratic factor. Dependency
    maps must be read by the caller before this SQLite transaction.
    """
    with hub.transaction() as c:
        _schema(c)
        recipients = list(c.execute('''SELECT DISTINCT s.id FROM sessions s
            JOIN work w ON w.session=s.id AND w.project=s.project
            WHERE w.status IN ('active','waiting') AND (? IS NULL OR s.project=?)
            ORDER BY s.id LIMIT ?''', (project, project, MAX_RECIPIENTS + 1)))
        changed = 0
        for recipient in recipients[:MAX_RECIPIENTS]:
            project = hub.session(c, recipient['id'])['project']
            dependencies = (dependency_maps or {}).get(project)
            _, _, inserted, _ = _refresh(c, hub, recipient['id'], True, dependencies)
            changed += int(inserted)
    if changed:
        with _condition(hub):
            _condition(hub).notify_all()
    return dict(recipients=min(len(recipients), MAX_RECIPIENTS),
                more=len(recipients) > MAX_RECIPIENTS, changed=changed)


def _page(hub, session, after, coverage, max_bytes):
    with hub.connect() as c:
        # Read recipient binding and the bounded queue/liveness projection from
        # one snapshot. Historical status/payload and dedupe remain immutable.
        c.execute('BEGIN')
        project = hub.session(c, session)['project']
        rows = list(c.execute('''SELECT n.seq,n.payload,n.created,
            w.status AS currentStatus,s.seen AS ownerSeen
            FROM parallel_notices n
            LEFT JOIN work w ON w.id=n.foreign_work
            LEFT JOIN sessions s ON s.id=w.session
            WHERE n.session=? AND n.project=? AND n.seq>? ORDER BY n.seq LIMIT ?''',
            (session, project, after, PAGE_SIZE + 1)))
    now = time.time()
    facts = []
    for row in rows[:PAGE_SIZE]:
        fact = dict(json.loads(row['payload']), id=row['seq'], observedAt=row['created'],
                    currentStatus=row['currentStatus'] or 'unknown', ownerSeen=row['ownerSeen'])
        if row['ownerSeen'] is None:
            fact['freshness'] = dict(state='unknown', ageSeconds=None)
            fresh = False
        else:
            age = max(0, now - row['ownerSeen'])
            fresh = age <= FRESH_SECONDS
            fact['freshness'] = dict(state='fresh' if fresh else 'stale', ageSeconds=round(age, 3))
        fact['activity'] = ('closed' if fact['currentStatus'] in ('done', 'cancelled') else
                            'declared-unfinished' if fresh and fact['currentStatus'] in ('active', 'waiting') else
                            'unknown')
        fact['runningVerified'] = False
        facts.append(fact)
    return _response(facts, project, coverage, after, max_bytes, pending_more=len(rows) > PAGE_SIZE)


def wait(hub, session, after, timeout=45, max_bytes=MAX_RESPONSE_BYTES, dependencies=None):
    """Replay a bounded durable page, or wait for local committed queue updates.

    Three finite rereads also observe changes from another local server process,
    whose Python condition is necessarily distinct. No session cursor is mutated.
    """
    if isinstance(after, bool) or not isinstance(after, int) or after < 0:
        raise HubError('invalid_argument', 'after must be a nonnegative notice cursor')
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
        raise HubError('invalid_argument', 'timeout must be a nonnegative finite number')
    duration = min(timeout, 45)
    max_bytes = _budget(max_bytes)
    deadline = time.monotonic() + duration
    condition = _condition(hub)
    with condition:
        reads = 0
        while True:
            current = notices(hub, session, enqueue=True, max_bytes=max_bytes, dependencies=dependencies)
            result = _page(hub, session, after, current['coverage'], max_bytes)
            if result['notices'] or result['more'] or time.monotonic() >= deadline:
                return result
            remaining = deadline - time.monotonic()
            # At most three timeout-driven fallback refreshes. Signals can wake
            # sooner; every wake reads the same durable sequence before waiting.
            interval = min(remaining, duration / 3) if reads < 3 else remaining
            condition.wait(interval)
            reads += 1
