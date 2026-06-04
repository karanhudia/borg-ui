# Backup Retry Lineage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each behavior change. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add backend retry endpoints for supported backup jobs and backup plan runs with durable lineage records.

**Architecture:** Create explicit retry-lineage tables for jobs and plan runs, add lightweight retry metadata columns to created `BackupJob` and `BackupPlanRun` rows, and route retries through existing backup, agent, plan execution, permission, and admission helpers.

**Tech Stack:** FastAPI, SQLAlchemy models, additive SQLite/PostgreSQL migration helpers, pytest, ruff.

---

## Files

- Modify: `app/database/models.py`
- Add: `app/database/migrations/119_add_backup_retry_lineage.py`
- Modify: `app/api/backup.py`
- Modify: `app/api/backup_plans.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Modify: `tests/unit/test_api_backup.py`
- Modify: `tests/unit/test_api_backup_plans.py`
- Optional docs update: `docs/architecture/job-system.md` if the existing architecture page mentions retry support or job immutability.

## Task 1: Add Failing Backup Job Retry Tests

- [ ] Add `TestBackupRetry` in `tests/unit/test_api_backup.py`.
- [ ] Test local failed job retry:
  - Arrange a repository and a `BackupJob(status="failed")`.
  - Patch `app.api.backup.backup_service.execute_backup` and
    `app.api.backup.asyncio.create_task`.
  - POST `/api/backup/jobs/{job.id}/retry`.
  - Expect HTTP 202, a new pending job, source job still failed, no plan/schedule
    links, attempt 2, original/source ids, requester id, requested timestamp,
    one lineage row with created job id and snapshot.
- [ ] Run:
  `pytest tests/unit/test_api_backup.py::TestBackupRetry::test_retry_failed_local_backup_creates_new_job_with_lineage -q`
  and confirm it fails because the endpoint/model does not exist.
- [ ] Test agent failed job retry:
  - Arrange an agent repository, failed source `BackupJob(execution_mode="agent")`,
    and linked terminal `AgentJob` with backup payload.
  - Patch `dispatch_agent_job_best_effort`.
  - Expect a new pending agent backup job, queued `AgentJob`, source row unchanged,
    and lineage snapshot containing the reconstructed agent payload.
- [ ] Run the new agent test and confirm it fails for missing endpoint/model.
- [ ] Test active job rejection:
  - Arrange `BackupJob(status="running")`.
  - POST retry.
  - Expect 400 and no new job.
- [ ] Test permission rejection:
  - Arrange a viewer without operator access to the repository.
  - POST retry with viewer headers.
  - Expect 403 and no new job.

## Task 2: Add Failing Backup Plan Retry Tests

- [ ] Add retry tests near existing run/cancel tests in
  `tests/unit/test_api_backup_plans.py`.
- [ ] Test failed-only retry:
  - Arrange a plan with two repositories and a failed source run.
  - Mark one child failed and one child completed.
  - Patch `app.services.backup_plan_execution_service.asyncio.create_task` to
    close the coroutine.
  - POST `/api/backup-plans/runs/{run.id}/retry`.
  - Expect HTTP 202, new `BackupPlanRun(trigger="retry", status="pending")`,
    one child for the failed repository, source run still failed, attempt 2,
    and lineage snapshot with mode `failed_only`.
- [ ] Run the failed-only test and confirm it fails for missing endpoint/model.
- [ ] Test non-failed active run rejection:
  - Arrange `BackupPlanRun(status="running")`.
  - Expect 400 and no new run.
- [ ] Test active current plan rejection:
  - Arrange a failed source run plus another active run for the same plan.
  - Expect 409 and no new retry run.
- [ ] Test permission rejection for a viewer without operator access:
  - Expect 403 and no retry run.

## Task 3: Add Schema And Migration

- [ ] Add `BackupJobRetryLineage` and `BackupPlanRunRetryLineage` models in
  `app/database/models.py`.
- [ ] Add nullable metadata columns to `BackupJob`:
  - `retry_original_job_id`
  - `retry_source_job_id`
  - `retry_attempt`
  - `retry_requested_by_user_id`
  - `retry_requested_at`
- [ ] Add nullable metadata columns to `BackupPlanRun`:
  - `retry_original_run_id`
  - `retry_source_run_id`
  - `retry_attempt`
  - `retry_requested_by_user_id`
  - `retry_requested_at`
- [ ] Add migration `119_add_backup_retry_lineage.py` that:
  - Adds missing metadata columns idempotently.
  - Creates both lineage tables idempotently.
  - Creates useful indexes on original/source/created ids.
  - Supports SQLite and PostgreSQL timestamp/JSON/text differences using local
    migration helper functions.
- [ ] Run the first failing tests again; expected failure should move from model
  import/column errors to missing endpoint behavior.

## Task 4: Implement Backup Job Retry Endpoint

- [ ] In `app/api/backup.py`, import the lineage model and helper functions
  needed for agent payloads.
- [ ] Add small helpers:
  - terminal status predicate for `failed`/`cancelled`.
  - source job category validator that rejects scheduled, plan-child, and
    maintenance-only rows.
  - repository resolver by `repository_id` then path.
  - lineage attempt calculator using `source.retry_attempt or 1`.
  - request snapshot builder for local/remote/agent retry.
- [ ] Add `@router.post("/jobs/{job_id}/retry", status_code=202)`.
- [ ] Apply permission and admission checks before dispatch.
- [ ] Create the new `BackupJob` with pending status and retry metadata.
- [ ] For local/remote jobs, recalculate route fields, commit, and schedule
  `backup_service.execute_backup(...)` with the deterministic request data.
- [ ] For agent jobs, queue a linked `AgentJob`, persist lineage, commit, and
  call `dispatch_agent_job_best_effort`.
- [ ] Return the existing `BackupResponse` shape plus retry metadata fields.
- [ ] Run each `TestBackupRetry` test after the smallest implementation slice
  that should make it pass.

## Task 5: Implement Backup Plan Run Retry Endpoint

- [ ] In `app/services/backup_plan_execution_service.py`, add a
  `retry_failed_run(db, source_run, requested_by_user_id)` method.
- [ ] Method responsibilities:
  - reject non-failed source runs.
  - reject missing plan.
  - reject active run for the current plan.
  - select failed source child repositories where child status is failed or the
    linked backup job status is failed/cancelled.
  - intersect selected ids with enabled current plan repositories.
  - create a new `BackupPlanRun(trigger="retry", status="pending")`.
  - create child rows only for selected repositories.
  - create a `BackupPlanRunRetryLineage` row with failed-only snapshot.
  - dispatch existing `execute_run`.
- [ ] In `app/api/backup_plans.py`, add
  `@router.post("/runs/{run_id}/retry", status_code=202)` before the dynamic
  `/{plan_id}` routes.
- [ ] Use `_load_run_or_404`, `_require_run_operator_access`, and normal
  serialization.
- [ ] Run each backup plan retry test after the smallest implementation slice
  that should make it pass.

## Task 6: Serialize Retry Metadata

- [ ] Include retry metadata in backup job list/status serializers in
  `app/api/backup.py`.
- [ ] Include retry metadata in `_serialize_backup_job()` and
  `_serialize_plan_run()` in `app/api/backup_plans.py`.
- [ ] Keep request snapshots out of general API payloads.
- [ ] Run targeted serializer-adjacent tests:
  `pytest tests/unit/test_api_backup.py::TestBackupRetry tests/unit/test_api_backup_plans.py::TestBackupPlanRoutes -k retry -q`

## Task 7: Final Validation

- [ ] Run targeted tests:
  `pytest tests/unit/test_api_backup.py::TestBackupRetry tests/unit/test_api_backup_plans.py::TestBackupPlanRoutes -k retry -q`
- [ ] Run broader touched API tests if targeted tests pass:
  `pytest tests/unit/test_api_backup.py tests/unit/test_api_backup_plans.py -k 'retry or run_backup_plan or start_backup' -q`
- [ ] Run required checks:
  - `ruff check app tests`
  - `ruff format --check app tests`
- [ ] Update the Linear workpad with completed checklist items and validation
  evidence before committing/pushing.
