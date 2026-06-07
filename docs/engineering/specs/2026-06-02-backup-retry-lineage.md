# Backup Retry Lineage Spec

## Problem

Failed or cancelled backup jobs and failed backup plan runs are terminal history
rows, but Borg UI has no backend retry contract for creating a new attempt from
that history. Existing rows also lack durable retry lineage, attempt numbers,
requester metadata, and request snapshots for cases where a retry must
reconstruct a backup request.

## Desired Outcome

Add backend retry endpoints that create new job/run rows for supported terminal
backup work and record auditable lineage back to the original attempt. Source
rows remain terminal history rows. Retry must pass through the existing
repository admission and permission checks so retry cannot bypass active-work
controls.

## Scope

In scope:

- `POST /api/backup/jobs/{job_id}/retry` for terminal `failed` and `cancelled`
  manual backup jobs where Borg UI can deterministically reconstruct the request.
- Local/server, remote-direct, and agent-backed manual backup jobs.
- `POST /api/backup-plans/runs/{run_id}/retry` for failed backup plan runs.
- Failed-only backup plan retry, using the source run's failed repositories as
  the retry target set while executing against the current plan configuration.
- Durable lineage rows for backup jobs and backup plan runs.
- Lightweight attempt/original/source metadata on created `BackupJob` and
  `BackupPlanRun` rows for simple serialization and filtering.

Out of scope:

- UI retry controls.
- Generic retry for restore, check, compact, prune, archive delete, repository
  wipe, package install, or standalone maintenance jobs.
- Reopening or mutating terminal source rows back to active states.
- Retrying destructive archive delete, repository wipe, and standalone prune
  work.

## Retry Lineage Contract

Each retry creates a new row:

- Backup job retry creates a new `BackupJob(status="pending")`.
- Backup plan run retry creates a new `BackupPlanRun(status="pending")` and new
  `BackupPlanRunRepository` children for failed source repositories.

Each retry also creates a lineage row:

- `backup_job_retry_lineage`
- `backup_plan_run_retry_lineage`

Lineage fields:

- original source id: first attempt in the retry chain.
- retry source id: immediate terminal row being retried.
- attempt number: original attempt is 1; each retry increments from its source.
- requested by user id.
- requested timestamp.
- created job/run id.
- request snapshot JSON.

The created job/run duplicates the original/source/attempt/requester/timestamp
metadata so list/detail serializers can expose retry context without joining the
lineage table.

## Backup Job Retry Behavior

The endpoint accepts no body in this slice.

Supported source rows:

- `BackupJob.status in {"failed", "cancelled"}`.
- `scheduled_job_id is NULL`, `backup_plan_id is NULL`, and
  `backup_plan_run_id is NULL`.
- The repository still exists by `repository_id` or stored `repository` path.
- The job is not maintenance-only work, destructive work, or a plan child.

Request reconstruction:

- Repository identity comes from the source job's `repository_id` or
  `repository` path.
- Source selections, excludes, compression, flags, upload limits, and agent
  payload details come from the current repository record or the existing agent
  job payload when present.
- Route fields are recalculated from the current repository/source settings
  using existing route helpers.
- The lineage snapshot records the reconstructed request and the source job
  metadata used to build it.

Dispatch:

- Local/server and remote-direct jobs use the same async backup execution path
  as `/api/backup/start`.
- Agent jobs create a new linked `AgentJob` through existing queue helpers and
  dispatch best-effort.
- Admission checks run before creating queued work.

Rejections:

- 404 for missing source job.
- 400 for active or unsupported source status.
- 400 for unsupported job category or missing deterministic repository/request
  data.
- 403 from normal repository permission checks.
- 409 from admission or manual backup capacity checks.

## Backup Plan Run Retry Behavior

The endpoint accepts no body in this slice and always retries failed
repositories only.

Supported source rows:

- `BackupPlanRun.status == "failed"`.
- The source run still references an existing backup plan.
- At least one source run repository failed or has a failed linked backup job.

Retry creation:

- Permission checks use the existing run/plan operator rules.
- The current plan must have no active run.
- The new run uses `trigger="retry"` and has children only for failed source
  repositories that still belong to the current enabled plan.
- The lineage snapshot records failed-only mode, source run status, selected
  repository ids, skipped failed repository ids, and that the current plan
  configuration is used for execution.
- The retry dispatch uses the existing plan execution service.

Rejections:

- 404 for missing source run.
- 400 for non-failed source run status.
- 400 when no retryable failed repositories remain.
- 403 from normal plan/repository permission checks.
- 409 when the plan already has an active run.

## Serialization

Backup job and plan run responses include retry metadata:

- `retry_attempt`
- `retry_original_job_id` / `retry_original_run_id`
- `retry_source_job_id` / `retry_source_run_id`
- `retry_requested_by_user_id`
- `retry_requested_at`

The raw request snapshot stays in the lineage table and is not returned from
general list endpoints.

## Validation

Required validation:

- Unit tests for local backup retry.
- Unit tests for agent backup retry.
- Unit tests for failed-only backup plan run retry.
- Unit tests for active-job/active-run rejection.
- Unit tests for permission checks.
- Unit tests proving terminal source rows remain terminal and lineage preserves
  original/source/attempt/requester/timestamp/created id/snapshot data.
- `ruff check app tests`
- `ruff format --check app tests`
- Targeted pytest paths for retry tests.
