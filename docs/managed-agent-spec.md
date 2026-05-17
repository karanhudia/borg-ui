---
title: Managed Agent Spec
nav_order: 15
description: "Architecture and implementation contract for Borg UI managed agents"
---

# Managed Agent Spec

This document defines the implementation contract for Borg UI managed agents.

The goal is to let users manage backups on many machines from one Borg UI
instance without installing the full Borg UI Docker application on every
machine.

## Status

Draft for implementation.

Changes to this document should happen before or alongside code changes when
the implementation needs to deviate from the design.

## Goals

- Run a lightweight Borg UI agent on Linux, macOS, and eventually Windows
- Keep the central Borg UI instance as the control plane
- Let agents connect outbound to Borg UI so users do not need inbound firewall
  rules on client machines
- Support users who want Borg backup management without a local web UI
- Reuse Borg UI's existing jobs, progress, repository, schedule, auth,
  notification, and activity concepts where practical
- Preserve Borg's local execution model: the machine that owns the data should
  run Borg against the configured repository

## Non-Goals

- The agent is not a second Borg UI server
- The agent does not embed the frontend
- The agent does not own the central database
- The agent does not require Docker
- The first release does not need inbound server-to-agent calls
- The first release does not need a full restore UI for every platform
- The first release does not replace SSH remote machines

## Product Model

Borg UI should expose a unified Machines area.

Machine connection types:

| Type | Meaning |
| --- | --- |
| `ssh` | Borg UI connects to the machine over SSH using the existing system SSH key model |
| `agent` | A lightweight agent connects outbound to Borg UI and executes jobs locally |

The current Remote Machines feature remains useful. Agent machines should be
added beside it, not forced into the existing `ssh_connections` table as a
compatibility hack.

## Architecture

The architecture has two parts:

- Borg UI server: control plane, API, UI, database, scheduler, job history,
  notifications, and repository metadata
- Borg UI Agent: small CLI/daemon installed on managed machines

The MVP transport is HTTPS polling:

1. The agent registers or is provisioned with an enrollment token.
2. The agent stores a long-lived agent credential locally.
3. The agent sends heartbeats with system and Borg capabilities.
4. The agent polls Borg UI for pending work.
5. The agent claims a job, executes Borg locally, streams progress/log events,
   and reports the final result.

Polling is intentionally chosen for the MVP because it works behind NAT,
consumer routers, corporate firewalls, and mobile machines without opening
ports.

Future transports such as WebSocket, MQTT, or server-sent events can be added
without changing the core job model.

## Reuse From Current Borg UI

The implementation should reuse:

- existing authenticated API patterns
- existing role and permission checks
- existing job statuses and activity semantics
- existing backup progress contract fields
- existing Borg 1 and Borg 2 command-building knowledge
- existing repository metadata concepts
- existing log retention and display patterns
- existing notification hooks for job completion
- existing schedule concepts

The implementation should not ship the full Borg UI application inside the
agent.

Agent code should be a separate runtime under an `agent/` directory or similar.
Shared protocol types can be extracted into a small shared module if that
reduces duplication without coupling the agent to the full backend.

## Agent Responsibilities

The agent is responsible for:

- enrollment and local credential storage
- identifying the machine consistently across restarts
- reporting hostname, OS, architecture, agent version, Borg versions, and
  supported capabilities
- polling for pending jobs
- claiming one job before execution
- running Borg locally
- streaming progress and log events back to Borg UI
- reporting job completion or failure
- supporting cancellation checks
- protecting local secrets and config files with restrictive permissions

The agent should be boring and small. It should not contain scheduling policy,
user management, repository ownership rules, notification policy, or UI logic.

## Server Responsibilities

Borg UI server is responsible for:

- creating and revoking enrollment tokens
- registering agents as managed machines
- issuing scoped agent credentials
- tracking machine status and capabilities
- storing repository and backup configuration
- scheduling agent jobs
- exposing pending jobs to agents
- accepting progress, logs, and final results
- showing agent machines in the UI
- enforcing user permissions
- notifying users about job outcomes

## MVP Scope

MVP must include:

