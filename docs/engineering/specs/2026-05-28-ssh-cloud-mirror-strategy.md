# SSH Cloud Mirror Strategy Spec

## Problem

BOR-67 moved rclone storage from a primary repository location into an optional cloud mirror. Local-primary repositories can already mirror by syncing the server-visible repository path to an rclone remote, but SSH-primary repositories are still blocked because the server has no trusted local source path to sync. Asking the client to provide a cache or staging path would put a storage trust boundary in the UI/API payload.

## Desired Outcome

SSH-primary repositories that use a Borg UI-managed SSH connection can opt into cloud mirror. The server owns the transfer path by mounting the SSH repository with the existing SSHFS mount service for the duration of each rclone sync, then syncing that mounted repository directory to the configured rclone remote. The API never accepts a client-provided cache or staging path for this flow.

## Strategy

The SSH mirror strategy is mounted storage, not streamed transfer and not a durable client-selected cache:

- The repository keeps its SSH primary location and stored `connection_id`.
- Mirror metadata remains a `RepositoryStorage` row with `backend="rclone"`.
- SSH mirror rows use `sync_direction="sshfs_mount_to_remote"` and do not persist a client cache/staging path.
- On sync, the server mounts the repository path through the existing SSHFS mount service using the stored SSH connection, runs `rclone sync <server-owned-mount> <remote:path>`, and unmounts in a `finally` block.
- If SSHFS mount or rclone sync fails, the repository remains unchanged and the mirror row records `sync_status="failed"` plus `last_sync_error`.
- Managed-agent-primary repositories remain ineligible until a separate managed-agent mirror strategy exists.

## Backend Behavior

- `rclone_cache_path` remains rejected on create, import, and update.
- Direct rclone repositories continue to derive their server cache under `RCLONE_CACHE_ROOT`.
- Local-primary cloud mirrors continue to sync the primary server path directly.
- SSH-primary cloud mirrors require a stored `connection_id`; legacy SSH-looking repositories without a managed connection are rejected because the server lacks credentials and a path authority for SSHFS.
- Remote path preflight still validates the rclone target before repository or mirror mutation.
- Enabling or updating a mirror rolls back validation/preflight failures without mutating the existing mirror row.

## UI Behavior

- The Cloud Mirror step is eligible for local-primary and SSH-primary repositories on the Borg UI server executor.
- Managed-agent repositories show an ineligible message that names the unsupported primary.
- SSH mirror route copy states that Borg UI mounts the SSH repository on the server before rclone sync.
- The UI continues to omit any cache/staging path input.
- Repository cards expose Enable cloud mirror for eligible local and SSH repositories without an existing mirror.

## Acceptance Criteria

- SSH-primary repositories can opt into cloud mirror through a server-owned SSHFS mount strategy.
- The strategy is documented as mounted storage.
- The UI communicates local/SSH eligibility, managed-agent ineligibility, and SSH route behavior.
- The backend rejects all client-provided cache/staging paths.
- Tests cover validation, sync failure handling, and rollback behavior.

## Validation

- Backend targeted tests cover SSH mirror validation, SSHFS sync source selection, first-sync failure persistence, and update rollback.
- Frontend targeted tests cover SSH eligibility, managed-agent failure messaging, SSH payload submission, and repository card action eligibility.
- Required backend and frontend lint/build gates run before handoff.
