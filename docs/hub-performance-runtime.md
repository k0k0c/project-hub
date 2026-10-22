# Prepared reads and parallel Hub runtime

The performance implementation keeps existing task IDs, append-only journals,
ownership, evidence provenance and the registry database. It does not create a
replacement user database. Python remains the implementation language: measured
delays came primarily from replay, copying, broad queries and shared locks.

## Runtime

Install the pinned optional server transport into this checkout:

```powershell
python -m pip install --target .local/server-deps -r requirements-server.txt
python scripts/project_portal.py --projects-home <existing-data-home> serve --transport asgi --port 8769
```

The ordinary startup scripts use `--transport auto`: ASGI when the dependencies
are available, otherwise the compatible threaded transport. `/api/health`
reports `transport`, `runtimeVersion`, `codeRoot`, `dataHome` and the serving PID.
Windows uses one asynchronous listening process and a fixed CPU-sized pool of
two to four spawn dispatch processes by default: one serialized mutation process
and the remaining reader processes with four request threads each. The default
is half the reported CPU count, bounded to 2..4. A request crosses direct process IPC, with no internal
HTTP proxy. This avoids Windows shared-listener accept failures. Other platforms
use the same fixed number of Uvicorn workers, each with four request threads. The I/O process has a
128-request admission bound, two large-body slots, a ten-second body deadline,
and at most 256 asynchronous SSE subscribers. Ordinary JSON requests are capped
at 16 KB; explicit artifact/image uploads and knowledge operations retain their
existing larger limits. Excess requests get 503 and can retry. Long-lived SSE
connections consume no request thread. Remote exposure/authentication remains a
separate project: this runtime retains the existing localhost access policy.
An exited dispatch worker causes an explicit 503, rebuilds the worker pool and
requires refresh before a mutation retry; the server never silently replays a
possibly committed mutation. A worker owns no listening socket.
Dispatch children detect a lost parent and drain accepted work before exit;
they do not wait for responses to be consumed by a dead listener.
Windows dispatch routes mutations to process zero and reads across the remaining
processes, selecting the reader with the fewest outstanding requests. Data reads
arriving during a mutation wait in the bounded parent queue until publication,
or their independent 150 ms admission deadline. They consume no request thread
while deferred; a deadline falls back to the ordinary fresh read. Health and
static files bypass this delay. Shutdown drains accepted packets and worker loss
fails them explicitly, including deferred packets. The one-process configuration retains separate read/mutation lanes
when at least two threads are configured. This isolates CPU work as well as
execution slots, without making the number of processes depend on client count.
The storage transaction limit still applies. This short admission delay is local
to one data home, whose writes already share one mutation lane. A distributed
deployment needs separate storage domains rather than one global publication queue.
The fixed reader-thread limit is configurable with `--request-threads` (1..32).
It is a hardware/workload setting, not a thread allocation per client.
The existing pure `hub_plan(task, expected)` API also uses the read lane even
though its transport is POST. Plan mutations and malformed calls retain the
mutation lane; scheduling does not replace backend identity or argument checks.
Each ASGI registry and coordination pool keeps at most 16 idle SQLite connections
and 64 exclusive leases. Coordination leases retain foreign-key enforcement and
open existing databases only. Returning a lease rolls back unfinished transactions.
Each checkout verifies database identity before lending a cached handle; shutdown
and a detected replacement discard cached handles. Standalone tools retain their
short-lived connections.

## Preparation and freshness

Prepared-view dependency digests are reused per owner and committed SQL
generation. Triggers on heads, ownership, transfers and checkpoints advance one
generation atomically for inserts, updates and deletes, including recovery and
direct SQL. Readers capture generation and inputs in one transaction and retain
at most 64 digest pairs, keyed by database identity. A replacement or generation
change recomputes the same public content hashes; rollback preserves the prior
generation. File freshness is still checked on every request. Producer
publication still compares complete fresh dependencies under its SQL reservation.

