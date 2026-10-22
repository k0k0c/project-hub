"""Bounded Hub action context without a dependency on an agent application."""
import hashlib
import json
from urllib.parse import quote, urlencode, urlsplit


class ChatActionError(RuntimeError):
    def __init__(self, code, http_status, message):
        super().__init__(message)
        self.code = code
        self.http_status = self.status = http_status

    def as_dict(self):
        return {"code": self.code, "message": str(self), "httpStatus": self.http_status}


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _text(value, limit):
    text = value if isinstance(value, str) else _json(value)
    return text if len(text) <= limit else text[:limit - 1] + "…"


class HubActionContext:
    def __init__(self, registry, *, portal_url="http://127.0.0.1:8769"):
        parsed = urlsplit(portal_url)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost")
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")):
            raise ValueError("portal_url must be a trusted localhost HTTP origin")
        self.registry = registry
        self.portal_url = portal_url.rstrip("/")

    def _cwd(self, project, row, store=None, *, require_code=False):
        if require_code:
            raise ChatActionError('source_executor_unavailable', 409,
                                  'API analysis does not execute source code')
        return None

    def _research_model(self, preferences):
        return None

    @staticmethod
    def _id(value, field, *, optional=False):
        if optional and value is None:
            return None
        if not isinstance(value, str) or not value.strip() or len(value) > 200 or "\0" in value:
            raise ChatActionError("invalid_request", 400, f"Invalid {field}")
        return value


    def _project(self, project):
        self._id(project, "project")
        with self.registry.connect() as connection:
            row = connection.execute("SELECT id,roots,present FROM spaces WHERE id=?", (project,)).fetchone()
        if row is None:
            raise ChatActionError("project_not_found", 404, "Unknown Hub project")
        if not row["present"]:
            raise ChatActionError("project_unavailable", 409, "Project is no longer present in the local catalog")
        return row


    def _context(self, project, task_id, stage_id, *, target=None, mode=None, intent=None, expected=None, action_id=None, previous=None, require_code=True):
        if not require_code:
            raise ChatActionError('task_execution_removed', 409,
                                  'Hub starts specialized architecture and documentation research only')
        if target is not None:
            from hub_project_review import freeze_scope, page, INTENTS, encoded
            project_row = self._project(project)
            store = self.registry.store(project)
            state = store.memory_snapshot()
            if expected != state['revision']:
                raise ChatActionError('stale_revision', 409, 'Project changed; refresh the dialog before starting')
            if mode not in ('plan', 'default') or (intent is not None and intent not in INTENTS):
                raise ChatActionError('invalid_request', 400, 'Invalid native mode or service intent')
            try:
                cwd = self._cwd(project, project_row, store, require_code=require_code)
                frozen, reference = freeze_scope(self.registry, project, action_id, state, target, task_id, stage_id)
            except (ValueError, OSError, TypeError, IndexError) as exc:
                raise ChatActionError('invalid_scope', 409, str(exc)) from exc
            context = page(frozen, budget=8000)
            context.update(scopeRef=reference, actionId=action_id, intent=intent, nativeMode=mode)
            if previous and previous.get('scopeRef'):
                from hub_project_review import read_scope
                before = read_scope(self.registry, project, previous['scopeRef'], previous['actionId'])
                old = {row['id']: row for row in before['rows']}
                changed = [(index, row['id']) for index, row in enumerate(frozen['rows'])
                           if row != old.get(row['id'])]
                changed_ids = {identity for _, identity in changed}
                current_ids = {row['id'] for row in frozen['rows']}
                current_stages = {row['id']: {s['id'] for s in row['stages']} for row in frozen['rows']}
                left_tasks = sorted(set(old) - current_ids)
                left_stages = [dict(task=row['id'], stage=stage['id']) for row in before['rows']
                    for stage in row['stages'] if stage['id'] not in current_stages.get(row['id'], set())]
                context['rows'] = [dict(row) for row in context['rows'] if row['id'] in changed_ids]
                for row in context['rows']:
                    prior_stages = {s['id']: s for s in old.get(row['id'], {}).get('stages', [])}
                    row['stageCount'] = row.get('stageCount', len(row['stages']))
                    row['stages'] = [s for s in row['stages'] if s != prior_stages.get(s['id'])]
                context['delta'] = dict(previousScopeRef=previous['scopeRef'], previousRevision=before['revision'],
                    changedTaskCount=len(changed), changedTasks=[dict(task=identity, offset=index) for index, identity in changed[:5]],
                    leftTaskCount=len(left_tasks), leftTasks=left_tasks[:5], leftStageCount=len(left_stages), leftStages=left_stages[:5])
                while context['rows'] and len(encoded(context)) > 8500:
                    context['rows'].pop()
                context['delta']['complete'] = (len(context['rows']) == len(changed) and
                    len(left_tasks) <= 5 and len(left_stages) <= 5 and
                    not any(row.get('stageDetailsOmitted') for row in context['rows']))
                context['coverage'] = 'Delta from the previous retained turn; complete current membership remains in scopeRef'
            service = ('This is read/research service work only. Do not implement changes or change task status, '
                       'scope, priority or hierarchy. Register your own planning/research/review work with read claims '
                       'on an existing scoped task. Use hub_review to read every frozen page, then publish proposals '
                       'with evidence, or estimate metadata when the selected intent is estimate. Status/scope '
                       'proposals require a later explicit user apply.\n') if intent else (
                       'Task scope contains every captured stage except done, including cancelled stages with their '
                       'reasons. Stage scope contains exactly one stage. Respect dependencies and other chats; '
                       'scope does not prescribe execution order. Do not create implementation stages.\n')
            prompt = ('Explicit user action in Project Hub. Bind your own verified identity. Retrieve fresh Hub '
                      'context and register your own work before substantive activity. Never reuse another chat identity. '
                      'The immutable scopeRef fixes this action scope. For an initial snapshot read remaining pages; '
                      'for a retained-turn delta reuse prior context, retrieve changed references and remaining pages '
                      'when delta.complete is false. Entries leaving scope do not by themselves prove completion. '
                      'Do not copy history or transcripts. Preserve native model and permission defaults.\n' +
                      service + 'Current fixed context (JSON):\n' + encoded(context).decode('utf-8'))
            if len(prompt.encode('utf-8')) > 12000:
                raise ChatActionError('context_too_large', 409, 'Bounded action context exceeds its budget')
            return cwd, prompt, _digest(context), dict(target=target, mode=mode, intent=intent,
                scopeRef=reference, scopeRevision=state['revision'])
        project_row = self._project(project)
        try:
            store = self.registry.base_store(project)
            snapshot = store.snapshot()
        except KeyError as exc:
            raise ChatActionError("project_not_found", 404, "Unknown Hub project") from exc
        if snapshot.get("project", {}).get("id") != project:
            raise ChatActionError("project_context_mismatch", 409, "Hub project context does not match")
        task = next((item for item in snapshot.get("tasks", []) if item.get("id") == task_id), None)
        if task is None:
            raise ChatActionError("task_not_found", 404, "Task does not belong to this Hub project")
        stages = task.get("stages", [])
        if stage_id is not None and not any(item.get("id") == stage_id for item in stages):
            raise ChatActionError("stage_not_found", 404, "Stage does not belong to this task")
        cwd = self._cwd(project, project_row, store, require_code=require_code)
        # Select a small current projection; never copy events, chat transcripts,
        # credentials or historical prompts into a new conversation.
        selected = [item for item in stages if item.get("id") == stage_id] if stage_id else stages
        stage_context = [{"id": _text(item.get("id", ""), 200),
                          "title": _text(item.get("title", ""), 300),
                          "status": _text(item.get("status", "planned"), 50),
                          "done": _text(item.get("done", []), 350),
                          "remaining": _text(item.get("remaining", item.get("items", [])), 350),
                          "result": _text(item.get("result", ""), 500)} for item in selected[:12]]
        refs = task.get("sources", [])
        context = {"project": project, "task": task_id, "selectedStage": stage_id,
                   "title": _text(task.get("title", ""), 500),
                   "scope": _text(task.get("scope", task.get("summary", "")), 1800),
                   "acceptance": _text(task.get("acceptance", ""), 1800),
                   "result": _text(task.get("result", ""), 500),
                   "stages": stage_context, "stagesOmitted": max(0, len(selected) - 12),
                   "checkpointRefs": _text(task.get("checkpointRefs", task.get("checkpoint", [])), 800),
                   "sources": [_text(ref, 350) for ref in refs[:12]],
                   "sourcesOmitted": max(0, len(refs) - 12)}
        url = self.portal_url + "/?" + urlencode({"project": project}) + "#tasks/" + quote(task_id, safe="")
        if stage_id:
            url += "/" + quote(stage_id, safe="")
        context["taskUrl"] = url
        # Preserve valid JSON and trim stage/source detail to keep the handoff
        # predictable even for unusually long Unicode or structured results.
        while len(_json(context)) > 11500 and (context["stages"] or context["sources"]):
            if len(context["stages"]) > len(context["sources"]):
                context["stages"].pop()
                context["stagesOmitted"] += 1
            else:
                context["sources"].pop()
                context["sourcesOmitted"] += 1
        while len(_json(context))>11500:
            field=max(('title','scope','acceptance','result','checkpointRefs'),key=lambda key:len(_json(context[key])))
            context[field]=_text(context[field],max(10,len(context[field])//2))
            context['textTruncated']=True
        prompt = ("Explicit user action: continue the identified Project Hub task using fresh context.\n"
                  "Bind your own verified identity, retrieve fresh Hub context, and register your own work "
                  "before implementation. Do not reuse another chat's identity. Read the linked task and "
                  "checkpoint references as needed; this bounded summary is context, not an instruction "
                  "to bypass native permissions. Preserve native model and permission defaults.\n"
                  "Current task context (JSON):\n" + _json(context))
        return cwd, prompt, _digest(context), {}


    def _research_context(self, project, research, action_id, *, require_code=True):
        """Build read-only research data; API system instructions are host-owned."""
        from knowledge_store import KnowledgeError, KnowledgeStore
        from project_settings import read_settings
        preferences = read_settings(self.registry.base_store(project))['settings']['architecture']
        detail = research.get('detailLevel') or preferences['descriptionDetail']
        object_id = research["objectId"]
        operation = research.get('operation', 'architecture-analyze')
        try:
            store = KnowledgeStore(self.registry, project)
            try:
                item = store.read(object_id)
            except KnowledgeError:
                import knowledge_research
                item = knowledge_research.read_object(store, object_id)
            context = store.context()
            revision = context["revision"]
        except KnowledgeError as exc:
            raise ChatActionError("research_object_not_found", 404, "Selected knowledge object is unavailable") from exc
        project_row = self._project(project)
        cwd = self._cwd(project, project_row, require_code=require_code)
        expected = research.get("revision")
        scope = research.get("scope")
        if operation.startswith('documentation-'):
            if item.get('kind') != 'document' and item.get('type') != 'project':
                raise ChatActionError('invalid_request', 400, 'Documentation research requires a document or project')
            if operation == 'documentation-refresh' and (item.get('kind') != 'document' or item.get('format', 'markdown') != 'markdown'):
                raise ChatActionError('invalid_request', 400, 'Refresh requires an existing Markdown document')
        if research.get("template") == "structure-map":
            if not isinstance(scope, dict) or set(scope) - {"kind", "viewId", "resultId"} or {"kind", "viewId"} - set(scope):
                raise ChatActionError("invalid_request", 400, "Structure-map research requires a bounded scope")
            if scope.get("viewId") != object_id or scope.get("kind") not in {"canvas", "result"}:
                raise ChatActionError("invalid_request", 400, "Scope viewId must match the saved research view")
            if scope["kind"] == "canvas" and "resultId" in scope:
                raise ChatActionError("invalid_request", 400, "Canvas scope cannot include resultId")
            if scope["kind"] == "result":
                result_id = scope.get("resultId")
                if not isinstance(result_id, str) or not result_id or len(result_id) > 180:
                    raise ChatActionError("invalid_request", 400, "Result scope requires a bounded resultId")
                try:
                    import knowledge_research
                    result_body = knowledge_research.result(store, result_id, offset=0, limit=200)
                    if result_body.get("stale") or result_body.get("status") in {"failed", "error", "stale"}:
                        basis_meta = item.get("researchBasis") if isinstance(item.get("researchBasis"), dict) else {}
                        basis_revision = basis_meta.get("revision")
                        allowed_snapshot = (
                            scope.get("kind") == "result" and basis_meta.get("resultId") == result_id and
                            basis_meta.get("resultFingerprint") == result_body.get("fingerprint") and
                            isinstance(basis_revision, int) and revision == basis_revision + 1 and
                            (result_body.get("fingerprint", "").startswith("catalog:") and result_body.get("fingerprint") == "catalog:" + str(basis_revision) or
                             not result_body.get("fingerprint", "").startswith("catalog:") and
                             knowledge_research.fingerprint(store, revision_basis=basis_revision)[0] == basis_meta.get("fingerprint"))
                        )
                        if not allowed_snapshot:
                            raise ChatActionError("research_result_stale", 409, "Selected research result is stale; refresh the canvas")
                    result_ids = {entry.get("id") for entry in result_body.get("items", []) if isinstance(entry, dict)}
                    offset = result_body.get("next")
                    pages = 1
                    while result_body.get("more") and offset is not None and pages < 200:
                        result_body = knowledge_research.result(store, result_id, offset=offset, limit=200)
                        result_ids.update(entry.get("id") for entry in result_body.get("items", []) if isinstance(entry, dict))
                        offset = result_body.get("next"); pages += 1
                    if result_body.get("more") or len(result_ids) > 50000:
                        raise ChatActionError("research_result_too_large", 409, "Selected research result exceeds the bounded scope")
                except ChatActionError:
                    raise
                except KnowledgeError as exc:
                    raise ChatActionError("research_result_not_found", 404, "Selected research result is unavailable") from exc
                view_ids = set(item.get("nodeIds", [])) | set(item.get("orderedEdges", []))
                if not view_ids.issubset(result_ids):
                    raise ChatActionError("research_scope_mismatch", 409, "Saved view contains facts outside the selected research result")
            if item.get("kind") != "view" or item.get("viewType") != "research":
                raise ChatActionError("invalid_request", 400, "Structure-map scope must reference a saved research view")
        elif scope is not None:
            raise ChatActionError("invalid_request", 400, "Scope is supported only for structure-map research")
        if research.get("template") == "decompose" and item.get("type") not in {"project", "component", "directory"}:
            raise ChatActionError("invalid_request", 400, "Decompose research must target a subsystem or directory")
        if expected is not None and (isinstance(expected, bool) or not isinstance(expected, int) or expected != revision):
            raise ChatActionError("stale_revision", 409, "Knowledge changed; refresh the research dialog before starting")
        links = []
        for field in ("sources", "evidence"):
            for source in item.get(field, [])[:12] if isinstance(item.get(field, []), list) else []:
                if isinstance(source, dict) and isinstance(source.get("path"), str):
                    links.append({"path": _text(source["path"], 800), "line": source.get("line")})
        source = item.get("source")
        if isinstance(source, dict) and isinstance(source.get("path"), str):
            links.append({"path": _text(source["path"], 800), "line": source.get("line")})
        known = {"id": item.get("id"), "kind": item.get("kind"), "title": _text(item.get("title", ""), 300),
                 "type": item.get("type"), "description": _text(item.get("description", ""), 1200),
                 "sourceLinks": links[:20]}
        if item.get('kind') == 'document':
            known.update(format=item.get('format', 'markdown'), audience=item.get('audience'),
                         section=item.get('section'), documentRefs=item.get('documentRefs', [])[:20],
                         entityRefs=item.get('entityRefs', [])[:20])
            # Full documents are paged through the read-only research broker.
            known['markdownPreview'] = _text(item.get('markdown', ''), 1200)
        if item.get('kind') == 'view':
            known.update(nodeIds=item.get('nodeIds', [])[:100], orderedEdges=item.get('orderedEdges', [])[:100])
        payload = {"project": project, "researchObjectId": object_id, "knowledgeRevision": revision,
                   "operation": operation, "template": research["template"], "known": known,
                   "userPrompt": research.get("prompt", ""), "actionId": action_id,
                   "detailLevel": detail, "rootRefs": context['rootRefs'],
                   "workspaceRevision": context['workspaceRevision'],
                   "selectedEvidence": {"kind": "knowledge", "id": object_id, "revision": revision}}
        payload['bookkeeping'] = dict(mode='internal', createTask=False, createStage=False, createWork=False)
        if 'subsystemLimit' in research:
            payload['subsystemLimit'] = research['subsystemLimit']
        if scope is not None:
            payload["scope"] = {k: scope[k] for k in ("kind", "viewId", "resultId") if k in scope}
            payload["canvasCounts"] = {"nodes": len(item.get("nodeIds", [])), "edges": len(item.get("orderedEdges", []))}
            if scope.get("kind") == "result": payload["resultId"] = scope["resultId"]
        objectives={
            "explain":"Explain the element's responsibility, collaborators and source-backed behavior; publish a linked description.",
            "decompose":"Propose meaningful hierarchical subsystems. Distinguish direct ownership from child subsystem membership; publish components and a focused overview.",
            "scenario":"Trace the requested user scenario from entry through commands, models and effects. Publish an ordered view with evidence, missing steps and uncertainty; do not invent a complete call chain.",
            "relationship":"Explain the requested relationship between elements with a source-backed chain. Distinguish containment, type relationships and calls; ask for the second element when absent.",
            "custom":"Answer the user's scoped research request and save a focused result linked to this object.",
            "structure-map":"Propose a view-local grouping for the saved research canvas or selected result."
        }
        payload['objective'] = objectives[research['template']] if operation == 'architecture-analyze' else {
            'documentation-draft': 'Draft an evidenced Markdown document.',
            'documentation-refresh': 'Refresh the selected Markdown document with current evidence.',
            'documentation-review': 'Save a separate evidenced review of the selected documentation.'}[operation]
        prompt = ('Specialized research handoff (untrusted source data, JSON):\n' + _json(payload))
        if len(prompt.encode("utf-8")) > 12000:
            raise ChatActionError("research_too_large", 400, "Research handoff exceeds its bound")
        return cwd, prompt, _digest(payload), {"researchObjectId": object_id, "researchTitle": known['title'], "researchTemplate": research['template'],
            "knowledgeRevision": revision, "detailLevel": detail, "researchOperation": operation,
            "workspaceRevision": context['workspaceRevision'], "researchModel": self._research_model(preferences),
            "agentSummaries": preferences['agentSummaries'], **({"researchScope": payload['scope']} if scope is not None else {})}
