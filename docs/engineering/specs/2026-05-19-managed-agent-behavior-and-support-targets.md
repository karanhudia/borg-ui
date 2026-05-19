# Managed Agent Behavior and Support Targets

Date: 2026-05-19

## Purpose

Borg UI's managed agent should let the server orchestrate Borg work on remote machines while the endpoint runs the backup or restore near the data. The server should decide what work should happen, enforce policy, track state, and present logs/progress. The agent should authenticate, poll for work, execute the permitted operation, and report durable results.

The important product goal is remote orchestration without unnecessary data hairpinning through the Borg UI server. For a remote-to-remote backup, Borg UI should be able to tell an enrolled endpoint to run Borg from that endpoint against a target repository so source data flows from the endpoint to the repository, not from endpoint to server to repository.

## Current Borg UI Managed Agent

Borg UI already has the base control-plane pieces:

- `agent/borg_ui_agent/runtime.py` advertises capabilities for job polling, claim/report, log streaming, `backup.create`, and cancellation.
- `agent/borg_ui_agent/cli.py` supports `register`, `status`, `once`, `run`, and `unregister`.
- `app/api/agents.py` exposes agent registration, heartbeat, unregister, job poll, claim, start, progress, logs, complete, fail, and cancel endpoints.
- `app/api/managed_machines.py` lets admins create enrollment tokens, list/revoke agents, queue manual agent backup jobs, inspect agent jobs/logs, and request cancellation.
- `app/api/backup.py` queues an `AgentJob` for manual backups when the repository has `execution_target == "agent"`.
- `agent/borg_ui_agent/backup.py` executes only `backup.create`, builds Borg 1 or Borg 2 commands from the job payload, streams logs, parses Borg JSON progress, and sends final complete/fail/cancel reports.

The current agent is intentionally narrow. It can run one backup job kind on the agent machine. It does not yet run restores, repository checks, prune/compact, archive deletion, repository initialization/verification, backup-plan orchestration, script hooks, file catalog upload, self-update, Borg installation, or stale-job reconciliation on the endpoint.

## Existing Borg UI Capabilities To Reuse

The managed-agent roadmap should reuse existing Borg UI behavior instead of inventing parallel concepts.

| Area | Existing capability | Reuse target for managed agents |
| --- | --- | --- |
| Repository execution model | `Repository.execution_target` already supports `local`, `ssh`, and `agent`; `agent_machine_id` links a repository to an enrolled machine. | Keep this as the primary routing switch for manual and scheduled work. |
| Agent transport | `AgentJob`, `AgentJobLog`, and agent endpoints already model queue, claim, running, progress, terminal status, logs, and cancellation. | Extend job kinds and durability on this transport instead of adding a second queue. |
| Manual backups | `app/api/backup.py` creates linked `BackupJob` + `AgentJob` and synchronizes agent terminal state back into `BackupJob`. | Use this as the pattern for backup-plan and future restore/maintenance jobs. |
| Borg 1/2 command shape | The agent supports Borg 1 and Borg 2 create syntax, while `BorgRouter` already routes server-side maintenance by Borg version. | Keep Borg-version-specific command construction explicit in each agent contract. |
| Repository payload fields | Repository path, passphrase, compression, excludes, custom flags, remote path, and Borg binary already flow into `backup.create`. | Promote these into stable schema fields with validation and redaction rules. |
| Backup plans | `BackupPlanExecutionService` already handles source locations, multi-repo ordering/parallelism, failure behavior, plan scripts, prune/compact/check-after options, and archive naming. | Add agent-aware plan execution that queues agent jobs instead of falling back to server execution. |
| Remote source handling | `backup_service` can mount or reference remote SSH source paths, and `remote_backup_service` can run a Borg command on a remote source over SSH when `BackupJob.execution_mode == "remote_ssh"`. | Reuse the source-location model, but prefer an enrolled agent for endpoint-side execution when available. |
| Scripts and hooks | Repository hooks and script-library execution already exist for server-side backups and backup plans. | Define an agent-side hook contract before enabling endpoint execution, including secrets and environment variable exposure. |
| Maintenance operations | Check, prune, compact, archive deletion, repository wipe, restore checks, and archive browsing already exist server-side. | Decide operation by operation whether the server or agent owns execution for agent-targeted repositories. |
| Progress/log UI | Backup jobs already display logs, progress fields, archive name, status, cancellation, and notifications. | Continue synchronizing agent jobs into existing job surfaces rather than creating a separate agent-only UX. |

