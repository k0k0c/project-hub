"""Read-only presentation filters for legacy Hub-owned internal operations."""
from copy import deepcopy
import hashlib
import json
import sqlite3
from pathlib import Path


def _table_exists(connection, name):
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _expected_sessions(registry, project, action_ids):
    """Derive only the service actors used by current and legacy research runners."""
    if not action_ids:
        return {}
    from agent_runtime import actor_id

    principal = 'hub-research:' + hashlib.sha256(project.encode('utf-8')).hexdigest()
    result = {action_id: {actor_id(principal, f'api:{action_id}')}
              for action_id in action_ids}
    try:
        with registry.connect() as connection:
            if not _table_exists(connection, 'client_bindings'):
                return result
            rows = connection.execute(
                "SELECT id,project,client,external_id FROM client_bindings WHERE project=? AND client='hub-api'",
                (project,)
            ).fetchall()
    except (sqlite3.Error, AttributeError, TypeError):
        return result
    for row in rows:
        action_id = row['external_id']
        if row['project'] == project and row['client'] == 'hub-api' and action_id in result:
            # Historical API-run invitations were project scoped because they
            # carried a project in client_bindings; actor_id therefore has no
            # third, global-scope project component here.
            result[action_id].add(actor_id(row['id'], f'api:{action_id}'))
    return result


def _work_evidence(registry, project, candidates):
    """Return verified work memberships; any absent or malformed evidence fails open."""
    database = registry.home / 'coordination' / 'coordination.sqlite3'
    if not candidates or not database.is_file():
        return {}
    work_ids = {work for _action, _task, _stage, work in candidates}
    try:
        with registry.coordination_connect() as connection:
            if not _table_exists(connection, 'work'):
                return {}
            tables = [name for name in ('work_stage_links', 'work_stages')
                      if _table_exists(connection, name)]
            if not tables:
                return {}
            membership = ' UNION '.join(f'SELECT work,stage FROM {name}' for name in tables)
            work_ids = sorted(work_ids)
            rows = []
            for offset in range(0, len(work_ids), 400):
                batch = work_ids[offset:offset + 400]
                placeholders = ','.join('?' for _ in batch)
                rows.extend(connection.execute(
                    f'''SELECT w.id,w.project,w.task,w.session,l.stage
                        FROM work w LEFT JOIN ({membership}) l ON l.work=w.id
                        WHERE w.id IN ({placeholders})''',
                    tuple(batch)
                ).fetchall())
    except (OSError, sqlite3.Error, AttributeError, TypeError):
        return {}
    result = {}
    for row in rows:
        item = result.setdefault(row['id'], {
            'project': row['project'], 'task': row['task'], 'session': row['session'], 'stages': set()
        })
        if row['stage']:
            item['stages'].add(row['stage'])
    return result


def _attested_actions(registry, project):
    """Read only API-run rows that can be paired with matching Hub work evidence."""
    try:
        with registry.connect() as connection:
            if not _table_exists(connection, 'api_agent_runs'):
                return {}
            rows = connection.execute(
                'SELECT project,action_id,body FROM api_agent_runs WHERE project=?', (project,)
            ).fetchall()
    except (sqlite3.Error, AttributeError, TypeError):
        return {}

    candidates = []
    for row in rows:
        action_id = row['action_id']
        try:
            body = json.loads(row['body'])
        except (ValueError, TypeError):
            continue
        if (row['project'] != project or not isinstance(action_id, str) or not action_id or
                not isinstance(body, dict) or body.get('research') is not True or
                body.get('project') != project or body.get('actionId') != action_id):
            continue
        host_task, host_stage, work = (body.get('hostTask'), body.get('hostStage'), body.get('work'))
        if not all(isinstance(value, str) and value for value in (host_task, host_stage, work)):
            continue
        expected_stage = 'api-analysis-' + hashlib.sha256(action_id.encode('utf-8')).hexdigest()[:16]
        if host_stage != expected_stage:
            continue
        candidates.append((action_id, host_task, host_stage, work))

    expected_sessions = _expected_sessions(registry, project, {item[0] for item in candidates})
    works = _work_evidence(registry, project, candidates)
    return {action_id: (host_task, host_stage, work)
            for action_id, host_task, host_stage, work in candidates
            if (evidence := works.get(work)) is not None and
            evidence.get('project') == project and evidence.get('task') == host_task and
            evidence.get('session') in expected_sessions.get(action_id, set()) and
            host_stage in evidence.get('stages', set())}


def research_actors(registry, project):
    """Service-only actors, without treating an application's name as evidence."""
    expected = _expected_sessions(registry, project, set(_attested_actions(registry, project)))
    result = set().union(*expected.values()) if expected else set()
    from agent_runtime import actor_id
    principal = 'hub-research:' + hashlib.sha256(project.encode('utf-8')).hexdigest()
    try:
        with registry.connect() as connection:
            if not _table_exists(connection, 'api_agent_runs'):
                return result
            for row in connection.execute('SELECT action_id,body FROM api_agent_runs WHERE project=?', (project,)):
                try:
                    body = json.loads(row['body'])
                except (ValueError, TypeError):
                    continue
                if (isinstance(body, dict) and body.get('research') is True and
                        body.get('project') == project and body.get('actionId') == row['action_id']):
                    result.add(actor_id(principal, 'api:' + row['action_id']))
    except (sqlite3.Error, AttributeError, TypeError):
        pass
    return result


def filter_portal_internal_tasks(registry, project, snapshot):
    """Hide only legacy research tasks with a complete, verifiable provenance chain.

    The returned object is independent of the caller's cached read model. Missing
    or malformed provenance is deliberately visible; task detail and histories
    are never edited by this presentation-only projection.
    """
    result = deepcopy(snapshot)
    if not isinstance(result, dict) or not isinstance(result.get('tasks'), list):
        return result
    actions = _attested_actions(registry, project)
    hidden = set()
    for task in result['tasks']:
        if not isinstance(task, dict) or not isinstance(task.get('id'), str):
            continue
        for action_id, (host_task, host_stage, _work) in actions.items():
            if task['id'] != host_task or task.get('title') != f'API research {action_id}':
                continue
            stages = task.get('stages')
            if isinstance(stages, list) and any(
                isinstance(stage, dict) and stage.get('id') == host_stage for stage in stages
            ):
                hidden.add(host_task)
                break
    if hidden:
        result['tasks'] = [task for task in result['tasks']
                           if not isinstance(task, dict) or task.get('id') not in hidden]
        main_task = result.get('mainTask')
        if isinstance(main_task, dict) and main_task.get('task') in hidden:
            result['mainTask'] = {'task': None, 'reason': 'none'}
    return result
