# Multiple Backup Source Locations Rework Spec

## Context

BOR-15 is in Rework because the previous implementation did not make the new
source directory modal rich enough for the main workflow: selecting source paths
from multiple source machines. The current UI and API still model backup input
as one `source_type`, one optional `source_ssh_connection_id`, and one shared
`source_directories` list. That cannot represent local paths plus SSH server A
plus SSH server B in one backup configuration.

The rework starts from `origin/main` and treats source selection as grouped
source locations. A source location is one source context plus its own paths:
local storage on the Borg UI host, or one SSH connection. The existing legacy
fields remain supported and are mirrored for old clients.

## UX Direction

Use the existing Borg UI operational UI language:

- compact MUI surfaces, outlined panels, chips, and restrained helper text;
- icons for source type and actions;
- explicit labels for form controls;
- visible keyboard focus and no placeholder-only labels;
- no heavy left accent borders or decorative landing-page treatment.

The source directory modal should let users add and review groups without
leaving the modal. Each group shows its source context, paths, and actions to
browse/add/remove paths.

## Data Contract

Introduce a `source_locations` JSON array on repositories and backup plans.
Each item has this shape:

```json
{
  "source_type": "local",
  "source_ssh_connection_id": null,
  "paths": ["/srv/app"]
}
```

For SSH sources:

```json
{
  "source_type": "remote",
  "source_ssh_connection_id": 12,
  "paths": ["/home/app/data"]
}
```

Compatibility rules:

- If `source_locations` is missing, derive one location from
  `source_type`, `source_ssh_connection_id`, and `source_directories`.
- When saving `source_locations`, also mirror legacy fields:
  - one local location -> `source_type: local`, no source SSH id;
  - one remote location -> `source_type: remote`, source SSH id set;
  - multiple or mixed locations -> `source_type: mixed`,
    `source_ssh_connection_id: null`, and flattened `source_directories`.
- Existing legacy API clients can keep sending `source_directories`.

## Runtime Behavior

Backup execution resolves grouped source locations into the same path list the
existing backup service already understands. Local paths are passed through.
Remote paths are converted to SSH URLs using each location's SSH connection and
then mounted through the existing SSHFS path preparation flow. This avoids a new
backup execution path and keeps SSHFS grouping by connection intact.

Scripts receive both the legacy flattened `BORG_UI_SOURCE_DIRECTORIES` and a new
`BORG_UI_SOURCE_LOCATIONS` JSON environment variable.

## Frontend Behavior

The backup-plan source chooser keeps database discovery intact. The Files and
folders route is replaced with a grouped picker:

1. Existing selected groups appear first.
2. Users choose a source context: local or any available SSH connection.
3. Users add paths manually or browse the currently selected context.
4. Adding paths appends to the matching group instead of replacing previous
   groups.
5. Users can remove paths or entire source groups.
6. The summary and review views display grouped sources instead of one flat
   path list when multiple groups exist.

Repository wizard legacy source settings use the same grouped input so editing
older repositories still works, while new submissions can send grouped sources.

## Acceptance Criteria

- Users can configure local paths and paths from multiple SSH connections in
  the same backup plan.
- Users can browse paths for each source context from the source directory
  modal without losing previous selections.
- Repository legacy source settings can persist grouped source locations when
  those settings are shown.
- Existing single-source payloads still create, update, serialize, and execute.
- Backup runtime uses the existing SSHFS mount preparation and supports more
  than one remote source connection in one backup job.
- Required backend, frontend, and runtime validations pass before review.

## Non-Goals

- Do not change repository storage destination behavior.
- Do not implement container source scanning.
- Do not change database discovery semantics beyond preserving its source
  selection compatibility.
