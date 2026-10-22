"""Specialized API research; previous task/native receipts stay readable history."""
import json

from agent_providers import Providers
from api_agent_runs import ApiAgentRuns
from hub_action_context import HubActionContext, ChatActionError
from legacy_action_receipts import LegacyActionReceipts


class UnifiedActions:
    RESEARCH_OPERATIONS = frozenset({'architecture-analyze', 'documentation-draft', 'documentation-refresh', 'documentation-review'})

    def __init__(self, registry, *, portal_url='http://127.0.0.1:8769', providers=None, driver_factory=None):
        self.registry = registry
        self.context = HubActionContext(registry, portal_url=portal_url)
        self.history = LegacyActionReceipts(registry)
        self.providers = providers or Providers(registry)
        options = dict(providers=self.providers)
        if driver_factory is not None:
            options['driver_factory'] = driver_factory
        self.api = ApiAgentRuns(registry, self.context, **options)

    def capabilities(self, project):
        self.context._project(project)
        provider = self.providers.selected()
        if provider is None:
            return dict(enabled=False, transport='none', hubResult=False, nativeChat=False,
                        sourceExecution=False, taskExecution=False, reason='provider_required')
        return dict(enabled=not self.api._stop.is_set(), transport='api', provider=provider['id'],
                    hubResult=True, nativeChat=False, sourceExecution=False, taskExecution=False,
                    operations=['architecture-analyze', 'documentation-draft', 'documentation-refresh', 'documentation-review'],
                    reason='API research saves results in Hub.')

    def models(self, project):
        provider = self.providers.selected()
        if provider is None:
            return dict(models=[], transport='none')
        self.context._project(project)
        return dict(models=[dict(id=provider['config']['model'], name=provider['name'],displayName=provider['name'],
                                 provider=provider['config']['provider'], nativeChat=False, sourceExecution=False)])

    def _route(self, project, action_id):
        if self.api.existing(project, action_id) is not None:
            return self.api
        existing = self.history.existing(project, action_id)
        if existing is not None:
            raise ChatActionError('legacy_action_read_only', 409, 'Previous native actions remain available as read-only history')
        return self.api

    def start(self, project, task, action_id, stage=None, thread_id=None, **options):
        self.context._project(project)
        raise ChatActionError('task_execution_removed', 409, 'Hub research cannot execute ordinary tasks, stages or project task reviews')

    def start_research(self, project, research, action_id):
        if not isinstance(research, dict) or research.get('operation') not in self.RESEARCH_OPERATIONS:
            raise ChatActionError('invalid_research_operation', 400, 'Select an architecture or documentation research operation')
        return self._route(project, action_id).start_research(project, research, action_id)

    def answer(self, project, action_id, request_id, answers):
        self.context._project(project)
        raise ChatActionError('task_execution_removed', 409, 'Research requests do not continue ordinary task chats')

    def cancel(self, project, action_id):
        self.context._project(project)
        existing = self.api.existing(project, action_id)
        if existing is None:
            if self.history.existing(project, action_id) is not None:
                raise ChatActionError('legacy_action_read_only', 409, 'Previous native actions remain available as read-only history')
            raise ChatActionError('action_not_found', 404, 'Research request is unavailable')
        if not json.loads(existing['body']).get('research'):
            raise ChatActionError('task_execution_removed', 409, 'Only research requests can be cancelled through this interface')
        return self.api.cancel(project, action_id)

    def recent(self, project, task):
        self.context._project(project)
        combined = self.history.recent(project, task)+self.api.recent(project, task)
        combined = [dict(item, resumeAllowed=False, readOnly=not item.get('research') or item.get('readOnly', False)) for item in combined]
        return sorted(combined, key=lambda item:(item.get('createdAt',0),item['actionId']), reverse=True)[:20]

    def research_history(self, project, offset=0, limit=20):
        self.context._project(project)
        try:
            offset, limit = max(0,int(offset)), min(20,max(1,int(limit)))
        except (ValueError,TypeError):
            raise ChatActionError('invalid_request', 400, 'Invalid history page') from None
        # One SQL union retains exact pagination across both durable ledgers.
        with self.registry.connect() as connection:
            legacy = ('''SELECT response AS body,created AS stamp,action_id FROM codex_chat_actions
                WHERE project=? AND task GLOB '__research__:*' UNION ALL '''
                if self.history.available(connection) else '')
            arguments = [project] if legacy else []
            arguments.extend([project, limit+1, offset])
            rows = connection.execute('''SELECT body FROM (''' + legacy + '''
                SELECT body,CAST(json_extract(body,'$.createdAt') AS REAL) AS stamp,action_id
                FROM api_agent_runs WHERE project=? AND json_extract(body,'$.research')=1)
                ORDER BY CASE WHEN json_extract(body,'$.status') IN ('requested','accepted','running','needs_attention') THEN 0 ELSE 1 END,
                stamp DESC,action_id DESC LIMIT ? OFFSET ?''', arguments).fetchall()
        items = []
        for row in rows[:limit]:
            body = json.loads(row['body'])
            if body.get('transport')=='api':
                items.append(body)
            else:
                items.append(self.history.decorate(row['body']))
        more = len(rows)>limit
        return dict(items=items,offset=offset,more=more,next=offset+limit if more else None)

    def close(self):
        self.api.close()
