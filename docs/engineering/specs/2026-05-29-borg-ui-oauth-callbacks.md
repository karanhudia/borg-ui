# Borg UI-Owned OAuth Callback Spec

## Problem

The guided Cloud Storage OAuth flow still shells out to `rclone authorize` and
depends on rclone's local callback listener at `127.0.0.1:53682`. Borg UI can
open the provider consent URL through a backend redirect, but the provider's
final redirect still targets the rclone loopback listener. That breaks Docker,
remote-server, and reverse-proxy deployments where the user's browser cannot
reach the backend/container loopback interface.

## Desired Outcome

Borg UI owns the OAuth redirect endpoint for Google Drive and Microsoft
OneDrive. Administrators configure Borg UI's public base URL and provider OAuth
app client credentials on the backend. The frontend opens provider consent URLs
that redirect to Borg UI, the backend validates state and exchanges codes
server-side, and the saved managed rclone config contains a rclone-compatible
token JSON plus the matching provider client settings needed for token refresh.

Unsupported providers and advanced setups keep the existing rclone
loopback/manual setup path.

## Scope

- Add backend OAuth provider settings for Google Drive and OneDrive client IDs
  and secrets.
- Use `PUBLIC_BASE_URL` to build provider redirect URLs:
  - `https://example.com/api/rclone/oauth/callback/drive`
  - `https://example.com/api/rclone/oauth/callback/onedrive`
- Validate that the public base URL is absolute, has no query/fragment, and is
  HTTPS unless it is a local development host.
- Add provider-owned OAuth session records with random state values.
- Add a public callback route that validates provider and state, handles
  provider error responses, exchanges authorization codes server-side, and
  stores rclone-compatible token JSON in the session.
- Keep existing rclone loopback OAuth session support for unsupported providers
  and explicit advanced fallback.
- Inject configured provider client settings into managed rclone config writes
  only when a Borg UI-owned OAuth token is saved.
- Redact provider client IDs, provider client secrets, authorization codes, and
  token values from API responses and log-safe error surfaces.
- Update Cloud Storage UI copy, status, and actions so users can distinguish
  Borg UI-owned OAuth from rclone loopback/manual authorization.
- Update user docs for Cloud Storage OAuth, configuration, and reverse-proxy
  callback URL setup.

## Provider Details

Google Drive uses Google's web-server OAuth flow, which is intended for apps
that can store confidential information and maintain state. The backend will
send users to `https://accounts.google.com/o/oauth2/v2/auth`, request offline
access, and redeem codes at `https://oauth2.googleapis.com/token`.

Google scopes:

- `https://www.googleapis.com/auth/drive` for the default rclone `scope=drive`
- `https://www.googleapis.com/auth/drive.readonly` when the user sets
  `scope=drive.readonly`

Microsoft OneDrive uses the Microsoft identity platform authorization-code flow
for confidential web apps. The backend will send users to
`https://login.microsoftonline.com/common/oauth2/v2.0/authorize` and redeem
codes at `https://login.microsoftonline.com/common/oauth2/v2.0/token`.

Microsoft scopes:

- `offline_access`
- `Files.Read`
- `Files.ReadWrite`
- `Files.Read.All`
- `Files.ReadWrite.All`

## UX Design

Use the existing Cloud Storage operational style: compact MUI surfaces,
balanced full outlines, subtle background tinting, lucide icons, and controlled
form state. Do not introduce hero layouts or decorative treatment.

For Google Drive and OneDrive:

1. The provider panel shows whether Borg UI-owned OAuth is configured.
2. When configured, the primary browser authorization button starts the
   provider-owned flow and opens the provider authorization URL directly.
3. The panel shows the exact Borg UI callback URL that must be registered with
   the provider.
4. When not configured, the panel explains the missing backend configuration
   and keeps the rclone loopback/manual fallback available.
5. For unsupported OAuth providers, the panel labels the flow as rclone
   loopback authorization and keeps the existing behavior.

The frontend never displays provider client IDs, provider client secrets,
authorization codes, access tokens, or refresh tokens.

## Backend Design

- Extend provider metadata with:
  - `oauth_mode`: `borg_ui`, `rclone_loopback`, or `manual`
  - `oauth_configured`: boolean
  - `oauth_callback_url`: string or null
  - `oauth_setup_key`: translation key for missing/invalid setup
- Add optional `mode` to OAuth session start requests:
  - `auto` defaults to Borg UI-owned OAuth for configured Google Drive/OneDrive
  - `borg_ui` requires provider-owned OAuth and fails with a setup error when
    unavailable
  - `rclone_loopback` preserves existing `rclone authorize` behavior
- Store Borg UI-owned sessions in the existing in-memory session map with:
  provider, status, state, redirect URI, config, output, error, and timestamps.
- Add callback route outside the authenticated router dependency because
  providers cannot send Borg UI credentials. Security relies on high-entropy
  state and short session TTL.
- Exchange provider codes with `httpx.AsyncClient` and form-encoded payloads.
- Convert token endpoint responses into rclone's token string format:
  `{"access_token":"...","token_type":"Bearer","refresh_token":"...","expiry":"..."}`
- On managed config writes, strip Borg UI internal marker keys and inject the
  configured client ID/client secret for provider-owned sessions.

## Validation

- Backend tests:
  - provider metadata reports Borg UI-owned OAuth status and callback URL
  - invalid or missing public base URL is rejected for provider-owned OAuth
  - callback validates provider and state
  - callback exchanges provider codes server-side
  - provider-owned token config writes rclone-compatible token JSON and client
    settings into the managed rclone config
  - secret and token values are redacted from API responses and log-safe errors
  - rclone loopback/manual fallback remains available
- Frontend tests:
  - Google Drive/OneDrive show Borg UI-owned OAuth when configured
  - provider-owned OAuth starts without exposing client credentials and opens
    the provider URL
  - callback/setup error states are visible
  - rclone loopback/manual fallback remains available
- Storybook:
  - update Cloud Storage or rclone dialog stories for provider-owned OAuth,
    setup-missing, and fallback states
  - regenerate snapshots
- Runtime walkthrough:
  - run Borg UI with `PUBLIC_BASE_URL` and dummy provider credentials
  - start a provider-owned Google Drive or OneDrive flow
  - call the Borg UI callback route with a mocked provider token exchange
  - confirm the flow never requires browser access to `127.0.0.1:53682`

## References

- Google web-server OAuth flow: https://developers.google.com/identity/protocols/oauth2/web-server
- Microsoft identity platform authorization-code flow: https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow
- rclone Google Drive configuration: https://rclone.org/drive/
- rclone OneDrive configuration: https://rclone.org/onedrive/
