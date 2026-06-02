# Job Concurrency Controls Investigation And Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement future slices from this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Document the job concurrency controls Borg UI already supports, identify gaps around retry and capacity control, and define the safest order for follow-up implementation.

**Architecture:** Treat retry and concurrency as job-control contracts instead of ad hoc buttons on existing history rows. Add durable retry lineage and DB-backed operation admission before expanding UI actions, because the current system mixes in-memory tasks, per-table status checks, agent queues, and scheduler loops.

**Tech Stack:** FastAPI, SQLAlchemy, asyncio background tasks, SQLite migrations, pytest, React, TanStack Query, MUI.

---

## Source Map

- Job models and settings: `app/database/models.py`
- Manual backup API and cancellation: `app/api/backup.py`
- Restore API and cancellation: `app/api/restore.py`
- Legacy scheduled backup dispatch: `app/api/schedule.py`
- Scheduled check dispatch: `app/services/check_scheduler.py`
- Scheduled restore-check dispatch: `app/services/restore_check_scheduler.py`
- Maintenance job helper: `app/api/maintenance_jobs.py`
- Repository maintenance routes and running-job summary: `app/api/repositories.py`
- Backup plan routes: `app/api/backup_plans.py`
- Backup plan execution service: `app/services/backup_plan_execution_service.py`
- Agent job API and queue helpers: `app/api/agents.py`, `app/services/repository_executor.py`
- Archive delete jobs: `app/api/archives.py`
- Package install jobs: `app/api/packages.py`
- Startup cleanup: `app/utils/process_utils.py`
- Frontend API helpers and job actions: `frontend/src/services/api.ts`, `frontend/src/components/BackupJobsTable.tsx`, `frontend/src/components/BackupPlanRunsPanel.tsx`
- Existing architecture note: `docs/architecture/job-system.md`

## Reproduction Signal

Retry is not currently supported as a job action. A strict endpoint/API-helper search found no retry or rerun routes:

```bash
rg -n "@router\\.(post|put|patch)\\(\"[^\"]*(retry|rerun)|api\\.(post|put|patch)\\([^\\n]*(retry|rerun)" app/api app/api/v2 frontend/src/services/api.ts -S
```

The command exits `1` with no output. The only backend "original_job_id" search hit is schedule duplication naming in `app/api/schedule.py`; it is not retry lineage.

## Supported Today

### Job lifecycle persistence

Most long-running work persists a row with `status`, timestamps, logs, and progress fields:

- `BackupJob`, `RestoreJob`, `CheckJob`, `RestoreCheckJob`, `CompactJob`, `PruneJob`, `DeleteArchiveJob`, `RepositoryWipeJob`, `PackageInstallJob`, `AgentJob`, `BackupPlanRun`, and `BackupPlanRunRepository`.
- The common statuses are `pending`, `running`, `completed`, `failed`, and `cancelled` or `canceled`, with extra warning/partial states for backup-plan and wipe flows.
- There are no retry count, retry lineage, idempotency key, queued-by, or original payload snapshot fields on these job tables.

### Async execution

- Manual backups create a `BackupJob(status="pending")` and then start a local `asyncio.create_task(...)` or enqueue an `AgentJob` for agent-backed repositories (`app/api/backup.py:224`, `app/api/backup.py:253`, `app/api/backup.py:269`).
- Restores create a `RestoreJob(status="pending")` and start an async restore task (`app/api/restore.py:177`, `app/api/restore.py:193`).
- Repository maintenance work uses `start_background_maintenance_job(...)`, which checks for a running same-type job, creates a new job row, and schedules the dispatcher (`app/api/maintenance_jobs.py:128`).
- Agent jobs have a queue-like protocol: poll queued jobs, claim, start, progress/log, complete/fail/cancel (`app/api/agents.py:1009`, `app/api/agents.py:1028`, `app/api/agents.py:1047`, `app/api/agents.py:1144`, `app/api/agents.py:1178`, `app/api/agents.py:1218`).

### Cancellation

