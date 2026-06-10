# Schedule-Aware Upload Limits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add backup-plan time-window upload-limit policies while preserving the
existing BOR-166 constant upload cap behavior.

**Architecture:** Store an ordered JSON policy list on `backup_plans`, validate
and serialize it through the backup-plan API, and resolve the active policy in a
small service helper before Borg 1/Borg 2 command construction. Frontend keeps
MB/s inputs at the UI boundary and converts to KiB/s in the existing backup-plan
payload helper.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, MUI, Vite, Vitest,
Storybook.

---

## Files

- Create: `app/database/migrations/124_add_backup_plan_upload_ratelimit_policies.py`
- Create: `app/services/upload_ratelimit_policies.py`
- Modify: `app/database/models.py`
- Modify: `app/api/backup_plans.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Modify: `tests/unit/test_database_operations.py`
- Modify: `tests/unit/test_api_backup_plans.py`
- Modify: `tests/unit/test_borg_router.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/utils/backupPlanPayload.ts`
- Modify: `frontend/src/pages/backup-plans/state.ts`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SettingsStep.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/ReviewStep.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/ReviewStep.stories.tsx`
- Modify: `frontend/src/pages/__tests__/BackupPlans.test.tsx`
- Modify: `frontend/src/pages/backup-plans/__tests__/ReviewStep.test.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/it.json`

## Task 1: Backend RED tests

- [ ] Add migration tests for `backup_plans.upload_ratelimit_schedule_policies`.
- [ ] Add API create/edit tests proving policy payloads persist, serialize, trim
  labels, and reject invalid times or non-positive caps.
- [ ] Add resolver tests proving day window, overnight window, unlimited policy,
  no-match fallback, and policy-over-constant precedence.
- [ ] Add backup-plan execution tests proving an active policy value is passed
  to `backup_service.execute_backup` and an active unlimited policy passes
  `None`.
- [ ] Add Borg router tests proving Borg 1 includes `--upload-ratelimit` for a
  resolved cap and Borg 2 receives the resolved cap through its builder.
- [ ] Run the targeted tests and confirm they fail because the scheduled policy
  feature does not exist.

## Task 2: Backend implementation

- [ ] Add nullable `upload_ratelimit_schedule_policies` text column to
  `BackupPlan`.
- [ ] Add idempotent migration `124_add_backup_plan_upload_ratelimit_policies`.
- [ ] Add policy validation and normalization in `app/api/backup_plans.py`.
- [ ] Serialize policies in list/detail plan responses.
- [ ] Add `resolve_upload_ratelimit_policy()` helper with timezone-aware
  matching and overnight-window support.
- [ ] Use the helper when building `RepositoryRunContext` values in
  `backup_plan_execution_service`.
- [ ] Keep existing constant resolution unchanged when no policy matches.
- [ ] Run targeted backend tests and keep them green.

## Task 3: Frontend RED tests

- [ ] Add `BackupPlans.test.tsx` coverage for creating a plan with a daytime cap
  and overnight unlimited policy.
- [ ] Add edit hydration coverage for `upload_ratelimit_schedule_policies`.
- [ ] Add `ReviewStep.test.tsx` coverage for policy summary rendering.
- [ ] Run focused Vitest tests and confirm failures before UI code changes.

## Task 4: Frontend implementation

- [ ] Extend backup-plan types and wizard state with
  `uploadRatelimitSchedulePolicies`.
- [ ] Convert policy MB/s values to nullable KiB/s in `buildBackupPlanPayload`.
- [ ] Hydrate API policies back to MB/s values in `state.ts`.
- [ ] Add a compact composed policy editor to `SettingsStep.tsx`.
- [ ] Add policy summary rows to `ReviewStep.tsx`.
- [ ] Update `ReviewStep.stories.tsx` with a day/night policy example.
- [ ] Add English, German, and Italian locale strings used by the new controls.
- [ ] Run focused frontend tests and keep them green.

## Task 5: Full validation and runtime walkthrough

- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run relevant backend `pytest` commands for migration, API, resolver,
  execution, and Borg command generation.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run focused Vitest tests for touched backup-plan UI.
- [ ] Launch Borg UI locally and capture runtime evidence that the active window
  resolves the expected cap for a backup plan run.

## Self-Review

- The plan preserves BOR-166 constant behavior by treating scheduled policies as
  an optional runtime override.
- The data model stays scoped to backup plans, matching the requested backup job
  policy behavior without adding repository-wide schedules.
- The backend exposes one resolved integer or `None` to Borg command builders,
  matching Borg's constant create-time `--upload-ratelimit` contract.
- The frontend work is limited to the existing backup-plan wizard and review
  surfaces, with Storybook and test coverage for the changed state.
