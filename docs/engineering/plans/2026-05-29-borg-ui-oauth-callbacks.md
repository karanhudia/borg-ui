# Borg UI-Owned OAuth Callback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Borg UI-owned OAuth callbacks for Google Drive and Microsoft OneDrive while preserving existing rclone loopback/manual authorization.

**Architecture:** Keep Cloud Storage's managed rclone remote model. Add provider-owned OAuth session handling in `app/api/rclone.py`, UI-saved provider credentials, and UI metadata/copy in the Cloud Storage dialog. Use tests first for every backend and frontend behavior change.

> Superseded note: provider client credentials are now saved in Borg UI, not read
> from `GOOGLE_DRIVE_OAUTH_*` or `ONEDRIVE_OAUTH_*` environment variables.

**Tech Stack:** FastAPI, Pydantic settings, httpx, SQLAlchemy models already in place, React, MUI, React Query, Vitest, Storybook screenshots.

---

## Task 1: Backend OAuth Configuration and Provider Metadata

**Files:**
- Modify: `app/config.py`
- Modify: `app/api/rclone.py`
- Test: `tests/unit/test_api_rclone.py`
- Docs: `docs/configuration.md`, `docs/reverse-proxy.md`

- [ ] Add failing backend tests proving Google Drive and OneDrive provider
      metadata includes `oauth_mode`, `oauth_configured`, and callback URLs only
      when `PUBLIC_BASE_URL` and provider credentials are valid.
- [ ] Implement UI-saved OAuth client credential storage for Google Drive and
      OneDrive.
- [ ] Implement public base URL validation and callback URL builders in
      `app/api/rclone.py`.
- [ ] Update `GET /api/rclone/providers` to return non-secret OAuth metadata.
- [ ] Update configuration and reverse-proxy docs with provider redirect URLs and
      UI-saved credential setup.
- [ ] Run `pytest tests/unit/test_api_rclone.py -q` and verify the new tests pass.

## Task 2: Backend Provider-Owned OAuth Sessions and Callback

**Files:**
- Modify: `app/api/rclone.py`
- Modify: `app/main.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing backend tests for `POST /api/rclone/oauth/sessions` with
      `mode: "borg_ui"` returning a provider authorization URL and no loopback
      URL for configured Google Drive/OneDrive.
- [ ] Add failing callback tests for invalid provider, missing session, state
      mismatch, provider error, and successful code exchange.
- [ ] Add a public rclone OAuth callback router and include it in `app/main.py`
      without the authenticated rclone router dependency.
- [ ] Implement provider authorization URL creation with high-entropy state and
      short-lived session storage.
- [ ] Implement provider token exchange through `httpx.AsyncClient`.
- [ ] Convert token responses into rclone-compatible token JSON in the session
      config.
- [ ] Keep existing rclone loopback session start/poll/authorize behavior for
      `mode: "rclone_loopback"` and unsupported OAuth providers.
- [ ] Run `pytest tests/unit/test_api_rclone.py -q`.

## Task 3: Backend Token Persistence and Redaction

**Files:**
- Modify: `app/api/rclone.py`
- Modify: `app/services/rclone_service.py`
- Test: `tests/unit/test_api_rclone.py`, `tests/unit/test_rclone_service.py`

- [ ] Add failing tests proving provider-owned session config writes token JSON,
      client ID, and client secret into the managed rclone config while API
      responses redact all of them.
- [ ] Add failing tests proving command redaction covers provider client IDs,
      client secrets, authorization codes, access tokens, and refresh tokens.
- [ ] Add internal marker handling so Borg UI-owned OAuth config injects backend
      provider credentials during managed config writes and strips marker fields
      from `rclone.conf`.
- [ ] Extend sensitive key/value redaction for provider OAuth fields.
- [ ] Run `pytest tests/unit/test_api_rclone.py tests/unit/test_rclone_service.py -q`.

## Task 4: Frontend API Types and Dialog Behavior

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/wizard/RcloneRemoteDialog.tsx`
- Modify: `frontend/src/pages/CloudStorage.tsx`
- Modify: `frontend/src/pages/__tests__/CloudStorage.test.tsx`
- Modify: locale files under `frontend/src/locales/`

- [ ] Add failing Vitest coverage for configured Borg UI-owned OAuth: the dialog
      explains the Borg UI callback, starts OAuth with `mode: "borg_ui"`, opens
      the provider authorization URL, and never sends client credentials.
- [ ] Add failing Vitest coverage for setup-missing and rclone-loopback fallback
      states.
- [ ] Extend frontend provider/session types with OAuth metadata and start mode.
- [ ] Update dialog copy and actions for Borg UI-owned OAuth, setup-missing, and
      rclone loopback/manual authorization.
- [ ] Keep manual JSON editing and Custom backend path working.
- [ ] Run `cd frontend && npm test -- CloudStorage.test.tsx`.

## Task 5: Stories and Snapshots

**Files:**
- Modify: `frontend/src/components/wizard/RcloneRemoteDialog.stories.tsx`
- Modify: `frontend/src/pages/CloudStorage.stories.tsx`
- Update: `frontend/storybook-snapshots/*.png`

- [ ] Update stories for provider-owned OAuth configured, setup missing, and
      rclone loopback fallback states.
- [ ] Run `cd frontend && npm run snapshots`.
- [ ] Inspect generated snapshot filenames and ensure changed screenshots match
      the intended UI states.

## Task 6: Final Validation, Runtime Walkthrough, and Handoff

**Files:**
- Update Linear workpad only
- Commit all touched source, docs, tests, stories, and snapshots

- [ ] Run backend gates: `ruff check app tests`, `ruff format --check app tests`,
      and targeted pytest.
- [ ] Run frontend gates: `cd frontend && npm run check:locales`,
      `npm run typecheck`, `npm run lint`, `npm run build`, targeted Vitest, and
      `npm run snapshots`.
- [ ] Run an app/Docker or remote-host walkthrough using dummy provider
      credentials and mocked provider token exchange to prove the browser only
      needs the Borg UI callback URL, not `127.0.0.1:53682`.
- [ ] Update the Linear workpad with completed acceptance criteria, validation
      evidence, commit SHA, and Human Review handoff note.
- [ ] Use the commit and push skills, create/link the PR, run the PR feedback
      sweep, confirm green checks, and move the issue to Human Review.