- Manual backup cancellation is supported for local running backup jobs, agent backup jobs, and backup jobs currently in prune/compact maintenance (`app/api/backup.py:452`).
- Restore cancellation is supported only for `RestoreJob.status == "running"` (`app/api/restore.py:343`).
- Backup plan run cancellation marks the run and pending/running child repositories cancelled and terminates running child backup work where possible (`app/api/backup_plans.py:1204`, `app/services/backup_plan_execution_service.py:448`).
- Agent jobs can be requested for cancel from the managed-machine API and acknowledged by the agent API (`app/api/managed_machines.py:540`, `app/api/agents.py:1218`).
- Archive delete cancellation has a dedicated endpoint (`app/api/archives.py:496`).
- Repository wipe has preview/queued cancellation but not a general process-kill contract (`app/api/repositories.py:5306`).

### Capacity and duplicate controls

- Legacy scheduled backups use `SystemSettings.max_concurrent_scheduled_backups`, defaulting to 2, and an in-memory active scheduled-backup task set (`app/api/schedule.py:151`, `app/api/schedule.py:2673`).
- Scheduled checks use `SystemSettings.max_concurrent_scheduled_checks`, defaulting to 4, and count DB rows in scheduled `pending` or `running` states after cleaning stale scheduled checks (`app/services/check_scheduler.py:37`, `app/services/check_scheduler.py:85`, `app/services/check_scheduler.py:104`).
- Backup plans support per-plan active-run blocking and repository-level series/parallel execution with `max_parallel_repositories` (`app/api/backup_plans.py:1389`, `app/services/backup_plan_execution_service.py:437`, `app/services/backup_plan_execution_service.py:841`).
- Repository maintenance routes block another running job of the same type on the same repository (`app/api/maintenance_jobs.py:44`).
- Archive deletion blocks another running delete for the same repository/archive (`app/api/archives.py:305`).
- Package install returns the existing pending/installing job for the same package (`app/api/packages.py:106`).

### Restart cleanup

On application startup, active backup jobs, restore jobs, check jobs, restore-check jobs, prune jobs, compact jobs, and backup-plan runs are normalized to failed, partial, cancelled, or completed states based on recorded children. Local check/compact orphan cleanup may break Borg locks; remote locks are left for manual handling (`app/main.py:353`, `app/utils/process_utils.py:279`, `app/utils/process_utils.py:354`, `app/utils/process_utils.py:381`, `app/utils/process_utils.py:566`).

## Unsupported Or Partial Today

- Retry and rerun are not first-class job actions. Terminal rows are immutable history rows, and the app has no endpoint to retry failed/cancelled jobs with lineage.
- Manual backup concurrency is not enforced. `SystemSettings.max_concurrent_backups` is stored, returned, and validated, but no backend code consumes it outside settings tests and settings serialization.
- The scheduled backup capacity control is process-local because it depends on an in-memory active task set. It is not durable across multiple server processes.
- Scheduled backup plans have a per-plan active-run guard, but no global scheduled-plan capacity limit. A plan with `repository_run_mode="parallel"` can fan out independently from legacy scheduled backup capacity.
- Scheduled restore checks have no shared capacity setting. They rely on the same-type per-repository running-job guard from the maintenance helper.
- The same-type maintenance guard checks only `status == "running"`. Rapid duplicate requests or agent-backed operations can create multiple pending same-type jobs before a worker marks one running.
- There is no cross-operation repository admission control. A check, compact, prune, restore-check, backup, archive delete, and wipe can be admitted independently until Borg locks or operation-specific guards fail later.
- Cancellation coverage is uneven. Check, restore-check, compact, and prune jobs do not have top-level route-specific cancel endpoints, even though some services can terminate prune/compact when they are child maintenance work for a backup.
- The frontend has action concepts for run now, cancel, delete, and lock breaking, but no retry action for terminal job rows. Scheduled `Run Now` creates a new scheduled execution, not a retry of a failed job.
- Job payload reconstruction is not consistently possible. For example, a manual `BackupJob` records the repository and archive metadata, but not a complete request snapshot for source overrides, exclusions, compression, or route options. Backup plan runs can be recreated from the current plan, but that may differ from the historical failed run.

