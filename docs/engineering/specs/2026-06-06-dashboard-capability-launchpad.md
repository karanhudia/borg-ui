# Dashboard Capability Launchpad Spec

## Problem

Borg UI has gained several newer operational workflows: backup plans, cloud
storage remotes, remote Borg UI clients, restore verification, and scheduled
plan automation. The dashboard already summarizes system health, storage,
repository status, upcoming work, and recent activity, but it does not give
users a compact way to discover those newer capabilities or act on the next
useful setup gap.

The Linear reference image is not directly available outside Linear auth during
this session, so the implementation should use the request's intent rather than
pixel-matching the image: take dashboard inspiration and add a useful Borg
UI-specific overview surface.

## Desired Outcome

Add a compact dashboard launchpad that summarizes key Borg UI capabilities and
links to the right workflow:

- Backup plan and automation coverage.
- Cloud storage remotes.
- Remote Borg UI clients.
- Restore verification coverage.

The launchpad should feel like part of the current operational dashboard: dense,
scan-friendly, neutral-surface rows, restrained Lucide icons, neutral text for
contrast, and responsive one-column behavior in the narrow left rail.

## Design

Create a focused `CapabilityLaunchpad` component under
`frontend/src/pages/dashboard-v3/`. It accepts the current dashboard summary and
repository health arrays plus cloud remote and remote client counts. It derives
four capability rows and reports interaction through callbacks passed by
`DashboardV3`.

The implementation intentionally does not add a dashboard backend field. It uses
existing frontend data sources:

- `summary.active_backup_plans`, `summary.total_backup_plans`,
  `summary.active_automations`, and `summary.total_automations` for plan and
  automation readiness.
- `rcloneAPI.listRemotes()` for configured Cloud Storage remotes.
- `listRemoteBackendClients()` for browser-registered remote Borg UI clients.
- `restore_check_configured` and `latest_restore_check_status` for restore
  verification coverage.

Each row shows a short title, mono numeric value, concise status label, icon, and
trailing arrow. The whole row is the action target with an accessible label.
Rows navigate to existing routes:

- Backup plans: `/backup-plans`.
- Cloud storage: `/cloud-storage`.
- Remote clients: `/remote-clients`.
- Restore verification: `/schedule/restore-checks`.

The launchpad belongs in the left dashboard rail between resource gauges and
upcoming/storage panels. That keeps it visible without competing with the main
repository health and activity panels. The dashboard skeleton should mirror the
new panel so loading layout stays stable.

## Testing

Use test-first coverage for the derived behavior:

- A DashboardV3 test should fail until the launchpad renders backup plan, cloud
  storage, remote client, and restore verification rows with expected counts.
- A DashboardV3 test should fail until launchpad actions navigate to the
  expected existing routes.
- A component Storybook story should cover mixed adoption and empty-start
  states for the launchpad.

## Documentation

Update `docs/navigation.md` so Dashboard is described as a place to identify
capability setup gaps and jump to backup plans, cloud storage, remote clients,
or restore-check scheduling. This is a main dashboard flow change, but it does
not alter sidebar tabs or navigation groups.

## Validation

- `cd frontend && npm test -- --run src/pages/__tests__/DashboardV3.test.tsx`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- Local UI walkthrough through the dashboard or Storybook at desktop and mobile
  widths, confirming the launchpad renders and actions target existing routes.
