# Local project checks

Agent runs use `project_hub_check_publish.py --title "Purpose of this check"`
with the runner flags below. `PROJECT_HUB_CHECK_TITLE` also supplies the purpose.
The adapter keeps this title separate from the concrete selected profiles.

`python scripts/project_hub_check.py --profile auto --explain` prints the selected
profiles, dependency reasons, exact commands and source-tree digest without
running checks. Omit `--explain` to run. Use `--profile full` for release coverage.
`--profile release` is an alias for `full`.
Every actual run also performs `git diff --check`, including receipt reuse.
`docs`, `documentation-ui`, `html-documents`, `plugin-docs`, `runner`, `css`,
`javascript`, `portal`, `core`, `package`, `artifacts` and `changesets` provide focused feedback;
the selectors and test patterns live in `.project-hub/testing.json`.

The standalone runtime has focused profiles for fast iteration:
`portable-runtime`, `global-agent-connections`, `research-only-ui`, `research-api`,
`installer-lifecycle` and `distribution`. Source-file rules actually select these
profiles; their existence alone is not enough. An EXE build does not invoke the
test runner. A local rebuild for feedback is a development artifact, not an
automatic release gate. Automatic Git checkpoints remain a separate policy.

## Fast development iterations

For an ordinary correction, diagnose the problem and finish one coherent edit
before testing. Inspect `auto --explain` for this task's exact `--scope` paths,
then run the same scoped selection through the publication adapter once. Other
dirty work must not expand task feedback. This applies to web changes, backend
fixes, source launches and local installer rebuilds. Do not run checks after
every small edit, and do not broaden a passed check merely to close a stage/task.

Worktree `auto` refuses to execute an implicitly selected full suite. Its
explanation still reports the conservative selection. For unknown or shared
dependencies inspect the affected contracts and use justified focused coverage;
choose `--profile full` explicitly only when its cross-cutting risk is concrete.
Staged hooks and explicit full/release validation retain complete coverage.

For a localized installer fix run `installer-lifecycle`, build the requested EXE
once, and exercise the changed installer behavior on disposable data. For changes
to payload assembly, embedded dependencies or common startup use `distribution`:
it checks packaging, startup, data separation, activation, HTTP/MCP and desktop
contracts plus bundled JavaScript syntax. Compile only when the user needs an
artifact. A source-only correction does not require an EXE or package acceptance.
Do not repeat a general runtime acceptance sweep when only one packaged behavior
changed. The real compiler in the requested build already checks installer syntax;
a separate syntax-only compile is useful feedback, not another mandatory stage.

Full is reserved for an explicitly requested release, pre-push, or a change whose
cross-cutting risks cannot be covered by targeted integration. Run it once on the
stable release snapshot. Keep durability, concurrency and recovery tests in full;
their runtime cost does not make them necessary for every development iteration.

CSS/UI and JavaScript profiles run the current UI contracts and syntax-check
bundled JavaScript. Local JS changes no longer automatically add every portal
HTTP test. Portal covers HTTP, catalog, document and editing tests.
Core covers task, stage, transfer, storage, settings and coordination contracts.
Package covers plugin, package, lifecycle and Git safety contracts. Full discovers
all `scripts/tests` and `tests` tests plus all JavaScript syntax checks. Auto unions
matching rules after applying each rule's `exclude` patterns. Test-only edits
select exact changed files, including newly added tests, in the internal
`test-files` selection. Explicit `sourceTests` maps local source/UI files to their
affected test files without inventing overlapping profiles. These exact mappings
replace generic source rules for the mapped path; unmapped paths still union
their matching rules. Declared validation inputs, build dependencies and profile
dependencies add their required coverage independently. Mixed edits combine the
exact tests and other paths' profiles. Missing/deleted selected tests fail clearly
and require an explicit coverage choice. Unknown executable paths and truly
shared dependencies still explain full, but worktree auto does not launch it.
Rules are conservative, not static dependency analysis; maintain them with
dependency changes. A clean tree selects diff-only validation. The configured
`javascriptProfiles` controls syntax checks, including focused UI/test selections.

## Selecting enough coverage

Inspect `auto --explain` before execution. Completing a task/stage or creating a
checkpoint does not itself require full. For local changes use these profiles:

