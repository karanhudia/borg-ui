# Borg Installer Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install and verify Borg from managed-agent setup with Borg 1 as the
default, advanced Borg 2 choices, and UI/reporting that exposes missing binaries.

**Architecture:** Keep the installer served from `app/api/agent_installer.py`,
extend the existing Add Agent wizard command builder, and enrich the agent's
existing Borg binary detection payload. The installer remains a plain bash
script, but the shell variables are separated so OS release metadata cannot
overwrite the agent Git ref.

**Tech Stack:** FastAPI response fixture, bash installer script, Python agent
stdlib detection, pytest, React/TypeScript, MUI, Vitest, Storybook.

---

### Task 1: Reproduce And Guard Installer Regression

**Files:**

- Modify: `tests/unit/test_agent_installer_api.py`
- Modify: `app/api/agent_installer.py`

- [ ] **Step 1: Write failing tests**

Add tests that assert the served script keeps the pip Git ref in an
`AGENT_REF` variable, does not use `${VERSION}` for pip install, includes the
new Borg install options in usage, and passes `bash -n`.

Run:

```bash
pytest tests/unit/test_agent_installer_api.py -q
```

Expected result before implementation: tests fail because the script uses
`VERSION`, lacks Borg option parsing, and includes no install-mode logic.

- [ ] **Step 2: Fix the installer variable collision**

Rename the agent source ref variable to `AGENT_REF`, keep `--version` as the
public option for compatibility, and install with:

```bash
"git+https://github.com/karanhudia/borg-ui.git@${AGENT_REF}"
```

- [ ] **Step 3: Add Borg install mode parsing and verification**

Add `BORG_VERSION="1"` and `SKIP_BORG_INSTALL="0"`. Parse
`--borg-version 1|2|both` and `--skip-borg-install`. Add shell helpers that
install selected missing binaries and verify `borg --version` or
`borg2 --version` reports the expected major before registration runs.

### Task 2: Agent Binary Reporting

**Files:**

- Modify: `agent/borg_ui_agent/borg.py`
- Modify: `tests/unit/test_agent_runtime.py`

- [ ] **Step 1: Write failing payload test**

Update `test_detect_borg_binaries` so each payload includes `install_source`,
for example:

```python
{"major": 1, "version": "1.2.8", "path": "/usr/bin/borg", "install_source": "system-package"}
```

Run:

```bash
pytest tests/unit/test_agent_runtime.py::test_detect_borg_binaries -q
```

Expected result before implementation: fails because `install_source` is absent.

- [ ] **Step 2: Implement source classification**

Add `install_source` to `BorgBinary` and classify paths under `/usr/bin` or
`/usr/sbin` as `system-package`, paths resolving under `/opt/borg-ui-agent` as
`borg-ui-installer`, and everything else as `custom-path`.

### Task 3: Add Agent UI Options And Warning

**Files:**

- Modify: `frontend/src/pages/managed-agents/agentInstallCommandText.ts`
- Modify: `frontend/src/pages/managed-agents/AddAgentDialog.tsx`
- Modify: `frontend/src/pages/managed-agents/AgentInstallCommand.tsx`
- Modify: `frontend/src/pages/ManagedAgents.tsx`
- Modify: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`
- Modify: `frontend/src/pages/ManagedAgents.stories.tsx`

- [ ] **Step 1: Write failing frontend tests**

Add coverage showing the default Add Agent command includes `--borg-version 1`,
selecting the Borg 2 beta option changes the command to `--borg-version 2`, and
an agent with an empty `borg_versions` list shows a warning.

Run:

```bash
cd frontend && npm run test -- ManagedAgents.test.tsx --run
```

Expected result before implementation: fails because there are no Borg install
radio controls, the command has no Borg flag, and empty Borg data renders as a
dash only.

- [ ] **Step 2: Implement radio-style choices**

Add a `BorgInstallMode` type with `borg1`, `borg2`, `both`, and `skip`. Render a
radio group in the Details step. Keep Borg 1 selected by default. Label Borg 2
and both modes as beta/experimental.

- [ ] **Step 3: Generate the correct command**

Update `buildAgentInstallCommand()` to append `--borg-version 1`,
`--borg-version 2`, `--borg-version both`, or `--skip-borg-install` based on the
chosen mode.

- [ ] **Step 4: Warn when no usable Borg binary exists**

Replace the plain dash-only Borg value with a warning surface on the agent card
when `borg_versions` is empty or absent.

- [ ] **Step 5: Update Storybook**

Add or update a Managed Agents story that opens the Add Agent dialog on the
Details step so reviewers can see the Borg install choices.

### Task 4: Validation And Handoff

- [ ] Run targeted backend tests:

```bash
pytest tests/unit/test_agent_installer_api.py tests/unit/test_agent_runtime.py::test_detect_borg_binaries -q
```

- [ ] Run targeted frontend tests:

```bash
cd frontend && npm run test -- ManagedAgents.test.tsx --run
```

- [ ] Run required backend checks:

```bash
ruff check app tests
ruff format --check app tests
```

- [ ] Run required frontend checks:

```bash
cd frontend && npm run check:locales
cd frontend && npm run typecheck
cd frontend && npm run lint
cd frontend && npm run build
cd frontend && npm run snapshots
```

- [ ] Run runtime/script proof:

```bash
bash -n /tmp/generated-agent-install.sh
bash -c 'AGENT_REF=main; . /etc/os-release; test "$AGENT_REF" = main'
```

- [ ] Commit, push, open the PR with the repository template, attach/link it to
      Linear, sweep PR comments/checks, and move the issue to Human Review only when
      green.
