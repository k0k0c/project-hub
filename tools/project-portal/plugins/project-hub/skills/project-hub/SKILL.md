---
name: project-hub
description: Use the connected project hub for project memory, automatic task bookkeeping and advisory coordination, without blocking agent work.
---

## Nonblocking coordination

**Internal Hub operations are an exception to task bookkeeping.** A Hub-originated
research, code description, scenario, subsystem proposal, project overview or
documentation request marked `bookkeeping.mode="internal"` is service work.
Never create a task, plan stage or work record for it and never call `hub_task`,
`hub_plan`, `hub_begin`, `hub_report` or `hub_task_close` for that operation.
Use its launch acknowledgement and designated knowledge result/history only.
This takes precedence over the generic task workflow below. Explicit user
implementation and `task-execute` requests retain normal task bookkeeping.

Project Hub supplies project memory, task bookkeeping, advisory coordination and observations. It must never block the user's task. Every tracked task, including a small fix, review, investigation or documentation task, must have at least one visible plan stage and a visible result. Bind your own context, reuse the best matching task (or create one when no task matches), and scale detail to scope: one stage and a concise result suffice for a small task; substantial work deserves detailed findings and evidence. Attach every created user-facing report or deliverable to the task. Unavailable MCP, identity errors, busy claims and incomplete observations may leave a recording gap; continue authorized work and mention the gap in the handoff. Native Codex approvals and sandbox restrictions remain independent: Hub neither grants nor denies filesystem access and does not authorize bypassing native restrictions.

Use hub_context, hub_memory, hub_plan, hub_task, hub_begin and hub_report for implementation and read-only work alike. First inspect existing tasks/history; create a task only when none reasonably matches. Scope and acceptance describe the assignment, not its plan or results. A decision/history entry is not a substitute for a plan stage. The primary agent may consolidate child results, but must preserve the parent task link and report the integrated outcome. Do not generate tracking scripts, create a replacement database or manually construct journal events. A failed bookkeeping call never stops the actual implementation; repair the publication gap when practical and disclose it until verified.

### Native instructions and work boundaries

For a native MCP connection, the verified instruction bundle and its short
application-wide bootstrap are authoritative. Read the local manifest and both
workflow.md/user-additions.md at startup and after compaction. Compare the
published manifest once at startup and refresh changed or damaged owned files
through native permissions. Preserve unrelated rules and private configuration.
Do not replace user additions with this template or edit installed plugin caches.
The user's authorization to connect covers owned instruction installation and
repair; native host approvals remain independent. Verify actual loading in a
fresh chat separately from saving files.

If a legacy `project-hub-user` skill is present, preserve and read its user text
through the normal skill mechanism. It does not override the current connection
contract or remove its explicit session/project/nativeChat requirements. Hub's
**Rules of work** settings edit the managed user additions; they do not prove
that a client loaded them.

Task creation and beginning work are separate signals. Choose/create the task
and a visible stage, then send `hub_begin` immediately before substantive
implementation, investigation, review or verification. Preliminary instruction
reading, identity binding, context lookup and task selection may precede it.
Declare concrete paths/shared resources and start a new precisely scoped work
when the assignment changes. A planned/open task alone never means work started.
Use `waiting` only for an actual external dependency; resume the same owned work
with its current revision. Report `done` only after that work's requirements are
verified; completing a work does not automatically satisfy its task. Stop,
Interrupt and SessionEnd are observations and never complete work/task records.

Parallel-work notices are advisory facts with declared scopes, identity and
freshness. Codex owns execution and coordination. A notice is not authorization
to send messages to another chat, close another agent's work, acquire filesystem
access or bypass native permission checks. Missing observation means unknown.

### Documentation and architecture upkeep

Write user-facing interfaces, help and documentation for a person who may use
Codex without knowing Hub internals. Begin with purpose and practical choices,
then offer optional technical detail. Explain unfamiliar terms, use natural
complete wording in the reader's language, and avoid duplicated instruction
text, mixed-language prose and unexplained internal identifiers. Keep page
headings above quoted instruction headings. Preserve exact API/file/event names
where useful for setup or diagnosis. Separate human explanations from original
agent-facing contracts and make prose suitable for future translation; never
claim multilingual support that has not been implemented.

These are universal Project Hub capabilities. Never assume a language, repository,
application, audience or component layout. `hub_knowledge` uses the bound project
and an independent numeric knowledge revision; `hub_plan.expected` is a different
contract. Start with `action=context` once per relevant task, reuse its policy and
capabilities, then retrieve only the items needed with `search`/`read`. Do not
read the full database or repeatedly rebind identity/reload instructions.

When asked to fill documentation or architecture, use this workflow:

1. Read project policy. Configure components, relative path prefixes, entrypoints,
   audiences and sections from verified project evidence using `changeset`.
   Model meaningful applications/subsystems (UI, domain, shared formats, testing)
   as project-specific components with optional `parent` component IDs. Use
   hierarchy and focused views to explain the whole project; do not turn every
   class into a semantic component. IDs are unique and parent links acyclic.
   Do not bake this configuration into the Hub implementation.
2. For architecture, `scan` queues/coalesces a local job; it never runs project code
   or calls AI. Continue useful work and read `job` at a convenient checkpoint.
   Python/Java adapters extract shallow types, declared inheritance and syntax
   references. Other languages provide a file inventory; report capabilities
   honestly. Unresolved/static edges are not proven runtime call paths.
3. Add useful purposes to important components, classes and relationships with
   authored changesets. Preserve generated facts, provenance and source evidence.
   Descriptions may contain up to 12000 characters. For a scoped architecture
   description request, honor the user's brief/standard/detailed level in the
   selected object's description; do not create a documentation article unless
   requested. Store standalone guides as documents. No exhaustive
   method/parameter/variable catalog.
   Create authored flow/scenario views where runtime order needs human evidence.
   Overview maps and dependency matrices compare direct child components at one
   level; drill down for their composition. Aggregate counts mean static source
   relations, never method calls. Scenario `orderedEdges` reference existing
   relationships, with evidence for any authored order.
   Research maps may carry `presentationGroups`: local `{id,title,parent?,
   nodeIds,description?}` categories whose direct participants belong to the view.
   Keep local IDs unique, parents acyclic and direct ownership disjoint. Grouping
   one research result or a canvas publishes a separate view; never change global
   class `component` ownership merely to improve one map. Named subsystem
   structuring instead considers its complete direct and child composition.

