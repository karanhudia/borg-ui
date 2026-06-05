# Remote Backend Client Switching Spec

## Problem

Borg UI can manage lightweight agents, but users who install full Borg UI on
multiple machines cannot use one frontend as a control surface for another
machine's backend. The current frontend binds its Axios and fetch helpers to one
static API base URL at startup. Operators must manually open another deployment
or change environment configuration to view a different backend.

## Desired Outcome

Add a frontend-managed Remote Clients mode. A user can register Borg UI backend
URLs, check their reachability and version compatibility, and switch the active
frontend target between the local backend and a selected remote backend. The
workflow should be simpler than managed agents: name, backend URL, health check,
status, version, and switch.

## Design

Remote clients are stored in browser local storage. This keeps the feature
available before the target backend is selected and avoids requiring a server to
persist endpoints for other servers. Each remote client stores:

- stable id;
- display name;
- normalized API base URL;
- derived web base URL for health checks;
- creation/update timestamps;
- latest health status, error, checked-at timestamp, app version, Borg versions,
  and compatibility result.

The local backend remains a synthetic built-in target using the existing
`VITE_API_URL || BASE_PATH/api` behavior.

The URL normalizer accepts DNS names, localhost URLs, LAN IPs, HTTPS
deployments, and URLs with existing `/api` or deployment-prefix paths. Bare
localhost and private-network inputs default to `http`; bare DNS inputs default
to `https`. URLs ending in `/api` are used as API bases. Other paths append
`/api`, preserving reverse-proxy prefixes such as `https://host/borg`.

Health checks are two-stage:

- reachability probes the derived web base `/health` without requiring auth;
- version and compatibility probes `<apiBase>/system/info` using the selected
  target's existing auth transport and token state.

Compatibility is based on the installed frontend version and the remote
backend's `app_version`. Matching major versions are compatible. Missing or
unparseable versions are marked unknown. Different major versions are blocked
from activation so the UI does not silently operate against an incompatible API
contract.

## Authentication

JWT tokens are scoped by backend target. The local backend continues to use the
legacy `access_token` localStorage key for backward compatibility. Remote
targets use target-specific token keys. When a user switches to a remote backend
that requires JWT auth and has no saved token, the normal login screen appears
against that backend. A compact target switcher is also shown in the auth shell
so the user can return to the local backend without being trapped on an
unauthenticated remote target.

Proxy-auth and insecure-no-auth modes continue to rely on the selected backend's
own auth config. Cross-origin proxy-auth deployments may require browser and
reverse-proxy CORS credentials to be configured outside Borg UI; the UI should
surface reachability/auth failures clearly rather than silently falling back to
local data.

## Frontend

Add a `RemoteBackendProvider` above `AuthProvider`. It exposes the active target,
registered clients, health checks, CRUD actions, and switch action. The existing
API helpers read the active API base URL at request time instead of capturing a
constant at module load. React Query cache is reset on target changes so pages
refetch from the selected backend.

Add a global target control near the profile menu in `AppHeader`. It shows the
current backend, local/remote state, health, version, and switch actions. It uses
semantic buttons, Lucide icons, subtle outlines, and status chips instead of
heavy accent borders.

Add a `Remote Clients` page under the Infrastructure navigation group, above
Remote Machines. The page lists local and registered remote clients, supports
add/edit/delete/check/switch, and shows clear online, offline, checking,
unknown, and incompatible states. Use MUI, existing layout patterns, shared
`ResponsiveDialog`, and labelled controls.

Add the same target selector to the auth layout so users can switch away from a
remote target before logging in.

## Backend

No backend persistence is required. Existing `/health` and `/api/system/info`
contracts are sufficient for reachability and version checks. Backend tests are
not required unless implementation changes those contracts.

## Testing

Use TDD for behavior changes.

Frontend targeted tests cover:

- URL normalization for localhost, private IPs, DNS names, HTTPS URLs, existing
  `/api` suffixes, and reverse-proxy prefixes.
- localStorage persistence, active target fallback, target-scoped token keys,
  and incompatible target activation blocking.
- dynamic Axios, fetch, and download URL helpers using the selected backend.
- AppHeader target switcher showing local and remote targets.
- Remote Clients page add/edit/delete/check/switch states.
- AppSidebar navigation includes Remote Clients under Infrastructure.
- Login/auth shell exposes the target switcher.

Storybook should cover the target switcher and Remote Clients page in local,
online remote, offline remote, and incompatible remote states.

## Documentation

Update `docs/navigation.md` to list Remote Clients under Infrastructure. Add a
new `docs/remote-clients.md` describing setup, URL rules, authentication,
health checks, version compatibility, DNS/reverse-proxy notes, and switching
back to local.

## Validation

- `cd frontend && npm run test -- --run <targeted test paths>`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- Runtime walkthrough: register a remote client URL, check it, switch requests
  to the remote API base, return to local, and confirm navigation remains
  usable.
