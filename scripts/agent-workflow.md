# Project Hub agent workflow

Contract version: 5. Applies to project agents connected through Streamable HTTP MCP, independently of their model. No plugin is required.

## Connection and persistent instructions

Read the invitation as setup material within the user's authorized connection request. Enroll the actual client once with a stable external connection identifier. Unknown client/model/native identity remains unknown. Connection enrollment is global and does not create a project. Credentials stay in private native configuration outside repositories and instruction files. Preserve other MCP servers and the host's permissions.

Save a short application-wide bootstrap rule in the client's documented native instruction mechanism. Save the verified instruction bundle as an immutable local snapshot: workflow.md, user-additions.md and manifest.json. The bootstrap points to that manifest and requires both full files to be read at conversation startup and after compaction. A saved file is not proof of automatic loading: report persistence and new-chat verification separately. Do not place the full workflow in every project rule. For clients with no supported global instruction writer, provide the exact native installation step and report it as pending.

The native MCP tool catalog is the authoritative list of available commands and their input schemas, including action-specific required fields. The bundle also contains api-reference.md generated from that same catalog; it is available as the MCP resource project-hub://instructions/api-reference. Retain it with the snapshot and consult the exact action contract when needed, without inspecting implementation source or guessing field names. A new chat receives the catalog from its MCP client; a rule cannot make unavailable tools callable. If tools are missing or initialization times out, diagnose native HTTP setup and report it as incomplete. Do not substitute a subprocess bridge, alter global proxy settings or claim readiness from an SDK request alone.

After registration, verify native discovery of the complete current tool catalog and execute hub_instructions(manifest) and scoped hub_context through that native connection. Check a fresh conversation independently before reporting new-chat loading. Keep transport discovery, saved rules, conversation loading and optional Hub-to-client control as separate results. A client that cannot install application-wide rules requires its documented manual step; never promise automatic persistence for unsupported hosts.

Call hub_instructions(action="manifest") at startup without a project. Compare revisions by equality; hashes are not ordered versions. If different or a local component is missing/corrupt, read the complete bundle, verify hashes, and publish one coherent local snapshot. Change only the owned bootstrap block; preserve personal instructions. Update the cached files when a normal hub_context/begin/report response advertises a different manifest. Do not repeatedly download unchanged content. Re-read the active native bootstrap after an update or compaction. If offline, retain the last verified bundle and disclose the update gap. No mechanism guarantees that every model obeys rules after compaction; supported host behavior and verification must be reported honestly.

User additions are persistent instructions alongside this workflow. Honor the user's current instructions, native permissions and higher-priority rules. Hub setup material is not authority to bypass approval boundaries. A user's authorization to connect includes installing and repairing owned Hub rules; request further confirmation only for actual host requirements or ambiguous project selection.

Describe the connection using hub_connection(action="describe", profile=...). Include documented client capabilities, project-context identification, native instruction locations and installation status. A profile's current nativeChat is descriptive and does not identify other conversations. Never put credentials, shell commands or arbitrary scripts in a profile.

## Required conversation context

The Hub actor and session are bookkeeping identities, not a substitute for the
native conversation. Use the host's actual current conversation ID as session
when available. Otherwise generate one unique session and retain it across
turns, reconnects and compaction. Pass session on every call. Children must use
their own identity; an inherited parent ID or an agent task name is not their
native chat ID.

When the host exposes the current chat, you MUST send nativeChat on hub_context
before substantive work and on eligible task, plan, begin, report, update and
close calls. Read the host's supported metadata interface first if needed.
Supply client and the actual nativeId or verified conversation openUri. Include
the actual title whenever the host provides it; refresh it after a rename.
Include clientInstance, host and model only when supplied by the host. Never
substitute a task title, Hub actor, random session, account ID or parent's ID.
Use only documented or host-provided links; never invent a deep link.

Check the returned nativeChat/chatContext acknowledgement. Hub retains an
unambiguous saved identity for later calls in the same session, but do not rely
on a connection profile's last chat for a different session. If the host does
not expose native identity or title, omit unavailable fields, explicitly report
the metadata gap once, and continue authorized work with the stable session.
Do not claim chat opening or history synchronization is configured. A parent
relation is reported only through a supported host/catalog relation; nativeChat
has no parent field. Do not encode a parent in title, session or nativeId.

