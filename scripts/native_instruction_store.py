"""Coherent local instruction snapshots and a small native application rule.

Only the documented Codex user rule is automatically writable. Other clients
receive their native installation text; saving a snapshot does not claim loading.
The caller's OS/sandbox permissions remain in force for every write.
"""
from dataclasses import dataclass, replace
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid

from agent_instructions import validate_bundle, connection_context
import agent_sdk
from native_onboarding import OnboardingError, build_plan, merge_block, read_rule


def guarded(path, forbidden_roots=()):
    path = Path(path)
    if not path.is_absolute():
        raise OnboardingError('Native instruction locations must be absolute.')
    from hub_launcher import external_path
    path = external_path(path)
    if any(path == Path(root).resolve() or Path(root).resolve() in path.parents for root in forbidden_roots):
        raise OnboardingError('Native instructions must be outside the application/source tree.')
    for parent in (path, *path.parents):
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise OnboardingError('Native instruction paths must not contain reparse points.')
    return path


def atomic(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.hub-instructions-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(name, stat.S_IMODE(path.stat().st_mode))
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@dataclass(frozen=True)
class BundlePlan:
    native: object
    files: tuple
    manifest: dict
    @property
    def host(self): return self.native.host
    @property
    def workspace(self): return self.native.workspace
    @property
    def mcp(self): return self.native.mcp
    @property
    def forbidden_roots(self): return self.native.forbidden_roots
    @property
    def registration(self): return self.native.registration
    @property
    def fingerprint(self):
        value = [self.native.fingerprint, [(str(p), hashlib.sha256(b or b'').hexdigest(),
                  b is not None, hashlib.sha256(a).hexdigest()) for p,b,a in self.files]]
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
    def preview(self):
        result = self.native.preview()
        result.update(previewSha256=self.fingerprint, instructionManifest=self.manifest,
                      instructionFiles=[dict(path=str(p), changed=b != a) for p,b,a in self.files],
                      globalRuleRequired=True)
        return result


def build_bundle_plan(host, connection, bundle, *, instructions_home=None, native_home=None,
                      forbidden_roots=(), connection_path=None, workspace=None):
    validate_bundle(bundle)
    if connection.get('scope') != 'global':
        raise OnboardingError('Versioned global rules require a global MCP connection.')
    native = build_plan(host, connection, 'Managed instruction snapshot.', forbidden_roots=forbidden_roots,
                        connection_path=connection_path)
    server = agent_sdk.mcp_server_name(connection)
    descriptor = connection_context(connection['binding'],connection['baseUrl'])
    remote=bundle.get('connectionContext')
    if remote is not None and (not isinstance(remote,dict) or set(remote)!={'connection','baseUrl'} or
                              connection_context(remote.get('connection'),remote.get('baseUrl'))!=descriptor):
        raise OnboardingError('The Hub connection changed; repair the enrolled private/native configuration before installing rules.')
    user_home = guarded(native_home or os.environ.get('CODEX_HOME', str(Path.home()/'.codex')), forbidden_roots)
    default = user_home/'project-hub'/server if host == 'codex' else Path.home()/'.project-hub/instructions'/server
    home = guarded(instructions_home or default, forbidden_roots)
    workspace = workspace or connection.get('workspace')
    if workspace and (home == Path(workspace).resolve() or Path(workspace).resolve() in home.parents):
        raise OnboardingError('Global instruction snapshots must be outside the project.')
    if workspace and connection_path and Path(connection_path).resolve().is_relative_to(Path(workspace).resolve()):
        raise OnboardingError('Keep the credential file outside the managed source workspace.')
    snapshot = home/bundle['manifest']['revision']
    pointer = home/'current.json'
    try:
        current = json.loads((read_rule(pointer) or b'{}').decode('utf-8'))
        candidate = Path(current.get('paths',{}).get('workflow.md','')).parent
        if current.get('revision')==bundle['manifest']['revision'] and candidate.is_relative_to(home) and candidate!=home:
            snapshot = guarded(candidate,forbidden_roots)
    except (ValueError,OnboardingError):
        pass
    if snapshot.exists():
        expected_manifest = dict(bundle['manifest'],connectionContext=descriptor,paths={name:(snapshot/name).as_posix() for name in bundle['files']})
        try:
            intact = all(read_rule(snapshot/name)==content.encode('utf-8') for name,content in bundle['files'].items())
            intact = intact and read_rule(snapshot/'manifest.json')==(json.dumps(expected_manifest,ensure_ascii=False,indent=2)+'\n').encode()
        except OnboardingError:
            intact = False
        if not intact:
            # Never mutate a published snapshot. Repair publishes a new complete
            # directory through the final atomic native-rule replacement.
            snapshot = home/(bundle['manifest']['revision']+'-'+uuid.uuid4().hex)
    manifest_path = snapshot/'manifest.json'
    body = ('## Project Hub — global MCP rule\n\n'
            f'MCP connection: {server}. Hub: {descriptor["baseUrl"]}. Connection ID: {connection["binding"]}.\n'
            f'Local manifest: {manifest_path.as_posix()}. Bundle revision: {bundle["manifest"]["revision"]}.\n'
            'The manifest names absolute local paths; read BOTH instruction files at startup and after compaction.\n\n'
            + bundle['files']['bootstrap.md'])
    if connection['token'] in body or any(connection['token'] in value for value in bundle['files'].values()):
        raise OnboardingError('Credentials must not be saved in instructions.')
    files = []
    for name, content in bundle['files'].items():
        target = guarded(snapshot/name, forbidden_roots)
        files.append((target, read_rule(target), content.encode('utf-8')))
    manifest = dict(bundle['manifest'], connectionContext=descriptor, paths={name:(snapshot/name).as_posix() for name in bundle['files']})
    files.append((manifest_path, read_rule(manifest_path), (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode()))
    files.append((pointer, read_rule(pointer), (json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode()))
    path = before = after = None
    if host == 'codex':
        override = guarded(user_home/'AGENTS.override.md', forbidden_roots)
        path = override if (read_rule(override) or b'').strip() else guarded(user_home/'AGENTS.md', forbidden_roots)
        before = read_rule(path)
        after = merge_block(before, body, begin=f'<!-- project-hub:global:{server}:start -->'.encode(),
                            end=f'<!-- project-hub:global:{server}:end -->'.encode())
        if len(after) > 32000:
            raise OnboardingError('Global rules exceed the default Codex instruction limit; reconcile the native size setting.')
    native = replace(native, path=path, before=before, after=after, rule=body,
                     limitations=tuple(item for item in native.limitations if 'does not choose or write' not in item)+(
                         'Full files require explicit reads; persistence does not prove new-chat loading or compaction behavior.',))
    return BundlePlan(native, tuple(files), manifest)


def apply_bundle_plan(plan, *, expected_preview):
    if expected_preview != plan.fingerprint:
        raise OnboardingError('Preview this exact instruction snapshot before applying it.')
    native = plan.native
    targets = list(plan.files)+([(native.path, native.before, native.after)] if native.path else [])
    for path,before,after in targets:
        guarded(path, native.forbidden_roots)
        if read_rule(path) != before:
            raise OnboardingError('Instructions changed after preview; preview the new snapshot.')
    changed = False
    # Immutable snapshot first, native rule last: every published rule references
    # a complete snapshot. Failed writes can be retried without deleting history.
    for path,before,after in targets:
        if before != after:
            guarded(path, native.forbidden_roots)
            if read_rule(path) != before:
                raise OnboardingError('Instructions changed during installation; preview again.')
            atomic(path, after)
            changed = True
    return dict(changed=changed, rulePath=str(native.path) if native.path else None,
                instructionManifest=plan.manifest, bundleSaved=True,
                bootstrapSha256=hashlib.sha256(native.rule.encode()).hexdigest(),connectionId=plan.manifest['connectionContext']['connection'],
                instructionsPersisted=native.path is not None, persistentRule=native.rule,
                setupVerified=False)
