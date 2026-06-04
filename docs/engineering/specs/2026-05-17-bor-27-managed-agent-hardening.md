# BOR-27 Managed Agent Hardening Spec

## Goal

Make the existing `feature/managed-cli-agent` branch reviewable as a client/server managed-agent MVP for Borg UI: one central Borg UI server manages lightweight outbound CLI agents installed on client machines.

## User Model

The primary user is an admin who wants one Borg UI server for a fleet of machines. The fleet may be an enterprise estate with workstations and servers behind firewalls, or a self-hosted lab with several SBCs and home servers. The client machine owns its local data and runs Borg locally; Borg UI remains the control plane for enrollment, repository configuration, job history, logs, and status.

## Product Direction

Use the managed-agent model already present on the branch:

- agents register using short-lived enrollment tokens generated in the server UI;
- agents authenticate with scoped agent credentials and poll over outbound HTTPS;
- admins can view agents, token state, and jobs from a server-side management page;
- repositories can target an enrolled agent so backup execution happens on that machine;
- agent jobs update existing backup job progress/log surfaces where linked.

This is more useful than requiring a full Borg UI Docker deployment per client machine because it keeps the admin interface centralized while preserving Borg's security and locality model. It also avoids inbound firewall requirements on clients, which matters for laptops, NATed SBCs, and enterprise networks.

## Design Notes

UI/UX Pro Max returned an enterprise infrastructure/dashboard direction: restrained management UI, accessible contrast, SVG icons, visible focus, and scannable status surfaces. Borg UI already uses MUI surfaces, Lucide icons, compact tables, chips, and outlined cards. The hardening pass should stay in that language instead of introducing a new decorative style.

The Managed Agents UI should read as an operational dashboard, not a landing page. It should prioritize:

- fleet status and recency at the top;
- tables/cards that show actionable state without heavy left accent borders;
- enrollment token creation with a copyable command;
- job progress, cancellation, and log viewing;
- Storybook coverage for the primary non-empty state.

## Scope

In scope for this pass:

- keep and validate the existing server/agent/API implementation on the feature branch;
- resolve the merge from latest `origin/main`;
- add a Storybook story and snapshot for the Managed Agents UI state;
- tighten any compile/test failures exposed by validation;
- document the branch plan and verification evidence.

Out of scope for this pass:

- Windows service support;
- WebSocket/MQTT transport;
- agent auto-update;
- restore, prune, check, compact, and mount execution through agents beyond the current backup MVP;
- replacing the existing SSH Remote Machines feature.

## Acceptance Criteria

- The branch contains a reviewable managed-agent MVP with server APIs, CLI runtime, and management UI.
- The Managed Agents UI has Storybook coverage for a realistic fleet/job/token state.
- Backend and frontend validation required by the repository policy passes for the final commit.
- Runtime walkthrough evidence shows the server-side managed-agent path renders and can be inspected locally.
- PR metadata and Linear workpad reflect the final validation and any residual limitations.