4. For documentation, search before adding an article. Use configurable audience
   and section, `type=tutorial|how-to|reference|explanation`, status
   `draft|current|historical|archived`, and `visibility=internal` by default.
   Link `entityRefs` to architecture IDs and architecture `documentRefs` to
   document IDs. Markdown and HTML are formats in the same semantic tree, never
   separate HTML-only sections. `audience=developer` opens Development; `section`
   is its slash-delimited topic folder. Classify by content and evidence, not
   extension or source directory. Use `import-preview` for Markdown/text/HTML
   sources and review diffs
   before selecting replacements in `import-apply`; never silently overwrite
   manually edited articles or claim missing images were imported.
   MCP previews return candidate summaries and `readArgs`. Use `import-read`
   with that identifier/index, field=source|markdown|html|diff, offset/limit and the returned
   cursor before accepting replacements. Export returns a validated download
   reference; use HTTP/CLI for the ZIP rather than reading the whole store.
   HTML import snapshots the entry and bounded local HTML/CSS/JS/images and
   linked files, without executing project code or changing originals. Check
   missing assets and external resources; external code/network requests, modules
   and application host bridges are unsupported in the isolated browser preview.
   Keep source markup as HTML; do not convert prototypes into Markdown or insert
   executable markup into the portal DOM. Default viewing is a full-width iframe;
   Open separately serves the same immutable snapshot without the Hub interface.
   During `import-apply`, optional `metadata` maps candidate IDs to reviewed
   title, description, audience, section, type, status, documentDate (YYYY-MM-DD),
   dateBasis, versionLabel, versionGroup, entityRefs and documentRefs. Distinguish
   document/design dates from filesystem timestamps or first Git appearance.
   Mark historical only with supersession evidence; unimplemented proposals may
   remain draft. Explain runtime/test resources explicitly. Preserve topic groups
   shared with Markdown and link earlier versions through documentRefs. Reimport
   checks dependency hashes too and retains existing authored classification.
5. Apply `changeset` with `expected`, a unique `key`, `operations` (put/delete),
   `reason`, current `task` and `stage`. Use `validate_only` for a preview.
   A conflict preserves current data: refresh and reconcile, never force-write.
   Retry uncertain writes with the identical key/content. `history`/`restore`
   preserve immutable history; restore makes a new revision.
6. Attach created documents via returned `sources` paths
   `knowledge/document/<id>` to task.sources and report evidence, preserving
   existing sources. Read them back with `hub_memory(ref="source:...")`;
   use its returned versionRef for consistent pages. These references survive
   removal of the original imported source files.

During ordinary work, assess knowledge impact before the final report without
waiting for the user to ask. Add/move/remove components or types, inheritance,
dependencies, entrypoints, shared formats or contracts: refresh extracted facts
and update affected authored views/descriptions and developer documentation.
Changes to visible behavior, workflows, configuration or public contracts:
update the relevant documentation even when the architecture is unchanged.
Cosmetic edits, internal method refactors and fixes with no structural or
documented behavior change require no manual architecture rewrite or artificial
article. `impact(paths,change)` helps locate affected items; the agent must still
judge meaning. Record a concise disposition in the work report (updated IDs, or
no-impact with reason). Missing adapters or uncertain relationships are explicit
limitations; never invent an edge or description to fill a gap.

For durable assessment, use `impact` with `record=true`, current task/stage and
`change.reason`. Unresolved assessments appear as review-needed in context/UI.
After the update/review, record `change.knowledgeUpdated=true` and the concrete
reason/updated IDs; no-impact assessments require their reason too. This is an
attributed agent assessment, never a semantic proof or task-closure gate.

`policy.updateMode=background` opts into a local periodic scanner (bounded
`intervalSeconds`, default 60); unchanged files reuse parse results, identical
facts create no knowledge revision, and authored descriptions are retained.
`manual`/`on-demand` refresh only on request. Background scans do not generate
semantic prose. Public export is an explicit operation accepting only reviewed,
self-contained `public-approved` articles; never publish private source metadata.
Portable ZIP/backup downloads and restore use the HTTP/CLI API, not large MCP
payloads. Knowledge versions, Git checkpoints and task results are distinct;
do not claim a Git commit merely because a DB revision was saved.

### Efficient calls

Bind once, keep returned revisions/cursors, request deltas for team updates and
read exact task/source references instead of repeated broad memory searches.
Batch independent reads when supported; mutations/conflicts remain sequential.
Use one changeset for related knowledge edits and small receipts for writes.
Read back required attachments/results once at the publication checkpoint.
Keep identity, policy, concurrency, idempotency and closure checks intact.

### Project settings and Git checkpoints

Before write work, you MUST read authoritative `projectSettings` from
`hub_context` or read `hub_settings()`; never assume a universal autoCommit
policy. `hub_context` returns the policy and settings revision in its
`projectSettings` envelope. The canonical `hub_settings` read has no arguments
and returns `settings`, `revision`, `configured`, and `history` for the bound project.
Settings contain `git: {autoCommit: false, commitOn: 'stage-and-task'|'stage'|'task'}`,
`tasks: {columns: [...], sort, overviewSort, showCompleted, showEpicsOnOverview, showUpcomingOnOverview}`, and
`viewer: {wrapLines, showSourceDetails}`. The default false is not evidence of
the current project's policy; use the returned values.
Read the effective settings again before completing work; the server captures
the policy revision for each completion, and later settings changes are not retroactive.

