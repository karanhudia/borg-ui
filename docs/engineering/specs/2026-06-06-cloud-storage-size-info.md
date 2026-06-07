# Cloud Storage Size Info Spec

## Problem

Cloud Storage remotes list provider, status, and repository usage count, but they do not show capacity. Remote Machines already show a storage band with used, free, total, and percentage used, so cloud storage users cannot quickly compare available capacity after testing a remote.

## Desired Outcome

Cloud Storage remote cards show the last known capacity from `rclone about` in the same compact used/free/total pattern as Remote Machine cards. When a provider does not return capacity, the card shows a graceful unavailable state instead of breaking the remote workflow.

## Acceptance Criteria

- The rclone remote API includes a nullable `storage` object with `total`, `used`, `available`, `percent_used`, formatted values, and `last_check`.
- Testing a remote updates the stored storage fields when `rclone about` returns usable capacity data.
- Testing a remote clears storage fields when `rclone about` succeeds but the provider does not return usable capacity data.
- Cloud Storage cards show used/free/total plus a usage bar when `storage` is present.
- Cloud Storage cards show a compact "No storage info" state when `storage` is missing.
- Storybook demonstrates remotes with and without storage info.

## Design Notes

- Persist the storage snapshot on `rclone_remotes`, mirroring the SSH connection storage fields rather than adding a new table.
- Keep collection tied to the existing "Test connection" action. This avoids background polling or new provider-specific behavior.
- Parse common `rclone about` text output keys (`Total`, `Used`, `Free`) and tolerate unsupported providers by returning `None`.
- Reuse the current Cloud Storage card surface. The capacity band should use balanced borders/background tinting and existing Lucide icons, not heavy accent borders.

## Validation

- `pytest tests/unit/test_api_rclone.py::<targeted storage tests>`
- `cd frontend && npm test -- CloudStorage.test.tsx`
- Backend required checks for backend changes.
- Frontend required checks for UI changes.
- Local Cloud Storage walkthrough with seeded or mocked size data.

## Original Request

> Can we show size info of cloud storage just like we show for rrmote machines.