Rebuildable SQL tables in the existing registry hold tasks, indexed evidence
registrations, normalized events, compact task lists and task details. A cold
read or changed journal prepares the projection once under the existing writer
protocol. Warm readers use immutable serialized views and current SQL ownership.
Source authorization does not replay every task or event. History pagination
sorts small event metadata, then reads only the selected event bodies. Internal
journal/settings freshness uses a restricted data context with no source root or
evidence API. Source access, canonical root checks and cold recovery still obtain
a fresh full store. The
browser reuses history pages by project, task, filter and data revision.
The server also retains at most 64 immutable history pages / 8 MiB per worker,
keyed by the verified domain revision, owner and pagination/filter parameters.
Concurrent cold page reads share one producer; writes and transfers invalidate
the key automatically.
History queries start with the current owner's indexed task references instead
of scanning every project's event table. The selected page still retains the
legacy chronological numbering, filtering and transfer order.
Prepared pages use a separate compact event projection for history counts,
primary selection and progress. They hydrate only the last 24 visible bodies;
checks retain their complete metadata. Complete history remains in indexed SQL
rows and is loaded only for explicit legacy full-state consumers. Updating a
task does not rewrite a journal-sized JSON view.
HTTP state and Git read prepared task bodies without reconstructing complete
history. Git loads at most 50 push receipts. Explicit legacy full-history APIs
retain their existing complete result.

View computation runs outside the writer barrier using immutable SQL inputs.
One producer per project coalesces requests across threads and processes; the
derived-view lock is separate from the writer lock. Builders reuse the initial
content proof only while preparing an unpublished result and bypass intermediate
page caches. Publication freshly rechecks files, coordination and settings,
then compares heads, ownership and checkpoints in the same SQLite transaction
that publishes the page, detail rows and hint. Pending stage transfers prohibit
optimistic publication. A racing mutation gets one serialized retry. A
writer holding the barrier bypasses the producer lock to avoid lock inversion.

Journal content digests name the exact bytes used for a projection. Every
freshness check opens the file with read permission. Digest reuse additionally
requires the same file identity, size, write time and metadata-change time:
NTFS `FILE_BASIC_INFO.ChangeTime` on Windows, ctime on POSIX. Restoring ordinary
mtime does not hide an edit. Unsupported Windows filesystems hash on each read;
a watcher is never the sole freshness proof. Replacement during projection is
retried, and unavailable/corrupt inputs fail rather than lending an old success.
Direct privileged manipulation of filesystem change timestamps is outside this
local file-change protocol; administrative restores should restart the server.
Verified file tokens and digests are also published with their SQL index head.
Other workers open the current file and compare its token before reusing that
proof, so an ordinary append does not make every worker scan the same journal.

Images are keyed by current original bytes, variant and encoder version. Atomic
derived blobs live in `<data-home>/prepared-sources`; per-content OS locks
deduplicate conversions across workers. Registered images are prepared in a
bounded background queue. Requests still check current ownership and current
original bytes, including conditional requests. Derived integrity is verified
before 304. Missing originals are explicit errors and can be retried after the
file reappears. The cache is disposable; background maintenance targets 1 GiB
and 2,048 entries, with temporary overshoot between one-minute sweeps. Lock files
use fixed stripes. Maintenance never removes originals, journals or write intents.

One revision producer per worker supplies immutable section hints to all tabs.
The minimal hint is persisted with the prepared view, so unchanged notification
polls decode only revision/settings/relation fields, without decoding all tasks.
Host/session discovery runs in a separate bounded observation pool and shares
one display-only cached result across processes in the existing registry.
A single project producer refreshes that observation; the cache retains one
entry per project. It never authorizes an agent or establishes its liveness. Coordination
SQL changes schedule observation immediately; host metadata is checked at most
every ten seconds. Knowledge revisions invalidate the cached navigator, while
unchanged remounts preserve already prepared items. Large graph/layout scripts
load only when architecture is opened. Agent plan/progress reads request the
selected task instead of downloading the complete journal.
Projects with no stream/API observation for 30 seconds stop background polling;
reconnection prepares a fresh initial hint.
An already registered agent's pure plan read revalidates its catalog assignment,
session project, canonical root and workspace without the journal writer
barrier. Cold bindings and changed assignments use the serialized lifecycle.
Unchanged bindings reserve no SQLite writer transaction. Already queued lifecycle
or plan reports retain serialized delivery before the plan response; an item
arriving after the empty-queue check remains durable for the next ordinary call.

## Writes, restart and rollback

