# Project selection contract

The shared selector is `resolve_project` in the bundled `hub_core.py`.
`scripts/project_resolution.py` exposes it with the read-only Codex assignment
adapter. Selection has no session/task/claim mutations.

- An explicit local Codex project assignment wins over cwd, including an old
  checkout no longer attached to that project.
- Unknown, non-local or unreadable assignment metadata never permits cwd fallback.
- Without an assignment, the most specific saved root wins; a primary root wins
  over secondary attachments at the same depth. External Git worktrees use the
  same selector. Ambiguity is an error, not the first matching database row.
- Project primary root, actual cwd and attached writable roots remain different
  concepts. Guard path normalization still uses actual cwd for relative paths.

## Audited consumers

- ServerHub: MCP, lifecycle hooks, resource guards and session reconciliation all
  dispatch through the common selector. Assignment is rechecked before ownership
  reconciliation. Permission checks remain in the server.
- Portal session discovery and registered-session projection use the same rule,
  including before a moved session next calls a hook/MCP. They never mutate the
  original registration, historical work, task ownership or reservations.
- Portal state/coordination/history/task/source endpoints already have an explicit
  project ID from the route. Coordination now uses that ID rather than resolving
  it again through the primary folder. Registry-created base stores keep this ID.
- Standalone legacy Hub lookup and standalone session discovery share the selector
  with a single-root registry. This mode has no Codex assignment source; the
  installed HTTP plugin does not execute this legacy CLI path.
- Local separation rehearsal uses the shared selector and assignment adapter.
  Its explicit primary-root precondition and offline rebinding remain intentional.
- Task transfers, memory, report outbox, evidence and participating-session history
  use persistent task/work project IDs. They must not reinterpret historical
  ownership through a chat's current folder or project assignment.

## Current sessions versus history

Archived Codex sessions and closed Hub sessions are excluded from the current
list. Sessions with active/waiting work in the selected project remain visible
and are labelled historical when archived, closed or moved elsewhere. Counts
describe the displayed projection. Missing metadata shows only retained work
participants with an explicit unavailable notice. No session history is deleted.

Regression fixtures cover moved chats before/after hooks, archived reservations,
shared and nested roots, unknown/non-local assignments, unavailable metadata and
real external Git worktrees. All mutations run against temporary catalogs/data.

Path/Git lookups are cached for five seconds to avoid repeated filesystem probes
on every SSE poll. Explicit assignment and saved-root changes use different cache
keys immediately; ownership metadata itself is reread on every projection.
