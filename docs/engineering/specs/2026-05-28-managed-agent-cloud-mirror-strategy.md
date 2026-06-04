# Managed-Agent Cloud Mirror Strategy Spec

## Problem

Local-primary repositories can mirror directly from the Borg UI server path, and SSH-primary repositories can mirror through a server-owned SSHFS mount. Managed-agent-primary repositories are still not eligible for rclone cloud mirrors because the server cannot see the agent-local repository path. Accepting a client-provided cache, staging, or transfer path would move storage ownership into the API payload and make repository creation responsible for trusting arbitrary paths.

## Desired Outcome

Managed-agent-primary repositories can opt into cloud mirroring without a client-supplied cache path. Borg UI owns the mirror metadata and rclone target, while the selected managed agent owns the local repository source and any temporary rclone execution files needed for the transfer. Failed mirror validation or first sync must not remove or rewrite the repository record.

## Strategy

Use an agent-executed rclone sync job rather than a server cache:

- The repository remains agent-primary with `executor_type="agent"`, `execution_target="agent"`, and its existing `agent_machine_id`.
- Mirror metadata remains a `RepositoryStorage` row with `backend="rclone"`.
- Managed-agent mirror rows use `sync_direction="agent_to_remote"` and do not persist a cache or staging path.
- Borg UI validates the selected agent is queueable and advertises the `repository.rclone_sync` capability before creating or enabling the mirror.
- Borg UI validates the rclone remote, relative target path, sync policy, and extra flags before mutating mirror metadata.
- On sync, Borg UI queues a `repository.rclone_sync` job for the repository's managed agent and passes the agent-local repository path, rclone remote name, relative target path, sync policy context, extra flags, and server-managed remote config values.
- The agent writes any rclone config needed for this job to an agent-created temporary file, runs `rclone sync <repository path> <remote:path>`, streams logs/progress through the existing agent job API, and removes the temp config file in a `finally` block.
- Borg UI records `sync_status="current"` on success, or `sync_status="failed"` with `last_sync_error` on failure. The repository row and `path` stay unchanged.

## Backend Behavior

- `rclone_cache_path` remains rejected for create, import, and update.
- Managed-agent mirrors require a valid `agent_machine_id`.
- Disabled, revoked, deleted, or missing agents are rejected before mirror metadata is created.
- Agents missing `repository.rclone_sync` are rejected before mirror metadata is created.
- Direct rclone repositories remain server-owned cache repositories and are not converted into agent mirrors.
- Local mirrors keep `sync_direction="primary_to_remote"`.
- SSH mirrors keep `sync_direction="sshfs_mount_to_remote"`.
- Managed-agent mirrors keep `cache_path=NULL` and `sync_direction="agent_to_remote"`.
- Remote path preflight still runs before repository or mirror mutation.
- On agent sync failure after repository creation, the repository row remains and the mirror row remains with failed status.
- On mirror update validation/preflight failure, the existing mirror row is left unchanged.

## UI Behavior

- The Cloud Mirror step is eligible for local-primary, SSH-primary, and managed-agent-primary repositories when the backing transport is supported.
- Managed-agent copy explains that the selected agent syncs its local repository path to the configured rclone remote and that Borg UI does not ask for a cache path.
- Repository cards surface both the managed-agent status and the mirror sync status when a managed-agent repository has a mirror.
- Repository cards expose Enable cloud mirror for manageable managed-agent repositories without an existing mirror.
- UI controls continue to omit cache/staging path input.

## Acceptance Criteria

- Managed-agent repositories have a documented server/agent-owned cloud mirror strategy.
- Any staging or transfer path is created and owned by Symphony/Borg UI or the managed agent, not supplied by the client.
- Agent status and mirror sync status are surfaced in repository UI.
- Backend preserves original repository data when mirror enablement or first sync fails.
- Tests cover agent eligibility, validation, sync failure handling, and rollback behavior.

## Validation

- Backend targeted tests cover managed-agent mirror eligibility, cache path rejection, capability validation, first-sync failure persistence, and update rollback.
- Agent runtime tests cover the new `repository.rclone_sync` payload, temporary config ownership, command construction, success, and failure.
- Frontend targeted tests cover managed-agent eligibility, managed-agent route messaging, repository card action/status display, and payload shape.
- Storybook stories and snapshots cover managed-agent cloud mirror status.
- Required backend and frontend lint/build gates run before handoff.

## Notes

This follows BOR-67 and extends the local/SSH mirror pattern without adding client-owned cache path fields.
