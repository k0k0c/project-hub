"""Explicit project-authorized work closure; never an ownership transfer."""
import json


def request(value):
    from hub_core import HubError, clean_text
    if not isinstance(value, dict) or set(value) - {'owner', 'status', 'reason'}:
        raise HubError('invalid_reconciliation', 'Supply the observed owner, status and a reconciliation reason')
    if value.get('status') not in ('active', 'waiting'):
        raise HubError('invalid_reconciliation', 'Observe active/waiting work before reconciliation')
    return dict(owner=clean_text(value.get('owner'), 'owner', 128), status=value['status'],
                reason=clean_text(value.get('reason'), 'reason', 1200))


def authorize(connection, session, work, value, status, phase, waiting_kind, *, user_action=False):
    from hub_core import HubError
    if not work or work['project'] != connection.execute('SELECT project FROM sessions WHERE id=?', (session,)).fetchone()[0]:
        raise HubError('work_project_mismatch', 'Select the project containing this work before reconciliation')
    if status not in ('done', 'cancelled') or phase is not None or waiting_kind is not None:
        raise HubError('invalid_reconciliation', 'Reconciliation only completes or cancels work; it does not resume or change its phase')
    if work['session'] != value['owner'] or work['status'] != value['status']:
        raise HubError('revision_conflict', 'Work ownership or status changed; read it again before reconciliation', revision=work['revision'])
    if work['session'] == session:
        raise HubError('reconciliation_not_required', 'Use an ordinary owned report to finish your own work')
    if work['status'] == 'active' and not user_action:
        raise HubError('work_active', 'Coordinate with the active worker first. Interrupting active work requires confirmation in the Hub work reconciliation dialog')
    owner = connection.execute('SELECT seen FROM sessions WHERE id=?', (work['session'],)).fetchone()
    return dict(actor=session, owner=work['session'], previousStatus=work['status'],
                previousRevision=work['revision'], reason=value['reason'], userAction=user_action,
                ownerSeen=owner[0] if owner else None,
                previousResult=work['result'], previousCheckpoint=work['checkpoint'],
                previousEvidence=json.loads(work['evidence']), gitBoundary='preserved')


def preview(connection, item):
    if item['status'] not in ('active', 'waiting'):
        return
    owner = connection.execute('SELECT seen FROM sessions WHERE id=?', (item['session'],)).fetchone()
    item['reconciliation'] = dict(owner=item['session'], status=item['status'],
        ownerSeen=owner[0] if owner else None, activeConfirmationRequired=item['status'] == 'active',
        instruction='Use hub_report with this revision, terminal status and reconcile={owner,status,reason}. '
                    'Active work requires user confirmation in the Hub work reconciliation dialog. '
                    'Owner activity is an observation, not proof of execution. Ownership and Git boundaries stay unchanged.')
