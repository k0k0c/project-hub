"""Explicit user actions driving owned Codex stdio runs from local Hub tasks."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import quote, urlencode, urlsplit

from codex_adapter import CodexAdapter, CodexAdapterError
from hub_action_context import HubActionContext, ChatActionError, _json, _digest, _text










class ChatActions(HubActionContext):
    """Persistent action receipts, in-memory owned runtimes, no desktop attach.

    The HTTP caller must authenticate its local explicit button action. This
    service accepts no caller cwd, prompt, executable or permission overrides.
    """
    def __init__(self, registry, adapter_factory=CodexAdapter, *,
                 portal_url="http://127.0.0.1:8769"):
        parsed = urlsplit(portal_url)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost")
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or parsed.path not in ("", "/")):
            raise ValueError("portal_url must be a trusted localhost HTTP origin")
        self.registry = registry
        self.adapter_factory = adapter_factory
        self.portal_url = portal_url.rstrip("/")
        self._lock = threading.RLock()
        self._runtimes = {}
        self._workers = set()
        self._stop = threading.Event()
        self._model_lock = threading.Lock()
        self._model_cache = None
        with registry.connect() as connection:
            connection.execute('''CREATE TABLE IF NOT EXISTS codex_chat_actions(
                project TEXT NOT NULL, task TEXT NOT NULL, action_id TEXT NOT NULL,
                request_digest TEXT NOT NULL, status TEXT NOT NULL,
                thread_id TEXT, turn_id TEXT, error TEXT, context_digest TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL, response TEXT NOT NULL,
                PRIMARY KEY(action_id))''')
            connection.execute('CREATE INDEX IF NOT EXISTS codex_actions_history ON codex_chat_actions(project,task,created DESC,action_id DESC)')
            connection.execute("CREATE INDEX IF NOT EXISTS codex_research_history ON codex_chat_actions(project,CASE WHEN status IN ('requested','accepted','running','needs_attention') THEN 0 ELSE 1 END,created DESC,action_id DESC) WHERE task GLOB '__research__:*'")



    @staticmethod
    def _enabled():
        return os.environ.get("PROJECT_HUB_CODEX_ADAPTER") == "stdio"

    def _research_model(self, preferences):
        return preferences['model']

    def capabilities(self, project):
        """No native initialization, discovery scan, model call or data replay."""
        self._project(project)
        enabled = self._enabled() and not self._stop.is_set()
        return {"enabled": enabled, "transport": "stdio", "experimental": True,
                "desktopAttachment": "unverified", "resumeOwnedOnly": True,
                "resumeProof": "same-retained-runtime-only", "approvalUi": "unsupported",
                "reason": ("Запуск из Hub доступен; продолжение требует сохранённого собственного native чата"
                           if enabled else "Адаптер запуска Codex отключён")}

    def models(self, project):
        """Explicit read-only catalog request; never starts a native thread."""
        self._project(project)
        if not self._enabled() or self._stop.is_set():
            return {'models': [], 'error': 'Адаптер запуска Codex отключён'}
        with self._model_lock:
            if self._model_cache and time.monotonic() - self._model_cache[0] < 60:
                return json.loads(_json(self._model_cache[1]))
            adapter = None
            try:
                adapter = self.adapter_factory()
                result = adapter.models()
                self._model_cache = (time.monotonic(), result)
                return result
            except CodexAdapterError:
                return {'models': [], 'error': 'Не удалось получить модели Codex. Проверьте установку и вход в аккаунт.'}
            finally:
                if adapter is not None:
                    adapter.close()

    def _cwd(self, project, row, store=None, *, require_code=True):
        if not require_code:
            return None
        try:
            from project_workspaces import local_access
            roots = json.loads(row['roots'])
            access = local_access(self.registry, project, roots)
            available = sorted(access['available'], key=int)
            if not available or store is not None and Path(store.root).resolve() != Path(roots[0]).resolve():
                raise ValueError('root unavailable')
            return str(Path(roots[int(available[0])]).resolve(strict=True))
        except (ValueError, OSError, TypeError, IndexError, KeyError) as exc:
            raise ChatActionError('project_root_unavailable', 409, 'Authoritative project root is unavailable') from exc



    def _existing(self, project, action_id):
        with self.registry.connect() as connection:
            return connection.execute("SELECT * FROM codex_chat_actions WHERE action_id=?",
                                      (action_id,)).fetchone()

    def _update(self, project, action_id, status, *, thread_id=None, turn_id=None, error=None, attention=None, activity=None, model=None):
        with self.registry.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT * FROM codex_chat_actions WHERE project=? AND action_id=?",
                                         (project, action_id)).fetchone()
                response = json.loads(row["response"])
                response.update(status=status, updatedAt=time.time())
                if thread_id is not None:
                    response["threadId"] = thread_id
                if turn_id is not None:
                    response["turnId"] = turn_id
                response["error"] = error
                response['attention'] = attention
                if activity is not None:
                    response['activity'] = activity
                if model is not None:
                    response['model'] = model
                connection.execute('''UPDATE codex_chat_actions SET status=?,thread_id=?,turn_id=?,
                    error=?,updated=?,response=? WHERE project=? AND action_id=?''',
                    (status, response["threadId"], response["turnId"], _json(error) if error else None,
                     response["updatedAt"], _json(response), project, action_id))
                connection.commit()
                return response
            except BaseException:
                connection.rollback()
                raise

    def start(self, project, task, action_id, stage=None, thread_id=None, *, target=None, mode=None, intent=None, expected=None, _research=None):
        """Only an authenticated explicit human button may call this mutation."""
        for value, name in ((project, "project"), (action_id, "action_id")):
            self._id(value, name)
        self._id(task, 'task', optional=target == 'project' or _research is not None)
        if target == 'project' and intent is None:
            raise ChatActionError('invalid_request', 400, 'Project actions require a service intent')
        self._id(stage, "stage", optional=True)
        self._id(thread_id, "thread_id", optional=True)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", action_id):
            raise ChatActionError("invalid_request", 400, "Invalid action_id")
        self._project(project)
        if not self._enabled() or self._stop.is_set():
            raise ChatActionError("adapter_disabled", 503, "Owned Codex adapter is disabled")
        signature_payload = {"project": project, "task": task, "stage": stage, "threadId": thread_id}
        if _research is not None: signature_payload["research"] = _research
        signature = _digest(signature_payload)
        if target is not None:
            signature = _digest(dict(project=project, task=task, stage=stage, threadId=thread_id,
                                     target=target, mode=mode, intent=intent, expected=expected))
        task_key = '__project_review__' if target == 'project' else task
        with self._lock:
            existing = self._existing(project, action_id)
            if existing is not None:
                if existing["request_digest"] != signature:
                    raise ChatActionError("action_id_conflict", 409, "Action ID already has a different request")
                return json.loads(existing["response"])
            runtime = None
            previous_response = None
            if thread_id is not None:
                runtime = self._runtimes.get(thread_id)
                if runtime is None:
                    raise ChatActionError("resume_unverified", 409, "Thread has no retained owned runtime; resume is unverified")
                if runtime["project"] != project or runtime["task"] != task_key:
                    raise ChatActionError("thread_ownership_mismatch", 409, "Thread belongs to a different Hub task or project")
                previous = self._existing(project, runtime["actionId"])
                if runtime["status"] != "completed" or previous is None or previous["status"] != "completed":
                    raise ChatActionError("thread_not_idle", 409, "Owned thread has no verified completed idle turn")
                previous_response = json.loads(previous['response'])
            if _research is not None:
                cwd, prompt, context_digest, scope_metadata = self._research_context(project, _research, action_id)
            else:
                cwd, prompt, context_digest, scope_metadata = self._context(project, task, stage,
                    target=target, mode=mode, intent=intent, expected=expected, action_id=action_id, previous=previous_response)
            if runtime and runtime['cwd'] != cwd:
                raise ChatActionError('thread_ownership_mismatch', 409, 'Thread belongs to a different Hub checkout')
            active_count = sum(item['status'] not in ('completed','failed','interrupted')
                               for item in self._runtimes.values())
            if active_count >= 4 or (thread_id is None and len(self._runtimes) >= 32):
                raise ChatActionError("adapter_capacity", 503, "Owned Codex runtime capacity reached")
            now = time.time()
            response = {"project": project, "task": task, "stage": stage, "actionId": action_id,
                        "status": "requested", "threadId": thread_id, "turnId": None, "error": None,
                        "contextDigest": context_digest, "transport": "stdio",
                        "desktopAttachment": "unverified", "createdAt": now, "updatedAt": now}
            response.update(scope_metadata)
            # DB reservation also deduplicates separate service instances. Never
            # hold a SQLite writer transaction while talking to native Codex.
            with self.registry.connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    raced = connection.execute("SELECT * FROM codex_chat_actions WHERE action_id=?",
                                               (action_id,)).fetchone()
                    if raced is not None:
                        connection.rollback()
                        if raced["request_digest"] != signature:
                            raise ChatActionError("action_id_conflict", 409, "Action ID already has a different request")
                        return json.loads(raced["response"])
                    connection.execute("INSERT INTO codex_chat_actions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (project, task_key, action_id, signature, "requested", thread_id, None, None,
                         context_digest, now, now, _json(response)))
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
            adapter = runtime["adapter"] if runtime else None
            try:
                if adapter is None:
                    adapter = self.adapter_factory()
                    model = scope_metadata.get('researchModel')
                    created = adapter.create_thread(cwd, **({'model': model} if model else {}))
                    thread_id = created["threadId"]
                    response = self._update(project, action_id, "requested", thread_id=thread_id, model=created.get('model'))
                    runtime = {"adapter": adapter, "project": project, "task": task_key, "cwd": cwd,
                               "actionId": action_id, "status": "requested", 'agentSummaries': scope_metadata.get('agentSummaries', True)}
                    self._runtimes[thread_id] = runtime
                    adapter.resume_guard = lambda identity, expected=thread_id: identity == expected
                    # Creation is already persisted. The owned, newly created
                    # thread is safe to resume once, before its first turn.
                runtime.update(actionId=action_id, status="requested")
                native_options = dict(collaboration_mode=mode) if target is not None else {}
                result = adapter.start(cwd, prompt, thread_id=thread_id, **native_options)
                turn_id = result.get("turnId")
                if result.get("threadId") != thread_id or not isinstance(turn_id, str) or not turn_id:
                    raise CodexAdapterError("native turn receipt invalid", outcome_unknown=True, thread_id=thread_id)
                runtime.update(status="accepted", turnId=turn_id)
                response = self._update(project, action_id, "accepted", thread_id=thread_id, turn_id=turn_id)
                worker = threading.Thread(target=self._watch, args=(project, action_id, thread_id),
                                          daemon=True, name="hub-codex-action")
                self._workers.add(worker)
                worker.start()
                return response
            except Exception as exc:
                uncertain = not isinstance(exc, CodexAdapterError) or exc.outcome_unknown
                status = "outcome_unknown" if uncertain else "failed"
                known_id = getattr(exc, "thread_id", None) or thread_id
                if runtime:
                    runtime["status"] = status
                if adapter is not None:
                    try:
                        adapter.close()
                    except Exception:
                        pass
                if not uncertain:
                    self._runtimes.pop(known_id,None)
                return self._update(project, action_id, status, thread_id=known_id,
                                    error={"code": getattr(exc, 'code', None) or ("native_outcome_unknown" if uncertain else "native_start_failed"),
                                           "message": ({'codex_not_found': 'Codex не найден в окружении сервиса. Установите Codex или добавьте его в PATH.',
                                                        'codex_launch_failed': 'Сервис не смог запустить Codex app-server.'}.get(getattr(exc, 'code', None)) or
                                                       ("Native action requires reconciliation" if uncertain else "Native action failed")),
                                           "httpStatus": 409 if uncertain else 502})

    def start_research(self, project, research, action_id):
        """Start research only after an explicit UI submit; never accepts runtime overrides."""
        self._id(project, "project"); self._id(action_id, "action_id"); self._project(project)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", action_id):
            raise ChatActionError("invalid_request", 400, "Invalid action_id")
        if not isinstance(research, dict) or set(research)-{'objectId','template','prompt','revision','detailLevel','scope'}:
            raise ChatActionError("invalid_request", 400, "Research must be an object")
        object_id = research.get("objectId")
        self._id(object_id, "research objectId")
        template = research.get("template")
        if template not in {"explain", "decompose", "scenario", "relationship", "custom", "structure-map"}:
            raise ChatActionError("invalid_request", 400, "Unknown research template")
        prompt = research.get("prompt", "")
        if not isinstance(prompt, str) or len(prompt) > 6000:
            raise ChatActionError("invalid_request", 400, "Research prompt must be at most 6000 characters")
        revision = research.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ChatActionError("invalid_request", 400, "Research requires the selected knowledge revision")
        clean = {"objectId": object_id, "template": template, "prompt": prompt, "revision": revision}
        if "scope" in research: clean["scope"] = research["scope"]
        if 'detailLevel' in research:
            if research['detailLevel'] not in ('brief', 'standard', 'detailed'):
                raise ChatActionError('invalid_request', 400, 'Unknown description detail level')
            clean['detailLevel'] = research['detailLevel']
        task = "__research__:" + object_id
        return self.start(project, task, action_id, _research=clean)

    @staticmethod
    def _question(request, thread_id, turn_id):
        if not isinstance(request, dict) or request.get('method') != 'item/tool/requestUserInput':
            return None
        identity = request.get('id')
        if isinstance(identity, bool) or not isinstance(identity, (str,int)) or (isinstance(identity,str) and (not identity or len(identity)>200)):
            return None
        params = request.get('params', {})
        if params.get('threadId') != thread_id or params.get('turnId') != turn_id:
            return None
        questions = params.get('questions')
        if not isinstance(questions, list) or not 1 <= len(questions) <= 3:
            return None
        clean = []
        for value in questions:
            if (not isinstance(value, dict) or value.get('isSecret') or
                    any(not isinstance(value.get(key), str) or not value[key].strip() or len(value[key]) > limit
                        for key, limit in (('id', 200), ('header', 120), ('question', 4000)))):
                return None
            options = value.get('options') or []
            if not isinstance(options, list) or len(options) > 10 or any(not isinstance(option, dict) or
                not isinstance(option.get('label'), str) or len(option['label']) > 400 or
                not isinstance(option.get('description', ''), str) or len(option.get('description', '')) > 800 for option in options):
                return None
            clean.append(dict(id=value['id'], header=value['header'], question=value['question'],
                              options=[dict(label=o['label'], description=o.get('description','')) for o in options]))
        if len({q['id'] for q in clean}) != len(clean):
            return None
        result = dict(requestId=request['id'], threadId=thread_id, turnId=turn_id, questions=clean)
        return result if len(_json(result).encode('utf-8')) <= 12000 else None

    def answer(self, project, action_id, request_id, answers):
        """Explicit local user answers only; native approval requests remain unsupported."""
        self._project(project)
        self._id(action_id, 'action_id')
        with self._lock:
            row = self._existing(project, action_id)
            if row is None or row['project'] != project:
                raise ChatActionError('action_not_found', 404, 'Unknown project action')
            response = json.loads(row['response'])
            runtime = self._runtimes.get(row['thread_id'])
            question = response.get('attention')
            if (not runtime or runtime['actionId'] != action_id or row['status'] != 'needs_attention' or
                    not question or question['requestId'] != request_id):
                raise ChatActionError('question_unavailable', 409, 'Question is no longer owned/current; refresh its status')
            try:
                runtime['adapter'].respond_user_input(request_id, answers)
            except (CodexAdapterError, ValueError) as exc:
                if isinstance(exc, CodexAdapterError) and exc.outcome_unknown:
                    runtime['status'] = 'outcome_unknown'
                    return self._update(project, action_id, 'outcome_unknown', error=dict(
                        code='answer_outcome_unknown', message='Answer acknowledgement is unknown; do not resend', httpStatus=409))
                raise ChatActionError('invalid_answer', 400, 'Answer does not match the current native questions') from exc
            runtime['status'] = 'accepted'
            response = self._update(project, action_id, 'accepted')
            worker = threading.Thread(target=self._watch, args=(project, action_id, row['thread_id']),
                                      daemon=True, name='hub-codex-answer')
            self._workers.add(worker); worker.start()
            return response

    def _watch(self, project, action_id, thread_id):
        runtime = self._runtimes[thread_id]
        try:
            while not self._stop.is_set():
                result = runtime["adapter"].wait_turn(1)
                if self._stop.is_set():
                    return
                status = result.get("status")
                # Persist only activity categories. The bounded public summary
                # stays in memory; raw reasoning, commands and transcripts are
                # never copied into Hub receipts.
                activity = runtime.get('activity', 'working')
                for event in runtime['adapter'].events().get('events', []):
                    params = event.get('params') or {}
                    if params.get('threadId') not in (None, thread_id):
                        continue
                    if params.get('turnId') not in (None, runtime.get('turnId')):
                        continue
                    if runtime.get('agentSummaries', True) and event.get('method') == 'item/reasoning/summaryTextDelta':
                        delta = params.get('delta')
                        if isinstance(delta, str):
                            key = (params.get('itemId'), params.get('summaryIndex'))
                            previous = runtime.get('summary', '') if runtime.get('summaryKey') == key else ''
                            runtime.update(summaryKey=key, summary=(previous + delta)[-480:])
                            activity = 'thinking'
                    if event.get('method') == 'item/started':
                        kind = (params.get('item') or {}).get('type')
                        if kind in ('commandExecution', 'mcpToolCall', 'dynamicToolCall', 'fileChange', 'webSearch'):
                            activity = 'tools'
                        elif kind == 'agentMessage':
                            activity = 'responding'
                        else:
                            activity = 'working'
                if status == "running":
                    if runtime['status'] != 'running' or runtime.get('activity') != activity:
                        with self._lock:
                            runtime.update(status='running', activity=activity)
                            self._update(project, action_id, 'running', activity=activity)
                    continue
                error = None
                attention = None
                if status == "needs-attention":
                    status = "needs_attention"
                    error = {"code": "native_user_attention", "httpStatus": 409,
                             "message": "Native user input or approval is required; this experimental transport has no approval UI. Desktop visibility is unverified."}
                    attention = self._question(result.get('request'), thread_id, runtime.get('turnId'))
                    if attention:
                        error = None
                elif status not in ("completed", "failed", "interrupted"):
                    status = "outcome_unknown"
                    error = {"code": "native_outcome_unknown", "httpStatus": 409,
                             "message": "Native turn outcome requires reconciliation"}
                with self._lock:
                    runtime["status"] = status
                    runtime.pop('summary', None)
                    self._update(project, action_id, status, error=error, attention=attention, activity=status)
                    if status in ('failed','interrupted'):
                        self._runtimes.pop(thread_id,None)
                if status in ('failed','interrupted'):
                    runtime['adapter'].close()
                return
        except Exception:
            with self._lock:
                runtime["status"] = "outcome_unknown"
                self._update(project, action_id, "outcome_unknown",
                             error={"code": "native_outcome_unknown", "httpStatus": 409,
                                    "message": "Native turn outcome requires reconciliation"})
        finally:
            with self._lock:
                self._workers.discard(threading.current_thread())

    def recent(self, project, task):
        """Only this service's receipts, never scan Codex or native transcripts."""
        self._project(project)
        self._id(task, "task")
        with self.registry.connect() as connection:
            rows = connection.execute("SELECT response FROM codex_chat_actions WHERE project=? AND task=? ORDER BY created DESC,action_id DESC LIMIT 20",
                                      (project, task)).fetchall()
        return self._decorate_receipts(project, rows)

    def research_history(self, project, offset=0, limit=20):
        """Project research receipts only, active first, with bounded pagination."""
        self._project(project)
        try:
            offset, limit = max(0, int(offset)), min(20, max(1, int(limit)))
        except (ValueError, TypeError):
            raise ChatActionError('invalid_request', 400, 'Invalid history page') from None
        with self.registry.connect() as connection:
            # Preserve the research-only ordering before LIMIT; the generic task
            # index can otherwise trigger a full journal sort for the GLOB range.
            rows = connection.execute("SELECT response FROM codex_chat_actions INDEXED BY codex_research_history WHERE project=? AND task GLOB '__research__:*' ORDER BY CASE WHEN status IN ('requested','accepted','running','needs_attention') THEN 0 ELSE 1 END,created DESC,action_id DESC LIMIT ? OFFSET ?",
                                      (project, limit+1, offset)).fetchall()
        more = len(rows)>limit
        return dict(items=self._decorate_receipts(project, rows[:limit]), offset=offset,
                    more=more, next=offset+limit if more else None)

    def _decorate_receipts(self, project, rows):
        with self._lock:
            result=[]
            for row in rows:
                response=json.loads(row["response"])
                runtime=self._runtimes.get(response.get('threadId'))
                if runtime and runtime['actionId'] == response['actionId'] and runtime.get('summary'):
                    now = time.monotonic()
                    if now - runtime.get('summaryPublishedAt', 0) >= 5:
                        runtime.update(summaryPublishedAt=now, publicSummary=runtime['summary'])
                    response['progressSummary'] = runtime.get('publicSummary', '')
                response['resumeAllowed']=bool(self._enabled() and not self._stop.is_set() and runtime and
                    runtime['status']=='completed' and runtime['project']==project and runtime['task']==response.get('task') and
                    runtime['actionId']==response['actionId'] and response['status']=='completed')
                result.append(response)
            return result

    def close(self):
        self._stop.set()
        with self._lock:
            runtimes = list(self._runtimes.items())
            workers = list(self._workers)
            for thread_id, runtime in runtimes:
                if runtime["status"] in ("requested", "accepted", "running", "needs_attention"):
                    runtime["status"] = "outcome_unknown"
                    self._update(runtime["project"], runtime["actionId"], "outcome_unknown",
                                 error={"code": "runtime_closed", "httpStatus": 409,
                                        "message": "Owned runtime closed; native outcome requires reconciliation"})
        for _, runtime in runtimes:
            runtime["adapter"].close()
        for worker in workers:
            worker.join(timeout=2)
