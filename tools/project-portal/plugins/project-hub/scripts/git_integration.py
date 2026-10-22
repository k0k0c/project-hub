"""Small, local-only Git adapter used by Project Hub.

The adapter has no GitHub credentials. It reports repository state and can
create a scoped local commit for a completed Hub work item; pushing requires
explicit caller confirmation. Callers provide the work snapshot captured at
reservation time, so pre-existing dirty files are rejected instead of being
swept into a task commit.
"""
from __future__ import annotations

import json
import os
import copy
import hashlib
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote


class GitIntegrationError(ValueError):
    """A safe, user-actionable Git integration failure."""

    def __init__(self, message, reason_code='git_operation_failed', layer='git'):
        super().__init__(message)
        self.reason_code, self.layer = reason_code, layer


def _run(root: str | Path, *args: str, timeout: float = 8, environment: dict | None = None) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            timeout=timeout,
            check=False,
            env=dict(os.environ, **environment) if environment is not None else None,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0,
        )
    except FileNotFoundError as error:
        raise GitIntegrationError('Git client is not installed or not available on PATH', 'git_client_unavailable') from error
    except subprocess.TimeoutExpired as error:
        raise GitIntegrationError('Git operation timed out', 'git_timeout') from error
    except (OSError, subprocess.SubprocessError) as error:
        raise GitIntegrationError(f"Git недоступен: {error}") from error
    if result.returncode:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        if len(detail) > 800:
            detail = detail[:480].rstrip() + "\n…\n" + detail[-300:].lstrip()
        raise GitIntegrationError(detail or "Операция Git завершилась ошибкой")
    # Do not use ``strip`` here: porcelain status uses the leading index/worktree
    # columns as significant data (`` M file`` must keep its first space).
    return result.stdout.decode("utf-8", errors="surrogateescape").rstrip("\r\n")


def _try(root: str | Path, *args: str) -> str | None:
    try:
        return _run(root, *args)
    except GitIntegrationError:
        return None


def _github_url(remote: str | None) -> str | None:
    if not remote:
        return None
    value = remote.strip()
    match = re.match(r"git@github\.com:(.+?)(?:\.git)?$", value, re.I)
    if match:
        return "https://github.com/" + match.group(1)
    match = re.match(r"https?://github\.com/(.+?)(?:\.git)?$", value, re.I)
    if match:
        return "https://github.com/" + match.group(1)
    match = re.match(r"ssh://git@github\.com/(.+?)(?:\.git)?$", value, re.I)
    if match:
        return "https://github.com/" + match.group(1)
    return None


def _github_links(repository_url: str | None, branch: str | None) -> dict | None:
    if not repository_url:
        return None
    encoded_branch = quote(branch or "", safe="")
    return {
        "repository": repository_url,
        "branch": f"{repository_url}/tree/{encoded_branch}" if branch else None,
        "issues": f"{repository_url}/issues",
        "pulls": f"{repository_url}/pulls",
        "actions": f"{repository_url}/actions",
        "compare": f"{repository_url}/compare/{encoded_branch}?expand=1" if branch else None,
    }