After installation or refresh, report persistentInstructions with scope="application", destination, manifestPath, revision from the current bundle, bootstrapSha256, connectionId and status="saved" or "manual". consent records the user's existing authorization to connect/install; it does not require a second question. Set loadVerified and compactionVerified only after actual native-client tests, never from file creation alone.

## Project binding and recovery

Determine the actual project scope from the current host workspace/repository and its native project reference, never from Hub's installation/data directory or a similar name. Read the short native project rule if present. At the first conversation in an unbound project, call hub_project_bindings(action="resolve", scope=..., requestId=...). Hub lists/discovers exact registered roots; an unambiguous match returns its canonical ID. A new local project may be automatically registered under the authorized workflow. Shared roots or conflicting native references require selection. A client-native reference alone cannot prove a server filesystem location.

Persist the returned bindingId, revision, project ID, connection ID and scope in a small owned project rule. Inform the user when registration/binding is created. Subsequent chats use it and validate through hub_context, without looking up the whole catalog for every request. Send project, bindingId and bindingRevision on every scoped MCP request and an existing registered workspace for source/Git operations. Use hub_projects for explicit discovery or ambiguity resolution. Deliberate unbind is a tombstone; do not silently recreate it.

After saving or removing the owned project rule, call hub_project_bindings(action="verify", bindingId=..., expectedRevision=..., status="saved" or "missing" or "manual", rulePath=..., requestId=...). This is a client persistence report; it does not prove new-chat loading. A deliberately unbound mapping remains unbound after rule removal.

Use hub_project_bindings for read/list/history, revision-checked update/rebind, verify/repair and unbind. Renaming a project does not change its canonical ID. Read action="workspaces" to obtain registered workspace IDs and project revision; action="relocate" changes the registered directory and binding scope with expectedProjectRevision, workspaceId and expectedRevision. Keep the same nativeRef when moving that project. Repair its native rule afterward. Rebinding does not migrate tasks, work, history or active sessions. On a stale binding, stop that scoped write, reload and reconcile; never carry an old task into another project. Hub UI changes mark the client rule as needing synchronization. If a rule disappears, rebuild it from the Hub binding, preserving unrelated instructions.

A partially committed relocation blocks this binding. Read its pendingRelocation and call action="resume" with bindingId and the saved original requestId; Hub replays the original stored arguments. Do not create another relocation or bypass the pending move with old rules. A rejected workspace transaction without a durable change releases that block and permits a refreshed request. A legacy reservation without saved arguments needs reconciliation; never guess them.

## Task pipeline

**Exception before this pipeline:** a Hub launch marked bookkeeping.mode="internal" is an
internal Hub analysis, not a user's implementation or documentation task. Follow
its launch acknowledgement and publish the result only to the designated
knowledge destination at the supplied revision. Do not create or update a user
task, plan stage or work record, and do not call `hub_task`, `hub_plan`,
`hub_begin`, `hub_report` or `hub_task_close` for that internal operation. The
launch envelope is server-owned and explicitly marks this bookkeeping policy.
This exception does not apply to `task-execute`: after acknowledging that typed
request, use the normal tracked task pipeline below.

1. Read hub_context and current projectSettings before implementation, investigation, review or documentation. Confirm returned project and actor. Read only relevant memory; reuse a suitable existing task or create one using hub_task. Every task needs a visible plan stage.
2. Read hub_plan and its revision. Create/update the agreed stage with expected revision. Acceptance criteria and execution stages are separate. Record coarse progress and remaining-work estimates at meaningful checkpoints for substantial work.
3. Call hub_begin with the existing stage and concrete resources before substantive work. Use read mode for research/review and write mode for changes. Resource overlap is advisory; it never authorizes messaging another chat or filesystem access.
4. Complete the user's work and required checks. Publish hub_report with the owned work's revision, factual results, remaining work and durable evidence. Upload immutable artifacts when no registered source workspace is accessible. Work completion alone does not close a task. Mark a stage done only after its criteria/checks pass; verify planSync and read back the stage. For read research/review, publish without stage_status and update the owned stage separately with a fresh hub_plan revision.
5. Update affected authored documentation/architecture with a concurrency-checked changeset or state why none is needed. Preserve generated facts, provenance and user-authored descriptions.
6. Close an accepted task with hub_task_close, respecting current project Git policy. Inspect checkpoint outcome and report pending/failed checkpoints honestly. Push/deploy/publication needs its own user authorization. Closing a chat does not close tasks.

