# Previous Python/plugin installation

Project Hub stores project history, task results and documentation and provides
advisory coordination for Codex chats. The bundle includes the local server,
existing web UI, shallow code scanner and Codex plugin. It contains no project
history, Codex profile, credentials or machine-specific installation paths.

## Install and start

Install Python 3.10+ and Git on PATH. Install a current Codex CLI that supports
`codex plugin marketplace add` and `codex plugin add`. Extract the ZIP and open a
terminal in its `project-hub-0.2.0` folder:

```powershell
python setup_project_hub.py verify
python setup_project_hub.py run
```

The first run verifies every bundled file, installs the runtime, prepares an
HTTP-only plugin for this machine and registers `project-hub@project-hub-local`
with the standard Codex CLI. It then starts the server in the foreground at
http://127.0.0.1:8769. Keep that terminal open; Ctrl+C stops the server. Later
`run` calls start the existing installation. Open the URL to view projects.

Defaults on Windows are `%LOCALAPPDATA%/ProjectHub/app` for the runtime and
`%LOCALAPPDATA%/ProjectHub/data` for writable data. On other platforms they are
`~/.local/share/ProjectHub/app` and `~/.local/share/ProjectHub/data`.
`PROJECT_HUB_HOME` overrides the data directory. Choose custom paths/port at
installation when needed:

```powershell
python setup_project_hub.py install --install-root "C:/Apps/Project Hub" --data-home "C:/Data/Project Hub" --port 8770
python setup_project_hub.py serve --install-root "C:/Apps/Project Hub"
```

Runtime and data must be separate directories. A custom port is written to the
prepared plugin configuration as well as the server configuration. The installer
refuses an unowned destination and an existing Project Hub from a different
marketplace. Inspect that installation before choosing a migration path.

## Codex and projects

Review the installed plugin's hook definition and apply the normal Codex trust
prompt. Installation does not grant hook trust or filesystem permissions. Open
a new chat and verify that startup context identifies that chat and its project.
The server must be running for MCP tools; hooks remain best effort when it is
unavailable. Enable the plugin/MCP server through the normal Codex controls if
your policy leaves them disabled.

The server discovers saved local Codex projects through a read-only desktop
catalog adapter. An empty or unavailable catalog starts with no discovered
projects; it does not fabricate projects or import history. Add/select projects
through Codex, then refresh Hub. Discovery depends on the supported desktop
metadata format rather than a stable public API.

The generated plugin uses loopback HTTP only. `PROJECT_HUB_URL` can override its
URL for MCP, hooks and check commands; remote URLs are rejected. The server binds to 127.0.0.1.
It has no remote authentication or multi-user service in this release.

For a server-only or manually registered installation, use
`install --skip-codex-registration`. It still prepares the plugin and local
marketplace under the application folder. Register them later with:

```powershell
codex plugin marketplace add "C:/Apps/Project Hub" --json
codex plugin add project-hub@project-hub-local --json
```

## Native user instructions

The Python installer creates a separate owned companion skill at
`~/.agents/skills/project-hub-user/SKILL.md` and an ownership marker beside it.
Location and history stay in the Hub data directory's `instructions` folder;
the bundled plugin workflow and defaults remain separate. Reinstall preserves
the existing skill body. A manually deleted owned file can be restored by the
installer or the Settings page's explicit reset at its configured location.

The Settings instructions tab edits only this skill's Markdown body, preserving
metadata. Its GET creates nothing; revisions protect against conflicting edits.
Reset uses the current bundled defaults. Project `AGENTS.md`, other skills,
project hooks and the plugin cache are not edited by this instruction editor.
Codex reads the skill through native discovery/application, including explicit
`$project-hub-user`; Hub responses do not deliver policy or reload a running chat.
Automatic application by every chat is not guaranteed.

On a new server-only installation, `--skip-codex-registration` without an
explicit skill location creates a private data skill outside native discovery.
To select a native location while skipping plugin registration, pass the exact
companion directory, for example:

```powershell
python setup_project_hub.py install --skip-codex-registration --user-skill-root "$HOME/.agents/skills/project-hub-user"
```

An existing installation retains its configured skill location; moving it is a
separate explicit migration. The instructions page reports whether the file
is connected to native discovery. Its hooks JSON recovery template contains
the current Python/package paths; the user imports it and reviews trust in
Codex. Copying the template does not change existing hooks or prove execution.
See [instructions and capabilities](hub-instructions.md) for the work lifecycle
and extension boundary.

## Project checks

The installed plugin includes the shared check wrapper and agent instructions.
Each project keeps its own test profiles, commands, scripts and language tools;
Project Hub records their execution rather than choosing tests. No project-local
Hub helper or copied runtime rules are required. With the example installation:

```powershell
python "C:/Apps/Project Hub/plugins/project-hub/scripts/client_entry.py" check exec --project PROJECT --task TASK --stage STAGE --cwd PROJECT_ROOT --title "Verification purpose" --profile PROJECT_PROFILE -- python project_runner.py focused
python "C:/Apps/Project Hub/plugins/project-hub/scripts/client_entry.py" check flush --project PROJECT --cwd PROJECT_ROOT
```

Use the verified Hub project/task/stage and the actual project runner argv.
The plugin reads this installation's configured port. Offline checks still run
and retain pending delivery beneath the project's `.local/checks`; runner status
and publication status are reported separately. See [check wrapper](check-wrapper.md)
for quoting, optional metadata and recovery. Direct commands launched outside
this wrapper are not guaranteed to appear in Checks automatically.

## Updates and recovery

Stop this foreground server, extract the new ZIP and run `install` again with
the same application directory. Existing data path and port are retained unless
explicitly changed. The previous owned runtime is kept in a sibling
`app-previous-...` directory, and Codex receives a fresh cache version. User data
is outside both runtimes and is not copied, deleted or migrated by installation.
If Codex registration fails, the prepared application remains available; inspect
the error and retry installation. Hook trust remains a user decision.

The service starts no scheduled task or background helper. Automatic startup is
an optional operator choice. Optional TIFF/HEIC previews require the separately
pinned dependencies in `requirements-images.txt`; the standard server needs
only Python's standard library. The parallel ASGI transport uses the pinned
`requirements-server.txt` dependencies; install them into `.local/server-deps`
as described in [performance runtime](hub-performance-runtime.md). Java type parsing additionally needs a local JDK;
without it, Java files remain in the inventory and the scanner reports the
unavailable adapter.

## Bundle integrity and provenance

`distribution.json` records SHA-256 for every distributed file, the normalized
source tree and source Git revision/dirty state. ZIP timestamps and text line
endings are deterministic. Binary assets are preserved. Vendor versions,
licenses, source links and byte-format notes are included under
`tools/project-portal/web/vendor`; see also `SOURCE-NOTICES.md`.

This is a local handoff package. Official public submission has additional
publisher and deployment requirements described in
[publication readiness](plugin-publication-readiness.md).
