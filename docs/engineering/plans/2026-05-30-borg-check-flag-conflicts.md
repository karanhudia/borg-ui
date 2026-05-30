# Borg Check Flag Conflict Guidance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement behavior changes test-first. Track progress in the BOR-97 Linear workpad.

**Goal:** Guard and explain unsupported Borg check flag combinations across manual checks, scheduled checks, and backup-plan maintenance.

**Architecture:** Share conflict detection in small backend/frontend helpers, reject invalid API payloads, preserve unlimited scheduled checks, and show inline UI warnings that steer users to `max_duration: 0`.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, MUI, React Query, Vitest, Storybook.

---

### Task 1: Backend Red Tests

**Files:**
- Modify: `tests/unit/test_api_repositories.py`
- Modify: `tests/unit/test_schedulers.py`
- Modify: `tests/unit/test_api_backup_plans.py`
- Modify: `tests/unit/test_api_v2_repositories.py` or `tests/unit/test_v2_services.py`

- [ ] Add a manual repository check test that posts `check_extra_flags: "--verify-data"` with `max_duration: 600` and expects HTTP 422.
- [ ] Add a repository schedule update test that posts `check_extra_flags: "--verify-data"` with `max_duration: 3600` and expects HTTP 422.
- [ ] Add or update a schedule dispatch test that stores `check_max_duration=0` with `check_extra_flags="--verify-data"` and expects the created `CheckJob.max_duration` to stay `0`.
- [ ] Add a backup plan payload test that rejects `run_check_after=true`, `check_extra_flags="--repair"`, and `check_max_duration=3600`.
- [ ] Run targeted pytest commands and confirm the new assertions fail against current behavior.

### Task 2: Backend Implementation

**Files:**
- Create: `app/services/check_flag_validation.py`
- Modify: `app/api/repositories.py`
- Modify: `app/api/v2/backups.py`
- Modify: `app/api/backup_plans.py`
- Modify: `app/services/check_scheduler.py`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Add `FULL_CHECK_REQUIRED_FLAGS`, conflict detection, and a `CheckFlagConflictError`.
- [ ] Map conflicts to HTTP 422 with `backend.errors.repo.checkFlagsRequireUnlimitedDuration`.
- [ ] Validate manual v1/v2 check requests before jobs are created or queued.
- [ ] Validate repository check schedule updates after merging request fields with persisted values.
- [ ] Validate backup plan create/update when `run_check_after` is enabled.
- [ ] Preserve scheduled `check_max_duration=0` instead of using the `or 3600` fallback.
- [ ] Add the backend locale error key in every locale file.
- [ ] Run targeted backend tests and confirm they pass.

### Task 3: Frontend Red Tests

**Files:**
- Modify: `frontend/src/components/__tests__/CheckWarningDialog.test.tsx`
- Modify: `frontend/src/components/__tests__/ScheduledChecksSection.test.tsx`
- Add or modify: backup plan schedule-step test coverage

- [ ] Add a manual check dialog test that enters `--verify-data` with a positive duration, expects conflict guidance, and expects submit disabled.
- [ ] Add a manual check dialog test that uses `maxDuration=0` with `--verify-data`, expects no conflict warning, and allows submit.
- [ ] Add a scheduled check test that confirms duration input allows `0` and conflict guidance clears at `0`.
- [ ] Add a backup plan schedule/maintenance test that renders a conflicting maintenance check and confirms the warning appears.
- [ ] Run targeted Vitest commands and confirm they fail before UI implementation.

### Task 4: Frontend Implementation

**Files:**
- Create: `frontend/src/utils/checkFlagConflicts.ts`
- Modify: `frontend/src/components/CheckWarningDialog.tsx`
- Modify: `frontend/src/components/ScheduledChecksSection.tsx`
- Modify: `frontend/src/pages/BackupPlans.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/ScheduleStep.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Add frontend full-check flag detection and conflict formatting.
- [ ] Show inline warning alerts on all three affected UI surfaces.
- [ ] Allow `0` in scheduled check max duration and update helper text to describe unlimited/full check mode.
- [ ] Disable manual confirm, scheduled update, and backup plan schedule progression while conflicts are present.
- [ ] Add or update all locale keys required by the UI.
- [ ] Run targeted frontend tests and confirm they pass.

### Task 5: Storybook and Snapshots

**Files:**
- Modify: `frontend/src/components/CheckWarningDialog.stories.tsx`
- Add: `frontend/src/pages/backup-plans/wizard-step/ScheduleStep.stories.tsx`
- Update: `frontend/storybook-snapshots/*`

- [ ] Add a manual check warning story with positive duration plus `--verify-data`.
- [ ] Add a backup plan schedule step story showing the maintenance warning.
- [ ] Run `cd frontend && npm run snapshots` and keep the updated screenshots.

### Task 6: Required Validation, Publish, and Handoff

**Commands:**
- `pytest tests/unit/test_api_repositories.py::TestRepositoryCheckSchedule tests/unit/test_schedulers.py::test_check_scheduler_creates_job_and_updates_next_run tests/unit/test_api_backup_plans.py::TestBackupPlanRoutes`
- `ruff check app tests`
- `ruff format --check app tests`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `cd frontend && npm run snapshots`

- [ ] Run targeted and required validation.
- [ ] Capture runtime walkthrough evidence for the changed configuration paths.
- [ ] Commit, push, create PR from `.github/PULL_REQUEST_TEMPLATE.md`, attach it to Linear, and add the `symphony` PR label.
- [ ] Sweep PR comments and checks, then move Linear to Human Review only when complete.
