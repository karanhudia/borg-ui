---
title: Authentication and SSO
nav_order: 8
description: "Local auth, passkeys, OIDC SSO, and trusted-header authentication"
---

# Authentication and SSO

Borg UI supports these auth options:

| Option | Use when |
| --- | --- |
| Local auth | You want Borg UI to manage usernames and passwords |
| Passkeys | Local users should sign in with WebAuthn passkeys instead of typing a password |
| Built-in OIDC SSO | Borg UI should authenticate users through an OIDC provider |
| Trusted-header auth | A reverse proxy authenticates users and passes trusted headers |
| No auth | Local development only |

Do not expose trusted-header auth or no-auth mode directly to users.

## Local Auth

Local username/password auth is the default. Users can also add passkeys to local password-backed accounts.

The first admin user is created with:

```text
admin / admin123
```

Change the password after first login. For new deployments, set a stronger first password:

```yaml
environment:
  - INITIAL_ADMIN_PASSWORD=change-this-password
```

## Passkeys

Borg UI supports WebAuthn passkeys for local sign-in.

Users can add and remove passkeys from:

```text
Settings > Account
```

Adding a passkey requires the user's current local password. After registration, the login page shows **Sign in with passkey** and also supports browser passkey autofill when available.

Passkeys are local Borg UI credentials. In an SSO deployment they can coexist with OIDC only while local login is enabled.

Requirements:

- the account must have a local password
- the browser and device must support WebAuthn
- the public Borg UI URL must be stable; passkeys are bound to the site origin

## Built-in OIDC SSO

Use built-in OIDC when Borg UI should talk directly to your identity provider.

OIDC users can still use local password and passkey login only if their Borg UI account has local credentials and local login remains enabled.

Configure it in:

```text
Settings > System > OIDC
```

Create an OIDC client in your identity provider and register this callback URL:

```text
https://backups.example.com/api/auth/oidc/callback
```

For a sub-path deployment:

```text
https://example.com/borg-ui/api/auth/oidc/callback
```

The browser-facing Borg UI URL and API URL should be the same public origin. Split-origin setups need extra CORS/cookie work and are not the normal deployment path.

## OIDC Settings

Minimum settings:

| Setting | Meaning |
| --- | --- |
| Enabled | Shows SSO on the login page |
| Provider name | Button label on the login page |
| Discovery URL | Provider `.well-known/openid-configuration` URL |
| Client ID | OIDC client ID |
| Client secret | OIDC client secret |
| Scopes | Usually `openid profile email` |
| Token auth method | `client_secret_post` or `client_secret_basic` |

The discovery URL must use HTTPS, except for localhost development.

If Borg UI builds the wrong callback URL behind a proxy, fix the forwarded headers or set:

```yaml
environment:
  - PUBLIC_BASE_URL=https://backups.example.com
```

You can also set a redirect URI override in the OIDC settings when the provider needs an exact custom value.

## Claims

Default claim names:

| Setting | Default |
| --- | --- |
| Username claim | `preferred_username` |
| Email claim | `email` |
| Full name claim | `name` |

Nested claims can be written with dots, for example:

```text
resource_access.borg-ui.role
```

If the username claim is missing, Borg UI falls back to `sub`, then to the email prefix when possible.

## New Users

OIDC new-user modes:

| Mode | Behavior |
| --- | --- |
| `deny` | Unknown SSO users cannot log in |
| `viewer` | Unknown SSO users are created immediately with the configured default roles |
| `pending` | Unknown SSO users are created inactive and need admin approval |
| `template` | Unknown SSO users copy roles and repository permissions from a template user |

Pending users appear in:

```text
Settings > Users
```

## Roles

Global roles:

- `viewer`
- `operator`
- `admin`

All-repositories roles:

- `viewer`
- `operator`

Borg UI can read roles from OIDC claims when configured. Role claim values must match Borg UI role names.

Admin role claims are only honored when the user also belongs to one of the configured admin groups. This prevents a loose role claim from granting admin access by itself.

If no valid role claim is present, Borg UI uses the configured default role.

## Account Linking

Existing local users can link SSO from:

```text
Settings > Account
```

If an OIDC login matches an existing local username but that account is not linked, Borg UI asks for account linking instead of silently taking over the local account.

Users can unlink SSO only when local auth is still enabled and the account has a local password.

## Disable Local Auth

After OIDC works, you can disable local password and passkey login from the OIDC settings.

Do this only after at least one active admin has successfully linked or logged in through OIDC. Otherwise you can lock yourself out.

## Trusted-Header Auth

Use trusted-header auth when another system, such as Authelia, Authentik proxy mode, OAuth2 Proxy, or Cloudflare Access, authenticates users before requests reach Borg UI.

Environment:

```yaml
environment:
  - DISABLE_AUTHENTICATION=true
  - PROXY_AUTH_HEADER=X-Forwarded-User
  - PROXY_AUTH_ROLE_HEADER=X-Borg-Role
  - PROXY_AUTH_ALL_REPOSITORIES_ROLE_HEADER=X-Borg-All-Repositories-Role
  - PROXY_AUTH_EMAIL_HEADER=X-Borg-Email
  - PROXY_AUTH_FULL_NAME_HEADER=X-Borg-Full-Name
```

Rules:

- only the trusted proxy can reach Borg UI
- the proxy must strip incoming user-controlled auth headers
- the proxy must set the configured headers itself
- bind Borg UI to localhost or isolate it on a private Docker network

If users can reach Borg UI directly, they can spoof the headers.

## No-Auth Mode

No-auth mode is for local development only:

```yaml
environment:
  - ALLOW_INSECURE_NO_AUTH=true
```

Do not use it on a networked deployment.

## Troubleshooting

### Redirect URI mismatch

The callback URL registered with the provider must match Borg UI's callback URL exactly. Check `PUBLIC_BASE_URL`, proxy forwarded headers, `BASE_PATH`, and any redirect URI override.

### SSO button is missing

OIDC must be enabled.

### Passkey login is missing

Passkey login is hidden when local login is disabled for OIDC. It also needs browser WebAuthn support and a registered passkey for this Borg UI origin.

### Passkey registration fails

Confirm that the account has a local password, the current password is correct, and Borg UI is being accessed through the same public origin users will use later.

### Login fails after provider callback

Check that the client secret is saved, then check the discovery URL, client ID, token auth method, scopes, and provider logs.

### User is pending

Approve the user in Settings > Users, or change the new-user mode.

### Role mapping does not grant admin

Configure a group claim and admin groups. Admin role claims without a matching admin group are ignored.

### Local auth was disabled too early

Use container/database access to restore local auth or fix the OIDC settings. Treat this as administrative recovery access.
