# Scheduled Cloud Mirror Jobs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add repository cloud mirror schedules with recorded rclone sync jobs, next-run status, and UI visibility.

**Architecture:** Extend the existing rclone mirror storage row with schedule cadence and next-run fields, reuse `RcloneSyncJob` for observable attempts, dispatch due mirror syncs from the existing minute scheduler loop, and surface the schedule in the existing Cloud Mirror settings step and repository cards.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, croniter schedule utilities, React, MUI, lucide-react, Vitest, Storybook screenshots.

---

## File Structure

- Modify `app/database/models.py`: add schedule columns to `RepositoryStorage` and job-log columns to `RcloneSyncJob`.
- Add `app/database/migrations/114_add_scheduled_rclone_mirror_jobs.py`: idempotent SQLite/PostgreSQL-safe migration for the new columns and next-run index.
- Modify `app/services/rclone_repository_service.py`: serialize schedule fields, validate/apply scheduled policy, record manual/scheduled sync jobs, and preserve scheduled metadata during manual syncs.
- Add `app/services/rclone_mirror_scheduler.py`: query due rclone mirrors, create scheduled jobs, execute syncs, advance next run, and fail observable jobs on dispatch errors.
- Modify `app/api/repositories.py`: accept schedule fields for create/import/update, calculate next-run metadata, and pass schedule data into mirror storage.
- Modify `app/api/schedule.py`: call the rclone mirror scheduler from the existing minute loop.
- Modify `frontend/src/services/api.ts` and `frontend/src/types/index.ts`: expose schedule fields and latest job summaries.
- Modify `frontend/src/components/RepositoryWizard.tsx` and `frontend/src/components/wizard/WizardStepCloudMirror.tsx`: add scheduled cron/timezone form state and payload.
- Modify `frontend/src/components/RepositoryCard.tsx`: show scheduled mirror state and failures.
- Modify locale JSON files for new UI strings.
- Modify Storybook stories and snapshots for changed card/settings states.
- Add/update tests in `tests/unit/test_rclone_repository_service.py`, `tests/unit/test_api_rclone.py`, `tests/unit/test_api_schedule_routes.py`, `frontend/src/components/wizard/__tests__/WizardStepCloudMirror.test.tsx`, and repository card tests/stories.

## Task 1: Backend Schedule Contract

- [ ] Add failing service tests that scheduled mirror storage requires cron/timezone and serializes `sync_cron_expression`, `sync_timezone`, `next_scheduled_sync_at`, and `last_scheduled_sync_at`.
- [ ] Add failing API tests that create/update with `rclone_sync_policy: "scheduled"` persists the schedule and returns `next_scheduled_sync_at`.
- [ ] Add migration/model fields and schedule helper functions.
- [ ] Wire create/import/update validation so scheduled policy requires a cron expression and valid timezone.
- [ ] Run `pytest tests/unit/test_rclone_repository_service.py tests/unit/test_api_rclone.py -q`.

## Task 2: Job Recording And Scheduler Execution

- [ ] Add failing service tests that manual sync records a manual `RcloneSyncJob` without changing scheduled next-run metadata.
- [ ] Add failing scheduler tests that due scheduled mirrors create a scheduled job, call rclone sync, update last/next scheduled run fields, and record logs.
- [ ] Add failing scheduler tests that sync failure marks the job failed, preserves repository path/target metadata, advances next run, and stores `last_sync_error`.
- [ ] Implement `RcloneRepositoryService.sync_repository(..., triggered_by, scheduled_for)` job recording.
- [ ] Implement `run_due_scheduled_rclone_mirrors(db, now)` and call it from `check_scheduled_jobs`.
- [ ] Run `pytest tests/unit/test_rclone_repository_service.py tests/unit/test_api_rclone.py tests/unit/test_api_schedule_routes.py -q`.

## Task 3: Frontend Scheduled Settings

- [ ] Add failing Cloud Mirror tests that selecting Scheduled reveals cron/timezone fields and submits `rclone_sync_cron_expression` plus `rclone_sync_timezone`.
- [ ] Add failing edit-mode tests that scheduled mirror settings are pre-populated from `rclone_storage`.
- [ ] Implement types, wizard state, scheduled fields, validation, payload mapping, and locale strings.
- [ ] Add/update `WizardStepCloudMirror` Storybook scheduled state.
- [ ] Run targeted Vitest for Cloud Mirror and repository wizard tests.

## Task 4: Repository Card State

- [ ] Add failing repository card tests for next scheduled mirror, failed scheduled mirror, and missing next-run states.
- [ ] Implement compact scheduled mirror chip using existing MUI chip/tooltip/lucide patterns and no heavy accent border.
- [ ] Add/update `RepositoryCard.stories.tsx` scheduled mirror stories.
- [ ] Run targeted Vitest for repository card tests.
- [ ] Run `cd frontend && npm run snapshots` and keep generated screenshots under `frontend/storybook-snapshots/`.

## Task 5: Final Validation And Handoff

- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run targeted backend pytest paths for rclone service/API/scheduler.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run targeted frontend Vitest tests for scheduled mirror UI.
- [ ] Run a Borg UI runtime walkthrough or smoke runner proving schedule configuration and failure visibility.
- [ ] Commit, push, open/update PR with the repository template, attach it to Linear, add `symphony`, sweep feedback/checks, and move BOR-73 to Human Review only when green.

## Self-Review

- Acceptance coverage: schedule configuration is Task 1/3; status/log/next-run recording is Task 2; card/settings UI is Task 3/4; failure observability and metadata isolation are Task 2; tests and snapshots are Task 1-5.
- Scope check: this does not add a general backup schedule type or direct rclone mount support.
- UI check: the plan keeps Borg UI's dense operational dashboard pattern, uses lucide icons, balanced chip borders, and avoids left-accent status treatments.
