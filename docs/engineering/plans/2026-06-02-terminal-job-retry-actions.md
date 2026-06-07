# Terminal Job Retry Actions Implementation Plan

**Goal:** Add frontend retry actions for supported terminal manual backup jobs and backup plan runs.

**Architecture:** Reuse the backend retry endpoints already present in `app/api/backup.py` and `app/api/backup_plans.py`. Keep retry as an explicit recovery action: manual backup retries go through `backupAPI.retryJob`, plan-run retries go through `backupPlansAPI.retryRun`, and UI controls remain disabled or absent when the backend contract would reject the request. Use existing MUI icon-button/table patterns and locale-backed tooltips instead of introducing a new action surface.

**Tech Stack:** React, TypeScript, MUI, lucide-react, TanStack Query, i18next, Vitest, Storybook.

---

### Task 1: API Helpers And Types

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/services/api.test.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/types/jobs.ts`

- [ ] Add `backupAPI.retryJob(jobId)` that posts to `/backup/jobs/{jobId}/retry`.
- [ ] Add `backupPlansAPI.retryRun(runId)` that posts to `/backup-plans/runs/{runId}/retry`.
- [ ] Add retry metadata fields to backup job and backup plan run types so responses serialize without loose access.
- [ ] Add Vitest API helper tests that fail before the helper implementation.

### Task 2: Backup Job Retry Action

**Files:**
- Modify: `frontend/src/components/BackupJobsTable.tsx`
- Modify: `frontend/src/components/__tests__/BackupJobsTable.actions.test.tsx`
- Modify: `frontend/src/pages/Backup.tsx`
- Modify: `frontend/src/pages/__tests__/Backup.test.tsx`

- [ ] Add an optional `actions.retry` action using `RotateCcw`, `color="info"`, and locale-backed tooltip text to stay distinct from `Run Now`'s play/success affordance.
- [ ] Show retry for terminal `failed` and `cancelled` rows when the row is a manual backup job.
- [ ] Disable retry with explicit tooltip text for missing repository context and insufficient backup/operator permission.
- [ ] Show a disabled retry affordance with a destructive-job tooltip for terminal unsupported job types such as prune or delete-like activity rows.
- [ ] Confirm before retrying, call the page-provided callback, and let page mutations invalidate backup job queries.

### Task 3: Backup Plan Run Retry Action

**Files:**
- Modify: `frontend/src/components/BackupPlanRunsPanel.tsx`
- Modify: `frontend/src/components/__tests__/BackupPlanRunsPanel.test.tsx`
- Modify: `frontend/src/pages/backup-plans/plan-runs/PlanRunsHistoryTable.tsx`
- Modify: `frontend/src/pages/backup-plans/plan-runs/BackupPlanHistoryDialog.tsx`
- Modify: `frontend/src/pages/Backup.tsx`
- Modify: `frontend/src/pages/BackupPlans.tsx`

- [ ] Add retry actions to recent plan-run rows and plan history dialog rows.
- [ ] Enable retry only for failed plan runs with at least one failed child repository and an attached backup plan.
- [ ] Disable retry with tooltip text when the run is cancelled/non-failed, has no failed repositories, has an active run for the same plan, or the user lacks backup/operator permission on failed child repositories.
- [ ] Confirm before retrying, call page mutation wiring, and invalidate backup plan run and backup plan queries.

### Task 4: Locale And Stories

**Files:**
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`
- Modify: `frontend/src/components/BackupJobsTable.stories.tsx`
- Add: `frontend/src/components/BackupPlanRunsPanel.stories.tsx`

- [ ] Add retry labels, confirmations, success/error toasts, disabled tooltips, and backend retry error translations in all shipped locales.
- [ ] Add Storybook coverage for a retryable failed manual backup job.
- [ ] Add Storybook coverage for a non-retryable destructive terminal job.
- [ ] Add Storybook coverage for a retryable failed backup plan run.

### Task 5: Validation

**Commands:**
- [ ] `cd frontend && npm run test -- src/services/api.test.ts src/components/__tests__/BackupJobsTable.actions.test.tsx src/components/__tests__/BackupPlanRunsPanel.test.tsx src/pages/__tests__/Backup.test.tsx`
- [ ] `cd frontend && npm run check:locales`
- [ ] `cd frontend && npm run typecheck`
- [ ] `cd frontend && npm run lint`
- [ ] `cd frontend && npm run build`
- [ ] `cd frontend && npm run snapshots`
- [ ] Runtime smoke or walkthrough for backup job and backup plan run retry controls.

### Self-Review

- The plan does not expose generic retry for restore, prune, compact, wipe, package, or scheduled run-now jobs.
- Backup plan run retry follows the current backend contract: failed plan runs only, failed repositories only.
- Disabled states use tooltips and do not rely on color alone.
- `Run Now` remains a play/success action; retry uses a repeat icon and info color.
