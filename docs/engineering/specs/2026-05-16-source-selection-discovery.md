# Source Selection Discovery Spec

## Goal

Rework backup-plan source setup into a guided source-selection flow that supports normal file paths today, database discovery now, and future container discovery without making users start from raw path fields.

## Context

The current backup-plan source step asks for the plan name, description, local or remote source, source directories, and excludes inline. There is no source-type chooser, no database scan entry point, and no explicit script creation decision.

Reviewer feedback requires the rework attempt to do three things differently:

- Move source selection into its own modal or mobile bottom sheet.
- Treat databases as one source type among paths, files/folders, and future Docker/container scan.
- When generated scripts are needed, tell users scripts will be created and let them create named scripts or reuse existing scripts.

Practical database backup research supports database-specific flows instead of a generic "copy files" assumption:

- PostgreSQL documents `pg_dump` as creating consistent logical backups while the database is in use.
- MySQL documents `mysqldump` and `--single-transaction` for logical backups.
- MongoDB documents `mongodump` for database dumps.
- Redis documents RDB snapshots and notes that RDB files are copy-friendly while Redis is running.

Sources:

- https://www.postgresql.org/docs/17/app-pgdump.html
- https://dev.mysql.com/doc/refman/8.4/en/using-mysqldump.html
- https://www.mongodb.com/docs/database-tools/mongodump/index.html
- https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/

## Product Behavior

The source step keeps plan name and description visible, then shows a compact source summary and a primary "Choose source" action. The raw path and exclude controls remain available only after a path-like source is selected.

The source chooser is a `ResponsiveDialog`, so it is a centered modal on desktop and a bottom sheet on mobile. It has three stages:

1. Choose source type:
   - Files and folders, enabled, preserves existing local/remote path behavior.
   - Database, enabled, opens scan results and templates.
   - Docker containers, visible but disabled as "coming next".
   - Manual paths, enabled, jumps to existing path entry.
2. Configure database source:
   - Load detected databases from the backend scan endpoint.
   - Show template choices for supported database engines even when nothing is detected.
   - Selecting a database sets suggested source directories and displays the generated pre/post script drafts.
3. Choose script handling:
   - Create new plan scripts with editable names.
   - Reuse existing scripts from the loaded script library.
   - Skip script assignment for now, leaving script draft visible for manual copying.

For database sources, applying the selection updates the backup-plan state:

- `sourceType` stays `local` for this initial implementation.
- `sourceDirectories` are populated from the selected database target.
- `preBackupScriptId` and `postBackupScriptId` are populated when scripts are created or reused.
- Existing path-based behavior remains compatible with the payload that backup plans already submit.

## Backend Contract

Add `GET /api/source-discovery/databases`.

Response shape:

```json
{
  "source_types": [
    {
      "id": "paths",
      "label": "Files and folders",
      "description": "Choose files or folders from the Borg UI server or a remote client.",
      "enabled": true
    }
  ],
  "databases": [
    {
      "id": "postgresql-local",
      "engine": "postgresql",
      "engine_label": "PostgreSQL",
      "display_name": "PostgreSQL on this server",
      "status": "detected",
      "confidence": "high",
      "service_name": "postgresql",
      "source_directories": ["/var/lib/postgresql"],
      "warnings": ["Scripts may require sudo privileges to stop and start services."],
      "pre_backup_script": "...",
      "post_backup_script": "...",
      "script_name_base": "PostgreSQL stop-start backup",
      "documentation_url": "https://www.postgresql.org/docs/17/app-pgdump.html"
    }
  ],
  "templates": []
}
```

Detection stays conservative:

- Inspect common data directories and UNIX socket paths.
- Check common local ports with a short timeout.
- Do not require root access.
- Return templates for PostgreSQL, MySQL/MariaDB, MongoDB, and Redis so users can proceed when scan cannot confirm services from the Borg UI process environment.

Generated scripts are drafts. They use `systemctl` or `service` where available and include clear environment-variable overrides for service name. They are editable before creation.

## UI Design Notes

The implementation follows existing Borg UI patterns:

- MUI surfaces, subdued outlines, and `ResponsiveDialog` for desktop/mobile behavior.
- Lucide icons for source types and actions.
- No heavy left accent borders.
- Cards are used only for repeated choices, not nested inside another card.
- The source step remains dense and operational rather than a marketing-style hero.

## Error Handling

- If the scan endpoint fails, the chooser shows an alert and keeps database templates available once backend data can be fetched again.
- If script creation fails, keep the dialog open and surface the error toast. Do not apply a partially configured database source silently.
- If the user chooses "reuse existing scripts" without selecting required scripts, the apply action is disabled.

## Acceptance Criteria

- Source setup opens a dedicated source-selection modal on desktop and bottom-sheet-like flow on mobile.
- Source choices include files/folders, database scan, Docker/container scan placeholder, and manual path entry.
- Database scan shows detected databases and supported templates.
- Database selection can populate source directories and generated script drafts.
- Script handling explicitly supports creating named scripts, reusing existing scripts, or skipping assignment.
- Existing path-based local/remote source setup and backup-plan payload compatibility are preserved.
