# Managed Agent Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a managed-agent diagnostics action that verifies live session health and optional TCP reachability through the outbound agent session.

**Architecture:** Add an ephemeral `diagnostics.run` session command and a managed-machine API endpoint that validates input, snapshots agent metadata, sends the command over `agent_connection_manager`, and returns normalized result states. Add a focused React dialog opened from each Managed Agents card, reusing the existing page/test/story structure and `ResponsiveDialog`.

**Tech Stack:** FastAPI, Pydantic, pytest, WebSocket session command manager, Python socket APIs, React, TypeScript, MUI, Lucide, TanStack Query, Vitest, Storybook.

---

### Task 1: Backend Diagnostics Endpoint

**Files:**
- Modify: `tests/unit/test_api_managed_machines.py`
- Modify: `app/api/managed_machines.py`

- [ ] **Step 1: Write failing backend tests**

  Add tests that post to `/api/managed-machines/agents/{agent.id}/diagnostics`
  and cover:

  - live-session success with no target and no `AgentJob` row;
  - live-session success with a TCP target result returned from the agent;
  - offline agent response with `session.status == "offline"`;
  - session command timeout response with `session.status == "timeout"`;
  - invalid target host/port/timeout returns 422;
  - agent-returned TCP failure stays HTTP 200 with `tcp.status == "failed"`.

- [ ] **Step 2: Run backend tests and confirm red**

  Run:

  ```bash
  pytest tests/unit/test_api_managed_machines.py -q -k diagnostic
  ```

  Expected before implementation: tests fail because the diagnostics endpoint
  and response contract do not exist.

- [ ] **Step 3: Implement the endpoint**

  Add Pydantic request/response models in `app/api/managed_machines.py`.
  Validate target host, port, and timeout before dispatch. Use
  `agent_connection_manager.send_command(agent.id, command="diagnostics.run",
  payload={...}, timeout_seconds=..., wait_for_result=True)` and map:

  - `AgentConnectionUnavailable` -> HTTP 200 with `session.status = "offline"`;
  - `AgentCommandTimeout` -> HTTP 200 with `session.status = "timeout"`;
  - `AgentCommandError` -> HTTP 200 with `session.status = "failed"`;
  - returned payload -> HTTP 200 with normalized session/TCP result objects.

- [ ] **Step 4: Re-run backend tests**

  Run:

  ```bash
  pytest tests/unit/test_api_managed_machines.py -q -k diagnostic
  ```

  Expected after implementation: targeted diagnostics tests pass.

### Task 2: Agent Diagnostics Command Handler

**Files:**
- Modify: `tests/unit/test_agent_runtime.py`
- Modify: `agent/borg_ui_agent/runtime.py`
- Modify: `agent/borg_ui_agent/session.py`

- [ ] **Step 1: Write failing agent tests**

  Add tests that:

  - assert `diagnostics.run` is advertised in `get_capabilities()`;
  - run a session command with no target and assert a success result with
    elapsed milliseconds;
  - run a session command with a TCP target and a mocked socket connection that
    succeeds;
  - run a session command with a mocked socket failure and assert normalized
    failed TCP result.

- [ ] **Step 2: Run agent tests and confirm red**

  Run:

  ```bash
  pytest tests/unit/test_agent_runtime.py -q -k diagnostic
  ```

  Expected before implementation: tests fail because the capability and handler
  do not exist.

- [ ] **Step 3: Implement agent handler**

  Add `diagnostics.run` to `DEFAULT_CAPABILITIES`. In
  `AgentSessionRuntime._handle_command`, route `diagnostics.run` to a helper
  that measures elapsed time with `time.monotonic()`, optionally calls
  `socket.create_connection((host, port), timeout=timeout_seconds)`, closes the
  socket, and returns normalized results. Keep all network calls mockable by
  referencing the imported socket module.

- [ ] **Step 4: Re-run agent tests**

  Run:

  ```bash
  pytest tests/unit/test_agent_runtime.py -q -k diagnostic
  ```

  Expected after implementation: targeted agent tests pass.

### Task 3: Frontend API Types and Diagnostics Dialog

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/pages/ManagedAgents.tsx`
- Modify: `frontend/src/pages/__tests__/ManagedAgents.test.tsx`

- [ ] **Step 1: Write failing frontend tests**

  Extend the Managed Agents API mock with `runDiagnostics`. Add tests for:

  - agent card exposes "Run diagnostics";
  - clicking it opens the dialog and runs session-only diagnostics;
  - loading state disables only the dialog run button;
  - success state displays metadata and elapsed session timing;
  - partial failure displays successful session plus failed TCP result;
  - offline and timeout results display clear status copy.

- [ ] **Step 2: Run frontend tests and confirm red**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/__tests__/ManagedAgents.test.tsx --run -t "diagnostic"
  ```

  Expected before implementation: tests fail because the API method, action, and
  dialog do not exist.

- [ ] **Step 3: Implement frontend behavior**

  Add request/response TypeScript types and
  `managedAgentsAPI.runDiagnostics(agentId, payload)`. Add
  `AgentDiagnosticsDialog` using `ResponsiveDialog`, text fields for optional
  host/port/timeout, status rows, role-aware error/success feedback, and a
  retry-capable run button. Add a compact card icon action with Lucide icon and
  tooltip, leaving logs, reinstall, revoke, and delete independent.

- [ ] **Step 4: Re-run frontend tests**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/__tests__/ManagedAgents.test.tsx --run -t "diagnostic"
  ```

  Expected after implementation: targeted diagnostics frontend tests pass.

### Task 4: Storybook and User Docs

**Files:**
- Modify: `frontend/src/pages/ManagedAgents.stories.tsx`
- Modify: `docs/managed-agents.md`

- [ ] **Step 1: Add Storybook states**

  Add stories that show diagnostics success, partial TCP failure, and offline or
  timeout dialog states. Do not commit generated Argos screenshots.

- [ ] **Step 2: Update docs**

  Add a concise Managed Agents diagnostics section explaining where the action
  lives, what the session check proves, what optional TCP target checks prove,
  and that the feature uses outbound agent sessions only.

### Task 5: Required Validation and Publish

**Files:**
- Inspect: `.github/PULL_REQUEST_TEMPLATE.md`

- [ ] **Step 1: Run targeted validation**

  Run:

  ```bash
  pytest tests/unit/test_api_managed_machines.py -q -k diagnostic
  pytest tests/unit/test_agent_runtime.py -q -k diagnostic
  cd frontend && npm run test -- src/pages/__tests__/ManagedAgents.test.tsx --run -t "diagnostic"
  ```

- [ ] **Step 2: Run required backend checks**

  Run:

  ```bash
  ruff check app tests
  ruff format --check app tests
  ```

- [ ] **Step 3: Run required frontend checks**

  Run:

  ```bash
  cd frontend && npm run check:locales
  cd frontend && npm run typecheck
  cd frontend && npm run lint
  cd frontend && npm run build
  ```

- [ ] **Step 4: Capture runtime evidence**

  Launch Borg UI locally with an available smoke/dev path and verify the
  Managed Agents page can open the diagnostics dialog, submit a session check,
  and show a result without blocking other card actions.

- [ ] **Step 5: Commit, push, PR, and Linear handoff**

  Commit the focused diff, push the branch, create/update a PR using
  `.github/PULL_REQUEST_TEMPLATE.md`, attach it to Linear, sweep PR feedback and
  checks, update this ticket workpad with validation evidence and handoff note,
  then move the issue to Human Review only when the completion bar is met.
