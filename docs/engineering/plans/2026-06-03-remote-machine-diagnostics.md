# Remote Machine Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Remote Machine diagnostics action with SSH health, latency, optional remote TCP reachability, and bounded SSH transport throughput results.

**Architecture:** Extend the existing SSH keys/Remote Machines API and page. Backend diagnostics stay ephemeral, validate all user inputs, reuse existing SSH key resolution patterns, and normalize per-probe results. Frontend state stays in `SSHConnectionsSingleKey.tsx`, rendering stays in the existing view/card/dialog split, and result states are covered by Vitest and Storybook.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, pytest, OpenSSH subprocesses, React, TypeScript, MUI, Lucide, TanStack Query, Vitest, Storybook.

---

### Task 1: Backend Failing Tests

**Files:**
- Modify: `tests/unit/test_api_ssh_keys.py`

- [ ] **Step 1: Add diagnostics response tests**

  Add tests that create a system `SSHKey` and `SSHConnection`, patch the new
  diagnostics runner helper, and post to:

  ```text
  /api/ssh-keys/connections/{connection.id}/diagnostics
  ```

  Cover:

  - success with `session.status == "success"`, `latency.status == "success"`,
    `tcp.status == "success"`, and `throughput.mbps` present;
  - failed TCP check remains HTTP 200 with `tcp.status == "failed"`;
  - command timeout returns HTTP 200 with `session.status == "timeout"` and no
    throughput value;
  - invalid host, port, timeout, and speed probe size return 422;
  - missing connection returns 404.

- [ ] **Step 2: Run red backend tests**

  Run:

  ```bash
  pytest tests/unit/test_api_ssh_keys.py -q -k diagnostic
  ```

  Expected before implementation: tests fail because the endpoint and helper
  do not exist.

### Task 2: Backend Implementation

**Files:**
- Modify: `app/api/ssh_keys.py`

- [ ] **Step 1: Add request models and constants**

  Add Pydantic models near the existing SSH connection models:

  ```python
  class SSHDiagnosticTarget(BaseModel):
      host: str
      port: int = Field(ge=1, le=65535)
      timeout_seconds: float = Field(default=3.0, ge=0.5, le=15.0)

      @field_validator("host")
      @classmethod
      def normalize_host(cls, value: str) -> str:
          return normalize_ssh_host(value)

  class SSHConnectionDiagnosticsRequest(BaseModel):
      target: Optional[SSHDiagnosticTarget] = None
      timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)
      speed_probe_bytes: int = Field(default=262144, ge=65536, le=5242880)
  ```

- [ ] **Step 2: Add SSH diagnostics helpers**

  Implement helpers for:

  - writing the SSH key to a temporary file with `write_ssh_key_to_tempfile`;
  - building the base SSH argument list;
  - running a subprocess with `asyncio.create_subprocess_exec`;
  - normalizing return-code errors and timeouts;
  - calculating elapsed milliseconds and MB/s.

  Keep user inputs validated before passing them into subprocess args.

- [ ] **Step 3: Add the diagnostics endpoint**

  Add:

  ```python
  @router.post("/connections/{connection_id}/diagnostics")
  async def run_connection_diagnostics(...):
      ...
  ```

  Resolve the connection, use the same system-key fallback as
  `test_existing_connection`, run diagnostics, and return the normalized
  response. Do not update the persisted connection status from this endpoint.

- [ ] **Step 4: Run backend tests green**

  Run:

  ```bash
  pytest tests/unit/test_api_ssh_keys.py -q -k diagnostic
  ```

### Task 3: Frontend Failing Tests

**Files:**
- Modify: `frontend/src/pages/__tests__/SSHConnectionsSingleKey.test.tsx`
- Modify: `frontend/src/components/__tests__/RemoteMachineCard.test.tsx`

- [ ] **Step 1: Add card/action tests**

  Update the card test fixture to pass `onRunDiagnostics`. Assert the card has
  a `Run diagnostics` button and calls the handler with the selected machine.

- [ ] **Step 2: Add page/dialog tests**

  Extend the SSH API mock with `runConnectionDiagnostics`. Add tests for:

  - opening the dialog from a card action;
  - submitting session-only diagnostics;
  - validating target host without a port;
  - rendering success values for latency, TCP, and throughput;
  - rendering failed TCP details.

