# Database Source Preservation and Capture Mode

## Status

Draft, approved design direction from the May 31, 2026 product discussion.

## Context

The current local work adds database scanning and template-backed script drafts
to the backup-plan source chooser, but the selected database flow is still
behaving like a terminal action. `applyDatabase()` updates the wizard and closes
the source dialog immediately. It also hardcodes the applied source as local,
which loses the machine where the database was discovered when the scan target
is a remote SSH host.

The desired model is closer to the Files tab: a database selection is added to
the Database tab, the dialog remains open, the tab shows that something is
selected, and reopening the dialog restores the same source model rather than
collapsing everything into plain file paths.

## Design Inputs

- `impeccable`: Borg UI is a product UI. Keep the dialog operational, compact,
  MUI-native, and consistent with `ResponsiveDialog`, shared selectors, balanced
  borders, chips, and factual copy.
- `ui-ux-pro-max`: Applied guidance on visible active states, accessible errors,
  sufficient contrast, and not using color alone. The generic design-system
  output suggested a funnel/dark-mode direction, but Borg UI's existing
  `PRODUCT.md` and `DESIGN.md` take precedence for this established product.

## Goals

- Selecting a database must not close the source selection dialog.
- `Add database` must queue the database in the Database tab, mark the Database
  tab as selected, and return the user to the database scan/list state.
- The Files tab and Database tab must each show selections in their own relevant
  locations.
- Reopening the source chooser must restore the same selected database, capture
  mode, scan target, live source path, dump path, final Borg backup path, and
  script choice.
- The default database capture mode is a generated dump or snapshot into a
  staging directory on the same machine where the database was discovered.
- An advanced option lets the user back up the original database location
  instead of a dump, with an explicit consistency warning.
- Database-generated or user-selected scripts run as backup-plan pre/post hooks.
- For remote SSH database sources, database hook work runs on that SSH source
  machine so the dump path and final backup path are on the same machine as the
  database.
- Fallback database templates are hidden behind a "Show templates" action unless
  no detections exist.

## Non-Goals

- Container database discovery.
- Live database credential management.
- Automatic parsing of database config files to infer database names, users, or
  socket paths.
- Changing repository-level scripts. This work is about backup-plan scripts.

## Core Decisions

### Capture Mode

The default is `dump`:

- Borg UI generates or reuses plan-level pre/post scripts.
- The pre-backup script writes a logical dump or safe snapshot to a staging
  directory.
- Borg backs up the staging directory.
- The post-backup script cleans the staging directory after all repository
  backup jobs complete.

Advanced mode is `original`:

- Borg backs up the detected original database path.
- Generated dump scripts are not selected by default.
- The UI keeps the script section available for users who want existing
  stop/start or quiesce hooks.
- The UI warns that hot database files may be inconsistent without a snapshot,
  stop/start hook, or engine-specific safe backup method.

### Source Machine

The selected database source location always uses the scan target:

- Local scan target: `source_type = "local"`, paths are local to the Borg UI
  server.
- Remote SSH scan target: `source_type = "remote"`,
  `source_ssh_connection_id = <scan target>`, paths are on that SSH machine.

The final Borg backup path is the path Borg will read on that same machine. In
`dump` mode this is the dump staging directory. In `original` mode this is the
detected source path.

### Script Execution

Database plan scripts are still plan-level pre/post scripts, but their execution
target becomes source-aware:

- Local database source: execute through the existing local script runner.
- Remote SSH database source: execute the script on the selected SSH source host
  using the same connection and key material used by remote scans and backups.

The script environment includes the existing plan variables and these database
variables:

| Variable | Value |
| --- | --- |
| `BORG_UI_DB_TEMPLATE_ID` | `postgresql`, `mysql`, `mongodb`, `redis`, or `sqlite` |
| `BORG_UI_DB_ENGINE` | Display engine name |
| `BORG_UI_DB_CAPTURE_MODE` | `dump` or `original` |
| `BORG_UI_DB_SOURCE_PATH` | Detected live path when available |
| `BORG_UI_DB_DUMP_DIR` | Selected dump directory in `dump` mode |
| `BORG_UI_DB_BACKUP_PATHS` | JSON array of final paths Borg will read |

