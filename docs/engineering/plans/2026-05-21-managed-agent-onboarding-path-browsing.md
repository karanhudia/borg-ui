# Managed Agent Onboarding And Path Browsing Implementation Plan

> **For agentic workers:** Use `superpowers:test-driven-development` for each
> behavior change and `superpowers:verification-before-completion` before
> claiming completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver one-command Linux managed-agent enrollment and shared
agent-aware path browsing across Managed Agents, Repository Wizard, and Backup
Plans.

**Architecture:** Add a small unauthenticated installer router, extend the
managed-machines API contract without breaking existing minute-based token
creation, and soft-delete agents by status/timestamp. On the frontend, extract
managed-agent onboarding into focused components/helpers and extend the shared
path selector to understand `agent` browse contexts.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, MUI, TanStack Query,
Vitest, Storybook, `borg-ui-agent`.

---

### Task 1: Installer Endpoint

**Files:**
- Create: `app/api/agent_installer.py`
- Modify: `app/main.py`
- Create: `tests/unit/test_agent_installer_api.py`

- [ ] Write failing tests for unauthenticated `GET /agent/install.sh`, content
  type, required command snippets, systemd enable/start, and no hardcoded
  `borgui_enroll_` token.
- [ ] Implement the installer router returning a static generated shell script.
- [ ] Register the router outside the authenticated `/api` dependency stack.
- [ ] Run `pytest tests/unit/test_agent_installer_api.py -q`.

### Task 2: Enrollment Expiry And Agent Delete

**Files:**
- Modify: `app/api/managed_machines.py`
- Modify: `app/api/agents.py`
- Modify: `app/core/agent_auth.py`
- Modify: `app/database/models.py`
- Create: `app/database/migrations/112_add_agent_deleted_at.py` if the schema
  needs a durable `deleted_at` column.
- Modify: `tests/unit/test_api_managed_machines.py`
- Modify: `tests/unit/test_api_agents.py`

- [ ] Write failing tests for 7-day token creation, never-expiring token
  creation, backwards-compatible `expires_in_minutes`, expired token rejection,
  revoked token rejection, delete hiding list results, deleted/revoked polling
  rejection, and job log readability after delete.
- [ ] Add nullable `expires_at` response models and expiry payload fields.
- [ ] Validate expiry values with a 5-minute minimum for expiring tokens.
- [ ] Soft-delete agents using `status = "deleted"` plus `deleted_at` when a
  durable column is needed.
- [ ] Filter deleted agents from active list responses and block deleted agents
  in agent auth and queueing paths.
- [ ] Run
  `pytest tests/unit/test_api_agents.py tests/unit/test_api_managed_machines.py -q`.

### Task 3: Shared Agent Path Browsing

**Files:**
- Modify: `frontend/src/components/PathSelectorField.tsx`
- Modify: `frontend/src/components/FileExplorerDialog.tsx` only if required for
  a shared agent adapter.
- Modify: `frontend/src/components/wizard/WizardStepLocation.tsx`
- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/components/__tests__/PathSelectorField.test.tsx`
- Modify: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`
- Modify: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`

- [ ] Write failing tests proving repository browse is enabled after selecting
  an agent and calls `managedAgentsAPI.browseFilesystem`.
- [ ] Write failing tests proving backup-plan agent browsing uses the shared
  path selector/browser path instead of the bespoke dialog behavior.
- [ ] Extend the shared path selector with `connectionType: "agent"` and an
  `agentId` browse target while keeping local/SSH behavior unchanged.
- [ ] Replace repository wizard inline browse disabling with agent-aware browse
  enablement.
- [ ] Replace backup-plan `AgentFileExplorerDialog` with the shared field or
  shared browser adapter.
- [ ] Run the targeted frontend tests for the touched components.

### Task 4: Managed Agents Add Agent Wizard

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/pages/ManagedAgents.tsx`
- Create: `frontend/src/pages/managed-agents/agentServerUrl.ts`
- Create: `frontend/src/pages/managed-agents/AgentInstallCommand.tsx`
- Create: `frontend/src/pages/managed-agents/AddAgentDialog.tsx`
- Modify: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`

- [ ] Write failing tests for backend URL derivation from absolute API URL and
  relative `/api` on local dev.
- [ ] Write failing tests for opening Add Agent, delaying token creation until
  confirmation, command generation, localhost warning, waiting success,
  revoke, delete call, and delete confirmation.
- [ ] Add the API client contracts for new token expiry payloads and
  `DELETE /managed-machines/agents/{id}`.
- [ ] Build the wizard with Linux/Raspberry Pi selected by default and macOS /
  Windows marked coming later.
- [ ] Use the generated backend URL in the one-line `curl ... install.sh`
  command.
- [ ] Add polling/waiting state that changes to success when a new agent
  appears.
- [ ] Add revoke/delete actions with confirmation copy.
- [ ] Run `cd frontend && npm test -- ManagedAgents.test.tsx --run`.

### Task 5: Stories, Snapshots, And Docs

**Files:**
- Modify: `frontend/src/pages/ManagedAgents.stories.tsx`
- Update: `frontend/storybook-snapshots/**`
- Modify: `agent/README.md`
- Modify: `docs/managed-agents.md`

- [ ] Add stories for fleet overview, platform step, install command, waiting,
  localhost warning, and delete confirmation.
- [ ] Run `cd frontend && npm run snapshots` and keep generated snapshots.
- [ ] Update docs to lead with one-command Linux install and explain manual
  setup, token expiry, permanent credentials, revoke/delete, and localhost.

### Task 6: Final Verification And Handoff

**Files:**
- Update PR metadata using `.github/PULL_REQUEST_TEMPLATE.md`.

- [ ] Run
  `pytest tests/unit/test_api_agents.py tests/unit/test_api_managed_machines.py tests/unit/test_agent_installer_api.py -q`.
- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run `cd frontend && npm test -- ManagedAgents.test.tsx --run`.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run `cd frontend && npm run snapshots`.
- [ ] Launch Borg UI locally or use an available smoke runner to capture
  runtime evidence for Add Agent and repository agent path browse.
- [ ] Run `git diff --check`.
- [ ] Commit, push, create/update PR, attach it to Linear, add `symphony`, sweep
  PR comments/checks, and move Linear to `Human Review` only when green.
