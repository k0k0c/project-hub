"""Owned Codex app-server stdio client; mutations require an explicit caller action.

This module never attaches to the desktop process or changes Codex configuration.
Keep the adapter alive until the accepted turn finishes or needs user attention.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
from typing import Any


class CodexAdapterError(RuntimeError):
    def __init__(self, message: str, *, outcome_unknown: bool = False,
                 thread_id: str | None = None, code: str | None = None):
        super().__init__(message)
        self.outcome_unknown = outcome_unknown
        self.thread_id = thread_id
        self.code = code


class CodexAdapter:
    """One owned server, serial operations, bounded replies and event buffering.

    allowed_threads maps explicitly Hub-owned thread IDs to project directories.
    resume_guard must acquire/verify a caller-side exclusive idle lease; the
    native status from this new server cannot prove another client is idle.
    executable may be an argv prefix (useful for isolated fake-child tests).
    """
    def __init__(self, executable: str | Sequence[str] | None = None, *,
                 timeout: float = 15.0,
                 allowed_threads: Mapping[str, str] | None = None,
                 resume_guard: Callable[[str], bool] | None = None):
        if timeout <= 0 or timeout > 120:
            raise ValueError("timeout must be in (0, 120] seconds")
        resolved = executable or self.resolve_executable()
        self.command = ([resolved] if isinstance(resolved, str) else list(resolved or []))
        self.timeout = timeout
        self.allowed_threads = dict(allowed_threads or {})
        # Presence in the caller's ownership mapping is not runtime loading
        # evidence. Only successful native create/resume establishes this set.
        self._loaded_threads: set[str] = set()
        self._collaboration_settings: dict[str, dict] = {}
        self.resume_guard = resume_guard
        self._process: subprocess.Popen | None = None
        self._operation = threading.RLock()
        self._condition = threading.Condition()
        self._pending: dict[int, queue.Queue] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=512)
        self._completions: deque[dict[str, Any]] = deque(maxlen=32)
        self._attention: dict[Any, dict] = {}
        self._stream_ended = False
        self._dropped = 0
        self._next_id = 0
        self._readers: list[threading.Thread] = []
        self._writer: threading.Thread | None = None
        self._write_pending = False
        self._active: tuple[str, str] | None = None
        self._closed = False
        self._uncertain = False

    @staticmethod
    def resolve_executable() -> str | None:
        """Prefer PATH, then the current user's installed Windows desktop CLI.

        Task Scheduler does not inherit Codex's per-session PATH injection.
        Inspect only the application's versioned bin directory, never sessions,
        credentials, projects or arbitrary downloaded executables.
        """
        resolved = shutil.which("codex")
        if resolved:
            return resolved
        local = os.environ.get("LOCALAPPDATA") if os.name == "nt" else None
        if not local:
            return None
        try:
            directory = Path(local) / "OpenAI" / "Codex" / "bin"
            candidates = [p for p in directory.glob("*/codex.exe") if p.is_file()]
            return str(max(candidates, key=lambda p: (p.stat().st_mtime_ns, str(p)))) if candidates else None
        except OSError:
            return None

    @staticmethod
    def _cwd(cwd: str) -> str:
        path = Path(cwd).resolve(strict=True)
        if not path.is_dir():
            raise ValueError("cwd must be an existing directory")
        return str(path)

    @staticmethod
    def _same_cwd(left: str, right: str) -> bool:
        return os.path.normcase(os.path.realpath(left)) == os.path.normcase(os.path.realpath(right))

    def _open(self) -> None:
        if self._closed:
            raise CodexAdapterError("adapter is closed")
        if self._process is not None:
            if self._process.poll() is not None:
                with self._condition:
                    self._loaded_threads.clear()
                raise CodexAdapterError("app-server exited")
            return
        if not self.command:
            raise CodexAdapterError("Codex executable unavailable", code="codex_not_found")
        try:
            self._process = subprocess.Popen(
                self.command + ["app-server"], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except OSError as exc:
            raise CodexAdapterError("cannot launch Codex app-server", code="codex_launch_failed") from exc
        for target in (self._read_stdout, self._drain_stderr):
            reader = threading.Thread(target=target, daemon=True)
            self._readers.append(reader)
            reader.start()
        try:
            self._request("initialize", {"clientInfo": {
                "name": "project_hub", "title": "Project Hub", "version": "0.1.0"},
                "capabilities": {"experimentalApi": True}})
            self._send({"method": "initialized", "params": {}})
        except Exception:
            self.close()
            raise

    def _abort_io(self) -> None:
        """Unblock a wedged pipe by stopping only this adapter's own child."""
        self._closed = True
        self._uncertain = True
        with self._condition:
            self._loaded_threads.clear()
        process = self._process
        if process is not None and process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                pass

    def _send(self, message: dict, *, deadline: float | None = None) -> None:
        assert self._process is not None and self._process.stdin is not None
        if self._closed:
            raise CodexAdapterError("adapter is closed", outcome_unknown=self._uncertain)
        deadline = deadline if deadline is not None else time.monotonic() + self.timeout
        done: queue.Queue = queue.Queue(maxsize=1)
        stream = self._process.stdin

        def write():
            failure = None
            try:
                stream.write(json.dumps(message, ensure_ascii=False) + "\n")
                stream.flush()
            except BaseException as exc:
                failure = exc
            finally:
                # Clear before publishing completion: close must not mistake a
                # finished write for a blocked writer still exiting its thread.
                self._write_pending = False
                done.put(failure)

        self._write_pending = True
        self._writer = threading.Thread(target=write, name="codex-stdio-write", daemon=True)
        self._writer.start()
        try:
            failure = done.get(timeout=max(0, deadline - time.monotonic()))
        except queue.Empty as exc:
            # Closing a buffered stream first can itself wait for its writer
            # lock forever. Kill first so the blocked write gets a broken pipe.
            self._abort_io()
            self._writer.join(timeout=0.25)
            raise CodexAdapterError("app-server write timed out; outcome unknown", outcome_unknown=True) from exc
        if isinstance(failure, (OSError, ValueError)):
            with self._condition:
                self._loaded_threads.clear()
            raise CodexAdapterError("app-server connection closed", outcome_unknown=True) from failure
        if failure is not None:
            raise failure

    def _read_stdout(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            for line in self._process.stdout:
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("non-object message")
                except ValueError:
                    break
                with self._condition:
                    # Server requests also have an id: only result/error replies
                    # may satisfy a pending client request with the same id.
                    if "method" not in message and ("result" in message or "error" in message):
                        waiter = self._pending.get(message.get("id"))
                        if waiter is not None:
                            waiter.put(message)
                    else:
                        if message.get("method") == "turn/completed":
                            self._completions.append(message)
                        if "id" in message and "method" in message:
                            if len(self._attention) >= 64 and message["id"] not in self._attention:
                                self._attention.pop(next(iter(self._attention)))
                                self._dropped += 1
                            self._attention[message["id"]] = message
                        if message.get("method") == "serverRequest/resolved":
                            self._attention.pop(message.get("params", {}).get("requestId"), None)
                        if len(self._events) == self._events.maxlen:
                            self._dropped += 1
                        self._events.append(message)
                        self._condition.notify_all()
        finally:
            with self._condition:
                self._stream_ended = True
                self._loaded_threads.clear()
                for waiter in self._pending.values():
                    waiter.put({"error": {"message": "app-server stream ended"}})
                self._condition.notify_all()

    def _drain_stderr(self) -> None:
        # Drain without retaining potentially sensitive native diagnostics.
        assert self._process is not None and self._process.stderr is not None
        for _ in self._process.stderr:
            pass

    def _request(self, method: str, params: dict) -> dict:
        with self._operation:
            deadline = time.monotonic() + self.timeout
            self._next_id += 1
            request_id = self._next_id
            waiter: queue.Queue = queue.Queue()
            with self._condition:
                self._pending[request_id] = waiter
            try:
                self._send({"id": request_id, "method": method, "params": params}, deadline=deadline)
                try:
                    reply = waiter.get(timeout=max(0, deadline - time.monotonic()))
                except queue.Empty as exc:
                    self._abort_io()
                    raise CodexAdapterError(f"{method} timed out; outcome unknown",
                                            outcome_unknown=True) from exc
                if "error" in reply:
                    # Native error details may contain paths/prompts; callers
                    # receive a stable failure rather than an automatic retry.
                    code = reply["error"].get("code", "disconnected")
                    raise CodexAdapterError(f"{method} failed ({code})",
                                            outcome_unknown=code == "disconnected")
                result = reply.get("result")
                if not isinstance(result, dict):
                    raise CodexAdapterError(f"{method} returned invalid result", outcome_unknown=True)
                return result
            finally:
                with self._condition:
                    self._pending.pop(request_id, None)

    def probe(self) -> dict:
        """Read-only version/handshake probe; no thread or model request."""
        base = {"available": False, "version": None, "transport": "stdio",
                "desktopAttachment": "unverified", "authentication": "unverified",
                "permissions": "native-defaults", "capabilities": {
                    "initialize": "unverified", "threadStart": "documented",
                    "threadResume": "documented-guarded", "turnStart": "documented",
                    "approvalUi": "unsupported", "steer": "unsupported"}}
        with self._operation:
            try:
                if not self.command:
                    raise CodexAdapterError("Codex executable unavailable")
                version = subprocess.run(self.command + ["--version"], capture_output=True,
                                         text=True, timeout=self.timeout,
                                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if version.returncode != 0:
                    raise CodexAdapterError("Codex version command failed")
                base["version"] = version.stdout.strip()[:200]
                self._open()
                base["available"] = True
                base["capabilities"]["initialize"] = "verified"
            except (CodexAdapterError, OSError, subprocess.TimeoutExpired) as exc:
                base["reason"] = str(exc) if isinstance(exc, CodexAdapterError) else "Codex probe failed"
        return base

    def models(self) -> dict:
        """Read the native account's model catalog without starting a turn."""
        with self._operation:
            self._open()
            result = self._request('model/list', {'limit': 100, 'includeHidden': False})
            rows = result.get('data', [])
            return {'models': [{'id': row['id'], 'displayName': row.get('displayName') or row['id']}
                               for row in rows if isinstance(row, dict) and isinstance(row.get('id'), str)],
                    'more': bool(result.get('nextCursor'))}

    def create_thread(self, cwd: str, *, model: str | None = None) -> dict:
        """Explicit mutation; creates a native thread without model generation."""
        with self._operation:
            cwd = self._cwd(cwd)
            if self._uncertain:
                raise CodexAdapterError("prior mutation outcome requires reconciliation", outcome_unknown=True)
            self._open()
            try:
                result = self._request("thread/start", {"cwd": cwd, **({'model': model} if model else {})})
            except CodexAdapterError as exc:
                self._uncertain = exc.outcome_unknown
                raise
            thread_id = result.get("thread", {}).get("id")
            if not isinstance(thread_id, str) or not thread_id:
                self._uncertain = True
                raise CodexAdapterError("thread/start returned no thread id", outcome_unknown=True)
            self.allowed_threads[thread_id] = cwd
            self._remember_settings(thread_id, result)
            with self._condition:
                if not self._stream_ended and not self._closed:
                    self._loaded_threads.add(thread_id)
            return {"threadId": thread_id, "cwd": cwd, "status": "created",
                    "model": result.get('model', result.get('thread', {}).get('model')),
                    "desktopAttachment": "unverified"}

    def _remember_settings(self, thread_id: str, result: dict) -> None:
        """Retain native configuration; never select a different model by guess."""
        thread = result.get('thread', {})
        model = result.get('model', thread.get('model'))
        effort = result.get('reasoningEffort', thread.get('reasoningEffort'))
        if isinstance(model, str) and model.strip() and (effort is None or effort in
                ('none', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max', 'ultra')):
            self._collaboration_settings[thread_id] = dict(model=model, reasoning_effort=effort,
                                                         developer_instructions=None)

    def skills(self, cwds: Sequence[str]) -> dict:
        """Read native skill discovery for explicit directories; no model turn."""
        if isinstance(cwds, (str, bytes)) or not cwds:
            raise ValueError("cwds must be a nonempty sequence of directories")
        directories = [self._cwd(cwd) for cwd in cwds]
        with self._operation:
            self._open()
            return self._request("skills/list", {"cwds": directories, "forceReload": True})

    def thread_read(self, thread_id: str) -> dict:
        """Read the summary of an explicitly owned thread without resuming it."""
        with self._operation:
            if thread_id not in self.allowed_threads:
                raise CodexAdapterError("thread is not Hub-owned")
            self._open()
            return self._request("thread/read", {"threadId": thread_id, "includeTurns": False})

    def start(self, cwd: str, prompt: str, thread_id: str | None = None, *, collaboration_mode: str | None = None) -> dict:
        """Explicit launch/resume. Success means accepted, not completed."""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be nonempty text")
        if collaboration_mode not in (None, 'plan', 'default'):
            raise ValueError('collaboration_mode must be plan or default')
        with self._operation:
            cwd = self._cwd(cwd)
            if self._uncertain:
                raise CodexAdapterError("prior mutation outcome requires reconciliation", outcome_unknown=True)
            if self._active is not None:
                raise CodexAdapterError("adapter already owns an unfinished turn")
            if thread_id is None:
                thread_id = self.create_thread(cwd)["threadId"]
            else:
                allowed = self.allowed_threads.get(thread_id)
                if not allowed or not self._same_cwd(allowed, cwd):
                    raise CodexAdapterError("thread is not Hub-owned in the requested project")
                if self.resume_guard is None or not self.resume_guard(thread_id):
                    raise CodexAdapterError("resume requires exclusive external idle evidence")
                self._open()
                try:
                    read = self._request("thread/read", {"threadId": thread_id, "includeTurns": False})
                except CodexAdapterError as exc:
                    # The thread was already verified as Hub-owned. Preserve
                    # that identity when native read fails before turn/start.
                    self._uncertain = exc.outcome_unknown
                    exc.thread_id = thread_id
                    raise
                self._remember_settings(thread_id, read)
                thread = read.get('thread', {})
                status = thread.get("status", {}).get("type")
                if (thread.get("id") != thread_id or not isinstance(thread.get("cwd"), str)
                        or not self._same_cwd(thread["cwd"], cwd)
                        or status not in ("idle", "notLoaded")):
                    raise CodexAdapterError("native thread project/status does not permit resume")
                with self._condition:
                    loaded_here = thread_id in self._loaded_threads
                if not loaded_here:
                    try:
                        resumed = self._request("thread/resume", {"threadId": thread_id})
                        self._remember_settings(thread_id, resumed)
                    except CodexAdapterError as exc:
                        self._uncertain = exc.outcome_unknown
                        exc.thread_id = thread_id
                        raise
                    with self._condition:
                        if not self._stream_ended and not self._closed:
                            self._loaded_threads.add(thread_id)
            try:
                params = {"threadId": thread_id, "input": [{"type": "text", "text": prompt}]}
                if collaboration_mode is not None:
                    settings = self._collaboration_settings.get(thread_id)
                    if settings is None:
                        raise CodexAdapterError('Native collaboration settings unavailable; requested mode cannot be verified')
                    params['collaborationMode'] = dict(mode=collaboration_mode, settings=dict(settings))
                result = self._request("turn/start", params)
                turn_id = result.get("turn", {}).get("id")
                if not isinstance(turn_id, str) or not turn_id:
                    raise CodexAdapterError("turn/start returned no turn id", outcome_unknown=True)
            except CodexAdapterError as exc:
                self._uncertain = exc.outcome_unknown
                exc.thread_id = thread_id
                raise
            self._active = (thread_id, turn_id)
            return {"threadId": thread_id, "turnId": turn_id, "status": "accepted",
                    "desktopAttachment": "unverified"}

    def respond_user_input(self, request_id, answers: dict) -> None:
        """Reply only to an owned native question; approval methods stay untouched."""
        with self._operation:
            with self._condition:
                request = self._attention.get(request_id)
                if not request or request.get('method') != 'item/tool/requestUserInput' or self._active is None:
                    raise CodexAdapterError('No matching owned user-input request')
                params = request.get('params', {})
                if (params.get('threadId'), params.get('turnId')) != self._active:
                    raise CodexAdapterError('User-input request belongs to another turn')
                questions = params.get('questions')
                if not isinstance(questions, list) or not 1 <= len(questions) <= 3:
                    raise CodexAdapterError('Unsupported user-input questions')
                ids = [question.get('id') for question in questions if isinstance(question, dict)]
                if len(ids) != len(questions) or len(set(ids)) != len(ids) or not all(isinstance(value, str) for value in ids):
                    raise CodexAdapterError('Invalid question identity')
                if not isinstance(answers, dict) or set(answers) != set(ids):
                    raise ValueError('Answer every question in this request')
                for values in answers.values():
                    if (not isinstance(values, list) or not 1 <= len(values) <= 10 or
                            any(not isinstance(value, str) or not value.strip() or len(value) > 4000 for value in values)):
                        raise ValueError('Use bounded nonempty answer lists')
                response = {'answers': {key: {'answers': values} for key, values in answers.items()}}
                if len(json.dumps(response).encode('utf-8')) > 12000:
                    raise ValueError('Answers exceed request budget')
            self._send({'id': request_id, 'result': response})
            with self._condition:
                self._attention.pop(request_id, None)
                self._condition.notify_all()

    def events(self) -> dict:
        """Drain bounded raw protocol events for the owning controller only."""
        with self._condition:
            result = {"events": list(self._events), "dropped": self._dropped}
            self._events.clear()
            self._dropped = 0
            return result

    def wait_turn(self, timeout: float = 0) -> dict:
        """Bounded wait; approvals are attention, never auto-approved."""
        if timeout < 0 or timeout > 60:
            raise ValueError("wait timeout must be in [0, 60] seconds")
        deadline = time.monotonic() + timeout
        with self._condition:
            if self._active is None:
                raise CodexAdapterError("no owned turn")
            thread_id, turn_id = self._active
            while True:
                for event in self._completions:
                    params = event.get("params", {})
                    if event.get("method") == "turn/completed" and params.get("threadId") == thread_id:
                        turn = params.get("turn", {})
                        if turn.get("id") == turn_id:
                            self._active = None
                            return {"threadId": thread_id, "turnId": turn_id,
                                    "status": turn.get("status", "unknown"), "turn": turn}
                attention = [value for value in self._attention.values() if
                             (value.get('params', {}).get('threadId'), value.get('params', {}).get('turnId')) == self._active]
                if attention:
                    request = next((value for value in attention if value.get('method') == 'item/tool/requestUserInput'), attention[0])
                    return {"threadId": thread_id, "turnId": turn_id,
                            "status": "needs-attention", "request": request}
                if self._stream_ended or self._process is None or self._process.poll() is not None:
                    raise CodexAdapterError("app-server exited during turn", outcome_unknown=True,
                                            thread_id=thread_id)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {"threadId": thread_id, "turnId": turn_id, "status": "running"}
                self._condition.wait(min(remaining, 0.25))

    def close(self) -> None:
        """Close only the owned process; never target other Codex processes."""
        with self._operation:
            self._closed = True
            with self._condition:
                self._loaded_threads.clear()
            process = self._process
            if process is None:
                return
            if self._write_pending:
                self._abort_io()
            if self._writer is not None:
                self._writer.join(timeout=0.25)
            if process.stdin is not None and not self._write_pending:
                try:
                    process.stdin.close()
                except OSError:
                    pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            for reader in self._readers:
                reader.join(timeout=1)
            for reader, stream in zip(self._readers, (process.stdout, process.stderr)):
                # A surviving inherited pipe can leave a daemon reader blocked.
                # Do not block close on that buffered stream's reader lock.
                if stream is not None and not reader.is_alive():
                    stream.close()

    def __enter__(self) -> "CodexAdapter":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
