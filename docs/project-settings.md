# Project settings storage

`tools/project-portal/plugins/project-hub/scripts/project_settings.py` provides:

- `read_settings(store)` returns `{settings, revision, history, configured}`.
- `update_settings(store, patch, expected, actor='local-user', reset=None)` returns
  the same envelope. `patch` is a partial object of partial sections. For a reset,
  pass `patch=None` (or `{}`) and one section name: `git`, `tasks`, or `viewer`.
  A nonempty patch and reset are mutually exclusive.

Callers must pass the authoritative `registry.base_store(project)`, never a
migrated task origin. Storage is exclusively `store.data/project-settings.json`;
there are no user-global preferences or database records. Both APIs acquire
`store.locked()`. The writer checks the opaque revision under that lock, writes
and fsyncs a temporary sibling, then atomically replaces the settings file.
Temporary files are removed after failures. The existing store owns lock files.

## Defaults and validation

```json
{
  "git": {"autoCommit": false, "commitOn": "stage-and-task"},
  "tasks": {
    "columns": ["title", "type", "priority", "status", "progress", "estimate", "created", "updated", "actions"],
    "sort": "created",
    "overviewSort": "created",
    "showCompleted": true
  },
  "viewer": {"wrapLines": true, "showSourceDetails": false}
}
```

All fields and sections are strict: unknown fields, wrong types and numeric
boolean substitutes are rejected. Columns must be a unique list drawn from the
default column list plus optional `summary` and `children`, and include `title`.
The stored order is preserved; the current UI uses its fixed column order.
Both sort fields accept the current UI modes: `created`, `created-oldest`,
`updated`, `priority`, `status`, `progress`, `title`. Commit modes are `stage`,
`task`, `stage-and-task`. Actor must be nonblank and at most 200 characters.

A missing file yields detached defaults, an opaque revision, empty history and
`configured=false`. Reading does not create the settings file. A real change
creates it with `configured=true`. Resetting every section does not erase history
or revert the configured flag. An empty or same-value update with the current
revision returns the existing envelope without writing, adding history, or
changing revision. A stale revision always conflicts, including same-value
retries. Clients must reread after conflicts; revisions are not numeric counters.

## History and errors

Each actual change appends `{at, actor, sections, before, after}`. `at` is UTC ISO
8601; `sections` lists changed sections in schema order; `before` and `after` are
complete settings snapshots. The newest 100 entries are retained in the same
file. Reads are capped at 1 MiB and validate the complete envelope, snapshots,
history continuity, and final settings. Invalid JSON, duplicate fields, malformed
or oversized existing files produce errors, including during reset; they are
never treated as missing or overwritten. Repair is an explicit external action.

`SettingsError` subclasses `ValueError` and exposes `code`, `status`, and
`body={error,message}` for adapters: `invalid_settings` (400),
`settings_conflict` (409), `corrupt_settings` (500). Filesystem errors propagate.
HTTP/MCP adapters, state projection and actual commit policy are separate work;
the storage module does not commit, install, publish, or mutate task history.

## Runtime contract

The project UI uses GET/POST `/api/v1/settings?project=<id>`. A write contains
`{expected,patch}` or `{expected,reset}`. MCP `hub_settings` reads the same
envelope or updates with the same fields. `hub_context.projectSettings` exposes
effective settings and their revision; agents must read them before work and
again before completion. Unknown settings are an error, never an implicit opt-out.
Standalone legacy clients cannot mutate settings: the connected server owns them.
Project state includes `settings`; SSE changes include its revision. Browser
list preferences override project defaults and may be reset for only that project.
Viewer defaults are applied each time a document opens.

## Completion checkpoints

The server's `ProjectView.record` is the common entry for HTTP lifecycle writes,
MCP plan edits and report outbox delivery. On a new `done` transition it persists
a checkpoint intent in the existing project registry, including the settings
revision and captured work boundaries. Git runs in a background worker outside
the ownership lock; long repository hooks do not block other Hub requests.
The task/stage exposes `gitCheckpoint` (`disabled`, `pending`, `committed`,
`no_changes`, or `error`), and successful SHA metadata as `gitCommit`.

Only verified write reservations can authorize dirty files. Pre-existing dirty
files, another active overlapping reservation, a pre-populated index, changed
history in the reserved scope or multiple checkouts require explicit review.
A clean repository without code work returns `no_changes`; a dirty repository
without a verified scope does not. No empty commits or implicit push are made.
Stage commits already covering work are not repeated at task closure.

