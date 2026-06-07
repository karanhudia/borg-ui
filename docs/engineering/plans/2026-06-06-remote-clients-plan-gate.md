# Remote Clients Plan Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development for implementation and
> superpowers:verification-before-completion before claiming completion. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate Remote Clients to Pro and Enterprise plans while keeping local
server access available for every plan.

**Architecture:** Add a shared `remote_clients` Pro-minimum feature key, then
reuse the existing `usePlan` and `PlanGate` primitives in the Remote Clients
route, sidebar navigation, and global server target switcher. Selector logic
will treat local targets separately from remote targets so Community users can
always return to or stay on this server.

**Tech Stack:** FastAPI feature catalog, React, TypeScript, MUI, lucide-react,
Vitest, Storybook.

---

## Task 1: Reproduction and Failing Tests

**Files:**

- Modify: `frontend/src/components/__tests__/AppSidebar.test.tsx`
- Modify: `frontend/src/pages/__tests__/RemoteClients.test.tsx`
- Modify: `frontend/src/components/__tests__/BackendTargetSwitcher.test.tsx`
- Modify if backend feature key is added: `tests/unit/test_core_features.py`

- [ ] Add a failing sidebar test proving Community users with SSH management
      permission do not see the Remote Clients link.
- [ ] Add a failing Remote Clients page test proving Community users see the
      plan gate instead of the management controls.
- [ ] Add a failing server switcher test proving Community users can keep local
      server access but cannot switch to a compatible remote client.
- [ ] Add a failing server switcher test proving Community users cannot open
      Remote Clients management from the global selector.
- [ ] Add a backend feature-catalog assertion if `remote_clients` is added to
      `app/core/features.py`.
- [ ] Run the targeted tests and record the red evidence.

## Task 2: Shared Entitlement Key

**Files:**

- Modify: `app/core/features.py`
- Modify: `frontend/src/core/features.ts`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Add `remote_clients` as a Pro feature in backend and frontend catalogs.
- [ ] Add Remote Clients-specific upgrade copy under existing locale sections.
- [ ] Keep the feature key name consistent across backend, frontend, tests, and
      analytics surfaces.

## Task 3: Gate Navigation and Management

**Files:**

- Modify: `frontend/src/components/AppSidebar.tsx`
- Modify: `frontend/src/pages/RemoteClients.tsx`
- Modify: `docs/navigation.md`
- Modify: `docs/remote-clients.md`

- [ ] Read `can('remote_clients')` in the sidebar and hide the Remote Clients
      nav item when the plan lacks access.
- [ ] Wrap `RemoteClientsContent` in `PlanGate feature="remote_clients"` after
      the existing permission check.
- [ ] Use a Remote Clients-specific fallback copy that points to upgrading to
      Pro.
- [ ] Update user docs to say Remote Clients require Pro or Enterprise and that
      this server remains available locally.

## Task 4: Gate Global Server Selection

**Files:**

- Modify: `frontend/src/components/BackendTargetSwitcher.tsx`
- Modify if needed: `frontend/src/components/backendTargetPresentation.tsx`
- Modify if needed: `frontend/src/components/BackendTargetSwitcher.stories.tsx`

- [ ] Use `can('remote_clients')` in the switcher.
- [ ] Leave the local target enabled for every plan.
- [ ] Disable remote target menu items when the plan lacks access, even if the
      remote target is otherwise compatible.
- [ ] Replace the manage-menu action with a disabled upgrade item for denied
      plans, so clicking it cannot navigate silently.
- [ ] Preserve the existing incompatible-client disabled state for all plans.

## Task 5: Stories and Final Validation

**Files:**

- Modify: `frontend/src/pages/RemoteClients.stories.tsx`
- Modify: `frontend/src/components/BackendTargetSwitcher.stories.tsx`

- [ ] Add locked Community stories for the Remote Clients page and global
      switcher.
- [ ] Run targeted Vitest tests for sidebar, management, switcher, and backend
      feature catalog if touched.
- [ ] Run required frontend validation: locales, typecheck, lint, build.
- [ ] Run backend validation required by changed backend files.
- [ ] Run a local runtime walkthrough for denied and allowed user paths.
- [ ] Commit, push, create/update PR from the repository template, add the
      `symphony` label, sweep PR feedback/checks, update the workpad handoff,
      and move the issue to Human Review only when all gates are green.
