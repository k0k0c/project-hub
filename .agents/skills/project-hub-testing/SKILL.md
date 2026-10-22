---
name: project-hub-testing
description: Select fast, task-scoped Project Hub development checks, with explicit release coverage and verified receipt reuse.
---

Use a short development loop: diagnose, finish a coherent edit, run the affected
contracts once, then return the result or build the requested artifact.
Read [project testing](../../../docs/project-testing.md) for coverage and runner
contracts. Inspect `python scripts/project_hub_check.py --profile auto --scope
relative/file --explain` first; repeat `--scope` for this task's files.
Execute through `python scripts/project_hub_check_publish.py --title "Verification
purpose" --profile auto --scope relative/file` or a justified focused profile.

Auto sees the whole dirty checkout unless scoped. Other chats' edits must not
expand task feedback. Source snapshots and receipts still cover the whole tree.
Scope is forbidden for staged/full/release checks. Test-only edits select exact
changed files; sourceTests maps local source/UI changes to their affected tests.
Unknown executable paths/shared dependencies may explain full, but worktree auto
refuses implicit full execution. Inspect the dependency, narrow foreign scope or
select sufficient focused contracts; do not blindly switch to full.

Small fixes, stage/task closure, source launches and local EXE/ZIP rebuilds MUST
NOT add a full-suite gate. A shared backend/storage/auth/HTTP/runtime/runner
filename alone is not a reason for full. Use affected integration contracts and
broaden only for a concrete unresolved dependency, new change or failure.
Full runs once for an explicitly requested release, pre-push, or a cross-cutting
change that targeted integration cannot cover. Keep the full suite and hooks;
never relabel a development rebuild as a release merely to justify full.

Installer corrections use installer-lifecycle; payload/build/dependency changes
use distribution; local runtime uses portable-runtime; runner/config/hook work
uses runner. UI rules select affected tests; shared CSS/JS keep broader UI checks.
Prose/layout uses docs, documentation-ui, html-documents or plugin-docs as needed.
Docs is diff-only; changed visual design may need visual acceptance.

After affected checks, compile the requested artifact once and verify the changed
packaged behavior on disposable data. The build's compiler checks syntax; a
separate syntax-only compile is optional feedback. Source-only corrections need
no EXE. Do not repeat general package acceptance for each localized fix or run
unchanged tests again after compilation. After failure rerun the reproducing
subset first. Do not run checks after every small edit or repeat passed coverage
without new changes, failures or a concrete unverified dependency.

The runner uses private source/data snapshots, never live catalogs/data.
--staged tests exact index bytes, including partial staging; preserve others'
changes and the existing index. Finish edits before checks and coordinate a
stable snapshot. Prefer exact staged verification when preparing a checkpoint.
Reuse only verified receipts: changed bytes/config/commands/runner/timeout/
environment/toolchain invalidate reuse. Never normalize fingerprints or bypass
hooks. --fresh forces execution.

Use configured timeout or --timeout SECONDS, never ad-hoc full runners. Inspect
timings, failureKind, stable and receiptReuse; failure, timeout and changed inputs
are different outcomes. Preserve durability, recovery, isolation and locks while
optimizing tests. Report actual profiles, result/log paths, publication status
and coverage limits. This skill/config/runner are repository-local and are not
part of the distributed plugin.
