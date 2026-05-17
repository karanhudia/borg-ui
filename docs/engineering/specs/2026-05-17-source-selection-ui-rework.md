# Source Selection UI Rework Spec

## Context

BOR-17 adds automatic database source discovery to backup-plan creation. The
previous attempt introduced the right concept but needs a full UI reset before
review: the chooser was too large, path/manual choices duplicated each other,
script previews did not use the existing code UI, long existing-script labels
were clipped, and the modal contained too many alert surfaces.

This rework starts from `origin/main` and treats source setup as one compact
backup-plan source chooser. Database discovery is one source type in that
chooser, and container scanning stays present as a disabled/planned type so the
model can grow later.

## Research

- PostgreSQL official documentation recommends `pg_dump` for logical database
  backups, with custom-format archives suitable for `pg_restore`:
  https://www.postgresql.org/docs/17/app-pgdump.html
- MySQL official documentation identifies `mysqldump` as the backup program and
  documents `--single-transaction` for consistent InnoDB dumps:
  https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html
- MongoDB official database-tools documentation uses `mongodump` for database
  dumps:
  https://www.mongodb.com/docs/database-tools/mongodump/index.html
- Redis official persistence documentation says RDB files are backup-friendly
  because completed RDB files are not modified while Redis is running:
  https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/

## UX Direction

Use the existing Borg UI MUI language: outlined cards, small chips, concise
helper text, visible focus states, and compact spacing. The `ui-ux-pro-max`
design-system search for Borg UI points toward a data-dense dashboard style:
high information density without clutter, tooltips for secondary guidance, and
flat, accessible surfaces. The modal should read as an operational tool, not a
marketing or onboarding panel.

## User Flow

1. In backup-plan creation, the source step shows plan name/description and a
   compact source setup summary with a `Choose source` action.
2. `Choose source` opens a responsive dialog. On mobile it uses the existing
   `ResponsiveDialog` full-screen/bottom-sheet-like behavior.
3. The first dialog view lists source types:
   - Files and folders: one route for local/remote path entry and browsing.
   - Database: enabled scan/template flow.
   - Docker containers: visible but disabled/planned.
4. Selecting Files and folders shows the existing location/SSH/path controls in
   one place. There is no separate manual-path card with identical behavior.
5. Selecting Database shows detected databases when available and fallback
   templates when no local database is detected.
6. Choosing a database/template shows a compact details view:
   source paths, database metadata chips, non-blocking notes, and editable
   pre/post script drafts using `CodeEditor`.
7. Script handling is explicit:
   - Create new pre/post scripts with editable names.
   - Reuse existing scripts using selectors that handle long labels.
   - Skip assigning scripts if the operator wants to configure them later.
8. Applying the database source updates source directories and selected/created
   script ids in the backup-plan wizard state.

## Backend Contract

Add an authenticated source-discovery route under `/api/source-discovery`:

- `GET /api/source-discovery/databases`
- Response includes `source_types`, `detections`, and `templates`.
- Supported templates in this scope: PostgreSQL, MySQL/MariaDB, MongoDB, Redis.
- Detection is conservative and local-only. It may inspect well-known data
  directories and the local PATH for client commands, but it must not connect to
  databases or require credentials.
- Each database item includes a generated source directory list plus script
  drafts:
  - `pre_backup`: prepare the logical dump or snapshot output in a stable path.
  - `post_backup`: remove transient dump files after Borg has captured them.
- Scripts must be editable in the frontend and must avoid destructive commands.

## Frontend Boundaries

- Keep the existing `WizardStepDataSource` path controls reusable.
- Add a focused source-selection component under the backup-plan wizard area.
- Add a small API wrapper for source discovery.
- Use `CodeEditor` for editable script drafts.
- Improve `ScriptSelectorSection` rendering so long selected script names do
  not lose useful content.
- Keep backup-plan payload compatibility: final payload still uses existing
  `source_type`, `source_ssh_connection_id`, `source_directories`,
  `pre_backup_script_id`, and `post_backup_script_id`.

## Non-Goals

- Do not implement Docker/container scanning yet.
- Do not perform live database authentication or credential storage.
- Do not change backup execution semantics.
- Do not add visual screenshots or generated assets.

## Acceptance Criteria

- Source setup presents a compact dedicated chooser on desktop and responsive
  full-screen/bottom-sheet-like flow on mobile.
- There is one path/manual files-and-folders route.
- Database discovery returns supported templates and conservative local
  detections.
- Selecting a database generates editable safe stop-backup-start script drafts.
- Script drafts are displayed/edited with the shared code editor surface.
- Existing-script reuse supports long script names/summary lines without
  truncating the useful content.
- Non-blocking warnings are reduced to helper text, metadata, chips, or
  tooltips; only blocking states use alerts.
- Existing path-based setup remains compatible.
