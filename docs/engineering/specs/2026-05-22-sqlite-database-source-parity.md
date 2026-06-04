# SQLite Database Source Parity Spec

## Context

BOR-54 points at GitHub issue 112, where borgmatic users asked for database-backup parity covering PostgreSQL, MariaDB/MySQL, and SQLite without hand-writing every hook. Borg UI already has database source discovery, script draft generation, script parameters, secret handling, and UI branding for SQLite, but the backend source-discovery templates currently return only MongoDB, MySQL/MariaDB, PostgreSQL, and Redis.

## Scope

Add SQLite as a supported database source template in the existing backup-plan source discovery flow.

The feature should:

- Return a SQLite template from `/api/source-discovery/databases`.
- Detect SQLite database files during local and remote scans when the scanned path is a `.db`, `.sqlite`, or `.sqlite3` file.
- Generate editable pre/post script drafts that stage a consistent SQLite backup under `/var/tmp/borg-ui/database-dumps/sqlite` and clean it afterward.
- Use script parameters for the SQLite database path so users can reuse the generated script across repositories or plans.
- Keep the existing SourceSelectionDialog flow unchanged except for showing SQLite as another database tile.

## Out Of Scope

Automatic zfs/btrfs filesystem snapshot orchestration is a separate borgmatic parity item because it needs different source semantics, mount/snapshot lifecycle rules, and stronger host capability validation than database dump templates.

## Acceptance Criteria

- SQLite appears alongside existing database templates.
- Local scans detect an explicit SQLite file path.
- Remote scans detect an explicit SQLite file path from probe output.
- SQLite script drafts include `sqlite3`, `SQLITE_DATABASE_PATH`, and the SQLite dump staging directory.
- Existing database source tests continue to pass.
- SourceSelectionDialog Storybook coverage shows SQLite in the database template grid.

## Validation

- `DATA_DIR=/tmp/borg-ui-test .venv/bin/pytest tests/unit/test_source_discovery.py -q`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `cd frontend && npm run snapshots`
