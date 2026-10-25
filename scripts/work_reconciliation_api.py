"""Local user reconciliation; active interruption is unavailable to MCP actors."""
import hashlib
import json
import time

from plugin_api import ServerHub, HubError
from task_transfer import barrier


def read(registry, project, task, offset=0):
    if not registry.store(project).task_context(task)['tasks']:
        raise HubError('task_missing', 'Choose a task in this project')
    if type(offset) is not int or offset < 0:
        raise HubError('invalid_offset', 'Use a nonnegative offset')
    hub = ServerHub(registry, resolve_host=False)
    with hub.connect() as c:
        rows = c.execute("SELECT * FROM work WHERE project=? AND task=? AND status IN ('active','waiting') ORDER BY created,id LIMIT 51 OFFSET ?",
                         (project, task, offset)).fetchall()
        result = []
        for row in rows[:50]:
            item = {key: row[key] for key in ('id', 'session', 'task', 'title', 'status', 'revision', 'result', 'checkpoint')}
            from work_reconciliation import preview
            preview(c, item)
            item['evidence'] = json.loads(row['evidence'])
            result.append(item)
    return dict(work=result, more=len(rows) > 50, next=offset + len(result))


def apply(registry, project, body):
    required = {'work', 'revision', 'owner', 'observedStatus', 'status', 'reason', 'result', 'confirmed', 'interruptActive'}
    if not isinstance(body, dict) or set(body) != required or type(body['revision']) is not int or type(body['interruptActive']) is not bool:
        raise HubError('invalid_reconciliation', 'Confirm the exact observed work and revision')
    if body['confirmed'] != str(body['work']) + ':' + str(body['revision']):
        raise HubError('confirmation_required', 'Confirm the work and revision displayed in the dialog')
    if body['observedStatus'] == 'active' and not body['interruptActive']:
        raise HubError('work_active', 'Explicitly confirm interruption of this active work')
    registry.store(project)
    with barrier(registry):
        hub = ServerHub(registry, resolve_host=False)
        actor = 'local-user:work-reconciliation:' + hashlib.sha256(project.encode()).hexdigest()[:32]
        with hub.transaction() as c:
            work = c.execute('SELECT project FROM work WHERE id=?', (body['work'],)).fetchone()
            if not work or work['project'] != project:
                raise HubError('work_project_mismatch', 'Select the project containing this work before reconciliation')
            c.execute("INSERT INTO sessions(id,project,state,seen) VALUES(?,?,'active',?) ON CONFLICT(id) DO NOTHING", (actor, project, time.time()))
        hub.user_reconciliation = True
        result = hub.report(actor, work=body['work'], revision=body['revision'], result=body['result'], status=body['status'],
            reconcile=dict(owner=body['owner'], status=body['observedStatus'], reason=body['reason']))
        from hub_memory import Memory
        result['planSync'] = 'saved' if Memory(hub, actor).flush_reports(work=body['work']) else 'pending'
        return result
