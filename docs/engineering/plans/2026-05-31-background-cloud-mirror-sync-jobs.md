# Background Cloud Mirror Sync Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save repository cloud mirror edits immediately while running initial rclone sync work in the background and surfacing cloud storage sync/hydrate jobs in Activity.

**Architecture:** Reuse `RcloneSyncJob` for cloud storage job persistence, add an `operation` discriminator for sync versus hydrate, enqueue `after_success` edit-mode initial syncs as pending background jobs, and extend existing Activity/job UI components to show rclone jobs with logs and active progress cards.

**Tech Stack:** FastAPI, SQLAlchemy, asyncio background tasks, pytest, React, MUI, lucide-react, TanStack Query, Vitest, Storybook screenshots.

---

## File Structure

- Modify `app/database/models.py`: add `RcloneSyncJob.operation` with default `sync`.
- Add `app/database/migrations/117_add_rclone_sync_job_operation.py`: idempotently add the `operation` column for existing installs.
- Modify `app/services/rclone_repository_service.py`: support pending job execution, enqueue background sync jobs, record hydrate jobs, and preserve current sync status transitions.
- Modify `app/api/repositories.py`: replace update-mode awaited `sync_repository` call with background job enqueueing.
- Modify `app/api/activity.py`: include rclone sync/hydrate jobs in recent Activity and wire log fetch/download/delete support.
- Modify `tests/unit/test_api_rclone.py`, `tests/unit/test_rclone_repository_service.py`, and `tests/unit/test_api_activity.py`: add failing backend coverage before implementation.
- Modify `frontend/src/pages/Activity.tsx`: render active cloud storage job progress cards and add rclone filters.
- Add `frontend/src/components/RunningCloudStorageJobsSection.tsx`: compact active-job progress surface for rclone sync/hydrate work.
- Add `frontend/src/components/RunningCloudStorageJobsSection.stories.tsx`: Storybook state for active rclone work.
- Modify `frontend/src/components/BackupJobsTable.tsx`: label/color rclone job types.
- Modify `frontend/src/components/shared/LogViewerDialog.tsx`: label rclone sync/hydrate logs.
- Modify `frontend/src/types/jobs.ts` and locale JSON files: document/add rclone activity type strings.
- Add or modify frontend tests under `frontend/src/components/__tests__/` and `frontend/src/pages/__tests__/`.

## Task 1: Backend Red Tests For Save Behavior

- [ ] Add `test_update_local_repository_cloud_mirror_default_policy_queues_initial_sync_job_without_awaiting_sync` in `tests/unit/test_api_rclone.py`.
  - Arrange a local repository and rclone remote.
  - Patch `app.services.rclone_repository_service.rclone_service.lsjson` to return an empty remote path listing.
  - Patch `app.api.repositories.rclone_repository_service.sync_repository` with an `AsyncMock` that raises if awaited.
  - Patch `app.api.repositories.asyncio.create_task` to capture and close the scheduled coroutine.
  - Send `PUT /api/repositories/{id}` with cloud mirror enabled and default/`after_success` policy.
  - Assert HTTP 200, one pending `RcloneSyncJob(triggered_by="initial", operation="sync")`, mirror `sync_status=="pending"`, one background task scheduled, and `sync_repository` not awaited by the request.
- [ ] Add a parametrized API test for `manual` and `scheduled` policies.
  - Reuse the same repository and rclone remote setup.
  - Patch `sync_repository` to raise if awaited and patch `create_task` to record calls.
  - Send the update with `rclone_sync_policy` set to the policy under test.
  - Assert HTTP 200, no initial pending `RcloneSyncJob`, no background task, and `sync_repository` not awaited.
- [ ] Run `pytest tests/unit/test_api_rclone.py -k "cloud_mirror_default_policy_queues_initial_sync_job or manual_or_scheduled" -q`.
  - Expected before implementation: fail because update still awaits sync and `RcloneSyncJob.operation` does not exist.

## Task 2: Backend Red Tests For Activity And Hydrate Visibility

- [ ] Add Activity API tests in `tests/unit/test_api_activity.py`.
  - Create repository rows and `RcloneSyncJob` rows for `operation="sync"` and `operation="hydrate"`.
  - Assert `/api/activity/recent` returns `type=="rclone_sync"` and `type=="rclone_hydrate"` entries with repository context and errors/log flags.
  - Assert `GET /api/activity/rclone_sync/{id}/logs` returns `log_text` plus `error_text` fallback content.
  - Assert `GET /api/activity/rclone_hydrate/{id}/logs/download` returns a text attachment.
- [ ] Add a hydrate service test in `tests/unit/test_rclone_repository_service.py`.
  - Patch the rclone copy operation to succeed without external IO.
  - Call `hydrate_repository`.
  - Assert a completed `RcloneSyncJob(operation="hydrate")` is recorded.
- [ ] Run `pytest tests/unit/test_api_activity.py -k rclone -q` and the hydrate service test.
  - Expected before implementation: fail because Activity omits rclone jobs and hydrate does not create job rows.

