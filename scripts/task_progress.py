"""Read-only task progress projection. Call after calculating journal revisions.

project_progress derives ``progress``, ``agentActivity``, ``currentWorks`` and
enrolled ``currentWork`` and returns ``mainTask``. Activity reflects the last
observed lifecycle state, not a runtime heartbeat. Long thinking and a missing
Stop cannot be distinguished by elapsed time; no speculative TTL is applied.
currentWorks never treats legacy history as live work.
All clocks are injectable; no writes, timers, model calls or inferred percentages.
"""
from contextlib import closing
from datetime import datetime, timezone
from heapq import merge
from pathlib import Path
import sqlite3
import time


# A lifecycle state is evidence of current work only while its observation is
# recent.  Older active rows remain useful history, but cannot keep a live
# activity badge indefinitely when a Stop event was missed.
LIVE_ACTIVITY_WINDOW = 15 * 60


def timestamp(value):
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
    except (ValueError, TypeError, AttributeError):
        return None


def event_key(event):
    return (timestamp(event.get('at')) or 0, event.get('originProject', ''), event.get('seq', 0), event.get('id', ''))


def primary_task(tasks, events, project):
    selected = None
    for event in sorted(events, key=event_key):
        identity = (event.get('originProject', project), event['taskId'])
        patch = event.get('patch', {})
        primary = patch.get('primary')
        if isinstance(primary, dict) and primary.get('project') == project:
            if primary.get('selected'):
                selected = identity
            elif selected == identity:
                selected = None
        if selected == identity and ((event['kind'] == 'task.updated' and patch.get('status') in ('done', 'cancelled')) or
                                     event['kind'] == 'task.transferred'):
            selected = None
    return next((t for t in tasks if (t.get('originProject', project), t['id']) == selected
                 and t.get('status') not in ('done', 'cancelled')), None)


