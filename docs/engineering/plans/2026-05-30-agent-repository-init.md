# Agent Repository Init Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Ensure create-mode managed-agent repositories are initialized on the
selected agent before Borg UI returns repository creation success.

**Architecture:** Keep Borg UI as the orchestrator. The server creates the
`Repository` row so the existing agent repository operation payload can be built,
queues `repository.init`, waits for completion, and deletes the row if init fails.
The agent handles `repository.init` like the existing repository operations,
using the shared Borg command helpers and existing secret-to-environment flow.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, Python managed-agent runtime, Borg 1,
Borg 2.

---

### Task 1: Server-Side Create Contract

**Files:**
- Modify: `app/api/repositories.py`
- Modify: `app/services/repository_executor.py`
- Test: `tests/unit/test_api_repositories.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Replace the metadata-only agent create test with a failing test that
  creates an agent advertising `repository.init`, posts an agent repository create
  payload, asserts `initialize_borg_repository` is not awaited, asserts a queued
  `AgentJob` with `payload["job_kind"] == "repository.init"`, and asserts the
  response is returned only after `wait_for_agent_repository_operation_job`.
- [ ] Add a failing test where waiting for `repository.init` raises
  `HTTPException(status_code=502)` and the newly created `Repository` row is
  deleted while the queued `AgentJob` remains inspectable.
- [ ] Add `repository.init` to `REPOSITORY_OPERATION_CAPABILITIES`.
- [ ] In `_create_agent_repository_record()`, queue `repository.init` for
  `imported=False` with `operation={"encryption": repository.encryption}` after
  the row exists and before returning success.
- [ ] On init wait `HTTPException`, delete the repository row, commit the delete,
  and re-raise the original exception.
- [ ] Leave `imported=True` as metadata-only import behavior.
- [ ] Update rclone-agent tests so cloud-mirror create agents advertise both
  `repository.init` and `repository.rclone_sync`, and missing-rclone tests still
  advertise `repository.init`.

### Task 2: Agent Runtime Init Operation

**Files:**
- Modify: `agent/borg_ui_agent/repository_ops.py`
- Modify: `agent/borg_ui_agent/runtime.py`
- Test: `tests/unit/test_agent_runtime.py`

- [ ] Add failing tests that `repository.init` appears in `get_capabilities()`
  and `JOB_HANDLERS`.
- [ ] Add failing tests that Borg 1 init builds
  `["borg", "init", "--encryption", "repokey", "/agent/repo"]`.
- [ ] Add failing tests that Borg 2 init builds
  `["borg2", "-r", "/agent/repo2", "repo-create", "--encryption", "repokey-aes-ocb"]`.
- [ ] Add `repository.init` to `REPOSITORY_JOB_KINDS`,
  `DEFAULT_CAPABILITIES`, and `JOB_HANDLERS`.
- [ ] In `RepositoryOperationPayload.build_command()`, handle
  `repository.init` by reading `operation["encryption"]`, defaulting only where
  the existing create API already supplies an encryption value.
- [ ] Build Borg 1 init commands through `_base_borg1("init")` and append the
  repository path.
- [ ] Build Borg 2 init commands through `_base_borg2("repo-create")`.
- [ ] Keep execution on the streaming repository operation path so progress,
  cancellation, return code, and `BORG_PASSPHRASE` behavior are shared with the
  existing operations.

### Task 3: Documentation

**Files:**
- Modify: `agent/README.md`

- [ ] Add `repository.init` to the current job support list.
- [ ] Add `repository.init` to managed-agent capability examples that include
  repository operations.

### Task 4: Validation And Handoff

**Files:**
- Modify as needed for validation-only fixes.

- [ ] Run `.venv311/bin/python -m pytest tests/unit/test_api_repositories.py::TestRepositoriesCreate -q`.
- [ ] Run `.venv311/bin/python -m pytest tests/unit/test_agent_runtime.py -q`.
- [ ] Run `.venv311/bin/python -m pytest tests/unit/test_api_rclone.py -q`.
- [ ] Run `.venv311/bin/python -m pytest tests/unit/test_api_agents.py -q`.
- [ ] Run `.venv311/bin/python -m ruff check app tests agent`.
- [ ] Run `.venv311/bin/python -m ruff format --check app tests agent`.
- [ ] Record local runtime evidence that agent create success is gated on init
  wait and init failure removes the repository row.
- [ ] Commit, push, create the PR from `.github/PULL_REQUEST_TEMPLATE.md`, attach
  it to Linear, apply the `symphony` label, run the full PR feedback sweep, and
  move the issue to Human Review only after checks and workpad acceptance are
  complete.