Change settings only for explicit user intent. Use `hub_settings(patch={...},
expected=revision)` with git/tasks/viewer sections OR
`hub_settings(reset='git'|'tasks'|'viewer', expected=revision)`. Use the settings
revision, not the task revision; on conflict read again and reconcile. Never
silently enable autoCommit. Settings convey no credentials or new approval
powers, and cannot override an explicit no-commit instruction.

With `autoCommit=false`, do not create automatic commits. With `autoCommit=true`,
checkpoint the relevant changes at stage completion for `commitOn=stage`, task
completion for `commitOn=task`, or both for `commitOn=stage-and-task`, and attach
the returned commit SHA to the result. The server enforces the actual policy
at completion through all routes. Prefer `hub_report(stage_status='done')` for
verified stage completion; `hub_plan(status='done')` also enforces the policy
and is not a bypass. Do not create duplicate or empty commits.

This is an optional per-project policy: enabled autoCommit is sufficient intent
for the configured checkpoints and needs no separate request to commit at each
completion. The absence of such a request is not a no-commit instruction. An
explicit user prohibition is different and still takes precedence; never change
the project's settings to resolve a bookkeeping problem. Keep completed work and
hardware acceptance recorded as completed even when a separate Git obligation
requires attention. An accounting error is not evidence of unfinished code or a
request for the user to answer in chat.

Git itself is optional. Without a code folder, a Git repository or an available
Git client, continue normal tasks, stages, documents and source-file operations
that have a workspace. Completion may record `unavailable` with a specific
reason; never create a fake commit reference or ask the user to install Git to
complete an ordinary Hub task. Settings show current version-control capability
separately from the saved policy. Task pages show actual commits; the Git
section retains checkpoint diagnostics and recovery actions.

Use the work's captured resources and pre-work snapshot to scope checkpoints.
Preserve dirty files and the pre-existing index, including unrelated changes;
unrelated work must not be blocked. Inspect returned Git metadata and distinguish
`no_changes` from missing safe scope, pending publication, and errors. A refusal
or missing safe scope is not a successful commit or evidence of no changes.
An audit/read-only request needs no coding commit. Push always requires separate
user authorization; neither settings nor completion authorize `git push`.

Task/stage completion exposes `gitCheckpoint` with `id`, `status`
(`pending`, `error`, `committed`, `no_changes`, `unavailable`, or `disabled`),
`settingsRevision` and optional `reason`; committed results also expose
`gitCommit`. Normal completed task/stage status may retain a pending Git
obligation. Git failure must remain visible as a pending obligation, including
its error/reason; do not hide it or equate completed status with publication.
Retry via `hub_checkpoint(task, expected=projectRevision, stage=optionalStage)`
or the UI after resolving the cause. This expected value is the current project
revision, not the settings revision. Never blindly expand safe scope to force
a checkpoint; preserve dirty files and the pre-existing index on retries too.
Git runs asynchronously: a successful completion response can still be `pending`.
Read the task/stage back at a convenient checkpoint before claiming a commit exists.
Task closure can reuse an existing stage SHA or list several already-covered
SHAs in `gitCheckpoint.commits`; it must not create duplicate commits.

For explicit reconciliation with existing commits, use
`hub_checkpoint(task, expected=projectRevision, stage=optionalStage, commits=[...], reason="...")`.
Supply `commits` and `reason` together: 1-20 full 40- or 64-hex commit SHAs,
oldest to newest, and a nonblank reason of at most 1200 characters. Without
`commits`, ordinary retry is unchanged; do not supply a reason alone.
Hex letters may be uppercase or lowercase. Duplicate SHAs are rejected ignoring
case; the server normalizes accepted SHAs to lowercase.
Reconciliation requires an error checkpoint and a completed target task/stage.
New server-owned write work stores immutable before and first completed-after
content boundaries in the existing CAS. Reconciliation verifies exact committed
and parent bytes/modes, ancestry and the frozen completed result. It records the
caller and explicit reason; a shared commit can cover several tasks without a
matching task trailer. Dirty baseline bytes remain original evidence and cannot
be assigned by matching filenames. Mixed content differing from the completed
result requires explicit reviewed batch coverage.
Legacy reservations without these boundaries retain the original same-task
trailer and scoped-history checks, labelled `legacy-scope-and-trailers`.
For that path, same-task commits from other stages are allowed, but all
intervening commits that change the original scope must be supplied.
A historical tip is accepted even when HEAD has advanced beyond it. Originally
dirty paths must have matching changed paths in the supplied commits; a task
trailer alone does not establish coverage. It performs no Git writes and retains the original
snapshots and error journal. Never replace snapshots, erase errors or expand
scope to make adoption succeed. Retrying the same commits/reason is idempotent;
conflicting completed adoption is rejected. Inspect the returned checkpoint and
read the target back before claiming reconciliation succeeded.

Large checkpoints expose compact file counts and hashes; complete verified file
lists remain in the existing checkpoint receipt. Read them through
`GET /api/v1/checkpoints/detail?project=...&checkpoint=...&section=files&offset=0&limit=50`;
sections also include `scopedFiles`, `commits` and `changesets`, with optional `commit=SHA`
for one commit's files. Follow `next` until null. Original snapshots are unchanged.

For shared-file work, use `hub_git_batch(action='preview', targets=[{task,stage?}],
expected=currentProjectRevision, reason=explicitAttribution, commit=existingSHA?)`.
It prepares an immutable candidate from the original changesets, including known
sequential dirty chains, identical binary deltas and disjoint UTF-8 text hunks
from linked worktrees. Unknown starting bytes and conflicts refuse. Legacy
obligations return `legacy_boundary_unproven`; inspect them separately and never
fabricate content boundaries. Preview keeps original checkpoint IDs and errors.
Read all paginated `steps`, `hunks`, `changes`, `changesets` and `files` with
`action='details', blob=batchBlob, section=..., offset=..., limit=...`.
Review the exact contributions and candidate before crediting coverage. Use
`action='reconcile'` with the same targets/reason, an existing full commit SHA,
fresh project revision and `confirmed=preview.batchId`. The entire parent and
candidate bytes/modes plus ancestry must match; each original target receives
the shared batch ID and retains its previous result. After a lost acknowledgement,
refresh the project revision and retry the same confirmed batch/commit/reason.
Already verified outcomes retry publication without Git reads or writes.

