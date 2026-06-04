# Cloud Storage Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated Cloud Storage page for reusable rclone remotes and
reshape repository setup so Cloud Storage is a normal Location card.

**Architecture:** Keep backend rclone repository behavior unchanged except for
remote usage-count serialization. Add a new React page that uses the existing
`rcloneAPI` and `RcloneRemoteDialog`, wire it into routing/sidebar, and simplify
`WizardStepLocation` so rclone is a fourth card instead of a wizard-local tab.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, Vite, MUI, TanStack Query,
Vitest, Storybook snapshots.

---

### Task 1: Backend Usage Count

**Files:**

- Modify: `app/api/rclone.py`
- Modify: `frontend/src/services/api.ts`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Write a failing API test showing `GET /api/rclone/remotes` includes
      `usage_count` for a remote referenced by `RepositoryStorage`.
- [ ] Update `_serialize_remote()` to include `usage_count`.
- [ ] Extend the frontend `RcloneRemote` type with `usage_count?: number`.
- [ ] Run `pytest tests/unit/test_api_rclone.py -q`.

### Task 2: Cloud Storage Page

**Files:**

- Create: `frontend/src/pages/CloudStorage.tsx`
- Create: `frontend/src/pages/__tests__/CloudStorage.test.tsx`
- Create: `frontend/src/pages/CloudStorage.stories.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Write failing tests for rendering remote cards, adding a managed remote,
      testing a remote, browsing a remote, empty state, and unavailable state.
- [ ] Implement `CloudStorage` with `rcloneAPI.getStatus`,
      `rcloneAPI.listRemotes`, `rcloneAPI.createRemote`,
      `rcloneAPI.testRemote`, and `rcloneAPI.browseRemote`.
- [ ] Reuse `RcloneRemoteDialog` for add-remote input and validation.
- [ ] Display provider, status, usage count, managed-config source, test
      action, and browse action on each remote.
- [ ] Add localized Cloud Storage page strings to every locale file.
- [ ] Add Storybook stories for populated, empty, and unavailable page states.

### Task 3: Sidebar And Route

**Files:**

- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppSidebar.tsx`
- Modify: `frontend/src/components/__tests__/AppSidebar.test.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Write a failing sidebar test that expects a BACKUP link named Cloud
      Storage with href `/cloud-storage`.
- [ ] Add the page route behind the same repository-management enablement used
      for Repositories.
- [ ] Add the sidebar item under BACKUP near Repositories using a cloud/storage
      lucide icon.
- [ ] Add navigation labels in every locale file.

### Task 4: Repository Wizard Location Cards

**Files:**

- Modify: `frontend/src/components/wizard/WizardStepLocation.tsx`
- Modify: `frontend/src/components/wizard/WizardStepLocation.stories.tsx`
- Modify: `frontend/src/components/wizard/__tests__/WizardStepLocation.test.tsx`
- Modify: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Write a failing wizard-location test that expects Cloud Storage to be a
      card beside Borg UI Server and SSH Server, not a tab.
- [ ] Remove the wizard-local Cloud sources/filesystem tabs.
- [ ] Render Cloud Storage as a fourth location card for local execution.
- [ ] Render managed-agent storage as a card in the same group while preserving
      the existing managed-agent selector behavior.
- [ ] Keep rclone fields below the location cards when Cloud Storage is
      selected and preserve the submitted rclone payload shape.
- [ ] Update stories and repository wizard integration tests for the new card.

### Task 5: Follow-Up Issue And Docs

**Files:**

- Modify: `docs/engineering/specs/2026-05-24-rclone-storage-integration.md`
- Modify: `docs/engineering/plans/2026-05-24-rclone-storage-integration.md`

- [ ] Update the original rclone spec/plan to reference the Cloud Storage page
      and repository-owned sync model.
- [ ] Create a Linear Backlog follow-up for enabling cloud mirrors on existing
      local repositories, related to BOR-66 and blocked by BOR-66.
- [ ] Reply to the PR comment with implemented changes and the follow-up
      rationale.

### Task 6: Verification And Handoff

**Files:**

- Modify generated snapshots under `frontend/storybook-snapshots/`.

- [ ] Run backend targeted validation:
      `ruff check app tests`, `ruff format --check app tests`, and
      `pytest tests/unit/test_api_rclone.py -q`.
- [ ] Run frontend validation:
      `cd frontend && npm run check:locales`,
      `cd frontend && npm run format:check`,
      `cd frontend && NODE_OPTIONS=--max-old-space-size=4096 npm run typecheck`,
      `cd frontend && NODE_OPTIONS=--max-old-space-size=4096 npm run lint`,
      `cd frontend && NODE_OPTIONS=--max-old-space-size=3072 ROLLUP_MAX_PARALLEL_FILE_OPS=1 npm run build`,
      and targeted Vitest.
- [ ] Run `cd frontend && NODE_OPTIONS=--max-old-space-size=3072 ROLLUP_MAX_PARALLEL_FILE_OPS=1 npm run snapshots`.
- [ ] Run local app walkthrough or smoke path for Cloud Storage remote
      management and rclone repository create/import/sync/hydrate.
- [ ] Commit, push, refresh PR body, re-sweep all PR feedback and checks, update
      the Linear workpad handoff, and move the issue back to Human Review only
      when green.
