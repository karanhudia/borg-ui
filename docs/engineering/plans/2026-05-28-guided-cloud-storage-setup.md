# Guided Cloud Storage Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add guided rclone provider setup for Cloud Storage remotes while keeping existing managed config payloads compatible.

**Architecture:** Add a small backend provider catalog, rclone-backed OAuth authorization sessions, and safer config redaction/preservation, then update the existing Cloud Storage dialog to consume provider metadata, use `ResponsiveDialog`, and edit JSON with the shared Monaco `CodeEditor`.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, Vite, MUI, Monaco editor, Vitest, Storybook screenshots.

---

## Implementation Tasks

### Task 1: Backend Provider Catalog And Redaction

**Files:**

- Modify: `app/api/rclone.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing tests for `GET /api/rclone/providers` returning Google Drive, OneDrive, S3, B2, WebDAV, SFTP, local, and custom provider metadata.
- [ ] Add failing tests for starting/polling a rclone OAuth session and rejecting non-OAuth providers.
- [ ] Add failing tests that creating a remote with `token` and provider secret keys writes the real `rclone.conf` values but returns redacted config values.
- [ ] Add failing tests that updating a remote with redacted secret markers preserves the existing config file secrets.
- [ ] Implement provider metadata constants and route.
- [ ] Implement rclone OAuth session start/poll endpoints backed by `rclone authorize --auth-no-open-browser`.
- [ ] Implement sensitive-key redaction and update-time secret preservation.
- [ ] Run `pytest tests/unit/test_api_rclone.py -q`.

### Task 2: Frontend API Types And Dialog Behavior

**Files:**

- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/wizard/RcloneRemoteDialog.tsx`
- Modify: `frontend/src/pages/CloudStorage.tsx`
- Test: `frontend/src/pages/__tests__/CloudStorage.test.tsx`

- [ ] Add failing frontend tests for loading provider metadata and rendering a provider selector with Google Drive and Microsoft OneDrive.
- [ ] Add failing frontend tests that selecting Google Drive submits a `drive` config template and that Custom backend still allows an arbitrary rclone type.
- [ ] Add failing frontend tests that rclone OAuth session polling injects the returned token into the config editor.
- [ ] Add failing frontend tests that the add dialog renders as a bottom sheet when `matchMedia` reports a mobile viewport.
- [ ] Add `RcloneProvider` types and `rcloneAPI.getProviders()`.
- [ ] Add `rcloneAPI.startOAuthSession()` and `rcloneAPI.getOAuthSession()`.
- [ ] Fetch provider metadata on the Cloud Storage page and pass it into add/edit dialogs.
- [ ] Replace the provider text field with a provider selector plus Custom backend input.
- [ ] Replace the multiline config `TextField` with `CodeEditor` in JSON mode.
- [ ] Render through `ResponsiveDialog` with actions in the `footer` slot.
- [ ] Run `cd frontend && npm run test -- src/pages/__tests__/CloudStorage.test.tsx --run`.

### Task 3: Localization, Stories, And Docs

**Files:**

- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`
- Modify: `frontend/src/components/wizard/RcloneRemoteDialog.stories.tsx`
- Modify: `frontend/src/pages/CloudStorage.stories.tsx`
- Modify: `docs/provider-guides.md`

- [ ] Add localized labels and helper text for provider selection, OAuth start/check actions, config editor, and custom backend mode.
- [ ] Add Storybook stories for guided Google Drive setup, custom backend setup, and mobile-relevant dialog state where possible.
- [ ] Update provider docs with the Cloud Storage guided rclone remote setup path.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run snapshots`.

### Task 4: Final Validation And Handoff

**Files:**

- Modify generated snapshots under `frontend/storybook-snapshots/`.

- [ ] Run backend validation: `ruff check app tests`, `ruff format --check app tests`, and `pytest tests/unit/test_api_rclone.py -q`.
- [ ] Run frontend validation: `cd frontend && npm run check:locales && npm run typecheck && npm run lint && npm run build`.
- [ ] Launch the app locally and walkthrough Cloud Storage add/edit on desktop and mobile widths.
- [ ] Commit, push, attach PR, apply the `symphony` PR label, sweep PR feedback/checks, update Linear handoff, and move to Human Review.

## Plan Self-Review

- Spec coverage: provider list, auth guidance, editor replacement, mobile bottom sheet, raw fallback, and secret handling are each mapped to tasks.
- Placeholder scan: no task uses placeholder implementation language.
- Type consistency: backend provider metadata maps to the frontend `RcloneProvider` type and existing create/update payload shape remains unchanged.
