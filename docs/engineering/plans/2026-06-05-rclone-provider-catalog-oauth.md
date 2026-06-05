# Rclone Provider Catalog and OAuth Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand Cloud Storage to expose rclone's provider catalog and make Borg UI-owned OAuth provider-driven instead of hard-coded.

**Architecture:** Keep managed rclone remotes as the persistence model. Add a server-side catalog builder with curated overrides plus rclone-generated entries, a generic OAuth credential table, and an OAuth adapter registry. Update the Cloud Storage dialog to handle a large provider list through search/grouping while preserving manual JSON escape hatches.

**Tech Stack:** FastAPI, SQLAlchemy, encrypted secrets, rclone CLI metadata, React, MUI, React Query, Vitest, Storybook.

---

## Remaining Provider Adapter Follow-Ups

Borg UI-owned standard browser callbacks are implemented for `box`, `drive`,
`dropbox`, `gcs`, `gphotos`, `hidrive`, `huaweidrive`, `onedrive`, `pcloud`,
`premiumizeme`, `putio`, `sharefile`, `yandex`, and `zoho`.

The remaining OAuth-token providers are non-standard setup flows rather than
simple callback adapters:

- [ ] `jottacloud` — implement a separate setup path if needed. rclone's
      standard flow consumes a personal login token and then may select/create
      device and mountpoint state; the traditional flow uses white-label
      service discovery. It is not exposed through OAuth session start today. No
      provider logo in installed icon packs; use the distinct cloud glyph.
- [ ] `mailru` — implement a separate username plus app-password credential
      flow if needed. rclone obtains the token through password-credentials auth,
      not a normal browser callback, and it is not exposed through OAuth session
      start today. Logo available: Mail.ru.

---

## Task 1: Backend Provider Catalog Expansion

**Files:**
- Modify: `app/api/rclone.py`
- Modify: `app/services/rclone_service.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing tests proving `GET /api/rclone/providers` includes generated providers such as `pcloud`, `yandex`, and `gphotos` when rclone provider metadata is available.
- [ ] Add failing tests proving the endpoint falls back to curated providers when rclone metadata is unavailable.
- [ ] Add `RcloneService.providers_command()` and an async provider metadata loader.
- [ ] Build a catalog merge that keeps curated definitions for known providers and adds generated entries for other rclone backends.
- [ ] Redact or omit sensitive defaults from generated provider metadata.
- [ ] Run `pytest tests/unit/test_api_rclone.py -k "provider" -q`.

## Task 2: Generic OAuth Credential Storage

**Files:**
- Modify: `app/database/models.py`
- Create: `app/database/migrations/121_add_rclone_oauth_provider_credentials_table.py`
- Modify: `app/api/rclone.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing tests proving OAuth credentials can be saved for `dropbox` and are returned redacted.
- [ ] Add failing tests proving existing Google Drive/OneDrive `system_settings` credentials are still read as legacy fallback.
- [ ] Add `RcloneOAuthProviderCredential` with provider, client ID, encrypted client secret, timestamps, and uniqueness on provider.
- [ ] Add migration with additive table creation.
- [ ] Update credential lookup/update helpers to use the new table first and legacy fields second.
- [ ] Run `pytest tests/unit/test_api_rclone.py -k "oauth_credentials" -q`.

## Task 3: OAuth Adapter Registry

**Files:**
- Modify: `app/api/rclone.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing tests proving OAuth metadata reports Borg UI-owned callback support for configured registry providers.
- [ ] Add failing tests proving unsupported OAuth providers remain on rclone loopback mode.
- [ ] Replace `BORG_UI_OAUTH_PROVIDERS` conditionals with adapter lookup helpers.
- [ ] Keep Google Drive and OneDrive adapters behavior-compatible with current tests.
- [ ] Add standard adapters for OAuth providers that have auth/token URLs and no special discovery requirement.
- [ ] Run `pytest tests/unit/test_api_rclone.py -k "oauth" -q`.

## Task 4: Callback Exchange and Persistence

**Files:**
- Modify: `app/api/rclone.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing tests proving a standard adapter exchanges a callback code at the provider token URL and stores rclone-compatible token JSON.
- [ ] Add failing tests proving marker-based config writes include provider client credentials without exposing token/client secret values in responses.
- [ ] Generalize token exchange URL and authorization parameter construction through adapters.
- [ ] Preserve OneDrive default-drive finalization.
- [ ] Run `pytest tests/unit/test_api_rclone.py -k "callback or token" -q`.

## Task 5: Frontend Provider Picker UX

**Files:**
- Modify: `frontend/src/components/wizard/RcloneRemoteDialog.tsx`
- Modify: `frontend/src/pages/CloudStorage.tsx`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/pages/__tests__/CloudStorage.test.tsx`
- Modify: `frontend/src/components/shared/RcloneProviderIcon.tsx`
- Modify: `frontend/src/locales/en.json`
- Mirror locale keys in `frontend/src/locales/de.json`, `frontend/src/locales/es.json`, and `frontend/src/locales/it.json`

- [ ] Add failing tests proving provider search can select a generated provider.
- [ ] Add failing tests proving Borg UI-owned OAuth and loopback fallback actions still render correctly.
- [ ] Add provider search state and grouped provider menu content.
- [ ] Add icon fallbacks for additional provider families without overfitting every provider.
- [ ] Keep manual JSON editor and custom backend behavior unchanged.
- [ ] Run `cd frontend && npm test -- CloudStorage.test.tsx`.

## Task 5a: Shared Rich Select Primitive

**Files:**
- Create: `frontend/src/components/shared/RichSelect.tsx`
- Create: `frontend/src/components/shared/RichSelect.stories.tsx`
- Create: `frontend/src/components/shared/__tests__/RichSelect.test.tsx`
- Modify: `frontend/src/components/shared/RichSelectRow.tsx`
- Modify: `frontend/src/components/shared/RcloneProviderSelect.tsx`
- Modify: `frontend/src/components/shared/ManagedAgentSelect.tsx`
- Modify: `frontend/src/components/shared/SshConnectionSelect.tsx`
- Modify: `frontend/src/components/shared/RcloneRemoteSelect.tsx`
- Modify: `frontend/src/components/shared/DestinationSelect.tsx`
- Modify: `frontend/src/components/shared/BackupPlanSelect.tsx`

- [ ] Extract common rich-row MUI select behavior into `RichSelect`.
- [ ] Support optional menu search while keeping the selected trigger display-only.
- [ ] Keep the trigger height fixed at 56px across rich dropdowns.
- [ ] Lock the dropdown paper width to the trigger width and ellipsize long row text with tooltips.
- [ ] Migrate existing rich dropdown wrappers without changing their public props.
- [ ] Add Storybook coverage for default, searchable, and narrow-width states.
- [ ] Add targeted component tests for selected rendering, search filtering, and selection changes.

## Task 6: Stories, Docs, and Verification

**Files:**
- Modify: `frontend/src/pages/CloudStorage.stories.tsx`
- Modify: `docs/provider-guides.md`
- Modify: `docs/reverse-proxy.md`
- Modify: `docs/configuration.md`

- [ ] Update Cloud Storage stories for expanded providers and OAuth provider states.
- [ ] Update docs to explain broad rclone provider discovery and explicit callback support.
- [ ] Run `pytest tests/unit/test_api_rclone.py -q`.
- [ ] Run `cd frontend && npm test -- CloudStorage.test.tsx`.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run any narrower type/lint checks needed by changed frontend files.
