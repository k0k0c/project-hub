# Project Hub plugin development

## Transferable local bundle

Build the server, web assets/licenses and canonical plugin with:

```powershell
python scripts/build_project_hub_distribution.py --output .local/distributions/project-hub-0.2.0-local.zip
```

The allowlist excludes project data, Codex profiles, tests and development-only
tracking configuration. UTF-8 text is normalized to LF; deterministic ZIP
entries and per-file SHA-256 cover the distributed bytes. The receiver runs
`python setup_project_hub.py run`; see [local installation](local-installation.md).
The canonical HTTP entry point is now plugin `scripts/client_entry.py`; the
root `project_hub_client_entry.py` is a compatibility launcher. Both portable
and legacy manifests/transports are generated together. Public submission
limitations are recorded in [publication readiness](plugin-publication-readiness.md).

This repository is the source of truth for the installable `project-hub`
Codex plugin. The canonical package is:

```text
tools/project-portal/plugins/project-hub/
```

The package contains the manifest, MCP entry point, hooks, runtime scripts and
the `skills/project-hub/SKILL.md` that defines Project Hub behavior for agents.

## AGENTS.md and SKILL.md

`AGENTS.md` is repository-local development guidance. It covers source edits,
tests, Git safety, data boundaries and the local extraction scope. It must not
be the source of Project Hub runtime behavior.

`SKILL.md` is part of the installable plugin. It defines Hub context binding,
task bookkeeping, plans, reports, child-agent coordination and task closure.
Those instructions are available from the installed plugin independently of
which project an agent is editing.

The packaged `scripts/client_entry.py check exec|flush` command and runtime skill
provide check publication for arbitrary project runners using the installed
connection. Project profiles, test selection, runner implementations and locks
remain outside the distribution. The transferable ZIP also includes
[the check wrapper guide](check-wrapper.md); validate changes through the prepared
package and a fresh receiving installation, not only a repository-local helper.

Keep the bundled workflow in the plugin skill. User preferences belong to the
separate owned `project-hub-user` companion, rather than copied runtime rules in
project `AGENTS.md` or `.codex` files.

## Build and install flow

1. Edit the canonical package and documentation in this repository.
2. Run the focused package checks and the normal test suite.
3. Use `scripts/prepare_project_hub_plugin.py` for a disposable package, or
   `scripts/install_project_hub_plugin.py --url http://127.0.0.1:8769` to update
   the local personal installation.
4. Restart Codex when the installed skill or hooks need to be reloaded.
5. Verify the installed manifest, MCP entry point and skill after installation.

The installer copies the repository package into the local plugin installation
and Codex cache. Those locations are generated artifacts, not source trees.
Never edit their `SKILL.md`, hooks or scripts by hand; make the change here and
reinstall. This keeps the public package, the local installation and future
rebuilds consistent.

The personal updater first verifies loopback `/api/v1/health` identifies a
multi-project Project Hub and declares an absolute data home. It initializes
the separate owned native companion at
`~/.agents/skills/project-hub-user/SKILL.md`, or retains the already configured
owned location. Prepared connection settings reference that skill and the
verified data home. Reinstall preserves its body/history; an unowned skill
directory is rejected. Plugin marketplace guards, backups and native trust
remain separate. The updater does not modify project `AGENTS.md`, foreign skills
or Codex trust, and does not hot-reload a running chat. See
[instruction boundaries](hub-instructions.md).

Project Hub runtime data, journals, coordination databases and evidence remain
outside this source repository. Source code and tests for those capabilities
belong here; live project data does not.

## Explicit stage start and activity

Call `hub_begin` with an existing `stage` when its work actually begins. The
server records a durable activation signal with the work boundary and publishes
planned → active for that stage and a planned task. An owning
`hub_report(status="active")` resumes the linked work through the same path.
`planSync` reports delivery; retry the identical request after an uncertain ack.

Delivery checks current work revision, stage/project linkage, active session
freshness (15 minutes), and task/stage state. It preserves completed, cancelled
and blocked states; stale, waiting, unlinked and session-only observations do not
activate a stage. Plan status persists after the agent stops; `agentActivity`
continues to describe only observed activity. Source-of-truth transitions use
the existing journal and outbox, not a UI-only status rewrite.

## Git checkpoint policy

The Project Hub Git adapter is local-only by default. `hub_begin` records the
current `HEAD` and the claimed project-relative resources. When the owning work
reports `status=done` with `stage_status=done`, Hub creates at most one scoped
local commit for that stage. A task with one stage uses the same checkpoint when
the task is closed; task closure must not create a second duplicate commit.
Pre-existing changes, a changed `HEAD` or already-staged unrelated files stop
the automatic checkpoint instead of being swept into it. Commit trailers retain
the task, stage and work identifiers.

Push is a separate operation and is never performed by `hub_begin`,
`hub_report`, stage completion or ordinary agent work. The browser/API push
action requires an explicit confirmation and a clean tree with a configured
upstream. GitHub links are derived from the configured remote; credentials and
remote workflow state are not stored in Hub.