## What Borg UI Should Support

These support targets are the recommended future scope. They should be implemented in separate tickets, not in BOR-38.

### 1. Agent-side backup parity

Managed-agent backups should support the same user-visible backup inputs as Borg UI server-side backups:

- manual backups for agent-targeted repositories;
- scheduled backup plans;
- local source paths on the agent machine;
- remote source locations where the agent can reach the source;
- SSH repositories, local repositories, and Borg 1/Borg 2 repositories;
- compression, excludes, custom flags, upload rate limits, archive naming, repository passphrases, remote Borg path, and Borg binary selection;
- progress, logs, cancellation, warning handling, terminal status, and notifications.

Current status: manual agent backups are queued through `app/api/backup.py`; backup plans still run through `BackupPlanExecutionService` and `backup_service.execute_backup`, which does not queue agent jobs based on `Repository.execution_target`.

### 2. Remote-to-remote orchestration without server hairpinning

The target architecture should distinguish the control plane from the data plane:

- Control plane: Borg UI server creates a signed or token-authenticated job, queues it for an enrolled agent, tracks progress, and persists terminal state.
- Data plane: the agent runs Borg where the source data is available and writes directly to the configured repository.

This means Borg UI should not require the server to mount a remote source and then write to another remote repository when an enrolled agent can do the work locally. The server may still own metadata, credentials, and policy, but it should avoid becoming the byte-moving middle box for remote-to-remote backup flows.

The existing `RemoteBackupService` proves Borg UI already has a command pattern for "run Borg on a remote machine against an SSH repository", but it is server-initiated over SSH and not integrated into managed-agent scheduling. The managed-agent version should reuse the same repository/source concepts while replacing server SSH reachability with agent polling.

### 3. Backup-plan support

Backup plans should route each repository according to its execution target:

- `local`: server executes with existing behavior.
- `ssh`: server executes against SSH repository/source behavior where intended.
- `agent`: server creates a linked `AgentJob` and waits for the agent result before marking the plan repository result.

Plan-level behavior should still apply: source-location selection, multi-repository ordering or parallelism, failure behavior, script policy, prune/compact/check-after options, archive naming, and cancellation. If a plan mixes local and agent repositories, the run model should clearly show which worker owns each repository.

### 4. Durability and recovery

The agent transport needs production recovery semantics before it owns critical scheduled backups:

- retry terminal complete/fail/cancel reports with backoff;
- reconcile jobs that the server thinks are running but the agent is not running;
- detect stale running jobs and mark them abandoned or retryable;
- kill whole process trees on cancellation, especially Borg SSH children;
- make terminal reports idempotent so retries do not corrupt job state;
- preserve enough logs to diagnose failures even when completion reporting is delayed.

### 5. Restore and maintenance job kinds

After backup parity, the next job-kind candidates are:

- `restore.extract` for restoring from an agent-accessible repository to an agent-local destination;
- `repository.check`;
- `repository.prune`;
- `repository.compact`;
- `archive.delete`;
- `repository.info` or `repository.verify` for endpoint-side validation;
- `hooks.run` only if the script/secrets contract is designed explicitly.

These should be explicit job contracts, not arbitrary shell-command jobs. Borg UI should keep server-side execution for operations where the server is the repository host or where endpoint-side credentials are not required.

### 6. Endpoint installation and lifecycle

Borg UI currently has documentation plus systemd/launchd templates. A complete managed-agent product needs:

- install and uninstall flows for Linux;
- launchd packaging and Full Disk Access guidance for macOS;
- Windows service installation;
- a Docker image for agentized environments;
- version reporting and compatibility checks;
- optional Borg binary discovery or installation policy;
- a self-update design only after signing, trust, rollback, and version pinning are defined.

## Upstream Reference Implementation Evidence

The upstream reference implementation at `marcpope/borgbackupserver` was inspected at commit `b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253`. It is useful because it is a mature endpoint-agent design with similar goals, but Borg UI should copy ideas only where they fit Borg UI's architecture.

