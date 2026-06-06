# Remote Clients Plan Gate Spec

## Problem

Remote Clients are currently available to any user who has the SSH management
permission. The workflow lets a browser register other Borg UI servers and
switch frontend API traffic to those servers, but it is not tied to the plan
entitlement system. Community users can therefore see and use a workflow that
should be limited to paid plans.

## Desired Outcome

Remote Clients are available only when the `remote_clients` feature is included
in the current plan. The minimum plan is Pro, so Enterprise inherits access.
Community users should keep using this local server normally, while remote
client registration, management, and switching are blocked with existing Borg UI
upgrade messaging.

## Entitlement

Add a `remote_clients` feature key as Pro-minimum in the shared backend and
frontend feature catalogs. The backend catalog feeds `/api/system/info`
`features` and `feature_access`; the frontend catalog remains the fallback when
older responses do not include a feature access override.

## UI Behavior

- Sidebar navigation should show Remote Clients only when the user has SSH
  management permission and the plan can access `remote_clients`.
- The `/remote-clients` route should continue to enforce SSH management
  permission and should render the shared `PlanGate` upgrade treatment for
  users whose plan lacks `remote_clients`.
- The global server target switcher should keep the local server selectable for
  every plan.
- The global server target switcher should not silently allow unavailable-plan
  users to switch to a remote target or open Remote Clients management.
- Upgrade copy should be specific to Remote Clients and use the existing Borg UI
  upgrade prompt treatment rather than adding a new gate pattern.
- Disabled remote targets should remain visibly disabled and keyboard-safe.

## Non-Goals

- Removing stored remote clients on downgrade.
- Adding backend persistence or API enforcement for remote clients; the current
  Remote Clients implementation is browser-local.
- Changing permissions for Remote Machines, Managed Agents, Cloud Storage, or
  other Infrastructure items.
- Changing plan pricing, licensing activation, or entitlement refresh behavior.

## Acceptance Mapping

- Remote Clients navigation and management access are gated to Pro and
  Enterprise users.
- Community users see the existing plan-gate upgrade treatment on the management
  page.
- The global server selector preserves local server access and blocks remote
  add/switch/manage paths for Community users.
- Pro and Enterprise users retain Remote Clients navigation, management, and
  switching.
- Tests cover allowed and denied plan states for navigation, management, and
  server selection.
- Storybook covers locked and allowed states for the changed UI surfaces.

## Validation

- Targeted Vitest tests for `AppSidebar`, `RemoteClients`, and
  `BackendTargetSwitcher`.
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- Backend feature-catalog tests if `app/core/features.py` changes.
- Runtime walkthrough covering a denied Community path and an allowed Pro path.
