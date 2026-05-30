# Cloud Storage OAuth Setup UX Implementation Plan

> **For agentic workers:** Execute with the repo's proportional TDD workflow. Write failing targeted tests before production code, verify red/green, then run the full validation gates listed below before handoff.

**Goal:** Polish Borg UI-owned Cloud Storage OAuth setup, credential management, token status, and callback completion while preserving rclone loopback/manual authorization.

**Architecture:** Persist supported provider OAuth app credentials in encrypted `system_settings` fields and resolve them through rclone API helpers. Keep raw tokens server-side for Borg UI-owned sessions by returning a session marker and token status to the frontend. Update the Cloud Storage dialog to show credential setup, callback progress, token expiry/refresh status, and fallback controls using existing Borg UI/MUI patterns.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, React, TypeScript, MUI, TanStack Query, Vitest, Storybook snapshots.

---

## Task 1: Backend Credential Storage and API

**Files:**
- Modify: `app/database/models.py`
- Create: `app/database/migrations/115_add_rclone_oauth_provider_credentials.py`
- Modify: `app/api/rclone.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing tests that prove only admins can read/update rclone OAuth credentials, saved client secrets are encrypted/redacted, and provider metadata reports credential source without returning secrets.
- [ ] Add `SystemSettings` columns for Google Drive and OneDrive OAuth client IDs and encrypted client secrets.
- [ ] Add an idempotent migration for those columns.
- [ ] Implement credential resolver helpers with database-first precedence and environment fallback.
- [ ] Add `GET /api/rclone/oauth/credentials` and `PUT /api/rclone/oauth/credentials/{provider}`.
- [ ] Extend provider metadata with non-secret credential source/status fields.
- [ ] Verify the targeted backend tests fail before implementation and pass after implementation.

## Task 2: Backend Token Status and Borg UI Session Redaction

**Files:**
- Modify: `app/api/rclone.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Add failing tests proving Borg UI-owned session polling does not return raw access/refresh tokens, returns token expiry/status metadata, and remote creation resolves an authorized server-side session marker into `rclone.conf`.
- [ ] Add failing tests proving managed OAuth remotes serialize token status/expiry/refresh availability without exposing token JSON.
- [ ] Implement token parsing/status helpers for valid, refreshable, expired, unknown, missing, and not-applicable states.
- [ ] Change Borg UI-owned session responses to return safe config markers and token status, while preserving loopback/manual raw config behavior.
- [ ] Resolve Borg UI session markers during create/update managed config writes and reject missing/stale markers.
- [ ] Improve callback HTML to communicate completion and next action clearly.
- [ ] Verify targeted backend red/green tests.

## Task 3: Frontend API Types, Dialog UX, and Tests

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/wizard/RcloneRemoteDialog.tsx`
- Modify: `frontend/src/pages/CloudStorage.tsx`
- Test: `frontend/src/pages/__tests__/CloudStorage.test.tsx`

- [ ] Add failing Vitest coverage for inline credential setup/save, configured and missing credential states, no raw token JSON after Borg UI callback, token expiry/status display, callback error recovery, and loopback fallback.
- [ ] Add API types/methods for OAuth credentials and token status.
- [ ] Add Cloud Storage query/mutation wiring for credential updates and provider refresh.
- [ ] Replace OAuth chip-only treatment with a compact setup/status panel using existing MUI outline/tint styling, labeled credential controls, progress feedback, and accessible errors.
- [ ] Keep the config editor available for advanced fields, but keep Borg UI-owned token/session markers hidden from the visible JSON.
- [ ] Verify targeted Vitest red/green tests.

## Task 4: Stories, Snapshots, and Documentation

**Files:**
- Modify: `frontend/src/components/wizard/RcloneRemoteDialog.stories.tsx`
- Update: `frontend/storybook-snapshots/*rclone-remote-dialog*.png`
- Modify: `docs/configuration.md`
- Modify: `docs/reverse-proxy.md`
- Modify as needed: `docs/navigation.md`

- [ ] Update stories for configured credentials, setup missing, callback authorized/token-ready, token expired/refreshable, and save error states.
- [ ] Run `cd frontend && npm run snapshots` and commit changed screenshots.
- [ ] Document UI-managed and environment credential sources, local/production redirect URLs, callback path behavior, fallback behavior, Google Drive/OneDrive support, and why additional OAuth providers remain loopback/manual.
- [ ] Update navigation docs only if the Cloud Storage user flow guidance changes.

## Task 5: Final Validation and Handoff

**Commands:**
- `pytest tests/unit/test_api_rclone.py -q`
- `ruff check app tests`
- `ruff format --check app tests`
- `cd frontend && npm run test -- src/pages/__tests__/CloudStorage.test.tsx`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `cd frontend && npm run snapshots`
- Local walkthrough via `./scripts/dev.sh`, Docker, or an available smoke runner that exercises the mocked Borg UI-owned callback path.

- [ ] Run required backend validation.
- [ ] Run required frontend validation and snapshots.
- [ ] Perform local walkthrough and record evidence.
- [ ] Commit changes.
- [ ] Push branch, open/update PR with the Borg UI PR template, attach/link it to Linear, and add GitHub label `symphony`.
- [ ] Run full PR feedback sweep and confirm checks are green.
- [ ] Update workpad with final checklist and Human Review handoff note.