- agent enrollment
- agent heartbeat
- agent capability reporting
- central list of agent machines
- creating an agent-managed repository record
- triggering an on-demand backup on an agent
- agent-side Borg backup execution
- progress/log upload
- job completion and failure reporting
- cancellation request handling
- basic agent install/run documentation

MVP may include:

- scheduled backups for agent repositories
- Linux systemd service installation
- macOS launchd service installation

MVP should not include:

- Windows service support unless it falls out cleanly
- remote restore execution
- archive mounting on agent machines
- bidirectional streaming transport
- package management for Borg installation
- automatic self-update
- agent-to-agent communication

## Follow-Up Scope

Likely follow-up features:

- scheduled agent backups
- restore to agent machine
- restore from agent repository to server
- repository check, prune, compact, and break-lock jobs
- agent auto-update
- richer file browsing through the agent
- WebSocket transport
- Windows service packaging
- per-agent policy controls
- agent groups or labels
- offline missed-run behavior

## Data Model

The first implementation should add dedicated models instead of overloading
`SSHConnection`.

### ManagedMachine

Represents a machine known to Borg UI.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | integer | Primary key |
| `name` | string | Friendly display name |
| `connection_type` | string | `ssh` or `agent` |
| `status` | string | `pending`, `online`, `offline`, `disabled`, `revoked` |
| `last_seen_at` | datetime | Last heartbeat time |
| `created_at` | datetime | Creation time |
| `updated_at` | datetime | Update time |

For MVP, this may be represented as `AgentMachine` only if unifying SSH and
agent machines would cause too much churn.

### AgentMachine

Represents agent-specific machine identity and capability data.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | integer | Primary key |
| `machine_id` | integer | Optional FK to `managed_machines.id` |
| `name` | string | Friendly display name |
| `agent_id` | string | Stable public identifier generated by server |
| `token_hash` | string | Hash of the agent credential |
| `token_prefix` | string | Short prefix for audit/debug |
| `hostname` | string | Reported hostname |
| `os` | string | `linux`, `darwin`, `windows`, etc. |
| `arch` | string | CPU architecture |
| `agent_version` | string | Installed agent version |
| `borg_versions` | JSON | Detected Borg binaries and versions |
| `capabilities` | JSON | Supported operations |
| `labels` | JSON | Optional labels |
| `status` | string | `pending`, `online`, `offline`, `disabled`, `revoked` |
| `last_seen_at` | datetime | Last successful heartbeat |
| `last_error` | text | Last agent-level error |
| `created_at` | datetime | Creation time |
| `updated_at` | datetime | Update time |

### AgentEnrollmentToken

Short-lived token used to register an agent.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | integer | Primary key |
| `name` | string | Admin-facing name |
| `token_hash` | string | Hash of one-time enrollment token |
| `token_prefix` | string | Prefix shown in UI |
| `created_by_user_id` | integer | User who created it |
| `expires_at` | datetime | Required |
| `used_at` | datetime | Set after successful enrollment |
| `used_by_agent_id` | integer | Agent that consumed it |
| `revoked_at` | datetime | Manual revocation |
| `created_at` | datetime | Creation time |

Enrollment tokens must be shown once.

### AgentJob

Represents work assigned to an agent.

Suggested fields:

| Field | Type | Notes |
| --- | --- | --- |
| `id` | integer | Primary key |
| `agent_machine_id` | integer | Target agent |
| `job_type` | string | `backup`, later `restore`, `check`, `prune`, etc. |
| `status` | string | `queued`, `claimed`, `running`, `cancel_requested`, `completed`, `failed`, `canceled` |
| `payload` | JSON | Command-specific request |
| `result` | JSON | Command-specific result |
| `claimed_at` | datetime | Set when agent claims work |
| `started_at` | datetime | Set when execution begins |
| `completed_at` | datetime | Set when final result arrives |
| `error_message` | text | Human-readable failure |
| `created_at` | datetime | Creation time |
| `updated_at` | datetime | Update time |

The implementation can either map `AgentJob` to existing `BackupJob` rows or
add a linking column from `BackupJob` to `AgentJob`. The UI-facing backup
history should remain consistent with local and SSH jobs.

## Agent API

All agent endpoints should live under:

```text
/api/agents
```

Admin/user-facing management endpoints may live under:

```text
/api/managed-machines
```

