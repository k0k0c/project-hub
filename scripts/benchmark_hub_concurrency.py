"""Bounded HTTP concurrency benchmark over disposable synthetic Project Hub data.

The benchmark never discovers or writes a real project.  It creates a temporary
registry, project root, baseline, journal and source corpus, then removes them
with the temporary directory.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import http.client
import json
import math
import os
from pathlib import Path
import socket
import sqlite3
import signal
import statistics
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import zlib
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from project_portal import PortalServer
from project_registry import CodexProjects, ProjectRegistry


def traced_app():
    """Benchmark-only ASGI factory with periodic worker stack dumps."""
    import faulthandler
    from portal_asgi import create_app
    target = os.environ.get("PROJECT_HUB_TRACE_LOG")
    worker_target = f"{target}.workers.{os.getpid()}.log" if target else None
    stream = open(worker_target, "a", encoding="utf-8", buffering=1) if worker_target else None
    faulthandler.dump_traceback_later(3, repeat=True, file=stream)
    return create_app()


def generated_png(width=1600, height=900):
    rows = [b"\x00" + b"".join(bytes((x * 255 // max(1, width - 1), y * 255 // max(1, height - 1), 96))
                                      for x in range(width)) for y in range(height)]
    def chunk(kind, payload):
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))]


def stats(samples, started, payloads, errors, server_timings, error_samples=None):
    values = [item[0] for item in samples]
    elapsed = max(time.perf_counter() - started, 1e-9)
    phases = {}
    for header in server_timings:
        for item in header.split(','):
            name, separator, duration = item.strip().partition(';dur=')
            if separator:
                try:
                    phases.setdefault(name, []).append(float(duration))
                except ValueError:
                    pass
    return dict(samples=len(values), p50Ms=percentile(values, .50) if values else None,
                p95Ms=percentile(values, .95) if values else None,
                p99Ms=percentile(values, .99) if values else None,
                maxMs=max(values) if values else None, throughputPerSec=len(values) / elapsed,
                errors=errors, payloadBytes=dict(p50=percentile(payloads, .50) if payloads else None,
                                                  max=max(payloads) if payloads else None),
                serverTimingSamples=server_timings[:20],
                serverTimingPhases={name: dict(samples=len(rows), p50Ms=percentile(rows,.5),
                    p95Ms=percentile(rows,.95), totalMs=sum(rows)) for name,rows in sorted(phases.items())},
                slowServerTimingSamples=[dict(latencyMs=round(sample[0],2),timing=timing)
                    for sample,timing in sorted(zip(samples,server_timings),key=lambda item:item[0][0],reverse=True)[:10]],
                errorSamples=(error_samples or [])[:5])


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def write_fixture(base):
    project = base / "project"
    project.mkdir()
    source_dir = project / "bench"
    source_dir.mkdir()
    text = ("Synthetic benchmark text. " * 2400).encode()[:57_000]
    small = ("Small synthetic source. " * 300).encode()[:4_600]
    (source_dir / "text.txt").write_bytes(text)
    (source_dir / "small.txt").write_bytes(small)
    (source_dir / "image.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" width="2" height="2"><rect width="2" height="2" fill="red"/></svg>')
    png = generated_png()
    (source_dir / "image.png").write_bytes(png)
    for index in range(91):
        (source_dir / f"source-{index:02d}.txt").write_text("synthetic source\n")
    sources = [dict(label="57KB text", path="bench/text.txt"), dict(label="4.6KB text", path="bench/small.txt"),
               dict(label="SVG", path="bench/image.svg"), dict(label="PNG", path="bench/image.png")]
    sources.extend(dict(label=f"Source {index}", path=f"bench/source-{index:02d}.txt") for index in range(91))
    tasks = []
    for index in range(200):
        tasks.append(dict(id=f"task-{index}", title=f"Synthetic task {index}", summary="Synthetic benchmark task",
                          status="active", type="task", priority="minor",
                          stages=[dict(id="stage-0", title="Synthetic stage", status="active", remaining=["work"])],
                          sources=[]))
    tasks[0]["stages"] = [dict(id=f"stage-{index:02d}", title=f"Stage {index}", status="done" if index < 10 else "active",
                                remaining=[] if index < 10 else ["work"], estimate=dict(percentLow=1, percentHigh=3, confidence="low"))
                       for index in range(49)]
    tasks[0]["sources"] = sources
    catalog = base / "catalog.json"
    catalog.write_text(json.dumps({"local-projects": {"bench": {"id": "bench", "name": "Synthetic benchmark", "rootPaths": [str(project)]}}}))
    # Include host discovery in the workload, without scanning the user's
    # session catalog or index in any spawned process.
    with sqlite3.connect(base/'state_5.sqlite') as connection:
        connection.execute('CREATE TABLE threads(id TEXT PRIMARY KEY,name TEXT,cwd TEXT,updated_at INTEGER,archived INTEGER,source TEXT)')
        connection.executemany('INSERT INTO threads VALUES(?,?,?,?,?,?)',
            [('benchmark-verified-session' if i==0 else f'benchmark-session-{i}',
              f'Synthetic session {i}',str(project),i,0,'cli') for i in range(200)])
    (base/'session_index.jsonl').write_text('\n'.join(json.dumps({
        'id':'benchmark-verified-session' if i==0 else f'benchmark-session-{i}',
        'thread_name':f'Synthetic session {i}'}) for i in range(200))+'\n')
    registry = ProjectRegistry(base / "data", CodexProjects(catalog))
    registry.refresh()
    project_id = registry.list()["projects"][0]["id"]
    store = registry.base_store(project_id)
    store.data.mkdir(parents=True, exist_ok=True)
    (store.data / "project.json").write_text(json.dumps(dict(schemaVersion=1, id=project_id, name="Synthetic benchmark", tasks=tasks)))
    events = []
    for seq in range(1, 5_001):
        events.append(json.dumps(dict(schemaVersion=1, id=f"event-{seq}", seq=seq, kind="note",
                                     taskId=f"task-{seq % 200}", title="Synthetic note",
                                     detail="Synthetic benchmark note " + ("x" * 2270), at="2026-01-01T00:00:00Z")))
    journal = "\n".join(events) + "\n"
    (store.data / "events.jsonl").write_text(journal)
    seed_bytes = len((store.data / "project.json").read_bytes())
    return registry, project_id, project, dict(journalBytes=len(journal.encode()), seedBytes=seed_bytes, imageBytes=len(png))


def process_sample(pid):
    if sys.platform != "win32":
        return None
    command = "Get-Process -Id %d | Select-Object Id,CPU,WorkingSet64 | ConvertTo-Json -Compress" % pid
    try:
        output = subprocess.check_output(["powershell", "-NoProfile", "-Command", command], text=True, timeout=5)
        return json.loads(output)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


class ServerHandle:
    def __init__(self, mode, registry, project_id, project, workers, trace=False, trace_log=None, threads=2):
        self.mode, self.registry, self.project_id, self.project = mode, registry, project_id, project
        self.process = None
        self.thread = None
        self.server = None
        self.workers = workers
        self.threads = threads
        self.health_pids = set()
        self.trace = trace
        self.log_path = Path(trace_log) if trace_log else self.project.parent / "asgi-process.log"
        self.log_stream = None
        self.original_host_metadata = None

    @property
    def url(self):
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        if self.mode == "threaded":
            import codex_session_catalog
            import project_portal
            self.original_host_metadata = codex_session_catalog.CATALOG,project_portal.SESSION_TITLES
            codex_session_catalog.CATALOG = codex_session_catalog.SessionCatalog(self.project.parent/'state_5.sqlite')
            project_portal.SESSION_TITLES = project_portal.SessionTitles(self.project.parent/'session_index.jsonl')
            self.server = PortalServer(("127.0.0.1", 0), registry=self.registry)
            self.port = self.server.server_port
            self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
            self.thread.start()
            return
        self.port = free_port()
        if self.trace:
            command = [sys.executable, "-m", "uvicorn", "benchmark_hub_concurrency:traced_app", "--factory",
                       "--host", "127.0.0.1", "--port", str(self.port), "--workers", str(self.workers),
                       "--limit-concurrency", "512", "--backlog", "2048", "--no-access-log"]
            command += ["--timeout-worker-healthcheck", "30"]
        else:
            command = [sys.executable, str(ROOT / "scripts/project_portal.py"), "--projects-home", str(self.registry.home),
                       "serve", "--transport", "asgi", "--workers", str(self.workers),
                       "--request-threads", str(self.threads), "--port", str(self.port)]
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if sys.platform == "win32" else 0
        environment = os.environ.copy()
        environment["PROJECT_HUB_ASGI_CATALOG"] = str(self.project.parent / "catalog.json")
        environment["PROJECT_HUB_ASGI_HOME"] = str(self.registry.home)
        environment["PROJECT_HUB_ASGI_PORT"] = str(self.port)
        environment["PROJECT_HUB_ASGI_REQUEST_THREADS"] = str(self.threads)
        environment['PROJECT_HUB_OBSERVATION_HOME'] = str(self.project.parent)
        if self.trace:
            environment["PROJECT_HUB_TRACE_LOG"] = str(self.log_path)
            environment["PYTHONPATH"] = str(ROOT / "scripts") + os.pathsep + str(ROOT / ".local/server-deps") + os.pathsep + environment.get("PYTHONPATH", "")
        self.log_stream = open(self.log_path, "a", encoding="utf-8", buffering=1)
        self.process = subprocess.Popen(command, cwd=ROOT, stdout=self.log_stream, stderr=subprocess.STDOUT,
                                        text=True, creationflags=creationflags, env=environment)

    def stop(self):
        if self.server:
            self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)
        if self.original_host_metadata is not None:
            import codex_session_catalog
            import project_portal
            codex_session_catalog.CATALOG,project_portal.SESSION_TITLES = self.original_host_metadata
            self.original_host_metadata = None
        if self.process:
            # Graceful ASGI shutdown lets uvicorn close its worker children.  If
            # the manager does not honor CTRL_BREAK, only kill PIDs we observed
            # serving this disposable fixture, then the verified manager PID.
            # Do not send CTRL_BREAK: it targets the shared console and can
            # interrupt the wrapper itself.  The Popen handle is this run's
            # verified manager; health-observed worker PIDs are the only other
            # processes eligible for cleanup below.
            if sys.platform == "win32" and self.process.poll() is None:
                # The Popen PID is this disposable run's verified listener /
                # supervisor.  Kill only its process tree to reap uvicorn
                # resource trackers and dispatch children; never use a name
                # or port-wide taskkill.
                try:
                    subprocess.run(["taskkill", "/PID", str(self.process.pid), "/T", "/F"],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   check=False, timeout=10)
                except (OSError, subprocess.SubprocessError):
                    pass
            try:
                self.process.terminate()
            except OSError:
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                verified = sorted(self.health_pids, reverse=True)
                for pid in verified:
                    if pid != self.process.pid:
                        try: os.kill(pid, signal.SIGTERM)
                        except OSError: pass
                try: self.process.wait(timeout=5)
                except subprocess.TimeoutExpired: self.process.kill(); self.process.wait(timeout=5)
            for pid in sorted(self.health_pids, reverse=True):
                if pid == self.process.pid or process_sample(pid) is None:
                    continue
                try: os.kill(pid, signal.SIGTERM)
                except OSError: pass
            if self.log_stream:
                self.log_stream.close(); self.log_stream = None


def request(handle, method, path, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", handle.port, timeout=20)
    try:
        raw = None if body is None else json.dumps(body).encode()
        headers = {"Content-Type": "application/json"} if raw is not None else {}
        connection.request(method, path, raw, headers)
        response = connection.getresponse()
        payload = response.read()
        return response.status, payload, response.getheader("Server-Timing", "")
    finally:
        connection.close()


def wait_health(handle, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, payload, _ = request(handle, "GET", "/api/health")
            health = json.loads(payload)
            if status == 200 and health.get("service") == "project-hub" and health.get("multiProject") is True:
                valid = (Path(health.get("dataHome", "")).resolve() == handle.registry.home.resolve() and
                         Path(health.get("codeRoot", "")).resolve() == ROOT.resolve())
                if handle.mode == "asgi": valid = valid and health.get("transport") == "asgi"
                if valid:
                    if isinstance(health.get("pid"), int): handle.health_pids.add(health["pid"])
                    return health
        except (OSError, ValueError):
            pass
        time.sleep(.05)
    raise RuntimeError("benchmark server did not become ready")


def collect_health_pids(handle, attempts=12):
    for _ in range(attempts):
        try:
            wait_health(handle, timeout=.5)
        except RuntimeError:
            pass
        time.sleep(.02)


def timed_request(handle, method, path, body=None):
    begin = time.perf_counter()
    status, payload, timing = request(handle, method, path, body)
    return (time.perf_counter() - begin) * 1000, len(payload), timing, status


def exception_sample(error, *, method=None, path=None, phase=None):
    frames = [line.strip() for line in traceback.format_exc().splitlines()
              if "socket" in line.lower() or "urllib" in line.lower() or "http.client" in line.lower()]
    return dict(exception=type(error).__name__, message=str(error)[:250], method=method,
                route=path, phase=phase, tracebackTail=frames[-4:])


def route_paths(handle):
    query = urlencode({"project": handle.project_id})
    return {
        "summary": f"/api/tasks/summary?{query}",
        "detail": f"/api/tasks/detail?{query}&task=task-0",
        "history": f"/api/history?{query}&task=task-0&limit=40",
        "rawtext": f"/api/evidence?{query}&path=bench/text.txt",
        "image": f"/api/image?{query}&path=bench/image.png&preview=thumbnail",
        "document": f"/api/document?{query}&path=bench/text.txt",
    }


def mcp_body(project, tool="hub_plan", arguments=None):
    return dict(cwd=str(project), session="benchmark-verified-session", tool=tool, arguments=arguments or {"task": "task-0"})


def benchmark_routes(handle, clients, repeats, selected=None):
    paths = route_paths(handle)
    if selected: paths = {name: path for name, path in paths.items() if name in selected}
    routes = {}
    for name, path in paths.items():
        # The benchmark warms shared views with context/plan first; this is a
        # one-request concurrency pass, not a claim about first-ever cold load.
        for label, count in (("concurrencyCold", 1), ("warm", clients * repeats)):
            samples, payloads, timings, errors, error_samples = [], [], [], 0, []
            started = time.perf_counter()
            def one(_):
                begin = time.perf_counter()
                status, payload, server_timing = request(handle, "GET", path)
                return ((time.perf_counter() - begin) * 1000, len(payload), server_timing, status, payload)
            with ThreadPoolExecutor(max_workers=min(100, max(1, clients))) as pool:
                futures = [pool.submit(one, index) for index in range(count)]
                for future in as_completed(futures):
                    try:
                        latency, size, server_timing, status, payload = future.result()
                        if status != 200:
                            errors += 1
                            error_samples.append(dict(status=status, body=payload[:250].decode("utf-8", "replace"), serverTiming=server_timing,
                                                       method="GET", route=path, phase="route"))
                        samples.append((latency, size)); payloads.append(size); timings.append(server_timing)
                    except Exception as error:
                        errors += 1
                        error_samples.append(exception_sample(error, method="GET", path=path, phase="route"))
                routes.setdefault(name, {})[label] = stats(samples, started, payloads, errors, timings, error_samples)
    return routes


def benchmark_mcp_and_writes(handle):
    status, payload, _ = request(handle, "POST", "/api/v1/plugin/call", mcp_body(handle.project, "hub_context", {"session": "benchmark-verified-session"}))
    if status != 200: raise RuntimeError(f"hub_context failed: {status} {payload[:200]!r}")
    status, payload, _ = request(handle, "POST", "/api/v1/plugin/call", mcp_body(handle.project))
    if status != 200: raise RuntimeError(f"hub_plan failed: {status} {payload[:200]!r}")
    samples, payloads, timings, errors = [], [], [], 0
    started = time.perf_counter()
    def one_text(index):
        begin = time.perf_counter(); status, payload, timing = request(handle, "GET", route_paths(handle)["rawtext"])
        return (time.perf_counter() - begin) * 1000, len(payload), timing, status
    def one_mcp(index):
        begin = time.perf_counter(); status, payload, timing = request(handle, "POST", "/api/v1/plugin/call", mcp_body(handle.project))
        return (time.perf_counter() - begin) * 1000, len(payload), timing, status
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(one_text, index) for index in range(5)]
        futures += [pool.submit(one_mcp, index) for index in range(5)]
        for future in as_completed(futures):
            try:
                latency, size, timing, status = future.result()
                if status != 200: errors += 1
                samples.append((latency, size)); payloads.append(size); timings.append(timing)
            except Exception: errors += 1
    reads = stats(samples, started, payloads, errors, timings)
    writes, write_errors = [], 0
    write_started = time.perf_counter()
    for index in range(5):
        try:
            summary_status, summary_payload, _ = request(handle, "GET", route_paths(handle)["summary"])
            current = json.loads(summary_payload)
            revision = current.get("revision")
            path = f"/api/v1/tasks/update?project={handle.project_id}&view=ack"
            latency, size, timing, status = timed_request(
                handle, "POST", path,
                {"task": "task-0", "expected": revision,
                 "patch": {"summary": f"benchmark note {index}-{time.time_ns()}"}})
            if status != 200: write_errors += 1
            writes.append((latency, size)); payloads.append(size); timings.append(timing)
        except (OSError, ValueError, KeyError):
            write_errors += 1
    return dict(reads=reads, writes=stats(writes, write_started, [item[1] for item in writes], write_errors, timings[-len(writes):] if writes else []),
                writeErrors=write_errors)


def benchmark_sse(handle, count=100):
    connections = []
    errors = 0
    ready = 0
    def open_one(_):
        connection = http.client.HTTPConnection("127.0.0.1", handle.port, timeout=10)
        try:
            connection.request("GET", f"/api/events?project={handle.project_id}")
            response = connection.getresponse()
            if response.status != 200:
                connection.close(); return None
            first = response.readline(4096)
            if not first:
                connection.close(); return None
            return connection, response
        except (OSError, http.client.HTTPException):
            connection.close()
            return None
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(open_one, i) for i in range(count)]
        try:
            for future in as_completed(futures, timeout=20):
                try:
                    item = future.result()
                    if item is None: errors += 1
                    else: ready += 1; connections.append(item)
                except Exception: errors += 1
        except TimeoutError:
            errors += sum(1 for future in futures if not future.done())
            for future in futures: future.cancel()
    setup_elapsed = (time.perf_counter() - started) * 1000
    initial_status, initial_payload, _ = request(handle, "GET", route_paths(handle)["summary"])
    initial = json.loads(initial_payload) if initial_status == 200 else {}
    write = None
    try:
        read_samples, read_payloads, read_timings, read_errors = [], [], [], 0
        read_paths = [route_paths(handle)["rawtext"], route_paths(handle)["detail"]]
        def sse_read(index):
            if index % 3 == 2:
                return timed_request(handle, "POST", "/api/v1/plugin/call",
                                     mcp_body(handle.project, "hub_plan"))
            return timed_request(handle, "GET", read_paths[index % 2])
        read_started = time.perf_counter()
        with ThreadPoolExecutor(max_workers=15) as pool:
            futures = [pool.submit(sse_read, index) for index in range(15)]
            for future in as_completed(futures):
                try:
                    sample = future.result()
                    if sample[3] != 200: read_errors += 1
                    read_samples.append((sample[0], sample[1])); read_payloads.append(sample[1]); read_timings.append(sample[2])
                except Exception:
                    read_errors += 1
        path = f"/api/v1/tasks/update?project={handle.project_id}&view=ack"
        write = timed_request(handle, "POST", path, {"task": "task-0", "expected": initial.get("revision"),
                                                        "patch": {"summary": f"sse benchmark note {time.time_ns()}"}})
        after_status, after_payload, _ = request(handle, "GET", route_paths(handle)["summary"])
        after = json.loads(after_payload) if after_status == 200 else {}
        expected_revision = after.get("revision")
        def await_revision(item):
            _, response = item
            deadline = time.monotonic() + 10
            try:
                while time.monotonic() < deadline:
                    line = response.readline(4096)
                    if not line: return False
                    if line.startswith(b"data:"):
                        try:
                            data = json.loads(line[5:].strip())
                            if data.get("revision") == expected_revision: return True
                        except ValueError:
                            pass
            except (OSError, TimeoutError):
                return False
            return False
        event_received = 0
        with ThreadPoolExecutor(max_workers=20) as pool:
            event_futures = [pool.submit(await_revision, item) for item in connections]
            try:
                for future in as_completed(event_futures, timeout=12):
                    try: event_received += int(bool(future.result()))
                    except Exception: pass
            except TimeoutError:
                pass
        return dict(clients=count, ready=ready, errors=errors, initialRevision=initial.get("revision"),
                    setupMs=setup_elapsed, eventReceived=event_received,
                    overlappingReads=stats(read_samples, read_started, read_payloads, read_errors, read_timings),
                    write=write, afterRevision=after.get("revision"), revisionChanged=after.get("revision") != initial.get("revision"),
                    coherent=after_status == 200 and bool(after.get("revision")) and event_received > 0)
    finally:
        for connection, response in connections:
            try: response.close()
            finally: connection.close()


def benchmark_paced(handle, seconds, clients):
    read_rate, write_rate = (30, 5) if clients == 10 else (100, 10)
    routes = route_paths(handle)
    read_paths = [("GET", routes[name]) for name in ("rawtext", "summary", "detail", "history", "image", "document")]
    read_paths.append(("POST", "/api/v1/plugin/call"))
    read_samples, write_samples, read_payloads, write_payloads = [], [], [], []
    read_timings, write_timings, read_errors, write_errors = [], [], [], []
    conflicts, writes, dropped, submitted, queue_delays = 0, 0, 0, 0, []
    started = time.perf_counter(); deadline = started + seconds
    stop_writer = threading.Event()
    status, payload, _ = request(handle, "GET", routes["summary"])
    revision = json.loads(payload).get("revision") if status == 200 else None
    def record_read(sample, queue_delay):
        queue_delays.append(queue_delay)
        if sample[3] != 200:
            read_errors.append(dict(status=sample[3], serverTiming=sample[2]))
        read_samples.append((sample[0], sample[1])); read_payloads.append(sample[1]); read_timings.append(sample[2])
    def read_one(kind, path):
        started_at = time.perf_counter()
        return timed_request(handle, kind, path, mcp_body(handle.project, "hub_plan") if kind == "POST" else None), started_at
    def writer():
        nonlocal conflicts, writes, revision
        next_write = time.perf_counter()
        while next_write < deadline and not stop_writer.is_set():
            if time.perf_counter() >= deadline: break
            try:
                write_path = f"/api/v1/tasks/update?project={handle.project_id}&view=ack"
                begin = time.perf_counter()
                status, payload, timing = request(
                    handle, "POST", write_path,
                    {"task": "task-0", "expected": revision,
                     "patch": {"summary": f"paced note {time.time_ns()}"}})
                sample = ((time.perf_counter() - begin) * 1000, len(payload), timing, status, payload)
                if sample[3] == 409:
                    conflicts += 1
                    status, payload, _ = request(handle, "GET", routes["summary"])
                    retry_revision = json.loads(payload).get("revision") if status == 200 else None
                    begin = time.perf_counter()
                    status, payload, timing = request(
                        handle, "POST", write_path,
                        {"task": "task-0", "expected": retry_revision,
                         "patch": {"summary": f"paced retry {time.time_ns()}"}})
                    sample = ((time.perf_counter() - begin) * 1000, len(payload), timing, status, payload)
                if sample[3] != 200: write_errors.append(dict(status=sample[3], serverTiming=sample[2]))
                else:
                    ack = json.loads(sample[4])
                    if ack.get("accepted") is not True or not ack.get("revision"):
                        write_errors.append(dict(status=sample[3], message="invalid ack response"))
                    else:
                        revision = ack["revision"]
                write_samples.append((sample[0], sample[1])); write_payloads.append(sample[1]); write_timings.append(sample[2]); writes += 1
            except Exception as error:
                write_errors.append(dict(exception=type(error).__name__, message=str(error)[:250]))
            next_write += 1.0 / write_rate
            time.sleep(max(0, next_write - time.perf_counter()))
    with ThreadPoolExecutor(max_workers=clients) as pool:
        semaphore = threading.BoundedSemaphore(clients * 2)
        futures = []
        writer_thread = threading.Thread(target=writer, daemon=True); writer_thread.start()
        next_read = started
        index = 0
        while next_read < deadline:
            wait = next_read - time.perf_counter()
            if wait > 0: time.sleep(wait)
            if not semaphore.acquire(blocking=False):
                dropped += 1
            else:
                kind, path = read_paths[index % len(read_paths)]; index += 1; scheduled = next_read
                future = pool.submit(read_one, kind, path)
                submitted += 1
                futures.append((future, scheduled, kind, path))
                future.add_done_callback(lambda _future, gate=semaphore: gate.release())
            next_read += 1.0 / read_rate
        stop_writer.set()
        drain_started = time.perf_counter()
        writer_thread.join(timeout=20)
        drain_seconds = time.perf_counter() - drain_started
        for future, scheduled, kind, path in futures:
            try:
                sample, worker_started = future.result()
                record_read(sample, max(0, (worker_started - scheduled) * 1000))
            except Exception as error:
                read_errors.append(exception_sample(error, method=kind, path=path, phase="paced-read"))
        drain_seconds = time.perf_counter() - drain_started
    elapsed = max(seconds, 1e-9)
    return dict(clients=clients, targetSeconds=seconds, elapsedSeconds=elapsed, drainSeconds=drain_seconds,
                writerAlive=writer_thread.is_alive(),
                targetReadRate=read_rate, targetWriteRate=write_rate,
                achievedReadRate=len(read_samples) / elapsed, achievedWriteRate=writes / elapsed,
                submittedReads=submitted, completedReads=len(read_samples), droppedReads=dropped,
                queueDelayMs=dict(p50=percentile(queue_delays, .5) if queue_delays else None,
                                                        p95=percentile(queue_delays, .95) if queue_delays else None),
                conflicts=conflicts, readErrors=len(read_errors), writeErrors=len(write_errors),
                reads=stats(read_samples, started, read_payloads, len(read_errors), read_timings, read_errors),
                writes=stats(write_samples, started, write_payloads, len(write_errors), write_timings, write_errors))


def capacity_checks(result):
    """Evaluate the explicit paced acceptance budget without changing defaults."""
    checks = {}
    for clients, read_limit, write_limit in ((10, 150, 250), (100, 300, 500)):
        phase = result.get("paced", {}).get(str(clients))
        failures = []
        if phase is None:
            failures.append("paced phase missing")
        else:
            reads = phase.get("reads", {})
            writes = phase.get("writes", {})
            if reads.get("p95Ms", float("inf")) > read_limit:
                failures.append(f"read p95 {reads.get('p95Ms')}ms > {read_limit}ms")
            if writes.get("p95Ms", float("inf")) > write_limit:
                failures.append(f"write p95 {writes.get('p95Ms')}ms > {write_limit}ms")
            for label, actual, target in (
                    ("read rate", phase.get("achievedReadRate", 0), phase.get("targetReadRate", 0)),
                    ("write rate", phase.get("achievedWriteRate", 0), phase.get("targetWriteRate", 0))):
                if actual < target * .98:
                    failures.append(f"{label} {actual} < 98% of {target}")
            for name, value in (("dropped reads", phase.get("droppedReads", 0)),
                                ("read errors", phase.get("readErrors", 0)),
                                ("write errors", phase.get("writeErrors", 0)),
                                ("conflicts", phase.get("conflicts", 0))):
                if value:
                    failures.append(f"{name}={value}")
            if phase.get("writerAlive"):
                failures.append("writer still alive after drain")
        checks[str(clients)] = dict(passed=not failures, failures=failures,
                                    limits=dict(readP95Ms=read_limit, writeP95Ms=write_limit,
                                                rateFraction=.98))
    sse = result.get("sse100")
    if sse is not None and not sse.get("skipped"):
        failures = []
        if sse.get("ready") != 100:
            failures.append(f"ready={sse.get('ready')}")
        if sse.get("eventReceived") != 100:
            failures.append(f"eventReceived={sse.get('eventReceived')}")
        if sse.get("errors", 0):
            failures.append(f"errors={sse.get('errors')}")
        checks["sse100"] = dict(passed=not failures, failures=failures,
                                limits=dict(ready=100, eventReceived=100, errors=0))
    return checks, [f"{name}: {failure}" for name, check in checks.items()
                    for failure in check["failures"]]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("threaded", "asgi"), default="threaded")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--clients", default="1,10,100", help="Comma-separated client counts")
    parser.add_argument("--repeats", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--routes", help="Comma-separated route names to measure")
    parser.add_argument("--trace", action="store_true", help="Use benchmark-only traced ASGI factory")
    parser.add_argument("--skip-sse", action="store_true", help="Skip SSE phase for focused route diagnosis")
    parser.add_argument("--paced", type=float, default=0, help="Run bounded paced mixed traffic for this many seconds")
    parser.add_argument("--require-capacity", action="store_true",
                        help="Fail after the run unless paced and SSE acceptance budgets pass")
    args = parser.parse_args(argv)
    clients = [int(value) for value in args.clients.split(",") if value.strip()]
    selected_routes = {value.strip() for value in args.routes.split(",") if value.strip()} if args.routes else None
    if not clients or any(value < 1 for value in clients) or args.repeats < 1: parser.error("clients and repeats must be positive")
    if not 1 <= args.threads <= 32: parser.error("threads must be between 1 and 32")
    if args.require_capacity and (args.paced < 30 or not {10, 100}.issubset(clients)):
        parser.error("--require-capacity requires --paced >= 30 and clients including 10,100")
    capacity_failed = False
    with tempfile.TemporaryDirectory(prefix="project-hub-concurrency-") as directory:
        registry, project_id, project, fixture_sizes = write_fixture(Path(directory))
        handle = ServerHandle(args.mode, registry, project_id, project, args.workers, args.trace,
                              args.output.with_suffix(".workers.log"), threads=args.threads)
        started_at = time.time(); handle.start()
        try:
            health = wait_health(handle)
            collect_health_pids(handle)
            process_before = {str(pid): process_sample(pid) for pid in sorted(handle.health_pids)} if handle.health_pids else None
            result = dict(schemaVersion=1, mode=args.mode, workers=args.workers, threads=args.threads, clients=clients, repeats=args.repeats,
                          runtimeVersion=health.get("runtimeVersion"),
                          fixture=dict(tasks=200, journalEvents=5000, heavyStages=49, heavySources=95,
                                       hostSessions=200,hostMetadata='isolated',
                                       textBytes=57000, smallTextBytes=4600, imageBytes=fixture_sizes["imageBytes"],
                                       journalBytes=fixture_sizes["journalBytes"], seedBytes=fixture_sizes["seedBytes"]),
                          routes={})
            result["mcpContextAndPlan"] = benchmark_mcp_and_writes(handle)
            print("phase=mcp-and-writes complete", flush=True)
            for count in clients:
                result["routes"][str(count)] = benchmark_routes(handle, count, args.repeats, selected_routes)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                print(f"phase=routes clients={count} complete", flush=True)
            result["sse100"] = benchmark_sse(handle, 100) if 100 in clients and not args.skip_sse else dict(skipped=True)
            if 100 in clients and not args.skip_sse: print("phase=sse100 complete", flush=True)
            if args.paced > 0:
                result["paced"] = {str(clients): benchmark_paced(handle, args.paced, clients) for clients in (10, 100)}
                args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
                print("phase=paced complete", flush=True)
            collect_health_pids(handle)
            process_after = {str(pid): process_sample(pid) for pid in sorted(handle.health_pids)} if handle.health_pids else None
            result["process"] = dict(platform=sys.platform, before=process_before, after=process_after,
                                     pids=sorted(handle.health_pids),
                                     note="threaded mode is in-process" if not handle.process else
                                     "CPU/RAM cover health-observed serving PIDs only; listener and mutation worker may not be sampled")
            if args.require_capacity:
                result["capacity"], capacity_failures = capacity_checks(result)
                capacity_failed = bool(capacity_failures)
                if capacity_failures:
                    result["capacityFailures"] = capacity_failures
            result["durationSec"] = time.time() - started_at
            # Persist the complete measurement before shutdown, so wrapper or
            # OS interruption during child cleanup cannot discard the matrix.
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        finally:
            handle.stop()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))
        if capacity_failed:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
