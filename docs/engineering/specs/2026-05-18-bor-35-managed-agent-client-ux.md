# BOR-35 Managed Agent Client UX Spec

## Goal

Make the managed-agent beta entry reliable after enablement and make the client
setup path explicit enough for a fresh machine.

## Current Signal

`ManagedAgents` uses the shared React Query key `['systemSettings']`, but its
query function caches an Axios response while `AppSidebar`, `Settings`, and
`BetaFeaturesTab` cache the raw `{ settings }` payload. When the sidebar cache
is present, `ManagedAgents` reads `data.data.settings`, treats the beta flag as
false, and redirects to `/dashboard`. When `ManagedAgents` writes the Axios
response into the shared cache, the sidebar can read `systemData.settings` as
missing and hide the tab until the next clean fetch.

The setup guide also duplicates enrollment-token creation, uses a vague install
step, and places copy actions outside the code fields.

## Design

- Standardize `ManagedAgents` to cache and read the raw system settings payload,
  matching the other users of `['systemSettings']`.
- Keep enrollment-token creation as the single primary top-level action.
- Keep the setup guide concise on the page, with detailed fresh-machine and
  startup guidance in a help dialog.
- Use icon-only copy buttons embedded inside code blocks.
- Explain that the server URL must be reachable from the client. `localhost:7879`
  is only correct when the agent runs on the same host as Borg UI; remote
  clients need the Borg UI host name, IP address, or HTTPS URL.
- Document the same setup and startup guidance in user-facing docs and the agent
  README.

## Acceptance

- Opening `/managed-agents` from a shared `{ settings }` query cache with
  `managed_agents_beta_enabled: true` stays on `/managed-agents`.
- The setup guide contains a concrete clone/install/register/run path.
- The setup guide has no duplicate Create Enrollment Token button.
- Copy controls are icon-only and inside code blocks.
- Startup guidance references the existing systemd and launchd templates.
