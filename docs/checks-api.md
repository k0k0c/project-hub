# External check publication

Project Hub records checks; it does not select project test suites or own their
resource locks. Project skills, profiles, dependency mapping and runners remain
outside the installable plugin. An agent follows those local instructions and
executes the resulting command through the plugin's generic check wrapper.

## Transport

`POST /api/v1/checks?project=<id>` records one lifecycle event. `hub_check` uses
the same fields and the MCP session's bound project. The server never executes
the supplied command. `GET /api/v1/checks?project=<id>&offset=0&limit=50` returns
`{runs,total,next,revision}`; limit is 1-100. The existing state endpoint keeps
its latest-30 preview. Paging exposes older runs without manufacturing history.

Required launch fields: `runId`, `task`, `command` (argv array), `startedAt`
(ISO8601 with timezone), and `status: running`. Optional immutable fields:
`title` (human-readable testing purpose, 1-240 characters), `stage`, `profile`,
`profileVersion`, `scope` (relative paths), and `revision`
with `head`, `dirty`, `fingerprint`. Profile and revision metadata are opaque;
Hub does not decide whether that profile is sufficient or reuse its results.

Terminal updates repeat identical launch metadata, set `finishedAt` and choose
`passed`, `failed`, `interrupted`, or `unknown`. Passed requires exitCode 0;
failed requires a nonzero integer. Interruptions or uncertain process outcomes
are never successful checks. Optional result fields: `durationMs`, `summary`,
`counts` (nonnegative integer counters), `log` (relative path) and `evidence`
(`{label,path}` entries). Logs are registered evidence, not arbitrary file reads.
Avoid credentials in argv, summaries and logs. Metadata is bounded to 15 KB;
large output belongs in the referenced log, not in a journal event.

## Identity and recovery

The existing journal is authoritative; no additional run database is created.
New starts require a task belonging to the selected project. The original
task journal retains events after ownership transfers. `originProject`,
`ownerProject` and `launchProject` distinguish historical origin, current task
ownership and actual execution context. Log provenance follows launchProject.
No project name or test command is hard-coded.

Run IDs cannot be reassigned to another task or launch metadata. Identical
retries are idempotent. Conflicting terminal results are rejected. Start must
precede completion; an offline publisher replays both in order. Task/stage
transfers and stage removal cannot detach a running check. Explicitly record
unknown/interrupted when the process outcome cannot be recovered; elapsed time
alone does not establish that a process has stopped.

The wrapper is the observation boundary. Direct commands outside it are not
automatically detected. When Hub is unavailable, the command still executes;
pending publication must remain visible locally and be retried without turning
a real failure into success or fabricating historical runs.

## Audited corrections

To correct a recorded result or complete a check whose recorded start is wrong,
submit the same check identity with a terminal status and
`correction: {reason, expectedEvent}`. Read the current projected run first and
use its `id` as `expectedEvent`, including when it is still `running`. A stale
event is rejected. Corrections append `check.corrected` events and preserve
every original receipt; they never execute the command or edit the journal.
Exact retries of both original receipts and historical corrections remain
idempotent even after subsequent corrections.

`runId`, task/stage, command, title, profile, scope and revision remain immutable.
Only an explicit correction can change `startedAt`; that change requires a
nonempty summary and a log or evidence link explaining the recovered facts.
Use a factual timestamp when retained, or `startedAt: null` when the original
timestamp is known to be wrong and the actual launch time is unknown. Null is
never accepted on an ordinary start or result. Keep `finishedAt` factual;
chronology is enforced whenever the corrected start is known. Do not invent
a start or duration merely to satisfy validation. Passed still requires a
recorded exit code of zero. A failed correction with an unknown exit code
requires explicit `exitCode: null`, summary and evidence.

For example, a receipt entered with a future start can be corrected to
`startedAt: null`, the observed earlier `finishedAt`, `status: passed` and
`exitCode: 0`, with the original log, explanatory summary and current event ID.
An unavailable outcome must instead remain `unknown` or `interrupted`.