The HTTP/MCP review API never creates a commit. A prepared preview supplies
`nativeCommit` fields for `scripts/client_entry.py git-batch --root ROOT --cas CAS
--batch-blob BLOB --confirmed BATCH_ID --title TITLE [--url URL]`. Execute this
only within the caller's native Git permissions after concrete review. It reads
the existing CAS and commits the exact current candidate with ordinary hooks,
frozen-index and concurrent HEAD/index guards; pre-existing staged changes refuse.
It preserves original work boundaries and creates no database. Afterwards review
and reconcile the returned SHA for all selected targets. Native restrictions or
refusals never authorize another writer or an indirect portal commit. Push still
requires separate user authorization.

Checkpoint diagnostics may include `reasonCode`, `layer`, `operationId` and a
shared `batchId`. A created commit whose content verification failed remains in
`gitOutcome`; it is not a successful verified checkpoint. Publication errors
carry their own layer and retry metadata without another commit. Native approval
or filesystem refusals do not grant permission to use another writer or script.
If `gitCheckpoint.publication.status=pending`, the Git outcome is saved but its
journal publication is incomplete. A SHA still means that commit exists. Retry
the checkpoint to publish the same receipt without creating another commit.
An old active reservation does not expire automatically: its owner must finish
it. Never close another session's work or manufacture missing original scope.
Explicit read-only reconciliation can verify a completed work's historical SHA
while unrelated overlapping work continues; it does not authorize new Git writes.

If settings are unavailable, continue authorized work and report unknown policy
and publication pending. Do not assume autoCommit is off or declare policy
compliance. Reconcile settings and completion publication when available.

### Planning and task creation

When a user request reaches planning for a substantial change (multiple files,
new API/schema/UI, migration, or a coordinated architectural change), announce
that planning has started and that the work will be represented in Project Hub.
Before implementation begins, inspect existing tasks and either reuse the best
match or prepare a new task with the agreed title, scope and acceptance criteria.
The user's authorized assignment is sufficient to create/update its bookkeeping
and plan. Create the task with `hub_task`, write its current plan with `hub_plan`,
then register actual work with `hub_begin`. Hub adds no separate approval gate.
Native permissions and any approval required for the requested external action
remain independent. Do not ask again for an already authorized plan. If the user
is still exploring or explicitly postpones implementation,
the task and current plan may exist without any `hub_begin` or code edits.

When the plan changes during discussion, update the current task plan and
replace its current stages/subpoints rather than narrating every discarded
draft. Durable event history may retain the server's audit record, but the
agent-facing plan and UI should show the latest agreed version. Small isolated
fixes do not need a confirmation card; they still receive the compact record
required above. If Hub or the host's elicitation UI is unavailable, continue
without blocking the user task and report the recording gap.

Task structure is available symmetrically through `hub_task` (including
`type`, `priority`, `parentTask` and optional `weight`), `hub_task_update` and
`hub_task_link`, and `hub_task_close` for manual or verified automatic closure.
Use the read-only `hub_migration_preview` before classifying legacy tasks. Use one structural parent for the tree; use links for
`blocks`, `blocked-by`, `related`, `duplicates` and `duplicated-by`. A task
may be an Epic, Task or Bug, and children can nest recursively. Never invent a
priority when the user has not supplied enough context.
An Epic's own priority is independent; its read-only
`maxDescendantPriority` projection reports the highest priority among
unfinished descendants and must not be written back as the Epic's priority.
Use `hub_task_close(mode=auto)` when the task has no unfinished descendants,
including a Bug or Task with no children. Use `mode=manual` only when the user
explicitly accepts closing with unfinished children; preserve and report the
returned warning.
For a cross-project relation, pass the target project id to `hub_task_link`;
do not use cross-project links as structural parents. Reuse the exact opaque
revision returned by the previous read or mutation for every task update,
link, or close operation; a stale revision must be refreshed, not silently
replaced.

### Explicit actions and project review

The Hub action dialog fixes project/task/one-stage scope before launching a native
turn. Task scope contains all stages except done, including cancelled stages and
their reasons; scope is not execution order. Plan is a native collaborationMode,
with the configured model and effort preserved. Busy/unknown/unowned chats remain
unavailable; never silently start a new chat in their place. Page opening,
hovering, refresh and missing status do not authorize a model run.
An owned retained-turn continuation supplies a delta with changed task offsets
and IDs leaving the previous scope. Reuse that prior context; the new immutable
scopeRef remains authoritative for full membership. Incomplete delta coverage
requires reading the referenced pages. Leaving scope alone is not completion.

For review/next-step/relevance/estimate/closure-review actions, bind your own
verified identity and register planning/research/review work with read claims on
an existing scoped task only for an explicit tracked task review. Internal Hub
research and project overviews follow the exception above without work records.
Read every bounded hub_review summary page of your own
initial actionId/scopeRef; on retained continuation reconcile its delta and read
additional pages when coverage is incomplete. Retrieve referenced details as necessary. This service
request authorizes reading/research and publishing evidenced proposals, not
implementation or silent status/scope/priority/hierarchy changes. Do not create
a task or stage solely for service bookkeeping. Read work in service phases
does not activate the plan. One project summary includes every unfinished task,
including hidden future tasks and epics; do not launch one model per task.

Use hub_review(action=propose,actionId,work,expected,proposals=[...]) with target
task/stage, decision=current/done/superseded/duplicate/clarify, reason, confidence,
immutable evidence and the current expectedState. done requires every acceptance
and remaining criterion mapped to listed immutable evidence. A replacement names
a different task and an existing stage with its expectedState and preserves all
unresolved requirements. Age/title/version similarity alone is insufficient.
The user reviews and explicitly applies selected proposals in Hub. MCP has no
apply action. A partial apply returns applied/remaining IDs and fresh revision;
do not blindly retry changed targets or pretend cancellation means completion.
Task-wide current proposals may include priority (a supported existing level or
null to clear it). The dialog shows the proposed priority before explicit user
apply; open write work blocks its application. Publishing it does not change
the task's priority.

