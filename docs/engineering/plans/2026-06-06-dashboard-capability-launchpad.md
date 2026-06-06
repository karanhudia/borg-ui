# Dashboard Capability Launchpad Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development for implementation and
> superpowers:verification-before-completion before claiming completion. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dashboard launchpad that helps users discover and act on newer
Borg UI capabilities, including backup plans, cloud storage, remote clients, and
restore verification.

**Architecture:** Add a focused `CapabilityLaunchpad` component under
`frontend/src/pages/dashboard-v3/`, derive row state from existing dashboard
overview data, `rcloneAPI.listRemotes()`, and remote-backend local storage,
place it in the DashboardV3 left rail, mirror it in the loading skeleton, and
add Storybook plus docs coverage. No backend contract changes are required.

**Tech Stack:** React, TypeScript, MUI, Lucide icons, TanStack Query existing
dashboard data, rclone API, remote-backend local storage, Vitest, Storybook,
VitePress docs.

---

## Task 1: Failing Dashboard Coverage

**Files:**

- Modify: `frontend/src/pages/__tests__/DashboardV3.test.tsx`

- [ ] Add a failing test that renders the existing `makeOverview()` fixture and
      expects an Operations launchpad with Backup plans, Cloud storage, Remote
      clients, and Restore verification rows.
- [ ] Add a failing test that clicks each launchpad action and expects
      navigation to `/backup-plans`, `/cloud-storage`, `/remote-clients`, and
      `/schedule/restore-checks`.
- [ ] Run:
      `cd frontend && npm test -- --run src/pages/__tests__/DashboardV3.test.tsx --testNamePattern "operations launchpad"`
      Expected: fail because the launchpad does not exist yet.

## Task 2: Launchpad Component

**Files:**

- Create: `frontend/src/pages/dashboard-v3/CapabilityLaunchpad.tsx`
- Modify: `frontend/src/pages/dashboard-v3/types.ts`

- [ ] Implement `CapabilityLaunchpad` props for `summary`, `repositories`,
      `cloudRemoteCount`, `remoteClientCount`, and an
      `onNavigate(destination, source)` callback.
- [ ] Derive backup-plan count from `summary.total_backup_plans` with legacy
      schedule fallback through `summary.total_schedules`.
- [ ] Derive cloud storage count from `rcloneAPI.listRemotes()` in DashboardV3.
- [ ] Derive remote client count from browser-registered remote backend clients.
- [ ] Derive restore verification count from repositories where
      `restore_check_configured` is true.
- [ ] Render four stable compact rows using existing dashboard tokens, MUI,
      Lucide icons, neutral text colors, hover/focus states, and row-level
      buttons.
- [ ] Run the operations launchpad tests and keep fixing until they pass.

## Task 3: Dashboard Integration and Skeleton

**Files:**

- Modify: `frontend/src/pages/DashboardV3.tsx`
- Modify: `frontend/src/pages/dashboard-v3/DashboardSkeleton.tsx`

- [ ] Import and render `CapabilityLaunchpad` in the left rail between
      Resources and Upcoming backups.
- [ ] Wire launchpad actions through the existing `trackNavigation` hook and
      `navigate()` calls.
- [ ] Add a matching skeleton panel with four compact rows so the loading
      layout does not jump.
- [ ] Run:
      `cd frontend && npm test -- --run src/pages/__tests__/DashboardV3.test.tsx --testNamePattern "operations launchpad"`
      Expected: pass.

## Task 4: Storybook and Locales

**Files:**

- Create: `frontend/src/pages/dashboard-v3/CapabilityLaunchpad.stories.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Add dashboard locale keys for launchpad title, row labels, status text,
      count text, and accessible action labels in all locale files.
- [ ] Add Storybook stories for MixedAdoption and EmptyStart states using
      `TokenContext` and the dashboard surface width.
- [ ] Run `cd frontend && npm run check:locales`.

## Task 5: Documentation

**Files:**

- Modify: `docs/navigation.md`

- [ ] Update Dashboard guidance to mention the launchpad's setup-gap actions.
- [ ] Keep the docs concise and focused on the user path.

## Task 6: Final Validation and Handoff

**Commands:**

- `cd frontend && npm test -- --run src/pages/__tests__/DashboardV3.test.tsx`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- Local UI walkthrough via Storybook or Borg UI at desktop and mobile widths.

- [ ] Run the targeted DashboardV3 Vitest suite.
- [ ] Run locale, typecheck, lint, and build gates.
- [ ] Run a local UI walkthrough and record evidence.
- [ ] Commit changes.
- [ ] Push branch, create/update PR from `.github/PULL_REQUEST_TEMPLATE.md`,
      add GitHub label `symphony`, attach/link PR to Linear, sweep PR feedback
      and checks, then move BOR-154 to Human Review when green.
