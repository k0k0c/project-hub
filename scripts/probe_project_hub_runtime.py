"""Read installed plugin/hook descriptors from Codex without a model call or new chat."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    process = subprocess.Popen(['codex', 'app-server', '--stdio'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
    messages = queue.Queue()
    def reader():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                pass
    threading.Thread(target=reader, daemon=True).start()
    def drain():
        for _ in process.stderr:
            pass  # Do not copy account/runtime logs into project evidence.
    threading.Thread(target=drain, daemon=True).start()
    def request(rid, method, params):
        process.stdin.write(json.dumps(dict(id=rid, method=method, params=params)) + '\n')
        process.stdin.flush()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            message = messages.get(timeout=max(.01, deadline - time.monotonic()))
            if message.get('id') == rid:
                return message
        raise TimeoutError(method)
    try:
        initialized = request(1, 'initialize', dict(clientInfo=dict(name='project-hub-probe', version='0.1.0'),
                                                  capabilities=dict(experimentalApi=True)))
        process.stdin.write(json.dumps(dict(method='initialized')) + '\n')
        process.stdin.flush()
        hooks = request(2, 'hooks/list', dict(cwds=[str(root)]))
        plugin = request(3, 'plugin/read', dict(pluginName='project-hub',
                    marketplacePath=str(Path.home() / '.agents/plugins/marketplace.json')))
        # Retain only this plugin's descriptors; no unrelated local configuration.
        def filter_hooks(value):
            if isinstance(value, list):
                return [filter_hooks(v) for v in value if 'project-hub' in json.dumps(v)]
            if isinstance(value, dict):
                return {k: filter_hooks(v) for k, v in value.items()}
            return value
        result = dict(version=subprocess.check_output(['codex', '--version'], text=True).strip(),
                      initialized='result' in initialized, hooks=filter_hooks(hooks), plugin=plugin,
                      modelCalls=0, newChats=0, hooksFired=False,
                      note='Descriptor discovery is not a live SessionStart test. Trust has not been changed.')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(result, ensure_ascii=False))
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == '__main__':
    main()
