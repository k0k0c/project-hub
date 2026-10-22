# Project Hub backup container, version 1.0

This is the portable contract for the whole Hub data home. The implementation
is `scripts/hub_backup.py`; its verification and restoration functions depend
only on Python's standard library. Live snapshot locks are supplied by the
current server adapter. The container does not depend on a Codex checkout.

## Layout and manifest

A backup is a ZIP with regular files, UTF-8 `manifest.json`, `home/` containing
the data-home tree, and optional `portable-instructions/` containing the owned
instruction directory. Directory entries are unnecessary and are rejected by
the current reader. The manifest itself is not listed in its file table.

Required manifest fields:

- `kind`: `project-hub-backup`.
- `formatVersion`: integer `major` and `minor`, currently `1` and `0`.
- `scope`: `all-projects`.
- `createdAt`: an ISO 8601 timestamp.
- `requiredFeatures`: reader capabilities needed for this payload. Version 1.0
  always requires `whole-data-home` and `sqlite-snapshot`; externally configured
  owned instructions additionally require `portable-instructions`. Preserved
  project-relative archive aliases additionally require `source-file-aliases`;
  these retain historical evidence without treating it as current source code.
- `storageSchemas`: actual schema versions. The reader supports registry and
  coordination versions `1` and `2`; the project journal remains version `1`.
  Coordination is listed only when that store exists. Version `2` allows
  independent projects and agents without a local code workspace. Opening a
  version `1` home does not implicitly upgrade it: upgrade an imported inactive
  copy explicitly before activating it.
- `projects`: sorted inventory with `id`, `name`, `tasks` (distinct task IDs in
  seed/history), and `journalEvents` for each registry project.
- `files`: exact map of payload-relative paths to integer byte `size` and
  lowercase hexadecimal `sha256`.

Writers also include `createdBy` with application/writer/runtime versions,
`excluded` describing omitted transient data, and `extensions` as a namespaced
object for optional metadata. Application release, container version and
storage schema versions are distinct compatibility dimensions.

## Evolution

An incompatible container change increments `major`; the reader rejects unknown
major versions. An additive compatible change increments `minor`. A newer
minor version is accepted when every required capability is understood and
the embedded storage schemas remain supported. A new mandatory semantic change
requires a new capability in `requiredFeatures`, even within the same major.

Unknown optional manifest fields and extension objects are preserved and ignored.
Additional opaque files can be carried below `home/`, with exact file-table
proofs. A future adapter requiring interpretation of new files must declare a
required capability. Unknown top-level payload areas are rejected by this reader.
Current restore performs no schema migration and never initializes a damaged
or missing registry. Later migrations must operate on a verified inactive copy.

## Snapshot contents

The snapshot preserves `registry.sqlite3` and optional
`coordination/coordination.sqlite3` through the SQLite backup API. It copies all
other authoritative and opaque data-home files, including project seeds,
journals, settings, knowledge blobs, artifact descriptor markers, history,
instruction metadata and durable delivery records. It excludes OS writer/edit
locks, Python bytecode, generated `language-servers` workspaces, and SQLite
sidecars for the databases already captured by the backup API.

The live adapter acquires the cross-process data-home writer barrier, every
project writer lock, the owned instruction editor lock and SQLite write
reservations. It checks ordinary source files before and after copying and
checks the complete file set. These locks cover supported Hub writers; direct
external edits are detected when their resulting changes intersect the snapshot.
ZIP compression and final verification run on the copied tree after the live
locks are released.

The top-level `runtime/` directory is transient server state and logs, and is
excluded. Durable project settings and installation-wide instructions live
outside that directory. New processes regenerate their own runtime state.

Configured owned instructions are copied to `portable-instructions/`, including
their owner marker. Restoration relocates them into the new data home and
rewrites only the copied `instructions/location.json`; the original client
profile is never modified. External source code, executables and foreign
client catalogs are deployment dependencies, rather than Hub-owned data.

## Validation and restoration

Before any destination is published, the reader checks ZIP members, supported
compression, bounded file/byte counts, exact manifest membership, per-file size
and digest, SQLite integrity and foreign keys, known storage versions, inventory
agreement, and instruction ownership when present. Paths are relative POSIX
names compatible with Windows: no traversal, absolute paths, links, reserved
device names, backslashes, duplicate or case-insensitive aliases.

The current caps are 2 GiB for the archive and expanded payload, 100 000 payload
files and 8 MiB for the manifest. Digest verification is streaming. Uploads use
512 KiB decoded chunks within 1 MiB JSON requests.

Restoration takes a new exclusive outer destination and publishes its verified
tree as `destination/data`; manifest metadata is retained alongside it.
`INCOMPLETE` remains if publication fails. Existing destinations are never
replaced. The API returns `active: false`, the actual data-home path and project
count. Switching a running installation requires a separate server lifecycle
operation with all SQLite handles closed.

## Web API

All routes require local Host access; POST also enforces same-origin access.
These are installation-wide routes and do not require a selected project.

- `GET /api/v1/backups`: available archives and restored inactive copies.
- `GET /api/v1/backups/download?id=ID`: streaming archive download.
- `POST /api/v1/backups`, `action=create`: create a snapshot.
- `action=upload-start`, `name`, `size`: reserve a bounded upload; return `id`
  and acknowledged `offset`.
- `action=upload-chunk`, `id`, `offset`, base64 `data`: append one chunk at the
  exact acknowledged offset and return the new offset.
- `action=upload-complete`, `id`: verify the complete archive and return its
  preview and `sha256`. Retry after success returns the same preview.
- `action=upload-abort`, `id`: cancel an unfinished/rejected upload and discard
  its partial file. A ready verified archive cannot be aborted.
- `action=restore-copy`, `id`, `expectedSha256`, `confirmed=true`: verify the
  selected archive digest again and restore an inactive copy. A retry after
  success returns the saved destination.

Archive IDs are server-generated; callers cannot supply filesystem destinations.
Archives and upload metadata live in the configured backup directory, defaulting
to the sibling `DATA_HOME-backups` directory. It cannot overlap the active data
folder, so subsequent snapshots do not recursively capture earlier backups.
The low-level restore API prepares an inactive copy. The application then uses
`POST /api/v1/storage`, `action=apply-import`, to publish selected projects into
the same active path. `mode=add` requires explicit per-project conflict choices;
`mode=replace-all` requires confirmation of project replacement/removal. Global
instructions/settings are imported only with `includeGlobals=true`. Current
credentials and launch configuration are protected in both modes.

`GET /api/v1/backups/status` exposes the common operation history, origin,
phase, progress and `writesPaused`. HTTP/MCP mutations are rejected while an
accepted project/backup operation is pending. Request IDs are idempotent; a lost
acknowledgment never implies success or automatically releases the barrier.
