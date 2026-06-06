# Cloud Storage Size Info Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show cloud storage capacity information on rclone remote cards after a remote has been tested.

**Architecture:** Add nullable storage snapshot columns to `rclone_remotes`, parse `rclone about` output during the existing test-remote flow, serialize the snapshot as `remote.storage`, and render it in the Cloud Storage card using the same used/free/total structure as remote machines.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite/PostgreSQL-compatible migrations, React, MUI, Vitest, Storybook.

---

### Task 1: Backend Storage Contract

**Files:**
- Modify: `tests/unit/test_api_rclone.py`
- Modify: `app/database/models.py`
- Add: `app/database/migrations/122_add_rclone_remote_storage.py`
- Modify: `app/api/rclone.py`

- [ ] Add a unit test that creates a `RcloneRemote` with storage columns and asserts `GET /api/rclone/remotes` returns `storage.total`, `storage.used`, `storage.available`, `storage.percent_used`, formatted values, and `last_check`.
- [ ] Add a unit test that mocks `rclone_service.about()` with `Total`, `Used`, and `Free` output and asserts `POST /api/rclone/remotes/{id}/test` persists and returns the storage snapshot.
- [ ] Add a unit test that mocks successful unsupported `rclone about` output and asserts the endpoint returns `storage: null`.
- [ ] Add nullable `storage_total`, `storage_used`, `storage_available`, `storage_percent_used`, and `last_storage_check` columns to the `RcloneRemote` model and migration.
- [ ] Add rclone-about parsing and shared storage serialization helpers in `app/api/rclone.py`.
- [ ] Run the targeted backend tests and confirm they pass.

### Task 2: Frontend Rendering

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/pages/CloudStorage.tsx`
- Modify: `frontend/src/pages/__tests__/CloudStorage.test.tsx`
- Modify: `frontend/src/pages/CloudStorage.stories.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Extend `RcloneRemote` with nullable `storage`.
- [ ] Add a failing Cloud Storage test for visible used/free/total storage values.
- [ ] Add a failing Cloud Storage test for the missing storage state.
- [ ] Render a storage band in `CloudStorageRemoteCard` with used/free stats, total text, and a usage bar.
- [ ] Add localized Cloud Storage labels for used, free, total, percent used, and no storage info.
- [ ] Update Storybook fixtures so at least one remote has storage and one has no storage.
- [ ] Run the targeted frontend test and confirm it passes.

### Task 3: Validation And Handoff

**Files:**
- Modify: Linear workpad only for evidence.

- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Launch Borg UI locally and verify Cloud Storage remotes show capacity or the graceful missing state.
- [ ] Commit, push, attach a PR, perform the required PR feedback sweep, and move the Linear issue to Human Review only when checks are green.
