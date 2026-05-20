# BOR-42 Agent-Aware Backup Plans Spec

## Goal

Make repository ownership and Backup Plan routing explicit for Borg UI server,
SSH, and managed-agent endpoints. Managed-agent repositories are agent-local
only: the central Borg UI instance orchestrates them, but Borg and backup data
stay on the owning agent.

## Current Signal

- `normalize_source_locations()` accepts only `local` and `remote` source
  locations. Passing `source_type: "agent"` currently normalizes to `local`,
  losing the selected agent endpoint.
- `TestRepositoriesCreate.test_create_agent_repository_preserves_ssh_target_axis`
  currently proves the wrong behavior for this ticket: an agent-owned repository
  with `connection_id` is accepted and stored as an SSH repository target.
- Backup Plan execution still treats plan sources as server/SSH sources and
  lacks a central route planner that can reject unsupported agent topologies
  before save or run.

## Product Rules

- Agent-owned repository means the repository path exists on the selected
  `AgentMachine`.
- Agent-owned repositories cannot use SSH repository targets or
  `connection_id`.
- All repository operations for agent-owned repositories run on the owning
  agent.
- Backup Plan source paths for an agent-owned repository must be on the same
  agent.
- Borg UI server is the control plane only for agent-owned repositories.

## Supported Routes

- Server source -> server local repository: `server_direct`.
- Server source -> server SSH repository: `server_direct_borg_ssh`.
- SSH source -> server local repository: `server_sshfs_pull`.
- SSH source -> server SSH repository on same SSH connection: `remote_direct`.
- SSH source -> server SSH repository on another SSH connection:
  `server_sshfs_pull_then_borg_ssh`.
- Agent source -> same agent-owned local repository: `agent_direct`.

## Unsupported Routes

- Agent-owned repository with an SSH target.
- Server source -> agent-owned repository.
- SSH source -> agent-owned repository.
- Agent source -> server-owned repository.
- Agent source -> different agent-owned repository.
- Mixed source groups that combine agent sources with server or SSH sources.

## Backend Design

- Extend source location normalization and decoding to preserve
  `agent_machine_id` for `source_type: "agent"` while keeping flattened
  `source_directories` for existing consumers.
- Add a route planner service that accepts a repository and normalized source
  locations, then returns a structured route result with support status,
  strategy, executor, agent id, reason key, and display params.
- Use the route planner during Backup Plan create/update and execution so
  unsupported topology errors are raised before Borg starts.
- Queue `backup.create` agent jobs for `agent_direct` and pass only same-agent
  local source paths.
- Add structured agent filesystem browse jobs and a server endpoint that queues
  and waits for those jobs.
- Route agent-owned repository maintenance/read operations through structured
  agent job kinds instead of local Borg commands.

## Frontend Design

- Repository wizard ownership uses an inline segmented choice consistent with
  the Borg v1/v2 switch style. When managed-agent ownership is selected, SSH
  repository location is unavailable and submitted payloads keep
  `connection_id: null`.
- Backup Plan source selection offers Borg UI server, SSH, and Managed agent
  endpoints. A single selected agent-owned repository defaults the source
  endpoint to that same agent.
- Source groups display endpoint labels for Borg UI server, SSH
  `user@host`, and Agent hostname.
- Review shows per-repository route preview and blocks save with specific
  unsupported-route messages.
- UI decisions follow `ui-ux-pro-max` guidance for Borg UI: flat, dense,
  accessible SaaS dashboard controls; icons from the existing icon set; stable
  hover/focus states; no heavy left accent borders.

## Acceptance

- Agent-owned repositories are always agent-local paths.
- Agent-owned repositories cannot be SSH repository targets.
- Backup Plans can choose Borg UI server, SSH, or managed-agent sources.
- Agent filesystem browsing works from the Backup Plan source picker.
- Backup Plan review clearly shows execution route per repository.
- Unsupported topologies are blocked before save and before run.
- Agent-owned repository operations never execute Borg on the Borg UI server.
- Existing server and SSH Backup Plan behavior remains intact.
- Repository wizard and Backup Plan stories cover supported and unsupported
  states, with updated Storybook snapshots.
