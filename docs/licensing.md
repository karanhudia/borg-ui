---
title: Licensing
nav_order: 12
---

# Licensing

Borg UI is open-source software licensed under the GNU AGPL v3.

The app also has plan-based feature gates for some product features.

## Current Plan Gates

| Feature | Community | Pro | Enterprise |
| --- | --- | --- | --- |
| Borg 1 repositories | yes | yes | yes |
| Scheduled backups | yes | yes | yes |
| Archive browsing and restore | yes | yes | yes |
| Notifications | yes | yes | yes |
| Script hooks | yes | yes | yes |
| Prometheus metrics | yes | yes | yes |
| Users | up to 5 | up to 10 | unlimited |
| Borg 2 beta access | no | yes | yes |
| RBAC | no | no | yes |

Roadmap items may appear in the plan drawer, but they should not be documented as current behavior until code ships.

## Full Access Period

New installations may receive a full access period on first boot. During that period, Pro and Enterprise-gated features are temporarily available.

After the period ends, the instance returns to the active plan.

## Activation Sync

Startup license sync contacts:

```text
https://license.borgui.com
```

To disable startup sync:

```bash
ENABLE_STARTUP_LICENSE_SYNC=false
```

## Enter a License

Open Settings > Licensing and enter the license key.

The app stores the effective plan locally and refreshes activation state when license sync is enabled.

## Offline Use

The Community feature set does not require a license key.

If you disable activation sync, plan upgrades and full-access activation cannot refresh automatically.