Only an explicit estimate intent permits hub_review(action=estimate) to publish
estimate metadata with its action-owning work and expected revision. Provide
target expectedState, confidence, basis note and coarse ranges when knowable.
Unknown time omits both hour bounds. No automatic status/scope change follows.
Remaining hours mean active analysis, edits, integration and necessary checks;
exclude waits, queues and pauses. Project totals use unique sequential work,
avoid adding epics/children or explicit duplicates twice and disclose unknown
coverage. Do not invent calibration or divide estimates by an arbitrary factor.

For multi-stage work, hub_report(stage=...) selects the one stage whose status
changes; an ambiguous stage_status is rejected. status=waiting with
waiting_kind=user_confirmation/external_dependency records genuine waiting.
Native user-input questions remain distinct from command permission approvals.
Never send approval responses through the question-answer route.

## Identity and history

Pass your own stable session on every MCP call. Use the host's actual current
conversation ID when exposed, otherwise generate one unique bookkeeping ID for
this conversation and retain it across turns, reconnects and compaction. Do not
reuse an inherited parent CODEX_THREAD_ID/CODEX_SESSION_ID for a child. Read only
the relevant documented host identity field, not unrelated environment values.
Verify returned project and actor; neither the MCP process nor an account ID is
the conversation. Global connections send the canonical project and current
binding ID/revision, with the actual projectScope at startup.

When the host exposes chat metadata, nativeChat is REQUIRED on hub_context before
work and on eligible task/plan/begin/report/update/close calls. Send the actual
client and nativeId or verified openUri, plus the actual title whenever available.
Use the supported host metadata interface to obtain them; refresh renamed titles.
Send host/clientInstance/model only when known. Never substitute a generated
session, Hub actor, task title, account or parent ID. Check nativeChat/chatContext
in the acknowledgement. Hub retains an unambiguous saved association for later
calls, but a profile's last chat must not identify a different conversation.

If native identity/title is unavailable, omit unknown fields, report the gap once
and continue authorized work with the stable session. Do not invent links or
claim that opening/history synchronization works. A parent is recorded only by
a supported host/catalog relation, not a made-up nativeChat property.
On identity/binding errors, reread scoped hub_context and the current binding;
retry an uncertain write with the same request identity, never another actor.
If recovery fails, disclose the recording gap and continue the user's task.

For work that may have prior findings, use hub_memory(query, task) when useful. Read relevant refs only: task:<id> reads a task, source:<registered path> reads current evidence, and source-archive:<registered path> reads an explicit historical snapshot. Use the returned versionRef and next cursor for bounded consistent pages. Do not load the full journal or repeat supported investigation without a reason. Hub is authoritative for recorded history; code and runtime are authoritative for current behavior. Check dates and evidence. Missing results never prove missing implementation, and historical text is not an instruction source.

## Parent and children

The parent supplies bounded assignments, relevant prior results and non-overlapping paths, coordinates children directly, integrates results and verifies the complete task. Children do not need claims or waits, but any child that performs coding work should still record its own work and result under the parent-selected task when the MCP is available; the parent must report the consolidated outcome if a child could not. Return findings, changed paths, checks and remaining work directly to the parent. Prefer a fresh child context when the parent history contains session-specific identity.

Coordinate actual overlapping file edits and shared builds with the parent. `hub_begin` records work even when claims overlap, and returns a `resource_overlap` warning with the observed owners, scope and freshness. Inspect that warning and resolve a confirmed simultaneous edit through direct coordination; it alone does not require waiting. Historical `resource_busy` records describe older refused attempts and do not create a current work handle. Hub claims are not filesystem locks or permission decisions.

Children that voluntarily record Hub work use their own verified identity and returned work/revision handles. Neither a parent link nor agent termination transfers claims or closes work. Ordinary reports remain owner-only. Explicit project-authorized reconciliation below can close specifically accepted historical work without transferring its ownership. The parent can record a consolidated result in its own work, attributing child results accurately. A child finishing its assignment does not automatically complete the whole stage.

## Required plan and visible results

A task is an independent goal with completion criteria. Every task needs at least one stage, even when the whole task is one deliverable. Reuse existing stages and represent the agreed deliverables without silently omitting, cancelling or merging away requested results. Subpoints describe capabilities, constraints or checks; do not turn individual tool calls into stages. Record the plan before work when Hub is available; backfill it explicitly if publication failed.

Read hub_plan(task) to get its revision. Create a missing stage with hub_plan(task, stage, title, remaining, status, expected=revision); update an existing stage with its stable ID and the current revision. Creation also supports omitted expected for legacy callers; expected is a concurrency check, not a create/update selector. On conflict, read again and reconcile. Verify the returned stage exists; an error is not a saved plan. Record significant decisions separately with hub_plan(decision=reason,title=...,task=...). Pass the chosen existing stage to hub_begin, or stages=[...] for one work spanning several existing stages. Select phase=planning/research/implementation/review/testing and mode=read for reviews/investigation, write for implementation. A work keeps one Git boundary. Without a stage, only initial planning of a task with no stages is allowed. Creation and substantive work registration are separate. Unexpected investigation during implementation remains in the selected stage; do not invent another implementation stage. Supply at least one relevant file/directory or resource:name, never an empty resources list.

A decision requires a nonempty `title` as well as `decision`; pass the current
`expected` revision. It records history and does not create a visible stage.
For an actual blocker, use `blocker={kind, reason, action}` on `hub_plan` or
`hub_task_update.patch`: kind is `technical`, `user_input`, or `administrative`.
Describe the concrete obstacle and required action; reserve `user_input` for a
specific missing answer. A chat message does not automatically resume work.
Clear resolved metadata with `blocker=null`. Keep verified results completed;
an accounting issue or Git obligation does not imply unfinished implementation.
Authorized diagnostic edits may proceed without registered write work when
binding or bookkeeping fails. Report the actual paths and checks for later
publication, without inventing a work handle, claim or lifecycle observation.

