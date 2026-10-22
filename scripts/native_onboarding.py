"""Preview and merge a credential-free owned rule for a native agent host.

MCP registration and private credential provisioning use the host's native
configuration. This adapter merges only the explicitly previewed project rule.
"""
import argparse
from dataclasses import dataclass, replace
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

import agent_sdk


BEGIN = b'<!-- project-hub:onboarding:start v1 -->'
END = b'<!-- project-hub:onboarding:end -->'
MAX_RULE_BYTES = 512_000
SOURCES = {
    'codexMcp': 'https://developers.openai.com/codex/mcp/',
    'codexCli': 'https://developers.openai.com/codex/cli/reference/',
    'codexRules': 'https://developers.openai.com/codex/guides/agents-md/',
    'cursorMcp': 'https://cursor.com/docs/mcp',
    'cursorRules': 'https://cursor.com/docs/rules',
    'cursorExtension': 'https://cursor.com/docs/extension-api',
}


class OnboardingError(ValueError):
    pass


def safe_path(value, forbidden_roots=()):
    try:
        path = Path(value)
    except TypeError:
        raise OnboardingError('Select an explicit absolute project or configuration path.') from None
    if not path.is_absolute():
        raise OnboardingError('Select an explicit absolute project or configuration path.')
    if any(part.lower() in ('.agents', '.codex') for part in path.parts):
        raise OnboardingError('This adapter does not write protected agent configuration directories.')
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise OnboardingError('Paths containing symlinks or reparse points are not supported.')
    resolved = path.resolve()
    application = Path(agent_sdk.__file__).resolve().parents[1]
    if application.name == 'app' and (application.parent / 'runtime' / 'python.exe').is_file():
        application = application.parent
    roots = [application, *map(Path, forbidden_roots)]
    if any(resolved == root.resolve() or root.resolve() in resolved.parents for root in roots):
        raise OnboardingError('Native rules and private configuration must be outside the Hub application/source tree.')
    return resolved


