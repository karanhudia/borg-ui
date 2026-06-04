# Managed Agent Reinstall Action Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tokenless reinstall/update command and card action for enrolled Borg UI managed agents.

**Architecture:** Extend the existing public installer script with a `--reinstall` mode that preserves the local agent config and skips registration. Add a React card action and dialog that builds a tokenless reinstall command from the same server URL used by the Add Agent flow.

**Tech Stack:** FastAPI, shell installer, pytest, React, TypeScript, MUI, Vitest, Storybook snapshots.

---

### Task 1: Backend Reinstall Script Mode

**Files:**
- Modify: `tests/unit/test_agent_installer_api.py`
- Modify: `app/api/agent_installer.py`

- [ ] **Step 1: Write the failing backend test**

Add a test asserting that `/agent/install.sh` documents `--reinstall`, requires an existing config for reinstall mode, preserves registration, and has a reinstall branch that does not call `register`.

- [ ] **Step 2: Run the backend test and confirm failure**

Run:

```bash
pytest tests/unit/test_agent_installer_api.py -q
```

Expected before implementation: the new reinstall assertions fail because the script has no `--reinstall` mode.

- [ ] **Step 3: Implement the installer changes**

Update `INSTALLER_SCRIPT` so:

- `REINSTALL="0"` is parsed from `--reinstall`.
- Initial install still requires `--server`, `--token`, and `--name`.
- Reinstall mode requires `/etc/borg-ui-agent/config.toml`, does not require token/name/server, and prints that registration is being preserved.
- Borg installation defaults to `--borg-version 1` for initial installs and skip for reinstall unless `--borg-version` is explicitly provided.
- The script installs/updates the agent virtualenv, skips `borg-ui-agent register` during reinstall, runs `service-check`, reloads systemd, enables the unit, and restarts the service.

- [ ] **Step 4: Re-run backend tests**

Run:

```bash
pytest tests/unit/test_agent_installer_api.py -q
```

Expected after implementation: all installer tests pass.

### Task 2: Frontend Reinstall Command and Card Dialog

**Files:**
- Modify: `frontend/src/pages/managed-agents/agentInstallCommandText.ts`
- Modify: `frontend/src/pages/ManagedAgents.tsx`
- Modify: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`
- Modify: `frontend/src/pages/ManagedAgents.stories.tsx`

- [ ] **Step 1: Write failing frontend tests**

Add tests that:

- call a new reinstall command builder and assert the command contains `/agent/install.sh` and `--reinstall`;
- assert it does not contain `--token`, `<enrollment-token>`, `--name`, or `register`;
- render an agent card, click "Reinstall agent", verify the dialog copy, and verify the copy action returns the tokenless command.

- [ ] **Step 2: Run the frontend test and confirm failure**

Run:

```bash
cd frontend && npm run test -- src/pages/__tests__/ManagedAgents.test.tsx --run -t "reinstall"
```

Expected before implementation: tests fail because the builder/action/dialog do not exist.

- [ ] **Step 3: Implement frontend behavior**

Add `buildAgentReinstallCommand(serverUrl)` and an exported `AgentReinstallDialog`. Extend `AgentList` with `serverUrl` and `onCopy` props, add the icon button, and wire the page to pass `defaultAgentServerUrl` plus the existing clipboard handler.

- [ ] **Step 4: Update Storybook**

Update `FleetOverview` to pass the new props and add an `AgentReinstallDialogOpen` story that shows the copyable reinstall command for an existing agent.

- [ ] **Step 5: Re-run targeted frontend tests**

Run:

```bash
cd frontend && npm run test -- src/pages/__tests__/ManagedAgents.test.tsx --run
```

Expected after implementation: Managed Agents tests pass.

### Task 3: User Documentation and Verification

**Files:**
- Modify: `docs/managed-agents.md`
- Generated: `frontend/storybook-snapshots/pages-managedagents--agent-reinstall-dialog-open.png`

- [ ] **Step 1: Update user docs**

Add a "Reinstall or Update an Existing Agent" section explaining that the card
action provides a tokenless `--reinstall` command that preserves local
credentials and restarts the service.

- [ ] **Step 2: Run required checks**

Run:

```bash
ruff check app tests
ruff format --check app tests
pytest tests/unit/test_agent_installer_api.py -q
cd frontend && npm run check:locales
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
cd frontend && npm run snapshots
```

- [ ] **Step 3: Run local walkthrough**

Launch Borg UI locally and verify the Managed Agents fleet story/app surface shows an existing agent card with a reinstall action that opens a tokenless command.