Save the actual result, evidence and next step with hub_report using your own work/revision. status=done completes the work; stage_status=done completes a fully verified stage when no other work in that stage remains open. If other work is active or waiting, Hub still saves this result and returns `stageCompletionDeferred` with the open work; the stage and its remaining product requirements stay open. A later owning work or explicit plan update can complete the stage after verification. Include findings, checks and limitations in the result, with relative evidence paths for the full report. An unlinked report is stored in work history but does not publish a visible stage result. Repair a legacy unlinked report with a new stage-linked publication work, attributing the original result without claiming to repeat it; never rewrite another work or journal.

### Continuing across connections and applications

Task access follows the selected project. A new app or connection may read,
edit, continue and close its tasks. Keep your own identity and begin new owned
work for continued implementation. To close specifically accepted historical
work, read `hub_context(work=id)` and use `hub_report` with the exact revision,
terminal status, factual result and `reconcile={owner,status,reason}`. The owner
and observed status must match the read. Prior evidence is retained; new
evidence is additive. The audit retains previous result/checkpoint, original
owner and current actor. Work/stage/task IDs, claims history and Git snapshots
stay unchanged; reconciliation never recaptures current source as old completed
content and does not itself prove a checkpoint.

Active work requires coordination first. MCP cannot interrupt it; the user
must confirm it in Hub: task Chats, Reconcile work records. Age is not proof of stopped
execution. Revision conflicts require another read and coordination. Identical
retries are idempotent, and other open work still defers stage completion.

### Documents and evidence

Creating a file or linking it in chat does not attach it to a Hub task. For tracked
user/task-execute work, attach every created report or user-facing deliverable,
and existing important files needed for the assignment or review. Do not attach
every source file read, credentials or private native configuration. Internal
Hub launches publish only to their designated knowledge destination/history.
For tracked deliverables:

1. Keep the file in the relevant project's accessible source tree, using the
   project's existing artifact location. Do not assume a particular machine,
   username, repository name or data-home path.
2. Read the task and current plan revision. Merge the document into task.sources
   with hub_task_update(task, expected=revision,
   patch={sources: [...existingSources, {label: "Review report", path: "docs/review.md"}]}).
   Use the actual project-relative path; preserve all existing sources and avoid
   duplicates. If a plan response is truncated, read task:<id> through hub_memory
   before replacing sources. For transferred tasks preserve existing provenance
   and use the supported current-project source contract.
3. Include the path in the stage-linked hub_report(evidence=[...]) as well.
   Task sources make documents discoverable in the task's document section;
   report evidence preserves their relation to the published result.
4. Read hub_plan/task memory back: check the stage result, sources and report
   delivery. Read source:<path> with hub_memory (or open the Hub document viewer)
   to verify that the attachment resolves. planSync=saved alone does not prove
   that task.sources was populated; missing planSync on an unlinked report is
   not confirmation of visible publication.

A small task need not generate an artificial standalone report, but it still
needs a stage and concise result. Substantial reviews must attach their detailed
findings and coverage rather than leave the analysis only in chat.

### Images in tasks and stages

For new any-format immutable evidence, prefer `hub_artifact(task, path,
expected=revision, stage?, label?, roles?, previous?)`. Project-relative originals
are snapshotted into the existing Hub CAS outside checkout; their current bytes
remain product/fixture inputs. Existing upload `hub-artifact` references can be
attached directly. Roles may combine and never authorize validation exclusions.
Continue a stable artifact ID only with an explicit registered `previous`.
Unsupported previews retain metadata and original downloads. Exact version
references preserve history; archive mode remains for legacy project sources.
Read task/stage and `source:<returned path>` back to verify attachment. Binary
memory reads return metadata/hash, not decoded text. The existing `hub_image`
and task source update workflows remain supported for legacy paths.

Images are first-class task sources and evidence, subject to the same attachment
and verification requirements as documents and other deliverables. You MUST
attach images relevant to understanding, defining, investigating, implementing
or verifying the task, without waiting for a separate user request to attach them.
This includes images supplied by the user (for example, a screenshot showing a
reported UI bug), and images created or captured during work, including screenshots
returned by MCP/browser/UI tools, diagrams, mockups and visual verification results.
Apply this rule when creating, updating or working on a task; it is not limited
to final results or to tasks explicitly classified as UI work.

Do not leave relevant images only in chat or tool output. Preserve the original
in the project's artifact directory with a descriptive label, then register it
as a task source or evidence of the relevant stage. Preserve both the initial
problem image and relevant verification images; do not replace one with the other.
Reuse existing attachments instead of duplicating them. If image bytes cannot
be retrieved from the host/tool, record the attachment gap explicitly and seek
an accessible original when needed; never claim the image was attached or invent
a file path. Continue useful work while resolving the gap.

Read `hub_plan(task)` and call `hub_image(task, path, expected=revision,
label="Descriptive caption", stage="optional-stage-id")`. Create the task and
stage first when needed. Without stage this adds a task source; with stage it
adds stage evidence. Both appear in the task's combined Sources gallery, with
the same path shown once. The stage shows only its own images. Reuse a path
when the same image supports several stages. Existing sources and provenance
are preserved. Refresh the revision before the next mutation. Include relevant
image paths in the stage-linked report's evidence as well.

JPEG/JFIF, PNG/APNG, GIF, WebP, AVIF, BMP, ICO and safe SVG have browser previews.
TIFF and HEIC/HEIF originals can also be attached; their previews require the
server's optional Pillow / pillow-heif decoders. Do not promise a preview when
the decoder is unavailable. The original remains downloadable. UI uploads
preserve original bytes, validate file content, limit each file to 20 MiB and
reuse identical content. Do not convert or overwrite the user's original just
to make an attachment work. Avoid attaching secrets or unrelated images.

