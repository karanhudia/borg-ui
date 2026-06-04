# Btrfs and ZFS Snapshot Sources Spec

## Goal

Add Borg UI backup source support for btrfs and zfs filesystem snapshots so users can configure consistent filesystem snapshot backups without hand-writing create/delete hook scripts.

## Current Signal

`normalize_source_locations()` currently strips unknown metadata from source locations. A local source location with a `snapshot` object returns only `source_type`, endpoint ids, and `paths`, so there is no durable way to configure snapshot lifecycle behavior. The source selection UI also has no btrfs/zfs affordance today.

## Scope

- Support snapshot source metadata on local Borg UI server source locations.
- Validate snapshot metadata in the existing source-location normalization path.
- Prepare snapshots inside `BackupService.execute_backup()` before source-size calculation and before Borg command construction.
- Replace live source paths with snapshot staging paths for the backup command.
- Clean up snapshots and staging paths from `BackupService` cleanup paths after success, warning, failure, or cancellation where feasible.
- Add frontend controls to the existing backup-plan source picker for local source groups.
- Show host/tool requirements and disable snapshot controls for remote SSH and managed-agent source targets.
- Add Storybook coverage for the snapshot source flow.

## Out Of Scope

- Running btrfs/zfs snapshot commands on remote SSH sources.
- Running snapshot lifecycle on managed agents.
- Automatic discovery of zfs dataset names from arbitrary paths.
- Database snapshot parity. Database source parity is covered by BOR-54.

## Source Location Contract

Snapshot configuration is stored on a source location as an optional `snapshot` object:

```json
{
  "source_type": "local",
  "source_ssh_connection_id": null,
  "agent_machine_id": null,
  "paths": ["/srv/app"],
  "snapshot": {
    "provider": "btrfs",
    "staging_path": "/var/tmp/borg-ui/snapshots",
    "recursive": false
  }
}
```

For zfs:

```json
{
  "snapshot": {
    "provider": "zfs",
    "dataset": "tank/app",
    "mountpoint": "/srv/app",
    "recursive": false
  }
}
```

Rules:

- `provider` must be `btrfs` or `zfs`.
- Snapshot configuration is valid only on `source_type: "local"` locations.
- `paths` must be absolute and non-empty.
- `btrfs` uses `staging_path`, defaulting to `/var/tmp/borg-ui/snapshots`.
- `zfs` requires `dataset` and `mountpoint`; snapshot backup paths are derived from `<mountpoint>/.zfs/snapshot/<snapshot_name>/<relative path>`.
- Unknown snapshot keys are dropped during normalization so persisted data stays predictable.

## Runtime Lifecycle

Before Borg runs, `BackupService` prepares snapshot sources:

- btrfs creates a read-only snapshot per source path under a job-scoped staging root.
- zfs creates one snapshot per source location and maps each selected source path into the `.zfs/snapshot` view.
- The Borg source path list uses the generated staging paths, not live source paths.
- Cleanup runs in the service `finally` block and removes tracked snapshots/staging data after terminal outcomes and exceptions.
- Cleanup best effort is logged; cleanup failure must not mask the original backup result.

## UI Design

The existing backup-plan source dialog gets a compact local-only snapshot section using the current MUI outlined card style, not heavy left accent borders. The section appears near local path entry and selected local groups:

- A segmented/select control chooses `No snapshot`, `btrfs`, or `zfs`.
- btrfs shows staging-root guidance and optional staging path.
- zfs shows required dataset and mountpoint fields.
- Remote SSH and managed-agent selections show an informational disabled state explaining snapshot commands must run on the host where Borg UI executes.
- Selected groups display a small snapshot chip so reviewers can see the configured provider.

## Validation Plan

- Backend unit tests for snapshot metadata normalization and incompatible target validation.
- Backend unit tests for btrfs/zfs command template generation.
- Backend unit tests for source path replacement and cleanup after success/failure/cancellation-feasible paths.
- Frontend tests for local snapshot controls, payload persistence, and disabled remote/agent controls where local test patterns support it.
- Storybook story and screenshot snapshot for the snapshot source configuration flow.
- Required repo checks before handoff:
  - `ruff check app tests`
  - `ruff format --check app tests`
  - targeted `pytest`
  - `cd frontend && npm run check:locales`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build`
  - `cd frontend && npm run snapshots`

## Self-Review

- Acceptance coverage: btrfs/zfs configuration, staging source inclusion, cleanup, UI requirements/guardrails, backend tests, and Storybook are covered.
- Scope boundaries: remote SSH and managed-agent snapshot execution are explicitly out of scope and guarded.
- Ambiguity resolved: zfs requires explicit dataset and mountpoint instead of guessing host state.