- `docs`: Markdown/text and design HTML/CSS in `docs`, root prose and repository
  skill prose. Runs diff validation with no backend unit suite. Design HTML still
  needs visual acceptance when its appearance/interaction changes; this profile
  does not execute embedded scripts. Executable skill helpers remain unknown.
- `documentation-ui`: documentation tree, HTML viewer CSS/JS and Knowledge UI;
  runs their UI, static-serving and shared-control regressions plus JS syntax.
- `html-documents`: HTML import/bundles, immutable bytes, sandbox, document/image
  source, knowledge storage/HTTP and documentation/Knowledge UI contracts.
- `plugin-docs`: plugin Markdown/SKILL text contracts and distribution packaging.
  This exception does not apply to plugin scripts, hooks or manifests.
- `hub-instructions`: the display strings in the exact package resource
  `assets/instructions-catalog.json`; runs instruction, HTTP, settings UI and
  packaging contracts. The resource contains help text only. Runtime behavior,
  recovery commands, ownership and editing remain in `hub_instructions.py`,
  whose changes still explain full and require an explicit coverage decision.
  Other JSON assets remain conservative.
  Settings CSS and JavaScript keep their ordinary UI profiles; mixed changes
  combine those profiles with instruction coverage.
- `runner`: selector, grouped discovery, isolation, staged content, receipts,
  failures, locks and publication adapter tests.
- `artifacts`: any-format CAS, immutable versions, transfer, backup, image/source
  compatibility and upload/download UI, plus bundled JavaScript syntax.
- `changesets`: immutable content boundaries and commit coverage, existing Git
  safety/reconciliation, frozen-index protection and transfer publication.

Use the affected contracts during development, including targeted integration
for backend/storage/auth/HTTP/runtime changes. A module's shared location alone
does not impose full. Keep release/pre-push full; require another integrated full
only for a concrete risk not covered by the selected contracts. Fix regressions
using the reproducing subset. Do not repeat or broaden passed coverage without
changes, a failure or a concrete unresolved dependency.

When another chat's dirty paths broaden auto, limit *selection* for worktree
feedback using repeatable exact relative files/directories, for example:

```text
python scripts/project_hub_check_publish.py --title "Documentation layout" --profile auto --scope tools/project-portal/web/documentation.css --explain
python scripts/project_hub_check_publish.py --title "Documentation layout" --profile auto --scope tools/project-portal/web/documentation.css
```

Scope matches changed paths only; an empty match is an error. Absolute paths,
traversal and scopes on `--staged`, `full` or `release` are rejected. The entire
source snapshot is still tested/fingerprinted; scope does not hide concurrent
edits from receipt validation. Results record both `scope` and `checkoutScope`,
`selectionScope` and `coverage=task-feedback`. This feedback is not a declaration
that every checkout change has been validated. Staged/release checks select all
their required paths. Explicit profile names come from the snapshot config;
adding a profile does not require editing a hardcoded CLI choice list.

## Execution time and diagnostics

Config version 2 defaults `timeoutSeconds` to 1800 seconds per command. Override
with `--timeout SECONDS` (positive finite value, maximum 86400). Version 1 configs
remain readable and keep their 900-second default. Changing timeout changes the
receipt key. Increase an observed insufficient limit in the standard runner;
do not create another full-suite script or treat a timeout as a test assertion.

Selected test patterns are deduplicated and discovered in one Python process per
directory, retaining sibling fixture imports. The timed unittest helper uses the
same discovery semantics for full and focused checks. A nonempty test profile
with no discovered tests fails; explicitly empty profiles such as docs are
allowed. Snapshots without the helper retain legacy discovery commands.

Results include `timings` per executed command and per test (including setup,
teardown and cleanups), counters and skipped tests. Reused receipts have no newly
executed timings; inspect their `reused` result for the original observations.
`failureKind` distinguishes diff, tests, timeout, launch, snapshot mutation and
changed inputs; `stable` independently describes checkout/toolchain stability.
Use this data to target integration fixture setup/worker waits before parallelizing
tests or weakening isolation. Do not infer exact fixture phase cost from a total
test duration. Class fixtures are included in command time, not individual tests.

## Snapshots and receipts

