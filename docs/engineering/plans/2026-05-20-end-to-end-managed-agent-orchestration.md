# End-to-End Managed Agent Orchestration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. This plan is
> the BOR-38 investigation artifact and the source for BOR-39 implementation
> planning.

**Goal:** Make Borg UI agents first-class Borg executors without replacing SSH
connections or creating a separate agent-only backup product.

**Decision summary:** Keep the server as the orchestrator. Split repository
execution into three explicit axes: who runs Borg, where source data lives, and
where the repository lives. Agents should run structured job kinds near the data
and report into the same `BackupJob`, plan run, maintenance, restore, progress,
log, and notification surfaces that server-run jobs already use.

**Recommended first slice:** migrate the data model and repository wizard to an
explicit `executor_type = server | agent`, keep existing server execution as the
default, and make manual `backup.create` plus backup-plan execution route through
the selected executor. Defer remote-to-remote SSH targets until the executor
model, plan routing, and reliability contracts are in place.

## Evidence Base

Current Borg UI source:

- Agent registration, heartbeat, job queue, progress, logs, and terminal status:
  [`app/api/agents.py`](../../../app/api/agents.py)
- Manual backup to agent routing:
  [`app/api/backup.py`](../../../app/api/backup.py)
- Agent runtime and backup command handler:
  [`agent/borg_ui_agent/runtime.py`](../../../agent/borg_ui_agent/runtime.py),
  [`agent/borg_ui_agent/backup.py`](../../../agent/borg_ui_agent/backup.py)
- Repository, agent, backup job, and plan models:
  [`app/database/models.py`](../../../app/database/models.py)
- Backup plan execution:
  [`app/services/backup_plan_execution_service.py`](../../../app/services/backup_plan_execution_service.py)
- Existing SSH and remote execution paths:
  [`app/services/backup_service.py`](../../../app/services/backup_service.py),
  [`app/services/remote_backup_service.py`](../../../app/services/remote_backup_service.py)
- Repository wizard behavior:
  [`frontend/src/components/RepositoryWizard.tsx`](../../../frontend/src/components/RepositoryWizard.tsx),
  [`frontend/src/components/wizard/WizardStepLocation.tsx`](../../../frontend/src/components/wizard/WizardStepLocation.tsx),
  [`frontend/src/components/wizard/WizardStepDataSource.tsx`](../../../frontend/src/components/wizard/WizardStepDataSource.tsx)

Upstream borgbackupserver source:

- Repository root:
  <https://github.com/marcpope/borgbackupserver>
- Agent runtime:
  <https://github.com/marcpope/borgbackupserver/blob/main/agent/bbs-agent.py>
- Agent API:
  <https://github.com/marcpope/borgbackupserver/blob/main/src/Controllers/Api/AgentApiController.php>
- Queue and task routing:
  <https://github.com/marcpope/borgbackupserver/blob/main/src/Services/QueueManager.php>
- Borg command and environment builder:
  <https://github.com/marcpope/borgbackupserver/blob/main/src/Services/BorgCommandBuilder.php>
- Backup plans and scheduler:
  <https://github.com/marcpope/borgbackupserver/blob/main/src/Controllers/BackupPlanController.php>,
  <https://github.com/marcpope/borgbackupserver/blob/main/src/Services/SchedulerService.php>
- Repository and maintenance surfaces:
  <https://github.com/marcpope/borgbackupserver/blob/main/src/Controllers/RepositoryController.php>

## Current Borg UI Behavior

Borg UI already has the core transport for managed agents:

- `AgentMachine` records enrolled agents with token auth, platform data, Borg
  binaries, capabilities, status, and last heartbeat.
- `AgentJob` stores queued, claimed, running, completed, failed, and canceled
  agent work with JSON payloads, progress fields, result, and logs.
- Agents register with an enrollment token, poll outbound over HTTP, claim one
  queued job, report logs/progress, and complete/fail/cancel the job.
- Linked agent jobs sync terminal status, progress, logs, archive name, and
  `Repository.last_backup` into the linked `BackupJob`.

The current implementation is still a backup MVP, not first-class
orchestration:

- The Python agent advertises only polling/reporting/log streaming plus
  `backup.create` and cancel. Unknown job kinds are failed.
