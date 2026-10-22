# Plugin server API

The independent server exposes `POST /api/v1/plugin/call` in registry mode.
MCP requests contain `cwd`, `session`, `tool`, and `arguments`. The server
resolves the saved local project from the absolute workspace and rejects reuse
of a session in another project. Journals and coordination remain server-owned.
MCP and hook operations share the ownership barrier with task transfers.

Set `PROJECT_HUB_URL=http://127.0.0.1:8769` for both MCP and hook processes to
select server mode. The packaged client connects to the independent server;
installation prepares its connection configuration from canonical source.
Server mode accepts loopback HTTP only, disables proxies and redirects, limits
payloads and response sizes, and never falls back to local database writes.
Other legacy CLI subcommands are rejected when server mode is selected.

Task taxonomy is exposed symmetrically through the MCP tools `hub_task`,
`hub_task_update`, `hub_task_link`, `hub_task_close` and the read-only
`hub_migration_preview`. The browser API exposes
the corresponding task update, link and close routes plus the read-only
`/api/v1/tasks/migration-preview` endpoint. Both previews return current
classification fields (`type`, `priority`, `parentTask`, and optional `weight`),
mark legacy rows that need review, and never write journal events.
Task projections also expose the derived `maxDescendantPriority` value: the
highest priority among unfinished descendants, without changing the task's
own priority.
Task links may target another project by passing its project id; structural
`parentTask` remains a single-tree relationship, while cross-project
relationships stay non-hierarchical. Task mutation calls must echo the exact
plan revision returned by `hub_plan(task)` or the preceding task mutation; stale opaque
revisions are rejected rather than replaced with the current revision.
`hub_task_close` accepts `mode=auto` only when every descendant is done or
cancelled. `mode=manual` always closes the task, records `closedManually` and
returns the unfinished descendant ids as a warning.

The browser state includes a credential-free Git projection (`git`) with the
current branch, upstream, ahead/behind counts, dirty status and derived
GitHub repository/branch/Issues/PR/Actions links. `GET /api/git?project=<id>`
returns a bounded task-centric projection with affected-task rows, recent
commits parsed from Project Hub trailers, push events and explicit
unassigned/ambiguous counters; it does not expose diffs. Stage commits are
also persisted as `git.commit` journal events, so `/api/history?kind=git`,
task history and the development history show the same task/stage association.
Commit links are enabled only when the commit is reachable from the configured
upstream; local commits remain non-clickable until push. `POST /api/git/push?project=<id>` accepts only
`{"confirm":true}` and is the sole push entry point; it requires a clean tree
and configured upstream. Stage completion publishes local commit metadata in
the stage projection. Hub never pushes implicitly and never stores GitHub
credentials.

User-facing history materializes explicit task-change events from the legacy
`task.updated` state events: `task.reopened`, `task.status_changed`,
`task.type_changed`, `task.priority_changed`, `task.parent_changed`,
`task.linked` and `task.unlinked`. Each event carries `change` metadata and a
human-readable old/new or relation detail. The migration is deterministic and
idempotent; the original state events remain the source of the task
projection. `work.started` and `work.completed` remain available to
coordination and diagnostics but are intentionally omitted from the
user-facing overview, task history and development history.

Hook observations exclude prompts, file content and tool outputs. PreToolUse
and PostToolUse are no-ops; Hub outages never deny edits or grant native
permissions. Missed lifecycle observations are not proof of active execution.
Long waits poll from the client without holding the ownership lock.

Task transfers reject active work and pending journal reports. Moved tasks
reject old-project plan changes and reservations. The new owner can read
history, edit the plan and continue work. Plan revisions are opaque strings;
integer revisions remain supported by the legacy writer. Identical plan
retries preserve writer receipt validation.

HTTP update, close, reopen and link preserve the exact supplied revision.
Closing validates it before any Git checkpoint; HTTP closure holds the
ownership barrier through validation, checkpoint and journal write. MCP closure
performs the same pre-check under its existing request barrier.

Single-task transfer requires explicit removal of structural parent/child links
before preview and execution. It never silently splits a tree. Hierarchy checks
and derived children/progress use the current owner's tasks, not the origin
journal's membership. Historical cross-project parents are hidden from current
trees without rewriting history; they must be explicitly cleared before another
transfer. A moved task can be assigned a parent in its destination project.

Recorded stage commit metadata is materialized idempotently on projection reads
without Git subprocess discovery under the transfer barrier. Project-level push
events stay in their originating project even when its tasks move. Both history
projections compare UTC instants with stable tie-breakers. Push pins the outgoing
HEAD and reports the range from the pre-push upstream; a successful push with a
journal failure returns eventRecorded=false and a visible UI warning.

## Plan and document publication contract

`hub_plan(task)` reads the task and its current revision. A mutation with
`stage`, `title`, `remaining`, `status` and `expected` creates a missing stage
or updates an existing one. `expected` only guards concurrency; it does not
select the operation. A retry of an already-applied identical request is
idempotent, including creation with a revision. A stale revision for a new
mutation is rejected. Creation without expected remains a legacy-compatible
operation; agents should read and supply a revision.

The portable plugin skill requires at least one stage per tracked task,
including read-only reviews. Start work with `hub_begin(..., stage=...)` and
publish its result/evidence with `hub_report`. An unlinked legacy report is
retained in coordination history but does not publish stage results.

Documents belong in task `sources`: read the latest plan, merge existing
sources with `{label, path}` entries, and call `hub_task_update` with its exact
revision. Paths are project-relative. Report evidence does not populate task
sources automatically. Confirm `planSync=saved`, read back the stage result
and sources, and resolve the attachment with `hub_memory(ref='source:<path>')`
before declaring publication complete. `hub_begin` and other calls can affect
the projection; reread the revision immediately before a later mutation.

The end-to-end contract is exercised by
`test_documented_review_lifecycle_publishes_plan_result_and_sources` in
`scripts/tests/test_project_hub_plugin_api.py` using temporary projects.

Verification: `python -m unittest discover -s scripts/tests` (214 tests passed
on 2026-09-19). The suite includes HTTP/MCP lifecycle, revision-safe stage
creation, retry receipts, document publication and ownership checks, all using
temporary data. Remote auth, team access and offline event replay are not
implemented here.