or a similar route, but agent runtime endpoints should stay separate from UI
management endpoints.

### Authentication

Agent runtime endpoints must use agent credentials, not normal browser login
tokens.

The first implementation should also wire existing generated API tokens into
backend authentication or introduce a dedicated agent-token verifier. Current
docs note that generated API tokens are not standalone credentials yet, so this
must be fixed before relying on API tokens for agent auth.

Suggested header:

```text
X-Borg-Agent-Authorization: Bearer <agent-token>
```

Using a separate header avoids collisions with browser auth, reverse proxies,
and existing `X-Borg-Authorization` behavior.

### Create Enrollment Token

User-facing admin endpoint.

```text
POST /api/managed-machines/enrollment-tokens
```

Request:

```json
{
  "name": "laptop setup",
  "expires_in_minutes": 60
}
```

Response:

```json
{
  "id": 1,
  "name": "laptop setup",
  "token": "borgui_enroll_...",
  "token_prefix": "borgui_enr",
  "expires_at": "2026-05-11T12:00:00Z"
}
```

### Register Agent

Agent runtime endpoint.

```text
POST /api/agents/register
```

Request:

```json
{
  "enrollment_token": "borgui_enroll_...",
  "name": "karan-macbook",
  "hostname": "karan-macbook.local",
  "os": "darwin",
  "arch": "arm64",
  "agent_version": "0.1.0",
  "borg_versions": [
    { "major": 1, "version": "1.2.8", "path": "/opt/homebrew/bin/borg" }
  ],
  "capabilities": ["backup.create", "backup.cancel", "logs.stream"]
}
```

Response:

```json
{
  "agent_id": "agt_...",
  "agent_token": "borgui_agent_...",
  "server_time": "2026-05-11T12:00:00Z",
  "poll_interval_seconds": 15
}
```

The server must store only a hash of `agent_token`.

### Heartbeat

```text
POST /api/agents/heartbeat
```

Request:

```json
{
  "agent_id": "agt_...",
  "hostname": "karan-macbook.local",
  "agent_version": "0.1.0",
  "borg_versions": [
    { "major": 1, "version": "1.2.8", "path": "/opt/homebrew/bin/borg" }
  ],
  "capabilities": ["backup.create", "backup.cancel", "logs.stream"],
  "running_job_ids": [12]
}
```

Response:

```json
{
  "server_time": "2026-05-11T12:00:00Z",
  "poll_interval_seconds": 15,
  "cancel_job_ids": []
}
```

### Poll Jobs

```text
GET /api/agents/jobs/poll?limit=1
```

Response:

```json
{
  "jobs": [
    {
      "id": 12,
      "type": "backup",
      "created_at": "2026-05-11T12:00:00Z",
      "payload": {
        "repository_id": 7,
        "borg_version": 1,
        "repository_path": "ssh://backup@example.com:22/backups/laptop",
        "archive_name": "laptop-{now}",
        "source_paths": ["/Users/karan/Documents"],
        "exclude_patterns": ["*.tmp"],
        "compression": "lz4",
        "environment": {
          "BORG_PASSPHRASE": { "secret_ref": "repo-passphrase" }
        }
      }
    }
  ]
}
```

The server should avoid sending plaintext secrets unless required for MVP.
If plaintext secrets are sent, the decision must be documented and limited to
the minimum required scope.

### Claim Job

```text
POST /api/agents/jobs/{job_id}/claim
```

Response:

```json
{
  "status": "claimed"
}
```

Claiming must be idempotent for the same agent and reject claims by other
agents.

### Start Job

```text
POST /api/agents/jobs/{job_id}/start
```

Request:

```json
{
  "started_at": "2026-05-11T12:00:01Z"
}
```

### Send Progress

```text
POST /api/agents/jobs/{job_id}/progress
```

Request:

```json
{
  "progress_percent": 42.5,
  "current_file": "/Users/karan/Documents/report.pdf",
  "original_size": 104857600,
  "compressed_size": 52428800,
  "deduplicated_size": 1048576,
  "nfiles": 184,
  "backup_speed": 8388608,
  "estimated_time_remaining": 60
}
```

Progress fields should follow `app/services/backup_progress_contract.py`.

### Send Logs

```text
POST /api/agents/jobs/{job_id}/logs
```

