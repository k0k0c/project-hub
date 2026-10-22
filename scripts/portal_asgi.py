"""ASGI transport for the shared Hub dispatcher and asynchronous SSE.

No internal HTTP hop: existing routes execute directly in a bounded executor.
Each worker has its own services; durable revisions/ownership stay in SQLite and
journals. SSE consumes producer hints on the event loop without worker threads.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from email.message import Message
import io
import json
import os
import time
from urllib.parse import parse_qs, quote, urlparse

from project_portal import Handler, PortalServer

_worker_dispatch = None


def initialize_dispatch(home, catalog, port, processes):
    """Spawn workers own services and data handles, but no listening socket."""
    global _worker_dispatch
    import runtime_diagnostics as diagnostics
    diagnostics.configure('request-worker',control=os.environ.get('PROJECT_HUB_CONTROL'),port=port)
    from types import SimpleNamespace
    from multiprocessing.util import Finalize
    from project_registry import CodexProjects, ProjectRegistry
    from storage_operations import internal
    from pathlib import Path
    standalone = isinstance(catalog, dict) and catalog.get('standalone') is True
    catalog_path = catalog.get('path') if isinstance(catalog, dict) else catalog
    with internal(SimpleNamespace(home=Path(home).resolve())):
        registry = ProjectRegistry(home, CodexProjects(catalog_path) if catalog_path else None, standalone=standalone)
        registry.refresh()
    registry.enable_connection_pool()
    service = PortalServer(('127.0.0.1', port), registry=registry, bind_and_activate=False)
    service.transport = 'asgi'
    service.dispatch_processes = processes
    _worker_dispatch = SimpleNamespace(service=service)
    Finalize(None, service.server_close, exitpriority=10)


def dispatch_process(scope, body):
    return PortalASGI.dispatch(_worker_dispatch, scope, body)


class DispatchHandler(Handler):
    def reject_unread_post(self, status, body):
        # ASGI has already received the body; there is no handler-owned socket
        # to half-close or drain as in BaseHTTPRequestHandler.
        self.reply(status, body)

    def stream_file(self, path):
        self.file_response = {'file': str(path)}

    def send_response(self, code, message=None):
        self.status = code

    def send_header(self, name, value):
        self.response_headers.append((name.lower().encode('ascii'), str(value).encode('latin-1')))

    def end_headers(self):
        pass


class PortalASGI:
    def __init__(self, registry, port=8769, *, threads=4, pending=128, subscribers=256, body_timeout=10, processes=0):
        if not 1 <= threads <= 32:
            raise ValueError('Request threads must be between 1 and 32')
        registry.enable_connection_pool()
        self.service = PortalServer(('127.0.0.1', port), registry=registry, bind_and_activate=False)
        self.service.transport = 'asgi'
        self.processes = processes
        self.request_threads = threads
        self.pending = pending
        self.service.dispatch_processes = processes
        from hub_lifecycle import shutdown_monitor
        shutdown_monitor(self.service.stopping.set)
        catalog = dict(path=str(registry.catalog.path) if hasattr(registry.catalog,'path') else None,
                       standalone=True) if registry.standalone else str(registry.catalog.path)
        self.dispatch_arguments = (str(registry.home), catalog, port, processes)
        self.executor = (self.new_process_executor()
                         if processes else ThreadPoolExecutor(max_workers=threads, thread_name_prefix='hub-request'))
        self.active = 0
        self.subscriber_limit, self.subscribers = subscribers, 0
        self.large_bodies = 0
        self.body_timeout = body_timeout
        self.executor_retry_at = 0

    def new_process_executor(self):
        from multiprocess_dispatch import DispatchExecutor
        return DispatchExecutor(*self.dispatch_arguments, threads=self.request_threads, pending=self.pending)

    def dispatch(self, scope, body):
        handler = object.__new__(DispatchHandler)
        handler.server = self.service
        handler.command = scope['method']
        raw = scope.get('raw_path')
        handler.path = raw.decode('ascii') if raw is not None else quote(scope['path'], safe='/')
        if scope.get('query_string'):
            handler.path += '?' + scope['query_string'].decode('ascii')
        handler.request_version = 'HTTP/' + scope.get('http_version', '1.1')
        handler.requestline = handler.command + ' ' + handler.path + ' ' + handler.request_version
        handler.client_address = scope.get('client') or ('127.0.0.1', 0)
        handler.close_connection = True
        handler.headers = Message()
        for name, value in scope.get('headers', []):
            handler.headers[name.decode('latin-1')] = value.decode('latin-1')
        if handler.headers.get('Content-Length') is None and body:
            handler.headers['Content-Length'] = str(len(body))
        handler.rfile, handler.wfile = io.BytesIO(body), io.BytesIO()
        handler.response_headers = []
        action = getattr(handler, 'do_' + handler.command, None)
        from runtime_diagnostics import record, exception
        started=time.monotonic()
        try:
            if action is None:
                handler.reply(405, {'error': 'Method not supported'})
            else:
                action()
        except BaseException as error:
            exception('request.failed',error,method=scope['method'],route=scope['path'])
            raise
        finally:
            elapsed=time.monotonic()-started
            if elapsed>=5:
                record('request.slow',method=scope['method'],route=scope['path'],elapsedSeconds=round(elapsed,3))
        return handler.status, handler.response_headers, getattr(handler, 'file_response', handler.wfile.getvalue())

    async def response(self, send, status, body):
        data = json.dumps(body).encode()
        await send({'type': 'http.response.start', 'status': status, 'headers': [
            (b'content-type', b'application/json'), (b'content-length', str(len(data)).encode()),
            (b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff')]})
        await send({'type': 'http.response.body', 'body': data})

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'lifespan':
            while True:
                event = await receive()
                if event['type'] == 'lifespan.startup':
                    await send({'type': 'lifespan.startup.complete'})
                elif event['type'] == 'lifespan.shutdown':
                    self.service.stopping.set()
                    await asyncio.to_thread(self.executor.shutdown, wait=True, cancel_futures=True)
                    await asyncio.to_thread(self.service.server_close)
                    await send({'type': 'lifespan.shutdown.complete'})
                    return
        if scope['type'] != 'http':
            return
        headers = scope.get('headers', [])
        hosts = [v.decode('latin-1') for k,v in headers if k.lower() == b'host']
        if len(hosts) != 1 or hosts[0] not in (f'127.0.0.1:{self.service.server_port}', f'localhost:{self.service.server_port}'):
            return await self.response(send, 403, {'error': 'Local access only'})
        lengths = [v for k,v in headers if k.lower() == b'content-length']
        if len(lengths) > 1:
            return await self.response(send, 400, {'error': 'Ambiguous content length'})
        if scope['method'] == 'GET' and scope['path'] in ('/api/events','/api/v1/events'):
            if lengths and lengths != [b'0']:
                return await self.response(send, 400, {'error': 'SSE requires an empty request body'})
            if self.subscribers >= self.subscriber_limit:
                return await self.response(send, 503, {'error': 'Subscriber limit reached; retry shortly'})
            self.subscribers += 1
            try:
                return await self.stream(scope, receive, send)
            finally:
                self.subscribers -= 1
        from backup_api import REQUEST_LIMIT
        from agent_sdk import MAX_AGENT_REQUEST_BYTES
        limit = (REQUEST_LIMIT if scope['path'] == '/api/v1/backups' else 28_000_000 if scope['path'] in ('/api/v1/images/upload', '/api/v1/artifacts/upload','/api/v1/agent/artifacts')
                 else 64_000_000 if scope['path'] == '/api/v1/knowledge' else MAX_AGENT_REQUEST_BYTES if scope['path'] in ('/mcp','/api/v1/agent/call') else 160_000 if scope['path'] in ('/api/agent-instructions','/api/v1/agent-instructions','/api/v1/connections') else 16_000) if scope['method'] == 'POST' else 0
        if lengths:
            try:
                declared = int(lengths[0])
                if declared < 0: raise ValueError()
            except ValueError:
                return await self.response(send, 400, {'error': 'Invalid content length'})
            if declared > limit:
                return await self.response(send, 413, {'error': 'Request exceeds route limit'})
        # Admission follows the actual body, not the route's maximum. MCP and
        # agent calls share upload-capable routes, but ordinary JSON requests
        # must not consume the two slots reserved for large in-memory bodies.
        large = bool(lengths and declared > 16_000)
        if large and self.large_bodies >= 2:
            return await self.response(send, 503, {'error': 'Upload queue is full; retry shortly'})
        if self.active >= self.pending:
            return await self.response(send, 503, {'error': 'Request queue is full; retry shortly'})
        self.active += 1
        self.large_bodies += int(large)
        try:
            body = bytearray()
            deadline = asyncio.get_running_loop().time() + self.body_timeout
            while True:
                try:
                    event = await asyncio.wait_for(receive(), max(.001, deadline - asyncio.get_running_loop().time()))
                except asyncio.TimeoutError:
                    return await self.response(send, 408, {'error': 'Request body timed out'})
                if event['type'] == 'http.disconnect':
                    return
                if event['type'] != 'http.request':
                    continue
                chunk = event.get('body', b'')
                size = len(body) + len(chunk)
                if size > limit:
                    return await self.response(send, 413, {'error': 'Request exceeds limit'})
                # Chunked bodies have no declared size. Reserve before copying
                # the first large chunk, and release on every exit/cancellation.
                if not large and size > 16_000:
                    if self.large_bodies >= 2:
                        return await self.response(send, 503, {'error': 'Upload queue is full; retry shortly'})
                    large = True
                    self.large_bodies += 1
                body.extend(chunk)
                if not event.get('more_body'):
                    break
            if lengths:
                try:
                    if int(lengths[0]) != len(body):
                        raise ValueError()
                except ValueError:
                    return await self.response(send, 400, {'error': 'Invalid content length'})
            request_scope = {key: scope[key] for key in ('method','path','raw_path','query_string','http_version','headers','client') if key in scope}
            executor = self.executor
            try:
                if scope['method'] == 'GET' and scope['path'] == '/api/health':
                    # Health describes the serving process, so do not route it
                    # through rotating request workers.
                    result = await asyncio.to_thread(self.dispatch, request_scope, bytes(body))
                else:
                    result = await asyncio.get_running_loop().run_in_executor(
                        executor, dispatch_process if self.processes else self.dispatch, request_scope, bytes(body))
            except BrokenProcessPool:
                # The event loop serializes replacement. Other in-flight calls
                # fail explicitly; a mutation is never replayed automatically.
                if self.executor is executor and not self.service.stopping.is_set() and time.monotonic() >= self.executor_retry_at:
                    self.executor_retry_at = time.monotonic() + 2
                    self.executor = self.new_process_executor()
                    executor.shutdown(wait=False, cancel_futures=True)
                from runtime_diagnostics import record
                record('request.worker_lost',method=scope['method'],route=scope['path'])
                return await self.response(send, 503, {'error':'Request worker exited; refresh before retrying'})
            except Exception as error:
                from runtime_diagnostics import exception
                exception('request.dispatch_failed',error,method=scope['method'],route=scope['path'])
                return await self.response(send,500,{'code':'request_failed','error':'Request failed; details are saved in server diagnostics.'})
            status, response_headers, data = result
            if isinstance(data, dict) and set(data) == {'file'}:
                # Only the shared dispatcher produces this private descriptor.
                # Open before sending headers; a missing file remains a JSON error.
                try:
                    source = await asyncio.to_thread(open, data['file'], 'rb')
                except OSError:
                    return await self.response(send, 404, {'error': 'Архив недоступен'})
                try:
                    expected_size = next(int(value) for key, value in response_headers if key == b'content-length')
                    if os.fstat(source.fileno()).st_size != expected_size:
                        return await self.response(send, 409, {'error': 'Archive changed before download'})
                    await send({'type': 'http.response.start', 'status': status, 'headers': response_headers})
                    while chunk := await asyncio.to_thread(source.read, 256 * 1024):
                        await send({'type': 'http.response.body', 'body': chunk, 'more_body': True})
                    await send({'type': 'http.response.body', 'body': b''})
                finally:
                    source.close()
            else:
                await send({'type': 'http.response.start', 'status': status, 'headers': response_headers})
                await send({'type': 'http.response.body', 'body': data})
        finally:
            self.active -= 1
            self.large_bodies -= int(large)

    async def stream(self, scope, receive, send):
        query = parse_qs(scope.get('query_string', b'').decode('ascii'))
        ids = query.get('project', [])
        if len(ids) != 1 or not ids[0]:
            return await self.response(send, 400, {'error': 'Select an explicit project'})
        try:
            store = self.service.registry.store(ids[0])
        except (ValueError, KeyError):
            return await self.response(send, 400, {'error': 'Unknown project'})
        broker = self.service.event_broker
        joined = time.monotonic()
        broker.state(store)
        # Drain the GET request before waiting for a disconnect; no blocking
        # executor task or database read belongs to a subscriber.
        event = await receive()
        if event['type'] == 'http.disconnect':
            return
        if event.get('body') or event.get('more_body'):
            return await self.response(send, 400, {'error': 'SSE requires an empty request body'})
        await send({'type':'http.response.start','status':200,'headers':[
            (b'content-type',b'text/event-stream; charset=utf-8'),(b'cache-control',b'no-cache'),
            (b'x-content-type-options',b'nosniff')]})
        disconnect = asyncio.create_task(receive())
        revision, pulse = None, 0
        try:
            while not self.service.stopping.is_set():
                if disconnect.done():
                    if disconnect.result()['type'] == 'http.disconnect':
                        return
                    disconnect = asyncio.create_task(receive())
                hint = broker.state(store)
                if broker.checked(store) >= joined and hint is not None and hint != revision:
                    revision = hint
                    data = f"id: {hint['revision']}:{hint['coordinationRevision']}\nevent: revision\ndata: {json.dumps(hint)}\n\n".encode()
                    await send({'type':'http.response.body','body':data,'more_body':True})
                if time.monotonic() - pulse > 10:
                    await send({'type':'http.response.body','body':b': connected\n\n','more_body':True})
                    pulse = time.monotonic()
                await asyncio.wait({disconnect}, timeout=.4)
        except (OSError, ValueError):
            pass
        finally:
            disconnect.cancel()
            await asyncio.gather(disconnect, return_exceptions=True)
        await send({'type':'http.response.body','body':b''})


def create_app():
    from project_registry import CodexProjects, ProjectRegistry
    from storage_operations import internal
    from types import SimpleNamespace
    from pathlib import Path
    catalog = CodexProjects(os.environ['PROJECT_HUB_ASGI_CATALOG']) if os.environ.get('PROJECT_HUB_ASGI_CATALOG') else None
    with internal(SimpleNamespace(home=Path(os.environ['PROJECT_HUB_ASGI_HOME']).resolve())):
        registry = ProjectRegistry(os.environ['PROJECT_HUB_ASGI_HOME'], catalog,
                                   standalone=os.environ.get('PROJECT_HUB_STANDALONE')=='1')
        registry.refresh()
    return PortalASGI(registry, int(os.environ.get('PROJECT_HUB_ASGI_PORT','8769')),
                      threads=int(os.environ.get('PROJECT_HUB_ASGI_REQUEST_THREADS','4')),
                      processes=int(os.environ.get('PROJECT_HUB_ASGI_DISPATCH_PROCESSES','0')))