def _status_rows(root: str | Path) -> list[dict[str, str]]:
    raw = _run(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    rows = []
    records = iter(raw.split("\0"))
    for line in records:
        if len(line) < 4:
            continue
        code, path = line[:2], line[3:]
        row = dict(code=code, path=path)
        if "R" in code or "C" in code:
            row["originalPath"] = next(records)
        rows.append(row)
    return rows


def _row_paths(row: dict) -> list[str]:
    return [row[key] for key in ("path", "originalPath") if key in row]


def _in_scope(value: str, paths: list[str]) -> bool:
    return any(value == path or value.startswith(path + "/") for path in paths)


def _repository(root: str | Path) -> dict:
    top = _run(root, "rev-parse", "--show-toplevel")
    if not top:
        return dict(available=False, root=str(Path(root).resolve()), reason="Папка не является Git-репозиторием")
    common = _try(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    head = _try(root, "rev-parse", "HEAD")
    branch = _try(root, "symbolic-ref", "--short", "-q", "HEAD") or "(detached HEAD)"
    remote = _try(root, "remote", "get-url", "origin")
    upstream = _try(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    ahead = behind = None
    if upstream:
        counts = _try(root, "rev-list", "--left-right", "--count", "HEAD...@{u}")
        if counts:
            values = counts.split()
            if len(values) == 2:
                ahead, behind = (int(values[0]), int(values[1]))
    rows = _status_rows(root)
    return dict(
        available=True,
        root=str(Path(top).resolve()),
        common=str(Path(common).resolve()) if common else None,
        head=head,
        shortHead=head[:10] if head else None,
        branch=branch,
        upstream=upstream,
        remote=remote,
        githubUrl=_github_url(remote),
        github=_github_links(_github_url(remote), branch),
        ahead=ahead,
        behind=behind,
        dirty=bool(rows),
        changedFiles=[row["path"] for row in rows],
    )


def repository(root: str | Path) -> dict:
    """Return a bounded, credential-free repository projection."""
    if root is None:
        return dict(available=False, root=None, reasonCode='workspace_required',
                    reason='Connect a code workspace to use Git')
    from version_control import workspace_status
    state = workspace_status(root)
    if state['status'] != 'detected':
        return dict(available=False, root=state['workspaceRoot'], reasonCode=state['status'],
                    reason='Git is unavailable for this workspace')
    try:
        return _repository(root)
    except GitIntegrationError as error:
        return dict(available=False, root=str(Path(root).resolve()), reason=str(error), reasonCode=error.reason_code)


_READ_CACHE_LOCK = threading.Lock()
_READ_CACHE = OrderedDict()


def _read_entry(root):
    identity = str(Path(root).resolve())
    with _READ_CACHE_LOCK:
        entry = _READ_CACHE.get(identity)
        if entry is None:
            entry = dict(lock=threading.Lock(), token=None, info=None, histories={}, validated_at=0, last_read=None)
            _READ_CACHE[identity] = entry
        _READ_CACHE.move_to_end(identity)
        while len(_READ_CACHE) > 64:
            _READ_CACHE.popitem(last=False)
        return entry


def _read_token(root):
    """Validate Git metadata through Git, including linked worktrees/includes.

    Never expose configuration content in the projection or cache keys. Working
    files and the index are validated separately by a fresh Git status on every
    read; a directory timestamp cannot detect arbitrary new untracked files.
    """
    locations = _run(root, 'rev-parse', '--path-format=absolute', '--show-toplevel',
                     '--git-common-dir', '--git-dir', 'HEAD').splitlines()
    if len(locations) != 4:
        raise GitIntegrationError('Не удалось определить Git-контекст чтения')
    top, common, gitdir, head = locations
    refs = _run(root, 'for-each-ref', '--format=%(refname) %(objectname) %(symref)')
    config = _run(root, 'config', '--null', '--list', '--includes')
    # These change history traversal without necessarily moving a reference.
    extras = []
    for directory in sorted({common, gitdir}):
        for name in ('HEAD', 'shallow', 'info/grafts'):
            path = Path(directory) / name
            try:
                extras.append((str(path), path.read_bytes().hex()))
            except FileNotFoundError:
                extras.append((str(path), None))
    environment = sorted((key, value) for key, value in os.environ.items() if key.startswith('GIT_'))
    encoded = json.dumps([top, common, gitdir, head, refs, config, extras, environment],
                         ensure_ascii=True).encode('ascii')
    return hashlib.sha256(encoded).hexdigest()


def _cached_read(root, limit):
    requested_at = time.monotonic()
    entry = _read_entry(root)
    count = None if limit is None else max(1, min(200, int(limit)))
    # A per-repository single flight shares history construction across /state
    # and /git readers. It is never held by a Git write or checkpoint preflight.
    with entry['lock']:
        for attempt in range(2):
            shared = entry['token'] is not None and entry['validated_at'] >= requested_at
            token = entry['token'] if shared else _read_token(root)
            if token != entry['token']:
                info = repository(root)
                if not info.get('available'):
                    return info, []
                commits = [] if count is None else history(root, count, _info=info)
                if _read_token(root) != token:
                    entry['token'] = None
                    continue
                entry.update(token=token, info=info, histories={} if count is None else {count: commits},
                             last_read=copy.deepcopy(info), validated_at=time.monotonic())
                return copy.deepcopy(info), copy.deepcopy(commits)
            info = copy.deepcopy(entry['last_read'] if shared else entry['info'])
            if not shared:
                rows = _status_rows(root)
                info.update(dirty=bool(rows), changedFiles=[row['path'] for row in rows])
            if limit is None:
                if not shared:
                    entry.update(last_read=copy.deepcopy(info), validated_at=time.monotonic())
                return info, []
            if count not in entry['histories']:
                commits = history(root, count, _info=info)
                if _read_token(root) != token:
                    entry['token'] = None
                    continue
                entry['histories'][count] = commits
                while len(entry['histories']) > 4:
                    del entry['histories'][next(iter(entry['histories']))]
            if not shared:
                entry.update(last_read=copy.deepcopy(info), validated_at=time.monotonic())
            return info, copy.deepcopy(entry['histories'][count])
        raise GitIntegrationError('Git изменился во время чтения; обновите сводку')


def cached_read_repository(root: str | Path) -> dict:
    """Cached UI metadata with fresh index/worktree status; never for writes."""
    from version_control import workspace_status
    if workspace_status(root)['status'] != 'detected':
        return repository(root)
    try:
        return _cached_read(root, None)[0]
    except (GitIntegrationError, OSError):
        # Unborn/unsupported repositories retain the ordinary projection. A
        # failed validation never serves a previously cached successful result.
        return repository(root)


def cached_read_projection(root: str | Path, limit: int = 100) -> tuple[dict, list[dict]]:
    """Share validated, bounded UI history; callers may decorate returned copies."""
    from version_control import workspace_status
    if workspace_status(root)['status'] != 'detected':
        return repository(root), []
    try:
        return _cached_read(root, limit)
    except (GitIntegrationError, OSError):
        info = repository(root)
        if not info.get('available'):
            return info, []
        if not info.get('head'):
            return info, []
        # Unlike the legacy history helper, the UI cache must not turn a failed
        # history read into a successful empty list (and clear visible commits).
        return info, history(root, limit, _info=info)


def _commit_files(root: str | Path, sha: str) -> list[str]:
    output = _try(root, "diff-tree", "--no-commit-id", "--name-only", "-z", "--no-renames", "-r", "--root", sha) or ""
    return [path for path in output.split("\0") if path]


def _commit_trailers(message: str) -> dict[str, str]:
    values = {}
    for line in message.splitlines():
        match = re.match(r"^Project-Hub-(Task|Stage|Work):\s*(\S+)\s*$", line, re.I)
        if match:
            values[match.group(1).lower() + "Id"] = match.group(2)
    return values


def _history_batch(root, arguments, revisions):
    """Use stdin so full push ranges do not overflow platform argv limits."""
    try:
        result = subprocess.run(['git', '-C', str(root), *arguments],
                                input=('\n'.join(revisions) + '\n').encode('ascii'),
                                capture_output=True, timeout=8, check=False,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
    except (OSError, subprocess.SubprocessError) as error:
        raise GitIntegrationError(f'Git недоступен: {error}') from error
    if result.returncode:
        detail = result.stderr.decode('utf-8', errors='replace').strip()
        raise GitIntegrationError(detail[-320:] or 'Операция Git завершилась ошибкой')
    return result.stdout.decode('utf-8', errors='surrogateescape')


def _history_files(root, revisions):
    files = {sha: [] for sha in revisions}
    raw = _history_batch(root, ['diff-tree', '--stdin', '--raw', '-z', '--no-renames', '-r', '--root'], revisions)
    # Raw records have a separate metadata token followed by exactly one path
    # (--no-renames). A filename equal to a SHA or starting ':' is unambiguous.
    tokens = iter(raw.split('\0'))
    current = None
    for token in tokens:
        if not token:
            continue
        if token in files:
            current = token
        elif token.startswith(':') and current is not None:
            path = next(tokens, None)
            if path is None:
                raise GitIntegrationError('Неполный ответ Git о файлах коммита')
            files[current].append(path)
        else:
            raise GitIntegrationError('Некорректный ответ Git о файлах коммита')
    return files


def history(root: str | Path, limit: int | None = 100, range_spec: str | None = None, *, _info=None) -> list[dict]:
    """Return recent commits with Project Hub trailers when present.

    This is deliberately local and bounded. Missing trailers are retained as
    unassigned commits instead of being guessed onto a task.
    """
    # Push receipts must include the whole pinned range, not the UI history cap.
    limits = [] if limit is None else [f"-{max(1, min(200, int(limit)))}"]
    info = repository(root) if _info is None else _info
    log_range = range_spec or "HEAD"
    raw = _run(root, "log", "--no-color", *limits, "--format=%H%x1f%h%x1f%aI%x1f%s%x1f%b%x1e", log_range)
    commits = []
    for record in raw.split("\x1e"):
        record = record.strip("\r\n")
        if not record:
            continue
        fields = record.split("\x1f", 4)
        if len(fields) != 5:
            continue
        sha, short_sha, authored_at, subject, body = fields
        authored_at = datetime.fromisoformat(authored_at).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        commit = dict(sha=sha, shortSha=short_sha, at=authored_at, message=subject,
                      files=[], fileCount=0)
        commit.update(_commit_trailers(body))
        commit["pushed"] = None if not info.get("upstream") else False
        if info.get("githubUrl"):
            commit["githubUrl"] = info["githubUrl"] + "/commit/" + sha
        commits.append(commit)
    if commits:
        revisions = [commit['sha'] for commit in commits]
        files = _history_files(root, revisions)
        upstream = _try(root, 'rev-parse', '--verify', info['upstream'] + '^{commit}') if info.get('upstream') else None
        unpushed = set(_history_batch(root, ['rev-list', '--stdin'], [*revisions, '^' + upstream]).splitlines()) if upstream else None
        for commit in commits:
            commit['files'] = files[commit['sha']]
            commit['fileCount'] = len(commit['files'])
            if unpushed is not None:
                commit['pushed'] = commit['sha'] not in unpushed
    return sorted(commits, key=lambda commit: (commit["at"], commit["sha"]), reverse=True)


def git_history(root: str | Path, limit: int = 100) -> list[dict]:
    """Credential-free, bounded commit history projection."""
    try:
        info = repository(root)
        if not info.get("available"):
            return []
        return history(root, limit, _info=info)
    except GitIntegrationError:
        return []


def commit_pushed(root: str | Path, sha: str, upstream: str | None = None) -> bool | None:
    """Return whether a commit is reachable from the configured upstream."""
    try:
        if upstream is None:
            info = repository(root)
            upstream = info.get('upstream')
            if not info.get('available') or not upstream:
                return None
        return _try(root, "merge-base", "--is-ancestor", sha, upstream) is not None
    except GitIntegrationError:
        return None


def commits_since(root: str | Path, base: str | None, limit: int = 100) -> list[dict]:
    """Return commits that will be sent by the next push."""
    try:
        if not repository(root).get("available"):
            return []
        return history(root, limit, f"{base}..HEAD" if base else "HEAD")
    except GitIntegrationError:
        return []


def _relative_paths(root: str | Path, resources: list[str], *, repository_root: str | Path | None = None) -> list[str]:
    base = Path(repository_root or _run(root, "rev-parse", "--show-toplevel")).resolve()
    result = []
    for resource in resources:
        if str(resource).casefold().startswith("resource:"):
            continue
        value = str(resource).replace("\\", "/").strip().rstrip("/")
        if not value or value.startswith("/") or ":" in value or any(part in ("", ".", "..") for part in value.split("/")):
            raise GitIntegrationError("Git-ресурс должен быть относительным путём")
        candidate = (base / value).resolve()
        try:
            candidate.relative_to(base)
        except ValueError as error:
            raise GitIntegrationError("Ресурс выходит за пределы репозитория") from error
        result.append(candidate.relative_to(base).as_posix())
    return sorted(set(result))


def work_snapshot(root: str | Path, resources: list[str], boundary_store=None, boundary_project=None) -> dict:
    """Capture the pre-work Git boundary for a reservation."""
    if root is None:
        return dict(available=False, reasonCode='workspace_required',
                    reason='Connect a code workspace to use Git', resources=resources)
    from version_control import workspace_status
    state = workspace_status(root)
    if state['status'] != 'detected':
        return dict(available=False, reasonCode=state['status'],
                    reason='Git is unavailable for this workspace', resources=resources)
    # Reservation safety needs HEAD and the complete dirty set, not the UI's
    # remote/branch/upstream projection. Capture status once; extra Git processes
    # both delay begin and widen the interval before its actual boundary.
    try:
        top = _run(root, "rev-parse", "--show-toplevel")
    except GitIntegrationError as error:
        return dict(available=False, reason=str(error), reasonCode=error.reason_code, resources=resources)
    paths = _relative_paths(root, resources, repository_root=top)
    head = _try(root, "rev-parse", "HEAD")
    try:
        rows = _status_rows(root)
    except GitIntegrationError as error:
        return dict(available=False, reason=str(error), resources=resources)
    selected = [row for row in rows if any(_in_scope(value, paths) for value in _row_paths(row))]
    snapshot = dict(available=True, root=str(Path(top).resolve()), head=head, resources=paths,
                    dirty=selected, allDirty=rows, capturedAt=head[:10] if head else None)
    if boundary_store is not None and paths and head:
        from git_changesets import capture, canonical, ChangesetError
        try:
            boundary = capture(top, paths, boundary_store.blob)
            if boundary['head'] != head:
                raise ChangesetError('concurrent_git_change', 'Git HEAD changed during reservation')
            snapshot['contentBoundary'] = dict(schemaVersion=1, project=boundary_project,
                                               blob=boundary_store.blob(canonical(boundary)))
        except (ChangesetError, OSError, ValueError) as error:
            snapshot['contentBoundaryError'] = dict(reason=str(error), reasonCode=getattr(error, 'reason_code', 'boundary_capture_failed'), layer='changeset')
    return snapshot


def _staged_paths(root: str | Path) -> list[str]:
    output = _run(root, "diff", "--cached", "--name-only", "--no-renames", "-z")
    return [path for path in output.split("\0") if path]


def commit_work(root: str | Path, snapshot: dict, task: str, stage: str | None, work: str, title: str, checkpoint: str | None = None, check_context: dict | None = None, expected_content=None) -> dict:
    """Commit only changes made after a clean work reservation."""
    if not snapshot or not snapshot.get("available"):
        return dict(status="unavailable", reason=(snapshot or {}).get("reason", "Git недоступен"))
    info = repository(root)
    if not info.get("available"):
        return dict(status="unavailable", reason=info.get("reason"))
    if snapshot.get("head") and snapshot["head"] != info.get("head"):
        raise GitIntegrationError("HEAD изменился во время работы; commit требует ручной проверки", 'head_changed')
    if snapshot.get("dirty"):
        raise GitIntegrationError("В заявленных файлах уже были изменения до начала работы", 'dirty_baseline', 'attribution')
    paths = _relative_paths(root, snapshot.get("resources", []))
    if not paths:
        return dict(status="no_changes", branch=info.get("branch"), repository=info.get("root"))
    staged = _staged_paths(root)
    if staged:
        raise GitIntegrationError("В индексе уже есть staged-изменения; автоматический commit остановлен", 'index_preexisting')
    rows = _status_rows(root)
    selected = [row for row in rows if any(_in_scope(value, paths) for value in _row_paths(row))]
    changed = sorted({value for row in selected for value in _row_paths(row)})
    preexisting = {value for row in snapshot.get("allDirty", []) for value in _row_paths(row)}
    if any(not _in_scope(value, paths) or value in preexisting for value in changed):
        raise GitIntegrationError("Изменения пересекают границы работы или прежние изменения")
    if not changed:
        return dict(status="no_changes", branch=info.get("branch"), repository=info.get("root"))
    message = (f"{title.strip()}\n\n"
               f"Project-Hub-Task: {task}\n"
               + (f"Project-Hub-Stage: {stage}\n" if stage else '') +
               f"Project-Hub-Work: {work}")
    if checkpoint:
        message += f"\nProject-Hub-Checkpoint: {checkpoint}"
    staged_index = None
    try:
        _run(root, "--literal-pathspecs", "add", "--", *changed)
        # Keep the exact index state produced by this add. A failed hook or a
        # concurrent Git command may change the index before cleanup.
        staged_index = _run(root, "ls-files", "--stage", "-z")
        if set(_staged_paths(root)) != set(changed):
            raise GitIntegrationError("Набор staged-файлов изменился; commit требует ручной проверки")
        if _try(root, "rev-parse", "HEAD") != snapshot.get("head"):
            raise GitIntegrationError("HEAD изменился перед commit")
        # Hooks may run project checks; carry real attribution, never test commands.
        environment = dict(PROJECT_HUB_CHECK_TASK=task, PROJECT_HUB_CHECK_STAGE=stage or '',
                           PROJECT_HUB_CHECK_PROJECT='', PROJECT_HUB_CHECK_URL='')
        if check_context:
            environment.update(PROJECT_HUB_CHECK_PROJECT=check_context['project'],
                               PROJECT_HUB_CHECK_URL=check_context['url'])
        # Git commit uses a frozen copy of our verified index. A late staged
        # file in the real index, or a late worktree edit, cannot enter it.
        index_path = Path(_run(root, "rev-parse", "--git-path", "index"))
        if not index_path.is_absolute():
            index_path = Path(root) / index_path
        with tempfile.TemporaryDirectory(prefix="project-hub-index-") as directory:
            frozen_path = Path(directory) / "index"
            shutil.copyfile(index_path, frozen_path)
            environment["GIT_INDEX_FILE"] = str(frozen_path)
            if _run(root, "ls-files", "--stage", "-z", environment=environment) != staged_index:
                raise GitIntegrationError("Git index changed while preparing the checkpoint commit")
            if expected_content is not None:
                from git_changesets import index_files
                if index_files(root, paths, environment) != expected_content:
                    raise GitIntegrationError('Candidate index differs from the immutable completed bytes',
                                              'candidate_content_changed', 'validation')
            _run(root, "commit", "-m", message, timeout=600, environment=environment)
    except (GitIntegrationError, OSError, ValueError) as error:
        if staged_index is not None:
            try:
                unchanged = (_try(root, "rev-parse", "HEAD") == snapshot.get("head")
                             and _run(root, "ls-files", "--stage", "-z") == staged_index)
            except GitIntegrationError:
                unchanged = False
            if not unchanged:
                raise GitIntegrationError(str(error) + "\nGit index or HEAD changed; staged files were left for manual review") from error
            try:
                _run(root, "--literal-pathspecs", "reset", "HEAD", "--", *changed)
            except GitIntegrationError as cleanup_error:
                raise GitIntegrationError(
                    str(error) + "\nCheckpoint-staged files remain in the index: " + str(cleanup_error)
                ) from error
        raise
    sha = _run(root, "rev-parse", "HEAD")
    committed_files = _commit_files(root, sha)
    if set(committed_files) != set(changed):
        raise GitIntegrationError(
            f"Commit {sha[:10]} создан, но состав файлов изменился; требуется ручная проверка")
    pushed = commit_pushed(root, sha, info.get("upstream"))
    return dict(status="committed", sha=sha, shortSha=sha[:10], message=title.strip(),
                repository=info.get("root"), branch=info.get("branch"),
                remote=info.get("remote"), githubUrl=(info.get("githubUrl") + "/commit/" + sha) if info.get("githubUrl") else None,
                pushed=pushed,
                files=committed_files)


def commit_reviewed_batch(root, batch, read_blob, put_blob, *, confirmed, title, check_context=None):
    """Native writer for an explicitly reviewed candidate; ordinary hooks run.

    Call this under the caller's native Git permissions. Portal/MCP batch review
    never invokes it. Original work snapshots remain immutable and independent.
    """
    from git_changesets import (validate_batch, identity, capture, verify_batch_coverage, ChangesetError)
    before, after = validate_batch(batch, read_blob, put_blob)
    if confirmed != batch['id']:
        raise ChangesetError('batch_preview_changed', 'Confirm the exact reviewed batch before creating its commit')
    current = identity(root)
    if any(current[key] != batch[key] for key in ('repositoryId', 'worktreeId')):
        raise ChangesetError('repository_mismatch', 'Use the reviewed integration worktree')
    if _run(root, 'rev-parse', 'HEAD') != batch['head']:
        raise GitIntegrationError('Integration HEAD changed since batch review', 'head_changed')
    candidate = capture(root, batch['scope'], put_blob)
    if candidate['files'] != after['files']:
        raise ChangesetError('completed_bytes_changed', 'Current candidate differs from the reviewed batch bytes and modes')
    changed = sorted(name for name in before['files'].keys() | after['files'].keys()
                     if before['files'].get(name) != after['files'].get(name))
    # This is the explicit integration-parent intent, not a refreshed work
    # reservation. Only the already reviewed deltas receive write authority.
    snapshot = dict(available=True, root=current['root'], head=batch['head'], resources=changed, dirty=[],
                    allDirty=[row for row in _status_rows(root) if not any(_in_scope(name, changed) for name in _row_paths(row))],
                    preparedBatch=batch['id'])
    primary = batch['associations'][0]
    result = commit_work(root, snapshot, primary['task'], primary.get('stage'), batch['id'], title,
                         checkpoint='batch-' + batch['id'], check_context=check_context,
                         expected_content={name: after['files'][name] for name in changed if name in after['files']})
    if result['status'] != 'committed':
        raise GitIntegrationError('Reviewed batch did not create a commit', 'batch_commit_missing')
    try:
        coverage = verify_batch_coverage(root, batch, result['sha'], read_blob, put_blob)
    except ChangesetError as error:
        error.git_outcome = result
        raise
    return dict(result, batchId=batch['id'], coverage=coverage, verification=coverage['verification'])


def push_repository(root: str | Path, confirmed: bool = False) -> dict:
    """Push the current branch only after an explicit caller confirmation."""
    if confirmed is not True:
        raise GitIntegrationError("Push требует явного подтверждения пользователя")
    info = repository(root)
    if not info.get("available"):
        raise GitIntegrationError(info.get("reason", "Git недоступен"))
    if not info.get("upstream"):
        raise GitIntegrationError("Для текущей ветки не задан upstream")
    if info.get("dirty"):
        raise GitIntegrationError("Перед push рабочее дерево должно быть чистым")
    head = _run(root, "rev-parse", "HEAD")
    before = _run(root, "rev-parse", "@{u}")
    remote = _run(root, "config", "--get", f"branch.{info['branch']}.remote")
    destination = _run(root, "config", "--get", f"branch.{info['branch']}.merge")
    if not destination.startswith("refs/heads/") or _try(root, "config", "--bool", f"remote.{remote}.mirror") == "true":
        raise GitIntegrationError("Push требует обычную upstream-ветку")
    pushed = history(root, None, f"{before}..{head}")
    _run(root, "push", "--no-follow-tags", "--", remote, f"{head}:{destination}", timeout=60)
    for commit in pushed:
        commit["pushed"] = True
    refreshed = repository(root)
    return dict(status="pushed", branch=refreshed.get("branch"), upstream=refreshed.get("upstream"),
                remote=refreshed.get("remote"), githubUrl=refreshed.get("githubUrl"),
                ahead=refreshed.get("ahead"), behind=refreshed.get("behind"), commits=pushed)


def encode_snapshot(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def decode_snapshot(value: str | None) -> dict:
    if not value:
        return {}
    try:
        result = json.loads(value)
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError):
        return {}
