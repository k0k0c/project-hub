"""Explicitly connect this Codex app session to the local Hub administration API.

Run inside Codex. The experimental host pipe is inherited, never discovered.
Only the separate bridge key reaches Hub's existing private credential vault.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import secrets
import shutil
import subprocess
import threading
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from hub_lifecycle import file_lock


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def local_url(value):
    url = urlsplit(value)
    if (url.scheme != 'http' or url.hostname != '127.0.0.1' or not url.port or
            url.username or url.password or url.query or url.fragment or url.path not in ('', '/')):
        raise ValueError('Use the local Hub URL http://127.0.0.1:PORT')
    return value.rstrip('/')


def request(base, route, body=None, key=None):
    headers = {'Content-Type': 'application/json'}
    if key:
        headers['Authorization'] = 'Bearer ' + key
    else:
        headers['Origin'] = base
    payload = json.dumps(body).encode() if body is not None else None
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(Request(base + route, data=payload, headers=headers), timeout=15) as response:
        return json.loads(response.read(2_000_000))


def process_alive(pid):
    if type(pid) is not int or pid <= 0:
        raise ValueError('Invalid bridge lock owner')
    if os.name != 'nt':
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.get_last_error() != 87  # Access denied or unknown: refuse to reclaim.
    try:
        status = wintypes.DWORD()
        return not kernel.GetExitCodeProcess(handle, ctypes.byref(status)) or status.value == 259
    finally:
        kernel.CloseHandle(handle)


def reclaim_lock(state):
    """Called under the setup OS lock; retain journal reservations after a crash."""
    lock = Path(str(state) + '.lock')
    if not lock.exists():
        return
    content = lock.read_bytes()
    if len(content) > 1024 or process_alive(json.loads(content)['pid']):
        raise ValueError('The bridge is already running or its owner cannot be verified')
    lock.unlink(missing_ok=True)


def input_profile(value):
    """Strip only server-generated annotations before revalidating a profile."""
    profile = json.loads(json.dumps(value or {'schemaVersion': 1}))
    if isinstance(profile.get('persistentInstructions'), dict):
        profile['persistentInstructions'].pop('verification', None)
    if isinstance(profile.get('nativeChat'), dict):
        profile['nativeChat'] = {key: item for key, item in profile['nativeChat'].items()
                                if key in ('client', 'clientInstance', 'host', 'nativeId', 'openUri', 'title', 'model')}
    return profile


def connect(base, connection, runtime, node=None):
    runtime = Path(runtime).resolve()
    runtime.mkdir(parents=True, exist_ok=True)
    # MSIX may virtualize a newly created AppData directory. Resolve again
    # after creation so the standard runtime lock sees its actual native path.
    runtime = runtime.resolve()
    with file_lock(runtime / 'setup.lock'):
        return _connect(base, connection, runtime, node)


def _connect(base, connection, runtime, node=None):
    base = local_url(base)
    if not os.environ.get('CODEX_APP_TOOLS_PIPE_PATH') or not os.environ.get('CODEX_THREAD_ID'):
        raise ValueError('Run setup from the Codex chat that authorizes this adapter')
    catalog = request(base, '/api/connections')
    matches = [row for row in catalog['bindings'] if row['id'] == connection and not row.get('revoked')]
    if len(matches) != 1 or matches[0]['client'] != 'codex':
        raise ValueError('Select an active Codex connection in this Hub')
    source = Path(__file__).resolve().parents[1]
    roots = [Path(item['scope']['root']).resolve() for item in matches[0].get('projectBindings', [])
             if item.get('scope', {}).get('root')]
    if runtime.is_relative_to(source) or any(runtime.is_relative_to(root) for root in roots):
        raise ValueError('Keep bridge runtime data outside source workspaces')
    instance = hashlib.sha256((os.environ['CODEX_APP_TOOLS_PIPE_PATH'] + '\n' + os.environ['CODEX_THREAD_ID']).encode()).hexdigest()
    state = runtime / ('journal-' + instance[:20] + '.json')
    reclaim_lock(state)
    # No key is written to setup metadata, logs, command lines or the checkout.
    key = secrets.token_urlsafe(48)
    environment = dict(os.environ, PROJECT_HUB_CODEX_BRIDGE_KEY=key)
    executable = node or os.environ.get('CODEX_MCP_NODE_PATH') or shutil.which('node')
    if not executable:
        raise ValueError('Codex Node.js runtime is unavailable')
    command = [executable, str(Path(__file__).with_name('codex_desktop_bridge.mjs')),
               '--state', str(state), '--hub-url', base, '--connection', connection]
    with (runtime / 'bridge.log').open('ab') as log:
        process = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=log,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            text=True, encoding='utf-8')
    result = queue.Queue()
    threading.Thread(target=lambda: result.put(process.stdout.readline()), daemon=True).start()
    try:
        line = result.get(timeout=15)
        ready = json.loads(line)
        target = local_url(ready['endpoint'])
        health = request(target, '/v1/health', key=key)
        if health.get('callerNativeId') != os.environ['CODEX_THREAD_ID'] or health.get('status') != 'ready':
            raise ValueError('The bridge did not verify its current Codex caller')
        profile = input_profile(matches[0].get('profile'))
        profile['control'] = {'protocol': 'http-json', 'endpoint': target}
        profile['capabilities'] = {
            'openChat': {'uriTemplate': 'codex://threads/{nativeId}'},
            'createChat': {'path': '/v1/chats/create', 'method': 'POST', 'idField': 'id', 'uriField': 'url',
                'timeoutSeconds': 30,
                'tool': 'codex-desktop-bridge.createChat', 'projectRouting': True,
                'arguments': {'prompt': '$prompt', 'workspace': '$workspace', 'requestId': '$requestId'}},
            'sendMessage': {'path': '/v1/chats/send', 'method': 'POST', 'projectRouting': True,
                'timeoutSeconds': 20,
                'tool': 'codex-desktop-bridge.sendMessage',
                'arguments': {'prompt': '$prompt', 'workspace': '$workspace',
                              'requestId': '$requestId', 'nativeId': '$nativeId'}}}
        metadata = runtime / 'connection.json'
        ready.update(connection=connection, projectRouting=health['projectRouting'],
                     projectBindings=health['projectBindings'], saved=False, probeStarted=False)
        metadata.write_text(json.dumps(ready, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        registration = {'action': 'configure-integration', 'id': connection, 'profile': profile,
            'expectedProfileRevision': matches[0].get('profileRevision'), 'protocol': 'http-json',
            'endpoint': target, 'apiKey': key, 'requestId': secrets.token_hex(16)}
        try:
            saved = request(base, '/api/v1/connections', registration)
        except Exception:
            # A dropped acknowledgement must not tear down a committed route.
            try:
                rows = request(base, '/api/connections')['bindings']
            except Exception:
                ready['registrationOutcome'] = 'unknown'
                ready['requiresReconciliation'] = True
                return ready  # Keep the possibly committed endpoint alive.
            current = next(row for row in rows if row['id'] == connection)
            # Compare declarative input after removing generated annotations.
            if input_profile(current.get('profile')) != profile or (current.get('control') or {}).get('endpoint') != target or not current['control'].get('hasCredential'):
                raise
            saved = {'saved': True}
        if saved.get('saved') is not True:
            raise ValueError('Hub did not acknowledge the saved bridge connection')
        ready['saved'] = True
        try:
            metadata.write_text(json.dumps(ready, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        except OSError:
            ready['metadataWarning'] = True
        return ready
    except Exception:
        process.terminate()
        process.wait(timeout=5)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hub-url', required=True)
    parser.add_argument('--connection', required=True)
    parser.add_argument('--runtime-dir', required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(connect(args.hub_url, args.connection, args.runtime_dir), ensure_ascii=False))
    except ValueError as error:
        parser.exit(1, str(error) + '\n')
    except Exception:
        parser.exit(1, 'Codex bridge setup failed; inspect the private runtime log and connection settings.\n')


if __name__ == '__main__':
    main()
