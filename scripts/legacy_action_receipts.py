"""Read former Hub action receipts without loading or calling an agent client."""
import json

from hub_action_context import ChatActionError, HubActionContext


class LegacyActionReceipts:
    def __init__(self, registry):
        self.registry = registry

    @staticmethod
    def available(connection):
        return connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='codex_chat_actions'").fetchone() is not None

    def existing(self, project, action_id):
        with self.registry.connect() as connection:
            if not self.available(connection):
                return None
            row = connection.execute('SELECT * FROM codex_chat_actions WHERE action_id=?', (action_id,)).fetchone()
        if row is not None and row['project'] != project:
            raise ChatActionError('action_id_conflict', 409, 'Action ID belongs to another project')
        return row

    @staticmethod
    def decorate(body):
        result = json.loads(body)
        result.update(resumeAllowed=False, readOnly=True)
        return result

    def recent(self, project, task):
        HubActionContext._id(task, 'task')
        with self.registry.connect() as connection:
            if not self.available(connection):
                return []
            rows = connection.execute('''SELECT response FROM codex_chat_actions
                WHERE project=? AND task=? ORDER BY created DESC,action_id DESC LIMIT 20''', (project, task)).fetchall()
        return [self.decorate(row['response']) for row in rows]
