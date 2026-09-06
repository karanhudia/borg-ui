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

Your instance talks to `https://license.borgui.com` to activate the 30-day full
access period, to check a license key you entered, and to refresh entitlement
state afterwards. Each request sends:

| Field | Value |
| --- | --- |
| `instance_id` | A random id generated on your instance |
| `app` | The literal string `borg-ui` |
| `app_version` | The version you are running |
| `hostname` | The container's `HOSTNAME` environment variable |
| `requested_plan` | The plan being asked for |

That is the whole payload (`app/services/licensing_service.py`). No repository
names, no paths, no archive contents, no file names, no user accounts, no email
addresses, and no authentication headers.

Community does not need a license key and no feature is gated behind reaching
this service. If the service is unreachable, Borg UI keeps working.

Contact happens at startup and then on a background refresh roughly every hour.
`ENABLE_STARTUP_LICENSE_SYNC=false` currently suppresses only the startup call,
not the background refresh, so it does not yet make an instance fully offline.
If you need an instance that never reaches the network, block the host at your
firewall until that setting covers both.

### Usage analytics

The web UI loads [Umami](https://umami.is) to count page views and feature
usage. It is on by default and you can turn it off in Settings > Preferences.

Before anything is sent, your real hostname and URL are replaced with
`app.borgui`, so your private DNS names and IP addresses do not leave the
browser. The identifier attached to a session is a hash of your install id and
username, not the username itself. See `frontend/src/utils/analytics.ts` and
[Analytics](analytics).

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
