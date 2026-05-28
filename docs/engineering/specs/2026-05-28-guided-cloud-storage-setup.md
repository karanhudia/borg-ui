# Guided Cloud Storage Setup Spec

## Problem

Cloud Storage remote setup is currently a thin wrapper around a raw rclone
config JSON text field. Users must know the rclone provider type string, obtain
OAuth tokens outside Borg UI, paste config manually, and work around long text
being clipped inside a standard dialog. The add/edit remote dialog also uses a
desktop `Dialog` on mobile instead of the established bottom-sheet pattern.

## Desired Outcome

Cloud Storage should guide administrators through common rclone remote setup
without taking ownership of provider protocol implementations. Borg UI should
present popular providers, explain each provider's auth/config path, preserve a
manual advanced path, store sensitive config safely in the server-managed
`rclone.conf`, and make the dialog usable on desktop and mobile.

## Scope

- Add a Borg UI provider catalog for common rclone backends:
  - Google Drive (`drive`)
  - Microsoft OneDrive (`onedrive`)
  - Dropbox (`dropbox`)
  - Box (`box`)
  - Amazon S3 / S3-compatible (`s3`)
  - Backblaze B2 (`b2`)
  - Azure Blob Storage (`azureblob`)
  - WebDAV (`webdav`)
  - SFTP (`sftp`)
  - Local filesystem (`local`)
  - Custom backend for unsupported rclone types
- Expose provider metadata through the rclone API so the UI is not hard-coded
  to the current list only.
- Show provider-specific auth guidance in the add/edit remote dialog.
- For OAuth providers, make the rclone token/callback handoff explicit:
  users start rclone's browser OAuth flow from Borg UI, complete the provider
  callback, then Borg UI polls the authorization session and saves the returned
  token JSON and provider config in the server-managed rclone config.
- Replace the raw multiline config text field with the shared Monaco
  `CodeEditor` in JSON mode.
- Render the add/edit dialog through `ResponsiveDialog` so it becomes a mobile
  bottom sheet.
- Preserve advanced manual JSON editing for unsupported or unusual backends.
- Redact sensitive rclone config values from API responses and database
  snapshots while preserving real values in the managed config file.

## Out Of Scope

- Provider-native OAuth client registrations inside Borg UI.
- Replacing rclone's own provider auth implementations.
- Running a long-lived rclone remote-control daemon.
- Generic rclone file management beyond existing test/browse actions.

## UX Design

Use Borg UI's existing operational settings style: dense controls, balanced
outlines, subtle tints, lucide icons, stable focus states, and plain labels.
The dialog should prioritize scannability over marketing presentation.

The create flow:

1. User opens Cloud Storage and chooses Add remote.
2. Dialog opens as a centered desktop dialog or bottom sheet on mobile.
3. User enters a remote name.
4. User chooses a provider from the supported provider list.
5. Borg UI shows the provider type, auth method, docs link, and important
   config keys.
6. Borg UI pre-fills editable JSON with a provider template.
7. For OAuth providers, user starts browser authorization, completes the rclone
   callback, and checks the session so the returned token is added to the JSON.
8. User edits the JSON or switches to Custom backend for raw setup.
9. Borg UI validates that the JSON is an object and submits the existing
   managed remote payload shape.

For OAuth providers, the UI should not imply Borg UI owns provider credentials.
It should state that rclone performs the browser authorization and Borg UI
starts/polls the rclone authorization process to save the resulting token/config
in the managed config file.

## Backend Design

- Add `GET /api/rclone/providers`.
- Add rclone OAuth session start/poll endpoints for providers that use browser
  OAuth, backed by `rclone authorize --auth-no-open-browser`.
- Keep `POST /api/rclone/remotes` and `PUT /api/rclone/remotes/{id}` payloads
  compatible.
- Redact sensitive fields such as `token`, `access_token`, `refresh_token`,
  `client_secret`, `secret_access_key`, `password`, `pass`, and provider key
  fields before serializing `redacted_config`.
- On update, preserve existing managed config secrets when a redacted marker is
  submitted back by the UI.

## Validation

- Unit test the provider catalog endpoint and provider list contents.
- Unit test that managed remote creation writes the real config file but returns
  redacted sensitive values.
- Unit test that editing a remote with redacted values preserves the existing
  secret in the managed config file.
- Unit test OAuth session start/poll behavior and unsupported-provider rejection.
- Frontend test the guided provider list, Google Drive/OneDrive presence,
  provider template submission, OAuth session token injection, raw custom
  backend path, and mobile bottom sheet rendering.
- Update Storybook stories for the guided create/edit states and regenerate
  snapshots.
- Run the repository-required frontend checks and targeted backend rclone tests.