## Recommendation

Do not start by adding a generic "Retry" button that mutates terminal job rows. Implement retries as new job/run rows with lineage, and tighten admission control at the same time so retries cannot amplify duplicate or conflicting work.

The safest first product slice is:

1. Add manual retry for terminal backup jobs and backup plan runs, creating new rows linked to the original.
2. Enforce DB-backed active admission for backup retries and same-type repository jobs.
3. Add UI retry actions only where the backend can reconstruct a deterministic payload and explain disabled states.

Destructive jobs should be excluded from the first slice:

- Archive delete
- Repository wipe
- Prune when it is not part of an explicit backup plan policy

These jobs can be retried later after we define operation-specific safety rules and user confirmation copy.

## Future Implementation Plan

### Task 1: Define A Durable Retry Contract

**Files:**

- Modify: `app/database/models.py`
- Add: `app/database/migrations/<next>_add_job_retry_lineage.py`
- Modify: `docs/architecture/job-system.md`
- Test: `tests/unit/test_job_retry_contract.py`

- [ ] Add retry metadata to retryable tables or a shared `job_retry_attempts` table.
  - Required fields: `job_type`, `original_job_id`, `retry_of_job_id`, `attempt_number`, `created_job_id`, `requested_by_user_id`, `requested_at`, `request_snapshot_json`.
  - Keep terminal source rows immutable.
- [ ] Store retry request snapshots before exposing retry.
  - For manual backup retry, snapshot repository id/path, source selections, exclusions, compression, archive template/name strategy, route strategy, executor type, and source SSH connection.
  - For backup-plan retry, snapshot the run mode: `failed_only` or `all_repositories`, plus the source run id.
- [ ] Document that retry creates a new job/run. It must not reopen or rewrite terminal history rows.
- [ ] Add tests proving attempt numbers increment and terminal source rows are unchanged.

### Task 2: Add DB-Backed Admission For Active Work

**Files:**

- Modify: `app/api/maintenance_jobs.py`
- Modify: `app/api/backup.py`
- Modify: `app/api/schedule.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Add: `app/services/job_admission.py`
- Add: `app/database/migrations/<next>_add_job_admission_locks.py`
- Test: `tests/unit/test_job_admission.py`
- Test: `tests/unit/test_schedulers.py`

- [ ] Create a small admission layer with active locks keyed by `resource_type`, `resource_id`, and `operation_class`.
  - Operation classes should distinguish write operations from read/check operations.
  - Active locks should cover `pending`, `queued`, `claimed`, `cancel_requested`, and `running` states, not just running.
- [ ] Replace same-type maintenance guards with admission checks that atomically reject duplicate active same-type operations.
- [ ] Decide and encode cross-operation conflicts.
  - Repository write operations should block other repository write operations.
  - Read operations may run concurrently only when Borg lock semantics and repository mode allow it.
  - Agent operations need the same admission rules before creating an `AgentJob`.
- [ ] Either enforce `max_concurrent_backups` for manual backups or remove it from API/settings docs. Preferred behavior is enforcement through the admission layer.
- [ ] Move legacy scheduled backup capacity from an in-memory set to DB-backed active job counting.

### Task 3: Implement Backup Retry Backend

**Files:**

- Modify: `app/api/backup.py`
- Modify: `app/services/backup_service.py`
- Modify: `app/services/repository_executor.py`
- Add: `app/services/job_retry.py`
- Test: `tests/unit/test_api_backup.py`
- Test: `tests/unit/test_agent_job_dispatcher.py`

- [ ] Add `POST /api/backup/jobs/{job_id}/retry`.
- [ ] Allow retry only for terminal failed or cancelled backup jobs where Borg UI can reconstruct a complete request snapshot.
- [ ] Reject retry for active jobs, unknown repositories, missing permissions, and destructive maintenance-only rows.
- [ ] For local/server backups, create a new `BackupJob(status="pending")`, attach retry lineage, then dispatch through the existing backup execution path.
- [ ] For agent backups, create a new `BackupJob` and `AgentJob` with retry lineage and dispatch through `dispatch_agent_job_best_effort`.
- [ ] Add tests for local retry, agent retry, active-job rejection, permission checks, and lineage preservation.

### Task 4: Implement Backup Plan Retry Backend

**Files:**

- Modify: `app/api/backup_plans.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Test: `tests/unit/test_api_backup_plans.py`

