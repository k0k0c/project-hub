"""Optional source-control capabilities; core Hub data does not require a VCS.

Git is the only implemented provider. Filesystem detection does not execute a
client, inspect repository configuration, or grant trust to a repository.
The legacy Git snapshot format remains durable for existing work/receipts.
"""
from pathlib import Path
import shutil


def workspace_status(root):
    """Cheap preflight for ordinary operations, with no VCS subprocesses."""
    client = dict(available=shutil.which('git') is not None)
    result = dict(provider=None, available=False, status='workspace_required',
                  workspaceRoot=None, repositoryRoot=None, client=client, operations=[])
    if root is None:
        return result
    try:
        path = Path(root).resolve()
        result['workspaceRoot'] = str(path)
        if not path.is_dir():
            return dict(result, status='workspace_unavailable')
        # A .git file is valid for linked worktrees and submodules. A project
        # may also be a subdirectory of its repository.
        marker = next((p for p in (path, *path.parents) if (p / '.git').exists()), None)
    except (OSError, RuntimeError):
        return dict(result, status='workspace_unavailable')
    if marker is None:
        return dict(result, status='no_repository')
    return dict(result, provider='git', repositoryRoot=str(marker),
                status='detected' if client['available'] else 'client_unavailable')


def inspect_workspace(root):
    """Explicit settings/diagnostic read; never part of task settings reads."""
    result = workspace_status(root)
    if result['status'] != 'detected':
        return result
    from git_integration import GitIntegrationError, _run
    try:
        top = _run(root, 'rev-parse', '--show-toplevel', timeout=3)
    except GitIntegrationError as error:
        return dict(result, status='client_unavailable' if error.reason_code == 'git_client_unavailable'
                    else 'repository_unavailable', reasonCode=error.reason_code)
    return dict(result, available=True, status='ready', repositoryRoot=str(Path(top).resolve()),
                operations=['history', 'changes', 'checkpoint', 'push'])


def capture_work(root, resources, mode='write', boundary_store=None, project=None):
    """Attach a Git boundary only to source-writing work in a repository."""
    if mode != 'write' or not any(not r.startswith('resource:') for r in resources):
        return dict(available=False, reasonCode='source_write_not_requested', resources=resources)
    state = workspace_status(root)
    if state['status'] != 'detected':
        return dict(available=False, reasonCode=state['status'], resources=resources,
                    reason='Version control is unavailable for this workspace')
    from git_integration import work_snapshot
    return work_snapshot(root, resources, boundary_store, project)


def source_revision(root):
    """Optional provenance; filesystem fingerprints establish scan freshness."""
    if workspace_status(root)['status'] != 'detected':
        return None
    from git_integration import _try
    return _try(root, 'rev-parse', 'HEAD')


def common_directory(root):
    """Git-only identity fallback for external worktrees and overlap checks."""
    if workspace_status(root)['status'] != 'detected':
        return None
    from git_integration import _try
    value = _try(root, 'rev-parse', '--path-format=absolute', '--git-common-dir')
    return str(Path(value).resolve()) if value else None


def worktree_root(root):
    if workspace_status(root)['status'] != 'detected':
        return None
    from git_integration import _try
    return _try(root, 'rev-parse', '--show-toplevel')