- [ ] **Step 3: Run red frontend tests**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/__tests__/SSHConnectionsSingleKey.test.tsx --run -t diagnostic
  cd frontend && npm run test -- src/components/__tests__/RemoteMachineCard.test.tsx --run -t diagnostic
  ```

### Task 4: Frontend Implementation

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/RemoteMachineCard.tsx`
- Modify: `frontend/src/pages/SSHConnectionsSingleKey.tsx`
- Modify: `frontend/src/pages/ssh-connections-single-key/SSHConnectionsSingleKeyView.tsx`
- Modify: `frontend/src/pages/ssh-connections-single-key/SSHConnectionDialogs.tsx`
- Create: `frontend/src/pages/ssh-connections-single-key/dialogs/ConnectionDiagnosticsDialog.tsx`
- Modify: `frontend/src/pages/ssh-connections-single-key/types.ts`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] **Step 1: Add API types and method**

  Add request/response interfaces for connection diagnostics and:

  ```typescript
  runConnectionDiagnostics: (connectionId: number, data: SSHConnectionDiagnosticsRequest) =>
    api.post<SSHConnectionDiagnosticsResponse>(
      `/ssh-keys/connections/${connectionId}/diagnostics`,
      data
    )
  ```

- [ ] **Step 2: Add card action**

  Add a Lucide diagnostics icon button to `RemoteMachineCard`, wire it through
  `RemoteConnectionsSection`, and keep edit/delete/deploy/test actions
  independent.

- [ ] **Step 3: Add dialog state and mutation**

  In `SSHConnectionsSingleKey.tsx`, add selected diagnostics connection state,
  a dialog-open boolean, and a mutation calling `sshKeysAPI.runConnectionDiagnostics`.
  Track success and failure through existing analytics/toast patterns.

- [ ] **Step 4: Implement `ConnectionDiagnosticsDialog`**

  Use `ResponsiveDialog`, MUI fields/buttons/chips, and Lucide status icons.
  Validate that a target host requires a valid port before submit. Show result
  rows for session, latency, TCP, and throughput.

- [ ] **Step 5: Run frontend tests green**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/__tests__/SSHConnectionsSingleKey.test.tsx --run -t diagnostic
  cd frontend && npm run test -- src/components/__tests__/RemoteMachineCard.test.tsx --run -t diagnostic
  ```

### Task 5: Storybook And Docs

**Files:**
- Create: `frontend/src/pages/ssh-connections-single-key/dialogs/ConnectionDiagnosticsDialog.stories.tsx`
- Modify: `docs/ssh-keys.md`

- [ ] **Step 1: Add Storybook states**

  Add stories for success, partial TCP failure, and timeout/failure states.

- [ ] **Step 2: Update docs**

  Add a Remote Machine Diagnostics section to `docs/ssh-keys.md` explaining
  session, remote TCP, and bounded speed probes.

### Task 6: Required Validation And Publish

**Files:**
- Inspect: `.github/PULL_REQUEST_TEMPLATE.md`

- [ ] **Step 1: Run targeted validation**

  Run:

  ```bash
  pytest tests/unit/test_api_ssh_keys.py -q -k diagnostic
  cd frontend && npm run test -- src/pages/__tests__/SSHConnectionsSingleKey.test.tsx --run -t diagnostic
  cd frontend && npm run test -- src/components/__tests__/RemoteMachineCard.test.tsx --run -t diagnostic
  ```

- [ ] **Step 2: Run backend checks**

  Run:

  ```bash
  ruff check app tests
  ruff format --check app tests
  ```

- [ ] **Step 3: Run frontend checks**

  Run:

  ```bash
  cd frontend && npm run check:locales
  cd frontend && npm run typecheck
  cd frontend && npm run lint
  cd frontend && npm run build
  ```

- [ ] **Step 4: Capture runtime evidence**

  Launch Borg UI locally with an available dev or smoke path. Open Remote
  Machines, open diagnostics for a configured connection when feasible, submit a
  check, and record the observed result or validation/error state.

- [ ] **Step 5: Publish and hand off**

  Commit the focused diff, push the branch, create/update a PR using
  `.github/PULL_REQUEST_TEMPLATE.md`, attach it to Linear, run the required PR
  feedback sweep, update the workpad with validation evidence and the Human
  Review handoff note, then move the issue to Human Review only when checks and
  feedback are clear.