Request:

```json
{
  "sequence": 18,
  "stream": "stderr",
  "message": "Creating archive at ...",
  "created_at": "2026-05-11T12:00:02Z"
}
```

Log sequence numbers must allow the server to ignore duplicate uploads.

### Complete Job

```text
POST /api/agents/jobs/{job_id}/complete
```

Request:

```json
{
  "completed_at": "2026-05-11T12:05:00Z",
  "result": {
    "archive_name": "laptop-2026-05-11T12:00:00",
    "return_code": 0,
    "stats": {
      "original_size": 104857600,
      "compressed_size": 52428800,
      "deduplicated_size": 1048576,
      "nfiles": 184
    }
  }
}
```

### Fail Job

```text
POST /api/agents/jobs/{job_id}/fail
```

Request:

```json
{
  "completed_at": "2026-05-11T12:01:00Z",
  "error_message": "borg create exited with code 2",
  "return_code": 2
}
```

## Agent CLI

Initial command shape:

```bash
borg-ui-agent register --server https://borgui.example.com --token borgui_enroll_...
borg-ui-agent status
borg-ui-agent run
borg-ui-agent once
borg-ui-agent unregister
```

Command meanings:

| Command | Meaning |
| --- | --- |
| `register` | Enroll with a Borg UI server and store agent credentials |
| `status` | Show local config, server URL, last heartbeat, Borg availability |
| `run` | Run the long-lived polling loop |
| `once` | Poll once and execute at most one job; useful for debugging |
| `unregister` | Remove local credentials and ask server to disable the agent |

Config location:

| Platform | Path |
| --- | --- |
| Linux | `/etc/borg-ui-agent/config.toml` for service installs, or `~/.config/borg-ui-agent/config.toml` for user installs |
| macOS | `~/Library/Application Support/borg-ui-agent/config.toml` |
| Windows | `%ProgramData%\\borg-ui-agent\\config.toml` |

Local config must contain the server URL, agent ID, and encrypted or protected
agent credential. File permissions must be restrictive where the platform
supports it.

## Job Payload Rules

Agent job payloads must be explicit and versioned.

Suggested top-level fields:

```json
{
  "schema_version": 1,
  "job_kind": "backup.create",
  "repository": {},
  "backup": {},
  "secrets": {}
}
```

Rules:

- Do not make the agent fetch arbitrary backend state for a job.
- Include enough immutable data in the payload for the job to run predictably.
- Include IDs for correlation, but do not depend on the agent having a local
  copy of the server database.
- Treat secrets as sensitive from payload creation through local process
  execution.
- Prefer environment variables over shell interpolation for secrets.
- Avoid shell string commands where argument arrays are possible.

## Secrets

The MVP may need to send repository passphrases to the agent so Borg can run on
the machine that owns the source data.

Minimum rules:

- agent tokens are hashed server-side
- enrollment tokens are hashed server-side and one-time use
- secrets must not be logged
- passphrases must be passed to Borg through environment variables, not command
  arguments
- progress/log uploads must redact known secret values
- job payloads containing secrets must only be delivered to the assigned agent
- revoking an agent prevents future polling and uploads

Future improvement:

- encrypt job secrets to an agent public key
- support secret references with short-lived retrieval
- support local agent-managed repository secrets where the server never stores
  the passphrase

## Security Model

Agent credentials authorize only one machine.

An agent credential may:

- heartbeat for its agent ID
- poll jobs assigned to that agent
- claim jobs assigned to that agent
- upload progress/logs/results for jobs assigned to that agent

An agent credential must not:

- access normal Borg UI user APIs
- list users
- list unrelated repositories
- list unrelated agents
- create arbitrary jobs
- read jobs assigned to another agent
- act after revocation

User-facing management of agents requires admin permission for MVP.

Later versions can add operator-level permissions for running jobs on machines
they are allowed to operate.

## Cancellation

Cancellation is cooperative.

Flow:

1. User requests cancellation in Borg UI.
2. Server marks the job as `cancel_requested`.
3. Agent sees cancellation in heartbeat or job status polling.
4. Agent terminates the Borg process gracefully.
5. Agent reports `canceled` if the process stops because of the request.

The agent should avoid force-killing immediately unless Borg ignores graceful
termination.

