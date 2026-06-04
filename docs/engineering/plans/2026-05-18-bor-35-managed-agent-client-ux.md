# BOR-35 Managed Agent Client UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking. This unattended workflow executes inline in the current workspace.

**Goal:** Stabilize the managed-agent beta route and clarify client setup.

**Architecture:** Fix the shared React Query shape at the source, then compose a
small setup guide from reusable copyable code blocks plus a details dialog. Keep
documentation in the product docs and the agent README.

**Tech Stack:** React, Vite, MUI, TanStack Query, Vitest, Storybook.

---

### Task 1: Red Tests

**Files:**
- Modify: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`

- [x] Add a failing cache-shape regression test that preloads
  `['systemSettings']` with `{ settings: { managed_agents_beta_enabled: true } }`
  and asserts `/managed-agents` does not redirect to `/dashboard`.
- [x] Add a failing setup-guide test that asserts there is no duplicate token
  button, the copy control is icon-only and labelled, fresh-machine install text
  is present, and the help dialog explains `localhost:7879` plus startup.
- [x] Run `cd frontend && npm test -- --run src/pages/__tests__/ManagedAgents.test.tsx`
  and confirm both new tests fail for the expected reasons.

### Task 2: Route and UI Fix

**Files:**
- Modify: `frontend/src/pages/ManagedAgents.tsx`
- Modify: `frontend/src/pages/ManagedAgents.stories.tsx`

- [x] Change `ManagedAgents` system settings query to return `response.data`
  and read `settingsQuery.data?.settings?.managed_agents_beta_enabled`.
- [x] Make the top-level Enrollment Token action `variant="contained"` and label
  it `Create Enrollment Token`.
- [x] Remove token creation from `AgentSetupGuide` props and layout.
- [x] Add a `CopyableCodeBlock` helper that renders code with an embedded
  icon-only copy button and tooltip.
- [x] Add a setup help dialog opened from the guide. Include clone/install,
  register, server URL, `localhost:7879`, and startup/service guidance.
- [x] Update the Storybook story for the changed props and setup guide state,
  including a help-details story that snapshots the detailed guidance.

### Task 3: Docs

**Files:**
- Modify: `agent/README.md`
- Modify: `docs/beta-features.md`
- Create: `docs/managed-agents.md`

- [x] Update `agent/README.md` with fresh-machine install, registration URL, run,
  and startup service instructions.
- [x] Add a managed-agent beta section/link from `docs/beta-features.md`.
- [x] Add user-facing managed-agent docs with enablement, setup, URL selection,
  and startup guidance.

### Task 4: Validation

**Commands:**
- [x] `cd frontend && npm test -- --run src/pages/__tests__/ManagedAgents.test.tsx src/components/__tests__/AppSidebar.test.tsx --testTimeout 60000 --maxWorkers=1 --no-file-parallelism`
- [x] `cd frontend && npm run snapshots`
- [x] `cd frontend && npm run check:locales && npm run typecheck && npm run lint && npm run build`
- [x] `cd frontend && npm run test:coverage -- --changed origin/main --testTimeout 60000 --maxWorkers=1 --no-file-parallelism`
- [x] `cd docs && npm run build`
- [x] `git diff --check`
- [x] Runtime walkthrough with `./scripts/dev.sh` and Playwright: beta enablement,
  `/managed-agents` route persistence, setup help, token creation/copy, command
  copy, and sidebar persistence after reload.