- The only real agent handler builds and runs `borg create` locally from a
  structured payload containing repository path, archive name, source paths,
  compression, excludes, custom flags, optional remote Borg path, and
  passphrase.
- Manual backup routing checks `Repository.execution_target == "agent"` and
  queues an `AgentJob`. Otherwise, the server executes via `backup_service`.
- Backup plans are not executor-aware. `BackupPlanExecutionService` creates a
  `BackupJob` for each repository and always calls server-side
  `backup_service.execute_backup`.
- `Repository.execution_target in {local, ssh, agent}` currently mixes two
  concepts: executor and repository location. `connection_id` and
  `source_ssh_connection_id` are also cleared or disabled in the wizard when
  agent execution is selected.
- Existing remote-source support is server-pull via SSHFS, and
  `RemoteBackupService` is a separate SSH command-execution path. Neither is the
  managed-agent data plane.

## Upstream Borgbackupserver Behavior

The upstream project is agent-first. Its central concepts are `agents`,
`repositories`, `backup_plans`, `schedules`, and `backup_jobs` owned by an agent.
The server builds tasks, the agent polls, and most endpoint-side work is
represented as a task assigned to that agent.

The upstream agent handles:

- Registration, token auth, heartbeat, server info, SSH key download, and SSH
  connection verification back to the server.
- Backup tasks by running a server-built Borg command, injecting environment,
  running pre/post backup plugin payloads, streaming file catalog data back to
  the server, parsing Borg JSON progress, and reporting final archive metadata.
- Restore tasks, including generic restores and database-specific MySQL,
  PostgreSQL, and MongoDB restore helpers.
- Plugin tasks for database backups and shell hooks.
- Borg binary update and agent self-update tasks.
- Cancellation from both progress responses and heartbeat responses, including
  process-tree cleanup for Borg and SSH child processes.
- Stalled job reconciliation through `check_jobs`, where the server asks the
  agent whether a supposedly running job is still active.

The upstream server handles:

- Agent registration and every authenticated agent request updating heartbeat
  status.
- Queue processing that promotes queued `backup_jobs` to sent tasks, with global
  queue limits, per-plan duplicate suppression, and special handling for
  management tasks.
- Scheduled backups by inserting queued `backup_jobs` for a plan's agent and
  repository.
- Terminal status idempotency: if a job is already completed, failed, or
  cancelled, a repeated terminal report returns OK without corrupting state.
- Server-side maintenance jobs for several repository operations. The queue code
  explicitly excludes prune, compact, S3 sync/restore, repo check/repair,
  break-lock, catalog rebuild, and archive delete from normal agent task polling
  and marks them for server-side execution.
- Remote SSH repository access by building `BORG_RSH` and, for remote SSH
  repositories, passing key material for the agent to write to a temporary key
  file.

The most important lesson is not to copy the upstream command payload exactly.
It sends broad server-built commands to the agent. Borg UI should keep the safer
structured job payload model and grow it by job kind.

## One-to-One Comparison

| Area | Borg UI today | Upstream borgbackupserver | Plan for Borg UI |
| --- | --- | --- | --- |
| Agent role | Lightweight worker for `backup.create` manual jobs. | Primary executor for backup plans, restores, updates, plugins, and some repository flows. | Treat agent as an executor, not a separate product surface. Route existing operations by executor. |
| Executor model | `Repository.execution_target` mixes local/SSH/agent. | Repository is owned by an agent; server builds tasks for that agent. | Split `executor_type` from repository location and source location. Keep legacy mapping during migration. |
| Source data | Repository and plan source fields support local and SSH pull. Agent source is just payload paths. | Plan directories are interpreted by the agent local filesystem. | Source paths bind to executor. Agent executor means paths are local to that agent. Mixed plans need explicit per-repo/per-source scope. |
| Repository location | Local or SSH target for server execution; SSH target is disabled in the wizard for agent execution. | Local server-hosted repo exposed over SSH to the agent, or remote SSH repo with agent-side `BORG_RSH`. | Allow agent-local repo first, then agent-to-SSH target. Do not hairpin data through the server. |
| Manual backup | Agent repos queue `AgentJob` and sync into `BackupJob`. | Backup job queue is the central path. | Keep the current linked `AgentJob` to `BackupJob` design and harden it. |
| Backup plans | Always server-executed today. | Schedules insert queued agent backup jobs. | Make plan execution route each repository through server or agent and wait for terminal state uniformly. |
| Job kinds | Only `backup.create`. | Backup, restore, database restore, plugin test, update Borg, update agent; many maintenance types are server-side. | Add a handler registry and structured payloads for restore, check, prune, compact, archive delete, info, and later hooks. |
| Reliability | Log sequence dedupe exists, but terminal endpoints reject repeated final reports. No local agent queue. | Repeated terminal reports are OK; heartbeat and tasks return stall/cancel probes. | Add idempotent terminal reports, local agent persistence, retry with jitter, reconciler, and process-tree cancellation. |
| UI | Managed Agents page is operational, but jobs are primarily visible there. Repository wizard has an agent choice but blocks SSH source/target combinations. | Agent/client pages own repos, plans, jobs, and logs. | Keep repository and backup-plan surfaces primary; show transport chips and keep Agent Jobs as diagnostics. |
| Security | Structured payload is good. No self-update, no arbitrary command execution. | More powerful command and update/plugin surface. | Preserve structured contracts. Defer self-update and hooks until signing, rollback, redaction, and sandbox decisions are made. |

