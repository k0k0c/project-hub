# Local installation and data-preservation checklist

This is developer guidance for changing a local Hub installation. Keep the program directory, Hub data home and managed source workspaces separate. A program may track its own development as an ordinary Hub project; its tasks, reports and settings belong to the external data home.

## Preserve the current installation

1. Read `/api/health` and record the active paths and runtime version in the installation's administration records.
2. Create a whole-data-home backup through **Projects → Backups**. Download the ZIP and retain its SHA-256 separately.
3. Restore to a new inactive folder. Verify project identifiers, journals, database integrity, documents, artifacts and owned instructions. See [the archive format](backup-format.md) and [backup workflow](backups.md).
4. Run migrations and development checks on separate copies. Keep one active writer for the current data home.

The coordinated snapshot captures committed SQLite WAL data. Pending journal writes and task transfers retain their recovery records.

## Program and project data

Persistent databases, configuration, instructions and runtime logs stay outside the Hub program/source directory. A managed code workspace is a separate optional input for source and Git features. Never infer it from the data-home path.

Development tests, caches and builds may use ignored service directories in the checkout. Exclude them and live project data from Git and the distribution's explicit input list.

Before moving historical development documents out of a public checkout, capture immutable snapshots and register evidence aliases. Verify the original bytes. Rewrite ordinary Markdown links separately: aliases preserve evidence reads only.

## Switch and verify

Stop the previous writer before activating a restored data home. Confirm the new runtime paths through health and check project history and representative evidence links. Verify the actual client connection and automatic update recovery. Synthetic fixtures alone do not establish live client integration.

Keep a compatible previous runtime and verified backup for rollback. Preserve writes made after the switch before reverting data. Preserve project IDs and history, and leave unrelated client configuration intact.
