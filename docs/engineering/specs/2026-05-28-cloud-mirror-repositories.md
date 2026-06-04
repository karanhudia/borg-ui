# Cloud Mirror Repositories Spec

## Context

BOR-66 added rclone remotes and rclone-backed repositories. BOR-67 changes the user-facing repository flow so cloud storage is no longer a primary repository location. A repository's primary location remains local, SSH, or managed-agent-backed, and rclone is an optional off-site mirror.

## Scope

- Add a Repository Wizard step after Location named Cloud Mirror.
- Keep the Location step focused on Borg UI Server, SSH Server, and Managed Agent.
- Allow users to enable a cloud mirror for eligible repositories, select an existing rclone remote, enter or browse a relative remote path, choose a sync policy, and add extra rclone flags.
- Do not show or accept a client-provided cache path in the mirror flow.
- Use the existing `repository_storage` rclone metadata as the cloud mirror record and preserve legacy direct-rclone API compatibility where it already exists.
- Treat local-primary repositories as eligible for actual mirror sync in this slice. SSH and managed-agent mirror strategies need server-owned staging/transfer design and are tracked separately:
  - BOR-71: SSH repository cloud mirror strategy.
  - BOR-72: Managed-agent repository cloud mirror strategy.
  - BOR-73: Scheduled cloud mirror jobs.
  - BOR-74: Direct Borg 2 `rclone:` repository support.
  - BOR-75: Direct `rclone mount` evaluation.

## UX

The wizard order becomes:

1. Basics
2. Location
3. Cloud Mirror
4. Security
5. Advanced
6. Review

The existing combined Basics/Location implementation may keep repository name in the Location component for now, but the visible step sequence must include Cloud Mirror immediately after primary Location.

The Cloud Mirror step is disabled by default. When enabled it shows:

- Rclone remote select populated from Cloud Storage remotes.
- Relative remote path text field with an inline folder icon button.
- Sync policy select.
- Extra rclone flags text field.

The folder picker browses the selected rclone remote and writes the chosen relative path back to the field. Paths chosen through the picker are marked verified so the backend can distinguish typed paths from explicitly browsed paths.

Existing repository cards continue showing mirror status when a mirror exists. Eligible local-primary repositories without a mirror expose an Enable cloud mirror edit action.

## Backend Behavior

- `cloud_mirror_enabled` is the explicit request flag for the mirror flow.
- Mirror metadata reuses `RepositoryStorage` with `backend="rclone"` and `cache_path` set server-side to the repository's actual primary local path.
- The backend rejects `rclone_cache_path` for create, import, and update.
- When enabling or updating a mirror, the backend validates:
  - the primary repository is eligible for this slice;
  - the remote exists;
  - the relative path is safe;
  - the sync policy is supported;
  - extra flags parse correctly;
  - non-empty remote targets are blocked unless the request marks the path as verified by browse.
- First sync failure must not mutate or delete the original repository record. The mirror row may remain with failed status so the UI can report the failure.
- Legacy `storage_backend: "rclone"` create/import behavior remains compatible for existing tests/API callers, but new UI does not expose it as a primary location.

## Review And Status

The Review step shows primary location/path and, when enabled, the cloud mirror target and sync policy. Repository card status uses existing rclone status states: pending, syncing, hydrating, current, and failed.

## Validation

- Backend tests cover mirror enablement, non-empty path preflight, cache path rejection, and rollback/preservation on first sync failure.
- Frontend tests cover wizard step order, disabled-by-default mirror state, folder-picker path selection, create/edit payload shape, review summary, and repository card action/status states.
- Storybook stories and snapshots cover Cloud Mirror disabled/enabled and repository card mirror action/status.
- Runtime walkthrough uses a local rclone test remote when available.
