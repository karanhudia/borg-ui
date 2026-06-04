# BOR-52 Agent Browsing Refinements Implementation Plan

> **For agentic workers:** Use `superpowers:test-driven-development` for each
> behavior change and `superpowers:verification-before-completion` before
> claiming completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce repeat managed-agent browsing latency, remove Raspberry
Pi-specific wording from user-facing setup surfaces, and align managed-agent
copy button styling with the app UI.

**Architecture:** Keep the backend agent browse timeout as the safety boundary
for fresh uncached requests. Add a dialog-local cache in the shared file
explorer for successful managed-agent browse results so revisiting checked
paths is immediate and does not enqueue another job. Update managed-agent copy
and Storybook fixtures in place without broad UI restructuring.

**Tech Stack:** React, MUI, Vitest, Storybook, FastAPI/pytest for unchanged
backend contract validation.

---

### Task 1: Agent Browse Cache

**Files:**
- Modify: `frontend/src/components/FileExplorerDialog.tsx`
- Modify: `frontend/src/components/__tests__/FileExplorerDialog.test.tsx`

- [x] Write a failing Vitest case proving an agent directory is served from
  cache when revisited through breadcrumbs.
- [x] Extend the existing service mock to include `managedAgentsAPI`.
- [x] Add a successful-response cache keyed by connection type, agent id, path,
  and hidden-file setting.
- [x] Populate `items`, `currentPath`, and `isInsideLocalMount` from cache
  without setting the loading spinner or issuing another request.
- [x] Clear the cache when the dialog fully closes or its browse identity
  changes.
- [x] Run
  `cd frontend && npm test -- FileExplorerDialog.test.tsx --run`.

### Task 2: Managed Agent Setup Copy And Button Styling

**Files:**
- Modify: `frontend/src/pages/ManagedAgents.tsx`
- Modify: `frontend/src/pages/managed-agents/AddAgentDialog.tsx`
- Modify: `frontend/src/pages/managed-agents/AgentInstallCommand.tsx`
- Modify: `frontend/src/pages/ManagedAgents.stories.tsx`
- Modify: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`
- Modify: `docs/managed-agents.md`

- [x] Write failing tests proving setup help no longer renders `Raspberry Pi`
  and still supports copy actions.
- [x] Replace setup copy with generic Linux/client-machine wording.
- [x] Change the add-agent platform card label from `Linux / Raspberry Pi` to
  `Linux`.
- [x] Rename Storybook example agent names away from Raspberry Pi-specific
  wording.
- [x] Adjust copy button styling to use theme primary-tinted background,
  primary border, visible focus, and hover tokens with sufficient contrast.
- [x] Run `cd frontend && npm test -- ManagedAgents.test.tsx --run`.

### Task 3: Storybook Snapshots

**Files:**
- Update: `frontend/storybook-snapshots/pages-managedagents--*.png`

- [x] Run `cd frontend && npm run snapshots`.
- [x] Inspect generated Managed Agents snapshots for generic Linux copy and
  copy button color alignment.

### Task 4: Final Verification And Handoff

**Files:**
- Update PR metadata using `.github/PULL_REQUEST_TEMPLATE.md`.

- [x] Run `git diff --check`.
- [x] Run frontend validation:
  `cd frontend && npm run check:locales`,
  `cd frontend && npm run typecheck`,
  `cd frontend && npm run lint`, and
  `cd frontend && npm run build`.
- [x] If backend files remain untouched, record backend validation as not
  applicable; otherwise run `ruff check app tests`,
  `ruff format --check app tests`, and relevant pytest paths.
- [x] Run a Borg UI runtime walkthrough for add-agent/Linux setup copy, copy
  button behavior, and managed-agent directory revisit behavior.
- [ ] Merge latest `origin/main` into the branch, rerun applicable checks,
  commit, push, create/update PR with template, attach PR to Linear, and add
  the `symphony` label.
- [ ] Sweep PR feedback and checks before moving BOR-52 to `Human Review`.
