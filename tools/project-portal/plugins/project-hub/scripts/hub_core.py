"""Local coordination shared by the plugin and portal. No model/network calls.

Legacy project tasks stay in their existing journal during the rolling upgrade.
This database owns sessions/work/claims only; it never rewrites that journal.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import time
import uuid


class HubError(ValueError):
    def __init__(self, code, message, **details):
        super().__init__(message)
        self.body = dict(error=code, message=message, **details)


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def bounded(rows, budget=6000):
    page, size = [], 0
    for row in rows:
        length = len(compact(row))
        if page and size + length > budget:
            break
        page.append(row)
        size += length
    return page


def home():
    return Path(os.environ.get("PROJECT_HUB_HOME", Path.home() / ".codex/project-hub"))


def canonical(path):
    return os.path.normcase(str(Path(path).resolve()))


def git_common(cwd):
    from version_control import common_directory
    value = common_directory(cwd)
    return canonical(value) if value else None


def workspace_root(cwd, project):
    if project.get('workspace_root'):
        return project['workspace_root']
    resolved = canonical(cwd)
    if resolved == project['root'] or resolved.startswith(project['root'] + os.sep):
        return project['root']
    from version_control import worktree_root
    value = worktree_root(cwd)
    return canonical(value) if value else canonical(cwd)


def clean_text(value, field, limit=1200, required=True):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise HubError("invalid_argument", f"{field}: expected text, maximum {limit} characters")
    return value.strip()


def hook_actor(raw):
    """Codex session_id is the root; agent_id identifies the actual executor."""
    event=dict(raw)
    agent=event.get('agent_id')
    # Compatibility with the diagnostic client used to verify real host payloads.
    if agent is None and isinstance(event.get('identity'),dict):
        agent=event['identity'].get('agent_id')
    if agent is not None:
        agent=clean_text(agent,'agent_id',150)
        if agent!=event.get('session_id'):
            event['origin_session_id']=event['session_id']
            event['session_id']=agent
        event['agent_id']=agent
    event.pop('identity',None)
    return event


def resource(value):
    """Files are project-relative; named resources are shared even across worktrees."""
    value = clean_text(value, "resource", 300).replace("\\", "/").rstrip("/")
    if value.startswith("resource:"):
        if len(value) <= 9:
            raise HubError("invalid_resource", "Named resource cannot be empty")
        return value.casefold()
    if ":" in value or value.startswith("/") or any(p in ("", ".", "..") for p in value.split("/")):
        raise HubError("invalid_resource", "Use a relative file/directory or resource:name")
    return value.casefold()


def overlaps(a, b):
    return a == b or (not a.startswith("resource:") and not b.startswith("resource:") and
                      (a.startswith(b + "/") or b.startswith(a + "/")))


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class Hub:
    def __init__(self, directory=None):
        self.home = Path(directory) if directory is not None else home()
        self.db = self.home / "coordination.sqlite3"

    def connect(self):
        self.home.mkdir(parents=True, exist_ok=True)
        factory = getattr(self,'connection_factory',None)
        if factory is not None and self.db.exists():
            return factory()
        connection = sqlite3.connect(self.db, timeout=5, isolation_level=None, factory=ClosingConnection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def setup(self):
        with self.connect() as c:
            version = getattr(self, 'new_schema_version', 1)
            if version not in (1, 2):
                raise HubError('schema_version', 'Unsupported coordination database; not modified')
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='meta'").fetchone():
                version = c.execute("SELECT version FROM meta").fetchone()[0]
                if version not in (1, 2):
                    raise HubError("schema_version", "Unsupported coordination database; not modified")
            c.execute("PRAGMA journal_mode=WAL")
            required = ' NOT NULL' if version == 1 else ''
            c.executescript(f"""
                CREATE TABLE IF NOT EXISTS meta (version INTEGER NOT NULL);
                INSERT INTO meta SELECT {version} WHERE NOT EXISTS (SELECT 1 FROM meta);
                CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, root TEXT UNIQUE{required}, git_common TEXT);
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id), workspace TEXT{required},
                    state TEXT NOT NULL, seen REAL NOT NULL, turn TEXT, checkpoint TEXT NOT NULL DEFAULT '',
                    task TEXT, last_cursor INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS work (
                    id TEXT PRIMARY KEY, project TEXT NOT NULL REFERENCES projects(id), session TEXT NOT NULL REFERENCES sessions(id),
                    task TEXT NOT NULL, title TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL,
                    created REAL NOT NULL, updated REAL NOT NULL, result TEXT NOT NULL DEFAULT '',
                    git_snapshot TEXT NOT NULL DEFAULT '',
                    checkpoint TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '[]');
                CREATE TABLE IF NOT EXISTS claims (
                    work TEXT NOT NULL REFERENCES work(id), name TEXT NOT NULL, mode TEXT NOT NULL,
                    PRIMARY KEY(work,name));
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, project TEXT NOT NULL,
                    session TEXT, kind TEXT NOT NULL, work TEXT, at REAL NOT NULL, body TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, hash TEXT NOT NULL, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS work_stages (work TEXT PRIMARY KEY REFERENCES work(id), stage TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS work_stage_links (
                    work TEXT NOT NULL REFERENCES work(id), stage TEXT NOT NULL, PRIMARY KEY(work,stage));
                CREATE TABLE IF NOT EXISTS session_agents (
                    session TEXT PRIMARY KEY REFERENCES sessions(id), parent TEXT NOT NULL,
                    agent_path TEXT, nickname TEXT, role TEXT);
                CREATE TABLE IF NOT EXISTS resource_attempts (
                    id TEXT PRIMARY KEY, project TEXT NOT NULL, session TEXT NOT NULL,
                    task TEXT NOT NULL, title TEXT NOT NULL, resources TEXT NOT NULL,
                    mode TEXT NOT NULL, stage TEXT, updated REAL NOT NULL, acquired TEXT);
                CREATE TABLE IF NOT EXISTS plan_outbox (id TEXT PRIMARY KEY, project TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS event_project ON events(project,seq);
                CREATE INDEX IF NOT EXISTS work_project ON work(project,status);
            """)
            columns = {row[1] for row in c.execute("PRAGMA table_info(work)")}
            if "git_snapshot" not in columns:
                c.execute("ALTER TABLE work ADD COLUMN git_snapshot TEXT NOT NULL DEFAULT ''")
            if 'phase' not in columns:
                c.execute("ALTER TABLE work ADD COLUMN phase TEXT NOT NULL DEFAULT 'legacy'")
            if 'waiting_kind' not in columns:
                c.execute('ALTER TABLE work ADD COLUMN waiting_kind TEXT')
            if c.execute("SELECT version FROM meta").fetchone()[0] not in (1, 2):
                raise HubError("schema_version", "Unsupported coordination database; not modified")

    @contextmanager
    def transaction(self):
        with self.connect() as c:
            try:
                c.execute("BEGIN IMMEDIATE")
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise

    def register(self, root, project=None):
        root = Path(root).resolve()
        seed = json.loads((root / "docs/project-portal/project.json").read_text(encoding="utf-8-sig"))
        project = clean_text(project or seed["id"], "project", 100)
        self.setup()
        common = git_common(root)
        with self.transaction() as c:
            old = c.execute("SELECT * FROM projects WHERE id=?", (project,)).fetchone()
            if old and old["root"] != canonical(root):
                raise HubError("project_exists", "Project already registered at another root", root=old["root"])
            c.execute("INSERT OR IGNORE INTO projects VALUES (?,?,?)", (project, canonical(root), common))
        return dict(project=project, root=str(root), database=str(self.db))

    def locate(self, cwd):
        if not self.db.exists():return None
        with self.connect() as c:
            projects=[dict(r) for r in c.execute('SELECT * FROM projects')]
        candidates=[dict(p,roots=[p['root']],present=True,codex_id=p['id']) for p in projects]
        match=resolve_project(candidates,cwd)
        return next(p for p in projects if p['id']==match[0]['id']) if match else None

    @staticmethod
    def session(c, session):
        row = c.execute("SELECT * FROM sessions WHERE id=?", (session,)).fetchone()
        if not row:
            raise HubError("session_missing", "Session is not registered; run hub_context first")
        return dict(row)

    @staticmethod
    def emit(c, project, session, kind, body, work=None):
        cursor = c.execute("INSERT INTO events(id,project,session,kind,work,at,body) VALUES (?,?,?,?,?,?,?)",
                           (str(uuid.uuid4()), project, session, kind, work, time.time(), compact(body)))
        return cursor.lastrowid

    def observe_edit(self, raw):
        """Best-effort evidence from a received hook, never a permission decision."""
        if raw.get('hook_event_name') not in ('PreToolUse', 'PostToolUse'):
            return
        if raw.get('tool_name') not in ('apply_patch', 'Edit', 'Write'):
            return
        # Do not create storage, bind identities, resolve Git, or wait on ownership.
        if not self.db.is_file():
            return
        event = hook_actor(raw)
        sid = event.get('session_id')
        cwd = event.get('cwd')
        if not isinstance(sid, str) or not sid or not isinstance(cwd, str) or not Path(cwd).is_absolute():
            return
        deadline = time.monotonic() + .25
        with sqlite3.connect(self.db.as_uri() + '?mode=rw', uri=True, timeout=.05,
                             factory=ClosingConnection) as c:
            c.row_factory = sqlite3.Row
            c.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            c.execute('BEGIN IMMEDIATE')
            s = c.execute('SELECT * FROM sessions WHERE id=?', (sid,)).fetchone()
            if not s or not c.execute("SELECT 1 FROM events WHERE session=? AND project=? AND kind IN ('McpConnect','McpBind') LIMIT 1",
                                     (sid, s['project'])).fetchone():
                return
            if not s['workspace']:
                return
            workspace = Path(s['workspace'])
            if not Path(cwd).resolve().is_relative_to(workspace):
                return
            root = c.execute('SELECT root FROM projects WHERE id=?', (s['project'],)).fetchone()
            if not root:
                return
            roots = [(workspace, '')]
            if canonical(workspace) != root[0]:
                # Alternate roots/worktrees need authoritative resource mapping.
                # Missing mapping is unknown, never evidence of missing work.
                return
            from hub_plugin import changed_paths
            paths = changed_paths(event, cwd, project_roots=roots)
            if not paths or len(paths) > 30:
                return
            paths = [resource(p) for p in paths]
            claims = [r[0] for r in c.execute("""SELECT cl.name FROM work w
                JOIN claims cl ON cl.work=w.id JOIN work_stages ws ON ws.work=w.id
                WHERE w.session=? AND w.project=? AND w.status='active' AND cl.mode='write'""",
                (sid, s['project']))]
            missing = [p for p in paths if not any(p == name or p.startswith(name + '/') for name in claims)]
            if missing and time.monotonic() <= deadline:
                self.emit(c, s['project'], sid, 'diagnostic.edit_without_write_work',
                          dict(tool=event['tool_name'], phase=event['hook_event_name'],
                               paths=missing, observation='edit_tool_received',
                               reason='no_matching_active_stage_write_work'))

    def lifecycle(self, event, request_id):
        """Sanitized hook input only. Idempotency lives in the same transaction."""
        project = self.locate(event["cwd"])
        if not project:
            return dict(registered=False)
        digest = hashlib.sha256(compact(event).encode()).hexdigest()
        workspace = workspace_root(event['cwd'], project)
        with self.transaction() as c:
            previous = c.execute("SELECT * FROM receipts WHERE id=?", (request_id,)).fetchone()
            if previous:
                if previous["hash"] != digest:
                    raise HubError("id_reused", "Request ID was reused with different data")
                return json.loads(previous["result"])
            sid = clean_text(event["session_id"], "session", 150)
            old = c.execute("SELECT project FROM sessions WHERE id=?", (sid,)).fetchone()
            if old and old[0] != project["id"]:
                raise HubError("session_project", "Session belongs to another project")
            kind = event["hook_event_name"]
            state = {"Stop": "idle", "SubagentStop": "idle", "Interrupt": "interrupted", "SessionEnd": "closed"}.get(kind, "active")
            c.execute("""INSERT INTO sessions(id,project,workspace,state,seen,turn) VALUES (?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET state=excluded.state,seen=excluded.seen,turn=excluded.turn,workspace=excluded.workspace""",
                      (sid, project["id"], workspace, state, time.time(), event.get("turn_id")))
            # No transcript, prompt, tool arguments or outputs are persisted.
            seq = self.emit(c, project["id"], sid, kind, {k: event[k] for k in ("source", "tool_name", "agent_id", "origin_session_id") if k in event})
            result = dict(registered=True, revision=seq)
            c.execute("INSERT INTO receipts VALUES (?,?,?)", (request_id, digest, compact(result)))
            return result

    def ensure_session(self, session, cwd):
        with self.connect() as c:
            old = c.execute("SELECT id FROM sessions WHERE id=?", (session,)).fetchone()
        if not old:
            return self.lifecycle(dict(session_id=session, cwd=str(cwd), hook_event_name="McpConnect"), str(uuid.uuid4()))
        return dict(registered=True)

    def create_task(self, session, title, scope, acceptance, type='task', priority=None, parentTask=None, weight=None):
        title = clean_text(title, 'title', 240)
        for key, values in (('scope', scope), ('acceptance', acceptance)):
            if not isinstance(values, list) or not 1 <= len(values) <= 8:
                raise HubError('invalid_argument', key + ': supply 1–8 short entries')
            for value in values:
                clean_text(value, key, 400)
        with self.connect() as c:
            s = self.session(c, session)
            root = c.execute('SELECT root FROM projects WHERE id=?', (s['project'],)).fetchone()[0]
        key = hashlib.sha256(compact([session, title, scope, acceptance, type, priority, parentTask, weight]).encode()).hexdigest()[:16]
        task = 'hub-' + key
        if type not in ('epic', 'task', 'bug'):
            raise HubError('invalid_argument', 'type must be epic, task or bug')
        if priority is not None and priority not in ('blocker', 'critical', 'major', 'minor', 'trivial'):
            raise HubError('invalid_argument', 'Invalid priority')
        event = dict(id='hub-task-' + key, taskId=task, kind='task.created', title=title,
                     patch=dict(title=title, status='active', scope=scope, acceptance=acceptance, stages=[],
                                createdBy=dict(session=session, project=s['project']),
                                type=type, priority=priority, parentTask=parentTask, weight=weight))
        if hasattr(self, 'store_factory'):
            store = self.store_factory(s['project'])
            state = getattr(store, 'memory_snapshot', store.snapshot)()
            if any(old.get('id') == event['id'] for old in state.get('allEvents', state.get('events', []))):
                existing = next((item for item in state['tasks'] if item['id'] == task), None)
                return dict(task=task, status=existing['status'] if existing else None, existing=True,
                            present=existing is not None)
            store.record(event)
            return dict(task=task, status='active')
        # Use the existing, locked writer during rolling upgrades. Never write its journal directly.
        process = subprocess.run([os.sys.executable, str(Path(root) / 'scripts/project_portal.py'), '--root', root, 'record'],
                                 input=compact(event), capture_output=True, text=True, encoding='utf-8', timeout=15,
                                 env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
        if process.returncode:
            raise HubError('task_write_failed', process.stderr.strip()[:200])
        return dict(task=task, status='active')

    def update_task(self, session, task, patch, expected):
        if not isinstance(task, str) or not isinstance(patch, dict) or not isinstance(expected, (int, str)):
            raise HubError('invalid_argument', 'task, patch and expected revision are required')
        allowed = {'title', 'summary', 'status', 'scope', 'deferred', 'acceptance', 'sources', 'type', 'priority', 'parentTask', 'links', 'weight', 'blocker'}
        if set(patch) - allowed:
            raise HubError('invalid_argument', 'Unsupported task fields')
        with self.connect() as c:
            project = self.session(c, session)['project']
        store = self.store_factory(project) if hasattr(self, 'store_factory') else None
        if store is None:
            raise HubError('task_write_failed', 'Task update requires server mode')
        snapshot = getattr(store, 'memory_snapshot', store.snapshot)
        state = snapshot()
        if not any(row['id'] == task for row in state['tasks']):
            raise HubError('task_missing', 'Choose an existing task')
        expected_revision = expected
        store.record(dict(id='hub-update-' + uuid.uuid4().hex, taskId=task, kind='task.updated',
                          title='Задача обновлена', patch=patch), expected_revision=expected_revision)
        return dict(task=task, status='updated', revision=snapshot()['revision'])

    def link_task(self, session, task, target, type, expected, project=None):
        if type not in ('blocks', 'blocked-by', 'related', 'duplicates', 'duplicated-by'):
            raise HubError('invalid_argument', 'Invalid task link type')
        with self.connect() as c:
            current_project = self.session(c, session)['project']
        store = self.store_factory(current_project) if hasattr(self, 'store_factory') else None
        if store is None:
            raise HubError('task_write_failed', 'Task link requires server mode')
        state = getattr(store, 'memory_snapshot', store.snapshot)()
        row = next((item for item in state['tasks'] if item['id'] == task), None)
        target_project = project or current_project
        target_store = self.store_factory(target_project)
        target_state = state if target_project == current_project else getattr(target_store, 'memory_snapshot', target_store.snapshot)()
        if not row or not any(item['id'] == target for item in target_state['tasks']):
            raise HubError('task_missing', 'Choose existing tasks')
        links = [link for link in row.get('links', []) if not (link.get('type') == type and link.get('target') == target)]
        link = {'type': type, 'target': target}
        if project: link['project'] = target_project
        links.append(link)
        return self.update_task(session, task, {'links': links}, expected)

    def _commit_single_stage(self, project, row, store):
        """Attach the one task-level checkpoint to a completed single stage."""
        if hasattr(store, 'registry'):
            return store.snapshot()
        if len(row.get('stages', [])) != 1:
            return store.snapshot()
        stage = row['stages'][0]
        if stage.get('status') != 'done' or stage.get('gitCommit'):
            return store.snapshot()
        with self.connect() as c:
            candidate = c.execute("SELECT * FROM work WHERE project=? AND task=? AND status='done' ORDER BY updated DESC LIMIT 1", (project, row['id'])).fetchone()
            claims = [r[0] for r in c.execute('SELECT name FROM claims WHERE work=? ORDER BY name', (candidate['id'],))] if candidate else []
            workspace = c.execute('SELECT workspace FROM sessions WHERE id=?', (candidate['session'],)).fetchone()['workspace'] if candidate else None
        if not candidate or not claims:
            return store.snapshot()
        from git_integration import commit_work, decode_snapshot
        captured = decode_snapshot(candidate['git_snapshot'])
        if not captured.get('available'):
            return store.snapshot()
        commit = commit_work(workspace, captured, row['id'], stage['id'], candidate['id'], row['title'])
        latest = store.snapshot()
        latest_row = next(item for item in latest['tasks'] if item['id'] == row['id'])
        latest_stage = next(item for item in latest_row['stages'] if item['id'] == stage['id'])
        if commit.get('sha') and not latest_stage.get('gitCommit'):
            store.record(dict(id='hub-stage-commit-' + uuid.uuid4().hex, taskId=row['id'], stageId=stage['id'],
                              kind='stage.updated', title='Commit этапа создан',
                              patch={'gitCommit': commit}), expected_revision=latest['revision'])
        return store.snapshot()

    def settings(self, session, patch=None, expected=None, reset=None):
        raise HubError('server_required', 'Project settings require the connected Project Hub server')

    def check(self, session, **args):
        raise HubError('server_required', 'Check publication requires the connected Project Hub server')

    def checkpoint(self, session, task, expected, stage=None, commits=None, reason=None):
        raise HubError('server_required', 'Checkpoint retry and reconciliation require the connected Project Hub server')

    def close_task(self, session, task, expected, mode='manual', reason=''):
        if mode not in ('auto', 'manual') or not isinstance(expected, (int, str)):
            raise HubError('invalid_argument', 'Use auto/manual mode and expected revision')
        with self.connect() as c:
            project = self.session(c, session)['project']
        store = self.store_factory(project) if hasattr(self, 'store_factory') else None
        if store is None:
            raise HubError('task_write_failed', 'Task close requires server mode')
        state = store.snapshot(); row = next((item for item in state['tasks'] if item['id'] == task), None)
        if expected != state['revision']:
            raise HubError('task_write_failed', 'Task changed; refresh before writing')
        if not row:
            raise HubError('task_missing', 'Choose an existing task')
        incomplete = row.get('completion', {}).get('incompleteChildren', [])
        if mode == 'auto' and incomplete:
            raise HubError('incomplete_children', 'Automatic close requires all child tasks to be complete')
        latest = self._commit_single_stage(project, row, store)
        if latest['revision'] != state['revision']:
            expected = latest['revision']
        patch = {'status': 'done', 'closedManually': mode == 'manual'}
        if incomplete: patch['closeWarning'] = incomplete
        if reason: patch['closeReason'] = str(reason)[:800]
        expected_revision = expected
        store.record(dict(id='hub-close-' + uuid.uuid4().hex, taskId=task, kind='task.updated',
                          title='Задача закрыта', patch=patch), expected_revision=expected_revision)
        return dict(task=task, status='done', warning=incomplete, revision=store.snapshot()['revision'])

    def tasks(self, project):
        """Read-only projection of the still-authoritative v1 task journal."""
        with self.connect() as c:
            root = c.execute("SELECT root FROM projects WHERE id=?", (project,)).fetchone()[0]
        data = Path(root) / "docs/project-portal"
        seed = json.loads((data / "project.json").read_text(encoding="utf-8-sig"))
        fields = ("id", "title", "status", "type", "priority", "parentTask", "weight")
        tasks = {t["id"]: {k: t.get(k) for k in fields} for t in seed["tasks"]}
        for task in tasks.values():
            task.setdefault("type", "task")
            task.setdefault("priority", None)
            task.setdefault("parentTask", None)
            task.setdefault("weight", None)
        journal = data / "events.jsonl"
        if journal.exists():
            for line in journal.read_text(encoding="utf-8").splitlines():
                e = json.loads(line)
                if e["kind"] == "task.created":
                    tasks[e["taskId"]] = dict(id=e["taskId"], **{k: e["patch"].get(k) for k in fields if k != "id"})
                    tasks[e["taskId"]].setdefault("type", "task")
                    tasks[e["taskId"]].setdefault("priority", None)
                    tasks[e["taskId"]].setdefault("parentTask", None)
                    tasks[e["taskId"]].setdefault("weight", None)
                elif e["kind"] == "task.updated":
                    tasks[e["taskId"]].update({k: v for k, v in e["patch"].items() if k in fields})
        return list(tasks.values())

    def migration_preview(self, session):
        """Return projected taxonomy without writing or reserving anything."""
        with self.connect() as c:
            project = self.session(c, session)["project"]
        rows = []
        for task in self.tasks(project):
            row = {
                "task": task["id"],
                "title": task.get("title", ""),
                "status": task.get("status"),
                "type": task.get("type") or "task",
                "priority": task.get("priority"),
                "parentTask": task.get("parentTask"),
                "weight": task.get("weight"),
            }
            row["needsReview"] = row["priority"] is None
            rows.append(row)
        return {
            "project": project,
            "revision": self.registry.store(project).snapshot()["revision"] if hasattr(self, "registry") else None,
            "tasks": rows,
            "needsReview": sum(row["needsReview"] for row in rows),
            "writes": 0,
            "message": "Preview only; no journal events were written.",
        }

    def begin(self, session, task, title, resources, mode="write", request_id=None, stage=None, stages=None, phase=None):
        from work_scope import PHASES, stages_for
        if stage is not None and stages is not None:
            raise HubError('invalid_stage', 'Use stage or stages, not both')
        selected = [stage] if stage is not None else stages if stages is not None else []
        if not isinstance(selected, list) or len(selected) > 30 or any(
                not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,119}', value) for value in selected):
            raise HubError('invalid_stage', 'Use up to 30 existing stable stage IDs')
        selected = sorted(set(selected))
        stage = selected[0] if selected else None
        explicit_phase = phase is not None
        phase = phase or ('implementation' if selected else 'planning')
        if phase not in PHASES:
            raise HubError('invalid_phase', 'Use planning/research/implementation/review/testing')
        title = clean_text(title, "title", 240)
        if mode not in ("read", "write"):
            raise HubError("invalid_mode", "mode must be read or write")
        if not isinstance(resources, list) or not 1 <= len(resources) <= 30:
            raise HubError("invalid_resources", "Declare 1–30 files, directories or resource:name entries")
        names = sorted(set(resource(r) for r in resources))
        if sum(map(len, names)) > 6000:
            raise HubError('scope_too_large', 'Split work into smaller precise scopes; maximum scope text is 6000 characters')
        with self.connect() as c:
            s = self.session(c, session)

        def existing(c):
            # An uncertain MCP response can be retried without reserving the same step twice.
            for old in c.execute("SELECT * FROM work WHERE project=? AND task=? AND title=? AND status IN ('active','waiting','done') ORDER BY updated DESC", (s['project'], task, title)):
                if sorted(stages_for(c, old['id'])) != selected or (old['phase'] != phase and
                        (explicit_phase or old['phase'] != 'legacy')):
                    continue
                old_claims = [(r[0], r[1]) for r in c.execute('SELECT name,mode FROM claims WHERE work=? ORDER BY name', (old['id'],))]
                if old_claims == [(n, mode) for n in names]:
                    if old['status'] == 'done':
                        return dict(work=old['id'], revision=old['revision'], status='done', result=old['result'],
                                    message='Matching work is already complete; inspect it instead of duplicating it')
                    if old['session'] == session:
                        response = dict(work=old['id'], revision=old['revision'], status=old['status'],
                                        stage=stage, stages=selected, phase=old['phase'])
                        conflicts = self.conflicts(c, s['project'], names, mode, own=old['id'])
                        if conflicts:
                            response.update(warning='resource_overlap', conflictCount=len(conflicts),
                                            conflicts=bounded(conflicts, 4000))
                        return response
            if request_id:
                old = c.execute("SELECT * FROM work WHERE id=?", (request_id,)).fetchone()
                if old:
                    claims = [r[0] for r in c.execute("SELECT name FROM claims WHERE work=? ORDER BY name", (request_id,))]
                    old_modes = {r[0] for r in c.execute('SELECT mode FROM claims WHERE work=?', (request_id,))}
                    if (old["session"] == session and old["task"] == task and old["title"] == title and claims == names
                            and old_modes == {mode} and sorted(stages_for(c, old['id'])) == selected and old['phase'] == phase):
                        return dict(work=old["id"], revision=old["revision"], status=old["status"],
                                    stage=stage, stages=selected, phase=old['phase'])
                    raise HubError("id_reused", "Work ID already used")
            return None

        def validate_target():
            target = next((t for t in self.tasks(s['project']) if t['id'] == task), None)
            if target is None:
                raise HubError("task_missing", "Choose an existing task from hub_context")
            if not selected and (phase != 'planning' or target.get('stages')):
                raise HubError('stage_required', 'Only initial planning of a task without stages may omit stages')
            if selected:
                from hub_memory import Memory
                for identity in selected:
                    Memory(self, session).stage(task, identity)

        # Lost acknowledgements must recover the original work without another
        # Git scan (which can itself time out), or recapturing a dirty boundary.
        with self.connect() as c:
            found = existing(c)
        if found is not None:
            validate_target()
            return found
        from git_integration import encode_snapshot
        from version_control import capture_work
        boundary_store = self.git_boundary_store(s['project']) if mode == 'write' and hasattr(self, 'git_boundary_store') else None
        git_snapshot = encode_snapshot(capture_work(s["workspace"], names, mode, boundary_store, s['project']))
        validate_target()
        with self.transaction() as c:
            # A concurrent retry may have registered while Git ran outside the
            # write transaction. Retain that first snapshot and reservation.
            found = existing(c)
            if found is not None:
                return found
            conflicts = self.conflicts(c, s["project"], names, mode)
            attempt = json.dumps([s['project'], session, task, title, names, mode, selected, phase], ensure_ascii=False)
            wid = request_id or uuid.uuid4().hex[:16]
            now = time.time()
            if conflicts:
                # Claims describe an observed overlap, not an exclusive lease.
                # Keep the warning durable while recording the new work and its
                # original Git boundary in the same transaction.
                c.execute('INSERT OR REPLACE INTO resource_attempts VALUES (?,?,?,?,?,?,?,?,?,?)',
                          (attempt, s['project'], session, task, title, json.dumps(names), mode, stage, now, wid))
                self.emit(c, s['project'], session, 'resource.overlap',
                          dict(task=task, title=title, resources=names, conflictCount=len(conflicts)), wid)
            seq = self.emit(c, s["project"], session, "work.started",
                            dict(title=title, task=task, resources=names, stages=selected, phase=phase,
                                 conflictCount=len(conflicts)), wid)
            c.execute("INSERT INTO work(id,project,session,task,title,status,revision,created,updated,git_snapshot,phase) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (wid, s["project"], session, task, title, "active", seq, now, now, git_snapshot, phase))
            c.executemany("INSERT INTO claims VALUES (?,?,?)", [(wid, name, mode) for name in names])
            if stage:
                c.execute('INSERT INTO work_stages VALUES (?,?)',(wid,stage))
                c.executemany('INSERT INTO work_stage_links VALUES (?,?)', [(wid, identity) for identity in selected])
            c.execute('UPDATE resource_attempts SET acquired=?,updated=? WHERE id=?', (wid, now, attempt))
            c.execute("UPDATE sessions SET task=?,state='active',seen=? WHERE id=?", (task, now, session))
            for identity in selected:
                if not (mode == 'read' and phase in ('planning','research','review')):
                    self.queue_activation(c, wid, task, identity, s['project'], seq)
            response = dict(work=wid, revision=seq, status="active", stage=stage, stages=selected, phase=phase)
            if conflicts:
                response.update(warning='resource_overlap', conflictCount=len(conflicts),
                                conflicts=bounded(conflicts, 4000))
            return response

    @staticmethod
    def queue_activation(c, work, task, stage, project, signal):
        """Publish a trusted work boundary, never infer a stage from a session."""
        suffix = hashlib.sha256(stage.encode()).hexdigest()[:12]
        payload = dict(id='work-activation-'+work+'-'+str(signal)+'-'+suffix, activation=True,
                       workId=work, taskId=task, stageId=stage, signal=signal)
        c.execute('INSERT OR IGNORE INTO plan_outbox VALUES (?,?,?)',
                  (payload['id'], project, compact(payload)))

    @staticmethod
    def conflicts(c, project, names, mode="write", own=None):
        result = []
        for r in c.execute("""SELECT w.id,w.title,w.task,w.session,w.status,c.name,c.mode,
                              s.seen AS ownerSeen,ws.stage FROM claims c JOIN work w ON w.id=c.work
                              JOIN sessions s ON s.id=w.session LEFT JOIN work_stages ws ON ws.work=w.id
                              WHERE (w.project=? OR c.name LIKE 'resource:migration-root-%')
                              AND w.status IN ('active','waiting')""", (project,)):
            if r["id"] != own and (mode == "write" or r["mode"] == "write") and any(overlaps(n, r["name"]) for n in names):
                from work_scope import describe
                result.append(describe(c, dict(r)))
        return result

    def validate_report_evidence(self, evidence, project):
        for path in evidence:
            resource(path)

    def report(self, session, work, revision, result, checkpoint="", status="active", evidence=None, stage_status=None,
               stage=None, phase=None, waiting_kind=None):
        from work_scope import PHASES, WAITING_KINDS, stages_for
        if phase is not None and phase not in PHASES:
            raise HubError('invalid_phase', 'Unknown work phase')
        if waiting_kind is not None and (waiting_kind not in WAITING_KINDS or status != 'waiting'):
            raise HubError('invalid_waiting_kind', 'waiting_kind requires waiting and external_dependency/user_confirmation')
        result = clean_text(result, "result", 1600)
        checkpoint = clean_text(checkpoint, "checkpoint", 1200, False)
        if status not in ("active", "waiting", "done", "cancelled"):
            raise HubError("invalid_status", "Use active, waiting, done or cancelled")
        evidence = evidence or []
        if not isinstance(evidence, list) or len(evidence) > 12:
            raise HubError("invalid_evidence", "Use at most 12 relative evidence paths")
        evidence = [clean_text(path, "evidence", 300) for path in evidence]
        if sum(map(len, evidence)) > 1600:
            raise HubError('evidence_too_large', 'Use shorter evidence paths or fewer artifacts')
        receipt = 'report:' + hashlib.sha256(compact([session, work, revision]).encode()).hexdigest()
        if stage_status not in (None,'active','done','blocked','cancelled'):
            raise HubError('invalid_stage_status','Use active/done/blocked/cancelled')
        digest = hashlib.sha256(compact([result, checkpoint, status, evidence] + ([stage_status] if stage_status else [])).encode()).hexdigest()
        if stage is not None or phase is not None or waiting_kind is not None:
            digest = hashlib.sha256(compact([digest, stage, phase, waiting_kind]).encode()).hexdigest()
        completed_snapshot = None
        if status == 'done' and hasattr(self, 'freeze_git_boundary'):
            # Capture outside the coordination write transaction. Retries retain
            # the first acknowledged boundary; ownership is checked before reads.
            with self.connect() as c:
                acknowledged = c.execute('SELECT id FROM receipts WHERE id=?', (receipt,)).fetchone()
                pending = c.execute('SELECT * FROM work WHERE id=?', (work,)).fetchone()
            if (not acknowledged and pending and pending['session'] == session
                    and pending['revision'] == revision and pending['status'] not in ('done', 'cancelled')):
                completed_snapshot = self.freeze_git_boundary(dict(pending))
        with self.transaction() as c:
            old = c.execute('SELECT * FROM receipts WHERE id=?', (receipt,)).fetchone()
            if old:
                if old['hash'] != digest:
                    raise HubError('revision_conflict', 'This revision was already updated with different content')
                return json.loads(old['result'])
            w = c.execute("SELECT * FROM work WHERE id=?", (work,)).fetchone()
            if not w or w["session"] != session:
                raise HubError("not_owner", "Only the owning session may update this work")
            if w["revision"] != revision:
                raise HubError("revision_conflict", "Read the current work revision before updating", revision=w["revision"])
            if w["status"] in ("done", "cancelled"):
                raise HubError("work_closed", "Work is already closed")
            if completed_snapshot is not None:
                c.execute('UPDATE work SET git_snapshot=? WHERE id=?', (completed_snapshot, work))
            self.validate_report_evidence(evidence, w['project'])
            link = c.execute('SELECT stage FROM work_stages WHERE work=?',(work,)).fetchone()
            linked_stages = stages_for(c, work)
            service_read = ((phase or w['phase']) in ('planning','research','review') and
                            not c.execute("SELECT 1 FROM claims WHERE work=? AND mode='write'", (work,)).fetchone())
            if service_read and stage_status is not None:
                raise HubError('service_read_only', 'Service read work may publish its result, not change plan status')
            if stage is not None and stage not in linked_stages:
                raise HubError('stage_missing', 'Selected stage does not belong to this work')
            if stage_status and len(linked_stages) > 1 and stage is None:
                raise HubError('stage_ambiguous', 'Select one linked stage for stage_status')
            selected_stage = stage or (link[0] if link else None)
            if stage_status and not link:
                raise HubError('stage_missing','This legacy work has no stage; update the plan explicitly')
            if stage_status == 'done' and status != 'done':
                raise HubError('stage_incomplete','Complete this work before completing its stage')
            open_work = []
            if stage_status == 'done':
                open_work = [dict(row) for row in c.execute("""SELECT w.id,w.title,w.session,w.status FROM work w
                    WHERE w.project=? AND w.task=? AND w.id<>? AND w.status IN ('active','waiting')
                    AND (EXISTS(SELECT 1 FROM work_stages s WHERE s.work=w.id AND s.stage=?) OR
                         EXISTS(SELECT 1 FROM work_stage_links s WHERE s.work=w.id AND s.stage=?))
                    ORDER BY w.created,w.id""", (w['project'],w['task'],work,selected_stage,selected_stage))]
            effective_stage_status = None if open_work else stage_status
            git_commit = None
            if status == 'done' and effective_stage_status == 'done' and not hasattr(self, 'registry'):
                from git_integration import commit_work, decode_snapshot
                session_row = c.execute('SELECT workspace FROM sessions WHERE id=?', (w['session'],)).fetchone()
                captured = decode_snapshot(w['git_snapshot'])
                if captured.get('available'):
                    git_commit = commit_work(session_row['workspace'], captured, w['task'], selected_stage, work, w['title'])
            deferred = (dict(openWorkCount=len(open_work), openWork=open_work[:12],
                             message='Work result saved; stage remains open while other work is active or waiting')
                        if open_work else None)
            event_body = dict(result=result, checkpoint=checkpoint, evidence=evidence,
                              phase=phase or w['phase'], waitingKind=waiting_kind)
            if deferred:
                event_body['stageCompletionDeferred'] = deferred
            seq = self.emit(c, w["project"], session, "work." + status, event_body, work)
            c.execute("UPDATE work SET status=?,revision=?,updated=?,result=?,checkpoint=?,evidence=? WHERE id=?",
                      (status, seq, time.time(), result, checkpoint, compact(evidence), work))
            c.execute('UPDATE work SET phase=?,waiting_kind=? WHERE id=?', (phase or w['phase'], waiting_kind, work))
            c.execute("UPDATE sessions SET checkpoint=?,seen=? WHERE id=?", (checkpoint, time.time(), session))
            if status == 'active':
                c.execute("UPDATE sessions SET state='active' WHERE id=?", (session,))
                for identity in linked_stages:
                    write_claim = c.execute("SELECT 1 FROM claims WHERE work=? AND mode='write'", (work,)).fetchone()
                    if write_claim or (phase or w['phase']) not in ('planning','research','review'):
                        self.queue_activation(c, work, w['task'], identity, w['project'], seq)
            for linked_stage in linked_stages:
                suffix = hashlib.sha256(linked_stage.encode()).hexdigest()[:12]
                detail = result + ('\nNext: '+checkpoint if checkpoint else '')
                if deferred:
                    detail += '\nStage completion deferred; open work: ' + ', '.join(row['id'] for row in open_work[:12])
                payload=dict(id='work-report-'+work+'-'+str(seq)+'-'+suffix,workId=work,taskId=w['task'],stageId=linked_stage,kind='work.completed' if status=='done' else 'note',title=w['title'],detail=detail,evidence=[dict(path=p,label=p) for p in evidence])
                c.execute('INSERT INTO plan_outbox VALUES (?,?,?)',(payload['id'],w['project'],compact(payload)))
                effective_for_link = effective_stage_status if linked_stage == selected_stage else None
                if effective_for_link or (status == 'done' and not service_read):
                    plan_patch = dict(appendDone=result) if status == 'done' else {}
                    if git_commit is not None and git_commit.get('sha'):
                        plan_patch['gitCommit'] = git_commit
                    if effective_for_link:
                        plan_patch['status']=effective_for_link
                    if effective_for_link == 'done':
                        plan_patch['remaining']=[]
                    payload=dict(id='stage-report-'+work+'-'+str(seq)+'-'+suffix,taskId=w['task'],stageId=linked_stage,kind='stage.updated',title=w['title'],patch=plan_patch)
                    c.execute('INSERT INTO plan_outbox VALUES (?,?,?)',(payload['id'],w['project'],compact(payload)))
            # Claims remain as history. Closed work is excluded by the transactionally consistent query.
            ack = dict(work=work, revision=seq, status=status)
            if deferred:
                ack['stageCompletionDeferred'] = deferred
            c.execute('INSERT INTO receipts VALUES (?,?,?)', (receipt, digest, compact(ack)))
            return ack

    def guard(self, session, paths):
        """Legacy advisory inspection. Hub never makes an edit permission decision."""
        with self.connect() as c:
            s = self.session(c, session)
            names = [resource(p) for p in paths]
            owned = [r[0] for r in c.execute("""SELECT c.name FROM claims c JOIN work w ON w.id=c.work
                       WHERE w.session=? AND w.project=? AND w.status='active' AND c.mode='write'""", (session,s['project']))]
            missing = [p for p in names if not any(p == n or p.startswith(n + "/") for n in owned)]
            if missing:
                return dict(allowed=True, warning='unregistered_scope',
                            reason='Register actual work scope for bookkeeping; native permissions remain independent', paths=missing)
            return dict(allowed=True)

    def incremental_notice(self, session, limit=8):
        """Legacy explicit event reader; no hook or chat delivery is implied."""
        with self.transaction() as c:
            s = self.session(c, session)
            rows = c.execute("""SELECT seq,session,kind,work,body FROM events WHERE project=? AND seq>?
                                AND kind LIKE 'work.%' AND session<>? ORDER BY seq LIMIT ?""",
                             (s['project'], s['last_cursor'], session, limit + 1)).fetchall()
            page = [dict(r) for r in rows[:limit]]
            for row in page:
                row['body'] = json.loads(row['body'])
            page = bounded(page)
            latest = c.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE project=?', (s['project'],)).fetchone()[0]
            cursor = page[-1]['seq'] if len(rows) > len(page) else latest
            c.execute('UPDATE sessions SET last_cursor=? WHERE id=?', (cursor, session))
        return dict(changes=page, cursor=cursor, more=len(rows) > len(page)) if page else None

    def context(self, session, after=None, limit=12):
        from work_scope import describe
        limit = max(1, min(int(limit), 30))
        with self.connect() as c:
            s = self.session(c, session)
            latest = c.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE project=?", (s["project"],)).fetchone()[0]
            if after is not None:
                if not isinstance(after, int) or after < 0 or after > latest:
                    raise HubError("invalid_cursor", "Read a fresh context without after")
                rows = c.execute("SELECT seq,session,kind,work,body FROM events WHERE project=? AND seq>? ORDER BY seq LIMIT ?",
                                 (s["project"], after, limit + 1)).fetchall()
                page = [dict(r) for r in rows[:limit]]
                for row in page:
                    row["body"] = json.loads(row["body"])
                page = bounded(page)
                return dict(changes=page, cursor=page[-1]["seq"] if page else latest, more=len(rows) > len(page))
            own = [dict(r) for r in c.execute("SELECT id,title,task,status,revision,result,checkpoint FROM work WHERE session=? ORDER BY updated DESC LIMIT ?",
                                               (session, limit + 1))]
            for item in own:
                link=c.execute('SELECT stage FROM work_stages WHERE work=?',(item['id'],)).fetchone()
                describe(c, item)
                item['resources']=[dict(r) for r in c.execute('SELECT name,mode FROM claims WHERE work=? ORDER BY name LIMIT 20',(item['id'],))]
            others = [dict(r) for r in c.execute("SELECT id,title,task,session,status,revision FROM work WHERE project=? AND session<>? AND status IN ('active','waiting') ORDER BY created LIMIT ?",
                                                  (s["project"], session, limit + 1))]
            for item in others:
                describe(c, item)
        own_page, other_page = bounded(own[:limit], 3200), bounded(others[:limit], 2400)
        return dict(project=s["project"], session=session, cursor=latest, checkpoint=s["checkpoint"],
                    own=own_page, active=other_page, more=len(own) > len(own_page) or len(others) > len(other_page),
                    tasks=bounded([dict(id=t['id'],title=t['title'],status=t['status'])
                        for t in self.tasks(s['project']) if t['status']=='active'][:limit],1600),
                    planHint='Read hub_plan(task) for the full plan; hub_memory for recorded results',
                    coverage="Connected sessions only; legacy chats are not guarded")

    def agent_context(self, session, limit=12):
        """Bounded team handoff for models. Relationships never confer ownership."""
        with self.connect() as c:
            current=self.session(c,session)
            relation=c.execute('SELECT * FROM session_agents WHERE session=?',(session,)).fetchone()
            parent=relation['parent'] if relation else None
            members=[dict(r) for r in c.execute('''SELECT s.id,s.state,s.seen,a.parent AS parentSession,
                    a.agent_path AS agentPath,a.nickname AS agentNickname
                FROM sessions s LEFT JOIN session_agents a ON a.session=s.id
                WHERE s.project=? AND (s.id=? OR s.id=? OR a.parent=? OR a.parent=?)
                ORDER BY CASE WHEN s.id=? THEN 0 WHEN s.id=? THEN 1 ELSE 2 END,s.seen DESC,s.id
                LIMIT ?''',(current['project'],session,parent,session,parent,session,parent,limit+1))]
            ids=[r['id'] for r in members[:limit]]
            works=[]
            if ids:
                marks=','.join('?' for _ in ids)
                works=[dict(r) for r in c.execute(f'''SELECT w.id,w.session,w.task,ws.stage,w.title,w.status,
                        w.revision,w.result,w.checkpoint FROM work w LEFT JOIN work_stages ws ON ws.work=w.id
                    WHERE w.project=? AND w.session IN ({marks})
                    ORDER BY CASE WHEN w.status IN ('active','waiting') THEN 0 ELSE 1 END,w.updated DESC LIMIT ?''',
                    [current['project'],*ids,limit+1])]
            from work_scope import describe
            for item in works:
                describe(c, item)
            hooks=c.execute("SELECT MAX(at) FROM events WHERE session=? AND kind='PreToolUse'",(session,)).fetchone()[0]
        page=bounded(works[:limit],4000)
        return dict(actor=dict(session=session,parentSession=parent,agentPath=relation['agent_path'] if relation else None,
                    hookObservedAt=hooks),members=members[:limit],work=page,
                    more=len(members)>limit or len(works)>len(page),
                    next='Use hub_context(work=id) for resources/evidence, hub_memory for reusable results. Only the owner may report or release work.')

    def lookup(self, session, work=None, query='', offset=0, limit=8):
        limit = max(1, min(int(limit), 20))
        if not isinstance(offset, int) or offset < 0:
            raise HubError('invalid_offset', 'offset must be a nonnegative integer')
        with self.connect() as c:
            s = self.session(c, session)
            if work:
                rows = c.execute('SELECT * FROM work WHERE (project=? OR session=?) AND id=?', (s['project'],session, work)).fetchall()
            else:
                query = clean_text(query, 'query', 200, False)
                pattern = '%' + query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
                rows = c.execute("""SELECT w.* FROM work w WHERE project=? AND
                    (title LIKE ? ESCAPE '\\' OR task LIKE ? ESCAPE '\\' OR EXISTS
                    (SELECT 1 FROM claims WHERE work=w.id AND name LIKE ? ESCAPE '\\'))
                    ORDER BY updated DESC LIMIT ? OFFSET ?""", (s['project'], pattern, pattern, pattern, limit + 1, offset)).fetchall()
            values = []
            for row in rows[:limit]:
                item = dict(row)
                from work_scope import describe
                describe(c, item)
                item['evidence'] = json.loads(item['evidence'])
                item['resources'] = [dict(r) for r in c.execute('SELECT name,mode FROM claims WHERE work=?', (item['id'],))]
                values.append(item)
            page = bounded(values)
        return dict(work=page, more=len(rows) > len(page), next=offset + len(page))

    def overview(self, project, offset=0, limit=50):
        with self.connect() as c:
            total = c.execute("SELECT COUNT(*) FROM sessions WHERE project=?", (project,)).fetchone()[0]
            sessions = [dict(r) for r in c.execute("SELECT * FROM sessions WHERE project=? ORDER BY seen DESC LIMIT ? OFFSET ?", (project, limit, offset))]
            work = [dict(r) for r in c.execute("SELECT * FROM work WHERE project=? AND status IN ('active','waiting') ORDER BY created LIMIT ? OFFSET ?", (project, limit, offset))]
            for w in work:
                w["resources"] = [dict(r) for r in c.execute("SELECT name,mode FROM claims WHERE work=?", (w["id"],))]
                linked = c.execute('SELECT stage FROM work_stages WHERE work=?', (w['id'],)).fetchone()
                from work_scope import describe
                describe(c, w)
                owner = c.execute('SELECT seen FROM sessions WHERE id=?', (w['session'],)).fetchone()
                w['ownerSeen'] = owner[0] if owner else None
            attempts = []
            rows = c.execute('SELECT * FROM resource_attempts WHERE project=? ORDER BY updated DESC LIMIT ? OFFSET ?',
                             (project, limit + 1, offset)).fetchall()
            for row in rows[:limit]:
                item = dict(row)
                item.pop('id')
                item['resources'] = json.loads(item['resources'])
                item['blockers'] = self.conflicts(c, project, item['resources'], item['mode'], own=item['acquired'])
                for blocker in item['blockers']:
                    owner = c.execute('SELECT w.task,s.seen,ws.stage FROM work w JOIN sessions s ON s.id=w.session LEFT JOIN work_stages ws ON ws.work=w.id WHERE w.id=?', (blocker['id'],)).fetchone()
                    blocker.update(dict(owner))
                item['state'] = ('overlap' if item['acquired'] and item['blockers'] else
                                 'resumed' if item['acquired'] else
                                 'blocked' if item['blockers'] else 'retry_ready')
                attempts.append(item)
            latest = c.execute("SELECT COALESCE(MAX(seq),0) FROM events WHERE project=?", (project,)).fetchone()[0]
        with self.connect() as c:
            changes=[dict(session=r['session'],at=r['at'],**json.loads(r['body'])) for r in c.execute(
                "SELECT session,at,body FROM events WHERE project=? AND kind='session.project_changed' ORDER BY seq DESC LIMIT 20",(project,))]
        return dict(sessions=sessions, projectChanges=changes, work=work, attempts=attempts, attemptsMore=len(rows)>limit, sessionCount=total, revision=latest, offset=offset,
                    more=offset + len(sessions) < total or len(work) == limit, coverage="partial", serverTime=time.time())


def resolve_project(projects, cwd, assigned_project=None, *, common_for=None):
    common_for = common_for or git_common
    resolved=Path(cwd).resolve()
    matches=[]
    if assigned_project:
        assigned=[p for p in projects if p['codex_id']==assigned_project and p['present']]
        if not assigned:
            raise HubError('project_unregistered','Assigned Codex project is unavailable; refusing cwd fallback')
        projects=assigned
    for project in projects:
        if not project['present']:continue
        for root in project['roots']:
            root=Path(root).resolve()
            if resolved==root or root in resolved.parents:
                matches.append((len(root.parts),project,root))
    if matches:
        depth=max(row[0] for row in matches)
        matches=[row for row in matches if row[0]==depth]
        assigned=[row for row in matches if row[1]['codex_id']==assigned_project]
        if assigned:matches=assigned
        # A folder may also be attached to another project for migration.
        # Its primary owner wins over those secondary attachments.
        primary=[row for row in matches if row[2]==Path(row[1]['roots'][0]).resolve()]
        if primary:matches=primary
    else:
        # A real Git worktree may live outside every saved project root.
        common=common_for(resolved)
        if common:
            for project in projects:
                if not project['present']:continue
                for root in project['roots']:
                    root_common=project.get('git_common') if len(project['roots'])==1 and 'git_common' in project else common_for(root) if (Path(root)/'.git').exists() else None
                    if root_common==common:
                        matches.append((0,project,Path(root).resolve()))
            primary=[row for row in matches if row[2]==Path(row[1]['roots'][0]).resolve()]
            if primary:matches=primary
    if not matches:
        if not assigned_project:return None
        project=projects[0]
        matches=[(0,project,Path(project['roots'][0]).resolve())]
    if len({row[1]['id'] for row in matches})!=1:
        raise HubError('project_ambiguous','Workspace matches multiple projects; resolve the saved roots')
    _,project,matched_root=matches[0]
    return project, matched_root
