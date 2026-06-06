# Remote Clients Database Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Store saved Remote Clients in the database with admin-only backend
access while keeping JWT tokens and active target selection browser-local.

**Architecture:** Add a small global `remote_backend_clients` table and
admin-only FastAPI router. Refactor the frontend remote backend provider so the
client list is hydrated from the API, legacy localStorage rows are imported once
for admins, and the target switcher blocks stale remote targets for non-admins.

**Tech Stack:** FastAPI, SQLAlchemy, custom SQLite/Postgres migrations, React,
Vite, MUI, Vitest, Storybook.

---

## Task 1: Backend Persistence Contract

**Files:**

- Create: `app/api/remote_clients.py`
- Create: `tests/unit/test_api_remote_clients.py`
- Create: `app/database/migrations/122_add_remote_backend_clients.py`
- Modify: `app/database/models.py`
- Modify: `app/main.py`

- [ ] **Step 1: Write failing backend API tests**

  Add tests that create a remote client as admin, verify the response shape,
  verify list/readback from the database, update URL/name, patch health, delete,
  and assert a viewer receives 403 on all endpoints.

- [ ] **Step 2: Run backend tests and verify RED**

  Run:

  ```bash
  pytest tests/unit/test_api_remote_clients.py -q
  ```

  Expected: fail because `/api/remote-clients` routes and model do not exist.

- [ ] **Step 3: Add model and migration**

  Add `RemoteBackendClient` to `app/database/models.py` and migration
  `122_add_remote_backend_clients.py` creating the table and indexes.

- [ ] **Step 4: Add admin-only router**

  Implement `/api/remote-clients` CRUD and health endpoints using
  `get_current_admin_user`, backend URL normalization, serialized UTC
  timestamps, and stable string IDs.

- [ ] **Step 5: Register router and verify GREEN**

  Include the router in `app/main.py`, then rerun:

  ```bash
  pytest tests/unit/test_api_remote_clients.py -q
  ```

  Expected: all tests in the new file pass.

## Task 2: Frontend API-Backed Remote Backend State

**Files:**

- Modify: `frontend/src/services/remoteBackends/storage.ts`
- Modify: `frontend/src/services/remoteBackends/context.tsx`
- Modify: `frontend/src/services/remoteBackends/storage.test.ts`
- Modify: `frontend/src/services/remoteBackends/context.test.tsx`
- Modify: `frontend/src/services/remoteBackends/types.ts`

- [ ] **Step 1: Write failing provider/storage tests**

  Update tests so remote clients are loaded from mocked `/remote-clients`
  responses, create/update/delete/health calls hit the API, legacy
  `borg_ui_remote_backends` entries import once, and the legacy `access_token`
  key remains unchanged for local JWTs.

- [ ] **Step 2: Run frontend tests and verify RED**

  Run:

  ```bash
  cd frontend && npm run test -- --run src/services/remoteBackends/storage.test.ts src/services/remoteBackends/context.test.tsx
  ```

  Expected: fail because the provider is still localStorage-backed.

- [ ] **Step 3: Refactor storage boundaries**

  Keep active target ID and target-scoped token helpers in localStorage. Move
  remote client list state to an in-memory snapshot managed by the provider,
  with legacy read/import helpers for `borg_ui_remote_backends`.

- [ ] **Step 4: Implement API hydration and mutations**

  In `RemoteBackendProvider`, fetch `/remote-clients` with the selected target's
  JWT, refresh after token changes, import legacy entries after successful admin
  hydration, and convert create/update/delete/check flows to async API
  mutations.

- [ ] **Step 5: Verify frontend state tests GREEN**

  Rerun the targeted storage/context Vitest command and keep it green.

## Task 3: UI Permission Gate and Story Coverage

**Files:**

- Modify: `frontend/src/pages/RemoteClients.tsx`
- Modify: `frontend/src/pages/__tests__/RemoteClients.test.tsx`
- Modify: `frontend/src/components/BackendTargetSwitcher.tsx`
- Modify: `frontend/src/components/__tests__/BackendTargetSwitcher.test.tsx`
- Modify: `frontend/src/pages/RemoteClients.stories.tsx`
- Modify: `docs/navigation.md` if navigation text changes

- [ ] **Step 1: Write failing UI tests**

  Assert the Remote Clients page uses async persistence, non-admins are
  redirected, and the switcher disables or hides remote switching when
  `settings.ssh.manage` is absent even if stale remote clients exist.

- [ ] **Step 2: Run UI tests and verify RED**

  Run:

  ```bash
  cd frontend && npm run test -- --run src/pages/__tests__/RemoteClients.test.tsx src/components/__tests__/BackendTargetSwitcher.test.tsx
  ```

  Expected: fail until UI handlers and switcher permission checks are updated.

- [ ] **Step 3: Update UI handlers and permission checks**

  Make add/edit/delete/check handlers async, render existing loading/error state
  cleanly, and gate switcher remote targets with both plan access and
  `settings.ssh.manage`.

- [ ] **Step 4: Update Storybook**

  Update `RemoteClients.stories.tsx` to demonstrate the database-backed admin
  state and any loading/error state introduced by API hydration.

- [ ] **Step 5: Verify UI tests GREEN**

  Rerun the targeted Remote Clients and switcher Vitest command.

## Task 4: Full Validation and Handoff

**Files:**

- Modify as needed based on validation findings.

- [ ] **Step 1: Backend validation**

  Run:

  ```bash
  ruff check app tests
  ruff format --check app tests
  pytest tests/unit/test_api_remote_clients.py -q
  ```

- [ ] **Step 2: Frontend validation**

  Run:

  ```bash
  cd frontend && npm run check:locales
  cd frontend && npm run typecheck
  cd frontend && npm run lint
  cd frontend && npm run build
  ```

- [ ] **Step 3: Runtime walkthrough**

  Launch Borg UI locally, log in as admin, save a remote client, confirm the
  network request writes to `/api/remote-clients`, refresh in a fresh browser
  context, confirm the saved client loads from DB, switch to it, and confirm a
  non-admin cannot see or call the remote-client endpoints.

- [ ] **Step 4: Commit, push, PR, and Linear handoff**

  Commit the scoped changes, push the branch, create/update the PR with the
  repository template, attach it to Linear, run the PR feedback sweep, and move
  BOR-155 to Human Review only after checks and feedback are green.