## Target Model

### 1. Data Model

Add explicit executor fields without removing the legacy field immediately:

- `Repository.executor_type in {"server", "agent"}`. Default `server`.
- `Repository.agent_machine_id` required only when `executor_type = "agent"`.
- Keep repository location in the existing repository target fields:
  `path`, `connection_id`, `remote_path`, Borg version, encryption, and
  passphrase.
- Keep source location in plan or repository source fields:
  source type, `source_ssh_connection_id`, source directories, and
  `source_locations`.
- Keep `execution_target` as a compatibility field for one release:
  - old `local` maps to executor `server` with no SSH repository target;
  - old `ssh` maps to executor `server` with an SSH repository target;
  - old `agent` maps to executor `agent`.

Add a light `Host` or `Endpoint` association after the executor split:

- `Host { id, name, hostname, labels, notes }`
- `SSHConnection.host_id nullable`
- `AgentMachine.host_id nullable`

This lets one Raspberry Pi have both an SSH connection and an enrolled agent.
The association is optional. SSH-only and agent-only endpoints remain valid.

### 2. Raspberry Pi Acceptance Walkthrough

This walkthrough is the product contract.

1. The user adds an SSH connection for `pi.local`. Borg UI can browse storage
   and use it as a server-pulled source or SSH repository target.
2. The user enrolls the agent on the same Pi. The Managed Agents page shows the
   Pi as online.
3. Borg UI detects matching hostname/fingerprint evidence and offers to link the
   SSH connection and agent to the same Host. It never links silently.
4. The user edits a repository and chooses executor `Agent: raspberrypi`.
5. The UI explains that source paths such as `/home` and `/etc` now mean the
   agent's local filesystem, not the server filesystem.
6. The user chooses repository location separately: agent-local filesystem for
   the first slice, SSH repository target in a later remote-to-remote slice.
7. The next manual backup or plan run queues an `AgentJob`. The agent polls,
   claims, runs Borg locally, streams progress/logs, and the result appears in
   normal repository backup history with a transport chip.
8. The user may keep the SSH connection for browsing and server-pull workflows
   while the agent owns backups for that repository.

### 3. Execution Routing

Create one routing layer used by manual backup, backup plans, and later
maintenance/restore services:

```python
if repository.executor_type == "server":
    await backup_service.execute_backup(...)
elif repository.executor_type == "agent":
    agent_job = enqueue_agent_job(...)
    await wait_for_terminal_agent_result(agent_job.id)
    sync_terminal_result_into_existing_job_surface(...)
```

For backup plans:

- Route per repository. Mixed executor plans are allowed only when source scope
  is explicit enough to avoid ambiguity.
- Preserve archive templating, compression, excludes, custom flags, rate limits,
  failure behavior, series/parallel ordering, and notifications.
- Plan cancellation must cancel queued/running agent jobs and server-side work.
- Server-side plan scripts continue to run on the server. Agent-side hooks are
  out of scope until a separate hooks contract exists.

### 4. Agent Job Kinds

Keep the current structured payload shape and add a discriminated `job_kind`.
Do not send arbitrary shell commands from the server to the agent.

