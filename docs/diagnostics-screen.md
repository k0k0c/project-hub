# Diagnostic Screen

The former coordination page is a read-only diagnostic view. The existing
`#coordination` route remains valid. It is not a resource dispatcher and does
not grant permissions or require agents to publish diagnostic reports.

## Default View

- Connection health and catalog availability are distinct from agent activity.
- Recent chats show the last observed timestamp, not an inferred running state.
- A task's plan status is independent from agent activity. The portal marks an
  agent as active only when its lifecycle session is observed within the live
  activity window (15 minutes); an older active row becomes "unknown" and does
  not appear as current work.
- Children are collapsed under their parent. Agent paths supply readable child
  labels; historical nicknames remain available in technical details.
- Search and incremental display replace the separately scrolling chat picker.
- IDs, raw states and integration metadata are collapsed by default.

The snapshot uses `Store.diagnostics()` and a bounded, compact session projection.
It does not load full coordination results, claims or attempt details. Existing
task progress, development history and overview events remain unchanged.

## Historical Data

The technical archive is fetched only when expanded, through
`/api/diagnostics/archive`. Its records are explicitly historical and are not
presented as current blockers. Existing IDs, evidence and journal entries are
preserved. The legacy coordination endpoint remains compatible.

## Model Overhead

No model calls collect data for this screen. Existing catalog and lifecycle
observations provide the diagnostic projection. UserPromptSubmit no longer
injects incremental technical history; SessionStart supplies only a short
optional-Hub notice. PreToolUse and PostToolUse remain no-ops. Native Codex
permissions are independent and are not changed by the diagnostic view.

## Verification

Run `python -m unittest discover -s scripts/tests` and
`node --check tools/project-portal/web/app.js`. Browser acceptance covers desktop
and mobile layouts, child labels, search, lazy archive loading, collapsed details
and absence of horizontal overflow. Use temporary catalogs and data homes for
tests, never production data.