Receipts precede the completion event but execute only when that event exists.
Pending receipts resume when the project is read after a restart. Successful
Git commits carry a unique `Project-Hub-Checkpoint` trailer so a retry can recover
a commit even if saving the receipt failed. Errors remain visible without undoing
the implementation status. Explicit retry uses MCP `hub_checkpoint(task,expected,
stage?)` or POST `/api/v1/checkpoints/retry?project=<id>` with the same fields.
Retry preserves the original settings revision and file boundary; it cannot
authorize a larger file set or silently absorb historical edits. New completion
events use the settings current at that time; changing settings is not retroactive.

### Explicit existing-commit reconciliation

MCP `hub_checkpoint(task, expected, stage?, commits?, reason?)` and the same
HTTP retry route also accept explicit adoption of existing commits. `commits`
and `reason` must be supplied together: an array of 1-20 full 40- or 64-hex
SHAs in oldest-to-newest order, and a nonblank reason no longer than 1200
characters. Hex letters may be uppercase or lowercase. Duplicate SHAs are
rejected ignoring case; the server normalizes accepted SHAs to lowercase.
`expected` remains the current project revision. Omitting both fields preserves
ordinary retry behavior.

Adoption requires an error checkpoint and a completed target task/stage. The
backend verifies same-task trailers, ancestry and coverage of the original
scoped changes. Commits from another stage of the same task are allowed. All
intervening commits affecting the original scope must be supplied, including
those between the captured baseline and the supplied tip. The supplied tip
may be historical when HEAD has advanced beyond it. Originally dirty paths
must have matching changed paths in the supplied commits; same-task trailers
alone do not prove coverage. Reconciliation performs no Git writes and preserves original
snapshots and the error journal. An identical commits/reason retry is
idempotent; a conflicting adoption of an already reconciled checkpoint is
rejected. This operation cannot expand the original scope or authorize a push.
Standalone clients return `server_required`; verification belongs to the server.

Large receipts keep full verification details in the existing registry while
journal patches and state responses expose file counts, SHA-256 digests and
`detailsAvailable`. Page the lists through
`GET /api/v1/checkpoints/detail?project=<id>&checkpoint=<id>&section=files&offset=0&limit=50`.
Supported sections are `files`, `scopedFiles`, and `commits`; add `commit=<sha>`
to retrieve one verified commit's files. Access follows current task ownership.
No original snapshot or historical event is replaced.

The verified Git result is durable before its journal event is published.
`publication.status=pending` identifies an incomplete metadata publication;
`sha` still identifies the saved commit. Ordinary retry republishes that exact
receipt without invoking Git. A lost journal acknowledgement reuses the same
event ID, avoiding duplicate events as well as duplicate commits.

## Verification

Run `python -B -m unittest discover -s scripts/tests -p test_project_settings.py`.
Tests use temporary data directories and exercise defaults, isolation, partial
updates, enums, strict rejection, section reset, history bounds, stale revisions,
no-op writes, concurrent independent store instances, corruption preservation,
and atomic replacement failures.

## Settings interface and personal menu

The three Settings routes cover personal interface preferences,
Git checkpoints, separate task-list and overview cards, document viewing, and
architecture defaults. Project Save/Cancel remains below the cards; restore and
history are disclosures. Switching the automatic Git checkbox preserves the
commit event selection while disabling its control.

The main-menu choice is origin-wide browser storage under
`project-hub-menu:v1`, with `auto` and `compact` values. Automatic mode uses the
existing narrow-screen breakpoint (760px); compact mode keeps icons at every
width. Resizing never changes the saved choice. Missing, invalid or unavailable
storage uses automatic mode; unavailable storage keeps the current choice in
memory and displays a notice. This preference is independent of project settings,
Save/Cancel, personal table filters and the API revision. Icon links retain names,
current-route state, keyboard focus and hover/focus labels.

Architecture uses the native model catalog and retains unavailable saved models.
Research actions start immediately with depth 1 and the saved representation.
The architecture page offers symbols with or without files; both retain symbols
for further exploration. Hidden files are transparent transit resources up to the
next visible symbol, and derived links retain the original chain. The previous
file-only setting is read as symbols with files by new UI actions. Depth is no
longer editable in this page; existing API depth values are retained for external
callers (positive integer from 1 to 10000 or `all`). A → B is a separate bounded
path search over all reachable facts. Source/provider selection remains automatic.
Negative semantic answers are retried because source fingerprints do not establish
external language-server index readiness.