| Dimension | Upstream reference | Borg UI today | Borg UI target |
| --- | --- | --- | --- |
| Control plane | Agent polls HTTPS endpoints for tasks, status, heartbeat, catalog, SSH key, and downloads. Source: `src/Core/App.php`, `agent/bbs-agent.py`. | Agent polls `/api/agents/jobs/poll` and uses explicit claim/start/progress/log/complete/fail/cancel endpoints. | Keep Borg UI's explicit state-machine API and add stronger retry/recovery semantics. |
| Data plane | Agent pushes Borg data over SSH using server-provisioned key and `BORG_RSH`; server constrains access with a forced-command gate. | Agent runs Borg against the repository path supplied in payload; server does not provision an append-only SSH gate for agents. | Decide whether Borg UI stays payload-path based or adds a managed append-only SSH repository option. |
| Backup execution | Server builds Borg command/env; agent runs plugins, Borg create, progress parsing, catalog streaming, and final status. | Agent builds Borg create command from structured payload and reports logs/progress. | Keep structured payloads, but add backup-plan parity and endpoint-side hooks only through defined contracts. |
| Restore | Supports file restore and database restore jobs on the endpoint. | Managed agent has no restore job kind. | Add `restore.extract` after backup parity and data-plane decisions. |
| Maintenance | Prune, compact, S3 sync/restore, repo check/repair, break-lock, catalog rebuild, and archive delete are server-side. | Borg UI has server-side maintenance services but does not route agent-targeted maintenance through the agent. | Choose per operation whether server or agent executes based on repository location and credentials. |
| Plugins/hooks | MySQL, PostgreSQL, MongoDB, InterWorx, and shell hooks run on the endpoint around backup. | Borg UI has repository and plan scripts server-side; managed agent does not execute them. | Reuse script concepts only after defining endpoint trust, environment, timeout, output, and secret handling. |
| Progress/logs | Parses Borg JSON and log messages; handles warning downgrades, restore counts, catalog entries, and cancellation. | Parses basic Borg JSON progress and sends sequenced logs. | Add richer warning classification, process-tree cancellation, and restore/file-count progress where applicable. |
| Completion durability | Terminal status reports retry with exponential backoff; heartbeat handles stalls and cancellations. | Terminal API call is not retried by the agent; heartbeat cancellation exists. | Add terminal retries, idempotent terminal endpoints, and stale-running reconciliation. |
| Installation | Has Linux/macOS/FreeBSD, Windows, Docker, startup wrapper, and self-update flows. | Borg UI has Python package install docs and service templates. | Build packaging/install lifecycle deliberately; defer self-update until release trust is designed. |

## Borg UI Extras Compared To The Reference

Borg UI already has several useful capabilities that should shape the target rather than be discarded:

- Borg 2 support exists in the agent and server command routing.
- Agent enrollment uses a one-time enrollment token that produces a separate durable agent token.
- Agent logs have a dedicated `(agent_job_id, sequence)` uniqueness model for idempotent streaming.
- Repository permissions, plans, multi-repo execution, source-location grouping, and script library concepts are already richer than a simple agent queue.
- Borg UI has a broader repository-management surface: checks, prune, compact, archive deletion, wipe workflows, restore checks, archive browsing, notifications, and plan-level failure behavior.

## Unsupported Or Incomplete Today

The following are current gaps for the managed-agent product:

- scheduled backup plans do not queue `AgentJob` work for agent-targeted repositories;
- agent job type support is limited to `backup.create`;
- remote-to-remote agent orchestration is not wired as a first-class flow;
- agent-side hooks/scripts are not supported;
- restore, check, prune, compact, archive delete, repository verify/init, and archive browse/catalog are not agent job contracts;
- terminal status report retry/backoff is missing;
- stale-running/abandoned job reconciliation is missing;
- cancellation terminates the immediate Borg process but does not guarantee full process-tree cleanup;
- endpoint packaging is limited to manual Python install plus service templates;
- Borg binary install/update and agent self-update are not supported;
- append-only SSH repository provisioning and server-managed agent repository credentials are not supported.

## Recommended Follow-Up Scope

BOR-39 should become the roadmap/design ticket for managed-agent orchestration support. Its acceptance criteria should require decisions on:

- the data-plane model: payload-path repositories, server-provisioned append-only SSH repositories, or both;
- backup-plan/manual parity for agent-targeted repositories;
- remote-to-remote backup behavior without server data hairpinning;
- which existing Borg UI capabilities must be reused rather than duplicated;
- durability requirements for final reports, cancellation, stale jobs, and process-tree cleanup;
- prioritized agent job kinds beyond `backup.create`;
- endpoint installer/package targets;
- security requirements for any self-update or Borg-binary management.

## Out Of Scope For BOR-38

BOR-38 is documentation and investigation only. It should not change runtime behavior, API contracts, database schema, UI, agent commands, or tests beyond documentation validation.
