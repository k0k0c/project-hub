# Native Codex adapter

`scripts/codex_adapter.py` connects to an **owned** `codex app-server` process
over its default stdio transport. It uses the native CLI profile and credentials
in place. It does not copy credentials, inspect rollout directories, edit state
databases, attach to a focused desktop chat, or override model, approval,
sandbox, or permission settings.

The protocol is documented by [OpenAI's app-server reference](https://learn.chatgpt.com/docs/app-server#protocol)
and [developer commands](https://learn.chatgpt.com/docs/developer-commands).
The connection sends `initialize`, waits for the response, then sends
`initialized`. Native thread creation is separate from model generation:
`thread/start` creates a thread; `turn/start` begins the user request.

## Controller interface

Instantiate `CodexAdapter(executable=None, timeout=15)` and keep it alive while
its turn runs. The default executable is `codex` on PATH. An explicit executable
path or argv prefix is also supported. Calls serialize on the adapter.

- `probe()` runs `--version` and the initialization handshake. It returns
  `available`, `version`, `transport: "stdio"`, native-default permission state,
  and individual capability states. Availability proves process/protocol access;
  authentication and desktop attachment remain `unverified`. No thread or model
  request is made. Failure returns `available: false` with a reason.
- `create_thread(cwd)` is an explicit mutation that returns `threadId`, `cwd`,
  and `status: "created"`. It makes no model request. The controller must persist
  the returned ID in its own action record immediately.
- `skills(cwds)` reads native skill discovery for explicit existing directories
  using `skills/list` with `forceReload: true` and returns the raw response.
  It starts no thread or model turn. Directories must be a nonempty sequence.
- `thread_read(thread_id)` reads a summary using `thread/read` with
  `includeTurns: false`, without loading or resuming the thread. The ID must
  belong to the adapter's explicit `allowed_threads` mapping.
- `start(cwd, prompt, thread_id=None)` creates or resumes a native thread, starts
  a turn, and returns `threadId`, `turnId`, and `status: "accepted"`. It does not
  claim completion or verified desktop sidebar visibility.
- `wait_turn(timeout=0)` waits at most 60 seconds and reports `running`, native
  terminal status, or `needs-attention` with a server request. It never approves
  commands or permissions. Completion remains observable after draining events.
- `events()` drains at most 512 buffered notifications/server requests and
  reports `dropped`. Treat payloads as private protocol data: do not publish raw
  prompts, tool output, or approval details in broad Hub responses. Event loss
  is explicit; this is not a durable audit log.
- `close()` closes stdio, waits briefly, and terminates/kills only the owned
  process if needed. Closing during a turn may interrupt native work; retain the
  process until a terminal state or explicit cancellation. A context manager is
  suitable for a probe or bounded create-only operation, not a fire-and-forget
  model launch.

Launching/resuming is permitted only from an explicit user action checked by the
controller. The adapter is a transport primitive, not an authorization boundary.
Do not call it automatically from a discovery scan, background observation, or
task bookkeeping hook. No generic steer or desktop-parent injection is exposed.

## Safe resume

Construct the adapter with `allowed_threads={thread_id: project_cwd}` from the
controller's persisted owned-action records and a `resume_guard(thread_id)`
callback. The callback must verify/acquire an exclusive caller-side idle lease
for that owned thread and return true only when starting a new turn is safe.
Hold the lease through turn submission and its lifecycle. The adapter rejects
an unknown ID, a mismatched requested project, missing/false idle evidence, a
native cwd mismatch, or native status other than `idle`/`notLoaded` before
`thread/resume` and `turn/start`.

The adapter tracks threads successfully created or resumed in its own retained
app-server. A provided ID that is already loaded by that runtime goes directly
from the guarded native cwd/status check to `turn/start`; it does not call
`thread/resume` again. This supports the create → persist ID → start flow:
The native PoC found that Codex 0.160.0 rejects `thread/resume` on a newly created
empty thread. That thread is already loaded; the initial generation path is
`turn/start`, whose native execution remains separate acceptance work. An ownership mapping alone
is never loading evidence: a fresh adapter still calls guarded `thread/resume`.
Loading evidence is cleared on close, stream loss, or I/O abort.

A new app-server's `notLoaded` status does not prove another Codex client is
idle. The controller must refuse resume if external idle ownership cannot be
established; it must not treat the native status alone as a lease. These guards
do not grant permission to message arbitrary existing chats.

## Action idempotency and uncertain outcomes

The controller must persist a unique user `actionId` and canonical payload
before mutation, serialize execution of that action, and replay its stored
result rather than re-submit a request. The app-server interface used here has
no client action-id deduplication guarantee.

For precise checkpoints, call `create_thread` first, store its `threadId`, then
start it using the same retained adapter, persisted ownership mapping, and idle
guard. The adapter starts the already loaded thread without native resume. The convenience
`start` path creates a thread itself; if turn submission fails its
`CodexAdapterError.thread_id` preserves the already returned native thread ID.
Persist `turnId` immediately on acceptance and retain the adapter in the owning
controller until completion or attention. Bind actions to the intended Hub task,
project, cwd, and explicit user trigger.

`CodexAdapterError.outcome_unknown` marks timeouts, disconnects, and invalid
responses where a mutation might have succeeded. A timed-out `thread/start`
can leave a persisted native thread whose ID was not received. A timed-out
`turn/start` can leave native generation underway. Mark the action uncertain,
retain any known thread ID, and require reconciliation; never retry it blindly
or report success. Restarting the controller cannot recover an in-memory owned
transport or prove a prior turn idle. Existing action records must make this
limitation visible.

## Acceptance limits and verification

Fake-child protocol tests live in `scripts/tests/test_codex_adapter.py`. They
exercise request IDs, approvals, event/completion buffering, strict resume
checks, native-default omission, disconnects, errors, and bounded cleanup;
they perform no model calls or production data edits. Run them through the
project's check publication wrapper under a verified agent identity.

A successful native probe verifies installed stdio initialization. A create-only
native PoC can establish that `thread/start` persists on the same machine.
Reading that returned ID through the desktop app is separate acceptance
evidence. Neither result alone establishes focused-desktop attachment, sidebar
registration, authentication for model generation, successful turns, or an
approval UI. `desktopAttachment: "unverified"` and `approvalUi: "unsupported"`
remain explicit until a supported integration is demonstrated.

Native probes and fake-child tests verify only the protocol behavior covered by
the selected environment. They do not establish model generation, desktop
attachment, sidebar visibility or approval interaction. Record the scope and
result of each local verification separately; do not treat a transport probe as
proof of a completed turn.

## Explicit Hub chat actions

`scripts/hub_chat_actions.py` provides `ChatActions(registry,
adapter_factory=CodexAdapter, portal_url="http://127.0.0.1:8769")`. The optional
URL is a trusted server constructor setting restricted to localhost HTTP;
the browser cannot supply a cwd, prompt, executable, or permission override.
The feature is disabled unless `PROJECT_HUB_CODEX_ADAPTER=stdio`. This is an
experimental owned stdio integration with unverified desktop attachment.

- `capabilities(project)` reads local configuration and project registration.
  It makes no native initialization or model request and reports the disabled
  reason, transport, approval-UI limitation, and same-runtime resume boundary.
- `start(project, task, action_id, stage=None, thread_id=None)` is a mutation
  for an authenticated explicit human button action. It validates the current
  project/task/stage, uses the registered primary project root, and constructs
  a bounded prompt from current scope, acceptance, stage progress/results,
  checkpoint/source references, and the localhost task link. It instructs the
  new agent to bind its own identity, retrieve fresh Hub context, and register
  its own work. It copies no complete history or transcript.
- `recent(project, task)` reads up to 20 action receipts belonging to that
  project/task. It never scans native Codex logs or chat databases.
- `close()` closes only this service's retained adapters. Unfinished receipts
  become `outcome_unknown`; shutdown is not native turn completion evidence.

The service stores functional receipts in the existing `registry.sqlite3`
through `registry.connect()`, using a `codex_chat_actions` table. It does not
write task journals or Codex state directly. Each global action ID has one
canonical request digest over project/task/stage/thread inputs. An identical
retry returns the stored current state even if task context subsequently
changes; different inputs with the same ID raise `action_id_conflict` (409).
The current bounded context has its own digest. A SQLite reservation persists
`requested` before native mutation and prevents concurrent double submissions,
including across service instances. No SQLite writer lock spans a native call.

The accepted lifecycle is `requested` → `accepted` → `completed`, `failed`,
`interrupted`, `needs_attention`, or `outcome_unknown`. Owned background workers
wait at most 30 seconds per native wait. They discard private deltas and persist
only receipts/status. No approval is granted automatically; native requests
produce `needs_attention` with a stable explanation that the experimental
transport has no approval UI and desktop visibility remains unverified. Raw
approval payloads, prompts, errors, and tool output are not copied to receipts.
Native timeouts/disconnects yield `outcome_unknown` without a blind retry.

Resume requires a thread retained in this service instance, associated with
the same project, task, and authoritative cwd, plus a completed prior action
verified both in the runtime and persistent receipt. The service serializes
the idle check and submission; the adapter additionally validates native
project/status. Arbitrary original desktop chats, active or attention-needed
turns, cross-task/project threads, and threads whose runtime was lost on restart
are rejected. A restart can read/replay existing receipts but cannot establish
resume proof from those records. A crash can leave a `requested` or `accepted`
receipt without a known final native outcome; its replay does not resubmit.
The user may explicitly create a new owned thread when enabled.

`ChatActionError` exposes `code`, `http_status` (also `status`), and `as_dict()`
with `code`, `message`, and `httpStatus`. Disabled actions return
`adapter_disabled` (503); malformed requests use 400, missing project/task/stage
use 404, ownership/idempotency/resume conflicts use 409. Native launch failures
are persistent action results with stable error codes and HTTP-status metadata.
The controller must preserve the local HTTP origin/authentication checks and
explicit action trigger when exposing this interface. Enabling the feature
does not advertise native desktop resume or prove native desktop visibility.

Fake-adapter service tests are in `scripts/tests/test_hub_chat_actions.py`.
They use temporary existing registries and cover disabled behavior, validation,
context bounds, persistent reservations, concurrent clicks, idempotency,
uncertain outcomes, retained completion/resume, restart and ownership rejection,
and attention without automatic approval. They make no native or model calls.
