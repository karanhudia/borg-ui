# SSH Cloud Mirror Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow SSH-primary repositories to use rclone cloud mirrors through a server-owned SSHFS mount strategy.

**Architecture:** Reuse `RepositoryStorage` for mirror metadata. Local mirrors keep using the primary local path as the rclone source; SSH mirrors store `sync_direction="sshfs_mount_to_remote"`, mount the SSH repository path with the existing mount service during sync, and unmount after rclone exits. The React wizard and repository card eligibility logic expand from local-only to local-or-SSH while keeping managed-agent repositories ineligible.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, Vite, MUI, Vitest, Storybook screenshots.

---

## Task 1: Backend SSH Mirror Contract

**Files:**

- Modify: `app/services/rclone_repository_service.py`
- Modify: `app/api/repositories.py`
- Test: `tests/unit/test_rclone_repository_service.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing service tests that `build_mirror_storage(..., source_backend="ssh")` stores no client cache path and marks `sync_direction="sshfs_mount_to_remote"`.
- [ ] Add failing service tests that SSH mirror sync mounts the stored SSH repository path, uses the mount point as the rclone source, and unmounts after sync.
- [ ] Add failing API tests that SSH repository create with `cloud_mirror_enabled: true` succeeds without `rclone_cache_path`.
- [ ] Add failing API tests that `rclone_cache_path` is still rejected for SSH mirrors.
- [ ] Implement the minimal backend strategy and keep direct rclone/local mirror behavior unchanged.
- [ ] Run `pytest tests/unit/test_rclone_repository_service.py tests/unit/test_api_rclone.py -q`.

## Task 2: Failure And Rollback Behavior

**Files:**

- Modify: `app/services/rclone_repository_service.py`
- Modify: `app/api/repositories.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing API tests that a first SSH mirror sync failure preserves the repository and records failed mirror status.
- [ ] Add failing API tests that SSH mirror remote/preflight update failures leave the existing mirror row unchanged.
- [ ] Ensure mount failures flow through the same failed mirror status path as rclone failures.
- [ ] Run the targeted backend tests again.

## Task 3: Frontend Eligibility And Messaging

**Files:**

- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/components/wizard/WizardStepCloudMirror.tsx`
- Modify: `frontend/src/components/RepositoryCard.tsx`
- Modify: `frontend/src/locales/*.json`
- Test: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`
- Test: `frontend/src/components/wizard/__tests__/WizardStepCloudMirror.test.tsx`
- Test: `frontend/src/components/__tests__/RepositoryCard.test.tsx`

- [ ] Add failing tests for SSH-primary cloud mirror eligibility and payload submission.
- [ ] Add failing tests for managed-agent ineligible copy.
- [ ] Add failing tests for repository cards exposing Enable cloud mirror on SSH repositories.
- [ ] Implement local-or-SSH eligibility and SSH route messaging.
- [ ] Run targeted Vitest tests.

## Task 4: Stories, Snapshots, And Final Gates

**Files:**

- Modify: `frontend/src/components/wizard/WizardStepCloudMirror.stories.tsx`
- Modify: `frontend/src/components/RepositoryCard.stories.tsx`
- Modify: `frontend/storybook-snapshots/**`
- Modify as needed for validation fixes only.

- [ ] Add/update stories for SSH mirror eligibility and managed-agent ineligibility.
- [ ] Run `cd frontend && npm run snapshots`.
- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run targeted backend pytest.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run targeted frontend Vitest tests.
- [ ] Launch or smoke Borg UI and record the repository cloud mirror walkthrough evidence.
