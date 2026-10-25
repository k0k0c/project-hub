"""Build a deterministic local handoff ZIP; never include live project data."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (
    'work_reconciliation_api.py',
    'outbound_http.py', 'chatgpt_auth.py',
    'project_portal.py', 'setup_wizard.py', 'hub_launcher.py', 'hub_lifecycle.py', 'hub_desktop.py', 'hub_tray.py', 'hub_instance.py', 'hub_source.py', 'hub_update.py', 'hub_import.py', 'project_registry.py', 'project_resolution.py', 'hub_storage_schema.py', 'ui_preferences.py',
    'plugin_api.py', 'agent_api.py', 'agent_bindings.py', 'agent_runtime.py', 'agent_contracts.py', 'agent_instructions.py', 'connection_capabilities.py', 'native_chats.py', 'storage_preparation.py', 'agent_sdk.py', 'hub_cli.py', 'native_onboarding.py', 'native_mcp_setup.py', 'mcp_stdio_client.py', 'provider_runtime.py', 'project_workspaces.py', 'mcp_transport.py', 'task_transfer.py', 'stage_operations.py', 'task_progress.py',
    'storage_merge.py', 'storage_operations.py', 'storage_application.py', 'windows_storage_broker.py', 'local_files.py',
    'agent-workflow.md', 'native_instruction_store.py', 'native_project_rule.py', 'project_bindings.py', 'agent_launches.py',
    'completion_policy.py', 'codex_session_catalog.py', 'codex_desktop_setup.py', 'codex_desktop_bridge.mjs', 'check_runs.py',
    'knowledge_store.py', 'subsystem_actions.py', 'knowledge_html.py', 'knowledge_scan.py', 'knowledge_research.py', 'knowledge_lsp.py', 'knowledge_language.py', 'ArchitectureSourceScanner.java',
    'image_sources.py', 'git_safety_check.py', 'prepare_project_hub_plugin.py',
    'project_hub_client_entry.py', 'backup_project_hub.py', 'hub_backup.py', 'backup_api.py', 'backup_session.py', 'project_hub_knowledge.py',
    'codex_adapter.py', 'hub_chat_actions.py', 'hub_action_context.py', 'legacy_action_receipts.py', 'hub_project_review.py', 'secret_vault.py', 'agent_providers.py', 'api_agent_runs.py', 'research_api.py', 'research_sources.py', 'internal_operations.py', 'unified_actions.py',
    'artifact_store.py', 'source_snapshots.py', 'git_batch_store.py', 'task_chats.py',
    'read_models.py', 'journal_append.py', 'prepared_sources.py',
    'request_metrics.py', 'runtime_diagnostics.py', 'event_broker.py', 'portal_asgi.py', 'file_freshness.py', 'sqlite_pool.py', 'multiprocess_dispatch.py',
)
TEXT_SUFFIXES = {'.py', '.ps1', '.java', '.js', '.mjs', '.json', '.css', '.html', '.md', '.txt', '.svg'}


def distribution_bytes(path):
    data = path.read_bytes()
    if path.suffix.lower() in TEXT_SUFFIXES or 'LICENSE' in path.name:
        data.decode('utf-8')  # Fail clearly rather than corrupt an unexpected encoding.
        data = data.replace(b'\r\n', b'\n')
    return data


def build(output, root=ROOT, *, standalone=False):
    root = Path(root).resolve()
    payload = {}

    def add(source, name=None):
        source = Path(source)
        if source.is_symlink() or not source.resolve().is_relative_to(root):
            raise ValueError('Distribution input must be a regular file inside the source root')
        name = name or source.relative_to(root).as_posix()
        payload[name] = distribution_bytes(source)

    for filename in RUNTIME:
        if standalone and filename in {'codex_adapter.py', 'hub_chat_actions.py', 'mcp_stdio_client.py'}:
            continue
        add(root / 'scripts' / filename)
    for relative in ('tools/project-portal/web', 'tools/project-portal/plugins/project-hub'):
        for path in sorted((root / relative).rglob('*')):
            if path.is_symlink():
                raise ValueError('Symlinks are not distribution inputs')
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                add(path)
    for relative in ('setup_project_hub.py', 'SOURCE-NOTICES.md', 'docs/local-installation.md', 'docs/legacy-plugin-installation.md',
                     'docs/plugin-publication-readiness.md', 'docs/check-wrapper.md', 'docs/hub-instructions.md', 'docs/mcp-project-connections.md', 'docs/codex-desktop-control.md',
                     'docs/codex-adapter.md', 'docs/agent-actions.md', 'docs/agent-analysis.md', 'docs/architecture-workspace.md', 'docs/project-portal/language-providers.md', 'docs/project-portal/knowledge.md', 'requirements-images.txt',
                     'requirements-server.txt', 'requirements-desktop.txt', 'docs/hub-performance-runtime.md', 'docs/backups.md', 'docs/backup-format.md', 'docs/project-spaces.md', 'docs/windows-installer.md'):
        if standalone and relative in {'setup_project_hub.py', 'docs/legacy-plugin-installation.md', 'docs/codex-adapter.md', 'docs/agent-actions.md'}:
            continue
        add(root / relative)
    add(root / ('docs/windows-installer.md' if standalone else 'docs/local-installation.md'), 'README.md')
    payload['README.md'] = payload['README.md'].replace(
        b'(plugin-publication-readiness.md)', b'(docs/plugin-publication-readiness.md)')
    payload['README.md'] = payload['README.md'].replace(b'(check-wrapper.md)', b'(docs/check-wrapper.md)')
    for name in ('project-spaces.md', 'backups.md', 'backup-format.md', 'legacy-plugin-installation.md', 'windows-installer.md', 'agent-analysis.md'):
        payload['README.md'] = payload['README.md'].replace(('('+name+')').encode(), ('(docs/'+name+')').encode())
    manifest = json.loads(payload['tools/project-portal/plugins/project-hub/plugin.json'])
    revision = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True)
    dirty = subprocess.run(['git', '-C', str(root), 'status', '--porcelain'],
                           capture_output=True, text=True)
    files = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payload.items())}
    tree = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    metadata = dict(schemaVersion=1, name='project-hub', version=manifest['version'],
        sourceRevision=revision.stdout.strip() if revision.returncode == 0 else None,
        sourceDirty=bool(dirty.stdout) if dirty.returncode == 0 else None,
        sourceTreeSha256=tree, lineEndings='LF for UTF-8 text; binary assets unchanged', files=files)
    payload['distribution.json'] = (json.dumps(metadata, sort_keys=True, indent=2) + '\n').encode()
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payload.items()):
            info = zipfile.ZipInfo('project-hub-' + manifest['version'] + '/' + name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data, compresslevel=9)
    return dict(path=str(output), sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                files=len(files), **{k: metadata[k] for k in ('version', 'sourceRevision', 'sourceDirty', 'sourceTreeSha256')})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))


if __name__ == '__main__':
    main()