Read the task/stage and `hub_memory(ref="source:<path>")` back to verify the
attachment resolves. For images memory returns metadata and a content hash,
not decoded binary text; inspect pixels with the image viewer. A file in the
filesystem, upload response, or chat link alone is not a saved task attachment.

### Completion and task closure

When a Bug or Task has satisfied all acceptance criteria, required checks and
requested deliverables, close the task itself with `hub_task_close`; do not
stop at `hub_report(status=done)`. First record the verified result and
evidence with a stage-linked `hub_report`, verify at least one stage, its visible
result and all created deliverables in task sources, refresh the exact revision, call
`hub_task_close` (normally `mode=auto` when no unfinished descendants remain),
and verify that the returned task status is `done`. Do not close while
acceptance criteria, required tests, requested deliverables or unfinished
child tasks remain. Do not claim Hub publication complete after an error or close
a task with an unresolved plan/document publication gap. If Hub is unavailable,
continue the authorized work, state
the closure gap in the handoff, and close the task later when practical.

### Source of truth and installation

This `SKILL.md` is part of the installable Project Hub plugin and is the
canonical source for Hub runtime behavior. Edit it only in the repository
package at `tools/project-portal/plugins/project-hub/skills/project-hub/`.
Never edit a generated installed package or Codex plugin cache by hand. After
changing the plugin, run the repository's documented prepare/install flow so
the installed package and cache are regenerated from this source.

Check planSync after a report: pending means the report is durable but visible plan delivery is incomplete. Retry on a later convenient Hub call, without delaying the task. Do not claim the visible plan updated until confirmed. If reporting fails, deliver the checkpoint directly to the parent or user and record it later when practical. Never rewrite historical journals.

Use hub_wait only as an optional convenience for a real dependency when no useful independent work remains. Never wait for a claim, identity repair, recording delivery or Hub availability as a condition of doing the user's task. Keep large logs in evidence files; exclude transcripts, secrets and internal reasoning from reports.

## Testing and check publication

Project-local instructions own test profiles, commands, selection and coordination.
Before an agent-initiated test, diagnostic or verification build, read the
project's applicable instructions, profile configuration and existing runner.
Use its required checks, selection rules, arguments and profile/version unchanged.
Wrap every such execution with the installed plugin's generic check command so
the observed run is published to Checks. A project helper is optional; copying
Hub runtime rules or a helper into every project's AGENTS.md is not required.
If no project profile exists, run the appropriate existing command with a factual
purpose; omit profile/version rather than inventing a test configuration.

Use the project verified by your own Hub context and an existing task/stage.
Locate the plugin root from this installed skill (two parents above its folder)
or the host-provided PLUGIN_ROOT; do not assume a creator's repository or user
directory. The shared entry point uses the installation's connection.json and
honors PROJECT_HUB_URL; project, task and cwd remain explicit:

```text
python "<PLUGIN_ROOT>/scripts/client_entry.py" check exec --project PROJECT --task TASK --stage STAGE --cwd PROJECT_ROOT --title "Verification purpose" --profile PROJECT_PROFILE --profile-version PROJECT_VERSION -- RUNNER ARGUMENTS
python "<PLUGIN_ROOT>/scripts/client_entry.py" check flush --project PROJECT --cwd PROJECT_ROOT
```

RUNNER and ARGUMENTS are the project's actual argv, in any language or framework.
The plugin never selects profiles, implements their tests or acquires project
locks. It does not guarantee detection of commands run directly in an IDE,
terminal or CI. Read the command's JSON result: status describes the runner;
publication=delivered confirms both events were acknowledged, pending requires
explicit flush, and unavailable means durable recording failed. Report a
publication gap independently of the runner's factual result.

Supply a short human-readable testing purpose with wrapper `--title` (MCP/HTTP
`title`). This describes the verification context, not the task name or profile.
Preserve the same title throughout a run; the profile is displayed separately.
The plugin's generic `scripts/hub_check.py exec` wraps an arbitrary runner argv;
it does not select profiles or acquire project locks. Use `--url`, `--project`,
`--task`, optional `--stage`, `--profile`, `--profile-version`, `--cwd` set to the
project root, and `--` followed by argv. Local logs and pending delivery records
live outside the checkout: set `PROJECT_HUB_CHECK_OUTPUT_HOME` to an external
base, or use the per-user `ProjectHub/checks/<root-hash>/` default. Run files,
`receipts/` and locks share that namespace; an optional `--log-dir` stays beneath
it and must be supplied again when flushing.
Do not auto-capture credentials or environment variables. Avoid secrets in argv
and runner output. Revision/scope/profile metadata is supplied by the caller.

Publish observed checks with `hub_check` or the wrapper: start with `running`,
then send a factual finish using the SAME immutable launch metadata and runId.
Global MCP connections use the explicit canonical project/binding and your own
session; never override another agent's identity. The HTTP contract is POST `/api/v1/checks?project=<id>`.
Check state uses flattened `check.*` events owned by the server, never manual
journal edits. Keep requests at most 16000 bytes, logs in files and evidence
paths project-relative. Oversized logs keep the terminal result and a bounded
summary while retaining the external log reference. `passed` requires an observed zero exit. Failed launch,
interruption, missing finish and abandoned execution are not successful checks.

Hub unavailability must not block the runner. Preserve pending events, warn about
the publication gap and retry with explicit `hub_check.py flush` using the same
URL, project, cwd and log-dir. Durable replay sends start before finish with the
original runId. A run without a finish stays running; only after confirming its
child has stopped may explicit `flush --abandon-run RUN_ID` record `unknown`.
Never infer success from stale running state or invent exit codes/counts.
Read publication results before claiming checks are visible; a successful runner
exit alone does not prove delivery. Report remaining gaps to the parent.

`write_outcome_unknown` means the server may have committed the write but its
acknowledgement was lost. `reason` distinguishes timeout, transport, malformed,
oversized and server-error responses. Read back the work/run. For reports and
checks, replay the identical request with its original work/revision or runId
and unchanged content; do not allocate another work/run to recover delivery.
For other writes, refresh the target and revision before deciding what to retry.
`server_unavailable` on a read does not establish the outcome of an earlier write.

