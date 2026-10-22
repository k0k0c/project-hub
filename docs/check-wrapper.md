# Generic check wrapper

Use `--title` for the human-readable purpose of each run, separately from its
`--profile`. HTTP/MCP use the optional `title` field (1-240 characters), immutable
across start/finish delivery. Older events retain their original titles.

Publication uses the shared client's bounded 15-second timeout so a busy local
Hub can acknowledge a durable write. Timeout/offline errors leave replayable
events and never replace the runner's factual exit code.

The canonical plugin ships `scripts/hub_check.py`. It executes arbitrary argv
without shell interpolation and publishes observed check runs; it contains no
project profiles, selection rules, runner implementation or project locks.
The prepared plugin exposes it through `scripts/client_entry.py check`, using
the receiver's `connection.json` URL (or `PROJECT_HUB_URL`). The installed runtime
skill requires agents to use this command for tests, diagnostics and verification
builds after selecting the project's own required checks. Locate the plugin root
from the installed skill or `PLUGIN_ROOT`; no creator repository, copied project
helper or project-specific Hub runtime rules are needed.

Keep the project's existing runner, profile names/versions and selection rules.
Profiles are opaque metadata to Hub. If the project has no profiles, omit those
fields and use its existing command with a factual testing purpose. Hub does not
install a profile configuration, select a suite or interpret test output.

Use the project's root as `--cwd`. Local logs and durable outbox records are
written outside the checkout. Set `PROJECT_HUB_CHECK_OUTPUT_HOME` to an
external base when needed; otherwise the runner uses the per-user
`ProjectHub/checks/<root-hash>/` namespace (with run files, `receipts/` and
locks). `--log-dir` must remain under that external namespace and must also be
supplied on later flushes.

```text
python "<PLUGIN_ROOT>/scripts/client_entry.py" check exec --project PROJECT --task TASK --stage STAGE --title "Verify changed behavior" --profile PROFILE --profile-version VERSION --cwd PROJECT_ROOT --scope src -- python project_runner.py focused
python "<PLUGIN_ROOT>/scripts/client_entry.py" check exec --project PROJECT --task TASK --stage STAGE --title "Run custom JavaScript checks" --cwd PROJECT_ROOT -- node scripts/verify.mjs
python "<PLUGIN_ROOT>/scripts/client_entry.py" check flush --project PROJECT --cwd PROJECT_ROOT
```

Use the project ID verified by your own Hub context and an existing task/stage.
The direct `hub_check.py exec|flush --url URL ...` entry point remains supported;
the configured entry point also accepts an explicit `--url` override.

Everything after `--` is the runner's argv. Pass values as individual arguments
using the calling shell's normal quoting. The wrapper does not interpret shell
operators. `--stage`, `--profile`, `--profile-version`, repeated `--scope`, and
`--revision` are optional. Revision is caller-supplied JSON with optional `head`,
`dirty` and `fingerprint` fields; `head` and `fingerprint` may be null. The
wrapper does not collect Git state, credentials
or environment variables. Avoid credentials in command arguments and output:
argv is published, and combined stdout/stderr is retained in the local log.

Each HTTP request posts the bounded check object to
`/api/v1/checks?project=PROJECT`, using the existing Client's loopback-only URL,
disabled proxy and redirect restrictions. A short transport timeout limits the
effect of an unavailable Hub. The child command still executes and returns its
actual exit code; launch failure records `unknown` and returns 127, while
interruption records `interrupted` and returns 130.
Publication failure is warned separately and does not change the child result.
The final JSON has separate `status` and `publication` fields: `delivered` means
both events were acknowledged; `pending` means they are saved for explicit flush;
`unavailable` means durable recording failed. A passed runner with pending delivery
is not yet a published check. Flush returns a factual pending count and exits
nonzero while delivery remains incomplete.
Local recording failure also warns and permits execution, but cannot promise
durable delivery. Input errors are rejected before launching the command.

`start.json` stores the project and running payload. `finish.json` stores the
terminal payload with the same runId, command, scope, profile/version, revision,
startedAt, task, stage and log metadata. `delivered.json` is written only after
both HTTP requests succeed. Retries resend start before finish with the original
runId; the server must accept identical retries without regressing terminal state.
There is no background retry, lock or selection policy. Do not manually rewrite
outbox records. Local outbox files are delivery records, not a second Hub database.

A killed wrapper can leave a start without a finish. `flush` only republishes
running in that case and returns nonzero while records remain pending. After
independently confirming that the child has stopped, explicitly use
`flush ... --abandon-run RUN_ID` to publish `unknown`, without inventing an exit
code. Do not abandon a live wrapper. The wrapper handles SIGINT/SIGTERM and
cleans up its child process group/tree; an uncatchable kill or machine shutdown
cannot guarantee cleanup or a finish record. Neither missing observations nor
an abandoned run imply success.

`hub_check` MCP accepts the same event fields without a project argument. The
server binds the project from the verified session and calls
`ServerHub.check(session, **args)`. Legacy local Hub mode returns `server_required`.
The server owns validation of task/stage ownership, immutable metadata, ordering,
deduplication and flattened `check.*` state events. The shared packaged validator
accepts at most 15000 bytes of check metadata; the MCP transport additionally
bounds its full envelope to 16000 bytes. The wrapper limits launch metadata to
13500 bytes to reserve room for the finish. Large logs remain external files;
requests carry relative paths. If a log is too large to publish, the terminal
result is still retained with a bounded summary and the log reference for
later inspection.
The runner may supply its own nonnegative integer `counts`, `summary` and `evidence` via the MCP/HTTP
contract. The generic wrapper does not parse test framework output or fabricate
counts. Server ingestion and complete end-to-end acceptance are separate from
the focused wrapper and client contract tests.

Direct IDE, terminal and CI commands are not guaranteed to be discovered. Such
commands must invoke the shared wrapper or explicitly publish their observed
lifecycle through the same API. Existing project runners may remain independent
of Hub; the installed command provides the publication boundary around them.
