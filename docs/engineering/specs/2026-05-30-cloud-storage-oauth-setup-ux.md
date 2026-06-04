# Cloud Storage OAuth Setup UX

## Problem

BOR-86 added Borg UI-owned OAuth callbacks for Google Drive and Microsoft OneDrive, but the admin/user flow still exposes too much implementation detail. Provider OAuth app credentials should be configured from the Cloud Storage UI, token expiry/refresh status is not visible, Borg UI-owned callback completion returns raw token/config details to the setup dialog, and unsupported providers need clearer fallback guidance.

## Goals

- Let admins configure supported provider OAuth app credentials from a backend-managed Cloud Storage UI surface.
- Use persisted Borg UI credentials as the only provider app credential source.
- Keep client secrets and provider tokens out of ordinary frontend responses, remote metadata, and logs.
- Show OAuth token status, expiry, and refresh availability for managed OAuth remotes.
- Improve Borg UI-owned callback completion so the browser sees a clear completion page and the setup dialog can save a server-side token result without displaying raw token JSON.
- Keep rclone loopback/manual authorization available for unsupported providers and advanced setups.

## Non-Goals

- Adding provider-owned OAuth for additional rclone providers in this change. Dropbox and Box remain loopback/manual until their app registration, token exchange, and rclone config requirements are implemented explicitly.
- Making OAuth token lifetime configurable. Google and Microsoft issue access-token expiry and refresh-token behavior; rclone refreshes with the stored refresh token when the provider allows it.
- Building a separate Settings tab. The Cloud Storage add/edit remote dialog is the admin surface for this workflow.

## Design

### Backend

- Add encrypted persisted OAuth credential columns to `system_settings` for Google Drive and OneDrive.
- Add admin-only rclone OAuth credential endpoints:
  - `GET /api/rclone/oauth/credentials`
  - `PUT /api/rclone/oauth/credentials/{provider}`
- Use a single credential resolver for provider authorization URLs, token exchange, and provider metadata. Missing persisted Borg UI credentials return configured=false with source/status explaining what is missing.
- Extend provider metadata with credential source/status and callback setup details, without returning client secrets.
- For Borg UI-owned sessions, return a server-side session marker plus token status instead of raw token JSON. Remote creation/update resolves that marker to the in-memory authorized session before writing `rclone.conf`.
- Preserve raw token JSON only for the existing rclone loopback/manual path, because rclone itself returns that token to the browser for manual copy/paste.
- Serialize managed OAuth remote token metadata by reading the server-side rclone config and returning only status, expiry, and refresh availability.

### Frontend

- Keep the current Cloud Storage page and `RcloneRemoteDialog` composition.
- Replace the chip-only OAuth state with a bordered/tinted setup panel that shows provider mode, credential source/status, callback URL, token progress, expiry, and refresh behavior.
- Add inline credential fields for Borg UI-owned providers. Save through the backend endpoint; never show saved client secrets.
- After Borg UI-owned callback completion, show that the token is ready to save server-side and keep raw token JSON out of the config editor.
- Continue showing loopback/manual controls for unsupported providers and as an explicit fallback for supported providers.

### Documentation

- Update Cloud Storage OAuth docs with local and production redirect URLs, UI-managed credential setup, fallback behavior, and supported provider scope.
- Update navigation/user docs if the Cloud Storage guided flow copy changes enough to affect navigation guidance.

## Acceptance Mapping

- Documentation covers setup, credential storage, redirect URLs, fallback, supported providers, and provider scope.
- UI and remote metadata show token expiry/status and refresh behavior; no configurable expiry is added because provider/rclone semantics own it.
- Admins can configure supported provider app credentials through backend-managed API/UI; secrets are encrypted at rest and redacted from responses.
- Borg UI-owned callbacks provide clear completion and session progress without default raw token JSON exposure.
- UI uses existing Borg UI operational card/dialog patterns with balanced borders and accessible labeled controls.
- Google Drive and OneDrive remain the supported Borg UI-owned providers; Dropbox, Box, and custom OAuth backends stay loopback/manual.
- Existing rclone loopback/manual authorization remains available.

## Validation

- Backend unit tests for credential persistence, redaction, non-admin access, missing credential handling, token status serialization, and Borg UI session marker handling.
- Frontend tests for credential setup, callback progress, expiry/status display, error state, and loopback fallback.
- Storybook stories and snapshots for configured, setup-missing, callback-ready, expiry/status, and error states.
- Backend and frontend quality gates required by repo policy.
- Local walkthrough with mocked Borg UI-owned OAuth callback path.