def work_activity(database, project, at):
    """Read all enrolled work and intersect active work with observed session turns.

    Work without hook history uses its explicit active/waiting boundaries. For
    hooked sessions Stop closes the interval even while a claim remains held.
    """
    if database is None or not Path(database).exists():
        return {}
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as c:
        c.row_factory = sqlite3.Row
        try:
            # Activity never consumes Git snapshots, event bodies or report
            # contents. Avoid loading those potentially large persisted blobs.
            work_columns = {r['name'] for r in c.execute('PRAGMA table_info(work)')}
            title = 'title' if 'title' in work_columns else 'id AS title'
            works = [dict(r) for r in c.execute(
                f'SELECT id,session,task,status,created,updated,{title} FROM work WHERE project=?', (project,))]
            events = [dict(r) for r in c.execute(
                'SELECT seq,session,work,kind,at FROM events WHERE project=? ORDER BY at,seq', (project,))]
            sessions = {r['id']: dict(r) for r in c.execute(
                'SELECT id,state,seen FROM sessions WHERE project=?', (project,))}
            stages = dict(c.execute('SELECT work,stage FROM work_stages')) if c.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='work_stages'").fetchone() else {}
            memberships = {work: [stage] for work, stage in stages.items()}
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='work_stage_links'").fetchone():
                for work, stage in c.execute('SELECT work,stage FROM work_stage_links ORDER BY work,stage'):
                    if stage not in memberships.setdefault(work, []):
                        memberships[work].append(stage)
            phases = dict(c.execute('SELECT id,phase FROM work')) if 'phase' in work_columns else {}
            waiting_kinds = dict(c.execute('SELECT id,waiting_kind FROM work')) if 'waiting_kind' in work_columns else {}
        except sqlite3.OperationalError:
            return {}
    result = {}
    stops = {'Stop', 'SubagentStop', 'Interrupt', 'SessionEnd'}
    starts = {'SessionStart', 'UserPromptSubmit', 'PreToolUse', 'McpConnect', 'SubagentStart'}
    lifecycle = stops | starts
    own_by_work, hooks_by_session = {}, {}
    for event in events:
        if event['kind'].startswith('work.'):
            own_by_work.setdefault(event.get('work'), []).append(event)
        elif event['kind'] in lifecycle:
            hooks_by_session.setdefault(event.get('session'), []).append(event)
    for work in works:
        entry = result.setdefault(work['task'], {'active': False, 'latest': 0, 'intervals': [], 'currentWorks': [], 'unknown': False, 'stages': {}})
        session = sessions.get(work['session'], {})
        session_state = session.get('state')
        seen = timestamp(session.get('seen'))
        fresh = seen is not None and at - seen <= LIVE_ACTIVITY_WINDOW
        linked = memberships.get(work['id'], [])
        stage_infos = [entry['stages'].setdefault(identity, {'unknown': False, 'sessions': set()}) for identity in linked]
        if work['status'] in ('active', 'waiting') and (
                session_state not in ('active', 'idle', 'interrupted', 'closed') or
                (session_state == 'active' and not fresh)):
            entry['unknown'] = True
            entry.setdefault('unknownSessions', set()).add(work['session'])
            for stage_info in stage_infos:
                stage_info['unknown'] = True
                stage_info.setdefault('unknownSessions', set()).add(work['session'])
        if work['status'] == 'waiting':
            entry.setdefault('waitingSessions', set()).add(work['session'])
            for stage_info in stage_infos:
                stage_info.setdefault('waitingSessions', set()).add(work['session'])
        own = own_by_work.get(work['id'], [])
        hooks = hooks_by_session.get(work['session'], [])
        # SQL already orders both subsequences; merge keeps the prior stable
        # own-before-hook tie order without sorting or rescanning the journal.
        boundaries = merge(own, hooks, key=lambda e: (e['at'], e['seq']))
        working, awake, begin = False, not hooks, None
        for event in boundaries:
            before = working and awake
            if event['kind'].startswith('work.'):
                working = event['kind'] in ('work.started', 'work.active')
            else:
                awake = event['kind'] in starts
            after = working and awake
            if after and not before:
                begin = max(event['at'], work['created'])
            elif before and not after and begin is not None:
                entry['intervals'].append((begin, event['at']))
                begin = None
        if not own:
            begin = work['created']
            working = work['status'] == 'active'
            if not working:
                entry['intervals'].append((begin, work['updated']))
                begin = None
        active = work['status'] == 'active' and session_state == 'active' and fresh
        entry['active'] |= active
        if active:
            for stage_info in stage_infos:
                stage_info['sessions'].add(work['session'])
            entry['latest'] = max(entry['latest'], work['updated'])
            entry['currentWorks'].append(dict(id=work['id'], eventId=work['id'], title=work.get('title', work['id']),
                stageId=stages.get(work['id']), session=work['session'], source='coordination',
                at=datetime.fromtimestamp(work['created'], timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z'),
                updatedAt=datetime.fromtimestamp(work['updated'], timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')))
            if 'phase' in work_columns:
                entry['currentWorks'][-1].update(stageIds=linked, phase=phases.get(work['id'], 'legacy'),
                                                 waitingKind=waiting_kinds.get(work['id']))
        if begin is not None and working and awake:
            end = at if active else min(at, sessions.get(work['session'], {}).get('seen', work['updated']))
            entry['intervals'].append((begin, end))
    return result


def active_seconds(intervals, since, at):
    # Union overlapping executors so an hour of parallel work is one active hour.
    total, end = 0, since
    for start, stop in sorted(intervals):
        start, stop = max(start, since, end), min(stop, at)
        if stop > start:
            total += stop - start
            end = stop
    return total


def project_progress(tasks, events, project, database=None, primary_events=None, at=None):
    at = time.time() if at is None else timestamp(at)
    activity = work_activity(database, project, at)
    latest = {}
    events_by_task = {}
    for event in events:
        events_by_task.setdefault(event['taskId'], []).append(event)
    for task in tasks:
        info = activity.get(task['id'])
        closed = task.get('status') in ('done', 'cancelled')
        task['currentWorks'] = sorted(info['currentWorks'], key=lambda w: (w['updatedAt'], w['at'], w['id']), reverse=True) if info and not closed else []
        session_count = len({w['session'] for w in task['currentWorks']})
        waiting = len(info.get('waitingSessions', [])) if info and not closed else 0
        observed = 'active' if session_count else 'unknown' if info is None or info['unknown'] else 'waiting' if waiting else 'idle'
        task['agentActivity'] = dict(state='idle' if closed else observed, sessions=session_count)
        if waiting:
            task['agentActivity']['waitingSessions'] = waiting
        task['agentSessions'] = dict(active=sorted({w['session'] for w in task['currentWorks']}),
            unknown=sorted(info.get('unknownSessions', [])) if info and not closed else [],
            waiting=sorted(info.get('waitingSessions', [])) if info and not closed else [])
        for stage in task.get('stages', []):
            stage_info = info['stages'].get(stage['id']) if info else None
            stage_closed = closed or stage.get('status') in ('done', 'cancelled')
            count = len(stage_info['sessions']) if stage_info and not stage_closed else 0
            waiting = len(stage_info.get('waitingSessions', [])) if stage_info and not stage_closed else 0
            state = 'active' if count else 'unknown' if stage_info is None or stage_info['unknown'] else 'waiting' if waiting else 'idle'
            stage['agentActivity'] = dict(state='idle' if stage_closed else state, sessions=count)
            if waiting:
                stage['agentActivity']['waitingSessions'] = waiting
            stage['agentSessions'] = dict(active=sorted(stage_info['sessions']) if stage_info and not stage_closed else [],
                unknown=sorted(stage_info.get('unknownSessions', [])) if stage_info and not stage_closed else [],
                waiting=sorted(stage_info.get('waitingSessions', [])) if stage_info and not stage_closed else [])
        if task['currentWorks']:
            task['currentWork'] = dict(task['currentWorks'][0])
        elif info is not None or closed:
            task.pop('currentWork', None)
        if info is None:
            current = task.get('currentWork') or {}
            started = timestamp(current.get('at'))
            info = {'active': bool(current), 'latest': started or 0,
                    'intervals': [(started, at)] if started is not None else []}
        active = info['active'] and task.get('status') not in ('done', 'cancelled')
        estimate = task.get('estimate')
        reviewed = timestamp((estimate or {}).get('updatedAt'))
        reason = 'missing' if not estimate else 'legacy' if reviewed is None else None
        if reviewed is not None:
            task_events = events_by_task.get(task['id'], [])
            review_seq = max((e.get('seq', 0) for e in task_events if
                              'estimate' in e.get('patch', {}) and timestamp(e.get('at')) == reviewed), default=-1)
            if any(e['kind'] in ('stage.updated', 'stage.created') and
                   e.get('patch', {}).get('status') == 'done' and
                   ((timestamp(e.get('at')) or 0) > reviewed or
                    (timestamp(e.get('at')) == reviewed and e.get('seq', 0) > review_seq)) for e in task_events):
                reason = 'milestone'
            elif active_seconds(info['intervals'], reviewed, at) >= 3600:
                reason = 'interval'
        task['progress'] = dict(reviewDue=bool(reason) and task.get('status') not in ('done', 'cancelled'),
                                reason=reason, updatedAt=(estimate or {}).get('updatedAt') if reviewed is not None else None,
                                active=bool(active))
        latest[task['id']] = info['latest']
    selected = primary_task(tasks, events if primary_events is None else primary_events, project)
    if selected:
        return dict(task=selected['id'], reason='explicit')
    # Primary fallback follows the plan status, not observed agent liveness.
    # A task can be explicitly in progress while no connected chat is active.
    active = [t for t in tasks if t.get('status') == 'active']
    estimated = [t for t in active if isinstance((t.get('estimate') or {}).get('hoursHigh'), (int, float))]
    if estimated:
        selected = max(estimated, key=lambda t: (t['estimate']['hoursHigh'], t['estimate'].get('hoursLow', 0), latest[t['id']], t['id']))
        return dict(task=selected['id'], reason='largest-active')
    if active:
        return dict(task=max(active, key=lambda t: (latest[t['id']], t['id']))['id'], reason='latest-active')
    return dict(task=None, reason='none')