To correct an incorrectly reported running or terminal check, read its current
projected event `id` from `/api/v1/checks?project=...` and send the corrected
factual payload through `hub_check` with
`correction={reason: "Why the earlier result was wrong", expectedEvent: "event-id"}`.
The server appends `check.corrected`; it never rewrites the original event.
A competing correction requires a fresh read; identical retries are idempotent.
An explicit correction may repair an erroneous `startedAt`; use `null` when
the true start is unknown, with a summary and retained evidence or log explaining
the correction. Do not invent dates or rerun a check merely to repair its record.
Other launch metadata remain immutable. Preserve the observed finish and exit code.
Only report exit codes/counts actually observed. A failed build is distinct from
failed metadata delivery and cannot be made passed by retrying publication.
When evidence confirms failure but the original numeric exit code was not
retained, an explicit failed correction may use `exitCode=null` with a log or
evidence link and a summary explaining that limitation. Ordinary failed finish
events still require a nonzero observed exit code; zero cannot mean failed.

## Readiness and observations

`hub_begin(task, stage, ...)` is the explicit, trusted start signal. Send it
when actual stage work starts, before edits or checks. Its durable delivery
promotes a planned stage and planned task to active. Resuming existing work
uses `hub_report(work, revision, status='active', result=...)`; the owning
stage link supplies the same trusted signal even without `stage_status`.
Read `planSync` and the stage back at the normal publication checkpoint.
Delivery rechecks active work, its current revision and stage link, a fresh
active session, and open task/stage status. Waiting, closed, stale, unknown,
unlinked or session-only observations never activate an arbitrary stage.
Only planned values are promoted; done, cancelled and blocked values remain.
These journal transitions describe work that has started. The observational
activity badge remains independent and may later become idle or unknown.

hub_plan(task) includes estimates, freshness and selected mainTask even in truncated plans. Percent ranges measure readiness against agreed scope and acceptance, not closed-stage counts. Hours mean remaining agent work. The primary agent can reassess after milestones, scope changes or a progressHint with reviewDue during a convenient checkpoint. This hint requires no timer, polling, automation or separate model run. Do not interrupt an operation or invent progress because time passed.

An explicit user request to continue, proceed without stopping, or keep working is also an estimate trigger when the task is substantial (multiple stages/files, a new API or UI, or work expected to span more than a short turn). Once the task and current plan exist, read `hub_plan` and write a coarse initial estimate before or immediately after `hub_begin`: include a readiness range, remaining agent-hours when knowable, confidence and an evidence-based note. This is a model judgment made at the normal checkpoint, not a background run. Use broad ranges and state the uncertainty rather than fabricating precision; if hours cannot be estimated, omit both hour bounds and explain why. Small isolated fixes still need their single stage and concise result, but no elaborate estimate. A failed or unavailable estimate call never pauses implementation.

An estimate update uses hub_plan(task, expected=revision, estimate={percentLow,percentHigh,hoursLow,hoursHigh,confidence,note}). Both percent bounds, confidence and an evidence-based note are required for that update. Hours are an optional pair; omit both if unknown and explain uncertainty. Unchanged ranges are valid after reassessment. Use 100% only after acceptance. Scope growth may lower readiness; never close a stage to raise percent. Children do not overwrite overall estimates unless assigned to do so.

When recording the user's named primary task, use hub_plan(task,primary=true,expected=revision); primary=false removes the designation. Otherwise the server selects among tasks with active work by remaining hours or latest work. Completed/cancelled tasks are excluded. Use the confirmed project; do not write another project's tasks under an incorrect binding.

Plan status and observed activity are separate. A task/stage marked active does not prove an agent is running. Optional work reports can describe genuine waiting/resumption; a pause does not mean the task is done. Lifecycle hooks provide best-effort observations; missing or stale observations mean unknown. Never fabricate lifecycle signals, poll to keep a badge active, or promise complete observation coverage. Hub hooks must not issue filesystem permission decisions or become an approval gate.

For received explicit edit-tool hooks (apply_patch, Edit, Write), the runtime may
record `diagnostic.edit_without_write_work` when an already MCP-bound actor has
no matching active stage-linked write work. This is advisory bookkeeping evidence,
not a claim that an attempted edit succeeded. Missing identity, path metadata,
root mapping or hook delivery is unknown and must not produce this diagnostic.
Read-only and opaque shell tools are ignored. Observation failures return `{}`;
no diagnostic grants permission, blocks an edit or changes another agent's work.

## On-demand architecture research

Use `research-capabilities` with an object ID before a semantic query. `research`
accepts a typed query (operation, id, optional target/provider/depth/representation)
and queues a local job; poll `job` and page `research-result` until `more=false`.
Prefer `provider=auto`: reuse a fresh result for the requested operation or
choose the configured semantic provider by symbol kind and negotiated capability.
Incomplete source/project diagnostics never prove the absence of relationships;
partial results are not a complete-result cache. Static catalog dependencies and
semantic calls/references have distinct coverage. Stale symbol positions are
refreshed when uniquely recoverable; ambiguous recovery remains explicit.
Depth is positive or `all`; there is no fixed participant preset. `research-object`
reads a current symbol from a fragment without falsely promoting it to authored
knowledge. `research-cancel` cancels owned local analysis; `research-history`
returns recent jobs. `research-save` atomically saves a selected canvas from
server-owned current nodeIds/edgeIds with expected revision, key and title.

Configured external language servers provide symbols, definitions, references,
call/type hierarchy only when supported. Do not supply executable commands via
queries; configuration belongs to the local administrator. Static calls are not
a complete dynamic execution trace. Stale/partial/unconfigured/unsupported states
must remain explicit. Agent-created subsystem descriptions and scenarios use
normal evidenced knowledge changesets; never invent missing steps or silently
replace user maps with the latest background result.