| Job kind | Existing surface | Priority | Notes |
| --- | --- | --- | --- |
| `backup.create` | `BackupJob` | Already exists | Harden payload, retries, terminal idempotency, process cleanup. |
| `restore.extract` | Restore flow | Next | Needed for restore-to-agent paths and agent-local source restores. |
| `repository.check` | Check/maintenance | Next | May be server or agent depending on repository location and executor. |
| `repository.prune` | Prune/maintenance | Next | Needs Borg version and repository lock semantics. |
| `repository.compact` | Compact/maintenance | Next | Borg 2 only where applicable. |
| `archive.delete` | Archive actions | Later | Must sync archive/catalog state on success. |
| `repository.info` | Diagnostics/verify | Later | Useful for repository verification and setup checks. |
| `paths.browse` | Source picker | Later | Could be replaced by heartbeat-reported mounts for the first slice. |
| `hooks.run` | Scripts/hooks | Deferred | Requires a security contract before implementation. |

### 5. Remote-to-Remote Data Plane

When executor is `agent` and repository location is an SSH target, Borg must run
on the agent and write directly to the target. The Borg UI server must not proxy
or SSHFS-mount the data path.

Start with user-managed credentials:

- The user installs an SSH key on the agent or points Borg UI to an agent-side
  key path.
- The remote target authorizes that key, ideally with
  `command="borg serve --append-only --restrict-to-repository=..."`.
- The agent payload includes structured repository target details and the Borg
  environment needed to set `BORG_RSH`.
- The server stores enough metadata to validate and display the target, but the
  agent performs the network write directly.

Plan for server-provisioned short-lived credentials later:

- The server mints per-job SSH certificates or forced-command credentials.
- The target enforces append-only and repository restriction.
- The agent never keeps long-lived target credentials.

Reject server proxying as the default remote-to-remote model because it restores
the server hairpin this feature is meant to remove.

### 6. Reliability Contract

Before scheduled backups depend on agents, harden these contracts:

- Terminal endpoints are idempotent by `(agent_job_id, terminal_status,
  attempt_token)` and return the same result on retry.
- Agent persists unsent logs, progress, and terminal reports locally, with
  exponential backoff and jitter until the server acknowledges them.
- Server reconciler marks stale claimed/running jobs abandoned after heartbeat
  grace, or requeues claimed-but-never-started work when safe.
- Heartbeat returns cancel and check-job probes for currently running jobs.
- Agent cancellation kills the whole process tree, including Borg SSH children.
- Server enforces minimum agent version by job kind and exposes clear upgrade
  messaging.
- Agent log redaction must run before sending output that may contain
  passphrases, SSH options, or hook secrets.

### 7. UI Direction

Follow the existing operational MUI dashboard style. Do not create a marketing
page or an agent-only backup workflow.

- Repository wizard asks one explicit question: "Where should backups run?"
  with Server and Agent choices.
- Repository location is a separate choice: server-local, SSH target,
  agent-local, and later agent-to-SSH target where appropriate.
- Source picker labels where paths are interpreted: server local, SSH source, or
  agent local.
- Repository backup history and backup plan run history stay primary. Add a
  small transport chip (`server`, `agent: raspberrypi`) to job rows.
- Managed Agents remains a fleet and diagnostics surface. It can show filtered
  Agent Jobs, but it is not the only place to find backup history.
- Introduce an Endpoints or Hosts page only after the data model can link an SSH
  connection and an agent to the same host.

### 8. Security Boundaries

Keep these out of the first implementation:

- Arbitrary command execution on agents.
- Agent-side scripts/hooks without signed delivery, timeout, environment,
  redaction, exit-code, and sandbox/user-separation decisions.
- Agent self-update without signed releases, version pinning, atomic rollback,
  trusted roots, and an audit trail.
- Agent-to-agent communication or peer sync.
- Silent fallback from agent execution to server execution when an agent is
  offline. Default should be queue with timeout, then fail with a clear reason.

## Implementation Phases

### M1. Executor Model Lock-In

- Add `executor_type` and compatibility mapping from `execution_target`.
- Add migration and repair checks for current `execution_target = "agent"` rows.
- Keep old API fields working during the migration window.
- Add backend tests for model mapping and repository create/update validation.

### M2. Repository Wizard and Manual Backup Parity