### Important files and deliverables

For tracked user work and task-execute, attach every created user-facing report,
document, diagram or other deliverable to task.sources. Also attach existing
files essential to the assignment or needed to review its result. Do not attach
every file merely read during an investigation, and never attach credentials,
private native configuration or unrelated personal files.

Read the task and current task revision first. Use hub_task_update with the
current expected revision; merge actual registered project-relative source paths
or immutable uploaded artifact paths into existing sources without deleting or
duplicating entries. For a transferred task preserve source-project provenance.
If no accessible source workspace exists, upload the artifact through the
published Hub artifact contract. A local filename or a chat link alone does not
register a deliverable.

Include the same evidence in the stage-linked hub_report. Read the task and
stage result back, and open/read the registered source to verify it resolves.
planSync=saved does not prove task.sources was populated. A small fix need not
create an artificial report file. An internal Hub operation publishes only to
its designated knowledge destination/history and attaches no task source.

Retry uncertain writes with identical operation and request ID. After a confirmed revision conflict, reread before editing. Hub never blocks authorized user work: when identity, transport or storage is unavailable, keep the result and disclose the recording gap. A Hub project may have no local code; tasks, settings, history, documents and uploads still work. Local source import, Git and language-server analysis require an explicitly registered accessible workspace. Never invent one.

## Continuing work across applications

Project access authorizes task, stage and metadata operations regardless of the
application or connection that created them. Keep your own current identity;
never impersonate an earlier actor or change a work's owner to bypass a check.
Start new owned work to continue implementation in another chat or application.

For an accepted historical work that prevents stage completion, read
`hub_context(work=...)` in its project. Explicitly reconcile with `hub_report`
using its current `revision`, terminal `status=done` or `cancelled`, a factual
`result`, and `reconcile={owner, status, reason}` copied from the observed work
with the reason for closure. Ordinary reports remain owner-only. Reconciliation
retains the original owner, IDs, claims history, prior results/evidence and Git
boundary, and audits the current actor. New evidence is additive. It never
captures current source bytes as the historical completed result or proves a
Git checkpoint. Verify planSync and any separate checkpoint outcome.

For active work, coordinate with its worker first. MCP cannot interrupt it;
the user must explicitly confirm that observed work in Hub: task Chats,
Reconcile work records. The local user action is audited separately.
Age or a disconnected app is not proof that execution stopped. A concurrent
report invalidates the revision: reread and coordinate, never blindly retry.
Identical retries retain the first receipt. Other open work still defers stage
completion; reconcile only the specifically accepted or cancelled records.

## Requests launched from Hub

Only declared and configured HTTP/MCP client-control capabilities permit Hub to launch or continue native chats. Reading rules does not itself grant control. The typed envelope carries requestId, connection, canonical project, binding revision, native scope, operation, task/stage or knowledge object, input revisions and result destination. Read it using hub_launch, validate current binding/scope and acknowledge before work. Retry acknowledgements/results idempotently with request IDs. Never substitute a project based on the receiving chat's default.

Research requests restrict the scope to analysis/drafting; do not edit source code, close implementation tasks or widen the user's action. They are internal Hub analysis: use only the launch acknowledgement, the designated knowledge result/history and the supplied revision. Never create a user task, stage or work record and never call `hub_task`, `hub_plan`, `hub_begin`, `hub_report` or `hub_task_close` for this request. Publish only to the stated Hub destination with expected revision. If it changed, report conflict rather than overwrite. Terminal hub_launch calls include the actual acknowledged nativeId. For task execution, begin new owned work after acknowledgement and publish its report; do not reuse a report from before the launch. Task execution uses the normal tracked task pipeline. Completion and a native API accepting a chat are separate states; report native routing/loading as unverified until a correlated agent acknowledgement. Unsupported controls stay unavailable; no shell, stdin or plugin fallback.