- [ ] Add `POST /api/backup-plans/runs/{run_id}/retry`.
- [ ] Support `failed_only` first; add `all_repositories` only after the failed-only path is stable.
- [ ] Use the source run repositories to choose retry targets, but execute through the current plan only after clearly recording that current plan config is used.
- [ ] Reject retry when the plan already has an active run.
- [ ] Preserve run lineage from the retry run back to the source run.
- [ ] Add tests for failed-only retry, all-terminal-no-fail rejection, active-run rejection, and cancellation interaction.

### Task 5: Add UI Retry Actions

**Files:**

- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/BackupJobsTable.tsx`
- Modify: `frontend/src/components/BackupPlanRunsPanel.tsx`
- Modify: `frontend/src/pages/Backup.tsx`
- Modify: `frontend/src/pages/BackupPlans.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`
- Add or modify Storybook stories for changed job rows and plan runs.
- Test: relevant Vitest tests under `frontend/src/components/__tests__/` and `frontend/src/pages/__tests__/`.

- [ ] Add retry API helpers for backup jobs and backup plan runs.
- [ ] Show retry only for retryable terminal statuses.
- [ ] Keep scheduled `Run Now` visually distinct from retry.
- [ ] Add disabled tooltips when retry is blocked by active work, missing payload snapshot, unsupported job type, or insufficient permission.
- [ ] Add Storybook coverage for retryable failed job, non-retryable destructive job, and retryable failed backup-plan run.

### Task 6: Validate End To End

**Backend checks:**

- [ ] `pytest tests/unit/test_job_admission.py -q`
- [ ] `pytest tests/unit/test_api_backup.py -k retry -q`
- [ ] `pytest tests/unit/test_api_backup_plans.py -k retry -q`
- [ ] `pytest tests/unit/test_schedulers.py -k concurrency -q`
- [ ] `ruff check app tests`
- [ ] `ruff format --check app tests`

**Frontend checks:**

- [ ] `cd frontend && npm run check:locales`
- [ ] `cd frontend && npm run typecheck`
- [ ] `cd frontend && npm run lint`
- [ ] `cd frontend && npm run build`
- [ ] Relevant Vitest retry-action tests.
- [ ] Storybook story updates for changed job/run states.

**Runtime walkthrough:**

- [ ] Start Borg UI locally.
- [ ] Create a backup job that fails deterministically.
- [ ] Retry it from the UI and verify a new job appears with a lineage indicator while the source job remains terminal.
- [ ] Attempt a second retry while the retry job is active and verify the backend rejects or disables it according to the admission contract.
- [ ] Cancel a backup plan run and retry failed-only children.

## Immediate Follow-Up Issues

Create separate implementation tickets instead of expanding BOR-115:

- Add DB-backed job admission and enforce manual backup concurrency.
- Add retry lineage plus backend retry endpoints for backup jobs and backup plan runs.
- Add frontend retry actions for supported terminal jobs after backend retry contracts exist.

## Self-Review

- The plan preserves the ticket scope by documenting current support and proposing follow-up implementation instead of changing runtime behavior.
- No unsupported retry claim is made; the reproduction signal is a route/API helper search with no matches.
- Capacity support is separated by actual enforcement source: settings-only, in-memory, DB-counted, and per-plan/per-repository controls.
- Destructive operations are explicitly excluded from the first retry slice to avoid unsafe duplicate delete or wipe behavior.
