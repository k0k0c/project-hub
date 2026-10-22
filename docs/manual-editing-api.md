# Manual editing HTTP API

All mutations are JSON POST requests on the local same-origin server. Every
route below requires `?project=<project-id>`. `expected` is the exact opaque
`revision` from the latest state or successful mutation. Never replace it with
`relationsRevision`. Success returns HTTP 200 and the updated project snapshot;
validation/concurrency conflicts return HTTP 409 with `{"error":"reason"}`.
There is no automatic stale-revision retry. Refresh, reconcile, and resubmit.

## Task editing

`POST /api/v1/tasks/create`

```json
{"task":{"title":"New task","type":"task","scope":[],"acceptance":[]},"expected":"revision"}
```

The response adds `createdTask`, the generated stable task ID. Creation accepts
`title`, `summary`, `status`, `scope`, `deferred`, `acceptance`, `sources`, `type`,
`priority`, `parentTask`, `weight`, `estimate`, and `links`. Status defaults to `planned`;
create an unfinished task before using lifecycle routes. No implicit priority.

`POST /api/v1/tasks/update`

```json
{"task":"task-id","patch":{"title":"Edited task","estimate":{"percentLow":20,"percentHigh":40,"hoursLow":1,"hoursHigh":3,"confidence":"low","note":"Remaining implementation"}},"expected":"revision"}
```

Estimate intervals must be finite, ordered, nonnegative pairs; percentages are
limited to 100. `estimate:null` clears an estimate. The update route also accepts
`links`. A transition into `done` requires `/api/v1/tasks/close` with
`{task,expected,mode:"auto"|"manual",reason?}`. Automatic closure rejects unfinished
descendants. Reopening requires `/api/v1/tasks/reopen` with `{task,expected}`.
An unchanged `done` status is accepted when editing other metadata of a done task.
The existing close route can perform its existing Git checkpoint behavior.

## Stage editing

`POST /api/v1/stages/create`

```json
{"task":"task-id","stage":{"id":"optional-stable-id","title":"New stage","status":"planned","remaining":["Acceptance check"],"dependsOn":[]},"expected":"revision"}
```

The response adds `createdStage`. Omit `id` for a generated ID. Stage fields are
`title`, `status`, `summary`, `done`, `remaining`, `dependsOn`, and `evidence`.
Creation defaults status to `planned`; titles must contain non-whitespace text.
`done`, `remaining`, and `dependsOn` are string arrays. Evidence is an array of
objects with project-relative `path` and optional `label`. Paths cannot escape
the project. Dependencies must name existing active stages in the same task and
must be acyclic. Task IDs and stage IDs cannot be changed by patch.

`POST /api/v1/stages/update`

```json
{"task":"task-id","stage":"stage-id","patch":{"title":"Edited stage","remaining":["Verify"]},"expected":"revision"}
```

Closed/cancelled tasks must be reopened before their stages can be edited.

`POST /api/v1/stages/delete` and `POST /api/v1/stages/unlink`

```json
{"task":"task-id","stage":"stage-id","expected":"revision","reason":"Optional explanation"}
```

Both logically detach a stage from the active plan. Delete records `deleted`;
unlink records `unlinked`. Neither erases a stage, evidence, or journal entry.
The full stage remains in `task.archivedStages` with
`lifecycle:{action,eventId,at,reason,targetTask?}`. Archived stages do not affect
active progress or dependency validation. Their IDs remain reserved for recovery.

`POST /api/v1/stages/restore`

```json
{"task":"task-id","stage":"stage-id","expected":"revision"}
```

Restore recovers the latest un-restored deleted/unlinked record into the same task
with its original ID, status, evidence and results. The archive record remains
and receives `lifecycle.restoredAt` and `lifecycle.restoredEventId`. For recovery
UI, offer restore only for `deleted`/`unlinked` archives without `restoredAt`.
Transferred archive entries are audit references, not independently restorable.

`POST /api/v1/stages/transfer`

```json
{"task":"source-task-id","stage":"stage-id","target":"destination-task-id","expected":"revision","reason":"Optional explanation","includeDependencies":false}
```

The destination must be a different task in the selected project. Both same-origin
and cross-origin tasks are supported, including a migrated task and a new local
task. ID, results, status, evidence, commit metadata and prior
stage history are retained. `stage.history` carries previous stage events and
`stage.transfers` records ownership changes; original events remain unchanged
under their original task. The source keeps an `archivedStages` audit reference.

