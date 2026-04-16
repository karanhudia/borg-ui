---
layout: default
title: Licensing
nav_order: 12
---

# Licensing

Borg UI is open-source software licensed under the GNU AGPL v3. On top of the open-source core, it offers three tiers that unlock additional features.

---

## Tiers

### Community

Free, no license key required. Includes:

- Unlimited repositories
- Scheduled backups with configurable retention and pruning
- Up to 5 user accounts
- Archive browsing and file-level restore
- Email and webhook notifications
- Script library and pre/post-backup hooks
- Prometheus metrics export
- Two-factor authentication (TOTP) with recovery codes
- Passkeys (biometric and hardware key login)
- Single server deployment, no external calls required after activation

### Pro

Requires a Pro license key. Includes everything in Community, plus:

- Borg v2 beta access
- Up to 10 user accounts
- Deployment on up to 3 servers

Coming soon: multi-repository backup, multi-source backup, backup reports, alerts and monitoring, automatic database and Docker container backup, Rclone support.

### Enterprise

Requires an Enterprise license key. Includes everything in Pro, plus:

- Role-based access control (RBAC) with granular permissions
- Unlimited user accounts
- Deployment on up to 15 servers

Coming soon: centralized multi-instance management, immutable audit log export, approval workflows for sensitive actions.

---

## 60-Day Full Access Period

Every new Borg UI installation automatically receives a **60-day full access period** on first boot. During this period, all Pro and Enterprise features are unlocked with no license key required. After 60 days, the instance returns to Community tier automatically.

This applies to self-hosted instances including air-gapped and private network deployments.

---

## Activation Service

On first boot, Borg UI contacts `license.borgui.com` to register the instance and activate the 60-day full access period. This call sends basic instance metadata only: a generated instance identifier and the application version. No personal data, repository contents, backup paths, or credentials are ever sent.

The activation endpoint is configured via the `ACTIVATION_SERVICE_URL` environment variable. It defaults to `https://license.borgui.com`. The 60-day trial is activated at this point regardless of whether you intend to purchase a license.

---

## Purchasing a License

Visit [borgui.com](https://borgui.com) to purchase a Pro or Enterprise license key. Once purchased, enter the key in **Settings > System** to activate the corresponding tier.