- Update the wizard to separate executor, repository location, and source
  location.
- Save agent executor repositories without clearing valid repository target data
  that will be supported by the chosen phase.
- Keep manual agent backup behavior but route through the new executor field.
- Add/update Storybook stories and snapshots for server, agent-local, and
  disabled/future SSH target states.
- Add backend and frontend validation for source path interpretation.

### M3. Backup Plans Become Executor-Aware

- Add an executor router to `BackupPlanExecutionService`.
- Queue linked `AgentJob` records from plan runs and wait for terminal state.
- Sync agent result into the same `BackupJob` and plan repository child row.
- Preserve failure behavior, cancellation, archive naming, and ordering.
- Add tests for series, parallel, mixed success/failure, cancellation, and
  offline-agent timeout.

### M4. Reliability Hardening

- Make agent terminal endpoints idempotent.
- Add agent local persistence for outgoing logs/progress/terminal reports.
- Add stale job reconciler and claimed-job requeue rules.
- Replace single-process termination with process-tree cancellation.
- Add focused unit tests plus an integration test with a fake polling agent.

### M5. Agent Discovery and Host Association

- Extend heartbeat with mounts, free space, useful source roots, and common repo
  path checks.
- Add optional Host association for SSH connections and AgentMachines.
- Surface same-host linking suggestions without automatic linking.
- Add Endpoints/Hosts UI only after the model exists.

### M6. Additional Job Kinds

- Add a handler registry on the agent.
- Implement restore, check, prune, compact, archive delete, and repository info
  incrementally.
- Each job kind must map terminal state into the existing Borg UI job surface.
- Defer hooks until the security contract is accepted.

### M7. Agent-to-SSH Repository Targets

- Add agent-to-SSH repository target support with user-managed credentials.
- Generate structured `BORG_RSH` environment for the agent.
- Document append-only forced-command hardening.
- Add a remote-to-remote smoke test proving data does not traverse Borg UI.

### M8. Endpoint Lifecycle and Security Upgrades

- Document Linux systemd as the canonical install path.
- Add macOS launchd guidance, Windows service packaging, and Docker agent image.
- Add minimum-version enforcement and upgrade messaging.
- Design signed self-update and Borg binary management before implementation.

## Verification Plan for Implementation Tickets

Each implementation ticket should include:

- Backend validation: `ruff check app tests`, `ruff format --check app tests`,
  and focused pytest paths for the touched service/API.
- Agent validation: unit tests for payload parsing, handler routing, retry,
  cancellation, and terminal reporting.
- Frontend validation for UI changes: `cd frontend && npm run check:locales`,
  `npm run typecheck`, `npm run lint`, `npm run build`, relevant Vitest tests,
  Storybook story updates, and `npm run snapshots`.
- Runtime proof for app-touching changes: a fake or real enrolled agent that
  polls, claims, runs or simulates a job, streams logs/progress, and updates the
  repository or plan history row.
- Remote-to-remote proof for M7: agent host sends Borg traffic directly to the
  SSH repository target while the Borg UI server only receives API traffic.

## What Borg UI Is Already Doing Extra

Borg UI already has several foundations that should be preserved instead of
replaced by the upstream pattern:

- Structured JSON agent payloads instead of arbitrary command execution.
- A separate `AgentJob` table linked to `BackupJob`, which can keep transport
  concerns isolated while existing backup history remains canonical.
- Richer source-location modeling for plans.
- Repository observe mode and source-aware repository scanning work.
- A React/MUI operational dashboard with Storybook/snapshot discipline.
- Existing SSH connection and remote backup services that can be reused as
  source/repository target concepts after the executor split.

## Open Decisions for BOR-39

BOR-39 should track the implementation plan and force these decisions before M2:

- Whether mixed-executor backup plans require per-repository source locations
  immediately, or whether they are blocked until that UI exists.
- Whether an offline agent queues for a configurable timeout or fails
  immediately. Recommendation: queue with a one-hour default timeout, no silent
  server fallback.
- Whether the first remote-to-remote slice stores only agent-side key paths or
  also encrypted private key material. Recommendation: agent-side key path first.
- Whether `Host` or `Endpoint` should be user-visible naming. Recommendation:
  use `Host` in the model, `Endpoints` in navigation.
- How long the legacy `execution_target` API field remains writable.
