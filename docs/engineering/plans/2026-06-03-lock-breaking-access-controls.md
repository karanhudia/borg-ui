# Lock Breaking Access Controls Implementation Plan

> **For agentic workers:** Execute this plan with test-first changes. Keep Linear's workpad synchronized after each milestone.

**Goal:** Add a default-on global lock-breaking setting and align UI/backend authorization with repository maintenance access.

**Architecture:** Store `lock_breaking_enabled` on `SystemSettings`, expose it through the existing settings API, and enforce it in the user-initiated break-lock endpoint. Frontend callers derive lock-break capability from `lock_breaking_enabled && canDo(repoId, 'maintenance')`; reusable job-table logic accepts either a boolean or per-job predicate.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, TypeScript, TanStack Query, Vitest, Storybook.

---

### Task 1: Backend Contract And Enforcement

**Files:**
- Modify: `tests/unit/test_api_repositories_dispatch.py`
- Modify: `tests/unit/test_api_settings_routes.py`
- Modify: `app/database/models.py`
- Create: `app/database/migrations/120_add_lock_breaking_enabled.py`
- Modify: `app/api/settings.py`
- Modify: `app/api/repositories.py`
- Modify: `frontend/src/locales/en.json`

- [ ] Add failing API tests:
  - `POST /api/repositories/{repo_id}/break-lock` returns `403` and does not call `BorgRouter` when `SystemSettings.lock_breaking_enabled` is false.
  - A repository `operator` permission can break the lock when the setting is enabled.
  - System settings GET returns `lock_breaking_enabled: true` by default and PUT persists false.
- [ ] Run the targeted pytest tests and confirm the new cases fail for missing model/API support.
- [ ] Add `SystemSettings.lock_breaking_enabled = Column(Boolean, default=True, nullable=False)`.
- [ ] Add an idempotent SQLite migration that adds `lock_breaking_enabled BOOLEAN DEFAULT 1 NOT NULL`.
- [ ] Add `lock_breaking_enabled` to `SystemSettingsUpdate`, GET serialization, and PUT persistence.
- [ ] In `break_repository_lock`, keep `_load_repository_with_access(..., "operator")`, then reject with `403` and `backend.errors.repo.lockBreakingDisabled` before preparing Borg env when the setting is false.
- [ ] Run the targeted pytest tests and confirm they pass.

### Task 2: Frontend Permission State

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/LockErrorDialog.tsx`
- Modify: `frontend/src/components/__tests__/LockErrorDialog.test.tsx`
- Modify: `frontend/src/components/BackupJobsTable.tsx`
- Modify: `frontend/src/components/__tests__/BackupJobsTable.test.tsx`
- Modify: `frontend/src/components/BackupJobsTable.stories.tsx`
- Modify: `frontend/src/pages/Repositories.tsx`
- Modify: `frontend/src/pages/Backup.tsx`
- Modify: `frontend/src/pages/Activity.tsx`
- Modify: `frontend/src/pages/Schedule.tsx`
- Modify: `frontend/src/locales/en.json`, `frontend/src/locales/de.json`, `frontend/src/locales/es.json`, `frontend/src/locales/it.json`

- [ ] Add failing Vitest coverage for:
  - `LockErrorDialog` showing a global-disabled message when `lockBreakingEnabled={false}`.
  - Disabled permission copy using repository maintenance access wording.
  - `BackupJobsTable` accepting a per-job `canBreakLocks` predicate and showing the action only for allowed lock-error jobs.
- [ ] Run the targeted Vitest tests and confirm the new cases fail.
- [ ] Extend `SystemSettings` with `lock_breaking_enabled?: boolean`.
- [ ] Extend `LockErrorDialog` with `lockBreakingEnabled?: boolean`, default true, and compute disabled reason from global setting first, then permission.
- [ ] Change `BackupJobsTable` `canBreakLocks` from boolean-only to `boolean | ((job) => boolean)` and pass the resolved per-job ability into `LockErrorDialog`.
- [ ] Query `systemSettings` in pages that surface lock-breaking controls and combine it with `permissions.canDo(repoId, 'maintenance')`.
- [ ] Add/update Storybook states for lock-error permission behavior and the settings switch.
- [ ] Run targeted Vitest tests and confirm they pass.

### Task 3: Settings UI

**Files:**
- Modify: `frontend/src/components/BetaFeaturesTab.tsx`
- Modify: `frontend/src/components/__tests__/BetaFeaturesTab.test.tsx`
- Modify: `frontend/src/components/BetaFeaturesTab.stories.tsx`
- Modify: locale files listed in Task 2

- [ ] Add failing Vitest coverage for rendering and toggling the global manual lock-breaking switch.
- [ ] Add `lockBreakingEnabled` local state, load it from `systemSettings.lock_breaking_enabled ?? true`, and save it through `settingsAPI.updateSystemSettings({ lock_breaking_enabled: checked })`.
- [ ] Present the switch near existing Borg lock handling controls with direct operational copy.
- [ ] Update Storybook initial settings so the switch renders in snapshots.
- [ ] Run targeted Vitest tests and confirm they pass.

### Task 4: Verification And Handoff

**Files:**
- Modify only if validation exposes defects.

- [ ] Run targeted backend tests:
  - `pytest tests/unit/test_api_repositories_dispatch.py::TestRepositoryApiDispatch -q`
  - `pytest tests/unit/test_api_settings_routes.py::TestSystemSettingsContracts -q`
- [ ] Run targeted frontend tests:
  - `cd frontend && npm test -- --run src/components/__tests__/LockErrorDialog.test.tsx src/components/__tests__/BackupJobsTable.test.tsx src/components/__tests__/BetaFeaturesTab.test.tsx`
- [ ] Run required backend checks: `ruff check app tests`, `ruff format --check app tests`.
- [ ] Run required frontend checks: `cd frontend && npm run check:locales && npm run typecheck && npm run lint && npm run build`.
- [ ] Perform local app/runtime walkthrough or document the concrete blocker if the environment cannot launch it.
- [ ] Commit, push, create PR with the template, attach PR to Linear, ensure `symphony` label, sweep comments/checks, then move Linear to Human Review.
