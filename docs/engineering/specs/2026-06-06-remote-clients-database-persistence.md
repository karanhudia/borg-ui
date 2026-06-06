# Remote Clients Database Persistence Spec

## Problem

Remote Clients are currently stored in browser localStorage. A saved remote
client is therefore available only in the browser where it was created, and an
admin loses the saved list when signing in from another device.

Remote Clients also represent a system-wide switching capability. The existing
UI is already hidden behind `settings.ssh.manage`, which maps to admin, but the
storage layer and target switcher still rely on browser-local state. The new
server-side contract needs to enforce admin-only access instead of trusting the
frontend.

## Desired Outcome

Persist saved remote clients in the Borg UI database. Any authenticated admin
can list, create, update, delete, check, and switch to the saved remote clients
from another browser or device.

The login JWT remains stored in localStorage using the current target-scoped
token behavior. The active backend target remains browser-local because it is a
per-browser routing choice, not a shared system setting. Switching to a remote
client still causes the selected target's normal auth flow to run when a token
is missing.

## Design

Add a `remote_backend_clients` table with string IDs so legacy browser-saved
client IDs can be migrated without breaking the active-target localStorage key.
Rows are global, not per-user, because the feature is admin-only and represents
registered Borg UI servers for the installation.

Each row stores:

- `id`;
- `name`;
- normalized `api_base_url`;
- normalized `web_base_url`;
- creation and update timestamps;
- latest health status, checked-at timestamp, app version, Borg versions,
  error, compatibility state, and compatibility message.

Add an admin-only FastAPI router at `/api/remote-clients`:

- `GET /api/remote-clients` lists saved clients.
- `POST /api/remote-clients` creates a client from a name and backend URL.
- `PUT /api/remote-clients/{client_id}` renames or retargets a client.
- `PATCH /api/remote-clients/{client_id}/health` persists the latest UI-run
  health check result.
- `DELETE /api/remote-clients/{client_id}` removes a client.

The backend normalizes the URL with the same rules as the frontend so the
database contract is stable and independently testable.

## Frontend Behavior

Replace client-list localStorage reads/writes with a provider-owned in-memory
snapshot hydrated from the active backend's `/remote-clients` API. The provider
continues to keep the active target and JWT token keys in localStorage.

After login or token changes, the provider refreshes the saved client list. If
legacy `borg_ui_remote_backends` localStorage entries exist, an authenticated
admin imports them into the database once, preserving their IDs where possible,
then removes the legacy list only after successful import.

Remote Clients UI remains visually consistent with the existing page: dense
admin controls, lucide icons, MUI surfaces, subtle full outlines, and shared
`ResponsiveDialog`/`PlanGate` primitives. No new decorative layout pattern is
introduced.

## RBAC

Backend endpoints require `get_current_admin_user`. Non-admin users receive
403 for list, create, update, health update, and delete.

Frontend surfaces continue to use `settings.ssh.manage` for admin visibility.
The target switcher also treats remote clients as unavailable when the user
lacks that permission, so old browser state cannot expose a remote switching
path to non-admin users.

## Non-Goals

- Sharing the active backend target across devices.
- Moving JWTs out of localStorage.
- Storing remote server passwords or API secrets in the database.
- Changing Remote Machines, Managed Agents, SSH connection persistence, or plan
  pricing behavior.

## Acceptance Mapping

- Saved remote clients are loaded from the database rather than
  `borg_ui_remote_backends` localStorage.
- Legacy browser-saved clients are imported once for admins and then removed
  from the legacy localStorage key.
- The legacy `access_token` key remains the local backend JWT key.
- Remote target tokens remain scoped to target-specific localStorage keys.
- Non-admin users cannot call any remote-client persistence endpoint.
- Non-admin users do not see Remote Clients management and cannot switch to
  browser-stale remote targets.
- Storybook covers the updated Remote Clients page state.

## Validation

- Backend unit tests for CRUD, URL normalization, health persistence, and
  non-admin 403s.
- Frontend Vitest tests for provider DB hydration, legacy import, JWT key
  preservation, Remote Clients UI, and target switcher permission gating.
- Storybook story for the database-backed Remote Clients page state.
- Standard backend and frontend validation commands for the changed scope.
- Runtime walkthrough covering admin save/switch from the DB-backed list and
  non-admin visibility/access denial.
