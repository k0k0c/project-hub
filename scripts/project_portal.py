"""Local project hub: durable events, read-only HTTP/SSE, agent CLI. Standard library only."""
from __future__ import annotations

import argparse
import copy
import hashlib
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, quote, unquote, urlparse
import uuid
sys.dont_write_bytecode = True
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
from task_progress import project_progress
from request_metrics import data_path, measure, measured_lock, runtime_version, timed, track_handler
from storage_operations import read_handler

ROOT = Path(__file__).resolve().parents[1]


def require_external_data(path, installation_root=ROOT):
    """Mutable Hub state may not overlap the program/source tree."""
    path, installation = Path(path).resolve(), Path(installation_root).resolve()
    if path.is_relative_to(installation) or installation.is_relative_to(path):
        raise ValueError('Hub data must be outside the program/source directory')
    return path


PLUGIN_SCRIPTS = ROOT / 'tools/project-portal/plugins/project-hub/scripts'
if PLUGIN_SCRIPTS.is_dir() and str(PLUGIN_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SCRIPTS))
try:
    from project_settings import SettingsError
except ImportError:
    class SettingsError(ValueError):
        pass
try:
    from git_integration import (GitIntegrationError, commit_pushed, git_history,
                                 push_repository, repository as git_repository,
                                 cached_read_repository, cached_read_projection)
except ImportError:
    class GitIntegrationError(ValueError):
        pass
    def push_repository(root, confirmed=False):
        raise GitIntegrationError('Git-интеграция плагина недоступна')
    def git_repository(root):
        return dict(available=False, root=str(Path(root).resolve()), reason='Git-интеграция плагина недоступна')
    def git_history(root, limit=100):
        return []
    def cached_read_repository(root):
        return git_repository(root)
    def cached_read_projection(root, limit=100):
        return git_repository(root), git_history(root, limit)
    def commit_pushed(root, sha, upstream=None):
        return None
STATUSES = {"planned", "active", "queued", "blocked", "done", "cancelled"}
TASK_TYPES = {"epic", "task", "bug"}
PRIORITIES = {"blocker", "critical", "major", "minor", "trivial"}
LINK_TYPES = {"blocks", "blocked-by", "related", "duplicates", "duplicated-by"}
TASK_CHANGE_KINDS = {"task.reopened", "task.status_changed", "task.type_changed",
                     "task.priority_changed", "task.parent_changed", "task.linked", "task.unlinked"}
HIDDEN_HISTORY_KINDS = {"work.started", "work.completed"}
SEMANTIC_TASK_FIELDS = {"status", "type", "priority", "parentTask", "links"}
GIT_SYNC_CACHE_TTL = 3.0
GIT_SYNC_CACHE = {}
GIT_SYNC_CACHE_LOCK = threading.Lock()
KINDS = {"task.created", "task.updated", "stage.created", "stage.updated", "work.started", "work.completed",
         "check.started", "check.passed", "check.failed", "check.interrupted", "check.unknown", "check.corrected", "finding", "decision", "note", "git.commit", "git.push",
         *TASK_CHANGE_KINDS}


def user_history_events(events):
    """Return the durable journal projection intended for user-facing history."""
    visible = []
    for event in events:
        if event.get("kind") in HIDDEN_HISTORY_KINDS:
            continue
        if event.get("kind") == "task.updated":
            patch = event.get("patch") or {}
            # A semantic event is generated for these state changes. Keep the
            # generic event only when it also carries unrelated task metadata,
            # such as a title or close warning.
            if patch and set(patch).issubset(SEMANTIC_TASK_FIELDS):
                continue
        visible.append(event)
    return visible


class SessionTitles:
    """Read only Codex's local name index; never read transcripts or rewrite its data."""
    def __init__(self, path=None):
        self.path = path or Path(os.environ.get('PROJECT_HUB_OBSERVATION_HOME',
            os.environ.get('CODEX_HOME', Path.home() / '.codex'))) / 'session_index.jsonl'
        self.signature = None
        self.names = {}
        self.lock = threading.Lock()

    def get(self, ids):
        with self.lock:
            try:
                stat = self.path.stat()
                signature = (stat.st_mtime_ns, stat.st_size)
                if signature != self.signature:
                    names = {}
                    with self.path.open(encoding='utf-8-sig') as source:
                        for line in source:
                            try:
                                entry = json.loads(line)
                                if isinstance(entry, dict) and isinstance(entry.get('id'), str) and isinstance(entry.get('thread_name'), str):
                                    names[entry['id']] = entry['thread_name']
                            except ValueError:
                                continue  # An append in progress must not hide all other names.
                    self.names, self.signature = names, signature
                return {sid: self.names.get(sid) for sid in ids}
            except (OSError, UnicodeError):
                return {sid: self.names.get(sid) for sid in ids}


SESSION_TITLES = SessionTitles()


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
            out.flush()
            os.fsync(out.fileno())
        deadline = time.monotonic() + .5
        while True:
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if os.name != 'nt' or time.monotonic() >= deadline:
                    raise
                time.sleep(.02)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_blocker(value):
    """Optional typed impediment; legacy blocked records remain readable."""
    if value is None:
        return
    if (not isinstance(value, dict) or set(value) != {'kind', 'reason', 'action'} or
            value.get('kind') not in ('technical', 'user_input', 'administrative') or
            any(not isinstance(value.get(key), str) or not value[key].strip() or len(value[key]) > 1200
                for key in ('reason', 'action'))):
        raise ValueError('Blocker requires kind (technical/user_input/administrative), reason and action')


def validate_estimate(estimate):
    if estimate is None:
        return
    if not isinstance(estimate, dict):
        raise ValueError('Estimate must be an object')
    for field in ('confidence', 'note', 'updatedBy', 'updatedAt'):
        if field in estimate and not isinstance(estimate[field], str):
            raise ValueError('Estimate ' + field + ' must be a string')
    for low, high, maximum in (('percentLow', 'percentHigh', 100), ('hoursLow', 'hoursHigh', math.inf)):
        if low in estimate or high in estimate:
            a, b = estimate.get(low), estimate.get(high)
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in (a, b)) or not 0 <= a <= b <= maximum:
                raise ValueError('Invalid estimate interval')


def validate_task(task):
    """Validate complete task state before allowing an event to become durable."""
    validate_blocker(task.get("blocker"))
    if not isinstance(task.get("id"), str) or not task["id"].strip() or not isinstance(task.get("title"), str) or not task["title"].strip():
        raise ValueError("Task ID/title must be non-empty strings")
    if task.get("status") not in STATUSES or not isinstance(task.get("stages"), list):
        raise ValueError("Invalid task status/stages")
    if 'summary' in task and not isinstance(task['summary'], str):
        raise ValueError('Task summary must be a string')
    task_type = task.get("type", "task")
    if task_type not in TASK_TYPES:
        raise ValueError("Invalid task type")
    priority = task.get("priority")
    if priority is not None and priority not in PRIORITIES:
        raise ValueError("Invalid task priority")
    parent = task.get("parentTask")
    if parent is not None and (not isinstance(parent, str) or not parent.strip() or parent == task.get("id")):
        raise ValueError("Invalid task parent")
    weight = task.get("weight")
    if weight is not None and (isinstance(weight, bool) or not isinstance(weight, (int, float)) or not math.isfinite(weight) or weight <= 0):
        raise ValueError("Invalid task weight")
    links = task.get("links", [])
    if not isinstance(links, list):
        raise ValueError("Task links must be a list")
    for link in links:
        if not isinstance(link, dict) or link.get("type") not in LINK_TYPES or not isinstance(link.get("target"), str) or not link["target"].strip():
            raise ValueError("Invalid task link")
    def strings(value):
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    for key in ("scope", "deferred", "acceptance"):
        if key in task and not strings(task[key]):
            raise ValueError(key + " must be a list of strings")
    stages = {}
    for stage in task["stages"]:
        if not isinstance(stage, dict) or not isinstance(stage.get("id"), str) or not stage["id"] or stage["id"] in stages:
            raise ValueError("Stage IDs must be unique non-empty strings")
        if not isinstance(stage.get("title"), str) or not stage["title"] or stage.get("status") not in STATUSES:
            raise ValueError("Invalid stage title/status")
        validate_blocker(stage.get("blocker"))
        validate_estimate(stage.get('estimate'))
        for key in ("done", "remaining", "dependsOn"):
            if key in stage and not strings(stage[key]):
                raise ValueError("Stage " + key + " must be a list of strings")
        if not stage['title'].strip() or ('summary' in stage and not isinstance(stage['summary'], str)):
            raise ValueError('Invalid stage text')
        evidence = stage.get('evidence', [])
        if not isinstance(evidence, list) or any(not isinstance(item, dict) or
                not isinstance(item.get('path'), str) or not item['path'].strip() for item in evidence):
            raise ValueError('Invalid stage evidence')
        stages[stage["id"]] = stage
    visited = set()
    def visit(stage_id, path):
        if stage_id not in stages or stage_id in path:
            raise ValueError("Stage dependency is missing or cyclic")
        if stage_id in visited:
            return
        for dependency in stages[stage_id].get("dependsOn", []):
            visit(dependency, path | {stage_id})
        visited.add(stage_id)
    for stage_id in stages:
        visit(stage_id, set())
    estimate = task.get("estimate")
    primary = task.get('primary')
    if primary is not None and (not isinstance(primary, dict) or
            type(primary.get('selected')) is not bool or
            not isinstance(primary.get('project'), str) or not primary['project'].strip() or
            set(primary) - {'selected', 'project', 'updatedAt'}):
        raise ValueError('Invalid primary selection')
    validate_estimate(estimate)
    creator = task.get('createdBy')
    if creator is not None and (not isinstance(creator, dict) or set(creator) != {'session', 'project'} or
            any(not isinstance(value, str) or not value.strip() or len(value) > 200 for value in creator.values())):
        raise ValueError('Invalid task creator provenance')


def validate_task_hierarchy(tasks):
    """Validate parent references and prevent cycles without changing old data."""
    by_id = {task["id"]: task for task in tasks}
    for task in tasks:
        parent = task.get("parentTask")
        if parent is None:
            continue
        if parent not in by_id:
            raise ValueError("Unknown task parent: " + parent)
        if by_id[parent].get("type", "task") != "epic" and task.get("type", "task") == "epic":
            raise ValueError("An epic cannot be a child of a non-epic task")
        seen = {task["id"]}
        current = parent
        while current is not None:
            if current in seen:
                raise ValueError("Task hierarchy is cyclic")
            if current not in by_id:
                raise ValueError("Unknown task parent: " + current)
            seen.add(current)
            current = by_id[current].get("parentTask")
    for task in tasks:
        for link in task.get("links", []):
            if link["target"] not in by_id and not isinstance(link.get('project'), str):
                raise ValueError("Unknown linked task: " + link["target"])