def read_rule(path):
    try:
        with path.open('rb') as stream:
            data = stream.read(MAX_RULE_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(data) > MAX_RULE_BYTES:
        raise OnboardingError('The instruction file exceeds the supported preview size.')
    try:
        data.decode('utf-8-sig')
    except UnicodeError:
        raise OnboardingError('The instruction file is not UTF-8; preserve it and convert it separately.') from None
    return data


def merge_block(original, body, *, begin=BEGIN, end=END):
    """Preserve every byte outside the single owned block, including its EOLs."""
    original = original or b''
    eol = b'\r\n' if b'\r\n' in original else b'\n'
    block = begin + eol + body.replace('\r\n', '\n').replace('\r', '\n').encode('utf-8').replace(b'\n', eol) + eol + end
    starts, ends = original.count(begin), original.count(end)
    if starts or ends:
        if starts != 1 or ends != 1:
            raise OnboardingError('Owned rule markers are incomplete or duplicated; reconcile them manually.')
        pattern = re.compile(rb'^' + re.escape(begin) + rb'\r?\n.*?^' + re.escape(end) + rb'(?=\r?$)', re.M | re.S)
        match = pattern.search(original)
        if not match:
            raise OnboardingError('Owned rule markers must be complete separate lines.')
        return original[:match.start()] + block + original[match.end():]
    separator = b'' if not original else eol + (b'' if original.endswith(eol) else eol)
    return original + separator + block + eol


def cursor_frontmatter(original):
    if not original:
        return b'---\ndescription: Project Hub workflow for this project\nalwaysApply: true\n---\n\n'
    match = re.match(rb'\A(?:\xef\xbb\xbf)?---\r?\n(.*?)\r?\n---(?:\r?\n|$)', original, re.S)
    if not match:
        raise OnboardingError('Existing Cursor rule lacks frontmatter; reconcile it manually before merging.')
    fields = re.findall(rb'^\s*alwaysApply\s*:\s*([^\r\n]+)', match[1], re.M)
    if len(fields) != 1 or fields[0].strip().lower() != b'true':
        raise OnboardingError('Existing Cursor rule is not Always Apply; its activation setting is preserved.')
    return original


@dataclass(frozen=True)
class Plan:
    host: str
    workspace: Path | None
    path: Path | None
    before: bytes | None
    after: bytes | None
    mcp: dict
    steps: tuple
    limitations: tuple
    forbidden_roots: tuple
    registration: object = None
    rule: str | None = None

    @property
    def fingerprint(self):
        value = dict(host=self.host, path=str(self.path) if self.path else None,
                     before=hashlib.sha256(self.before or b'').hexdigest(), exists=self.before is not None,
                     after=hashlib.sha256(self.after or b'').hexdigest(), mcp=self.mcp,
                     steps=self.steps, limitations=self.limitations,
                     rule=self.rule,
                     registration=self.registration.preview() if self.registration else None)
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    def preview(self):
        diff = '' if self.path is None else ''.join(difflib.unified_diff(
            (self.before or b'').decode('utf-8-sig').splitlines(keepends=True),
            (self.after or b'').decode('utf-8-sig').splitlines(keepends=True),
            fromfile=str(self.path), tofile=str(self.path)))
        return dict(host=self.host, rulePath=str(self.path) if self.path else None,
                    previewSha256=self.fingerprint, changed=self.before != self.after,
                    ruleDiff=diff, mcp=self.mcp, steps=list(self.steps), limitations=list(self.limitations),
                    setupVerified=False, sources=SOURCES,
                    persistentRule=self.rule,
                    registration=self.registration.preview() if self.registration else None)


def build_plan(host, connection, workflow, *, workspace=None, forbidden_roots=(), connection_path=None,
               instructions_home=None, native_home=None):
    if isinstance(workflow, dict):
        from native_instruction_store import build_bundle_plan
        return build_bundle_plan(host, connection, workflow, instructions_home=instructions_home,
                                 native_home=native_home, forbidden_roots=forbidden_roots,
                                 connection_path=connection_path, workspace=workspace)
    if host not in ('codex', 'cursor', 'generic'):
        raise OnboardingError('Supported adapters are codex, cursor and generic.')
    if not isinstance(connection, dict):
        raise OnboardingError('An enrolled Hub connection is required.')
    global_connection = connection.get('scope') == 'global'
    if not global_connection and (not isinstance(connection.get('project'),str) or not connection['project'].strip()):
        raise OnboardingError('An enrolled Hub connection is required.')
    try:
        client = agent_sdk.Client(connection.get('baseUrl'), connection.get('token'))
    except (TypeError, ValueError) as error:
        raise OnboardingError('The enrolled connection URL or credential is invalid.') from error
    if not client.token:
        raise OnboardingError('An enrolled Hub credential is required.')
    if not isinstance(workflow, str) or not workflow.strip() or len(workflow.encode()) > 160_000:
        raise OnboardingError('Supply the bounded full workflow obtained during setup.')
    if 'project-hub:onboarding:' in workflow or client.token in workflow or any(
            isinstance(connection.get(key), str) and connection[key] and connection[key] in workflow
            for key in ('invitation',)):
        raise OnboardingError('The workflow contains an ownership marker or credential; do not persist it.')
    project = connection.get('project')
    if project is not None and (not isinstance(project,str) or len(project)>128 or any(ord(char)<32 for char in project) or 'project-hub:onboarding:' in project):
        raise OnboardingError('Invalid project identifier.')
    binding = connection.get('binding', '')
    if not isinstance(binding, str) or len(binding) > 128 or any(ord(char) < 32 for char in binding):
        raise OnboardingError('Invalid enrollment binding identifier.')
    try:
        server = agent_sdk.mcp_server_name(connection)
    except ValueError as error:
        raise OnboardingError(str(error)) from error
    suffix = server.removeprefix('project_hub_')
    variable = 'PROJECT_HUB_TOKEN_' + suffix.upper()
    # Use the reserved local hostname for native HTTP clients. Some system
    # proxy implementations bypass localhost but send numeric loopback through
    # their proxy; changing global proxy/environment settings is unnecessary.
    url = agent_sdk.mcp_http_endpoint(client.baseUrl)
    limitations = [
        'Provision the credential through a private secret store or an environment variable available to the host process; this adapter never writes the token.',
        'Native permissions, trust prompts and existing host approval settings remain unchanged.',
        'Verify hub_context with a distinct current conversation session and verify the persistent rule in a new conversation before claiming setup complete.',
        'A local rule does not register a code folder in Hub or prove that every future host conversation loads it.',
    ]
    if host == 'codex':
        entry = dict(url=url,bearer_token_env_var=variable)
        mcp = dict(format='streamable-http', nativeFormat='toml',entry=entry,privateTarget='user Codex config.toml', server=server, credentialEnvironment=variable,
                   fragment=f'[mcp_servers.{server}]\nurl = {json.dumps(url)}\nbearer_token_env_var = {json.dumps(variable)}\n')
        steps = (dict(action='review-existing-server', argv=['codex', 'mcp', 'list']),
                 dict(action='manual-registration-after-review', argv=['codex', 'mcp', 'add', server, '--url', url, '--bearer-token-env-var', variable]))
    else:
        entry = dict(url=url,headers={'Authorization':'Bearer ${env:' + variable + '}'})
        config = dict(mcpServers={server:entry})
        mcp = dict(format='streamable-http', nativeFormat='json',entry=entry,privateTarget='user Cursor mcp.json' if host == 'cursor' else 'host-specific private MCP configuration',
                   server=server, credentialEnvironment=variable, fragment=config)
        steps = (dict(action='manual-merge-after-review', instruction='Merge only this server into native private MCP configuration, preserving unrelated servers. Do not place the credential in source control.'),)
        if host == 'cursor':
            limitations.append('Cursor registerServer is an extension-host API; this Python adapter cannot invoke it or claim persistent runtime registration.')
        else:
            limitations.append('The generic adapter cannot discover or modify arbitrary applications. Persistent rule and MCP APIs require a host-specific adapter or manual setup; environment interpolation syntax is only verified for Cursor.')
            mcp = dict(format='host-specific-plan', server=server, endpoint=url,
                       authentication='Bearer', credentialEnvironment=variable)
    if connection_path is not None:
        private = safe_path(connection_path, forbidden_roots)
        if agent_sdk.load_connection(private) != connection:
            raise OnboardingError('The private connection differs from the previewed enrollment.')
        target_root = workspace or connection.get('workspace')
        if target_root and private.is_relative_to(Path(target_root).resolve()):
            raise OnboardingError('Keep the credential file outside the managed source workspace.')
    credential_instruction = f'Its Hub credential is supplied privately through {variable}; never copy its value into instructions.'
    selection = ('This is a global Hub connection. Call hub_projects to discover registered projects, then supply an explicit project '
                 'and an optional registered code workspace on every project tool request. Do not infer them from another conversation.\n'
                 if global_connection else f'Legacy bound project ID: {json.dumps(project, ensure_ascii=False)}.\n')
    body = ('## Project Hub connection\n\n' + selection +
            f'Use the native Streamable HTTP MCP connection named {server}. {credential_instruction}\n'
            'Use a distinct session for each conversation and each child agent. Read hub_context and current projectSettings before substantive work.\n\n'
            + workflow.rstrip())
    if client.token in body:
        raise OnboardingError('The generated rule would expose a credential.')
    if host == 'generic' or (global_connection and not workspace and not connection.get('workspace')):
        limitations.append('Persist the displayed credential-free rule through the host\'s native global instruction mechanism. This adapter does not choose or write a protected user instruction file.')
        return Plan(host,None,None,None,None,mcp,steps,tuple(limitations),tuple(forbidden_roots),rule=body)
    target = workspace or connection.get('workspace')
    if not target:
        raise OnboardingError('Select an explicit local workspace; do not infer one from the Hub data directory.')
    root = safe_path(target, forbidden_roots)
    if not root.is_dir():
        raise OnboardingError('The selected workspace does not exist.')
    bound = connection.get('workspace')
    if bound is not None and safe_path(bound, forbidden_roots) != root:
        raise OnboardingError('The selected workspace differs from the enrolled workspace.')
    path = safe_path(root / ('AGENTS.md' if host == 'codex' else '.cursor/rules/project-hub.mdc'), forbidden_roots)
    if host == 'codex':
        override = safe_path(root / 'AGENTS.override.md', forbidden_roots)
        if (read_rule(override) or b'').strip():
            raise OnboardingError('AGENTS.override.md overrides AGENTS.md here; choose a reviewed native instruction location manually.')
        limitations.append('Codex instruction discovery and size limits can affect nested projects; confirm the loaded rule in a new conversation.')
    before = read_rule(path)
    if before and client.token.encode() in before:
        raise OnboardingError('The existing rule contains this credential; redact it separately before previewing.')
    original = cursor_frontmatter(before) if host == 'cursor' else before
    after = merge_block(original, body)
    if len(after) > MAX_RULE_BYTES:
        raise OnboardingError('The merged instruction file exceeds the supported size.')
    return Plan(host, root, path, before, after, mcp, steps, tuple(limitations), tuple(forbidden_roots),rule=body)


def apply_plan(plan, *, expected_preview):
    from native_instruction_store import BundlePlan, apply_bundle_plan
    if isinstance(plan, BundlePlan):
        return apply_bundle_plan(plan, expected_preview=expected_preview)
    if expected_preview != plan.fingerprint:
        raise OnboardingError('Preview this exact plan and supply its preview fingerprint before applying it.')
    if plan.path is None or plan.after is None:
        if plan.registration is not None and plan.host in ('codex','cursor'):
            return dict(changed=False,rulePath=None,instructionsPersisted=False,
                        persistentRule=plan.rule,setupVerified=False)
        raise OnboardingError('This is a manual instruction plan and cannot write native host instruction files.')
    path = safe_path(plan.path, plan.forbidden_roots)
    if read_rule(path) != plan.before:
        raise OnboardingError('The rule changed after preview; build and review a new plan.')
    if plan.before == plan.after:
        return dict(changed=False, rulePath=str(path), setupVerified=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_path(path, plan.forbidden_roots)
    descriptor, temporary = tempfile.mkstemp(prefix='.hub-rule-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(plan.after)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644)
        safe_path(path, plan.forbidden_roots)
        if read_rule(path) != plan.before:
            raise OnboardingError('The rule changed while applying; review a new plan.')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return dict(changed=True, rulePath=str(path), setupVerified=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Preview a native Project Hub rule from a private enrolled connection.')
    parser.add_argument('--host', choices=('codex', 'cursor', 'generic'), required=True)
    parser.add_argument('--connection', type=Path, required=True, help='Private SDK connection file outside source control')
    parser.add_argument('--workflow', type=Path, help='Full workflow obtained during setup; defaults to the enrolled connection workflow')
    parser.add_argument('--refresh', action='store_true', help='Fetch the current verified instruction bundle through MCP-compatible Hub API')
    parser.add_argument('--session', help='Current conversation ID for instruction refresh')
    parser.add_argument('--workspace', type=Path)
    parser.add_argument('--instructions-home', type=Path, help='Managed instruction snapshots outside repositories')
    parser.add_argument('--native-home', type=Path, help='Documented native user instruction home (Codex: CODEX_HOME)')
    parser.add_argument('--application-home', type=Path, action='append', default=[], help='Additional application/source root to exclude')
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--register-mcp', action='store_true', help='Preview and register Streamable HTTP MCP using a private credential environment reference')
    parser.add_argument('--host-config', type=Path, help='Explicit native user configuration file; defaults to the host user home')
    parser.add_argument('--codex-executable', type=Path, help='Installed Codex executable when it is not on PATH')
    parser.add_argument('--expected-preview', help='Fingerprint returned by the preview of this exact plan')
    args = parser.parse_args(argv)
    try:
        private = safe_path(args.connection, args.application_home)
        connection = agent_sdk.load_connection(private)
        selected = args.workspace or connection.get('workspace')
        if selected and private.is_relative_to(Path(selected).resolve()):
            raise OnboardingError('Keep the credential file outside the managed source workspace.')
        if args.refresh:
            if not args.session:
                raise OnboardingError('Supply the current conversation session for instruction refresh.')
            workflow = agent_sdk.Client(connection['baseUrl'], connection['token'],session=args.session).call('hub_instructions',dict(action='read'))
        elif args.workflow:
            with args.workflow.open('rb') as stream:
                raw = stream.read(160_001)
            if len(raw) > 160_000:
                raise OnboardingError('The workflow exceeds the supported size.')
            workflow = raw.decode('utf-8-sig')
        else:
            workflow = connection.get('instructionBundle') or connection.get('workflow')
        plan = build_plan(args.host, connection, workflow, workspace=args.workspace, forbidden_roots=args.application_home,
                          connection_path=private, instructions_home=args.instructions_home, native_home=args.native_home)
        if args.register_mcp:
            from native_mcp_setup import build_registration, apply_registration
            registration = build_registration(plan,host_config=args.host_config,codex_executable=args.codex_executable)
            from native_instruction_store import BundlePlan
            plan = replace(plan, native=replace(plan.native, registration=registration)) if isinstance(plan, BundlePlan) else replace(plan, registration=registration)
        result = apply_plan(plan, expected_preview=args.expected_preview) if args.apply else plan.preview()
        if args.apply and plan.registration:
            result['mcpRegistration']=apply_registration(plan.registration)
            from native_mcp_setup import verify_registration
            result['mcpVerification']=verify_registration(plan.registration)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    raise SystemExit(main())
