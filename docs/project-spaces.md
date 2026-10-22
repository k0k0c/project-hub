# Projects and code workspaces

A Hub project stores tasks, history, documentation, architecture descriptions and settings. It has its own name and permanent identifier. A local code folder is an optional connection for features that read source files or Git history.

## Manage projects

Open **Projects → Projects** and choose **Add project** to enter its name. You may also provide an existing local code folder using its absolute path. A project without a code folder can still contain tasks, results and documents.

Use **Configure** on a project's card to edit its name and connect one or more code folders. Agents and model connections are configured globally in **Settings → Agents and connections**, including before any project exists. Open the overview directly from the card. Its action menu contains archive and delete actions. Archiving removes it from the ordinary project selector. Deleting also removes it from that selector; its card remains in **Deleted projects**, where you can restore it. These actions retain the project's identifier and stored history. They do not delete or rename its code folder.

Each edit uses the revision shown when editing began. If another client changes the project first, refresh the card and review the new value before retrying. When a request loses its response, **Retry last change** repeats the same operation identifier. Do not submit a different operation until that result is known.

Backups cover the whole Hub data home, including all projects and shared records. See [the backup workflow](backups.md). A project's archive state and a downloadable backup are separate things.

## Features that need code

Source previews, Git operations, source scans and local language servers need a configured, accessible code folder. Without one, Hub reports that the workspace is required. It never treats the data-home directory or server's current directory as a project's source folder.

Completing a task without code still records its result. If automatic Git checkpoints are enabled, the completion records that no code workspace is available; it does not invent a commit or prevent completion.

## Optional version control

Open **Settings → General → Version control** to see the selected project's code
folder, detected Git repository and Git client availability. These are current
runtime details, separate from saved project preferences. Refresh the details
after installing Git or moving a repository. Hub currently implements Git only;
a folder managed with another system can still be used as an ordinary code folder.

Tasks, stages, documents and project history work without a repository or Git
client. Source scans use the files themselves to detect changes. A Git revision,
when available, is additional provenance for a scan.

Automatic commits are off by default. When enabled, they apply only to an
available Git repository and verified changes reserved for the work. Git trust,
file scope, existing edits and index checks still apply. A Git error does not
undo a completed task. Saved preferences remain intact while Git is unavailable.

Task and stage pages show commit links only when an actual commit exists. Open
**Git** for checkpoint diagnostics, retries and reconciliation of existing
commits. An empty or skipped checkpoint is not displayed as a task result.

## Describe and edit architecture

Open **Architecture and code** and select **Project overview** in the navigator. Right-click it, or use the actions at the bottom of its inspector, to describe the project, describe its main subsystems or add a subsystem manually. A keyboard context menu opens with **Shift+F10** or the context menu key.

Select a subsystem to edit its name, parent, short description and code boundaries, add a child subsystem, request an updated description from an agent or remove an empty subsystem. These actions appear in its context menu and at the bottom of the inspector. Editing and confirmation use separate windows. Renaming preserves the subsystem's identifier and history; removal requires reassigning its children and references first.

An editing window preserves its draft during live updates. Closing the window does not submit changes. If a save loses its response, reopen **Retry save** and retry the same pending operation before making another change.

## Developer reference

Independent project management requires registry schema 2. Existing schema 1 homes remain readable without automatic migration. Until a copied home is explicitly upgraded, its management forms stay disabled. Opening an existing home must not silently replace its schema.

`ProjectRegistry.upgrade(confirmed=True)` is an administrative operation for an inactive copied home. Each SQLite migration is atomic. A persistent pending marker protects a partially upgraded copy from activation or project edits; retry the upgrade on that copy to finish it. Keep the original home and a verified backup until acceptance is complete.

`GET /api/v1/projects` returns `schemaVersion`, `projects` and `discovery`. Use `includeDeleted=true` to include recoverable deleted rows. `POST /api/v1/projects` accepts one of:

- `{action:"create", name, roots:[], requestId}`
- `{action:"update", project, patch:{name|archived|deleted}, expected, requestId}`

`expected` is the integer project revision, distinct from task and settings revisions. `requestId` is a unique 32-character hexadecimal identifier. Retry an uncertain operation with exactly the same identifier and payload. Reusing it for different contents is rejected.

Projects managed by Hub retain their name and lifecycle flags when an external client catalog changes. Client discovery remains a compatibility adapter, not the owner of an independently managed project.

`GET /api/version-control?project=<id>` reads optional source-control capability
without changing the settings revision. `provider` is `git` when a Git marker is
found, otherwise null. `status` distinguishes an available repository, missing
repository, missing client, inaccessible repository and missing/inaccessible
workspace. Only the explicit runtime read invokes Git to verify the repository;
ordinary settings reads remain filesystem-independent. The packaged
`version_control.py` dispatches optional source snapshots, revision provenance
and external-worktree identity to the Git adapter. The existing durable
`git_snapshot` and checkpoint formats remain readable.