class Store:
    @timed('store_init')
    def __init__(self, root=ROOT, *, data_dir=None, installation_root=ROOT, coordination_home=None):
        if root is None and data_dir is None:
            raise ValueError('A project without a code workspace requires an explicit data directory')
        self.root = Path(root).resolve() if root is not None else None
        self.installation_root = ROOT if installation_root is ROOT else Path(installation_root).resolve()
        self.data = data_path(data_dir) if data_dir is not None else self.root / "docs/project-portal"
        require_external_data(self.data, self.installation_root)
        self.coordination_home = (require_external_data(coordination_home, self.installation_root)
                                  if coordination_home is not None else None)
        self.journal = self.data / "events.jsonl"
        self.lockfile = self.data / 'writer.lock' if data_dir is not None else self.root / ".local/project-portal/writer.lock"
        self.thread_lock = threading.RLock()

    def writer_probe(self):
        """An independent lock handle for this already selected data directory.

        The probe never resolves evidence or owns registry/source-load state.
        Use the exact writer lock path, rather than re-resolving unrelated roots
        for each non-blocking visibility probe.
        """
        probe = object.__new__(Store)
        for name in ('root', 'installation_root', 'data', 'coordination_home', 'journal', 'lockfile'):
            setattr(probe, name, getattr(self, name))
        probe.thread_lock = threading.RLock()
        return probe

    @staticmethod
    def lock_probe(lockfile):
        """Independent OS-lock handle with no project or evidence authority."""
        probe = object.__new__(Store)
        probe.lockfile = Path(lockfile)
        probe.thread_lock = threading.RLock()
        return probe

    def event_signature(self):
        """Cheap invalidation hint for SSE, never a write-concurrency revision."""
        registry = getattr(self, 'registry', None)
        paths = [self.data / 'project.json', self.journal, self.data / 'project-settings.json']
        if registry is not None:
            with registry.connect() as connection:
                projects = [row[0] for row in connection.execute('SELECT id FROM spaces')]
            paths.extend(registry.home / 'projects' / pid / name for pid in projects
                         for name in ('project.json', 'events.jsonl', 'project-settings.json'))
            paths.extend([registry.database, Path(str(registry.database) + '-wal'), registry.catalog.path])
        if self.coordination_home is not None:
            database = Path(self.coordination_home) / 'coordination.sqlite3'
            paths.extend([database, Path(str(database) + '-wal')])
        # Codex's database changes for unrelated host activity (including message
        # writes). Observe its optional session metadata on the periodic refresh,
        # rather than making every host write trigger all portal subscribers.
        paths.append(SESSION_TITLES.path)
        result = []
        for path in paths:
            try:
                stat = Path(path).stat()
                # SQLite readers can create/remove an empty WAL. Treat that as
                # absence: it contains no transaction and must not invalidate
                # the observer that just opened a read connection itself.
                result.append((str(path), None, None) if str(path).endswith('-wal') and not stat.st_size
                              else (str(path), stat.st_mtime_ns, stat.st_size))
            except OSError:
                # This is only a hint. Optional host metadata may be unreadable;
                # the periodic snapshot retains authoritative storage errors.
                result.append((str(path), None, None))
        return tuple(result)

    @contextmanager
    def locked(self, *, label='journal', poll_interval=.005, timeout=10):
        registry = getattr(self, 'registry', None)
        if registry is not None and not getattr(registry.transfer_local, 'depth', 0):
            from task_transfer import barrier
            with barrier(registry):
                with self.locked(label=label, poll_interval=poll_interval, timeout=timeout):
                    yield
            return
        # OS lock releases on process exit. All readers/writers see complete committed journals.
        with measured_lock(self.thread_lock, label):
            self.lockfile.parent.mkdir(parents=True, exist_ok=True)
            with open(self.lockfile, "a+b") as lock:
                if lock.tell() == 0:
                    lock.write(b"0")
                    lock.flush()
                deadline = time.monotonic() + timeout
                with measure(label + '_os_wait'):
                    while True:
                        try:
                            lock.seek(0)
                            if os.name == "nt":
                                import msvcrt
                                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                            else:
                                import fcntl
                                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except OSError as error:
                            if time.monotonic() >= deadline:
                                raise TimeoutError("Project journal is busy") from error
                            time.sleep(poll_interval)
                try:
                    yield
                finally:
                    lock.seek(0)
                    if os.name == "nt":
                        msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(lock, fcntl.LOCK_UN)

    @timed('journal_read')
    def _load(self):
        seed_bytes = (self.data / 'project.json').read_bytes()
        seed = json.loads(seed_bytes.decode('utf-8-sig'))
        if seed.get("schemaVersion") != 1:
            raise ValueError("Unsupported project schema")
        events = []
        try:
            journal_bytes = self.journal.read_bytes()
        except FileNotFoundError:
            journal_bytes = None
        if journal_bytes is not None:
            for line in journal_bytes.decode('utf-8').splitlines():
                event = json.loads(line)
                if event.get("seq") != len(events) + 1 or event.get("schemaVersion") != 1:
                    raise ValueError("Invalid journal sequence/version; history was not changed")
                events.append(event)
        self._loaded_signature = (hashlib.sha256(seed_bytes).digest(),
                                  hashlib.sha256(journal_bytes).digest() if journal_bytes is not None else None)
        self._loaded_journal_bytes = journal_bytes
        return seed, events

    def _sync_git_commit_events(self, *, discover=True):
        """Backfill durable Git events from already-recorded stage commits.

        Stage completion predates the explicit Git history event.  Keep the
        migration local, deterministic and idempotent so existing stage
        commit metadata becomes visible in task and project history without
        guessing ownership from file names.
        """
        discover = discover and self.root is not None
        if discover:
            cache_key = (str(self.root), str(self.data))
            checked = time.monotonic()
            with GIT_SYNC_CACHE_LOCK:
                if checked - GIT_SYNC_CACHE.get(cache_key, 0) < GIT_SYNC_CACHE_TTL:
                    discover = False
                else:
                    GIT_SYNC_CACHE[cache_key] = checked
        with self.locked():
            seed, events = self._load()
            known = {event.get("id") for event in events}
            additions = []
            tasks = {task["id"]: task for task in self.project(seed, events, hierarchy=False)}

            def append_commit(commit, source=None):
                task_id = commit.get("taskId")
                stage_id = commit.get("stageId")
                if not task_id or task_id not in tasks:
                    return
                if stage_id and not any(stage.get("id") == stage_id for stage in tasks[task_id].get("stages", [])):
                    return
                sha = commit.get("sha")
                if not sha:
                    return
                event_id = "git-commit-" + str(sha)
                if event_id in known:
                    return
                short_sha = commit.get("shortSha") or str(sha)[:10]
                files = commit.get("files") if isinstance(commit.get("files"), list) else []
                message = commit.get("message") or "Без сообщения"
                additions.append({
                    "id": event_id,
                    "taskId": task_id,
                    "stageId": stage_id,
                    "kind": "git.commit",
                    "title": "Git commit создан",
                    "detail": f"{message} · {short_sha} · {len(files)} файлов",
                    "workId": commit.get("workId") or (source or {}).get("workId"),
                    "git": commit,
                    "schemaVersion": 1,
                    "seq": len(events) + len(additions) + 1,
                    "at": commit.get("at") or (source or {}).get("at") or now(),
                })
                known.add(event_id)

            for source in events:
                if source.get("kind") not in ("stage.updated", "task.updated"):
                    continue
                commit = (source.get("patch") or {}).get("gitCommit")
                if not isinstance(commit, dict) or commit.get("status") != "committed" or not commit.get("sha"):
                    continue
                commit = {**commit, "taskId": source["taskId"], "stageId": source.get("stageId")}
                append_commit(commit, source)
            if discover:
                try:
                    for commit in git_history(self.root, 200):
                        append_commit(commit)
                except (GitIntegrationError, OSError, ValueError):
                    pass
            if additions:
                atomic_write(self.journal, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in [*events, *additions]))

    def _sync_task_change_events(self):
        """Materialize explicit history events for meaningful task changes.

        Older writers intentionally used one ``task.updated`` event for every
        task mutation.  Keep that event as the state source, but add a stable
        audit event for each meaningful taxonomy/lifecycle/link change.  The
        deterministic IDs make this migration safe to run on every read and
        also make it cover updates written by older plugin versions.
        """
        with self.locked():
            seed, events = self._load()
            known = {event.get("id") for event in events}
            additions = []
            type_labels = {"epic": "Epic", "task": "Task", "bug": "Bug"}
            priority_labels = {"blocker": "Blocker", "critical": "Critical", "major": "Major",
                               "minor": "Minor", "trivial": "Trivial", None: "Не задан"}
            status_labels = {"planned": "Предстоит", "active": "В работе", "queued": "В очереди",
                             "blocked": "Есть препятствие", "done": "Завершено", "cancelled": "Отменено"}
            link_labels = {"blocks": "блокирует", "blocked-by": "зависит от", "related": "связана с",
                           "duplicates": "дублирует", "duplicated-by": "дублируется задачей"}

            def task_name(tasks, task_id):
                if task_id is None:
                    return "Проект"
                task = next((item for item in tasks if item.get("id") == task_id), None)
                return task.get("title") if task else str(task_id)

            def value_label(field, value, tasks):
                if field == "status":
                    return status_labels.get(value, str(value))
                if field == "type":
                    return type_labels.get(value, str(value))
                if field == "priority":
                    return priority_labels.get(value, str(value))
                if field == "parentTask":
                    return task_name(tasks, value)
                return str(value)

            def append_change(source, kind, title, detail, change, suffix):
                event_id = "task-change-" + str(source["id"]) + "-" + suffix
                if event_id in known:
                    return
                additions.append({
                    "id": event_id,
                    "taskId": source["taskId"],
                    "kind": kind,
                    "title": title,
                    "detail": detail,
                    "change": {**change, "sourceEventId": source["id"]},
                    "schemaVersion": 1,
                    "seq": len(events) + len(additions) + 1,
                    "at": source.get("at") or now(),
                })
                known.add(event_id)

            # Keep only the small state slice needed to compare task changes.
            # Rebuilding the complete projection for every event would make
            # legacy migration quadratic for large project journals.
            tasks = {task["id"]: json.loads(json.dumps(task)) for task in seed.get("tasks", [])}
            for task in tasks.values():
                task.setdefault("type", "task")
                task.setdefault("priority", None)
                task.setdefault("parentTask", None)
                task.setdefault("links", [])

            for source in events:
                if source.get("kind") == "task.created":
                    task = {**json.loads(json.dumps(source.get("patch") or {})), "id": source.get("taskId")}
                    task.setdefault("type", "task")
                    task.setdefault("priority", None)
                    task.setdefault("parentTask", None)
                    task.setdefault("links", [])
                    tasks[task["id"]] = task
                    continue
                if source.get("kind") != "task.updated":
                    continue
                patch = source.get("patch") or {}
                task = tasks.get(source.get("taskId"))
                if not isinstance(patch, dict) or not task:
                    continue
                before = list(tasks.values())
                if not (set(patch) & SEMANTIC_TASK_FIELDS):
                    task.update(patch)
                    continue
                for field in ("status", "type", "priority", "parentTask"):
                    if field not in patch:
                        continue
                    old, new = task.get(field), patch[field]
                    if old == new:
                        continue
                    if field == "status":
                        # Closing already has its own explicit historical title;
                        # avoid presenting a duplicate status-change row for it.
                        if source.get("title") == "Задача закрыта" and new == "done":
                            continue
                        kind = "task.reopened" if old in {"done", "cancelled"} and new == "active" else "task.status_changed"
                        title = "Задача переоткрыта" if kind == "task.reopened" else "Статус задачи изменён"
                        detail = f"Статус: «{value_label(field, old, before)}» → «{value_label(field, new, before)}»"
                    else:
                        kind = {"type": "task.type_changed", "priority": "task.priority_changed",
                                "parentTask": "task.parent_changed"}[field]
                        title = {"type": "Тип задачи изменён", "priority": "Приоритет задачи изменён",
                                 "parentTask": "Родитель задачи изменён"}[field]
                        detail = f"{title.removesuffix(' изменён')}: «{value_label(field, old, before)}» → «{value_label(field, new, before)}»"
                    append_change(source, kind, title, detail,
                                  {"field": field, "from": old, "to": new}, field)

                if "links" in patch and isinstance(patch["links"], list):
                    old_links = {json.dumps(link, sort_keys=True, ensure_ascii=False): link
                                 for link in task.get("links", []) if isinstance(link, dict)}
                    new_links = {json.dumps(link, sort_keys=True, ensure_ascii=False): link
                                 for link in patch["links"] if isinstance(link, dict)}
                    for direction, changed, kind, title in (
                        ("added", new_links.keys() - old_links.keys(), "task.linked", "Связь задач добавлена"),
                        ("removed", old_links.keys() - new_links.keys(), "task.unlinked", "Связь задач удалена"),
                    ):
                        for link_key in sorted(changed):
                            link = (new_links if direction == "added" else old_links)[link_key]
                            target = task_name(before, link.get("target"))
                            relation = link_labels.get(link.get("type"), link.get("type", "связь"))
                            detail = f"{relation.capitalize()}: «{target}»"
                            digest = hashlib.sha256(link_key.encode("utf-8")).hexdigest()[:12]
                            append_change(source, kind, title, detail,
                                          {"field": "links", "direction": direction, "link": link},
                                          "links-" + direction + "-" + digest)
                task.update(patch)
                if patch.get("status") in {"planned", "active", "queued", "blocked"}:
                    for field in ("closedManually", "closeWarning", "closeReason"):
                        task.pop(field, None)
            if additions:
                atomic_write(self.journal, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in [*events, *additions]))

    @staticmethod
    @timed('projection')
    def project(seed, events, *, hierarchy=True):
        tasks = {task["id"]: json.loads(json.dumps(task)) for task in seed["tasks"]}
        for task in tasks.values():
            task.setdefault("type", "task")
            task.setdefault("priority", None)
            task.setdefault("parentTask", None)
            task.setdefault("links", [])
            task.setdefault("weight", None)
            task.setdefault("createdAt", seed.get("baselineAt"))
            task.setdefault("updatedAt", task.get("createdAt"))
        for event in events:
            kind, task_id, patch = event["kind"], event["taskId"], event.get("patch", {})
            if kind in {"git.commit", "git.push", *TASK_CHANGE_KINDS}:
                continue
            if kind == "task.created":
                tasks[task_id] = {**json.loads(json.dumps(patch)), "id": task_id}
                tasks[task_id].setdefault('stages', [])
                tasks[task_id].setdefault('type', 'task')
                tasks[task_id].setdefault('priority', None)
                tasks[task_id].setdefault('parentTask', None)
                tasks[task_id].setdefault('links', [])
                tasks[task_id].setdefault('weight', None)
                tasks[task_id]['createdAt'] = event['at']
            task = tasks[task_id]
            if kind in ('stage.deleted', 'stage.unlinked', 'stage.transferred', 'stage.restored', 'stage.exported', 'stage.imported'):
                from stage_operations import project_operation
                project_operation(tasks, event)
            if kind == "task.updated":
                task.update(patch)
                if patch.get("status") in {"planned", "active", "queued", "blocked"}:
                    for field in ("closedManually", "closeWarning", "closeReason"):
                        task.pop(field, None)
            if kind in ('task.updated', 'task.created'):
                for field in ('estimate', 'primary'):
                    if isinstance(patch.get(field), dict):
                        task[field] = {**patch[field], 'updatedAt': event['at']}
            if kind == "stage.updated":
                stage = next(s for s in task["stages"] if s["id"] == event["stageId"])
                stage.update({k:v for k,v in patch.items() if k != 'appendDone'})
                if isinstance(patch.get('estimate'), dict):
                    stage['estimate'] = {**patch['estimate'], 'updatedAt': event['at']}
                if patch.get('appendDone') and patch['appendDone'] not in stage.get('done',[]):
                    stage.setdefault('done',[]).append(patch['appendDone'])
            if kind == "stage.created":
                task['stages'].append({"done": [], "remaining": [], **patch, "id": event['stageId']})
            if kind == "work.started":
                task["currentWork"] = {"title": event["title"], "at": event["at"], "stageId": event.get("stageId"), "eventId": event["id"]}
            if kind == "work.completed" and (not event.get("workId") or event.get("workId") == task.get("currentWork", {}).get("eventId")):
                task.pop("currentWork", None)
            task["updatedAt"] = event["at"]
        result = list(tasks.values())
        for task in result:
            validate_task(task)
        if not hierarchy:
            return result
        validate_task_hierarchy(result)
        by_id = {task['id']: task for task in result}
        for task in result:
            task['children'] = []
        for task in result:
            if task.get('parentTask') in by_id:
                by_id[task['parentTask']]['children'].append(task['id'])
        def aggregate(task_id, trail=None):
            trail = set() if trail is None else trail
            if task_id in trail:
                raise ValueError('Task hierarchy is cyclic')
            task = by_id[task_id]
            own_total = len(task.get('stages', []))
            own_done = sum(stage.get('status') == 'done' for stage in task.get('stages', []))
            child_metrics = [aggregate(child, trail | {task_id}) for child in task['children']]
            total = own_total + sum(metric['total'] for metric in child_metrics)
            done = own_done + sum(metric['done'] for metric in child_metrics)
            task['progressAggregate'] = {'done': done, 'total': total, 'percent': round(done / total * 100, 1) if total else 0}
            return {'done': done, 'total': total}
        for task in result:
            aggregate(task['id'])
        def descendants(task_id):
            found = []
            for child_id in by_id[task_id]['children']:
                found.append(by_id[child_id])
                found.extend(descendants(child_id))
            return found
        priority_rank = {'trivial': 1, 'minor': 2, 'major': 3, 'critical': 4, 'blocker': 5}
        for task in result:
            children = descendants(task['id'])
            incomplete = [child['id'] for child in children if child.get('status') not in ('done', 'cancelled')]
            task['completion'] = {'autoEligible': bool(children) and not incomplete,
                                  'incompleteChildren': incomplete}
            unfinished_priorities = [child.get('priority') for child in children
                                     if child.get('status') not in ('done', 'cancelled')
                                     and child.get('priority') in priority_rank]
            task['maxDescendantPriority'] = max(unfinished_priorities,
                                                key=priority_rank.get) if unfinished_priorities else None
        return result

    def _decorate_git_commits(self, tasks, events=None):
        info = git_repository(self.root)
        if not info.get("available"):
            return
        def decorate(commit):
            if not isinstance(commit, dict) or not commit.get("sha"):
                return
            commit["pushed"] = commit_pushed(self.root, commit["sha"], info.get("upstream"))
            if info.get("githubUrl"):
                commit["githubUrl"] = info["githubUrl"] + "/commit/" + commit["sha"]
        for task in tasks:
            for stage in task.get("stages", []):
                decorate(stage.get("gitCommit"))
        for event in events or []:
            if event.get("kind") == "git.commit":
                decorate(event.get("git"))

    def snapshot(self):
        self._sync_git_commit_events()
        self._sync_task_change_events()
        with self.locked():
            seed, events = self._load()
            runs = {}
            for event in reversed(events):
                if event["kind"].startswith("check."):
                    runs.setdefault(event.get("runId", event["id"]), event)
            tasks = self.project(seed, events)
            self._decorate_git_commits(tasks, events)
            visible_events = user_history_events(events)
            project_id = getattr(self, 'project_id', seed.get('id'))
            try:
                from check_runs import project_runs
                checks = project_runs(events, project_id)
            except ImportError:
                checks = list(runs.values())
            database = Path(self.coordination_home) / 'coordination.sqlite3' if self.coordination_home is not None else None
            main_task = project_progress(tasks, events, project_id, database)
            return {"project": {k: v for k, v in seed.items() if k != "tasks"},
                    "tasks": tasks, "revision": len(events), "allEvents": events, "mainTask": main_task,
                    "events": list(reversed(visible_events[-24:])), "eventCount": len(visible_events),
                    "lastEventAt": events[-1]["at"] if events else None,
                    "checks": checks[:30], "checkCount": len(checks),
                    "serverTime": now(), "coordination": self.diagnostics()}

    def diagnostics(self, limit=200):
        """Small observation-only session projection; detailed work is archive-only."""
        plugin_scripts = self.installation_root / 'tools/project-portal/plugins/project-hub/scripts'
        if not plugin_scripts.is_dir():
            return {"available": False, "reason": "Plugin source is not present in this checkout"}
        try:
            if str(plugin_scripts) not in sys.path:
                sys.path.insert(0, str(plugin_scripts))
            from hub_core import Hub
            from codex_session_catalog import CATALOG, merge_sessions
            hub = Hub(self.coordination_home) if self.coordination_home is not None else Hub()
            if hasattr(self,'registry'):
                hub.connection_factory = self.registry.coordination_connect
            if not hub.db.exists():
                return {"available": False, "reason": "No Hub observations have been recorded"}
            project = {'id': self.project_id} if hasattr(self, 'registry') else hub.locate(self.root)
            if not project:
                return {"available": False, "reason": "Project is not registered with the coordination plugin"}
            limit = max(1, min(200, limit))
            with hub.connect() as c:
                query = 'SELECT id,project,workspace,state,seen,task FROM sessions'
                registered = [dict(r) for r in c.execute(query if hasattr(self, 'registry') else query + ' WHERE project=?',
                              () if hasattr(self, 'registry') else (project['id'],))]
                hook_sessions = {r[0] for r in c.execute("SELECT DISTINCT session FROM events WHERE project=? AND kind IN ('SessionStart','UserPromptSubmit','PreToolUse','Stop','Interrupt','SessionEnd')", (project['id'],))}
                active_counts = dict(c.execute("SELECT session,COUNT(*) FROM work WHERE project=? AND status IN ('active','waiting') GROUP BY session", (project['id'],)))
                revision = c.execute('SELECT COALESCE(MAX(seq),0) FROM events WHERE project=?', (project['id'],)).fetchone()[0]
                if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='session_agents'").fetchone():
                    relations = {r['session']: dict(r) for r in c.execute('SELECT a.* FROM session_agents a JOIN sessions s ON s.id=a.session WHERE s.project=?', (project['id'],))}
                else:
                    relations = {}
            catalog = dict(CATALOG.read_project(self.registry, project['id'], registered, active_counts)
                           if hasattr(self, 'registry') else CATALOG.read(self.root))
            registered = catalog.pop('registered', registered)
            names = SESSION_TITLES.get([s['id'] for s in registered] + [s['id'] for s in catalog['sessions']])
            merged = merge_sessions(catalog['sessions'], registered, names, hook_sessions, active_counts)
            fields = ('id', 'title', 'workspace', 'state', 'seen', 'task', 'integration', 'historical',
                      'kind', 'parentSession', 'agentPath', 'agentNickname', 'agentRole', 'updatedAt')
            sessions = []
            child_counts = {}
            for row in merged:
                item = {key: row[key] for key in fields if key in row}
                relation = relations.get(row['id'], {})
                for field, column in [('parentSession', 'parent'), ('agentPath', 'agent_path'), ('agentNickname', 'nickname'), ('agentRole', 'role')]:
                    if not item.get(field) and relation.get(column):
                        item[field] = relation[column]
                if item.get('parentSession'):
                    item['kind'] = 'subagent'
                    parent = item['parentSession']
                    child_counts[parent] = child_counts.get(parent, 0) + 1
                sessions.append(item)
            for item in sessions:
                item['childCount'] = child_counts.get(item['id'], 0)
            discovery = {k: v for k, v in catalog.items() if k != 'sessions'}
            titles_revision = hashlib.sha256(json.dumps([sessions, discovery], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
            return dict(available=True, sessions=sessions[:limit], sessionCount=len(sessions), more=len(sessions) > limit,
                        registeredCount=len(registered), hookSessionCount=sum(s['integration'] == 'hooks' for s in sessions),
                        discovery=discovery, revision=revision, titlesRevision=titles_revision)
        except Exception as error:
            return {"available": False, "reason": str(error)[:180]}

    def coordination(self, offset=0, limit=50):
        """Read additive coordination state; legacy task writers stay unchanged."""
        plugin_scripts = self.installation_root / 'tools/project-portal/plugins/project-hub/scripts'
        if not plugin_scripts.is_dir():
            return {"available": False, "reason": "Plugin source is not present in this checkout"}
        try:
            if str(plugin_scripts) not in sys.path:
                sys.path.insert(0, str(plugin_scripts))
            from hub_core import Hub
            from codex_session_catalog import CATALOG, merge_sessions
            hub = Hub(self.coordination_home) if self.coordination_home is not None else Hub()
            project = {'id':self.project_id} if hasattr(self,'registry') else hub.locate(self.root)
            if hasattr(self,'registry'):
                hub.new_schema_version = self.registry.schema_version
                hub.connection_factory = self.registry.coordination_connect
            if not project:
                return {"available": False, "reason": "Project is not registered with the coordination plugin"}
            with hub.connect() as connection:
                needs_upgrade = not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='resource_attempts'").fetchone()
            if needs_upgrade:
                hub.setup()
            overview = hub.overview(project['id'], offset, limit)
            with hub.connect() as c:
                registered = [dict(r) for r in c.execute('SELECT * FROM sessions')] if hasattr(self,'registry') else [dict(r) for r in c.execute('SELECT * FROM sessions WHERE project=?',(project['id'],))]
                hook_sessions = {r[0] for r in c.execute("SELECT DISTINCT session FROM events WHERE project=? AND kind IN ('SessionStart','UserPromptSubmit','PreToolUse','Stop','Interrupt','SessionEnd')", (project['id'],))}
                active_counts = dict(c.execute("SELECT session,COUNT(*) FROM work WHERE project=? AND status IN ('active','waiting') GROUP BY session", (project['id'],)))
            catalog = CATALOG.read_project(self.registry,project['id'],registered,active_counts) if hasattr(self,'registry') else CATALOG.read(self.root)
            registered = catalog.pop('registered',registered)
            names = SESSION_TITLES.get([s['id'] for s in registered] + [s['id'] for s in catalog['sessions']])
            merged = merge_sessions(catalog['sessions'], registered, names, hook_sessions, active_counts)
            overview['team'] = self.team_projection(hub, project['id'], merged)
            overview['sessions'] = merged[offset:offset + limit]
            overview['registeredCount'] = len(registered)
            overview['hookSessionCount'] = sum(s['integration']=='hooks' for s in merged)
            overview['sessionCount'] = len(merged)
            overview['more'] = offset + limit < len(merged) or len(overview['work']) == limit
            overview['discovery'] = {k: v for k, v in catalog.items() if k != 'sessions'}
            for work in overview['work']:
                work['sessionTitle'] = names.get(work['session'])
            for attempt in overview.get('attempts', []):
                attempt['sessionTitle'] = names.get(attempt['session'])
                for blocker in attempt['blockers']:
                    blocker['sessionTitle'] = names.get(blocker['session'])
            overview['more'] = overview['more'] or overview.get('attemptsMore', False)
            overview['titlesRevision'] = hashlib.sha256(json.dumps([merged, overview['discovery']], sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
            return {"available": True, **overview}
        except Exception as error:
            # A plugin/database fault must not hide the running legacy task journal.
            return {"available": False, "reason": str(error)[:180]}

    @staticmethod
    def team_projection(hub, project, sessions, limit=100):
        """Bounded project work and results; parent links never assign tasks."""
        limit = max(1, min(100, limit))
        known = {s['id']: s for s in sessions}
        members = {s['id']: dict(s) for s in sessions[:limit]}
        with hub.connect() as c:
            active = c.execute("SELECT w.*,ws.stage FROM work w LEFT JOIN work_stages ws ON ws.work=w.id WHERE w.project=? AND w.status IN ('active','waiting') ORDER BY w.updated DESC,w.id LIMIT ?", (project, limit + 1)).fetchall()
            recent = c.execute("SELECT w.*,ws.stage FROM work w LEFT JOIN work_stages ws ON ws.work=w.id WHERE w.project=? AND w.status NOT IN ('active','waiting') ORDER BY w.updated DESC,w.id LIMIT ?", (project, limit + 1)).fetchall()
            work = []
            for row in [*active[:limit], *recent[:limit]]:
                item = dict(row)
                from work_scope import describe
                describe(c, item)
                item['resources'] = [dict(r) for r in c.execute('SELECT name,mode FROM claims WHERE work=?', (item['id'],))]
                item['resourcesHeld'] = item['status'] in ('active', 'waiting')
                item['evidence'] = json.loads(item.get('evidence') or '[]')
                work.append(item)
                if item['session'] not in members:
                    members[item['session']] = dict(known.get(item['session'], {'id': item['session'], 'state': 'unknown', 'historical': True}))
            if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='session_agents'").fetchone():
                for member in members.values():
                    relation = c.execute('SELECT * FROM session_agents WHERE session=?', (member['id'],)).fetchone()
                    if relation:
                        for field, column in [('parentSession','parent'), ('agentPath','agent_path'), ('agentNickname','nickname'), ('agentRole','role')]:
                            if not member.get(field) and relation[column]:
                                member[field] = relation[column]
                        if member.get('parentSession'):
                            member['kind'] = 'subagent'
        return {'sessions': list(members.values()), 'work': work, 'sessionsMore': len(sessions) > limit,
                'activeMore': len(active) > limit, 'recentMore': len(recent) > limit, 'limit': limit}

    def history(self, task_id=None, before=None, limit=40, kind=None):
        self._sync_git_commit_events()
        self._sync_task_change_events()
        with self.locked():
            _, events = self._load()
        filtered = [e for e in reversed(user_history_events(events)) if (not task_id or e["taskId"] == task_id)
                    and (before is None or e["seq"] < before) and (not kind or e["kind"].startswith(kind))]
        page = filtered[:limit]
        return {"events": page, "next": page[-1]["seq"] if len(filtered) > limit else None}

    def git_overview(self, limit=100, *, snapshot=None):
        """Return a bounded, task-centric projection of the local repository."""
        repository, commits = cached_read_projection(self.root, limit)
        if not repository.get('available'):
            return {'repository': repository, 'summary': {}, 'tasks': [], 'commits': [], 'pushes': [],
                    'unassigned': {'localFiles': 0, 'ambiguousFiles': 0, 'commits': 0}}
        state = snapshot if snapshot is not None else self.snapshot()
        tasks = {task['id']: task for task in state['tasks']}
        for commit in commits:
            task = tasks.get(commit.get('taskId'))
            if task:
                commit['taskTitle'] = task.get('title')
                stage = next((item for item in task.get('stages', []) if item.get('id') == commit.get('stageId')), None)
                if stage:
                    commit['stageTitle'] = stage.get('title')
        claims = []
        if self.coordination_home is not None:
            import sqlite3
            database = Path(self.coordination_home) / 'coordination.sqlite3'
            if database.exists():
                with sqlite3.connect(database) as connection:
                    rows = connection.execute(
                        "SELECT w.task,c.name FROM claims c JOIN work w ON w.id=c.work "
                        "WHERE w.project=? AND w.status IN ('active','waiting')",
                        (getattr(self, 'project_id', state['project'].get('id')),),
                    ).fetchall()
                    claims = [(task_id, str(name).replace('\\', '/').strip('/'))
                              for task_id, name in rows
                              if not str(name).startswith(('resource:', '@roots/'))]
        local_by_task = {}
        ambiguous = 0
        unassigned = 0
        for path in repository.get('changedFiles', []):
            normalized = str(path).replace('\\', '/').lstrip('/')
            matches = sorted({task_id for task_id, claim in claims
                              if normalized == claim or normalized.startswith(claim + '/')})
            if len(matches) == 1 and matches[0] in tasks:
                local_by_task.setdefault(matches[0], set()).add(normalized)
            elif len(matches) > 1:
                ambiguous += 1
            else:
                unassigned += 1
        task_rows = {}
        for task_id, paths in local_by_task.items():
            task_rows[task_id] = {'taskId': task_id, 'title': tasks[task_id].get('title'),
                                  'status': tasks[task_id].get('status'), 'localFiles': len(paths),
                                  'commitCount': 0, 'commitFiles': 0, 'latestCommit': None,
                                  'association': 'local'}
        linked_commits = 0
        for commit in commits:
            task_id = commit.get('taskId')
            if task_id not in tasks:
                continue
            linked_commits += 1
            row = task_rows.setdefault(task_id, {'taskId': task_id, 'title': tasks[task_id].get('title'),
                                                 'status': tasks[task_id].get('status'), 'localFiles': 0,
                                                 'commitCount': 0, 'commitFiles': 0, 'latestCommit': None,
                                                 'association': 'committed'})
            row['commitCount'] += 1
            row['commitFiles'] += commit.get('fileCount', len(commit.get('files', [])))
            if row['latestCommit'] is None:
                row['latestCommit'] = commit
            if row['localFiles']:
                row['association'] = 'mixed'
        for row in task_rows.values():
            if row['commitCount'] and row['localFiles']:
                row['association'] = 'mixed'
        event_pushes = [event for event in state.get('allEvents', []) if event.get('kind') == 'git.push']
        return {
            'repository': repository,
            'summary': {
                'changedFiles': len(repository.get('changedFiles', [])),
                'affectedTasks': len(task_rows),
                'commits': len(commits),
                'linkedCommits': linked_commits,
                'ahead': repository.get('ahead'),
                'behind': repository.get('behind'),
            },
            'tasks': sorted(task_rows.values(), key=lambda row: (-(row['localFiles'] > 0), row['title'] or '')),
            'commits': commits,
            'pushes': list(reversed(event_pushes[-50:])),
            'unassigned': {'localFiles': unassigned, 'ambiguousFiles': ambiguous,
                           'commits': len(commits) - linked_commits},
        }

    def record(self, payload, expected_revision=None, *, hierarchy_tasks=None):
        self.write_receipt = None
        models = getattr(getattr(self, 'registry', None), 'read_models', None)
        head = None
        if models is not None:
            # A cold/restored head may acquire this project's journal lock to
            # replay it. Prepare it before taking that non-reentrant OS lock.
            if not getattr(self.registry.transfer_local, 'depth', 0):
                from task_transfer import barrier
                with barrier(self.registry):
                    return self.record(payload, expected_revision, hierarchy_tasks=hierarchy_tasks)
            head = models.head(self.project_id)
        with self.locked():
            raw_tasks = None
            if models is None:
                seed, events = self._load()
                event_count = len(events)
            else:
                # A verified SQL head already describes these journal bytes.
                # Read bytes for the append proof without parsing every older
                # event again; cold/restored inputs are validated by head().
                with measure('journal_read'):
                    seed_hash = models.file_digests.digest(self.data / 'project.json')
                    try:
                        from file_freshness import token
                        _,journal_proof = models.file_proofs(self.project_id)
                        with self.journal.open('rb') as journal_input:
                            input_token = token(journal_input)
                            proven = (input_token is not None and journal_proof is not None and
                                      tuple(journal_proof[0]) == input_token and journal_proof[1] == head['journal_hash'])
                            if proven:
                                prior = None
                                self._loaded_journal_size = input_token[2]
                                if input_token[2]:
                                    journal_input.seek(-1,os.SEEK_END)
                                self._loaded_journal_last = journal_input.read(1)
                            else:
                                prior = journal_input.read()
                                self._loaded_journal_size = len(prior)
                                self._loaded_journal_last = prior[-1:]
                            self._loaded_journal_token = input_token if input_token == token(journal_input) else None
                    except FileNotFoundError:
                        prior = None
                        self._loaded_journal_token = None
                        self._loaded_journal_size = 0
                        self._loaded_journal_last = b''
                        proven = False
                signature = (seed_hash,head['journal_hash'] if proven else
                             hashlib.sha256(prior).digest() if prior is not None else None)
                if signature != (head['seed_hash'], head['journal_hash']):
                    raise ValueError('Journal changed before append; retry the write')
                self._loaded_signature, self._loaded_journal_bytes = signature, prior
                seed, events, event_count = json.loads(head['project_body']), [], head['journal_seq']
                # The owner caller supplies the complete graph for hierarchy
                # validation. Origin projection needs only the affected task;
                # standalone writers still obtain all original task bodies.
                raw_tasks = models.origin_tasks(self.project_id, signature,
                                               task=payload.get('taskId') if hierarchy_tasks is not None else None)
                if raw_tasks is None:
                    raise ValueError('Prepared tasks changed before append; retry the write')
            allowed = {"id", "taskId", "stageId", "kind", "title", "detail", "evidence", "patch", "change", "workId", "runId", "git", "check"}
            if set(payload) - allowed:
                raise ValueError("Unknown event fields: " + ", ".join(sorted(set(payload) - allowed)))
            if payload.get("kind") not in KINDS:
                raise ValueError("Unknown event kind")
            for key in ("taskId", "title"):
                if not isinstance(payload.get(key), str) or not payload[key].strip():
                    raise ValueError(key + " is required")
            event_id = payload.get("id") or str(uuid.uuid4())
            existing = (models.origin_event(self.project_id, event_id) if models is not None else
                        next((event for event in events if event["id"] == event_id), None))
            body = {**payload, "id": event_id}
            if existing:
                original = {k: v for k, v in existing.items() if k not in {"at", "seq", "schemaVersion"}}
                if original != body:
                    raise ValueError("Event ID already used for different content")
                return existing
            if expected_revision is not None and expected_revision != event_count:
                raise ValueError('Plan revision changed; read the current plan and retry')
            projection_seed = dict(seed, tasks=raw_tasks) if raw_tasks is not None else seed
            projection_events = [] if raw_tasks is not None else events
            # Indexed rows are already validated for this exact journal head.
            # Do not clone every unchanged task to validate one incoming event.
            tasks = ({t['id']: t for t in raw_tasks} if raw_tasks is not None else
                     {t['id']: t for t in self.project(projection_seed, projection_events,
                                                     hierarchy=hierarchy_tasks is None)})
            kind, task_id = payload["kind"], payload["taskId"]
            patch = payload.get("patch", {})
            if not isinstance(patch, dict):
                raise ValueError("patch must be an object")
            if kind in TASK_CHANGE_KINDS and not isinstance(payload.get("change"), dict):
                raise ValueError("Task change event requires change metadata")
            if "status" in patch and patch["status"] not in STATUSES:
                raise ValueError("Invalid status")
            if kind == "task.created":
                if task_id in tasks or not patch.get("title") or not patch.get("status"):
                    raise ValueError("New task requires a unique ID, title and status")
                if set(patch) - {"title", "summary", "status", "stages", "estimate", "primary", "scope", "deferred", "acceptance", "sources", "type", "priority", "parentTask", "links", "weight", "closedManually", "closeWarning", "closeReason", "blocker", "createdBy"}:
                    raise ValueError("Unsupported task fields")
                stages = patch.get("stages", [])
                ids = [stage["id"] for stage in stages]
                if len(set(ids)) != len(ids) or any(stage.get("status") not in STATUSES for stage in stages):
                    raise ValueError("Invalid task stages")
            elif kind not in ("git.commit", "git.push"):
                if task_id not in tasks:
                    raise ValueError("Unknown task: " + task_id)
                if kind != 'stage.created' and payload.get("stageId") and not any(s["id"] == payload["stageId"] for s in tasks[task_id]["stages"]):
                    raise ValueError("Unknown stage")
            if kind == "git.push" and task_id != "__project__":
                raise ValueError("Git push events must use the project task marker")
            if kind in ("git.commit", "git.push") and not isinstance(payload.get("git"), dict):
                raise ValueError("Git event requires git metadata")
            if kind == "git.commit" and not payload.get("stageId"):
                raise ValueError("Git commit event requires a stage")
            if kind == "task.updated" and set(patch) - {"title", "summary", "status", "estimate", "primary", "scope", "deferred", "acceptance", "sources", "type", "priority", "parentTask", "links", "weight", "closedManually", "closeWarning", "closeReason", "gitCheckpoint", "gitCommit", "blocker"}:
                raise ValueError("Unsupported task patch")
            if 'primary' in patch and (not isinstance(patch['primary'], dict) or
                    set(patch['primary']) != {'selected', 'project'}):
                raise ValueError('Primary patch requires selected and project')
            if kind in ("stage.created", "stage.updated"):
                if not payload.get("stageId") or set(patch) - {"title", "status", "done", "remaining", "evidence", "dependsOn", "summary", "appendDone", "gitCommit", "gitCheckpoint", "blocker", "estimate"}:
                    raise ValueError("Invalid stage patch")
                if 'appendDone' in patch and (kind != 'stage.updated' or not isinstance(patch['appendDone'],str) or len(patch['appendDone'])>1600):
                    raise ValueError('Invalid completed result')
                if kind == 'stage.created' and (not patch.get('title') or patch.get('status') not in STATUSES or any(s['id'] == payload['stageId'] for s in tasks[task_id]['stages'])):
                    raise ValueError('New stage requires unique ID, title and status')
                for source in patch.get('evidence', []):
                    self.validate_evidence_ref(source['path'], source.get('sourceProject'))
            if patch and kind not in {"task.created", "task.updated", "stage.created", "stage.updated"}:
                raise ValueError("This event cannot change task state")
            for evidence in payload.get("evidence", []):
                self.validate_evidence_ref(evidence["path"], evidence.get('sourceProject'))
            if len(json.dumps(body)) > 64_000:
                raise ValueError("Event too large; link to a file instead")
            event = {**body, "schemaVersion": 1, "seq": event_count + 1, "at": now()}
            events.append(event)
            incremental = raw_tasks is not None and hierarchy_tasks is not None
            if incremental:
                # Ordinary events affect one task. Structural validity still
                # uses the complete current-owner graph before any append.
                selected = [tasks[task_id]] if task_id in tasks else []
                projected = self.project(dict(seed,tasks=selected), [event], hierarchy=False)
                # Owner-only parent/link decoration must not leak into the
                # origin index, or disappear during hierarchy validation.
                owner_ids = {task['id'] for task in hierarchy_tasks}
                owner_selected = [task for task in hierarchy_tasks if task['id'] == task_id]
                changed = {task['id']: task for task in
                           self.project(dict(seed,tasks=owner_selected),[event],hierarchy=False)}
                owner_tasks = [changed.get(task['id'],task) for task in hierarchy_tasks]
                owner_tasks.extend(task for task in changed.values() if task['id'] not in owner_ids)
                validate_task_hierarchy(owner_tasks)
            else:
                projected = self.project(projection_seed, [*projection_events,event] if raw_tasks is not None else events,
                                         hierarchy=hierarchy_tasks is None)
            if hierarchy_tasks is not None and not incremental:
                # Origin journals preserve provenance; structural validation
                # belongs to the current owner's complete task collection.
                self.project({'tasks': hierarchy_tasks}, [event])
            # Copy-on-write journal preserves the previous complete version after a failed write.
            if models is not None:
                from journal_append import append, prepare
                before = self._loaded_signature
                prepared_view = models.capture_append_view(self.project_id, event)
                prepared_append = prepare(self,event)
                prepared_view = models.prepare_append_view(prepared_view,self.project_id,event)
                # Readers may lend the previous completed SQL head while this
                # writer is active, with exact pre/post-append file proofs.
                after_hash = append(self,event,prepared=prepared_append,retain_intent=True)
                self.write_receipt = models.appended(self.project_id,before,after_hash,projected,event,
                                                     prepared_view=prepared_view)
            else:
                atomic_write(self.journal, "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events))
            return event

    def validate_evidence_ref(self, relative, source_project=None):
        if source_project is not None and source_project != self.project_id:
            if not isinstance(source_project, str) or not getattr(self, 'registry', None):
                raise ValueError('Invalid evidence source project')
            # Ownership writes bind and authorize the source before reaching
            # this origin journal. A moved task can publish a document from
            # its current project while retaining its original journal.
            try:
                source_store = self.registry.base_store(source_project)
            except KeyError:
                raise ValueError('Unknown evidence source project') from None
            source_store.validate_evidence_ref(relative)
            return
        if isinstance(relative, str) and relative.startswith('knowledge/'):
            match = re.fullmatch(r'knowledge/(?:(?:revision/([0-9]+))/)?document/(.+)', relative)
            if not match or not getattr(self, 'registry', None) or '..' in Path(relative).parts or any(ord(c)<32 for c in relative):
                raise ValueError('Invalid knowledge evidence reference')
            from knowledge_store import KnowledgeStore, KnowledgeError
            try:
                item = KnowledgeStore(self.registry, self.project_id).read(match[2], int(match[1]) if match[1] else None)
            except KnowledgeError as error:
                raise ValueError('Knowledge evidence must reference a document in this project') from error
            if item['kind'] != 'document':
                raise ValueError('Knowledge evidence must reference a document in this project')
            return
        self.resolve_path(relative)

    def resolve_path(self, relative):
        if isinstance(relative, str) and relative.startswith('hub-artifact/'):
            from artifact_store import materialize
            return materialize(self, relative)
        if self.root is None:
            raise ValueError('Connect a code workspace to read current source files')
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root) or Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise ValueError("Evidence must belong to this project")
        return path

    def evidence_origin(self, relative):
        with self.locked():
            seed, events = self._load()
            allowed = set()
            def collect(value):
                if isinstance(value, dict):
                    if isinstance(value.get("path"), str):
                        allowed.add(value["path"])
                    for item in value.values():
                        collect(item)
                elif isinstance(value, list):
                    for item in value:
                        collect(item)
            collect(seed)
            collect(events)
            if relative not in allowed:
                raise ValueError("File is not a registered evidence source")
            return self, relative

    def resolve_evidence_path(self, relative, mode='current'):
        if mode not in ('current', 'archive'):
            raise ValueError('Source mode must be current or archive')
        if relative.startswith('hub-artifact/'):
            if mode != 'current':
                raise ValueError('Artifact history uses explicit immutable version references')
            return self.resolve_path(relative)
        if Path(relative).is_absolute() or '..' in Path(relative).parts:
            raise ValueError('Evidence must belong to this project')
        if mode == 'archive' and getattr(self, 'registry', None):
            from source_snapshots import materialize
            snapshot = materialize(self, Path(relative).as_posix())
            if snapshot is not None:
                return snapshot
        archive = (self.data / 'source-archive').resolve()
        archived = (archive / relative).resolve()
        if not archived.is_relative_to(archive):
            raise ValueError('Evidence archive path escapes its root')
        return archived if mode == 'archive' else self.resolve_path(relative)

    def source_info(self, relative, mode='current'):
        import re
        authorized=re.sub(r'knowledge/revision/[0-9]+/document/','knowledge/document/',relative,count=1)
        try: origin, source_path = self.evidence_origin(relative)
        except ValueError:
            if authorized==relative: raise
            origin,source_path=self.evidence_origin(authorized)
        if source_path.startswith('hub-artifact/'):
            if mode != 'current':
                raise ValueError('Artifact history uses explicit immutable version references')
            from artifact_store import resolve, materialize
            item, content = resolve(origin, source_path)
            path = materialize(origin, source_path)
            from image_sources import image_info
            try:
                image = image_info(path)
            except ValueError:
                image = None
            try:
                text = content.decode('utf-8-sig')
                text_preview = not any(ord(c) < 32 and c not in '\t\r\n' for c in text)
            except UnicodeDecodeError:
                text_preview = False
            return dict(kind='artifact', path=source_path, sourceProject=origin.project_id,
                        available=True, currentAvailable=True, archiveAvailable=False,
                        resolvedPath=str(path), modifiedAt=None, version='sha256:' + item['contentHash'],
                        sha256=item['contentHash'], size=item['size'], name=item['name'],
                        artifactId=item['artifactId'], roles=item['roles'], provenance=item['provenance'],
                        previous=item.get('previous'), textPreviewAvailable=text_preview, image=image)
        if source_path.startswith('knowledge/'):
            if authorized!=relative: source_path=relative[relative.index('knowledge/'):]
            if mode!='current': raise ValueError('Knowledge history uses an explicit revision reference')
            from knowledge_store import KnowledgeStore, KnowledgeError
            import re
            match=re.fullmatch(r'knowledge/(?:(?:revision/([0-9]+)/))?document/(.+)',source_path)
            if not match: raise ValueError('Invalid knowledge source reference')
            store=KnowledgeStore(origin.registry,origin.project_id)
            revision=int(match[1]) if match[1] else store.context()['revision']
            try: item=store.read(match[2],revision)
            except KnowledgeError as error: raise FileNotFoundError(str(error)) from error
            if item['kind']!='document': raise ValueError('Knowledge source must be a document')
            if item.get('format')=='html':
                from knowledge_html import content
                data=content(store,item)
            else: data=item.get('markdown','').encode('utf-8')
            digest=hashlib.sha256(data).hexdigest()
            return dict(kind='knowledge',path=source_path,sourceProject=origin.project_id,
                        available=True,currentAvailable=True,archiveAvailable=False,image=None,
                        knowledgeRevision=revision,knowledgeId=item['id'],size=len(data),sha256=digest,
                        version='sha256:'+digest,versionPath=f'knowledge/revision/{revision}/document/'+item['id'],
                        resolvedPath=None,modifiedAt=None)
        path = origin.resolve_evidence_path(source_path, mode)
        current = origin.resolve_evidence_path(source_path, 'current')
        archive = origin.resolve_evidence_path(source_path, 'archive')
        stat = path.stat() if path.is_file() else None
        result = dict(kind=mode, path=source_path, resolvedPath=str(path),
                    projectRoot=str(origin.root), sourceProject=getattr(origin, 'project_id', None),
                    available=stat is not None, currentAvailable=current.is_file(), archiveAvailable=archive.is_file(),
                    version=f'{mode}:{stat.st_mtime_ns}:{stat.st_size}' if stat else None,
                    modifiedAt=datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat() if stat else None,
                    size=stat.st_size if stat else None)
        if mode == 'archive' and stat and getattr(origin, 'registry', None):
            from source_snapshots import entry_for
            snapshot = entry_for(origin, Path(source_path).as_posix())
            if snapshot:
                result.update(version='sha256:' + snapshot['sha256'], sha256=snapshot['sha256'],
                              snapshot=snapshot['snapshot'], modifiedAt=None)
        from image_sources import image_info
        result['image'] = image_info(path) if stat else None
        return result

    def evidence_path(self, relative, mode='current'):
        info = self.source_info(relative, mode)
        return self._available_source_path(info, mode)

    @staticmethod
    def _available_source_path(info, mode):
        if not info['available']:
            alternative = '; archived snapshot is available (select archive explicitly)' if mode == 'current' and info['archiveAvailable'] else ''
            raise FileNotFoundError(f'{mode.capitalize()} source is unavailable: {info["path"]}{alternative}')
        return Path(info['resolvedPath'])

    def read_evidence(self, relative, mode='current', *, text_only=False):
        info = self.source_info(relative, mode)
        if info['kind']=='knowledge':
            from knowledge_store import KnowledgeStore
            knowledge=KnowledgeStore(self.registry,info['sourceProject'])
            item=knowledge.read(info['knowledgeId'],info['knowledgeRevision'])
            if item.get('format')=='html':
                from knowledge_html import content
                return content(knowledge,item),info
            return item.get('markdown','').encode('utf-8'),info
        if text_only and info.get('image'):
            raise ValueError('Image source: use the image viewer or download the original')
        if text_only and info['kind'] == 'artifact' and not info['textPreviewAvailable']:
            raise ValueError('Artifact preview is unavailable; download the original')
        path = self._available_source_path(info, mode)
        if path.stat().st_size > 4_000_000:
            raise ValueError("Source exceeds preview limit; use the paged log viewer")
        with measure('filesystem'):
            with path.open('rb') as stream:
                data = stream.read(4_000_001)
        if len(data) > 4_000_000:
            raise ValueError("Source exceeds preview limit; use the paged log viewer")
        after = self.source_info(relative, mode)
        if info['version'] != after['version'] or info['resolvedPath'] != after['resolvedPath']:
            raise ValueError('File changed; refresh the viewer before continuing')
        info.update(sha256=hashlib.sha256(data).hexdigest(), size=len(data))
        info['version'] = 'sha256:' + info['sha256']
        return data, info

    def evidence(self, relative, mode='current'):
        return self.read_evidence(relative, mode)[0]

    def document(self, relative, mode='current'):
        data, info = self.read_evidence(relative, mode, text_only=True)
        return dict(text=data.decode('utf-8-sig', errors='replace'), source=info)

    def log_page(self, relative, offset=0, line=1, search='', level='', previous='', version='', mode='current'):
        import re
        info = self.source_info(relative, mode)
        path = self._available_source_path(info, mode)
        stat = path.stat()
        current = f'{mode}:{stat.st_mtime_ns}:{stat.st_size}'
        if version and current != version:
            raise ValueError('File changed; refresh the viewer before continuing')
        if offset < 0 or offset > stat.st_size or line < 1:
            raise ValueError('Invalid log cursor')
        if level not in ('', 'ERROR', 'WARN', 'INFO', 'DEBUG', 'TRACE'):
            raise ValueError('Invalid log level')
        rows, scanned = [], 0
        with path.open('rb') as source:
            source.seek(offset)
            while len(rows) < 200 and scanned < 2_000_000:
                raw = source.readline(65536)
                if not raw:
                    break
                scanned += len(raw)
                text = raw.decode('utf-8', errors='replace').rstrip('\r\n')
                text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
                match = re.search(r'\b(ERROR|FATAL|SEVERE|WARN(?:ING)?|INFO|DEBUG|TRACE)\b', text, re.I)
                continuation = bool(re.match(r'^\s+(?:at |\.\.\.)|^Caused by:|^Suppressed:', text))
                tone = match.group(1).upper() if match else (previous if continuation else '')
                tone = {'FATAL':'ERROR','SEVERE':'ERROR','WARNING':'WARN'}.get(tone,tone)
                previous = tone
                if (not level or tone == level) and search.casefold() in text.casefold():
                    rows.append(dict(line=line, text=text, level=tone, continued=not raw.endswith(b'\n') and len(raw)==65536))
                if raw.endswith(b'\n') or len(raw) < 65536:
                    line += 1
            next_offset = source.tell()
        if f'{mode}:{path.stat().st_mtime_ns}:{path.stat().st_size}' != current:
            raise ValueError('File changed; refresh the viewer before continuing')
        return dict(rows=rows, next=next_offset, line=line, previous=previous,
                    more=next_offset < stat.st_size, version=current, size=stat.st_size,
                    scanned=scanned, source=info)


class PortalServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 256
    def __init__(self, address, store=None, registry=None, *, bind_and_activate=True):
        self.store = store
        self.registry = registry
        if registry is not None:
            registry.require_ready()
        self.server_port = address[1]
        self.transport = 'threaded'
        self.stopping = threading.Event()
        self.event_cache_lock = threading.Lock()
        self.event_cache = {}
        self.chat_actions = None
        self.chat_actions_lock = threading.Lock()
        self.knowledge_watcher = None
        self.runtime_version = runtime_version(str(ROOT))
        from event_broker import EventBroker
        self.event_broker = EventBroker(self)
        super().__init__(address, Handler, bind_and_activate=bind_and_activate)
        if registry is not None:
            registry.check_url = 'http://127.0.0.1:' + str(self.server_port)
            from prepared_sources import PreparedSources
            registry.prepared_sources = PreparedSources(registry)
            from knowledge_store import watch
            self.knowledge_watcher = threading.Thread(target=watch,args=(registry,self.stopping),name='knowledge-watch',daemon=True)
            self.knowledge_watcher.start()

    def actions_service(self):
        with self.chat_actions_lock:
            if self.chat_actions is None:
                from unified_actions import UnifiedActions
                self.chat_actions=UnifiedActions(self.registry,portal_url='http://127.0.0.1:'+str(self.server_port))
            return self.chat_actions

    def serve_forever(self, poll_interval=.05):
        return super().serve_forever(poll_interval=poll_interval)

    def get_request(self):
        connection, address = super().get_request()
        from hub_lifecycle import control_directory
        if control_directory() is not None:
            connection.settimeout(5)  # Idle keep-alive sockets cannot stall a drain.
        return connection, address

    def read_snapshot(self, store):
        """One materialized read model for HTTP and SSE; writes bypass it.

        Capture inputs before materialization so concurrent changes force the
        next reader to rebuild. Never lend the shared object to a caller.
        Optional host observations are refreshed at least every ten seconds.
        """
        if getattr(store, 'registry', None) is not None:
            return store.registry.read_models.snapshot(store, observations=False, complete_history=False)
        key = str(store.data)
        with self.event_cache_lock:
            entry = self.event_cache.setdefault(key, {'lock': threading.Lock()})
        with entry['lock']:
            signature = store.event_signature()
            if (entry.get('signature') != signature or
                    time.monotonic() - entry.get('checked', float('-inf')) >= 10):
                checked = time.monotonic()
                state = store.snapshot()
                if getattr(self, 'registry', None) is not None:
                    from stage_operations import project_links
                    project_links(self.registry, store.project_id, state)
                entry.update(signature=signature, checked=checked, state=state)
            return copy.deepcopy(entry['state'])

    def event_state(self, store):
        return self.event_broker.state(store)

    def shutdown(self):
        self.stopping.set()
        super().shutdown()

    def server_close(self):
        self.stopping.set()
        super().server_close()
        if self.knowledge_watcher is not None:
            self.knowledge_watcher.join()
        self.event_broker.close()
        if self.chat_actions is not None:
            self.chat_actions.close()
        if self.registry and hasattr(self.registry,'_knowledge_executor'):
            self.registry._knowledge_executor.shutdown(wait=True,cancel_futures=True)
        if self.registry and hasattr(self.registry, '_connection_executor'):
            self.registry._connection_executor.shutdown(wait=True,cancel_futures=True)
        if self.registry and hasattr(self.registry, 'prepared_sources'):
            self.registry.prepared_sources.close()
        if self.registry:
            self.registry.close_connection_pool()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def reject_unread_post(self, status, body):
        """Deliver the rejection before closing an unread request on Windows.

        Closing immediately with pending input can reset TCP and discard the
        response. Half-close output, then discard a bounded amount for at most
        100 ms. Rejected bytes are never parsed or authorized as another call.
        """
        self.reply(status, body)
        self.wfile.flush()
        import socket
        previous = self.connection.gettimeout()
        try:
            self.connection.shutdown(socket.SHUT_WR)
            deadline, remaining = time.monotonic() + .1, 1_048_576
            while remaining > 0 and time.monotonic() < deadline:
                self.connection.settimeout(max(.001, deadline - time.monotonic()))
                chunk = self.rfile.read1(min(65536, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
        except (OSError, ValueError):
            pass
        finally:
            self.connection.settimeout(previous)

    def local_access(self, *, origin=False):
        hosts = self.headers.get_all('Host') or []
        origins = self.headers.get_all('Origin') or []
        allowed = (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')
        return len(hosts)==1 and hosts[0] in allowed and (not origin or
            len(origins)<=1 and (not origins or origins[0] in tuple('http://'+host for host in allowed)))
    def handle(self):
        try:
            super().handle()
        except ConnectionError:
            # Browser/health-check clients may close a keep-alive socket between requests.
            pass
        except Exception as error:
            from runtime_diagnostics import exception
            exception('request.connection_failed',error,method=getattr(self,'command',None),route=urlparse(getattr(self,'path','')).path)
            raise

    def log_message(self, fmt, *args):
        if '/connect/' in self.path or urlparse(self.path).path.startswith('/auth/'):
            return  # Invitation URLs are capabilities, never access-log data.
        if args and str(args[1] if len(args) > 1 else "") not in {"200", "304"}:
            from runtime_diagnostics import record
            record('request.response_error',method=getattr(self,'command',None),route=urlparse(self.path).path,status=str(args[1] if len(args)>1 else ''))
            if sys.stderr is not None:
                super().log_message(fmt, *args)

    def reply(self, status, body, content_type="application/json; charset=utf-8", image_download=False, *, etag=None, cache_control=None, content_policy=None):
        if status == 200 and self.server.registry and isinstance(body, dict) and \
                isinstance(body.get('tasks'), list) and isinstance(body.get('project'), dict) and 'relationsRevision' not in body:
            from stage_operations import project_links
            project_links(self.server.registry, body['project']['id'], body)
        with measure('serialization'):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        if etag and self.headers.get('If-None-Match') == etag:
            status, data = 304, b''
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if status != 304:
            self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache_control or ("no-cache" if etag else "no-store"))
        if etag:
            self.send_header('ETag', etag)
        self.send_header("X-Content-Type-Options", "nosniff")
        if urlparse(self.path).path.startswith('/auth/'):
            self.send_header('Referrer-Policy','no-referrer')
        timings = getattr(self, 'request_timings', None)
        metrics = getattr(self, 'metrics', None)
        if metrics:
            for name, duration in timings or []:
                metrics.add(name, duration)
            self.send_header('X-Request-ID', metrics.identifier)
            self.send_header('Server-Timing', metrics.header())
        elif timings:
            self.send_header('Server-Timing', ', '.join(f'{name};dur={duration * 1000:.2f}'
                                                       for name, duration in timings))
        if image_download:
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(str(image_download), safe=''))
        policy = "sandbox; default-src 'none'; style-src 'unsafe-inline'" if content_type.startswith('image/') else "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
        self.send_header("Content-Security-Policy", content_policy or policy)
        self.end_headers()
        self.wfile.write(data)

    def reply_html_source(self, reference, content, *, etag=None):
        if Path(reference).suffix.lower() not in ('.html', '.htm'):
            raise ValueError('HTML preview requires an HTML source')
        # Serve original bytes as a standalone page. Inline interactions work,
        # while the opaque sandbox keeps document scripts away from Hub data.
        policy = "sandbox allow-scripts; default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data: blob:; font-src data:; connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
        return self.reply(200, content, 'text/html; charset=utf-8', etag=etag, content_policy=policy)

    def reply_file(self, path, name):
        """Stream managed archives without allocating their full contents."""
        # Pin the file before headers. On Windows this also prevents deletion
        # during a download; on POSIX an unlinked open file remains readable.
        with path.open('rb') as source:
            return self._reply_open_file(path, name, os.fstat(source.fileno()).st_size)

    def _reply_open_file(self, path, name, size):
        self.send_response(200)
        self.send_header('Content-Type', 'application/zip')
        self.send_header('Content-Length', str(size))
        self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(name, safe=''))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.stream_file(path)

    def stream_file(self, path):
        with path.open('rb') as source:
            for chunk in iter(lambda: source.read(256 * 1024), b''):
                self.wfile.write(chunk)

    def backups(self):
        if not self.server.registry:
            raise ValueError('Резервные копии требуют общего хранилища проектов')
        from backup_api import Backups
        return Backups(self.server.registry, self.server.runtime_version)

    @track_handler
    @read_handler
    def do_GET(self):
        self.request_timings = []
        if not self.local_access():
            return self.reply(403, {"error": "Local access only"})
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            route = parsed.path.replace('/api/v1/', '/api/', 1)
            if route in ('/api/chatgpt-auth','/auth/chatgpt/authorize','/auth/callback'):
                from chatgpt_auth import ChatGPTAuth, AuthError
                if not self.server.registry:
                    return self.reply(404,{'error':'Multi-project mode required'})
                auth=ChatGPTAuth(self.server.registry)
                try:
                    if route=='/api/chatgpt-auth':
                        return self.reply(200,auth.attempt(query['attemptId'][0]) if query.get('attemptId') else auth.catalog())
                    if route=='/auth/chatgpt/authorize':
                        if set(query)!={'attemptId'} or len(query['attemptId'])!=1:
                            raise AuthError('chatgpt_invalid_request')
                        location=auth.authorization_url(query['attemptId'][0])
                    else:
                        if len(parsed.query)>12000:
                            raise AuthError('chatgpt_callback_invalid')
                        auth.callback(parse_qs(parsed.query,keep_blank_values=True),self.server.server_port)
                        location='/#settings/agents/models'
                    self.send_response(303)
                    self.send_header('Location',location)
                    self.send_header('Content-Length','0')
                    self.send_header('Cache-Control','no-store')
                    self.send_header('Referrer-Policy','no-referrer')
                    self.end_headers()
                    return
                except AuthError as error:
                    if route.startswith('/auth/'):
                        from chatgpt_auth import browser_error
                        from ui_preferences import read, PreferenceError
                        try:
                            language=read(self.server.registry)['language']
                        except PreferenceError:
                            language='ru'
                        return self.reply(error.status,browser_error(error,language),'text/html; charset=utf-8')
                    return self.reply(error.status,error.body)
            if route == '/api/runtime/diagnostics':
                from runtime_diagnostics import report
                return self.reply(200,report(include_tail=True))
            if route == '/api/runtime':
                from hub_desktop import runtime_status, DesktopError
                try:
                    return self.reply(200, runtime_status(self.server))
                except DesktopError as error:
                    return self.reply(error.status, {'code':'tray_visibility_removed','error':str(error)})
            if route == '/api/agent-workflow':
                from agent_instructions import bundle
                return self.reply(200, bundle(self.server.registry, 'http://127.0.0.1:'+str(self.server.server_port)))
            if route == '/api/agent-instructions':
                from agent_instructions import read
                from agent_bindings import BindingError
                if not self.server.registry:
                    return self.reply(404, {'error':'Multi-project mode required'})
                try:
                    return self.reply(200, read(self.server.registry))
                except BindingError as error:
                    return self.reply(error.status, error.body)
            if route == '/api/storage':
                from hub_import import storage_catalog
                if not self.server.registry:
                    return self.reply(404, {'error':'Multi-project mode required'})
                return self.reply(200, storage_catalog(self.server.registry))
            if route == '/api/agent-providers':
                from agent_providers import Providers, ProviderError
                if not self.server.registry:
                    return self.reply(404, {'error':'Multi-project mode required'})
                try:
                    providers = Providers(self.server.registry)
                    return self.reply(200, providers.probe_receipt(query['requestId'][0]) if query.get('requestId') else providers.catalog())
                except ProviderError as error:
                    return self.reply(error.status, error.body)
            if route == '/api/workspaces':
                from project_workspaces import Workspaces, WorkspaceError, installed_runtime_roots
                ids=query.get('project',[])
                if not self.server.registry or len(ids)!=1:
                    raise ValueError('Select an explicit registered project')
                try:
                    return self.reply(200, Workspaces(self.server.registry,runtime_roots=installed_runtime_roots()).catalog(ids[0]))
                except WorkspaceError as error:
                    return self.reply(error.status,error.body)
            if route == '/api/preferences':
                from ui_preferences import read, PreferenceError
                if not self.server.registry:
                    return self.reply(404, {'error':'Multi-project mode required'})
                try:
                    return self.reply(200, read(self.server.registry))
                except PreferenceError as error:
                    return self.reply(error.status, error.body)
            if parsed.path == '/mcp':
                if not self.local_access(origin=True):
                    return self.reply(403, {'error':'Local same-origin access only'})
                return self.reply(405, {'error':'Use POST for this MCP endpoint'})
            if route == '/api/connections':
                if not self.server.registry:return self.reply(404,{'error':'Multi-project mode required'})
                from agent_bindings import Connections, BindingError
                try:
                    return self.reply(200,Connections(self.server.registry).catalog())
                except BindingError as error:
                    return self.reply(error.status,error.body)
            if route == '/api/connection-tests':
                if not self.server.registry:return self.reply(404,{'error':'Multi-project mode required'})
                from agent_bindings import BindingError
                from connection_capabilities import Profiles
                try:
                    if set(query)-{'id','offset','limit'} or any(len(values)!=1 for values in query.values()):
                        raise BindingError('invalid_history_page','Use id, offset and limit once each')
                    return self.reply(200,Profiles(self.server.registry).history(query.get('id',[''])[0],
                        offset=query.get('offset',[0])[0],limit=query.get('limit',[20])[0]))
                except BindingError as error:
                    return self.reply(error.status,error.body)
            if route == '/api/task-launches':
                if not self.server.registry:return self.reply(404,{'error':'Multi-project mode required'})
                from agent_bindings import BindingError
                from agent_launches import Launches
                try:
                    return self.reply(200,Launches(self.server.registry).task_state(
                        query.get('project',[''])[0],query.get('task',[''])[0]))
                except BindingError as error:
                    return self.reply(error.status,error.body)
            if parsed.path.startswith('/connect/'):
                if not self.server.registry:return self.reply(404,{'error':'Multi-project mode required'})
                from agent_api import bootstrap
                from agent_bindings import BindingError
                try:
                    if query or not self.local_access(origin=True):
                        return self.reply(403,{'error':'Local same-origin access only'})
                    return self.reply(200,bootstrap(self.server.registry,parsed.path.removeprefix('/connect/'),
                        'http://127.0.0.1:'+str(self.server.server_port)))
                except BindingError as error:
                    return self.reply(error.status,error.body)
            if route == '/api/projects':
                if self.server.registry:
                    if set(query)-{'includeDeleted'} or query.get('includeDeleted') not in (None,['true'],['false']):
                        raise ValueError('Use includeDeleted=true or false')
                    return self.reply(200, self.server.registry.list(include_deleted=query.get('includeDeleted')==['true']))
                snapshot = self.server.store.snapshot()
                return self.reply(200, dict(schemaVersion=1, legacy=True, projects=[snapshot['project']]))
            if route == '/api/backups':
                if 'job' in query:
                    if set(query) != {'job'} or len(query['job']) != 1:
                        raise ValueError('Select one backup operation')
                    return self.reply(200, {'job': self.backups().job(query['job'][0])})
                if query:
                    if set(query) - {'page','pageSize','historyPage','sort','direction'} or any(len(values) != 1 for values in query.values()):
                        raise ValueError('Use valid backup pagination parameters')
                    return self.reply(200, self.backups().catalog(page=int(query.get('page',['1'])[0]),
                        page_size=int(query.get('pageSize',['20'])[0]), history_page=int(query.get('historyPage',['1'])[0]),
                        sort=query.get('sort',['createdAt'])[0], direction=query.get('direction',['desc'])[0]))
                return self.reply(200, self.backups().catalog())
            if route == '/api/backups/status':
                from storage_operations import status
                return self.reply(200, status(self.server.registry) if self.server.registry else
                                  {'writesPaused': False, 'operations': []})
            if route == '/api/backups/download':
                if set(query) != {'id'} or len(query['id']) != 1:
                    raise ValueError('Укажите один архив для скачивания')
                path, name = self.backups().download(query['id'][0])
                return self.reply_file(path, name)
            self.store = self.server.store
            if route == '/api/instructions' and self.server.registry:
                from hub_instructions import catalog, InstructionsError
                try:
                    return self.reply(200, catalog(self.server.registry.home))
                except InstructionsError as error:
                    return self.reply(error.status, error.body)
            if route in ('/api/state','/api/settings') and self.server.registry and self.server.registry.standalone and not query.get('project'):
                if route == '/api/settings':
                    return self.reply(200, dict(project=None,configured=False,scope='hub',projectRequired=True))
                return self.reply(200, dict(project=None,tasks=[],events=[],eventCount=0,
                    projectRequired=True,capabilities=dict(projectManagement=self.server.registry.schema_version==2)))
            if route.startswith('/api/knowledge/html/'):
                from knowledge_store import KnowledgeStore, KnowledgeError
                from knowledge_html import content, embedded_theme, mime
                try:
                    parts=route.removeprefix('/api/knowledge/html/').split('/',4)
                    if len(parts)!=5 or parts[3]!='files' or not re.fullmatch(r'[0-9]+',parts[1]):
                        raise ValueError('Use a versioned HTML bundle URL')
                    project,revision,identifier,_,relative=parts
                    project,identifier,relative=unquote(project),unquote(identifier),unquote(relative)
                    if query.get('project') not in (None,[project]): raise ValueError('Conflicting project selection')
                    if not self.server.registry: raise ValueError('HTML documents require multi-project mode')
                    knowledge=KnowledgeStore(self.server.registry,project)
                    item=knowledge.read(identifier,int(revision))
                    data=content(knowledge,item,relative)
                    if mime(relative).startswith('text/html') and (query.get('hub-embed')==['1'] or self.headers.get('Sec-Fetch-Dest')=='iframe'):
                        data=embedded_theme(data)
                    prefix=parsed.path.split('/files/',1)[0]+'/files/'
                    allowed='http://'+self.headers['Host']+prefix
                    policy="sandbox allow-scripts; default-src 'none'; script-src "+allowed+" 'unsafe-inline'; style-src "+allowed+" 'unsafe-inline'; img-src "+allowed+" data: blob:; font-src "+allowed+" data:; connect-src 'none'; frame-src 'none'; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
                    return self.reply(200,data,mime(relative),content_policy=policy)
                except KnowledgeError as error: return self.reply(error.status,error.body)
            if route.startswith('/api/') and route != '/api/health' and self.server.registry:
                ids = query.get('project', [])
                if len(ids) != 1 or not ids[0]:
                    return self.reply(400, {'error': 'Select an explicit project'})
                self.store = self.server.registry.store(ids[0])
            if route == "/api/health":
                from hub_lifecycle import control_directory, supervisor_alive
                control = control_directory()
                return self.reply(200, {"service": "project-hub", "root": str(self.store.root) if self.store else None, "pid": os.getpid(), 'multiProject': bool(self.server.registry), 'codeRoot': str(Path(__file__).resolve().parents[1]), 'dataHome': str(self.server.registry.home) if self.server.registry else str(self.store.data), 'runtimeVersion': self.server.runtime_version, 'runtimeMode':os.environ.get('PROJECT_HUB_RUNTIME_MODE', 'source'), 'transport': self.server.transport, 'supervised': control is not None, 'supervisorAlive': supervisor_alive(control) if control else None})
            if route == '/api/knowledge/blob':
                from knowledge_store import KnowledgeStore, KnowledgeError
                import mimetypes
                try:
                    data=KnowledgeStore(self.server.registry,self.store.project_id).read_blob(query.get('hash',[''])[0])
                    name=query.get('name',['asset'])[0]
                    mime=mimetypes.guess_type(name)[0]
                    mime=mime if mime in ('image/png','image/jpeg','image/gif','image/webp','image/svg+xml') else 'application/octet-stream'
                    return self.reply(200,data,mime,image_download=name if mime=='application/octet-stream' else False)
                except KnowledgeError as error: return self.reply(error.status,error.body)
            if route == '/api/knowledge/download':
                from knowledge_store import KnowledgeStore, KnowledgeError
                try:
                    knowledge=KnowledgeStore(self.server.registry,self.store.project_id)
                    if query.get('action',['export'])[0]=='backup':
                        return self.reply(200,json.dumps(knowledge.backup(),ensure_ascii=False).encode('utf-8'),
                                          'application/json; charset=utf-8',image_download='knowledge-backup.json')
                    if query.get('action',['export'])[0]!='export': raise ValueError('Unknown download action')
                    return self.reply(200,knowledge.export_bundle(public=query.get('public')==['true']),
                                      'application/zip',image_download='knowledge-export.zip')
                except KnowledgeError as error: return self.reply(error.status,error.body)
            if route == '/api/knowledge':
                if not self.server.registry:
                    raise ValueError('Knowledge requires multi-project mode')
                from knowledge_store import execute, KnowledgeError
                action = query.get('action', ['context'])[0]
                if action not in ('context','search','source-tree','source-read','read','history','job','import-read','export','backup','research-capabilities','research-object','research-result','research-history','research-providers'):
                    raise ValueError('Use JSON POST for knowledge mutations')
                args = {key: value[0] for key,value in query.items() if key not in ('project','action')}
                if 'revision' in args: args['revision'] = int(args['revision'])
                if 'public' in args: args['public'] = args['public'] == 'true'
                try:
                    return self.reply(200, execute(self.server.registry, self.store.project_id, action, args))
                except KnowledgeError as error:
                    return self.reply(error.status, error.body)
            if route == "/api/state":
                started = time.monotonic()
                state = self.server.read_snapshot(self.store)
                self.request_timings.append(('snapshot', time.monotonic() - started))
                state.pop('allEvents', None)
                if query.get('view') == ['portal'] and self.server.registry:
                    from internal_operations import filter_portal_internal_tasks
                    state = filter_portal_internal_tasks(self.server.registry, self.store.project_id, state)
                if hasattr(self.store, 'display_name'):
                    state['project']['name'] = self.store.display_name
                # The portal reads Git through /api/git. Preserve the complete
                # API for other clients without making bootstrap wait for Git.
                if query.get('view') != ['portal']:
                    started = time.monotonic()
                    state['git'] = cached_read_repository(self.store.root)
                    self.request_timings.append(('git', time.monotonic() - started))
                return self.reply(200, state)
            if route in ('/api/tasks/summary', '/api/tasks/detail'):
                if not self.server.registry:
                    raise ValueError('Prepared task views require multi-project mode')
                result = self.server.registry.read_models.snapshot(self.store, observations=False,
                    summary=route == '/api/tasks/summary',
                    task=query.get('task', [''])[0] if route == '/api/tasks/detail' else None)
                if route == '/api/tasks/summary':
                    from internal_operations import filter_portal_internal_tasks
                    result = filter_portal_internal_tasks(self.server.registry, self.store.project_id, result)
                    result['coordination'] = self.server.event_broker.diagnostics(self.store)
                    result['project']['name'] = self.store.display_name
                return self.reply(200, result)
            if route == '/api/version-control':
                from version_control import inspect_workspace
                return self.reply(200, inspect_workspace(self.store.root))
            if route == '/api/settings':
                from project_settings import read_settings
                if not self.server.registry:
                    raise ValueError('Project settings require multi-project mode')
                frozen = self.server.registry.read_models.backup_view(self.store.project_id)
                if frozen is not None:
                    return self.reply(200, json.loads(frozen[1])['settings'])
                return self.reply(200, read_settings(self.server.registry.base_store(self.store.project_id)))
            if route == '/api/instructions':
                from hub_instructions import catalog, InstructionsError
                if not self.server.registry:
                    raise ValueError('Instructions require multi-project mode')
                try:
                    return self.reply(200, catalog(self.server.registry.home))
                except InstructionsError as error:
                    return self.reply(error.status, error.body)
            if route == '/api/architecture-agent-models':
                if not self.server.registry:
                    raise ValueError('Agent models require multi-project mode')
                return self.reply(200, self.server.actions_service().models(self.store.project_id))
            if route == '/api/architecture-agent-history':
                from hub_action_context import ChatActionError
                if not self.server.registry:
                    raise ValueError('Agent history requires multi-project mode')
                try:
                    return self.reply(200, self.server.actions_service().research_history(
                        self.store.project_id, query.get('offset',[0])[0], query.get('limit',[20])[0]))
                except ChatActionError as error:
                    return self.reply(error.status,error.as_dict())
            if route == '/api/chat-actions':
                from hub_action_context import ChatActionError
                if not self.server.registry:
                    raise ValueError('Chat actions require multi-project mode')
                try:
                    service=self.server.actions_service()
                    task=query.get('task',[''])[0]
                    return self.reply(200,dict(capabilities=service.capabilities(self.store.project_id),
                                              recent=service.recent(self.store.project_id,task)))
                except ChatActionError as error:
                    return self.reply(error.status,error.as_dict())
            if route == '/api/review-summary':
                from hub_project_review import summary
                return self.reply(200, summary(self.server.registry, self.store.project_id,
                    target=query.get('target',['project'])[0], task=query.get('task',[None])[0],
                    stage=query.get('stage',[None])[0], offset=int(query.get('offset',['0'])[0]),
                    expected=query.get('expected',[None])[0]))
            if route == '/api/review':
                from hub_project_review import read_review, digest
                review=read_review(self.server.registry,self.store.project_id,query.get('ref',[''])[0])
                prefix='review-apply-'+digest(review)[:20]+'-'
                state=self.store.memory_snapshot();ids={event['id'] for event in state['allEvents']}
                return self.reply(200,dict(review,applied=[value['id'] for value in review['proposals'] if
                    prefix+value['id']+'-final' in ids],currentRevision=state['revision']))
            if route == '/api/checks':
                from check_runs import list_runs
                return self.reply(200, list_runs(self.store, int(query.get('offset', ['0'])[0]),
                                                  int(query.get('limit', ['50'])[0])))
            if route == '/api/checkpoints/detail':
                from completion_policy import checkpoint_details
                if not self.server.registry:
                    raise ValueError('Checkpoint details require multi-project mode')
                return self.reply(200, checkpoint_details(self.server.registry, self.store.project_id,
                    query.get('checkpoint', [''])[0], query.get('section', ['files'])[0],
                    int(query.get('offset', ['0'])[0]), int(query.get('limit', ['50'])[0]),
                    query.get('commit', [None])[0]))
            if route == '/api/checkpoints/batch-detail':
                from completion_policy import batch_details
                if not self.server.registry:
                    raise ValueError('Batch details require multi-project mode')
                return self.reply(200, batch_details(self.server.registry, self.store.project_id,
                    query.get('blob', [''])[0], query.get('section', ['steps'])[0],
                    int(query.get('offset', ['0'])[0]), int(query.get('limit', ['25'])[0])))
            if route == '/api/checkpoints/batch-content':
                from completion_policy import batch_content
                if not self.server.registry:
                    raise ValueError('Batch content requires multi-project mode')
                version = batch_content(self.server.registry, self.store.project_id, query.get('blob', [''])[0],
                    query.get('path', [''])[0], query.get('side', ['after'])[0], query.get('changeset', [None])[0], query.get('version', [None])[0])
                return self.reply(200, version['data'], 'application/octet-stream', image_download=version['name'],
                                  etag=version['sha256'], cache_control='private, no-cache')
            if route == "/api/git":
                started = time.monotonic()
                state = self.server.read_snapshot(self.store)
                if self.server.registry:
                    from task_transfer import barrier
                    models = self.server.registry.read_models
                    # Git needs the latest push receipts, not every journal
                    # body. Keep task ownership and these receipts coherent.
                    from backup_session import active
                    from contextlib import nullcontext
                    frozen = active(self.server.registry) is not None
                    with nullcontext() if frozen else barrier(self.server.registry):
                        if not frozen and state['revision'] != models.domain_key(self.store.project_id):
                            state = self.server.read_snapshot(self.store)
                        pushes = models.history(self.store.project_id, kind='git.push', limit=50, visible=False)
                        state['allEvents'] = list(reversed(pushes['events']))
                self.request_timings.append(('snapshot', time.monotonic() - started))
                started = time.monotonic()
                result = self.store.git_overview(snapshot=state)
                self.request_timings.append(('git', time.monotonic() - started))
                return self.reply(200, result)
            if route == '/api/tasks/migration-preview':
                state = self.store.snapshot()
                rows = []
                for task in state['tasks']:
                    rows.append({'task': task['id'], 'title': task['title'],
                                 'status': task.get('status'), 'type': task.get('type', 'task'),
                                 'priority': task.get('priority'), 'parentTask': task.get('parentTask'),
                                 'weight': task.get('weight'), 'needsReview': task.get('priority') is None})
                return self.reply(200, {'project': state['project'], 'revision': state['revision'],
                                        'tasks': rows, 'needsReview': sum(row['needsReview'] for row in rows),
                                        'writes': 0, 'message': 'Preview only; no journal events were written.'})
            if route == "/api/history":
                before = int(query["before"][0]) if "before" in query else None
                limit = max(1, min(100, int(query.get("limit", ["40"])[0])))
                return self.reply(200, self.store.history(query.get("task", [None])[0], before, limit, query.get("kind", [None])[0]))
            if route == '/api/diagnostics':
                return self.reply(200, self.store.diagnostics())
            if route == '/api/chats':
                from task_chats import chat_history
                return self.reply(200, chat_history(self.store, task=query.get('task', [None])[0],
                    offset=max(0, int(query.get('offset', ['0'])[0])),
                    limit=max(1, min(100, int(query.get('limit', ['25'])[0]))),
                    query=query.get('q', [''])[0][:200]))
            if route in ('/api/coordination', '/api/diagnostics/archive'):
                offset = max(0, int(query.get('offset', ['0'])[0]))
                return self.reply(200, self.store.coordination(offset))
            if route == "/api/evidence":
                reference = query.get('path', [''])[0]
                data, info = self.store.read_evidence(reference, query.get('mode', ['current'])[0])
                etag = '"' + info['sha256'] + '"' if 'sha256' in info else None
                if query.get('preview') == ['html']:
                    return self.reply_html_source(reference, data, etag=etag)
                return self.reply(200, data, 'text/plain; charset=utf-8', etag=etag)
            if route == '/api/artifact':
                if query.get('mode', ['current'])[0] != 'current':
                    raise ValueError('Artifact history uses explicit immutable version references')
                reference = query.get('path', [''])[0]
                origin, relative = self.store.evidence_origin(reference)
                from artifact_store import resolve
                item, content = resolve(origin, relative)
                if query.get('preview') == ['html']:
                    return self.reply_html_source(item['name'], content, etag='"' + item['contentHash'] + '"')
                return self.reply(200, content, 'application/octet-stream', image_download=item['name'],
                                  etag='"' + item['contentHash'] + '"')
            if route == '/api/image':
                from image_sources import read_image
                path = self.store.evidence_path(query.get('path', [''])[0], query.get('mode', ['current'])[0])
                preview = query.get('preview', ['full'])[0]
                if self.server.registry:
                    data, mime, etag = self.server.registry.prepared_sources.image(
                        path, preview, if_none_match=self.headers.get('If-None-Match'))
                else:
                    data, mime = read_image(path, preview)
                    etag = '"' + hashlib.sha256(data).hexdigest() + '"'
                # Gallery images may be ordinary mutable project files. Keep
                # a short browser lifetime and revalidate changed responses.
                return self.reply(200, data, mime, image_download=path.name if preview == 'original' else False,
                                  etag=etag, cache_control='private, no-cache')
            if route in ('/api/source', '/api/document'):
                reader = self.store.source_info if route == '/api/source' else self.store.document
                return self.reply(200, reader(query.get('path', [''])[0], query.get('mode', ['current'])[0]))
            if route == '/api/log':
                q = lambda key, default='': query.get(key, [default])[0]
                return self.reply(200, self.store.log_page(q('path'), int(q('offset','0')), int(q('line','1')), q('search'), q('level'), q('previous'), q('version'), q('mode','current')))
            if route == "/api/events":
                return self.stream()
            assets = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css", "/favicon.svg": "favicon.svg"}
            assets.update({f'/{name}': name for name in ('viewer.js', 'viewer.css', 'vendor/marked.js', 'vendor/purify.js', 'vendor/highlight.js', 'vendor/lucide.js', 'vendor/cytoscape.js')})
            assets.update({f'/{name}': name for name in ('asset-loader.js', 'live-ui.js', 'task-table.js', 'task-table.css', 'ui-state.js', 'task-editor.js', 'task-editor.css')})
            assets.update({f'/{name}': name for name in ('settings.js', 'settings.css', 'agent-providers.js',
                'agent-providers.css', 'runtime-status.js', 'runtime-status.css', 'local-files.js')})
            assets.update({f'/{name}': name for name in ('i18n.js', 'locale-catalog.js')})
            assets.update({f'/{name}': name for name in ('backups.js', 'backups.css', 'backup-status.js')})
            assets.update({f'/{name}': name for name in ('projects.js', 'projects.css')})
            assets.update({f'/{name}': name for name in ('connections.js', 'connection-projects.js', 'connections.css', 'native-chats.js')})
            assets.update({f'/{name}': name for name in ('storage.js', 'subsystems.js', 'workspaces.js')})
            assets.update({f'/{name}': name for name in ('chat-actions.js', 'chat-actions.css')})
            assets.update({f'/{name}': name for name in ('task-launches.js', 'task-launches.css')})
            assets.update({f'/{name}': name for name in ('checks.js', 'checks.css')})
            assets.update({f'/{name}': name for name in ('images.js', 'images.css')})
            assets.update({f'/{name}': name for name in ('knowledge.js', 'knowledge.css', 'documentation.js', 'documentation.css')})
            assets.update({f'/{name}': name for name in ('knowledge-research.js', 'knowledge-research.css')})
            assets.update({f'/{name}': name for name in ('html-documents.js','html-documents.css')})
            assets.update({f'/{name}': name for name in ('architecture-map.js', 'architecture-routing.js', 'architecture-canvas.js', 'knowledge-workspace.js', 'vendor/layout-base.js', 'vendor/cose-base.js', 'vendor/cytoscape-fcose.js', 'vendor/elk-api.js', 'vendor/elk-worker.min.js')})
            if parsed.path not in assets:
                return self.reply(404, {"error": "Not found"})
            path = (self.store.installation_root if self.store else ROOT) / "tools/project-portal/web" / assets[parsed.path]
            mime = {".js": "text/javascript", ".css": "text/css", ".html": "text/html", ".svg": "image/svg+xml"}[path.suffix]
            data = path.read_bytes()
            if parsed.path == '/' and self.server.registry:
                from ui_preferences import read, PreferenceError
                try:
                    language = read(self.server.registry)['language']
                except PreferenceError:
                    language = 'ru'
                data = data.replace(b'<html lang="ru">',
                    ('<html lang="'+language+'" data-hub-locale="'+language+'">').encode())
            return self.reply(200, data, mime + "; charset=utf-8",
                              etag='"' + hashlib.sha256(data).hexdigest() + '"')
        except SettingsError as error:
            return self.reply(error.status, error.body)
        except FileNotFoundError as error:
            return self.reply(404, {"error": str(error)})
        except (ValueError, KeyError, TimeoutError) as error:
            return self.reply(400, {"error": str(error)})
        except (ConnectionResetError, BrokenPipeError):
            pass

    def task_write_response(self, store, *, receipt=None):
        if parse_qs(urlparse(self.path).query).get('view') == ['ack']:
            revision = (receipt['revision'] if receipt is not None and receipt['project'] == store.project_id
                        else store.registry.read_models.domain_key(store.project_id))
            return dict(accepted=True, revision=revision)
        if parse_qs(urlparse(self.path).query).get('view') == ['summary']:
            result = store.registry.read_models.snapshot(store, observations=False, summary=True)
            result['coordination'] = self.server.event_broker.diagnostics(store)
            return result
        return store.snapshot()

    @track_handler
    def do_POST(self):
        # Rejected requests may have an unread body; never parse it as another request.
        self.close_connection = True
        if not self.local_access(origin=True):
            return self.reject_unread_post(403,dict(error='Local same-origin access only'))
        if not self.server.registry:return self.reject_unread_post(404,dict(error='Multi-project mode required'))
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':
            return self.reject_unread_post(415,dict(error='JSON required'))
        try:
            size=int(self.headers.get('Content-Length','0'))
            route=urlparse(self.path).path
            from backup_api import REQUEST_LIMIT
            from agent_sdk import MAX_AGENT_REQUEST_BYTES
            limit = REQUEST_LIMIT if route == '/api/v1/backups' else 28_000_000 if route in ('/api/v1/images/upload', '/api/v1/artifacts/upload','/api/v1/agent/artifacts') else 64_000_000 if route == '/api/v1/knowledge' else MAX_AGENT_REQUEST_BYTES if route in ('/mcp','/api/v1/agent/call') else 160000 if route in ('/api/agent-instructions','/api/v1/agent-instructions','/api/v1/connections') else 16000
            if route == '/api/v1/backups' and size > limit:
                return self.reject_unread_post(413, {'error': 'Превышен размер блока загрузки'})
            if route in ('/mcp','/api/v1/agent/call','/api/v1/connections') and size > limit:
                return self.reject_unread_post(413, {'error': 'Request exceeds route limit'})
            if not 0<size<=limit:raise ValueError('Invalid request size')
            raw=self.rfile.read(size)
            if route == '/mcp':
                from mcp_transport import dispatch,error
                from agent_instructions import bundle
                try:
                    body=json.loads(raw,parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON number')))
                except (ValueError,UnicodeError):
                    return self.reply(400,error(None,-32700,'Parse error'))
                status,body=dispatch(self.server.registry,body,self.headers,
                    bundle(self.server.registry, 'http://127.0.0.1:'+str(self.server.server_port))['workflow'],
                    base='http://127.0.0.1:'+str(self.server.server_port))
                return self.reply(status,b'' if body is None else body)
            body=json.loads(raw)
            if route in ('/api/runtime', '/api/v1/runtime'):
                from hub_desktop import update_runtime, DesktopError
                try:
                    return self.reply(200, update_runtime(self.server, body))
                except DesktopError as error:
                    return self.reply(error.status, {'code':'tray_visibility_removed','error':str(error)})
            from hub_lifecycle import draining
            if draining():
                return self.reply(423, {'error':'storage_switch_in_progress', 'retryable':True})
            if route == '/api/v1/local-files':
                from local_files import execute, LocalFileError
                try:
                    return self.reply(200, execute(self.server.registry, body, application_home=ROOT))
                except LocalFileError as error:
                    return self.reply(400, {'error': str(error), 'code': 'local_folder_unavailable'})
            background_project = route == '/api/v1/projects' and isinstance(body, dict) and body.get('background') is True
            if route not in ('/api/v1/backups', '/api/v1/storage', '/api/v1/agent/call') and not background_project:
                from storage_operations import ensure_writable
                ensure_writable(self.server.registry)
            if route == '/api/v1/connection-probes/answer':
                from connection_capabilities import Profiles
                from agent_bindings import BindingError
                try:
                    return self.reply(200, Profiles(self.server.registry).answer(body))
                except BindingError as error:
                    return self.reply(error.status, error.body)
            if route in ('/api/agent-instructions', '/api/v1/agent-instructions'):
                from agent_instructions import update
                from agent_bindings import BindingError
                try:
                    return self.reply(200, update(self.server.registry, body))
                except BindingError as error:
                    return self.reply(error.status, error.body)
            if route == '/api/v1/storage':
                from hub_import import storage_action
                return self.reply(200, storage_action(self.server.registry, body))
            if route == '/api/v1/preferences':
                from ui_preferences import update, PreferenceError
                from backup_session import BackupBusy
                try:
                    return self.reply(200, update(self.server.registry, body))
                except PreferenceError as error:
                    return self.reply(error.status, error.body)
                except BackupBusy:
                    return self.reply(423, {'error':'backup_in_progress','retryable':True})
            if route not in ('/api/v1/backups','/api/v1/agent/call'):
                from backup_session import active
                if active(self.server.registry) is not None:
                    return self.reply(423, {'error': 'backup_in_progress', 'retryable': True,
                        'message': 'Снимок резервной копии создаётся. Просмотр доступен; повторите изменение после завершения снимка.'})
            if route in ('/api/v1/connections','/api/v1/agent/enroll','/api/v1/agent/call','/api/v1/agent/artifacts'):
                from agent_api import execute
                from agent_bindings import BindingError
                from hub_core import HubError
                try:
                    return self.reply(200,execute(self.server.registry,route,body,self.headers,
                        'http://127.0.0.1:'+str(self.server.server_port),administrator=True))
                except BindingError as error:
                    return self.reply(error.status,error.body)
                except HubError as error:
                    return self.reply(423 if error.body.get('error') in ('backup_in_progress', 'storage_operation_in_progress') else 409,error.body)
            if route == '/api/v1/workspaces':
                # Each workspace edit is checked against its explicit project revision.
                from project_workspaces import Workspaces, WorkspaceError, installed_runtime_roots
                from project_registry import ProjectRevisionConflict
                if not isinstance(body,dict) or set(body)-{'project','action','expected','requestId','workspace','root','enabled'} or not {'project','action','expected','requestId'}<=set(body):
                    raise ValueError('Use an explicit project and workspace operation')
                try:
                    return self.reply(200, Workspaces(self.server.registry,runtime_roots=installed_runtime_roots()).change(
                        body['project'],body['action'],expected=body['expected'],request_id=body['requestId'],
                        **{key:body[key] for key in ('workspace','root','enabled') if key in body}))
                except WorkspaceError as error:
                    return self.reply(error.status,error.body)
                except ProjectRevisionConflict as error:
                    return self.reply(409,{'error':'project_revision_conflict','message':str(error)})
            if route == '/api/v1/agent-providers':
                from agent_providers import Providers, ProviderError
                from chatgpt_auth import AuthError
                from provider_runtime import RuntimeError as ProviderRuntimeError
                try:
                    return self.reply(200, Providers(self.server.registry).change(body))
                except ProviderError as error:
                    return self.reply(error.status, error.body)
                except AuthError as error:
                    return self.reply(error.status,error.body)
                except ProviderRuntimeError as error:
                    return self.reply(400, {'error':error.code, 'message':'Check the provider configuration'})
            if route == '/api/v1/chatgpt-auth':
                from chatgpt_auth import ChatGPTAuth, AuthError
                if self.headers.get_content_type()!='application/json':
                    return self.reply(400,{'error':'chatgpt_invalid_request'})
                try:
                    return self.reply(200,ChatGPTAuth(self.server.registry).change(body,self.server.server_port))
                except AuthError as error:
                    return self.reply(error.status,error.body)
            if route == '/api/v1/source-snapshots':
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not isinstance(body, dict) or set(body) != {'snapshot', 'files'}:
                    raise ValueError('Use an explicit project, snapshot and source paths')
                from source_snapshots import register
                return self.reply(200, register(self.server.registry.base_store(ids[0]), body['snapshot'], body['files']))
            if route == '/api/v1/backups':
                try:
                    from storage_operations import ensure_writable, Operations
                    if body.get('action') == 'upload-start':
                        replay = self.backups().upload_replay(body)
                        if replay is not None:
                            return self.reply(200, replay)
                    if body.get('background') is not True and body.get('action') not in ('upload-chunk', 'upload-abort', 'upload-complete'):
                        ensure_writable(self.server.registry)
                    elif body.get('background') is not True and any(row.get('status') in ('queued', 'running') or row.get('blocking')
                             for row in Operations(self.server.registry).catalog()):
                        ensure_writable(self.server.registry)
                    if isinstance(body, dict) and body.get('background') is True:
                        request_id = body.get('requestId')
                        operation = {k: v for k, v in body.items() if k != 'background' and
                                     (k != 'requestId' or body.get('action') in ('delete-archive','delete-copy'))}
                        return self.reply(202, {'job': self.backups().start(operation, request_id)})
                    return self.reply(200, self.backups().execute(body))
                except OSError:
                    return self.reply(500, {'error': 'Не удалось прочитать или сохранить резервную копию. Проверьте доступ и свободное место в папке данных.'})
            if route == '/api/v1/projects':
                if not isinstance(body,dict):
                    raise ValueError('Use a project operation object')
                if body.get('background') is True:
                    from project_registry import start_operation
                    return self.reply(202, start_operation(self.server.registry, body))
                if body.get('action')=='create' and set(body)=={'action','name','roots','requestId'}:
                    return self.reply(200, dict(project=self.server.registry.create(
                        body['name'],body['roots'],request_id=body['requestId'])))
                if body.get('action')=='update' and set(body)=={'action','project','patch','expected','requestId'}:
                    from project_registry import ProjectRevisionConflict
                    try:
                        return self.reply(200, dict(project=self.server.registry.update(
                            body['project'],body['patch'],expected=body['expected'],request_id=body['requestId'])))
                    except ProjectRevisionConflict as error:
                        return self.reply(409, dict(error=str(error), code='project_revision_conflict'))
                raise ValueError('Use create or update with an explicit project operation and request ID')
            if route in ('/api/v1/chat-answer','/api/v1/review-apply'):
                return self.reply(410, dict(code='task_execution_removed',
                    error='Task execution, continuation and automated task reviews were removed.'))
            if route == '/api/v1/architecture-agent':
                ids=parse_qs(urlparse(self.path).query).get('project',[])
                if len(ids)!=1 or not ids[0] or not isinstance(body,dict) or set(body)!={'research','actionId'}:
                    raise ValueError('Architecture research requires an explicit project, research and actionId')
                from hub_action_context import ChatActionError
                try:
                    return self.reply(202,self.server.actions_service().start_research(ids[0],body['research'],body['actionId']))
                except ChatActionError as error:
                    return self.reply(error.status,error.as_dict())
            if route == '/api/v1/chat-actions':
                ids=parse_qs(urlparse(self.path).query).get('project',[])
                if len(ids)!=1 or not ids[0]:
                    raise ValueError('Select an explicit project')
                if not isinstance(body,dict):
                    raise ValueError('Research requires a JSON object')
                if set(body) & {'task','stage','threadId','target','mode','intent','expected'}:
                    return self.reply(410, dict(code='task_execution_removed',
                        error='Hub requests support architecture and documentation research only.'))
                from hub_action_context import ChatActionError
                try:
                    if body.get('action') == 'new' and set(body) == {'action','actionId','research'}:
                        return self.reply(202,self.server.actions_service().start_research(
                            ids[0],body['research'],body['actionId']))
                    if body.get('action') == 'cancel' and set(body) == {'action','actionId'}:
                        return self.reply(202,self.server.actions_service().cancel(ids[0],body['actionId']))
                    raise ValueError('Use new with research/actionId, or cancel with actionId')
                except ChatActionError as error:
                    return self.reply(error.status,error.as_dict())
            if route == '/api/v1/knowledge':
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not ids[0] or not isinstance(body,dict) or set(body)-{'action','args'}:
                    raise ValueError('Knowledge needs an explicit project and action/args object')
                from knowledge_store import execute, KnowledgeError
                try:
                    return self.reply(200, execute(self.server.registry, ids[0], body.get('action'), body.get('args')))
                except KnowledgeError as error:
                    return self.reply(error.status, error.body)
            if route in ('/api/v1/images/upload', '/api/v1/artifacts/upload'):
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not ids[0]:
                    raise ValueError('Select an explicit project')
                allowed = {'name', 'content'} if route == '/api/v1/images/upload' else {'name', 'content', 'roles', 'previous'}
                if not isinstance(body, dict) or set(body) - allowed or not {'name', 'content'} <= set(body):
                    raise ValueError('Upload requires name and base64 content')
                store = self.server.registry.store(ids[0])
                if route == '/api/v1/images/upload':
                    from image_sources import upload
                    result = upload(store, body['name'], body['content'])
                else:
                    from artifact_store import upload
                    result = upload(store, body['name'], body['content'],
                                    **{key: body[key] for key in ('roles', 'previous') if key in body})
                from image_sources import read_image
                import base64
                try:
                    data, mime = read_image(store.resolve_path(result['source']['path']), 'thumbnail')
                    result['preview'] = dict(mime=mime, content=base64.b64encode(data).decode('ascii'))
                except ValueError:
                    result['preview'] = None
                return self.reply(200, result)
            if urlparse(self.path).path == '/api/v1/plugin/call':
                from plugin_api import call, HubError
                try:
                    return self.reply(200,call(self.server.registry,body))
                except HubError as error:
                    return self.reply(409,error.body)
            route=urlparse(self.path).path
            if route == '/api/v1/checks':
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not ids[0]:
                    raise ValueError('Select an explicit project')
                from check_runs import ingest
                from plugin_api import compact_write_ack
                return self.reply(200, compact_write_ack('hub_check', ingest(self.server.registry, ids[0], body)))
            if route == '/api/v1/instructions':
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not ids[0] or not self.server.registry:
                    raise ValueError('Select an explicit project')
                self.server.registry.base_store(ids[0])
                if not isinstance(body, dict) or set(body) - {'expected', 'patch', 'reset'}:
                    raise ValueError('Unknown instructions fields')
                from hub_instructions import Instructions, InstructionsError, catalog
                try:
                    Instructions(self.server.registry.home).update(body.get('expected'), body.get('patch'), body.get('reset'))
                    return self.reply(200, catalog(self.server.registry.home))
                except InstructionsError as error:
                    return self.reply(error.status, error.body)
            if route in ('/api/v1/settings', '/api/v1/checkpoints/retry', '/api/v1/checkpoints/batch'):
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not ids[0]:
                    raise ValueError('Select an explicit project')
                if not isinstance(body, dict):
                    raise ValueError('JSON object required')
                from task_transfer import barrier
                with barrier(self.server.registry):
                    if route == '/api/v1/settings':
                        if set(body) - {'expected', 'patch', 'reset'}:
                            raise ValueError('Unknown settings fields')
                        if ('patch' in body) == ('reset' in body):
                            raise SettingsError('invalid_settings', 'Use patch OR reset with expected settings revision')
                        from project_settings import update_settings
                        result = update_settings(self.server.registry.base_store(ids[0]), body.get('patch'),
                                                 body.get('expected'), actor='local-user', reset=body.get('reset'))
                    elif route == '/api/v1/checkpoints/batch':
                        if set(body) - {'targets', 'expected', 'reason', 'action', 'commit', 'confirmed'}:
                            raise ValueError('Unknown reviewed batch fields')
                        from completion_policy import checkpoint_batch
                        result = checkpoint_batch(self.server.registry, ids[0], **body)
                    else:
                        if set(body) - {'task', 'stage', 'expected', 'commits', 'reason'} or not isinstance(body.get('task'), str):
                            raise ValueError('Checkpoint retry requires task and expected revision')
                        if ('commits' in body or 'reason' in body) and (body.get('commits') is None or body.get('reason') is None):
                            raise ValueError('Supply commits and reason together with non-null values')
                        from completion_policy import retry_checkpoint
                        result = retry_checkpoint(self.server.registry, ids[0], body['task'],
                                                  body.get('expected'), body.get('stage'), body.get('commits'), body.get('reason'))
                return self.reply(200, result)
            if route == '/api/v1/tasks/create' or route in {
                    '/api/v1/stages/create', '/api/v1/stages/update', '/api/v1/stages/delete',
                    '/api/v1/stages/unlink', '/api/v1/stages/transfer', '/api/v1/stages/restore'}:
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not ids[0]:
                    raise ValueError('Select an explicit project')
                from stage_operations import manual_operation
                return self.reply(200, manual_operation(self.server.registry, ids[0], route, body))
            if route == '/api/git/push':
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not ids[0] or body != {'confirm': True}:
                    raise ValueError('Push requires an explicit confirmation for one project')
                store = self.server.registry.store(ids[0])
                try:
                    if store.root is None:
                        return self.reply(409, dict(error='Configure a code workspace before pushing Git commits', code='workspace_required'))
                    result = push_repository(store.root, confirmed=True)
                    try:
                        current = store.snapshot()
                        pushed = result.get('commits', [])
                        store.record(dict(id='git-push-' + uuid.uuid4().hex, taskId='__project__', kind='git.push',
                                          title='Git push выполнен',
                                          detail=f"Отправлено commit-ов: {len(pushed)} · ветка: {result.get('branch') or '—'}",
                                          git={'branch': result.get('branch'), 'upstream': result.get('upstream'),
                                               'commits': pushed}), expected_revision=current['revision'])
                        result['eventRecorded'] = True
                    except (ValueError, OSError, TimeoutError) as error:
                        result['eventRecorded'] = False
                        result['eventWarning'] = str(error)[:240]
                    return self.reply(200, result)
                except GitIntegrationError as error:
                    return self.reply(409, {'error': str(error)})
            if route == '/api/v1/tasks/update':
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not ids[0]:
                    raise ValueError('Select an explicit project')
                if not isinstance(body, dict) or set(body) - {'task', 'expected', 'patch'}:
                    raise ValueError('Invalid task update fields')
                task_id, expected, patch = body.get('task'), body.get('expected'), body.get('patch')
                if not isinstance(task_id, str) or not isinstance(expected, (int, str)) or not isinstance(patch, dict):
                    raise ValueError('Task update requires task, expected revision and patch')
                allowed = {'title', 'summary', 'status', 'scope', 'deferred', 'acceptance', 'sources', 'type', 'priority', 'parentTask', 'links', 'weight', 'estimate', 'blocker'}
                if set(patch) - allowed:
                    raise ValueError('Unsupported task patch')
                store = self.server.registry.store(ids[0])
                # Status guards need only this owner's selected task. record()
                # still rechecks the supplied revision and validates the whole
                # resulting owner hierarchy under its writer barrier.
                tasks = self.server.registry.read_models.raw_tasks(ids[0], task=task_id)
                if not tasks:
                    raise ValueError('Unknown task')
                current = tasks[0]
                if patch.get('status') == 'done' and current['status'] != 'done':
                    raise ValueError('Use the explicit task close route')
                if 'status' in patch and current['status'] in ('done', 'cancelled') and patch['status'] != current['status']:
                    raise ValueError('Use the explicit task reopen route')
                if 'links' in patch:
                    from stage_operations import validate_links
                    validate_links(self.server.registry, ids[0], task_id, patch['links'])
                expected_revision = expected
                store.record(dict(id='task-update-' + uuid.uuid4().hex, taskId=task_id,
                                  kind='task.updated', title='Задача обновлена', patch=patch),
                             expected_revision=expected_revision)
                return self.reply(200, self.task_write_response(store, receipt=getattr(store,'write_receipt',None)))
            if route == '/api/v1/tasks/close':
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not ids[0]:
                    raise ValueError('Select an explicit project')
                if not isinstance(body, dict) or set(body) - {'task', 'expected', 'mode', 'reason'}:
                    raise ValueError('Invalid task close fields')
                task_id, expected, mode = body.get('task'), body.get('expected'), body.get('mode', 'manual')
                if not isinstance(task_id, str) or not isinstance(expected, (int, str)) or mode not in ('auto', 'manual'):
                    raise ValueError('Task close requires task, expected revision and auto/manual mode')
                from task_transfer import barrier
                # Keep validation, the optional Git checkpoint and closure in one
                # ownership transaction so stale requests cannot commit files.
                with barrier(self.server.registry):
                    store = self.server.registry.store(ids[0]); state = store.task_context(task_id)
                    if expected != state['revision']:
                        raise ValueError('Task changed; refresh before writing')
                    task = next((row for row in state['tasks'] if row['id'] == task_id), None)
                    if not task:
                        raise ValueError('Unknown task')
                    incomplete = task.get('completion', {}).get('incompleteChildren', [])
                    if mode == 'auto' and incomplete:
                        raise ValueError('Automatic close requires all child tasks to be complete')
                    patch = {'status': 'done', 'closedManually': mode == 'manual'}
                    if incomplete:
                        patch['closeWarning'] = incomplete
                    if body.get('reason'):
                        patch['closeReason'] = str(body['reason'])[:800]
                    store.record(dict(id='task-close-' + uuid.uuid4().hex, taskId=task_id,
                                      kind='task.updated', title='Задача закрыта', patch=patch),
                                 expected_revision=state['revision'])
                    result = {'warning': incomplete, **self.task_write_response(store)}
                return self.reply(200, result)
            if route == '/api/v1/tasks/reopen':
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not ids[0]:
                    raise ValueError('Select an explicit project')
                if not isinstance(body, dict) or set(body) - {'task', 'expected'}:
                    raise ValueError('Invalid task reopen fields')
                task_id, expected = body.get('task'), body.get('expected')
                if not isinstance(task_id, str) or not isinstance(expected, (int, str)):
                    raise ValueError('Task reopen requires task and expected revision')
                store = self.server.registry.store(ids[0]); state = store.task_context(task_id)
                task = next((row for row in state['tasks'] if row['id'] == task_id), None)
                if not task:
                    raise ValueError('Unknown task')
                if task['status'] not in ('done', 'cancelled'):
                    raise ValueError('Only a closed task can be reopened')
                expected_revision = expected
                store.record(dict(id='task-reopen-' + uuid.uuid4().hex, taskId=task_id,
                                  kind='task.updated', title='Задача переоткрыта',
                                  patch={'status': 'active'}),
                             expected_revision=expected_revision)
                return self.reply(200, self.task_write_response(store))
            if route == '/api/v1/tasks/link':
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not ids[0]:
                    raise ValueError('Select an explicit project')
                if not isinstance(body, dict) or set(body) - {'task', 'target', 'type', 'project', 'expected'}:
                    raise ValueError('Invalid task link fields')
                task_id, target, link_type, link_project, expected = body.get('task'), body.get('target'), body.get('type'), body.get('project'), body.get('expected')
                if not all(isinstance(value, str) for value in (task_id, target, link_type)) or not isinstance(expected, (int, str)):
                    raise ValueError('Task link requires task, target, type and expected revision')
                if link_type not in LINK_TYPES:
                    raise ValueError('Invalid task link type')
                from stage_operations import validate_links
                validate_links(self.server.registry, ids[0], task_id,
                               [{'type': link_type, 'target': target, **({'project': link_project} if link_project is not None else {})}])
                store = self.server.registry.store(ids[0])
                state = store.memory_tasks()
                task = next((t for t in state['tasks'] if t['id'] == task_id), None)
                if not task or (not any(t['id'] == target for t in state['tasks']) and not isinstance(link_project, str)):
                    raise ValueError('Unknown linked task')
                links = [link for link in task.get('links', []) if not (link.get('type') == link_type and link.get('target') == target and (link.get('project') or ids[0]) == (link_project or ids[0]))]
                link = {'type': link_type, 'target': target}
                if link_project: link['project'] = link_project
                links.append(link)
                expected_revision = expected
                store.record(dict(id='task-link-' + uuid.uuid4().hex, taskId=task_id,
                                  kind='task.updated', title='Связь задач добавлена', patch={'links': links}),
                             expected_revision=expected_revision)
                return self.reply(200, self.task_write_response(store))
            if route == '/api/v1/tasks/primary':
                ids = parse_qs(urlparse(self.path).query).get('project', [])
                if len(ids) != 1 or not ids[0]:
                    raise ValueError('Select an explicit project')
                if not isinstance(body, dict) or set(body) - {'task', 'expected'} or not isinstance(body.get('task'), str):
                    raise ValueError('Invalid primary task fields')
                expected = body.get('expected')
                if not isinstance(expected, str) or not 1 <= len(expected) <= 100:
                    raise ValueError('Invalid plan revision')
                store = self.server.registry.store(ids[0])
                state = store.task_context(body['task'])
                task = next((t for t in state['tasks'] if t['id'] == body['task']), None)
                if not task:
                    raise ValueError('Unknown task')
                if task.get('status') in ('done', 'cancelled'):
                    raise ValueError('Only an unfinished task can be primary')
                event = dict(id='primary-' + uuid.uuid4().hex, taskId=body['task'],
                             kind='task.updated', title='Основная задача выбрана',
                             patch={'primary': {'selected': True, 'project': ids[0]}})
                store.record(event, expected_revision=expected)
                return self.reply(200, self.task_write_response(store))
            if not isinstance(body,dict) or set(body)-{'source','target','task','expected','request'}:
                raise ValueError('Invalid transfer fields')
            for field in ('source','target','task'):
                if not isinstance(body.get(field),str) or not 1<=len(body[field])<=120:raise ValueError('Invalid '+field)
            for field in ('expected','request'):
                if field in body and (not isinstance(body[field],str) or not 1<=len(body[field])<=100):raise ValueError('Invalid '+field)
            if route not in ('/api/v1/tasks/transfer/preview','/api/v1/tasks/transfer'):
                return self.reply(404,dict(error='Not found'))
            from task_transfer import transfer
            result=transfer(self.server.registry,body['source'],body['target'],body['task'],
                            expected=body.get('expected'),request=body.get('request'),
                            actor='local-user',preview=route.endswith('/preview'))
            return self.reply(200,result)
        except SettingsError as error:
            return self.reply(error.status, error.body)
        except (ValueError,KeyError,TypeError,TimeoutError) as error:
            from backup_session import BackupBusy
            if isinstance(error, BackupBusy):
                return self.reply(423, {'error': 'storage_operation_in_progress', 'message': str(error), 'retryable': True})
            if isinstance(getattr(error, 'body', None), dict) and getattr(error, 'status', None) == 409:
                return self.reply(error.status, error.body)
            details = dict(reasonCode=error.reason_code, layer=error.layer,
                           operationId=getattr(error, 'operation_id', None)) if hasattr(error, 'reason_code') else {}
            return self.reply(409,dict(error=str(error), **details))
        except OSError as error:
            return self.reply(503, dict(error='Storage write interrupted; refresh to recover any committed stage transfer', detail=str(error)))

    def stream(self):
        self.server.event_broker.subscribe(self.store)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        revision = None
        pulse = 0
        try:
            while not self.server.stopping.is_set():
                current_revision = self.server.event_state(self.store)
                if current_revision is not None and current_revision != revision:
                    revision = current_revision
                    payload = revision
                    self.wfile.write(f"id: {revision['revision']}:{revision['coordinationRevision']}\nevent: revision\ndata: {json.dumps(payload)}\n\n".encode())
                    self.wfile.flush()
                if time.monotonic() - pulse > 10:
                    self.wfile.write(b": connected\n\n")
                    self.wfile.flush()
                    pulse = time.monotonic()
                self.server.stopping.wait(.4)
        except (ConnectionError, OSError):
            pass
        except (ValueError, TimeoutError):
            # Close instead of displaying stale state as connected. EventSource reconnects.
            pass


def serve_projects(args):
    from project_registry import CodexProjects, ProjectRegistry
    catalog_path = os.environ.get('PROJECT_HUB_ASGI_CATALOG')
    registry = ProjectRegistry(args.projects_home, CodexProjects(catalog_path) if catalog_path else None,
                               standalone=args.standalone)
    registry.refresh()
    dependencies = ROOT / '.local/server-deps'
    if dependencies.is_dir():
        sys.path.insert(0, str(dependencies))
    import importlib.util
    asgi_available = importlib.util.find_spec('uvicorn') is not None
    if args.transport == 'asgi' or (args.transport == 'auto' and asgi_available):
        if not asgi_available:
            raise ValueError('Install requirements-server.txt before selecting ASGI')
        if not 1 <= args.workers <= 32 or not 1 <= args.request_threads <= 32 or not 1 <= args.port <= 65535:
            raise ValueError('ASGI requires 1..32 workers, 1..32 request threads and an explicit TCP port')
        os.environ['PROJECT_HUB_ASGI_HOME'] = str(registry.home)
        os.environ['PROJECT_HUB_STANDALONE'] = '1' if args.standalone else '0'
        os.environ['PROJECT_HUB_ASGI_PORT'] = str(args.port)
        os.environ['PROJECT_HUB_ASGI_REQUEST_THREADS'] = str(args.request_threads)
        # Windows shared listening sockets intermittently fail or stall
        # under concurrent accepts. One I/O loop hands requests directly
        # to independent spawn processes; no internal HTTP proxy is used.
        os.environ['PROJECT_HUB_ASGI_DISPATCH_PROCESSES'] = str(args.workers if os.name == 'nt' and args.workers > 1 else 0)
        import uvicorn
        from hub_lifecycle import shutdown_monitor, control_directory
        if control_directory() is not None:
            # asyncio binds both loopback families for localhost. IPv4-only
            # listening makes IPv6-first clients wait before falling back.
            config = uvicorn.Config('portal_asgi:create_app', factory=True, host='localhost', port=args.port,
                                    limit_concurrency=512, backlog=2048, timeout_graceful_shutdown=30, access_log=False)
            server = uvicorn.Server(config)
            shutdown_monitor(lambda: setattr(server, 'should_exit', True))
            server.run()
        else:
            uvicorn.run('portal_asgi:create_app', factory=True, host='localhost', port=args.port,
                        workers=1 if os.name == 'nt' else args.workers, limit_concurrency=512, backlog=2048,
                        timeout_graceful_shutdown=15, timeout_worker_healthcheck=30, access_log=False)
        return 0
    server = PortalServer(('127.0.0.1', args.port), registry=registry)
    from hub_lifecycle import shutdown_monitor, control_directory
    if control_directory() is not None:
        # Accepted request threads must finish before server_close releases the
        # data-home lifetime lease. SSE readers observe server.stopping.
        server.daemon_threads = False
    def stop():
        server.stopping.set()
        server.shutdown()
    shutdown_monitor(stop)
    print(f'http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv=None):
    from runtime_diagnostics import cleanup, exception
    try:
        return _main(argv)
    except Exception as error:
        exception('server.failed',error)
        raise
    finally:
        cleanup()


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Explicit managed source project (legacy single-project commands)")
    parser.add_argument("--data-dir", type=Path, help="Explicit project state directory outside source checkout")
    parser.add_argument("--coordination-home", type=Path, help="Explicit coordination database directory")
    parser.add_argument("--projects-home", type=Path, help="Enable independent multi-project server with this data directory")
    parser.add_argument('--standalone', action='store_true', help='Use Hub-owned projects; do not discover a host catalog')
    parser.add_argument('--development', action='store_true', help='Explicit isolated headless development/test server')
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8769)
    serve.add_argument('--transport', choices=('auto','asgi','threaded'), default='auto')
    serve.add_argument('--workers', type=int, default=min(4, max(2, (os.cpu_count() or 2) // 2)),
                       help='Fixed ASGI processes (default: CPU-sized, 2..4)')
    serve.add_argument('--request-threads', type=int, default=4,
                       help='Fixed request threads per ASGI read worker (1..32)')
    commands.add_parser("state")
    record = commands.add_parser("record")
    record.add_argument("--file", type=Path, help="UTF-8 JSON event; stdin when omitted")
    run = commands.add_parser("run", help="Record a check and its real exit result")
    run.add_argument("--task", required=True)
    run.add_argument("--stage")
    run.add_argument("--title", required=True)
    run.add_argument("--log", required=True)
    run.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    if args.command == 'serve':
        from runtime_diagnostics import configure, record
        diagnostic_home=os.environ.get('PROJECT_HUB_DIAGNOSTICS_HOME')
        if diagnostic_home is None and args.projects_home is not None:
            diagnostic_home=args.projects_home.parent / (args.projects_home.name+'-diagnostics')
        configure('server',directory=diagnostic_home,codeRoot=str(ROOT),control=os.environ.get('PROJECT_HUB_CONTROL'),
                  mode=os.environ.get('PROJECT_HUB_RUNTIME_MODE','development' if args.development else 'source'),port=args.port)
        record('server.started')
        from hub_lifecycle import control_directory
        if args.development:
            os.environ['PROJECT_HUB_RUNTIME_MODE'] = 'development'
        if control_directory() is None and os.environ.get('PROJECT_HUB_RUNTIME_MODE') != 'development':
            parser.error('Use hub_source.py or hub_launcher.py for the main server; use --development with separate data for a headless test runtime.')
    if args.command == 'serve' and args.root is None and args.data_dir is None and args.projects_home is None:
        from project_registry import default_data_home
        args.projects_home = default_data_home()
    if args.projects_home is None and args.root is None:
        parser.error('Single-project commands require --root and data outside the program directory')
    if args.projects_home:
        if args.command != 'serve':
            parser.error('--projects-home currently supports serve only')
        from hub_lifecycle import home_lease
        with home_lease(args.projects_home):
            expected = os.environ.get('PROJECT_HUB_ACTIVATION_EXPECTED')
            if expected is not None:
                from hub_import import inspect_home
                inspected = inspect_home(args.projects_home)
                if inspected['revision'] != expected:
                    raise ValueError('Copied storage changed before runtime activation')
                schemas = inspected['storageSchemas']
                if schemas['registry'] != 2 or schemas.get('coordination', 2) != 2:
                    raise ValueError('Explicitly upgrade the inactive copy before activation')
            elif args.standalone:
                from storage_preparation import prepare
                prepare(args.projects_home)
            # Bootstrap may prepare schema/read caches behind a durable recovery
            # barrier. Accepted user mutations are guarded in HTTP and MCP.
            from storage_operations import internal
            from types import SimpleNamespace
            with internal(SimpleNamespace(home=Path(args.projects_home).resolve())):
                return serve_projects(args)
    if args.command == 'serve':
        from contextlib import ExitStack
        from hub_lifecycle import home_lease
        with ExitStack() as leases:
            leases.enter_context(home_lease(args.data_dir or Path(args.root) / 'docs/project-portal'))
            if args.coordination_home:
                leases.enter_context(home_lease(args.coordination_home))
            return serve_legacy(args)
    store = Store(args.root, data_dir=args.data_dir, coordination_home=args.coordination_home)
    if args.command == "state":
        print(json.dumps(store.snapshot(), ensure_ascii=False, indent=2))
    elif args.command == "record":
        body = read_json(args.file) if args.file else json.load(sys.stdin)
        print(json.dumps(store.record(body), ensure_ascii=False))
    elif args.command == "run":
        command = args.args[1:] if args.args[:1] == ["--"] else args.args
        if not command:
            parser.error("run needs a command after --")
        log = store.resolve_path(args.log)
        require_external_data(log, store.installation_root)
        log.parent.mkdir(parents=True, exist_ok=True)
        run_id = str(uuid.uuid4())
        base = {"taskId": args.task, "title": args.title, "runId": run_id, "evidence": [{"label": "Журнал проверки", "path": args.log}]}
        if args.stage:
            base["stageId"] = args.stage
        store.record({**base, "kind": "check.started"})
        start = time.monotonic()
        try:
            with open(log, "wb") as output:
                code = subprocess.run(command, cwd=store.root, stdout=output, stderr=subprocess.STDOUT, check=False).returncode
            detail = f"Exit {code}; {time.monotonic() - start:.1f} s"
        except (OSError, KeyboardInterrupt) as error:
            code, detail = 1, str(error) or "Interrupted"
        store.record({**base, "kind": "check.passed" if code == 0 else "check.failed", "detail": detail})
        return code
    return 0


def serve_legacy(args):
    store = Store(args.root, data_dir=args.data_dir, coordination_home=args.coordination_home)
    store.snapshot()
    server = PortalServer(('127.0.0.1', args.port), store)
    print(f'http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, TimeoutError) as error:
        from runtime_diagnostics import exception
        exception('server.failed',error)
        print(str(error), file=sys.stderr)
        sys.exit(1)
