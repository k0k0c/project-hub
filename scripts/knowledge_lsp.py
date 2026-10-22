"""Small, bounded LSP client used by the knowledge architecture provider.

The client deliberately accepts an argv list (never a shell command).  It is
an adapter for configured language servers, rather than an installer or a
language implementation; Java/JDT-LS is one possible external configuration.
"""
from __future__ import annotations

import atexit
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
from typing import Any
from urllib.parse import quote, unquote, urlparse


class LspError(RuntimeError):
    pass


class LspUnsupported(LspError):
    pass


def _uri(path: Path) -> str:
    return path.resolve().as_uri()


def _path_from_uri(value: str) -> Path:
    parsed = urlparse(value)
    if parsed.scheme != "file": return Path(value)
    raw = unquote(parsed.path)
    if parsed.netloc and parsed.netloc not in ("", "localhost"):
        return Path("//" + parsed.netloc + raw)
    # file:///C:/... is represented as /C:/... by urlparse on Windows.
    if len(raw) >= 3 and raw[0] == "/" and raw[2] == ":": raw = raw[1:]
    return Path(raw)


def _position(line: int, column: int) -> dict[str, int]:
    return {"line": max(0, int(line) - 1), "character": max(0, int(column) - 1)}


class LspTransport:
    """Thread-safe JSON-RPC transport with Content-Length framing."""

    def __init__(self, command: list[str], root: Path, timeout: float = 8.0):
        if not isinstance(command, list) or not command or not all(isinstance(x, str) and x for x in command):
            raise LspError("LSP command must be a non-empty argv array")
        self.root, self.timeout = root.resolve(), max(.1, min(120., float(timeout)))
        popen_options = {}
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            popen_options["creationflags"] = subprocess.CREATE_NO_WINDOW
        try:
            self.process = subprocess.Popen(command, cwd=str(self.root), stdin=subprocess.PIPE,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                            bufsize=0, shell=False, **popen_options)
        except OSError as exc:
            raise LspError(f"Unable to start language server: {exc}") from exc
        self._next = 1
        self._pending: dict[int, queue.Queue] = {}
        self._lock = threading.RLock()
        self.operation_lock = threading.RLock()
        self._closed = False
        self.diagnostics: list[dict[str, Any]] = []
        self.document_diagnostics: dict[str, dict[str, Any]] = {}
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        self._stderr_reader = threading.Thread(target=self._read_stderr, daemon=True)
        self._stderr_reader.start()
        self.capabilities: dict[str, Any] = {}

    def _diagnostic(self, value: dict[str, Any]) -> None:
        if isinstance(value.get('uri'),str) and isinstance(value.get('diagnostics'),list):
            self.document_diagnostics[value['uri']]=value
            if len(self.document_diagnostics)>256:
                self.document_diagnostics.pop(next(iter(self.document_diagnostics)))
        self.diagnostics.append(value)
        if len(self.diagnostics) > 100:
            del self.diagnostics[:-100]

    def _read_stderr(self) -> None:
        stream = self.process.stderr
        if stream is None: return
        try:
            for line in iter(stream.readline, b""):
                if line:
                    self._diagnostic({"code": "server-stderr", "message": line.decode("utf-8", "replace")[:500]})
        except Exception as exc:
            self._diagnostic({"code": "stderr", "message": str(exc)[:500]})

    def _send(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        assert self.process.stdin is not None
        self.process.stdin.write(f"Content-Length: {len(data)}\r\n\r\n".encode("ascii") + data)
        self.process.stdin.flush()

    def _read_loop(self) -> None:
        stream = self.process.stdout
        if stream is None:
            return
        try:
            while True:
                headers = b""
                while not headers.endswith(b"\r\n\r\n"):
                    part = stream.read(1)
                    if not part:
                        raise EOFError("language server closed stdout")
                    headers += part
                    if len(headers) > 8192:
                        raise LspError("oversized LSP headers")
                values = {}
                for line in headers[:-4].decode("ascii", "replace").split("\r\n"):
                    if ":" in line:
                        key, value = line.split(":", 1); values[key.lower()] = value.strip()
                length = int(values.get("content-length", "-1"))
                if length < 0 or length > 20_000_000:
                    raise LspError("invalid or oversized LSP message")
                body = bytearray()
                while len(body) < length:
                    part = stream.read(length - len(body))
                    if not part: break
                    body.extend(part)
                if len(body) != length:
                    raise EOFError("truncated LSP message")
                message = json.loads(bytes(body).decode("utf-8"))
                if "id" in message and ("result" in message or "error" in message):
                    waiter = self._pending.get(message["id"])
                    if waiter: waiter.put(message)
                elif "method" in message and "id" in message:
                    method = message["method"]
                    if method == "workspace/configuration":
                        result = [self._settings_for(item) for item in (message.get("params", {}).get("items") or [])]
                    elif method == "workspace/applyEdit":
                        result = {"applied": False}
                    else:
                        result = None
                    with self._lock:
                        if not self._closed:
                            self._send({"jsonrpc": "2.0", "id": message["id"], "result": result})
                elif message.get("method") == "textDocument/publishDiagnostics":
                    self._diagnostic(message.get("params", {}))
        except Exception as exc:
            self._diagnostic({"code": "transport", "message": str(exc)[:500]})
        finally:
            error = {"error": {"code": -32099, "message": "language server stopped"}}
            for waiter in list(self._pending.values()):
                try: waiter.put_nowait(error)
                except queue.Full: pass

    def _settings_for(self, item: Any) -> Any:
        settings = getattr(self, "settings", {})
        if not isinstance(settings, dict) or not isinstance(item, dict): return None
        section = item.get("section")
        if not isinstance(section, str) or not section: return settings
        value: Any = settings
        for part in section.split("."):
            if not isinstance(value, dict): return None
            value = value.get(part)
        return value

    def request(self, method: str, params: Any = None, timeout: float | None = None, on_cancel=None, cancelled=None) -> Any:
        with self._lock:
            if self._closed: raise LspError("language server is closed")
            ident = self._next; self._next += 1
            waiter: queue.Queue = queue.Queue(1); self._pending[ident] = waiter
            try: self._send({"jsonrpc": "2.0", "id": ident, "method": method, "params": params})
            except Exception:
                self._pending.pop(ident, None); raise
        deadline = time.monotonic() + (self.timeout if timeout is None else max(.1, timeout))
        while True:
            if cancelled is not None and cancelled():
                self._pending.pop(ident, None)
                try: self.notify("$/cancelRequest", {"id": ident})
                except Exception: pass
                if on_cancel is not None:
                    try: on_cancel(ident, method)
                    except Exception: pass
                raise LspError(f"LSP request cancelled: {method}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._pending.pop(ident, None)
                try: self.notify("$/cancelRequest", {"id": ident})
                except Exception: pass
                if on_cancel is not None:
                    try: on_cancel(ident, method)
                    except Exception: pass
                raise LspError(f"LSP request timed out: {method}")
            try:
                message = waiter.get(timeout=min(.1, remaining))
                break
            except queue.Empty:
                continue
        self._pending.pop(ident, None)
        if "error" in message:
            error = message["error"]
            if error.get("code") == -32601:
                raise LspUnsupported(f"LSP method is unsupported: {method}")
            raise LspError(f"LSP {method} failed: {error}")
        return message.get("result")

    def notify(self, method: str, params: Any = None) -> None:
        with self._lock:
            if not self._closed: self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def close(self) -> None:
        with self._lock:
            if self._closed: return
            self._closed = True
            try: self._send({"jsonrpc": "2.0", "method": "shutdown", "id": self._next})
            except Exception: pass
            try: self.process.stdin.close()  # type: ignore[union-attr]
            except Exception: pass
        try: self.process.wait(timeout=.5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try: self.process.wait(timeout=.5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                try: self.process.wait(timeout=.5)
                except subprocess.TimeoutExpired: pass
        # Leave stdout/stderr for the daemon readers to observe EOF. Closing a
        # pipe while a platform reader is blocked can itself deadlock shutdown.


class LspManager:
    OPERATIONS = {"symbols", "definition", "references", "incoming-calls", "outgoing-calls", "base-types", "implementations"}

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout; self._servers: dict[str, LspTransport] = {}; self._lock = threading.RLock()

    def _server(self, root: Path, config: dict[str, Any]) -> LspTransport:
        root = root.resolve()
        command = config.get("command")
        key = hashlib.sha256(json.dumps([str(root), config], sort_keys=True, default=str).encode()).hexdigest()
        with self._lock:
            existing = self._servers.get(key)
            if existing is not None:
                if existing.process.poll() is None and not existing._closed: return existing
                self._servers.pop(key, None)
                existing.close()
            server = LspTransport(command, root, config.get("timeout", self.timeout))
            languages = config.get("languages", {})
            server.settings = config.get("settings", {})
            init = {"processId": os.getpid(), "rootUri": _uri(root), "workspaceFolders": [{"uri": _uri(root), "name": root.name}],
                    "capabilities": {"workspace": {"workspaceFolders": True}, "textDocument": {"documentSymbol": {"hierarchicalDocumentSymbolSupport": True}, "definition": {}, "references": {}, "typeHierarchy": {}, "callHierarchy": {}}},
                    "initializationOptions": config.get("initializationOptions", {}), "clientInfo": {"name": "project-hub-knowledge"}}
            try:
                initialized = server.request("initialize", init) or {}
            except Exception:
                server.close()
                raise
            server.capabilities = initialized.get("capabilities", {}) if isinstance(initialized, dict) else {}
            server.notify("initialized", {})
            server._languages = languages
            self._servers[key] = server
            return server

    def _document(self, server: LspTransport, root: Path, path: str) -> tuple[str, dict[str, Any]]:
        with server.operation_lock:
            if str(path).startswith("file:"):
                candidate = _path_from_uri(str(path)).resolve()
            else:
                candidate = (root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
            if not candidate.is_relative_to(root): raise LspError("source path is outside the registered root")
            if not candidate.is_file(): raise LspError("source file does not exist")
            text = candidate.read_text(encoding="utf-8-sig")
            uri = _uri(candidate)
            language_config = getattr(server, "_languages", {})
            extension=candidate.suffix.lower().lstrip(".")
            language = (language_config.get(extension, extension) if isinstance(language_config, dict) else
                        {'py':'python','js':'javascript','mjs':'javascript','jsx':'javascriptreact','ts':'typescript','tsx':'typescriptreact','cc':'cpp','h':'cpp','rs':'rust','kt':'kotlin'}.get(extension,extension))
            versions = getattr(server, "_versions", {}); old = versions.get(uri)
            version = (old[0] + 1) if old else 1; versions[uri] = (version, text); server._versions = versions
            if old is None: server.notify("textDocument/didOpen", {"textDocument": {"uri": uri, "languageId": language, "version": version, "text": text}})
            elif old[1] != text: server.notify("textDocument/didChange", {"textDocument": {"uri": uri, "version": version}, "contentChanges": [{"text": text}]})
            return uri, {"uri": uri, "languageId": language, "version": version, "text": text}

    @staticmethod
    def _items(value: Any) -> list[Any]:
        if value is None: return []
        return value if isinstance(value, list) else [value]

    @staticmethod
    def _supports(capabilities: dict[str, Any], operation: str) -> bool:
        key = {"symbols": "documentSymbolProvider", "definition": "definitionProvider",
               "references": "referencesProvider", "implementations": "implementationProvider",
               "incoming-calls": "callHierarchyProvider", "outgoing-calls": "callHierarchyProvider",
               "base-types": "typeHierarchyProvider"}[operation]
        value = capabilities.get(key)
        return value is True or isinstance(value, dict)

    @staticmethod
    def _range_contains(outer: dict[str, Any], inner: dict[str, Any]) -> bool:
        def point(value):
            p = value or {}
            return (int(p.get("line", 0)), int(p.get("character", 0)))
        a, b = point(outer.get("start")), point(outer.get("end"))
        c, d = point(inner.get("start")), point(inner.get("end"))
        return a <= c and d <= b

    def _repair_call_ranges(self, server, root, items, diagnostics, timeout, cancelled):
        """Resolve callable declaration selections without changing call-site evidence."""
        cache = {}
        def symbols(uri):
            if uri in cache: return cache[uri]
            try:
                candidate = _path_from_uri(uri).resolve()
                if not candidate.is_relative_to(root) or not candidate.is_file():
                    diagnostics.append({"code": "call-selection-unresolved", "uri": uri, "message": "Source is outside the registered root"})
                    cache[uri] = []
                    return []
                value = server.request("textDocument/documentSymbol", {"textDocument": {"uri": uri}}, timeout=timeout, cancelled=cancelled)
                flattened = []
                def visit(nodes):
                    for node in self._items(nodes):
                        if not isinstance(node, dict): continue
                        flattened.append(node)
                        visit(node.get("children", []))
                visit(value)
                cache[uri] = flattened
                return flattened
            except Exception as exc:
                diagnostics.append({"code": "call-selection-unresolved", "uri": uri, "message": str(exc)[:300]})
                cache[uri] = []
                return []
        for entry in self._items(items):
            if not isinstance(entry, dict): continue
            for field in ("from", "to"):
                callable_item = entry.get(field)
                if not isinstance(callable_item, dict): continue
                uri = callable_item.get("uri")
                call_range = callable_item.get("range")
                name = callable_item.get("name", "")
                if not isinstance(uri, str) or not isinstance(call_range, dict): continue
                base_name = name.split(" : ", 1)[0].strip() if isinstance(name, str) else ""
                candidates = [symbol for symbol in symbols(uri)
                              if isinstance(symbol.get("name"), str) and symbol["name"] == base_name
                              and isinstance(symbol.get("range"), dict)
                              and self._range_contains(symbol["range"], call_range)]
                if not candidates:
                    diagnostics.append({"code": "call-selection-unresolved", "uri": uri,
                                         "name": name, "message": "No enclosing declaration symbol matched"})
                    continue
                symbol = min(candidates, key=lambda value: (
                    int(value.get("range", {}).get("end", {}).get("line", 0)) - int(value.get("range", {}).get("start", {}).get("line", 0)),
                    int(value.get("range", {}).get("end", {}).get("character", 0)) - int(value.get("range", {}).get("start", {}).get("character", 0))))
                selection = symbol.get("selectionRange")
                if isinstance(selection, dict):
                    callable_item["selectionRange"] = selection

    def _query_impl(self, root: Path, config: dict[str, Any], operation: str, path: str, line: int = 1, column: int = 1, timeout: float | None = None, cancelled=None) -> dict[str, Any]:
        result = {"capabilities": {}, "results": [], "status": "error", "diagnostics": []}
        if operation not in self.OPERATIONS: result.update(status="unsupported", diagnostics=[{"code": "unsupported-operation"}]); return result
        try:
            root = Path(root).resolve(); server = self._server(root, config); result["capabilities"] = server.capabilities
            if not self._supports(server.capabilities, operation):
                result.update(status="unsupported", diagnostics=[{"code": "unsupported-capability", "operation": operation}])
                return result
            uri, doc = self._document(server, root, path); pos = _position(line, column)
            def request(method, params):
                return server.request(method, params, timeout=timeout, cancelled=cancelled)
            td = {"textDocument": {"uri": uri}, "position": pos}
            methods = {"symbols": ("textDocument/documentSymbol", {"textDocument": {"uri": uri}}), "definition": ("textDocument/definition", td), "references": ("textDocument/references", {**td, "context": {"includeDeclaration": True}}), "implementations": ("textDocument/implementation", td)}
            if operation in methods: value = request(*methods[operation])
            else:
                prep = request("textDocument/prepareCallHierarchy" if "calls" in operation else "textDocument/prepareTypeHierarchy", td)
                items = self._items(prep)
                if not items: value = []
                else:
                    method = {"incoming-calls": "callHierarchy/incomingCalls", "outgoing-calls": "callHierarchy/outgoingCalls", "base-types": "typeHierarchy/supertypes"}[operation]
                    value = []
                    for item in items:
                        value.extend(self._items(request(method, {"item": item})))
            result["results"] = self._items(value)
            if operation in {"incoming-calls", "outgoing-calls"} and self._supports(server.capabilities, "symbols"):
                self._repair_call_ranges(server, root, result["results"], result["diagnostics"], timeout, cancelled)
            result["status"] = "ok" if result["results"] else "empty"
            current=server.document_diagnostics.get(uri,{})
            problems=current.get('diagnostics',[])
            if operation!='symbols' and any(d.get('severity')==1 or any(text in str(d.get('message','')).lower() for text in ('non-project file','only syntax errors','not indexed','project is not loaded')) for d in problems):
                result['status']='partial'
                result['diagnostics'].append({'code':'semantic-incomplete','message':'Сервер не подтвердил полный семантический анализ этого файла. Пустой результат не доказывает отсутствие связей.','uri':uri,'diagnostics':problems})
        except LspUnsupported as exc:
            result["status"] = "unsupported"; result["diagnostics"] = [{"code": "unsupported", "message": str(exc)[:500]}]
        except Exception as exc:
            result["diagnostics"] = [{"code": "lsp-error", "message": str(exc)[:500]}]
        if 'server' in locals():
            result["diagnostics"].extend([d for d in server.diagnostics[-20:] if not d.get('uri')])
            if 'uri' in locals() and server.document_diagnostics.get(uri):result['diagnostics'].append(server.document_diagnostics[uri])
        return result

    def query(self, root: Path, config: dict[str, Any], operation: str, path: str, line: int = 1, column: int = 1, timeout: float | None = None, cancelled=None) -> dict[str, Any]:
        # A single server must see didChange and the corresponding request as
        # one transaction; otherwise concurrent callers can observe stale text.
        if operation not in self.OPERATIONS:
            return {'capabilities':{},'results':[],'status':'unsupported','diagnostics':[{'code':'unsupported-operation'}]}
        root = Path(root).resolve()
        server = None
        try:
            server = self._server(root, config)
            with server.operation_lock:
                return self._query_impl(root, config, operation, path, line, column, timeout, cancelled)
        except Exception as exc:
            return {"capabilities": {}, "results": [], "status": "error",
                    "diagnostics": [{"code": "lsp-init", "message": str(exc)[:500]}]}
        finally:
            if server is not None and server.process.poll() is not None:
                key = hashlib.sha256(json.dumps([str(root), config], sort_keys=True, default=str).encode()).hexdigest()
                with self._lock:
                    if self._servers.get(key) is server: self._servers.pop(key, None)

    def close(self) -> None:
        with self._lock:
            servers = list(self._servers.values()); self._servers.clear()
        for server in servers: server.close()


KnowledgeLspManager = LspManager
LspProvider = LspManager
KnowledgeLspProvider = LspManager
manager = LspManager()
atexit.register(manager.close)