The runner has no Hub imports, calls, database or registration requirement.
It copies tracked and nonignored untracked worktree bytes into a private
temporary source tree. Ignored local data and `.git` are excluded. Check
results, logs, locks and receipts are written outside the checkout under
`PROJECT_HUB_CHECK_OUTPUT_HOME/<root-hash>/` when that variable is set, or the
per-user `ProjectHub/checks/<root-hash>/` default. Tests that require a Git
repository create their own temporary repositories. Symlinks, submodules and
unmerged index entries fail closed. `--staged` instead copies actual index blobs,
preserving the hook's alternate index if present. It does not stash, modify the
index, or test unstaged fixes. Staged config and tests come from that snapshot.

Each execution has its own temporary home, Codex home, Hub home, temp directories
and cleared inherited Git/plugin context. The default service URL is an unused
loopback endpoint; existing integration tests start their own disposable servers.
For manual Hub development, agents must use
`python scripts/hub_source.py --mode development --no-browser` with disposable
data; stop that profile with `--mode development --stop`. The ordinary source
shortcut uses work mode and shares the installed application's user storage.
Do not use that working profile for tests. See the
[source launch modes](windows-installer.md#developer-source-launch).
This is test isolation, not a security sandbox for arbitrary test code. Do not
add tests that access production or external mutable inputs to receipt-enabled
profiles. Installed external libraries, system configuration, or runtime assets
outside the snapshot require a fingerprint extension or disabled reuse.

On Windows, Python 3.13 owner-only temporary-directory ACLs can be incompatible
with the host sandbox token even beneath a writable root. When this is observed,
use native approval for the isolated test command. Do not rewrite ACLs, patch
tempfile security or bypass host permissions in the project runner.

Receipts cover the complete tested file bytes and executable modes, config,
ordered commands, configured timeout, runner implementation, tool executable hashes, Python version
and standard-library/native-module hashes (tests run with `-S`),
platform, Python search paths and effective environment hash. Secret environment
values are never saved. Exact snapshot equivalence permits worktree-to-index
reuse; different line endings or untracked inputs deliberately cause a miss.
Mode is recorded in each result. A narrower profile cannot satisfy full coverage;
an exact-tree full receipt can satisfy a focused request.
Each new receipt includes an exact input manifest (path, mode, byte hash and
size) and an `ExecutionSpec`: absolute argv, effective environment digest,
runtime hashes, manifest/config/runner hashes and timeout. The launcher executes
those resolved commands with the captured environment. Private directories and
timing paths use templates in the spec and are substituted only for that run.
Legacy receipts without these contracts are readable history, never reusable.

The source-controlled `executionEnvironment` policy in the testing configuration
selects native launch normalization. On Windows it resolves the same recognized
Git for Windows installation, replaces its shell-added PATH entries with native
`cmd`/`usr/bin` entries, removes the shell-inserted ambient `HOME/bin` (HOME is
replaced by a private empty directory), and removes MSYS shell variables from
the environment actually passed to tests. Other inputs remain hashed. This
applies before executable resolution and fingerprinting; different tool bytes
are never equated. Legacy configurations retain captured environments.
The real Windows regression compares native launch with an ordinary pre-commit
hook in a disposable repository. Unsupported Git layouts fail explicitly.

Diff preflight has a separate spec, retains the caller's Git context including
alternate index, always executes on reuse and checks stability before success.
Timeout, launch failure or disappearance of a tool still produce a failed result.
Artifact roles never narrow the manifest: tracked/nonignored product bytes all
remain inputs, and uploads outside checkout cannot expand product selection.
External validation inputs are an explicit exception to that last boundary:
`validationInputs` version 1 in the source-controlled configuration declares
`artifacts`, pinned dependency `files`, `builds` and `profileDependencies`.
An artifact entry has `environment`, `path` and immutable `ref`; a file entry
has `environment`, `path`, `sha256` and `mode`. Host locators use declared
`PROJECT_HUB_INPUT_*` variables and point outside checkout. Artifact locators
select the existing knowledge CAS directory containing `blobs/`; both descriptor
and content hashes, sizes and metadata are validated. Original bytes are copied
into the private snapshot at a safe, noncolliding relative path. The locator
variables are removed before tests, and no host locator value is emitted.
Missing, corrupt, unsafe or changed external inputs fail closed. The project
tests use disposable stores only, never a production catalog or data home.

A build entry has a stable `id`, explicit `argv`, relative input patterns and
`profiles`. Matching inputs contribute dependency coverage; acyclic profile
dependencies expand the selected union. Every resolved external target also
participates in auto selection, even for a clean checkout. Unknown coverage
selects full. Declared build commands run before tests; full/release includes
every build and the complete test suite. Roles never remove a declared input.
Only successful, stable runs publish receipts. Before reuse, result and log hashes
must still match. `--fresh` ignores receipts. Receipts are local evidence, not
tamper-proof attestations or substitutes for CI.

`git_changesets.py` supplies read-only many-to-many coverage:
immutable before/after blobs, source repository/worktree identities, original
dirty baseline, explicit actor/attribution and task/stage links. Exact coverage
checks commit and parent bytes/modes plus ancestry, including binary files and
deletions. One shared commit may cover several changesets without task trailers.
An integration worktree may verify coverage from the same repository. Existing
frozen-index commits retain their safety guards and now check exact completed
content against the frozen candidate before commit. Server-owned write work
captures its original boundary in the existing CAS and freezes its completed
bytes on the first acknowledged done report. Physical source bytes are retained
alongside Git's verified built-in EOL projection; other clean transforms require
an explicit adapter. Automatic checkpoints validate parent/candidate content.
New reconciliation requires frozen completed bytes and explicit actor/reason;
one shared commit can satisfy distinct tasks without a matching task trailer.
Legacy reservations retain the original trailer/history check and are labelled
`legacy-scope-and-trailers`, never upgraded by inference. Original snapshots,
errors, IDs and index contents remain intact. Typed outcomes distinguish Git,
content validation, native permissions and publication; a commit already created
before a validation failure is retained as a separate outcome and recovered on
retry.

`hub_git_batch` and `POST /api/v1/checkpoints/batch` prepare a reviewed candidate
from 1–20 completed task/stage checkpoint obligations. Select explicit targets,
current project revision and an attribution reason. Preview can use the current
integration HEAD or one existing non-merge commit. Its immutable CAS contract
keeps every original changeset and association. It composes complete sequential
content chains, identical binary outcomes and disjoint UTF-8 line edits from
linked worktrees. Unknown dirty starts, ambiguous insertions, overlapping edits,
distinct binary outcomes and unsupported transforms refuse; supply a separately
reviewed resolved changeset. Preview does not rewrite old boundaries or outcomes.
Legacy obligations return `legacy_boundary_unproven`; their original history
remains available for separate legacy reconciliation, never inferred ownership.

Inspect all paginated `steps`, `hunks`, `changes`, `changesets` and `files` through
`hub_git_batch(action='details', blob=batchBlob, section=..., offset=..., limit=...)`
or `GET /api/checkpoints/batch-detail`. The UI also offers exact before/after
downloads for candidate steps and individual contributions through
`GET /api/checkpoints/batch-content`. A batch cannot retrieve unrelated CAS bytes.
Reconcile an existing commit with the exact preview `batchId` in `confirmed` and
the same reason; verification compares the complete scoped parent/candidate tree,
file modes and ancestry. Every target retains its checkpoint ID and previous
error. Verified outcomes are stored before journal publication. Identical retries
of a confirmed outcome only publish metadata, without Git reads or writes.

New commits use native permissions, independently of the HTTP/MCP review API:
`python <prepared-plugin>/scripts/client_entry.py git-batch --root ROOT --cas CAS
--batch-blob BLOB --confirmed BATCH_ID --title TITLE [--url URL]`.
Use only `nativeCommit` fields from the reviewed preview. This command reads the
existing CAS, validates the current candidate, and uses the existing frozen-index,
concurrent HEAD/index guards and ordinary hooks. It never modifies work snapshots,
creates a new database or publishes via the portal. It refuses pre-existing staged
changes and never pushes. Afterwards preview/reconcile the returned SHA to credit
all selected targets. Runtime/package installation and native startup acceptance
must still be verified independently of source tests.

Each result now includes `receiptInputs` (source, runner and toolchain hashes)
and `receiptReuse`; the log records the same reuse decision. A miss compares the
latest successful run with the same commands and lists changed fingerprint
components. Old results contain only the source digest, so missing components
are explicitly reported as unrecorded, never inferred to match. No environment
values are saved. This diagnostic comparison does not authorize receipt reuse.

For a check intended to be reused by pre-commit, stage the intended changes and
run the publication adapter with `--staged`. A worktree check tests worktree
bytes: Git line-ending conversion can make even a clean checkout differ from
the index. Such a receipt cannot safely substitute for testing the index.
Do not normalize fingerprints or bypass the staged hook to force a hit.

Logs and JSON results have unique names in the external run namespace.
Successful receipts are atomically published under its `receipts/` directory.
An OS file lock under `locks/` protects only an identical receipt key, preventing duplicate identical
runs and conflicting publication. Different isolated profiles/trees run in
parallel. Locks release on process exit/crash; a lock timeout fails clearly.
No global Hub or production lock is used. Input changes during execution fail
validation and do not create a successful receipt for the new tree.

## Source runtime cryptography

Source-only dependency smoke checks must use the same Python interpreter as the
running source Hub. The prepared distribution can target a different Python
version; its native wheels must not be assumed compatible with a developer's
interpreter. In particular, a `cffi` extension for one CPython version cannot
serve a different version. Install source dependencies for the interpreter that
will run Hub, using the pinned requirements in `requirements-server.txt`.

Run `python -S scripts/tests/test_chatgpt_crypto.py --deps .local/server-deps`
through the packaged check wrapper when verifying prepared source dependencies.
This explicit mode must execute the RSA/EC checks and fail if crypto cannot load.
The general isolated suite may skip this dependency test, so a skipped result
does not prove that the source runtime can verify ChatGPT signatures.

## Hook handoff

Pre-commit retains `git_safety_check.py commit` first, then runs auto staged
validation. Pre-push retains the existing per-ref safety loop and runs full
worktree validation after consuming stdin; it still validates the checkout,
not every pushed object. Full worktree receipts can satisfy full staged checks
only with identical source/config/toolchain/environment inputs. Safety checks
are never skipped by test receipt reuse.

The parent task owns `scripts/project_hub_check_publish.py`, the project-local
publication adapter invoked by both hooks. It passes concrete selected profiles
to the generic wrapper and uses `PROJECT_HUB_CHECK_TASK`,
`PROJECT_HUB_CHECK_PROJECT` and `PROJECT_HUB_CHECK_STAGE` when supplied. Missing
context must still execute checks with an explicit publication warning, without
inventing a task. Preserve exit codes, safety ordering, push stdin consumption,
and the alternate index for staged checks. Do not install hooks, change `core.hooksPath`,
install the plugin or restart production as part of testing. This config and skill
remain repository-local; do not include them in the shipped plugin package.

`--explain` emits one JSON object only: `schemaVersion`, `configVersion`,
`configDigest`, `profileVersion` (the config byte digest), `scope` (changed paths),
`mode` (`staged` or `worktree`), `profiles` (concrete selection), `checkoutScope`,
`selectionScope`, `coverage`, `timeoutSeconds`,
`reasons`, `commands` (test argv arrays), `selectedTests` (exact changed/mapped tests),
`diffChecks` (checkout preflight argv),
`tree` (tested input digest), `validationScope`, `externalInputs`,
`buildDependencies`, the exact `inputManifest` and its hash, and the resolved
`executionSpec` without environment values. Errors go
to stderr with a nonzero exit. The adapter must preserve all selected profiles;
multiple profiles are one union, not an invitation to run the same tests twice.

Focused runner regression checks:
`python scripts/project_hub_check_publish.py --title "Runner contracts" --profile runner`.

Storage/import development uses `--profile storage-import`: whole-project merge,
same-path publication and rollback, shared write admission, local file adapters,
backup HTTP/read sessions, affected settings UI and MCP/ASGI contracts on temporary
data homes. Inspect `auto --explain --scope` first. For the final local installer,
`--profile storage-acceptance` combines this coverage with `installer-lifecycle`
and `distribution` without repeating their shared tests, including bundled
JavaScript syntax. This is focused development coverage, not a release/full run.
`--profile storage-runtime` runs only the real supervisor/HTTP workflow: folder
import, ZIP restoration, publication at the current path, folder changes and
backup creation. It uses disposable data, a private port and no desktop UI.
