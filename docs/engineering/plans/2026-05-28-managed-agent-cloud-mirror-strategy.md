# Managed-Agent Cloud Mirror Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow managed-agent-primary repositories to use rclone cloud mirrors through a server/agent-owned sync strategy.

**Architecture:** Reuse `RepositoryStorage` for mirror metadata. Managed-agent mirrors store `sync_direction="agent_to_remote"` and no cache path. The server validates rclone target metadata and agent eligibility, queues a `repository.rclone_sync` agent job for sync, and records mirror status from the job result. The agent writes a temporary rclone config for the job, runs `rclone sync` from its repository path to the configured target, and removes temporary files after the process exits.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, Python managed-agent runtime, React, Vite, MUI, Vitest, Storybook screenshots.

---

## Task 1: Backend Contract And Reproduction

**Files:**

- Modify: `app/services/rclone_repository_service.py`
- Modify: `app/services/repository_executor.py`
- Modify: `app/api/repositories.py`
- Test: `tests/unit/test_rclone_repository_service.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing service tests that `build_mirror_storage(..., source_backend="agent")` stores `cache_path is None` and `sync_direction == "agent_to_remote"`.
- [ ] Add failing API tests that a managed-agent repository with `cloud_mirror_enabled: true` creates a mirror row instead of silently ignoring the mirror request.
- [ ] Add failing API tests that agent mirrors reject `rclone_cache_path`.
- [ ] Add failing API tests that disabled/revoked/missing agents and agents missing `repository.rclone_sync` are rejected before mirror metadata is written.
- [ ] Implement the minimal backend validation and mirror row construction while keeping local and SSH mirror behavior unchanged.
- [ ] Run `pytest tests/unit/test_rclone_repository_service.py tests/unit/test_api_rclone.py -q`.

## Task 2: Agent Sync Execution

**Files:**

- Modify: `app/services/rclone_repository_service.py`
- Modify: `app/services/repository_executor.py`
- Modify: `agent/borg_ui_agent/runtime.py`
- Modify: `agent/borg_ui_agent/repository_ops.py`
- Test: `tests/unit/test_rclone_repository_service.py`
- Test: `tests/unit/test_agent_runtime.py`

- [ ] Add failing service tests that managed-agent mirror sync queues `repository.rclone_sync`, marks storage `syncing`, and updates storage to `current` when the agent job completes.
- [ ] Add failing service tests that agent job failure records `sync_status="failed"` and `last_sync_error` without changing `repository.path`.
- [ ] Add failing agent runtime tests for `repository.rclone_sync` command construction, temporary config creation, cleanup, success, and failure.
- [ ] Implement the server-side agent job payload and wait logic.
- [ ] Implement the agent-side rclone sync handler and add `repository.rclone_sync` to advertised capabilities.
- [ ] Run `pytest tests/unit/test_rclone_repository_service.py tests/unit/test_agent_runtime.py -q`.

## Task 3: Failure And Rollback Behavior

**Files:**

- Modify: `app/api/repositories.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing API tests that first managed-agent mirror sync failure preserves the repository row and stores failed mirror status.
- [ ] Add failing API tests that managed-agent mirror update preflight/capability failures leave the existing mirror row unchanged.
- [ ] Ensure update logic preserves `cache_path is None` for agent mirrors after repository edits.
- [ ] Run targeted backend tests again.

## Task 4: Repository UI Status

**Files:**

- Modify: `app/api/repositories.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/components/RepositoryCard.tsx`
- Modify: `frontend/src/components/RepositoryCard.stories.tsx`
- Modify: `frontend/src/components/wizard/WizardStepCloudMirror.tsx`
- Modify: `frontend/src/components/wizard/WizardStepCloudMirror.stories.tsx`
- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/locales/*.json`
- Test: `frontend/src/components/__tests__/RepositoryCard.test.tsx`
- Test: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`
- Test: `frontend/src/components/wizard/__tests__/WizardStepCloudMirror.test.tsx`

- [ ] Add failing frontend tests that managed-agent repositories can enable cloud mirror and submit the rclone payload without a cache path.
- [ ] Add failing frontend tests that managed-agent route copy explains the agent-owned sync route.
- [ ] Add failing frontend tests that repository cards show agent status beside mirror sync status for mirrored agent repositories.
- [ ] Implement UI eligibility, payload, status display, translations, stories, and snapshots.
- [ ] Run targeted Vitest tests and `cd frontend && npm run snapshots`.

## Task 5: Docs And Final Gates

**Files:**

- Modify: `docs/managed-agents.md`
- Modify as needed for validation fixes only.

- [ ] Update managed-agent user docs with cloud mirror strategy, eligibility, and failure-status behavior.
- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run targeted backend pytest.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run targeted frontend Vitest tests.
- [ ] Run `cd frontend && npm run snapshots`.
- [ ] Launch or smoke Borg UI and record repository cloud mirror walkthrough evidence.
