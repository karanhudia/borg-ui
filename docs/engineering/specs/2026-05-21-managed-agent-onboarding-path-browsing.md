# Managed Agent Onboarding And Path Browsing Spec

## Goal

Make managed-agent setup a one-command Linux/Raspberry Pi flow, and make
agent-owned path browsing work wherever Borg UI asks for repository or backup
source paths.

## User Model

The primary user is an admin managing one Borg UI control plane and several
machines that run the lightweight `borg-ui-agent`. They need to enroll a new
machine without manually creating venvs or systemd services, then select paths
on that enrolled machine when creating repositories or backup plans.

## Product Direction

The ticket-provided plan is the approved product direction for this unattended
run. The onboarding UI should replace the token-first workflow with an `Add
Agent` wizard that keeps advanced token management available in its existing
tab. The generated command must target the backend API host, not the frontend
dev server, and should warn when that host is local-only.

The repository and backup-plan path pickers should converge on the existing
field/browser pattern. Agent browsing is a source capability, not a separate UI
language. The repository modal should enable browsing after a managed agent is
selected.

UI/UX Pro Max guidance for this change: use progressive disclosure, flat
dashboard surfaces, labeled controls, visible focus states, Lucide icons, and
existing MUI cards/tables. Avoid heavy left accent borders and avoid adding
decorative treatment to operational screens.

## Scope

In scope:

- unauthenticated `GET /agent/install.sh` endpoint that serves a token-free
  Linux/Raspberry Pi installer script;
- installer command generation in the UI, including server URL derivation and
  localhost warnings;
- enrollment token expiry options for hours, days, and never, while preserving
  the existing `expires_in_minutes` API;
- agent revoke/delete support, with delete removing the agent from active fleet
  lists and revoked/deleted agents blocked from polling;
- shared local/SSH/agent path browsing component behavior in repository and
  backup-plan path entry flows;
- Storybook stories and snapshots for the changed managed-agent page states;
- docs for one-command install, expiry semantics, revoke/delete, and localhost
  caveats.

Out of scope:

- macOS or Windows installers;
- agent auto-update;
- replacing the existing SSH Remote Machines feature;
- changing agent credentials to expire after enrollment. Enrollment expiry is
  temporary enrollment only; registered agents keep working until revoked or
  deleted.

## Acceptance Criteria

- Repository wizard browse is enabled for managed-agent execution after a
  selected agent is available, and browsing uses the agent filesystem endpoint.
- Backup-plan source selection and repository path entry share the same
  browsing component/pattern for local, SSH, and managed-agent contexts.
- `GET /agent/install.sh` returns `text/x-shellscript`, requires no UI auth,
  embeds no token, accepts `--server`, `--token`, `--name`, and optional
  `--version`, installs dependencies, registers the agent, writes a systemd
  service, runs `service-check`, and enables/starts the service by default.
- Enrollment tokens support 1 hour, 24 hours, 7 days, 30 days, and Never.
  Existing `expires_in_minutes` payloads remain valid.
- Deleted agents are hidden from normal fleet lists; revoked and deleted agents
  cannot poll jobs; job and log history remains readable.
- The Managed Agents page opens an `Add Agent` wizard with platform, details,
  server URL, install command, copy, waiting, success, and localhost warning
  states.
- Revoke and delete are distinct actions. Delete requires confirmation copy that
  explains it removes the fleet-list entry but does not uninstall the local
  service.
- Managed-agent docs lead with the one-command Linux install and move manual
  setup into advanced/troubleshooting.

## Validation

- Backend: targeted pytest coverage for installer, enrollment tokens, agent
  delete, expired/revoked tokens, and revoked/deleted polling.
- Frontend: Vitest coverage for server URL derivation, wizard token creation,
  command generation, waiting success, localhost warning, revoke, delete
  confirmation, and agent path browsing.
- Storybook: managed-agent fleet overview, Add Agent wizard platform/install
  command/waiting/localhost states, and delete confirmation.
- Repository policy: `ruff check app tests`, `ruff format --check app tests`,
  frontend locales/typecheck/lint/build, snapshots, runtime walkthrough, and
  `git diff --check`.
