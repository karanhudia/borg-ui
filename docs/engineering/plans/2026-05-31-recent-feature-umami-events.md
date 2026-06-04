# Recent Feature Umami Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Umami event coverage for recent cloud storage, managed agent, and backup plan features.

**Architecture:** Instrument container pages where the workflow state and action handlers already live. Reuse `useAnalytics`, existing event categories, and stable non-sensitive payloads. Add focused tests by mocking `useAnalytics` in each page test file and asserting user actions call `track`/`trackSystem` with the expected metadata.

**Tech Stack:** React, TypeScript, Vite, Vitest, React Testing Library, existing Borg UI analytics utilities.

---

## Task 1: Cloud Storage Analytics

**Files:**
- Modify: `frontend/src/pages/CloudStorage.tsx`
- Modify: `frontend/src/pages/__tests__/CloudStorage.test.tsx`

- [ ] Add a failing test in `CloudStorage.test.tsx` that mocks `../../hooks/useAnalytics`, renders the page, and verifies cloud storage actions emit `System` events with `section: 'cloud_storage'`.
- [ ] Run `cd frontend && npm run test -- --run src/pages/__tests__/CloudStorage.test.tsx` and confirm the new test fails because analytics calls are missing.
- [ ] Import `useAnalytics` in `CloudStorage.tsx`.
- [ ] Track refresh, search, sort, group, add dialog view, create/update/delete/test/browse/browser navigation, OAuth start, and OAuth credential save events.
- [ ] Keep payloads limited to operation, provider, auth mode/status, sort/group value, and path presence/count metadata.
- [ ] Re-run the targeted CloudStorage test and confirm it passes.

## Task 2: Managed Agents Analytics

**Files:**
- Modify: `frontend/src/pages/ManagedAgents.tsx`
- Modify: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`

- [ ] Add a failing test that mocks `../../hooks/useAnalytics`, performs refresh, tab, copy, log, token, and agent actions, and verifies `System` events with `section: 'managed_agents'`.
- [ ] Run `cd frontend && npm run test -- --run src/pages/__tests__/ManagedAgents.test.tsx` and confirm the test fails because analytics calls are missing.
- [ ] Import `useAnalytics` in `ManagedAgents.tsx`.
- [ ] Track refresh, tab changes, add dialog view, setup/help command copy, token create/revoke, agent revoke/delete, reinstall command view, log view, and job cancel actions.
- [ ] Keep payloads limited to operation, source, tab, status, job type, and boolean state metadata.
- [ ] Re-run the targeted ManagedAgents test and confirm it passes.

## Task 3: Backup Plans Analytics

**Files:**
- Modify: `frontend/src/pages/BackupPlans.tsx`
- Modify: `frontend/src/pages/backup-plans/BackupPlansContent.tsx`
- Modify: `frontend/src/pages/backup-plans/__tests__/BackupPlansContent.test.tsx`

- [ ] Add a failing content-level test that passes analytics-aware callbacks and verifies search, sort, group, repository-filter clear, and card actions can be tracked by the parent callbacks.
- [ ] Run `cd frontend && npm run test -- --run src/pages/backup-plans/__tests__/BackupPlansContent.test.tsx src/pages/__tests__/BackupPlans.test.tsx` and confirm the new analytics assertions fail before implementation.
- [ ] Import `useAnalytics` in `BackupPlans.tsx`.
- [ ] Wrap `BackupPlansContent` callbacks to track create view, run, cancel run, logs, toggle, edit view, delete, history view, linked repository navigation, filter clear, search, sort, and group.
- [ ] Track create/update success after mutation success using the submitted payload and edit/create mode.
- [ ] Re-run the backup plan targeted tests and confirm they pass.

## Task 4: Final Validation

**Files:**
- No additional files expected.

- [ ] Run `cd frontend && npm run test -- --run src/pages/__tests__/CloudStorage.test.tsx src/pages/__tests__/ManagedAgents.test.tsx src/pages/__tests__/BackupPlans.test.tsx src/pages/backup-plans/__tests__/BackupPlansContent.test.tsx`.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Record validation evidence in the Linear workpad before commit/push.
