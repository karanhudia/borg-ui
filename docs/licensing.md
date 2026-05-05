---
title: Licensing
nav_order: 12
---

# Licensing

Borg UI is open-source software licensed under the GNU AGPL v3.

The app also has plan-based feature gates for some product features. See the current plan details at:

```text
https://borgui.com/buy
```

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