## Task 3: Implement Backend Job Flow

- [ ] Add the model field and migration.
  - Use `Column(String, default="sync", nullable=False)` on `RcloneSyncJob`.
  - In migration `117_add_rclone_sync_job_operation.py`, add `operation VARCHAR DEFAULT 'sync' NOT NULL` if missing.
- [ ] Add pending job helpers in `app/services/rclone_repository_service.py`.
  - `enqueue_repository_sync_job(db, repository, triggered_by="initial")` creates a pending sync job, marks mirror storage pending, commits, and schedules background execution.
  - `_run_background_sync_job(job_id)` opens `SessionLocal`, reloads the job/repository, and calls `sync_repository(..., job_id=job_id, triggered_by=job.triggered_by, scheduled_for=job.scheduled_for)`.
  - `sync_repository(..., job_id=None, operation="sync")` reuses an existing pending job when `job_id` is provided, otherwise creates the current running job.
- [ ] Replace `await rclone_repository_service.sync_repository(db, repository)` in `update_repository` with the enqueue helper when `sync_cloud_mirror_after_update` is true.
- [ ] Record hydrate jobs in `hydrate_repository`, updating status/log/error timestamps through the same success/failure paths as sync jobs.
- [ ] Extend `app/api/activity.py`.
  - Add rclone job query sections for `rclone_sync` and `rclone_hydrate`.
  - Add log fetch/download support for both rclone types using `log_text` and `error_text`.
  - Add delete support with type-to-operation validation.
- [ ] Run the backend targeted tests from Task 1 and Task 2 until they pass.

## Task 4: Frontend Red Tests And UI

- [ ] Add failing tests for rclone labels and active cloud storage jobs.
  - In `frontend/src/components/__tests__/LogViewerDialog.test.tsx`, assert rclone sync/hydrate jobs render cloud storage titles.
  - Add `frontend/src/components/__tests__/RunningCloudStorageJobsSection.test.tsx` covering pending/running sync and hydrate cards.
  - Update `frontend/src/pages/__tests__/Activity.test.tsx` so mocked Activity data with active rclone jobs renders the new progress section and rclone filter options.
- [ ] Run the targeted Vitest tests before implementation.
  - Expected before implementation: fail because labels, component, and filters do not exist.
- [ ] Implement `RunningCloudStorageJobsSection`.
  - Use MUI `Card`, `Stack`, `Chip`, `LinearProgress`, existing `StatusBadge`, and lucide cloud icons.
  - Render only active `pending` or `running` rclone jobs.
  - Keep balanced full outlines and compact metadata; no heavy left borders.
- [ ] Update `Activity.tsx`.
  - Add filter options for Cloud sync and Cloud hydrate.
  - Render active rclone progress cards above `BackupJobsTable`.
  - Keep log viewing routed through existing shared `LogViewerDialog`.
- [ ] Update `BackupJobsTable`, `LogViewerDialog`, `types/jobs.ts`, and locale JSON files for `rclone_sync` and `rclone_hydrate`.
- [ ] Add `RunningCloudStorageJobsSection.stories.tsx` with pending sync, running hydrate, and failed/error-adjacent context where useful.
- [ ] Run targeted Vitest tests until they pass.
- [ ] Run `cd frontend && npm run snapshots` and keep generated files under `frontend/storybook-snapshots/`.

## Task 5: Required Validation And Runtime Proof

- [ ] Run targeted backend tests:
  - `pytest tests/unit/test_api_rclone.py -k "cloud_mirror_default_policy_queues_initial_sync_job or manual_or_scheduled" -q`
  - `pytest tests/unit/test_api_activity.py -k rclone -q`
  - relevant hydrate test path from `tests/unit/test_rclone_repository_service.py`
- [ ] Run required backend checks:
  - `ruff check app tests`
  - `ruff format --check app tests`
- [ ] Run targeted frontend tests:
  - `cd frontend && npm run test -- RunningCloudStorageJobsSection LogViewerDialog Activity --run`
- [ ] Run required frontend checks:
  - `cd frontend && npm run check:locales`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build`
- [ ] Run a Borg UI app walkthrough using the available local runner.
  - Enable a cloud mirror in repository edit mode.
  - Save and verify the dialog returns promptly.
  - Verify repository card status shows pending/syncing and Activity shows the rclone job.
- [ ] Run PR feedback sweep, verify checks, update the Linear workpad handoff note, and move BOR-105 to Human Review only after completion criteria are met.

## Self-Review

- Acceptance coverage: save-without-await is Task 1/3; policy-specific no-op behavior is Task 1/3; cloud job visibility is Task 2/3/4; repository card status preservation is Task 3 plus runtime proof; Activity/progress UI is Task 4; validation is Task 5.
- Scope check: the plan does not add a new Activity route or alter scheduled cadence behavior. It reuses existing Activity and job table patterns.
- TDD check: runtime implementation steps are blocked behind explicit failing backend and frontend tests.
- UI check: the plan uses Borg UI's existing operational table/log patterns and a compact progress card with icons, chips, and balanced borders.
