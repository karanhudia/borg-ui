# Borg Check Extra Flags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add advanced Borg `check` flag support across manual repository checks, scheduled checks, and backup plan maintenance checks.

**Architecture:** Store check-specific flag text on repository schedule defaults, backup plan defaults, and the check job that actually runs. APIs accept/return `check_extra_flags`; execution parses with `shlex.split` and appends arguments to Borg 1 and Borg 2 check commands without using a shell.

**Tech Stack:** FastAPI, SQLAlchemy models/migrations, pytest, React, MUI, React Query, Vitest, Storybook.

---

### Task 1: Backend RED Tests

**Files:**
- Modify: `tests/unit/test_api_repositories.py`
- Modify: `tests/unit/test_schedulers.py`
- Modify: `tests/unit/test_api_backup_plans.py`
- Modify: `tests/unit/test_v2_services.py`

- [ ] Add failing tests asserting manual repository checks, scheduled checks, scheduled dispatch, backup plan maintenance, and Borg 2 checks preserve `check_extra_flags` / `extra_flags`.
- [ ] Run the targeted pytest commands and confirm they fail because the fields do not exist yet.

### Task 2: Backend Implementation

**Files:**
- Modify: `app/database/models.py`
- Create: `app/database/migrations/107_add_check_extra_flags.py`
- Modify: `app/api/repositories.py`
- Modify: `app/api/v2/backups.py`
- Modify: `app/api/backup_plans.py`
- Modify: `app/services/check_scheduler.py`
- Modify: `app/services/check_service.py`
- Modify: `app/services/v2/check_service.py`
- Modify: `app/services/backup_plan_execution_service.py`

- [ ] Add `check_extra_flags` columns to repositories and backup plans, and `extra_flags` to check jobs.
- [ ] Accept, trim, persist, serialize, and propagate `check_extra_flags` through repository schedule and backup plan APIs.
- [ ] Copy configured flags into `CheckJob.extra_flags` when jobs are created from manual, scheduled, Borg 2, or backup-plan maintenance flows.
- [ ] Parse and append check flags to Borg 1 and Borg 2 command argument lists.
- [ ] Run the targeted backend tests and confirm they pass.

### Task 3: Frontend RED Tests

**Files:**
- Modify: `frontend/src/services/borgApi/client.test.ts`
- Modify: `frontend/src/components/__tests__/ScheduledChecksSection.test.tsx`
- Modify: `frontend/src/pages/__tests__/BackupPlans.test.tsx`

- [ ] Add failing tests for check client payloads, scheduled check form submission, and backup plan payload trimming.
- [ ] Run targeted Vitest commands and confirm they fail before UI/client implementation.

### Task 4: Frontend Implementation

**Files:**
- Modify: `frontend/src/services/borgApi/client.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/CheckWarningDialog.tsx`
- Modify: `frontend/src/components/ScheduledChecksSection.tsx`
- Modify: `frontend/src/components/ScheduleCheckCard.tsx`
- Modify: `frontend/src/pages/Repositories.tsx`
- Modify: `frontend/src/pages/backup-plans/state.ts`
- Modify: `frontend/src/utils/backupPlanPayload.ts`
- Modify: `frontend/src/pages/backup-plans/wizard-step/ScheduleStep.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/ReviewStep.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Extend types and payload builders with `checkExtraFlags` / `check_extra_flags`.
- [ ] Add labeled advanced check flag fields to the manual check dialog, scheduled check dialog, and backup plan maintenance check section.
- [ ] Display configured scheduled and plan check flags in compact review/card surfaces.
- [ ] Update locale keys in all locale files.
- [ ] Run targeted frontend tests and confirm they pass.

### Task 5: Storybook and Snapshots

**Files:**
- Create: `frontend/src/components/CheckWarningDialog.stories.tsx`
- Update: `frontend/storybook-snapshots/*`

- [ ] Add a Storybook story for the manual check dialog with advanced check flags populated.
- [ ] Run `cd frontend && npm run snapshots` and commit the generated screenshot.

### Task 6: Required Validation and Handoff

**Commands:**
- `pytest tests/unit/test_api_repositories.py::TestRepositoryCheckSchedule tests/unit/test_schedulers.py::test_check_scheduler_creates_job_and_updates_next_run tests/unit/test_api_backup_plans.py::TestBackupPlanRoutes tests/unit/test_v2_services.py`
- `ruff check app tests`
- `ruff format --check app tests`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `cd frontend && npm run snapshots`

- [ ] Run targeted and required checks.
- [ ] Launch the app and capture runtime walkthrough evidence for repository check, scheduled check, and backup plan check flag paths.
- [ ] Commit, push, open/update PR with template content, add `symphony` label, attach PR to Linear.
- [ ] Sweep PR feedback and checks before moving Linear to Human Review.