Validated appends first persist an exact suffix intent in the registry, then
append/fsync that suffix. Recovery recognizes an already completed append or a
proven partial suffix and finishes exactly once. An unrelated replacement or
ambiguous empty file fails closed; inspect it before recovery. SQLite/journal
publication is recoverable, not one cross-file atomic transaction. Derived SQL
heads can lag and are rebuilt from authoritative journals. Semantic history and
Git evidence retain the existing deterministic migration path.
Ordinary writers retain the durable intent until the matching SQL head, file
proof and prepared page are published. The intent is removed in that transaction,
so competing readers cannot see a new journal with no marker and an old head.
While an origin writer is active, readers may use its previous completed SQL
head with matching predecessor file proofs, or a verified post-append token
stored against that exact intent. They probe the origin lock, not an unrelated
writer's global lock. Changed/missing proofs fall back to recovery; an inactive
writer always recovers. Stage transfers retain the serialized recovery path.
Restart recovery first publishes exactly the verified journal bytes and consumes
the intent with a version-zero migration marker; deterministic history migrations
run afterwards and publish the current version. A migration cannot
make its own audit append conflict with the still-pending recovery suffix.
New intents retain the exact previous digest, size and suffix; their empty
`after_hash` denotes the suffix-proof format. A complete post-write scan verifies
the previous prefix and exact suffix together and obtains the resulting digest
in one pass. Existing intents with a 32-byte resulting digest remain recoverable.
A current verified file token allows the ordinary writer to read only the last
byte before appending. Unsupported or changed file identities use the full proof
path; every successful write still performs the complete final verification.
A cold head is prepared before acquiring its project's non-reentrant journal
lock. The append checks exact bytes again while locked and rejects an intervening
replacement rather than attempting a nested replay.
An indexed ordinary append projects the affected task and updates its SQL row.
The complete current-owner hierarchy is still validated before durability;
owner-relative links and legacy parents stay separate from origin journal data.
The portal can request a small durable revision acknowledgement and then refresh
its prepared view. The default mutation response remains compatible.
Settings writers atomically replace complete validated files. Ordinary settings
reads open one completed version without reserving the task journal writer;
corrupt externally edited files still fail validation. Agent context links read
ownership metadata rather than decode task bodies and the entire journal. A tool
execution verifies each canonical Git boundary once; the next request verifies
it afresh, without an identity cache across requests.
Ordinary notes and summary edits advance a warm prepared page before appending
the journal. Its changed task, source revisions and recent history are published
in the same SQLite transaction as the new index head. Readers cannot observe a
new head with the previous prepared page. Exact file inputs, ownership,
checkpoints, coordination, settings and clock are checked before publication;
changed dependencies or an event preceding existing history use the full builder.
Already published views with an exact current key bypass cold-build queues.
Unchanged task detail bodies stay immutable on an ordinary append; replies obtain
their origin sequence from the exact captured compact view. A note therefore
does not rewrite every detail row. The final append proof streams the complete
prefix and exact suffix in bounded chunks, preserving both verification and fsync.
Large serialized pages use versioned compressed blobs in the same derived SQL
table, reducing WAL write amplification. Small pages and legacy TEXT rows remain
supported. Decompression checks the format, stream completion and a 64 MiB bound.
Journals, durability markers, ownership and checkpoints retain their original
storage and durability.
Head, pending intent and matching file proofs are captured in one SQLite read
transaction. Fresh file checks still decide whether that captured head can be
served; batching metadata does not cache file freshness between requests.
If a file token overtakes the captured SQL head, readers recheck the append
publication before hashing a successor journal. A miss grants no freshness;
unknown or unmanaged changes retain the locked full-content check and recovery.
Ten-second display refreshes reuse the unchanged task, history, relation and
checkpoint projection. The page keeps private compiled journal facts needed for
progress; clock refresh recalculates activity and progress from these facts and
current coordination rows. Content, coordination sequence, settings or relation
changes retain the complete builder, final fresh validation and atomic CAS.
Private progress inputs never appear in public responses; older pages rebuild
once when those optional derived inputs are absent.
Task writes decode the affected task and retain the complete owner graph as
small records containing IDs, types, parents and links. Hierarchy and cross-owner
link checks still see the entire graph; unrelated sources and stages do not need
to be copied twice. These records are published atomically with each task and
index head. Version 4 rebuilds earlier derived indexes from the same journals.
Standalone and ordinary full-input callers keep full bodies.
The writer reuses private encoded fragments of unchanged tasks. Each page header
captures its origin sequences; every public full, summary, detail and task-list
reply overlays those exact sequences and hides the internal header. Older captured
pages retain their own sequences after a later write. The private writer cache
is bounded to four owners and 16 MiB of encoded pages, compares the exact SQL key
and both bodies, and is updated only after a successful atomic publication.
The cache also retains the exact compressed SQL blobs, so a repeated writer can
reuse its private decoded page only when both persisted blobs match. A replaced
or corrupt blob still follows the decode/rebuild path. Summary-only updates skip
unchanged task-graph and source extraction work. Seed digest reuse checks the
fresh file token before preparing or finishing an append. Final prefix/suffix
verification uses one reusable 1 MiB buffer; it still reads and proves every byte.
An ordinary task-update acknowledgement uses the content revision of its exact
committed prepared publication. It does not reread every origin after committing.
CAS misses, semantic rebuilds and checkpoint transitions retain the fresh fallback.
Subsequent mutations always validate their expected revision independently.
Decoding a prepared task response also resumes persisted pending Git checkpoints
from their existing identifiers. Compact stages keep only the pending identifier
and status needed for this recovery. The scheduler freshly checks each ID and
deduplicates active jobs; warm reads do not rebuild history or scan all checkpoints.
Prepared-page format 5 replaces older summaries once so pending-stage identifiers
are present. The journal/event/task-graph index remains version 4 and is reused.

