# Rclone Provider Catalog and OAuth Expansion

## Problem

Cloud Storage currently exposes a small hand-written rclone provider catalog.
That makes common providers easy to set up, but it hides most of rclone's
installed backends. The OAuth path also has a narrow Borg UI-owned callback
implementation for Google Drive and Microsoft OneDrive while other OAuth
providers fall back to rclone's loopback authorization flow.

The result is uneven: users can see only a fraction of rclone's supported
providers, and self-hosted browser authorization remains fragile for OAuth
providers that still depend on `127.0.0.1` loopback callbacks.

## Desired Outcome

Cloud Storage lists the installed rclone provider catalog while preserving
curated Borg UI guidance for common backup targets. Providers with OAuth needs
are represented explicitly, and Borg UI-owned OAuth support is provider-driven
instead of hard-coded to a small conditional.

Operators can pick common providers quickly, search the long-tail provider
list, and understand whether a provider uses Borg UI-owned OAuth, rclone
loopback OAuth, access keys, basic credentials, or manual configuration.

## Scope

- Build provider metadata from rclone's provider catalog when rclone is
  available, with a static fallback for tests and unavailable-runtime states.
- Keep curated overrides for common providers so labels, templates, fields, and
  docs stay concise.
- Add provider grouping/search to the Cloud Storage remote dialog so a large
  provider list remains usable.
- Replace fixed Borg UI-owned OAuth provider checks with a provider registry.
- Store provider OAuth app credentials in a generic table keyed by provider.
- Preserve existing Google Drive and OneDrive Borg UI-owned OAuth behavior.
- Add Borg UI-owned OAuth adapters for standard OAuth providers that can use
  provider auth/token URLs and rclone-compatible token JSON without special
  account discovery.
- Keep rclone loopback/manual fallback for providers without a Borg UI-owned
  adapter or deployments without valid `PUBLIC_BASE_URL`.
- Update docs for expanded provider availability and OAuth callback behavior.

## Out Of Scope

- Guaranteeing every rclone backend can be fully configured without manual JSON.
- Implementing provider-specific post-authorization discovery beyond existing
  OneDrive default drive discovery.
- Replacing rclone's config semantics or hiding advanced provider options.
- Committing generated Argos PNGs.

## Backend Design

Introduce a provider catalog builder in `app/api/rclone.py` or a focused helper
module. It should:

- Start from curated provider definitions for common Borg UI providers.
- Read `rclone config providers` JSON when available.
- Convert rclone provider options into Borg UI field metadata for visible
  required/basic/credential fields.
- Add generated provider entries not covered by curated definitions.
- Fall back to the curated catalog if rclone is unavailable or returns invalid
  JSON.

OAuth should be described by an explicit registry. Each adapter defines:

- provider type
- label
- authorization URL
- token URL
- default scopes or provider-specific authorization params
- whether client secret is required
- optional config finalization hook

Google Drive keeps its Drive scopes and offline prompt behavior. OneDrive keeps
Microsoft scopes and default-drive discovery. Standard OAuth adapters use
rclone's `auth_url` and `token_url` provider metadata where it is enough to
complete an authorization-code exchange and write rclone-compatible token JSON.

Provider OAuth app credentials should move from provider-specific
`system_settings` columns to a generic table with encrypted secret storage.
Legacy Google Drive and OneDrive columns remain readable for migration and
backward compatibility until a later cleanup.

## UI Design

Use the existing Cloud Storage operational UI: compact MUI surfaces, balanced
outlines, small icons, clear status chips, and no marketing treatment.

The Add/Edit remote dialog should:

- Keep common providers near the top.
- Provide search/filter for all providers.
- Use the shared `RichSelect` primitive for provider, destination, SSH,
  managed-agent, rclone-remote, and backup-plan dropdowns so menu sizing,
  56px trigger height, rich-row truncation, and tooltips stay consistent.
- Show provider auth mode in the provider summary.
- Show Borg UI callback URL only for providers with Borg UI-owned OAuth support.
- Keep the rclone loopback fallback action visible for OAuth providers.
- Keep the advanced JSON editor available for generated or uncommon providers.

Do not introduce cards inside cards or heavy left accent borders.

## Provider Set

OAuth/browser-flow providers identified from rclone v1.74.2 include:

- `box`
- `drive`
- `dropbox`
- `gcs`
- `gphotos`
- `hidrive`
- `huaweidrive`
- `jottacloud`
- `mailru`
- `onedrive`
- `pcloud`
- `premiumizeme`
- `putio`
- `sharefile`
- `yandex`
- `zoho`

Not all should receive identical UX. Some providers are better served by
service-account, access-key, or manual setup. The registry should make support
explicit rather than infer correctness from the presence of a `token` field.

## Remaining Follow-Up List

Borg UI-owned callback support is implemented for:

- `box`
- `drive`
- `dropbox`
- `gcs`
- `gphotos`
- `hidrive`
- `huaweidrive`
- `onedrive`
- `pcloud`
- `premiumizeme`
- `putio`
- `sharefile`
- `yandex`
- `zoho`

The standard browser callback adapters above were verified against upstream
rclone backend source. The remaining providers in the OAuth-token provider set
are not simple Borg UI callback adapters:

| Provider | Current behavior | Work left | Icon/logo coverage |
| --- | --- | --- | --- |
| `jottacloud` | Catalog provider with manual config only; not exposed through OAuth session start | Implement a separate Jottacloud setup path if needed: rclone's standard flow consumes a personal login token and then may select/create device and mountpoint state; its traditional flow uses white-label service discovery. | Distinct cloud glyph; no provider logo in installed icon packs |
| `mailru` | Catalog provider with basic/app-password config only; not exposed through OAuth session start | Implement a separate username plus app-password credential flow if needed; rclone obtains the token through password-credentials auth, not a normal browser callback. | Mail.ru logo |

## Validation

- Backend tests cover provider catalog expansion, fallback behavior, generated
  provider metadata, OAuth credential CRUD, legacy credential fallback,
  callback URL metadata, session start, callback exchange, token persistence,
  and redaction.
- Frontend tests cover provider search/grouping, generated provider selection,
  Borg UI-owned OAuth setup, rclone loopback fallback, and JSON submission.
- Shared select tests cover display-only selected values, optional in-menu
  search, search filtering, and selection changes.
- Storybook covers Cloud Storage with expanded provider choices and OAuth setup
  states plus the shared rich-select default/search/narrow-width states.
- Docs explain that rclone has many providers, but Borg UI-owned callback
  support is explicit per provider.
