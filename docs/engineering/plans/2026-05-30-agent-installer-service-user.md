# Agent Installer Service User Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Linux managed-agent installs run as the sudo-invoking user by default, with explicit dedicated-user and root service modes.

**Architecture:** Extend the installer shell script served by FastAPI with service-user resolution helpers, then thread the selected mode through the Add Agent command builder and wizard. Keep filesystem permissions tied to the selected OS user instead of granting broad path permissions.

**Tech Stack:** FastAPI shell-script fixture tests, React/MUI Add Agent wizard, Vitest, Storybook snapshots, Markdown docs.

---

## Task 1: Installer Contract

**Files:**
- Modify: `tests/unit/test_agent_installer_api.py`
- Modify: `app/api/agent_installer.py`

- [ ] Add tests asserting the installer advertises `--service-user`, defaults to `current`, resolves `SUDO_USER`, refuses direct-root current mode, supports `borg-ui-agent`, supports `root`, validates explicit users, and writes `User=${SERVICE_USER}`, `Group=${SERVICE_GROUP}`, and `WorkingDirectory=${SERVICE_HOME}`.
- [ ] Run `pytest tests/unit/test_agent_installer_api.py -q` and confirm the new tests fail because the script has no service-user support.
- [ ] Add shell variables `SERVICE_USER_MODE="current"`, `SERVICE_USER=""`, `SERVICE_GROUP=""`, and `SERVICE_HOME=""`.
- [ ] Add argument parsing for `--service-user MODE_OR_USERNAME`.
- [ ] Add helper functions inside the installer script:
  - `resolve_user_group_home USERNAME`
  - `resolve_current_service_user`
  - `resolve_service_identity`
- [ ] Change directory creation so `/etc/borg-ui-agent` is owned by the selected service user/group, `/var/lib/borg-ui-agent` is created only for dedicated mode, and `/opt/borg-ui-agent` remains root-owned.
- [ ] Change registration from `runuser -u borg-ui-agent -- ...` to `runuser -u "${SERVICE_USER}" -- ...`.
- [ ] Change generated systemd unit to use selected user/group/home.
- [ ] Change `service-check` arguments to use selected user/group.
- [ ] Run `pytest tests/unit/test_agent_installer_api.py -q` and confirm the suite passes.

## Task 2: Install Command Builder And Wizard UI

**Files:**
- Modify: `frontend/src/pages/managed-agents/agentInstallCommandText.ts`
- Modify: `frontend/src/pages/managed-agents/AddAgentDialog.tsx`
- Modify: `frontend/src/pages/managed-agents/AgentInstallCommand.tsx` if prop threading requires it.
- Modify: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`

- [ ] Add Vitest coverage for `buildAgentInstallCommand()` showing default current-user mode omits extra args, dedicated mode emits `--service-user borg-ui-agent`, and root mode emits `--service-user root`.
- [ ] Run `cd frontend && npm test -- ManagedAgents.test.tsx --runInBand` or the repo's equivalent focused Vitest command and confirm the new assertions fail.
- [ ] Add `AgentServiceUserMode = 'current' | 'dedicated' | 'root'` and service-user argument generation in `agentInstallCommandText.ts`.
- [ ] Add service-user state to `AddAgentDialog`, defaulting to `current`.
- [ ] Add a "Service user" radio group in the Details step with:
  - Installing user, selected by default.
  - Dedicated `borg-ui-agent` user.
  - Root, with warning copy.
- [ ] Pass the selected service-user mode into `AgentInstallCommand`.
- [ ] Run the focused frontend tests and confirm they pass.

## Task 3: Storybook Stories And Snapshots

**Files:**
- Modify: `frontend/src/pages/ManagedAgents.stories.tsx`
- Update generated: `frontend/storybook-snapshots/*.png`

- [ ] Update the Add Agent Borg/options story so the Details step shows the service-user choice.
- [ ] Add or adjust a story showing root mode selected and warning copy visible.
- [ ] Run `cd frontend && npm run snapshots`.
- [ ] Inspect changed snapshots for readable layout and no overlapping text.

## Task 4: Documentation

**Files:**
- Modify: `agent/README.md`
- Modify: `docs/managed-agents.md`
- Modify: `docs/navigation.md` only if wizard flow names change.

- [ ] Update one-command install docs to explain that the service runs as the sudo-invoking user by default.
- [ ] Document `--service-user current`, `--service-user borg-ui-agent`, `--service-user root`, and explicit existing usernames.
- [ ] Explain that repository paths must be writable by the selected service user.
- [ ] Explain root mode is for backing up root-owned paths and should be used deliberately.

## Task 5: Final Verification

**Files:**
- Verify touched files.

- [ ] Run `.venv311/bin/python -m pytest tests/unit/test_agent_installer_api.py -q`.
- [ ] Run `.venv311/bin/python -m pytest tests/unit/test_api_repositories.py::TestRepositoriesCreate -q` to ensure the earlier repo-init wait fix still passes.
- [ ] Run `cd frontend && npm test -- ManagedAgents.test.tsx`.
- [ ] Run `cd frontend && npm run snapshots`.
- [ ] Run `.venv311/bin/python -m ruff check app/api/agent_installer.py tests/unit/test_agent_installer_api.py`.
- [ ] Run `.venv311/bin/python -m ruff format --check app/api/agent_installer.py tests/unit/test_agent_installer_api.py`.
- [ ] Run `git diff --check`.