The generated scripts should use these variables instead of baking in UI state.
For example, the PostgreSQL draft writes to `${BORG_UI_DB_DUMP_DIR}` and leaves
database naming to `POSTGRES_DB` with a default.

When multiple generated database templates are queued in one source chooser
session, Borg UI creates one generated pre-backup script and one generated
post-backup script. Each script contains one block per queued database; each
block exports that database's `BORG_UI_DB_*` values before running the template
commands.

## Data Contract

Add a database metadata object to the relevant source location. The expected
database metadata fields must be preserved by frontend and backend
normalization; unknown fields inside the database object may be dropped.

```ts
export type DatabaseCaptureMode = 'dump' | 'original'

export interface SourceDatabaseSelection {
  template_id: 'postgresql' | 'mysql' | 'mongodb' | 'redis' | 'sqlite'
  engine: string
  display_name: string
  backup_strategy: string
  detected_source_path: string | null
  detection_label: string | null
  capture_mode: DatabaseCaptureMode
  dump_path: string | null
  backup_paths: string[]
  script_execution_target: 'source' | 'server'
}

export interface SourceLocation {
  source_type: 'local' | 'remote' | 'agent'
  source_ssh_connection_id?: number | null
  agent_machine_id?: number | null
  paths: string[]
  snapshot?: SourceSnapshotConfig
  database?: SourceDatabaseSelection
}
```

In `dump` mode:

```json
{
  "source_type": "remote",
  "source_ssh_connection_id": 11,
  "paths": ["/var/tmp/borg-ui/database-dumps/postgresql"],
  "database": {
    "template_id": "postgresql",
    "engine": "PostgreSQL",
    "display_name": "PostgreSQL database",
    "backup_strategy": "logical_dump",
    "detected_source_path": "/var/lib/postgresql",
    "detection_label": "backup-a@server-a.example",
    "capture_mode": "dump",
    "dump_path": "/var/tmp/borg-ui/database-dumps/postgresql",
    "backup_paths": ["/var/tmp/borg-ui/database-dumps/postgresql"],
    "script_execution_target": "source"
  }
}
```

In `original` mode, `paths` and `database.backup_paths` point at the detected
source path, and `database.dump_path` is `null`.

Keep `backup_plans.database_template_id` as a compatibility/search field, but
do not rely on it as the only source of truth for restoring the dialog state.

## UI Specification

### Database List

- Scan target and scan paths stay at the top.
- Detected databases render first.
- Templates render only after the user opens `Show templates`, except when
  there are no detections and no selected database.
- The Database tab count reflects the queued database selections.
- The Files tab count reflects queued file paths only.

### Database Detail

The detail view contains:

- Database title and chips: engine, strategy, detected/template.
- Source panel with source machine, live database path, dump path, and final
  Borg backup path.
- Capture mode control:
  - `Dump to staging path` recommended.
  - `Back up original path` advanced.
- Dump path field in dump mode.
- Script mode controls:
  - Create generated pre/post scripts.
  - Reuse existing scripts.
  - Skip scripts.
- `Add database` action. This does not close the dialog.

### Reopen Behavior

When the user reopens the source chooser:

- If a database metadata object exists, open on the Database tab.
- Restore the selected database detail state from source metadata.
- Restore the selected scan target from the source location.
- Keep templates collapsed unless the saved selection came from a template and
  no matching detection is available.

## Acceptance Criteria

- A detected PostgreSQL database selected from a remote SSH scan queues a remote
  source location whose `paths` are the remote dump path, not local paths.
- `Add database` keeps the source chooser open and marks the Database tab with a
  selected count.
- `Use these paths` is the final action that closes the chooser.
- Reopening the chooser after applying a database plan restores the Database tab
  and the selected database information.
- Switching from a database source to files clears database metadata and changes
  the summary back to Files and folders.
- Original-path mode stores the original detected path as the final backup path
  and shows a consistency warning.
- Generated scripts receive `BORG_UI_DB_*` variables.
- Remote database scripts execute on the remote source host.
- Fallback templates are collapsed behind `Show templates`.
- Storybook covers detected database selected, original-path advanced mode, and
  templates-collapsed states, with snapshots committed.
- `docs/usage-guide.md` and `docs/script-parameters.md` document the new user
  flow and injected variables.
