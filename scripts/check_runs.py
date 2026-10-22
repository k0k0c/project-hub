"""Owner-aware ingestion and projection of externally executed checks."""
import hashlib
import json
from hub_check import validate_check
from hub_core import HubError

STATUSES = {'running': 'check.started', 'passed': 'check.passed',
            'failed': 'check.failed', 'interrupted': 'check.interrupted',
            'unknown': 'check.unknown'}
IMMUTABLE = ('runId', 'task', 'stage', 'title', 'profile', 'profileVersion', 'command',
             'scope', 'revision')
def validate(body):
    try:
        return json.loads(validate_check(body))
    except HubError as error:
        raise ValueError(error.body['message']) from error


def project_runs(events, owner=None):
    runs = {}
    for event in reversed(events):
        if not event['kind'].startswith('check.'):
            continue
        key = (event.get('originProject'), event.get('runId', event['id']))
        if key in runs:
            continue
        metadata = event.get('check', {})
        row = {**metadata, **event}
        row.pop('check', None)
        row['ownerProject'] = owner
        row['status'] = metadata.get('status') or next((k for k, v in STATUSES.items() if v == event['kind']), 'unknown')
        row['legacy'] = not bool(metadata)
        runs[key] = row
    return list(runs.values())


def list_runs(store, offset=0, limit=50):
    if not isinstance(offset, int) or offset < 0 or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError('Invalid checks pagination')
    state = store.snapshot()
    rows = project_runs(state['allEvents'], getattr(store, 'project_id', state['project'].get('id')))
    end = offset + limit
    return dict(runs=rows[offset:end], total=len(rows), next=end if end < len(rows) else None,
                revision=state['revision'])


def ingest(registry, project, body):
    from task_transfer import barrier, inventory
    body = validate(body)
    correction = body.get('correction')
    event_id = 'check-' + hashlib.sha256(body['runId'].encode()).hexdigest() + '-' + body['status']
    if correction:
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(',', ':'),
                                          ensure_ascii=True).encode()).hexdigest()
        event_id = 'check-correction-' + digest
    registry.base_store(project)
    with barrier(registry):
        snapshots, owners, _ = inventory(registry)
        previous = [(pid, event) for pid, (_, _, events) in snapshots.items() for event in events
                    if event.get('runId') == body['runId'] and event['kind'].startswith('check.')]
        if previous:
            origins = {pid for pid, _ in previous}
            if len(origins) != 1:
                raise ValueError('Ambiguous historical check runId')
            origin = previous[0][0]
            old = previous[0][1].get('check')
            if not old or any(old.get(k) != body.get(k) for k in IMMUTABLE):
                raise ValueError('Check runId already used with different launch metadata')
            owner = next((o for o in owners if o['origin'] == origin and o['task'] == body['task']), None)
            if not owner or project not in (old['launchProject'], owner['owner']):
                raise ValueError('Check belongs to another project')
            terminal = next((e for _, e in reversed(previous) if e['kind'] != 'check.started'), None)
            matching = next((e for _, e in previous if e['id'] == event_id), None)
            if matching:
                comparison = {k: v for k, v in matching['check'].items() if k != 'launchProject'}
                if comparison != body:
                    raise ValueError('Check event already recorded with different content')
                return dict(run=project_runs([dict(matching, originProject=origin)], owner['owner'])[0], duplicate=True)
            if correction:
                current = previous[-1][1]
                if correction['expectedEvent'] != current['id']:
                    raise ValueError('Check result changed; read the current event before correcting')
                if current['check'].get('startedAt') != body['startedAt'] and not (
                        body.get('summary', '').strip() and (body.get('log') or body.get('evidence'))):
                    raise ValueError('Correcting startedAt requires evidence and summary')
            elif terminal:
                raise ValueError('Check already has a terminal result')
            elif previous[-1][1]['check'].get('startedAt') != body['startedAt']:
                raise ValueError('Check runId already used with different launch metadata')
            launch_project = old['launchProject']
        else:
            if correction:
                raise ValueError('Correction requires an existing check event')
            if body['status'] != 'running':
                raise ValueError('Register check start before its result')
            owner = next((o for o in owners if o['owner'] == project and o['task'] == body['task']), None)
            if not owner:
                raise ValueError('Task does not belong to selected project')
            origin, launch_project = owner['origin'], project
        store = registry.store(owner['owner'])
        # Evidence refers to the execution project even after task ownership changes.
        evidence = list(body.get('evidence', []))
        if body.get('log') and not any(e['path'] == body['log'] for e in evidence):
            evidence.append(dict(label='Run log', path=body['log']))
        for item in evidence:
            registry.base_store(launch_project).resolve_path(item['path'])
        evidence = [dict(item, sourceProject=launch_project) for item in evidence]
        event = dict(id=event_id,
                     taskId=body['task'], kind='check.corrected' if correction else STATUSES[body['status']], runId=body['runId'],
                     title=body.get('title', 'Check'), detail=correction['reason'] if correction else body.get('summary', ''),
                     evidence=evidence, check=dict(body, launchProject=launch_project))
        if body.get('stage'):
            event['stageId'] = body['stage']
        saved = store.record(event)
        return dict(run=project_runs([dict(saved, originProject=origin)], owner['owner'])[0], duplicate=False)
