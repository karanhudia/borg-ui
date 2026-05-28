# Cloud Mirror Repositories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional rclone cloud mirror flow for normal repositories while preserving existing direct-rclone backend compatibility.

**Architecture:** Reuse rclone remotes and `RepositoryStorage` as the mirror metadata row. Add explicit mirror request fields and preflight validation in the repository API, move rclone controls from Location into a dedicated wizard step, and keep repository cards/status wired to the existing `rclone_storage` response.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, Vite, MUI, Vitest, Storybook screenshots.

---

## Task 1: Backend Mirror Contract

**Files:**

- Modify: `app/services/rclone_repository_service.py`
- Modify: `app/api/repositories.py`
- Test: `tests/unit/test_rclone_repository_service.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing service tests for a mirror storage row whose source is the repository's primary local path.
- [ ] Add failing API tests for local repository create with `cloud_mirror_enabled: true`.
- [ ] Add failing API tests that `rclone_cache_path` is rejected for the mirror flow.
- [ ] Implement mirror validation helpers that reuse remote lookup, relative path normalization, sync policy validation, and extra flag normalization.
- [ ] Implement first-sync failure preservation: commit the repository, create the mirror row, attempt sync, and persist failed mirror status without rolling back the original repository.
- [ ] Keep legacy `storage_backend: "rclone"` tests passing.
- [ ] Run `pytest tests/unit/test_rclone_repository_service.py tests/unit/test_api_rclone.py -q`.

## Task 2: Remote Path Preflight

**Files:**

- Modify: `app/services/rclone_repository_service.py`
- Modify: `app/api/repositories.py`
- Test: `tests/unit/test_rclone_repository_service.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing tests for non-empty remote path rejection when `rclone_remote_path_verified` is false.
- [ ] Add passing tests for empty remote path and verified non-empty remote path.
- [ ] Implement `preflight_remote_path` using the selected remote target and `rclone lsjson`.
- [ ] Treat missing remote path as safe-to-create only when rclone reports a not-found-style listing failure; other listing failures block with a validation error.
- [ ] Run targeted rclone tests again.

## Task 3: Frontend Wizard State And Payload

**Files:**

- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/components/wizard/WizardStepLocation.tsx`
- Create: `frontend/src/components/wizard/WizardStepCloudMirror.tsx`
- Create: `frontend/src/components/wizard/RcloneRemoteFolderPickerDialog.tsx`
- Modify: `frontend/src/components/wizard/WizardStepReview.tsx`
- Modify: `frontend/src/components/wizard/index.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/locales/*.json`
- Test: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`
- Test: `frontend/src/components/wizard/__tests__/WizardStepLocation.test.tsx`
- Create: `frontend/src/components/wizard/__tests__/WizardStepCloudMirror.test.tsx`
- Test: `frontend/src/components/wizard/__tests__/WizardStepReview.test.tsx`

- [ ] Add failing tests that the step sequence includes Cloud Mirror after Location.
- [ ] Add failing tests that Cloud Mirror is disabled by default and the payload omits mirror fields.
- [ ] Add failing tests that enabling mirror submits `cloud_mirror_enabled`, remote id, relative path, sync policy, extra flags, and no cache path.
- [ ] Remove the Cloud Storage location card and rclone cache preview from Location.
- [ ] Add the dedicated Cloud Mirror step with remote select, add-remote action, inline folder browse button, sync policy, and extra flags.
- [ ] Add the rclone folder picker dialog and mark selected paths verified.
- [ ] Update Review to show primary repository location plus mirror target when enabled.
- [ ] Run targeted Vitest tests.

## Task 4: Existing Repository Card And Stories

**Files:**

- Modify: `frontend/src/components/RepositoryCard.tsx`
- Modify: `frontend/src/components/RepositoryCard.stories.tsx`
- Modify: `frontend/src/components/wizard/WizardStepLocation.stories.tsx`
- Create: `frontend/src/components/wizard/WizardStepCloudMirror.stories.tsx`
- Modify: `frontend/src/components/wizard/WizardStepReview.stories.tsx`
- Test: `frontend/src/components/__tests__/RepositoryCard.test.tsx`

- [ ] Add failing tests for eligible local repository exposing Enable cloud mirror when no mirror exists.
- [ ] Add/update tests for first-sync pending/failure/current status states.
- [ ] Add stories for Cloud Mirror disabled/enabled and repository card enable/status states.
- [ ] Run `cd frontend && npm run snapshots` and commit updated files under `frontend/storybook-snapshots/`.

## Task 5: Final Validation And Handoff

**Files:**

- Modify as required by validation fixes only.

- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run backend targeted pytest paths.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run targeted frontend Vitest tests.
- [ ] Run local rclone smoke/walkthrough if `rclone` is available; otherwise record the unavailable proof and the closest automated coverage.
- [ ] Commit, push, create/update PR with `.github/PULL_REQUEST_TEMPLATE.md`, add `symphony` label, sweep PR feedback, and move BOR-67 to Human Review only when checks are green.
