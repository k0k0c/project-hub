"""Exercise two installed MCP processes in an isolated project; no models or live claims."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import time


class Client:
    def __init__(self, command, root, env, session):
        self.process = subprocess.Popen(command, cwd=root,
            env={**env, 'CODEX_THREAD_ID': session, 'CODEX_SESSION_ID': session},
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', bufsize=1)
        self.messages = queue.Queue()
        self.errors = []
        self.counter = 0
        def reader():
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except ValueError:
                    self.messages.put({'invalid': line[:200]})
        def errors():
            for line in self.process.stderr:
                self.errors.append(line[:200])
        self.readers = [threading.Thread(target=reader, daemon=True), threading.Thread(target=errors, daemon=True)]
        for thread in self.readers:
            thread.start()

    def request(self, method, params):
        self.counter += 1
        rid = self.counter
        self.process.stdin.write(json.dumps(dict(jsonrpc='2.0', id=rid, method=method, params=params)) + '\n')
        self.process.stdin.flush()
        response = self.messages.get(timeout=10)
        if response.get('id') != rid or 'result' not in response:
            raise AssertionError(response)
        return response['result']

    def call(self, name, arguments, error=False):
        response = self.request('tools/call', dict(name=name, arguments=arguments))
        value = json.loads(response['content'][0]['text'])
        assert bool(response.get('isError')) == error, value
        return value

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait()
        for thread in self.readers:
            thread.join(timeout=1)
        self.process.stdout.close()
        self.process.stderr.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin-root', type=Path, default=Path.home() / 'plugins/project-hub')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    plugin = args.plugin_root.resolve()
    manifest = json.loads((plugin / '.codex-plugin/plugin.json').read_text(encoding='utf-8'))
    config = json.loads((plugin / '.mcp.json').read_text(encoding='utf-8'))['mcpServers']['project_hub']
    command = [config['command'], *config['args']]
    checks = []
    clients = []
    result = dict(pluginVersion=manifest['version'], command=command, checks=checks,
                  processCount=2, modelCalls=0, realCodexChats=0, liveProjectWrites=0,
                  scope='Installed MCP transport and shared-store acceptance; not two-model behavior')
    result['sourceSha256'] = {name: hashlib.sha256((plugin / 'scripts' / name).read_bytes()).hexdigest()
                              for name in ('hub_core.py', 'hub_plugin.py')}
    try:
        with tempfile.TemporaryDirectory(prefix='hub-coordination-') as temp:
            root = Path(temp) / 'project'
            data = root / 'docs/project-portal'
            data.mkdir(parents=True)
            (data / 'project.json').write_text(json.dumps(dict(schemaVersion=1, id='acceptance', name='Acceptance',
                tasks=[dict(id='task', title='Acceptance', status='active', stages=[])])), encoding='utf-8')
            env = {**os.environ, 'PROJECT_HUB_HOME': str(Path(temp) / 'state'), 'PYTHONIOENCODING': 'utf-8'}
            subprocess.run([config['command'], str(plugin / 'scripts/hub_plugin.py'), 'register', '--root', str(root)],
                           env=env, check=True, capture_output=True, timeout=10)
            try:
                for sid in ('acceptance-a', 'acceptance-b'):
                    client = Client(command, root, env, sid)
                    clients.append(client)
                    initialized = client.request('initialize', dict(protocolVersion='2025-03-26', capabilities={},
                        clientInfo=dict(name='hub-acceptance', version='1')))
                    assert initialized['serverInfo']['name'] == 'project-hub'
                    assert len(client.request('tools/list', {})['tools']) == 5
                    client.call('hub_context', {})
                a, b = clients
                checks.append('two independent installed MCP servers initialized')
                step = dict(task='task', title='Implement shared function', resources=['src/shared'])
                work = a.call('hub_begin', step)
                denied = b.call('hub_begin', step, error=True)
                assert denied['error'] == 'resource_busy' and denied['conflicts'][0]['session'] == 'acceptance-a'
                checks.append('competing writer refused with owner information')
                other = b.call('hub_begin', dict(task='task', title='Independent UI', resources=['src/ui']))
                checks.append('non-overlapping work proceeds while shared resource is busy')
                invalid = b.call('hub_report', dict(work=work['work'], revision=work['revision'],
                    result='Cannot close someone else', status='done'), error=True)
                assert invalid['error'] == 'not_owner'
                checks.append('other session cannot release the owner reservation')
                cursor = b.call('hub_context', {})['cursor']
                submitted = threading.Event()
                def wait_for_change():
                    submitted.set()
                    return b.call('hub_wait', dict(after=cursor, seconds=5))
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    waiting = pool.submit(wait_for_change)
                    submitted.wait(timeout=2)
                    time.sleep(.4)
                    assert not waiting.done(), 'Wait returned without any new work event'
                    a.call('hub_report', dict(work=work['work'], revision=work['revision'],
                        result='Shared function ready', checkpoint='Use completed shared function', status='done'))
                    delta = waiting.result(timeout=8)
                assert any(row['work'] == work['work'] and row['kind'] == 'work.done' for row in delta['changes'])
                checks.append('pending wait wakes on completion and delivers result')
                reused = b.call('hub_begin', step)
                assert reused['status'] == 'done' and reused['work'] == work['work'] and reused['result'] == 'Shared function ready'
                checks.append('matching completed work reused instead of duplicated')
                next_work = b.call('hub_begin', dict(task='task', title='Extend shared function', resources=['src/shared']))
                assert next_work['status'] == 'active'
                checks.append('released resource can be acquired for a different step')
                for current in (other, next_work):
                    b.call('hub_report', dict(work=current['work'], revision=current['revision'], result='Acceptance complete', status='done'))
                assert not b.call('hub_context', {})['active']
                result['passed'] = True
            finally:
                for client in clients:
                    client.close()
    except Exception as exc:
        result['passed'] = False
        result['failure'] = str(exc)[:500]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