Delete, unlink and transfer reject incoming or outgoing dependencies. Update
dependencies explicitly first; they are never silently removed or rebound.
Alternatively, transfer accepts `includeDependencies:true`: the complete
connected dependency group moves atomically, preserving every stage ID and
`dependsOn` edge. This includes reverse dependents and shared prerequisites,
not just the selected stage's prerequisites. A collision anywhere in the group
rejects the entire operation. The source's unrelated stages remain in place.
Archived IDs are also reserved: a return transfer is allowed only when each
matching archive is a transfer record proven by the incoming stage's ancestry.
An unrelated deleted/unlinked archive causes a conflict, even if restored in the
past; no historical identity is guessed or replaced.
They also reject active work, pending reports, destination ID collisions and
closed affected tasks. The registry ownership barrier, journal locks acquired in
stable project-ID order, and coordination transaction protect validation and the
write. Both source revisions are checked before committing an intent. Validation
or stale-revision conflicts leave both journals unchanged.

### Cross-origin recovery

Same-origin transfer remains one `stage.transferred` journal event. Cross-origin
transfer commits a redo intent to `stage_transactions` in the existing registry
SQLite database before replacing either journal. It records both baseline hashes,
preimage hashes, expected revisions, postimage hashes, and fully validated
`stage.exported`/`stage.imported` events with stable IDs. No second database is
created. The source archive still exposes `lifecycle.action:"transferred"` and
`targetTask`; its `transactionId` proves a later return transfer's ancestry.

The outermost ownership barrier recovers pending intents before inventory,
coordinated reads or mutations. Registry-backed base `Store` locks also enter
that barrier. Recovery locks both journals, checks every participant against its
expected preimage or postimage, writes only missing events, and marks the intent
done. Repeated recovery and restarts do not duplicate events. Divergent journal
or baseline content causes a conflict before any further writes; the pending
intent is retained for reconciliation and divergent data is never overwritten.
Unmanaged filesystem edits or registry-unaware raw file reads are outside this
coordinated protocol; divergent writes are detected by recovery hashes.

After durable intent, an interrupted request can still commit through the next
read's recovery. HTTP 503 after storage failure therefore requires a refresh to
determine the outcome, not a blind retry or rollback. Before intent, failures
leave both journals unchanged. Crash tests cover committed intent, first journal
replacement, second replacement, repeated restart, and divergence.

Imported stage/history evidence stores raw relative paths with explicit original
`sourceProject`, including evidence inherited from a third project. Later edits
operate normally on the target origin journal. Projected `hub-source/...` paths
submitted by editors are resolved through the registered `evidence_origin` map
before persistence; changing a label never stores or duplicates that prefix.
Unregistered foreign references are rejected. New relative paths bind to the
current project, while registered original evidence remains accessible after
subsequent task moves.

Active/waiting coordination work on either affected task and pending outbox
reports are tested with the real temporary coordination schema. Rejection keeps
work result/evidence/revision, outbox payloads and both task journals unchanged.
After normal `Memory.flush_reports` delivery, the move succeeds and preserves
both tasks' previously unpublished results and evidence.

## Relations projection

`task.links` contains only persisted outgoing relations and remains the field to
edit with `/api/v1/tasks/update` or `/api/v1/tasks/link`. `task.relations` is derived
on HTTP snapshot responses and contains both directions, including other projects:

```json
{"type":"blocked-by","target":"source-task-id","project":"source-project-id","direction":"incoming","sourceTask":"source-task-id","sourceProject":"source-project-id"}
```

Inverse pairs are `blocks`/`blocked-by`, `duplicates`/`duplicated-by`, and
`related`/`related`. Explicit reciprocal records are deduplicated in this view,
never added to the target journal. `project` is the current project of `target`;
`sourceTask`/`sourceProject` identify the persisted link's owner for editing.
Use those owner fields when removing an incoming relation. Unresolvable legacy
links remain in raw `links` but are omitted from the projection. New links must
resolve to an existing task/project; self-links are rejected.

`state.relationsRevision` tracks this derived array independently of the local
plan revision. Include it in the UI refresh comparison so remote incoming-link
changes become visible. Mutation `expected` must still use `state.revision`.

## Static assets and checks

The explicit static allowlist includes `ui-state.js`, `task-table.js`,
`task-table.css`, `task-editor.js`, and `task-editor.css`, alongside existing assets.

Focused tests: `test_manual_editing.py`, `test_stage_operations.py`,
`test_stage_transfer_recovery.py`, and `test_task_relations.py` in `scripts/tests`. Every test uses temporary catalogs,
project roots and data homes, never production task data.
