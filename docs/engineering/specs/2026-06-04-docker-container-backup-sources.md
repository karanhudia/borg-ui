# Docker Container Backup Sources

## Problem

The backup-plan source chooser exposes Files, Database, and Container as source kinds, but Container is disabled with a "Soon" badge. The backend source-discovery endpoint also reports Docker containers as planned and disabled. Users cannot create a backup plan that represents a Docker container backup from the source flow.

## Desired Outcome

The source chooser lets operators select a Docker container source with the same calm, compact Borg UI treatment used by files and database sources. Operators can scan the Borg UI server or an SSH source for Docker containers, inspect what `docker export` will include, and still enter a container manually when scanning is unavailable. A Docker source stages a container filesystem export into a Borg-readable path, stores typed container metadata in `source_locations`, and uses source-level scripts to prepare and clean that staged export during backup-plan execution.

## Scope

- Enable the Container source kind in `SourceSelectionDialog`.
- Add a Docker container source form that captures:
  - source machine: Borg UI server, SSH source, or managed agent when available;
  - container name or ID;
  - export staging path;
  - optional image/name note for reviewer context.
- Add Docker container scanning for Borg UI server and SSH sources, returning detected containers, export staging paths, and mount coverage details with opt-in mount selection.
- Generate source-level pre/post script assignments for Docker container exports, using the existing source script execution phase (`source-pre-backup` and `source-post-backup`).
- Preserve normalized container metadata through frontend payload building and backend `source_locations` normalization.
- Update source summaries, review labels, Storybook, tests, and locale strings for the new source state.

## Out Of Scope

- Volume graph introspection.
- Starting, stopping, pausing, or checkpointing containers.
- Docker socket installation or permission management beyond clear UI copy and generated script behavior.
- Managed-agent Docker container scanning. Managed-agent container sources remain manually entered in this server-side scan flow.

## Approach

The implementation should treat Docker as metadata on an existing source location rather than as a new `source_type`. Borg still reads from a local, remote, or agent execution target. The `container` block describes why that path exists and which source-level scripts populate it.

Example normalized source location:

```json
{
  "source_type": "local",
  "source_ssh_connection_id": null,
  "agent_machine_id": null,
  "paths": ["/var/tmp/borg-ui/container-exports/postgres"],
  "container": {
    "container_name": "postgres",
    "display_name": "postgres",
    "backup_mode": "export",
    "export_path": "/var/tmp/borg-ui/container-exports/postgres",
    "script_execution_target": "source",
    "pre_backup_script_id": 17,
    "post_backup_script_id": 18,
    "pre_backup_script_parameters": {
      "CONTAINER_EXPORT_FORMAT": "tar"
    },
    "post_backup_script_parameters": {
      "CLEAN_EXPORT": "yes"
    },
    "script_execution_order": 1
  }
}
```

`BORG_UI_CONTAINER_*` values are injected by the backend at script execution time and should not be modeled as user-provided script parameters. Container script parameters are only for user-configurable values such as export format, cleanup policy, or other script-specific knobs.

The generated pre-backup script should create the export directory, write `docker inspect` output, and export the container filesystem into `filesystem.tar`. The post-backup script should remove the staged export directory. Remote Docker sources run their scripts on the remote source when `script_execution_target` is `source`, matching remote database behavior.

## UX Notes

- The Container tab should look like the Files and Database tabs: same segmented pivot, full outline treatment, MUI controls, lucide icon, no heavy side borders.
- Copy must be operational and precise: "Docker container export", "Container name or ID", "Export staging path".
- The scan result should show that `docker export` captures the container filesystem and should list bind mounts or named volumes as not included by the export. Operators can select detected mount source paths from the Container tab, and Borg UI adds those paths as normal Files source locations in the same plan.
- Apply remains one commit action for queued source groups. The Container tab should queue the container source and return to the tab list, like Database queues sources before applying.

## Acceptance Criteria

- Container is selectable in the source-kind pivot and is no longer marked disabled/soon.
- Selecting Container, entering a name/ID, and applying creates a source location with a populated `container` metadata block.
- The Container tab can scan Docker containers on the Borg UI server and SSH sources and queue a detected container into the same source-location/script path as manual entry.
- Detected containers show the exact export staging path, visibly disclose that bind mounts and named volumes are not included by `docker export`, and let users select mount source paths to include as Files sources.
- Backend normalization preserves the `container` metadata and rejects invalid empty container/export path input.
- Source-level Docker scripts execute in backup-plan runs with container-specific environment variables.
- Source summaries and review surfaces identify Docker container sources distinctly from plain files.
- Storybook includes a Docker container source state.
- Required frontend/backend validation and local walkthrough evidence are recorded in the Linear workpad.

## Validation

- Red/green frontend tests:
  - `cd frontend && npm test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx -t "configures a Docker container source" --run`
  - `cd frontend && npm test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx -t "Docker|container|mount" --run`
  - `cd frontend && npm test -- src/pages/__tests__/BackupPlans.test.tsx -t "preserves Docker container source metadata" --run`
- Red/green backend tests:
  - `pytest tests/unit/test_source_discovery.py::TestSourceDiscovery::test_database_discovery_returns_extensible_source_types -q`
  - `pytest tests/unit/test_source_discovery.py -k "container_scan" -q`
  - `pytest tests/unit/test_api_backup_plans.py -k "container_source" -q`
- Required gates:
  - `cd frontend && npm run check:locales`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build`
  - `ruff check app tests`
  - `ruff format --check app tests`
- Runtime walkthrough:
  - Launch Borg UI locally, open backup plan creation, choose Sources, select Container, scan mocked Docker containers, verify included filesystem/excluded mount disclosure, select a detected mount path, queue the detected container, apply, and verify the source summary/review shows both the Docker source and selected Files mount path.

## Original Request

> In sources, we have files and database scanning for now while creating backup plans. We left one docker container disabled as "coming soon", so it's time to implement this. Basically, you can back up a whole container or something; that's the idea. Keep the same design language as the other two and use impeccable skill.
