"""Preview native MCP registration without copying credentials into host config."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import queue
import shutil
import subprocess
import tempfile
import threading
import time
import tomllib

from native_onboarding import OnboardingError, safe_path


def installed_codex():
    path = shutil.which('codex')
    if path:
        return path
    local = os.environ.get('LOCALAPPDATA')
    if local:
        candidates = [item for item in (Path(local)/'OpenAI/Codex/bin').glob('*/codex.exe') if item.is_file()]
        if candidates:
            return str(max(candidates,key=lambda item:item.stat().st_mtime))
    return None


def read_config(path):
    try:
        with path.open('rb') as stream:
            raw = stream.read(1_000_001)
    except FileNotFoundError:
        return None
    if len(raw) > 1_000_000:
        raise OnboardingError('The native MCP configuration exceeds the supported preview size.')
    return raw


def parse_config(host, raw):
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise ValueError('Duplicate configuration key')
            value[key]=item
        return value
    try:
        data = (tomllib.loads(raw.decode('utf-8-sig')) if host=='codex' else json.loads(raw.decode('utf-8-sig'),object_pairs_hook=unique)) if raw else {}
    except (ValueError, UnicodeError):
        raise OnboardingError('The native configuration could not be parsed; preserve it and repair it separately.') from None
    if not isinstance(data, dict):
        raise OnboardingError('Native MCP configuration must be an object.')
    name = 'mcp_servers' if host=='codex' else 'mcpServers'
    if not isinstance(data.get(name, {}),dict):
        raise OnboardingError('The native MCP server registry must be an object.')
    return data


def same_local_endpoint(left, right):
    """Allow only the two Hub loopback aliases, with identical port and path."""
    from urllib.parse import urlsplit
    try:
        a, b = urlsplit(left), urlsplit(right)
        return (a.scheme == b.scheme == 'http' and a.hostname in ('localhost','127.0.0.1')
                and b.hostname in ('localhost','127.0.0.1') and a.port == b.port
                and a.path == b.path == '/mcp' and not any((a.username,b.username,a.password,b.password,
                    a.query,b.query,a.fragment,b.fragment)))
    except (TypeError,ValueError):
        return False


@dataclass(frozen=True)
class Registration:
    host: str
    path: Path
    before: bytes | None
    server: str
    entry: dict
    executable: str | None

    def preview(self):
        return dict(host=self.host, configPath=str(self.path),
                    beforeSha256=hashlib.sha256(self.before or b'').hexdigest(), existed=self.before is not None,
                    server=self.server, entry=self.entry, executable=self.executable)


def build_registration(plan, *, host_config=None, codex_executable=None):
    if plan.host not in ('codex','cursor') or plan.mcp.get('format')!='streamable-http':
        raise OnboardingError('Automatic registration requires a documented Codex or Cursor Streamable HTTP plan.')
    # Codex configuration is written through its native CLI. The general rule
    # writer deliberately continues to reject protected agent directories.
    if plan.host=='codex':
        root = Path(os.environ.get('CODEX_HOME',str(Path.home()/'.codex')))
        path = Path(host_config) if host_config else root/'config.toml'
        if path.name!='config.toml':
            raise OnboardingError('Codex configuration must be a config.toml file in its selected user home.')
        safe_path(path.parent.parent,plan.forbidden_roots)
        from hub_launcher import external_path
        path = external_path(path)
        executable = str(codex_executable or installed_codex() or '')
        if not executable or not Path(executable).is_file():
            raise OnboardingError('Select the installed Codex executable to register its MCP server.')
        executable = str(Path(executable).resolve())
    else:
        path = safe_path(host_config or Path.home()/'.cursor/mcp.json',plan.forbidden_roots)
        executable = None
    if plan.workspace and (path==plan.workspace or plan.workspace in path.parents):
        raise OnboardingError('Select native user configuration outside the managed source workspace.')
    before = read_config(path)
    data = parse_config(plan.host,before)
    server,entry = plan.mcp['server'],plan.mcp['entry']
    existing = data.get('mcp_servers' if plan.host=='codex' else 'mcpServers',{}).get(server)
    if existing is not None and (not isinstance(existing,dict) or any(existing.get(key)!=value and
                                not (key=='url' and same_local_endpoint(existing.get(key),value)) for key,value in entry.items()) or
                                any(key in existing for key in ('command','args','env','env_vars','http_headers'))):
        raise OnboardingError('The generated MCP name belongs to a different configuration; preserve it and reconcile the conflict.')
    return Registration(plan.host,path,before,server,entry,executable)


def apply_registration(registration):
    r = registration
    from hub_launcher import external_path
    external_path(r.path)
    if read_config(r.path)!=r.before:
        raise OnboardingError('Native MCP configuration changed after preview; review a new plan.')
    before = parse_config(r.host,r.before)
    registry = 'mcp_servers' if r.host=='codex' else 'mcpServers'
    existing = before.get(registry,{}).get(r.server)
    if existing is not None and existing.get('url') == r.entry['url']:
        return dict(changed=False,server=r.server,configPath=str(r.path),registered=True)
    if existing is not None:
        # A narrowly scoped repair of an already owned local HTTP entry. Keep
        # every other server option and every unrelated byte/comment intact.
        if not same_local_endpoint(existing.get('url'),r.entry['url']):
            raise OnboardingError('The MCP endpoint differs; reconcile the connection before changing it.')
        if r.host == 'codex':
            pattern = re.compile(rb'(?m)^\[mcp_servers\.' + re.escape(r.server.encode()) + rb'\]\r?\n(?P<body>(?:(?!^\[)[\s\S])*)')
            match = pattern.search(r.before)
            if not match:
                raise OnboardingError('The native server section needs a reviewed endpoint repair.')
            section,count = re.subn(rb'(?m)^(\s*url\s*=\s*)(?:"[^"\r\n]*"|\x27[^\x27\r\n]*\x27)',
                lambda item:item[1]+json.dumps(r.entry['url']).encode(),match['body'])
            if count != 1:
                raise OnboardingError('The native server URL needs a reviewed endpoint repair.')
            encoded = r.before[:match.start('body')]+section+r.before[match.end('body'):]
        else:
            changed = {**before,registry:{**before[registry],r.server:{**existing,'url':r.entry['url']}}}
            encoded = (json.dumps(changed,ensure_ascii=False,indent=2)+'\n').encode()
        expected = {**before,registry:{**before[registry],r.server:{**existing,'url':r.entry['url']}}}
        if parse_config(r.host,encoded) != expected:
            raise OnboardingError('Endpoint repair would change other settings; preserve the native configuration.')
        descriptor,temporary = tempfile.mkstemp(prefix='.hub-mcp-',dir=r.path.parent)
        try:
            with os.fdopen(descriptor,'wb') as stream:
                stream.write(encoded);stream.flush();os.fsync(stream.fileno())
            if read_config(r.path) != r.before:
                raise OnboardingError('Native MCP configuration changed during repair; review a new plan.')
            os.replace(temporary,r.path)
        finally:
            try:os.unlink(temporary)
            except FileNotFoundError:pass
        return dict(changed=True,server=r.server,configPath=str(r.path),registered=True,endpointRepaired=True)
    if r.host=='codex':
        environment = os.environ.copy()
        environment['CODEX_HOME'] = str(r.path.parent)
        try:
            process = subprocess.run([r.executable,'mcp','add',r.server,'--url',r.entry['url'],
                                      '--bearer-token-env-var',r.entry['bearer_token_env_var']],
                                     env=environment,stdin=subprocess.DEVNULL,capture_output=True,timeout=60,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
        except subprocess.TimeoutExpired:
            raise OnboardingError('Native Codex MCP registration timed out; inspect the host configuration before retrying.') from None
        if process.returncode:
            raise OnboardingError('Native Codex MCP registration failed; inspect the host configuration and retry the same preview.')
    else:
        after = dict(before)
        after[registry] = {**before.get(registry,{}),r.server:r.entry}
        encoded = (json.dumps(after,ensure_ascii=False,indent=2)+'\n').encode()
        r.path.parent.mkdir(parents=True,exist_ok=True)
        safe_path(r.path)
        descriptor,temporary = tempfile.mkstemp(prefix='.hub-mcp-',dir=r.path.parent)
        try:
            with os.fdopen(descriptor,'wb') as stream:
                stream.write(encoded);stream.flush();os.fsync(stream.fileno())
            if read_config(r.path)!=r.before:
                raise OnboardingError('Native MCP configuration changed during registration; review a new plan.')
            os.replace(temporary,r.path)
        finally:
            try:os.unlink(temporary)
            except FileNotFoundError:pass
    actual = parse_config(r.host,read_config(r.path))
    entry = actual.get(registry,{}).get(r.server,{})
    if any(entry.get(key)!=value for key,value in r.entry.items()):
        raise OnboardingError('Native MCP registration could not be verified; preserve the configuration and inspect it.')
    remaining = {**actual,registry:{k:v for k,v in actual.get(registry,{}).items() if k!=r.server}}
    original = {**before,registry:before.get(registry,{})}
    if remaining!=original:
        raise OnboardingError('Unrelated native configuration changed during registration; preserve it and inspect the host.')
    return dict(changed=True,server=r.server,configPath=str(r.path),registered=True)


def verify_registration(registration, *, timeout=12):
    """Discover HTTP tools using an isolated installed host, without a chat.

    Codex's documented app-server control protocol is only a diagnostic client;
    the MCP transport remains Streamable HTTP. No proxy/environment settings,
    native configuration, conversations or project data are changed here.
    """
    r = registration
    result = dict(transport='streamable-http',nativeDiscoveryVerified=False,
                  conversationLoadVerified=False,server=r.server)
    if r.host != 'codex':
        return dict(result,state='manual',reason='Verify tools/list in the native client and test a fresh conversation.')
    entry = parse_config(r.host,read_config(r.path)).get('mcp_servers',{}).get(r.server,{})
    if any(entry.get(key)!=value for key,value in r.entry.items()):
        return dict(result,state='failed',reason='Native registration differs from the selected connection.')
    variable = r.entry['bearer_token_env_var']
    if not os.environ.get(variable):
        return dict(result,state='pending',reason='The native host credential environment is not available to this verifier.')
    from agent_runtime import tools
    expected = {item['name'] for item in tools()}
    environment = dict(os.environ,CODEX_HOME=str(r.path.parent))
    # The app-server reads the selected native configuration. Do not pass
    # per-server -c overrides here: quoted TOML names are interpreted as
    # literal server names by CodexCLI and can create invalid phantom entries.
    command = [r.executable,'app-server','--stdio']
    started = time.monotonic()
    process = None
    messages = queue.Queue(maxsize=4)
    def read_messages():
        while True:
            line = process.stdout.readline(1_000_001)
            if not line:
                try: messages.put_nowait(dict(kind='eof'))
                except queue.Full: pass
                return
            if len(line)>1_000_000:
                try: messages.put_nowait(dict(kind='protocol_error'))
                except queue.Full: pass
                return
            try: message = json.loads(line)
            except (ValueError,UnicodeError): continue
            if not isinstance(message,dict) or message.get('id') == 0 and 'error' in message:
                try: messages.put_nowait(dict(kind='protocol_error'))
                except queue.Full: pass
                return
            if message.get('id')==1:
                try: messages.put_nowait(dict(kind='message',message=message))
                except queue.Full: pass
                return
    def drain_errors():
        # Native logs may contain private host headers; never echo/store them.
        while process.stderr.read(4096): pass
    try:
        process = subprocess.Popen(command,env=environment,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
        readers = [threading.Thread(target=target,daemon=True) for target in (read_messages,drain_errors)]
        for reader in readers: reader.start()
        for message in (
            dict(id=0,method='initialize',params=dict(clientInfo=dict(name='project-hub-setup-verifier',version='1'),capabilities=dict(experimentalApi=True))),
            dict(method='initialized',params={}),
            dict(id=1,method='mcpServerStatus/list',params=dict(serverName=r.server,detail='toolsAndAuthOnly',limit=100))):
            try:
                process.stdin.write((json.dumps(message)+'\n').encode())
                process.stdin.flush()
            except (BrokenPipeError, OSError):
                exit_code = process.poll()
                return dict(result,state='failed',reason='native_process_exit',exitCode=exit_code,
                            elapsedSeconds=round(time.monotonic()-started,3))
        deadline = started + max(0.0, float(timeout))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return dict(result,state='failed',reason='native_timeout',
                            elapsedSeconds=round(time.monotonic()-started,3))
            try:
                event = messages.get(timeout=min(remaining,.1))
            except queue.Empty:
                if process.poll() is not None:
                    return dict(result,state='failed',reason='native_process_exit',
                                exitCode=process.poll(),elapsedSeconds=round(time.monotonic()-started,3))
                continue
            if event.get('kind') == 'eof':
                exit_code = process.poll()
                return dict(result,state='failed',reason='native_process_exit' if exit_code is not None else 'native_eof',
                            exitCode=exit_code,elapsedSeconds=round(time.monotonic()-started,3))
            if event.get('kind') == 'protocol_error':
                return dict(result,state='failed',reason='native_protocol_error',
                            elapsedSeconds=round(time.monotonic()-started,3))
            message = event.get('message',{})
            if 'error' in message:
                return dict(result,state='failed',reason='native_protocol_error',
                            elapsedSeconds=round(time.monotonic()-started,3))
            payload = message.get('result')
            if not isinstance(payload,dict) or not isinstance(payload.get('data'),list):
                return dict(result,state='failed',reason='native_protocol_error',
                            elapsedSeconds=round(time.monotonic()-started,3))
            servers = payload['data']
            break
        native = next((item for item in servers if isinstance(item,dict) and item.get('name')==r.server),{})
        if not native:
            return dict(result,state='failed',reason='target_server_missing',
                        elapsedSeconds=round(time.monotonic()-started,3))
        catalog = native.get('tools',{})
        if not isinstance(catalog,(dict,list)):
            return dict(result,state='failed',reason='catalog_incomplete',
                        elapsedSeconds=round(time.monotonic()-started,3))
        if isinstance(catalog,list):
            names = {item.get('name','').split('__')[-1] for item in catalog if isinstance(item,dict)}
        else:
            names = {item.get('name',key).split('__')[-1] for key,item in catalog.items() if isinstance(item,dict)}
        missing = sorted(expected-names)
        return dict(result,state='failed' if missing else 'verified',nativeDiscoveryVerified=not missing,
                    expectedTools=len(expected),discoveredTools=len(names),missingTools=missing,
                    elapsedSeconds=round(time.monotonic()-started,3))
    except queue.Empty:
        return dict(result,state='failed',reason='native_timeout',
                    elapsedSeconds=round(time.monotonic()-started,3))
    except (OSError,ValueError,TypeError,KeyError):
        return dict(result,state='failed',reason='Native HTTP MCP discovery failed; inspect the client diagnostics.')
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired: process.kill();process.wait(timeout=3)
            for reader in readers: reader.join(timeout=1)
            for stream in (process.stdin,process.stdout,process.stderr):
                try: stream.close()
                except OSError: pass