## Offline Behavior

The server marks agents offline when `last_seen_at` exceeds a configured
threshold.

Suggested defaults:

| Setting | Default |
| --- | --- |
| Heartbeat interval | 30 seconds |
| Job poll interval | 15 seconds |
| Offline threshold | 2 minutes |

Queued jobs remain queued while the agent is offline unless canceled by the
user or expired by policy.

MVP does not need missed schedule catch-up logic.

## Repository Model

Agent-managed repositories should be identifiable from existing repositories.

Possible fields on `Repository`:

| Field | Meaning |
| --- | --- |
| `execution_target` | `local`, `ssh`, or `agent` |
| `agent_machine_id` | Agent machine that runs backup jobs |

For MVP, `repository_type` should continue to describe repository location
where possible, and a new execution-target field should describe where Borg
executes.

This distinction matters:

- repository location: where the Borg repository lives
- execution target: where `borg create` runs
- source paths: paths visible to the execution target

## UI Requirements

MVP UI should include:

- Machines list showing SSH and agent machines, or an agent-only page if a
  unified page is too much for the first change
- agent status, last seen, hostname, OS, architecture, agent version, Borg
  versions, and capabilities
- create enrollment token dialog
- copyable install/register command
- disable/revoke agent action
- repository create/import flow that can target an agent
- on-demand backup action for agent repositories
- progress and logs in existing job views

Avoid teaching users transport details in primary UI text. The visible model
should be "this machine is managed by an agent".

## Packaging

Preferred implementation language for MVP: Python.

Reasons:

- repository is already Python-heavy
- Borg UI already has Borg command/parsing logic in Python
- packaging can start simple
- unit tests can share existing test tooling

Packaging stages:

1. source checkout/dev command
2. Python package entry point
3. install script for Linux/macOS services
4. standalone binaries, if needed
5. Windows service packaging

## Observability

The server should log:

- enrollment token creation, use, and revocation
- agent registration
- heartbeat status transitions
- job claim/start/completion/failure
- auth failures for agent endpoints

Logs must not include:

- enrollment token values
- agent token values
- repository passphrases
- full secret-bearing payloads

## Testing Plan

Backend unit tests:

- enrollment token creation and one-time use
- agent token authentication
- heartbeat status updates
- job polling only returns jobs for the authenticated agent
- job claiming is idempotent for the assigned agent
- unrelated agents cannot read or mutate jobs
- revocation blocks runtime endpoints

Agent unit tests:

- config file read/write permissions
- Borg binary detection
- payload validation
- progress parsing
- log sequence handling
- cancellation handling

Integration tests:

- fake agent enrolls, heartbeats, polls, completes job
- fake agent fails job and server records error
- cancellation request reaches fake agent
- UI-facing backup job state is updated from agent events

Smoke tests:

- Linux agent backs up a temporary directory to a local temporary repository
- agent reconnects after restart and keeps the same identity

## Implementation Phases

### Phase 1: Foundation

- add spec
- add models and migrations
- add agent auth verifier
- add enrollment token API
- add register and heartbeat endpoints
- add basic tests

### Phase 2: Job Transport

- add agent job model
- add poll, claim, start, progress, logs, complete, and fail endpoints
- add cancellation state
- add fake-agent integration tests

### Phase 3: Agent Runtime

- add `borg-ui-agent` package/entry point
- add register/status/run/once commands
- add local config handling
- add Borg detection
- add backup execution
- add progress/log upload

### Phase 4: UI

- add agent machine list
- add enrollment token UI
- add install/register command helper
- add agent target in repository flow
- connect agent jobs to existing progress/log surfaces

### Phase 5: Hardening

- service installation docs
- log redaction review
- token rotation/revocation polish
- offline behavior
- smoke tests

## Open Decisions

- whether to introduce `ManagedMachine` immediately or start with
  `AgentMachine`
- whether agent job rows link to `BackupJob` or embed backup state directly
- whether passphrases are sent in job payloads for MVP or stored locally on the
  agent
- whether the initial UI should unify SSH and agent machines in one page
- whether the first package should be repo-local only or published as a Python
  package

Before implementation starts, resolve the first three decisions or choose
conservative defaults in the first implementation PR.