Back up the existing data home before operational migration. New derived tables
and blobs may be rebuilt; `journal_append_intents` are durable user writes and
must never be discarded. Before rollback to a version without this recovery
protocol, start the new runtime, verify recovery and confirm that the intent
table is empty. The old runtime can then read the existing journal format.

## Measurement and testing

HTTP replies include `X-Request-ID` and `Server-Timing` for lock wait/hold,
freshness/rebuild, decoding, file IO and serialization. The disposable
`scripts/benchmark_hub_concurrency.py` measures 1/10/100 clients on a synthetic
200-task, 5,000-event fixture with 49 stages, 95 sources and a journal comparable
to the real heavy project. It includes actual writes, overlapping agent/file
reads, 100 SSE subscribers and revision receipt. CPU/RAM samples cover the serving
PIDs observed through health requests; the listener and mutation process may be
absent, so these samples are not total runtime CPU/RAM. It never
discovers or writes real user projects. Its 200-session observation fixture is
also isolated using `PROJECT_HUB_OBSERVATION_HOME`, which affects display metadata
only and does not change verified API identity. Cold labels after warmup are explicitly
concurrency probes, not claims about first-ever migration cost.

The standard test worker now reports setup, body, teardown and cleanup timings.
Private fixtures live outside the checkout, with a Git discovery ceiling, so a
fixture without its own Git repository cannot find the Hub index or fingerprint.
Long evidence paths also remain within native Windows path limits.
The existing profile, release and pre-push rules remain in force. Customizing
test policy is tracked separately. The finished shared-contract snapshot needs
one integrated full run through the existing publication adapter.

Acceptance requires a sustained run with `--require-capacity`: the workload,
achieved request rates, latency limits, zero errors/drops and all 100 SSE revision
receipts must pass on the finished runtime. Earlier measurements are not evidence
for a later source snapshot. These are server/network measurements on the
synthetic fixture, not browser paint timings or a claim about 10,000-client
capacity.

Save each measurement with its runtime version, workload, achieved rates, latency distribution, errors and SSE receipts. Record the process and memory sample boundaries separately. A result validates that measured configuration and workload; later changes need their own required checks. Keep acceptance limits fixed while addressing failed measurements.

Large deployments need stateless request nodes behind a balancer, shared artifact
storage and caches, durable background jobs, and a database with partitioned
write domains and read replicas as measured load requires. SQLite, authoritative
local journals and the data-home writer barrier are explicit limits of this
local rollout. Increasing clients never creates a thread or process per client;
the next storage migration must remove these global limits, rather than multiply
local writer processes. There is no 10,000-client acceptance claim.

Upstream contracts: [ASGI HTTP/SSE](https://asgi.readthedocs.io/en/latest/specs/www.html),
[Uvicorn deployment](https://www.uvicorn.org/deployment/),
[Windows file change time](https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_basic_info).
