---
title: What Borg UI Does With Your Data
nav_order: 8
description: "What Borg UI stores, what it encrypts, and what leaves your machine"
---

# What Borg UI Does With Your Data

Borg UI holds the keys to your backups. Before you install it, you should know
what it keeps, what it protects, and what it sends anywhere else.

Everything on this page is checkable. Borg UI is AGPL-3.0 and the whole source
tree is public, so every claim below names the file that implements it. If a
claim and the code disagree, the code is right and this page is a bug.

For hardening a deployment (TLS, the Docker socket, reverse proxies, `/metrics`),
see [Security](security). This page is about the software itself.

## Secrets Are Encrypted At Rest

Your Borg repository passphrase is encrypted in the database, not stored in
plain text. So are the other secrets the app holds:

| Secret | Where |
| --- | --- |
| Borg repository passphrase | `repositories.passphrase` |
| SSH private keys | SSH key storage |
| Two-factor (TOTP) secrets | `users.totp_secret_encrypted` |
| OIDC client secret and cached ID tokens | OIDC settings, session rows |
| Cloud provider OAuth client secrets | Google Drive, OneDrive settings |
| Password-type script parameters | Script parameter values |

Encryption is Fernet (AES-128-CBC with an HMAC), keyed from the instance's
`SECRET_KEY`. See `EncryptedString` in `app/database/models.py` and
`encrypt_secret` in `app/core/security.py`.

**What this protects against:** someone who reads a copy of the database, such
as a stolen backup of `/data`, a leaked volume snapshot, or an SQL injection
that dumps a table.

**What it does not protect against:** someone who has your whole `/data`
directory. The key is derived from `SECRET_KEY`, which is generated into `/data`
on first boot, so an attacker holding all of `/data` holds the key as well.
Treat `/data` as being exactly as sensitive as the backups it can restore, and
set `SECRET_KEY` yourself if you want the key to live somewhere else.

## SSH Hosts Are Verified

Every SSH connection Borg UI makes verifies the remote host's key. Connecting
to a machine whose key does not match the one on record fails; it is never
accepted silently.

The model is OpenSSH's own trust on first use:

- **New connections.** When you add a remote machine, Borg UI shows you the
  host's fingerprint and asks you to confirm it before storing it. The
  fingerprint shown matches `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`
  on the host exactly, so you can compare the two.
- **Connections that predate this feature.** Those were already running with no
  verification at all. Rather than break every existing install on upgrade, the
  key in use is recorded on first contact after the upgrade.
- **Either way, a key that changes later is refused** and you have to
  re-verify before the connection works again.

The recorded key is stored on the connection row and is visible in the UI, so
you can see what your instance trusts. See `app/utils/ssh_host_keys.py`.

Before this shipped, every SSH invocation passed `StrictHostKeyChecking=no`
with `UserKnownHostsFile=/dev/null`, meaning anything that answered on the
address was trusted. If you are running an older version, upgrade.

## What Leaves Your Machine

Two things, both of which you can see and control.

### The license service

Your instance talks to a license service to activate the 30-day full access
period, to check a license key you entered, and to refresh entitlement state
afterward. The endpoint defaults to `https://license.borgui.com` and is
overridable with `ACTIVATION_SERVICE_URL`, so if you want to see the traffic or
block it, point that at your own host or firewall the one you configured.

Four requests exist, and this is every field each one sends
(`app/services/licensing_service.py`):

| Request | Fields |
| --- | --- |
| Full access activation (`/v1/trials/activate`) | `instance_id`, `app`, `app_version`, `hostname`, `fingerprint`, `requested_plan` |
| Entitlement refresh (`/v1/entitlements/refresh`) | `instance_id`, `current_entitlement_id`, `app_version` |
| License activation (`/v1/licenses/activate`) | `instance_id`, `license_key`, `app_version` |
| License deactivation (`/v1/licenses/deactivate`) | `instance_id`, `license_id` |

`instance_id` is a random id generated on your instance. `hostname` is the
container's `HOSTNAME` environment variable, and it is sent only by the first
request. No authentication headers are attached to any of them.

Nothing else is in these requests: no repository names, no paths, no archive
contents, no file names, no user accounts, and no email addresses.

Community does not need a license key and no feature is gated behind reaching
this service. If it is unreachable, Borg UI keeps working.

To stop the contact entirely, set:

```bash
ENABLE_STARTUP_LICENSE_SYNC=false
```

That covers both the call at startup and the hourly refresh, so the instance
stops contacting the service on its own. Plan upgrades and full-access
activation then cannot refresh automatically.

What remains is only contact you start yourself: entering a license key,
refreshing it, or removing it from Settings, all admin-only actions that do
nothing until you take them. If you want an instance that cannot reach the
service at all, block it at your firewall.

### Usage analytics

The web UI loads [Umami](https://umami.is) to count page views and feature
usage. It is on by default and you can turn it off in Settings > Preferences.

Before anything is sent, your real hostname and URL are replaced with
`app.borgui`, so your private DNS names and IP addresses do not leave the
browser. The script tag is loaded with `referrerpolicy="no-referrer"` so the
request that fetches it cannot carry the origin either. The identifier attached
to a session is a hash of your install id and username, not the username
itself. See `frontend/src/utils/analytics.ts` and [Analytics](analytics).

Nothing else phones home. No crash reporting, no error telemetry, no update
beacon.

### What never leaves

Your backup data. Borg UI runs `borg` against your repositories on your
infrastructure. Archive contents, file names, and repository paths are never
transmitted anywhere. There is no cloud component in the backup path.

## Your Keys Keep Working

- Borg UI is AGPL-3.0. You can read it, fork it, patch it, and run your fork.
- Repositories are ordinary Borg repositories. If Borg UI disappears tomorrow,
  `borg list`, `borg extract`, and `borg mount` still work against them from
  the command line. There is no proprietary format and no lock-in.
- A license key is a signed document validated on your instance. It is not a
  runtime permission slip fetched from us on every action.

## Reporting a Vulnerability

Report security issues privately through
[GitHub security advisories](https://github.com/karanhudia/borg-ui/security/advisories/new)
rather than a public issue.
