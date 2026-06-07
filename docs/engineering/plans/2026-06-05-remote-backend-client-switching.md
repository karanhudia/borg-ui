# Remote Backend Client Switching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development for implementation and
> superpowers:verification-before-completion before claiming completion. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Borg UI users register remote Borg UI backends, monitor their
health/version compatibility, and switch the frontend target between local and
remote backends.

**Architecture:** Add a frontend remote-backend provider backed by localStorage,
route all API helpers through a runtime-selected API base URL, scope JWT tokens
per backend target, and add a header/auth-shell selector plus a Remote Clients
management page under Infrastructure. Reuse existing `/health` and
`/api/system/info` contracts; no backend persistence is planned.

**Tech Stack:** React, TypeScript, MUI, TanStack Query, Axios, Vitest,
Storybook, FastAPI existing health/system-info contracts.

---

## Task 1: Remote Backend URL, Persistence, and Auth Token Helpers

**Files:**

- Create: `frontend/src/services/remoteBackends/types.ts`
- Create: `frontend/src/services/remoteBackends/url.ts`
- Create: `frontend/src/services/remoteBackends/storage.ts`
- Modify: `frontend/src/services/authHeaders.ts`
- Test: `frontend/src/services/remoteBackends/url.test.ts`
- Test: `frontend/src/services/remoteBackends/storage.test.ts`

- [ ] Add failing URL tests for `localhost:8000`, `192.168.1.10:8080`,
      `backup.example.com`, `https://backup.example.com/api`,
      `https://backup.example.com/borg`, invalid schemes, and empty inputs.
- [ ] Add failing storage tests for CRUD, active target fallback to local,
      target-scoped token get/set/clear, and incompatible target activation
      rejection.
- [ ] Implement remote backend types for local target, remote clients, health
      status, compatibility status, and stored state.
- [ ] Implement URL normalization and web-base derivation.
- [ ] Implement localStorage read/write with defensive parsing and same-tab
      subscriptions.
- [ ] Replace direct access-token reads in `authHeaders.ts` with active
      target-aware helpers while preserving legacy `access_token` for local.
- [ ] Run targeted tests and record red/green evidence.

## Task 2: Dynamic API Base Routing

**Files:**

- Modify: `frontend/src/utils/downloadUrl.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/services/authRequest.ts`
- Modify: `frontend/src/services/borgApi/client.ts`
- Modify: `frontend/src/pages/Login.tsx`
- Test: `frontend/src/utils/__tests__/downloadUrl.test.ts`
- Test: `frontend/src/services/api.test.ts`
- Test: `frontend/src/services/borgApi/client.test.ts`

- [ ] Add failing tests showing download URLs, Axios requests, auth fetches,
      and BorgApiClient requests use the currently selected backend.
- [ ] Add a runtime `getApiBaseUrl()` helper and keep `API_BASE_URL` as the
      local default for existing imports.
- [ ] Set Axios `baseURL` in request interceptors from `getApiBaseUrl()` for
      both shared clients.
- [ ] Make fetch helpers and download URL construction call `getApiBaseUrl()`
      at execution time.
- [ ] Replace Login passkey autofill direct token writes with target-scoped
      token writes.
- [ ] Run targeted tests and record red/green evidence.

## Task 3: Remote Backend Provider and Auth Reinitialization

**Files:**

- Create: `frontend/src/services/remoteBackends/context.tsx`
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/hooks/useAuth.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Test: `frontend/src/services/remoteBackends/context.test.tsx`
- Test: `frontend/src/hooks/__tests__/useAuth.test.tsx`
- Test: `frontend/src/components/__tests__/Layout.test.tsx`

- [ ] Add failing provider tests for add/edit/remove/check/switch and blocking
      incompatible targets.
- [ ] Add failing auth tests showing target changes re-check auth config and
      use the selected target token.
- [ ] Add `RemoteBackendProvider` above `AuthProvider`.
- [ ] Re-run auth initialization when the active target changes and clear only
      the selected target token on selected-target 401/logout.
- [ ] Clear TanStack Query data on target switch so views refetch from the
      selected backend.
- [ ] Run targeted tests and record red/green evidence.

## Task 4: Header Selector and Auth-Shell Selector

**Files:**

- Create: `frontend/src/components/BackendTargetSwitcher.tsx`
- Create: `frontend/src/components/BackendTargetSwitcher.stories.tsx`
- Modify: `frontend/src/components/AppHeader.tsx`
- Modify: `frontend/src/components/AuthLayout.tsx`
- Test: `frontend/src/components/__tests__/BackendTargetSwitcher.test.tsx`
- Test: `frontend/src/components/__tests__/AppHeader.test.tsx`

- [ ] Add failing tests for local/remote display, remote switch action,
      incompatible-disabled state, and manage-link action.
- [ ] Build a compact MUI/Lucide target switcher with labelled buttons,
      status chips, no heavy accent borders, and keyboard-visible focus.
- [ ] Place the switcher near the profile menu in `AppHeader`.
- [ ] Render the switcher in `AuthLayout` so unauthenticated remote users can
      switch back to local.
- [ ] Add Storybook states for local, online remote, offline remote, and
      incompatible remote targets.
- [ ] Run targeted tests and record red/green evidence.

## Task 5: Remote Clients Page, Navigation, Locales, and Docs

**Files:**

- Create: `frontend/src/pages/RemoteClients.tsx`
- Create: `frontend/src/pages/RemoteClients.stories.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/AppSidebar.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`
- Create: `docs/remote-clients.md`
- Modify: `docs/navigation.md`
- Test: `frontend/src/pages/__tests__/RemoteClients.test.tsx`
- Test: `frontend/src/components/__tests__/AppSidebar.test.tsx`

- [ ] Add failing tests for Remote Clients navigation, route rendering,
      add/edit/delete/check/switch flow, URL validation, and inaccessible
      remote status messaging.
- [ ] Add `/remote-clients` route under existing protected connections access.
- [ ] Add Remote Clients to Infrastructure navigation above Remote Machines.
- [ ] Build the management page using MUI, `ResponsiveDialog`, labelled form
      controls, clear status chips, and concise recovery text.
- [ ] Add locales for navigation and Remote Clients text in all locale files.
- [ ] Add docs for setup, DNS/URL rules, auth, health, compatibility, and
      switching back local.
- [ ] Add Storybook states for empty, online, offline, and incompatible lists.
- [ ] Run targeted tests and record red/green evidence.

## Task 6: Final Validation and Handoff

**Commands:**

- `cd frontend && npm run test -- --run frontend/src/services/remoteBackends/url.test.ts frontend/src/services/remoteBackends/storage.test.ts frontend/src/components/__tests__/BackendTargetSwitcher.test.tsx frontend/src/pages/__tests__/RemoteClients.test.tsx frontend/src/components/__tests__/AppSidebar.test.tsx frontend/src/components/__tests__/AppHeader.test.tsx`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- Runtime walkthrough via `./scripts/dev.sh`, Docker, or available smoke runner.

- [ ] Run all targeted Vitest paths.
- [ ] Run frontend locale, typecheck, lint, and build gates.
- [ ] Run backend gates only if backend files/contracts changed.
- [ ] Perform local walkthrough for add/check/switch/switch-back behavior.
- [ ] Commit changes.
- [ ] Push branch, create/update PR from `.github/PULL_REQUEST_TEMPLATE.md`,
      add GitHub label `symphony`, attach/link PR to Linear, sweep PR feedback
      and checks, then move BOR-151 to Human Review when green.
