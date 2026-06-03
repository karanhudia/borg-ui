# Broken Repository Check Recovery UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for app behavior changes. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make broken repository Check and Info flows produce explicit feedback and copyable recovery commands.

**Architecture:** Keep the fix frontend-first. `Repositories.tsx` will announce terminal manual-check results from the existing job history endpoint, while `RepositoryInfoDialog.tsx` will render a reusable copyable recovery command panel when info loading fails.

**Tech Stack:** React, TypeScript, MUI, TanStack Query, Vitest, React Testing Library, Storybook.

---

## Implementation Tasks

### Task 1: Reproduce Silent Manual Check Completion

**Files:**

- Modify: `frontend/src/pages/__tests__/Repositories.test.tsx`
- Read: `frontend/src/pages/Repositories.tsx`

- [ ] Write a failing test that renders `Repositories`, starts with a tracked check job, flips `useMaintenanceJobs` to no running jobs, mocks `repositoriesAPI.getRepositoryCheckJobs` to return a failed latest check job, and expects an error toast containing the stored error.
- [ ] Run `cd frontend && npm test -- src/pages/__tests__/Repositories.test.tsx --runInBand` or the repo-equivalent targeted Vitest command and confirm the failure is due to missing terminal feedback.

### Task 2: Announce Terminal Check Results

**Files:**

- Modify: `frontend/src/pages/Repositories.tsx`
- Test: `frontend/src/pages/__tests__/Repositories.test.tsx`

- [ ] In `handleJobCompleted`, when the tracked operation is `Check`, fetch `repositoriesAPI.getRepositoryCheckJobs(repositoryId, 1)` as it already does.
- [ ] If the latest job status is `completed`, show `toast.success(t('repositories.toasts.checkCompleted'))`.
- [ ] If the latest job status is `completed_with_warnings`, show `toast(t('repositories.toasts.checkCompletedWithWarnings'), { icon: '!' })`.
- [ ] For any other terminal status, show `toast.error(t('repositories.toasts.checkFailedWithMessage', { message }))`, where `message` is `translateBackendKey(latestJob.error_message)` when present or `t('repositories.toasts.checkRunFailed')`.
- [ ] Keep existing analytics tracking and query invalidation behavior.
- [ ] Run the targeted test and confirm it passes.

### Task 3: Add Info Recovery Commands

**Files:**

- Modify: `frontend/src/components/RepositoryInfoDialog.tsx`
- Modify: `frontend/src/components/__tests__/RepositoryInfoDialog.test.tsx`
- Modify: `frontend/src/components/RepositoryInfoDialog.stories.tsx`
- Modify: `frontend/src/locales/en.json`
- Mirror new locale keys in existing locale files.

- [ ] Add a small internal copyable command block to `RepositoryInfoDialog.tsx` using `navigator.clipboard.writeText`, `toast.success`, and `toast.error`.
- [ ] Generate commands with the repository path, Borg version, `remote_path`, and encryption. Use `generateBorgInitCommand` for initialization.
- [ ] In the failed info state, render the existing failed alert plus recovery commands for check, repair, and initialize.
- [ ] Write a test that renders the failed state and asserts the three commands are present.
- [ ] Write a test that clicks a recovery command copy button and asserts `navigator.clipboard.writeText` receives that command.
- [ ] Add or update the Storybook story showing the failed recovery state.
- [ ] Run the targeted Info dialog test and confirm it passes.

### Task 4: Required Validation and Handoff

**Files:**

- Read/Update: Linear workpad comment
- Commit/push through repo skills

- [ ] Run targeted frontend tests for `Repositories` and `RepositoryInfoDialog`.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run runtime validation for the Info failed-state story or app path and record the evidence.
- [ ] Commit changes, push the BOR-127 branch, create/link PR, add `symphony` label, sweep PR feedback/checks, then move Linear to Human Review only when green.
