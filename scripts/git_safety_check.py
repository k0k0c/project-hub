"""Guard local commits and pushes against accidental destructive changes."""

from __future__ import annotations

import argparse
import subprocess
import sys


MAX_DELETED_FILES = 20
PROTECTED_PATHS = {
    ".codex/config.toml",
    ".codex/rules/project-git.rules",
    "AGENTS.md",
}


def git(*args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def staged_paths() -> list[tuple[str, str]]:
    rows = git("diff", "--cached", "--name-status", "--find-renames").splitlines()
    result: list[tuple[str, str]] = []
    for row in rows:
        fields = row.split("\t")
        if len(fields) >= 2:
            result.append((fields[0], fields[-1]))
    return result


def check_staged() -> list[str]:
    issues: list[str] = []
    paths = staged_paths()
    deleted = [path for status, path in paths if status.startswith("D")]
    if len(deleted) > MAX_DELETED_FILES:
        issues.append(
            f"staged deletion of {len(deleted)} files exceeds the safety limit "
            f"({MAX_DELETED_FILES})"
        )
    for status, path in paths:
        normalized = path.replace("\\", "/")
        if status.startswith("D") and normalized in PROTECTED_PATHS:
            issues.append(f"protected project policy file would be deleted: {normalized}")
    return issues


def check_push(remote: str, local_ref: str, remote_ref: str) -> list[str]:
    issues = check_staged()
    if local_ref.startswith("-") or remote.startswith("-"):
        issues.append("invalid push ref or remote")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["commit", "push"])
    parser.add_argument("args", nargs="*")
    parsed = parser.parse_args(argv)
    try:
        if parsed.mode == "commit":
            issues = check_staged()
        elif len(parsed.args) >= 3:
            issues = check_push(*parsed.args[:3])
        else:
            issues = ["push hook did not provide the expected ref arguments"]
    except (RuntimeError, ValueError) as exc:
        print(f"git safety check failed: {exc}", file=sys.stderr)
        return 1
    if issues:
        for issue in issues:
            print(f"git safety check: {issue}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
