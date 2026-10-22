# Project Hub plugin development

This repository is the canonical source for the public Project Hub plugin and
its local development server/UI. The installable package is
`tools/project-portal/plugins/project-hub`; its manifest, MCP entry point,
hooks, scripts and `skills/project-hub/SKILL.md` are shipped together.

The installed plugin and Codex plugin cache are generated artifacts. Never edit
their skills, hooks or scripts by hand. Make plugin changes in this repository
and run the documented prepare/install flow. Runtime Hub behavior, task
bookkeeping, identity, reports, child-agent coordination and task closure are
defined by the packaged `SKILL.md`, not by this file.

Keep repository-development concerns separate from runtime/user data:

- Read `docs/local-cutover-checkpoint.md` before continuing extraction work.
- Source, writable data and managed project roots are separate. Never run tests
  against production data; use temporary catalogs and data homes.
- For testing this repository, read `.agents/skills/project-hub-testing/SKILL.md`.
  Its project-local profiles and runner select checks by changed area and risk;
  they are not part of the distributed plugin. Use the packaged Hub check
  wrapper for agent-initiated runs so the task, profile and result are recorded.
  Preserve broad integration coverage for shared contracts and release checks.
- Inspect `auto --explain` before running checks. Use the relevant focused
  profile for local layout, documentation and test-only edits; task or stage
  completion alone is not a reason to run full. If auto includes another chat's
  dirty files, use explicit profile feedback or worktree `--scope` and report
  that boundary. Scope never narrows staged, full or release validation.
- Default to a fast development iteration: diagnose, finish one coherent edit,
  run the affected contracts once, then return the result or rebuild if requested.
  For task feedback pass `--profile auto --scope` for this task's exact files;
  source snapshots and receipt fingerprints still include the whole checkout.
  Test-only edits select the changed test files, not all profiles containing them.
- A small fix, stage/task closure, source launch or a local EXE/ZIP rebuild is
  not a release and MUST NOT add a full-suite gate. Shared backend/HTTP/runtime
  filenames alone do not require full; select the affected contracts and explain
  any concrete unresolved dependency. Auto worktree feedback refuses implicit
  full execution. If explanation selects full for unknown/foreign paths, narrow
  the task scope or choose justified focused coverage; never blindly retry full.
- Run full once for an explicitly requested release, pre-push, or a concrete
  cross-cutting change whose risks cannot be covered by targeted integration.
  Keep all release tests and safety hooks. Do not call every development build
  a release. After a failure rerun the reproducing subset; repeat/broaden passed
  coverage only for new changes, failures or a concrete unverified risk.
- For a localized installer correction use `installer-lifecycle`; for changed
  payload/build/dependency contracts use `distribution`. Build the requested
  artifact once after affected checks, then verify the changed packaged behavior
  on disposable data. Do not repeat a general acceptance sweep for each small
  fix or rerun unchanged tests merely because the EXE has just been compiled.
- Before a long final check, finish edits and coordinate the tested snapshot.
  When preparing a checkpoint, prefer exact staged checks so pre-commit can
  reuse a verified receipt. Preserve others' changes and the existing index;
  never bypass hooks or normalize fingerprints to force reuse. Timeout,
  changed inputs and failed tests are distinct outcomes. Use the standard
  runner's timeout/timings rather than creating a temporary full-run script.
- Keep dependencies and licenses with bundled web assets.
- For interface text, help, user documentation and localization, apply
  [.agents/skills/project-hub-localization/SKILL.md](.agents/skills/project-hub-localization/SKILL.md).
- The current scope is local extraction. Installers, portability,
  remote/multi-user functionality require separate user-requested tasks.
- Preserve existing task IDs, history, evidence links and user data. Do not
  fabricate tracking scripts or create another database.
- Do not use Computer Use to manage Codex projects or chats; the user handles
  unsupported UI actions.

For substantial source changes, split independent work into non-overlapping
paths and integrate the results in the parent task. Native approvals and
sandbox restrictions are separate from the plugin source and must not be
bypassed by repository scripts.

<!-- project-hub:binding:5cd63040cfb24f53bdb502e90dbf6d00:start -->
## Project Hub project binding

{
  "connection": "5cd63040cfb24f53bdb502e90dbf6d00",
  "bindingId": "fcfbfd9404b44d42bfd712b7a0ba9ca5",
  "project": "project-hub",
  "revision": 1,
  "scope": {
    "kind": "workspace",
    "root": "C:\\java\\repos\\project-hub"
  },
  "status": "active"
}
Use this canonical project and binding revision with the global MCP rules. At startup validate with hub_context; refresh on binding conflict. This rule applies only to the stated root/native project scope.

<!-- project-hub:binding:5cd63040cfb24f53bdb502e90dbf6d00:end -->
