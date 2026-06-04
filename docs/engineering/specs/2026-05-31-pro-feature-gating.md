# Pro Feature Gating Spec

## Problem

Community plan users can currently configure rclone-backed repositories/remotes,
managed-agent repositories/sources, and backup plans that combine different
source types. These are paid-plan capabilities, so the current behavior lets
Community users reach workflows they should not be able to use.

## Goals

- Gate rclone/cloud-storage backup and repository capabilities to Pro and
  Enterprise users.
- Gate managed-agent backup and repository capabilities to Pro and Enterprise
  users.
- Gate backup plans that combine distinct source types to Pro and Enterprise
  users.
- Keep multiple locations of the same source type allowed for Community users
  where the underlying backup route supports them.
- Enforce the rules in backend validation, not only through frontend controls.
- Surface frontend gates with existing Borg UI plan-gate/shared component
  patterns.

## Non-Goals

- Changing plan pricing, license activation, or entitlement fetching.
- Gating single-source database scanning when it remains a local source.
- Removing existing data for paid features when an instance is downgraded.
- Reworking navigation structure or replacing shared source/repository wizard
  components.

## Entitlements

Add three feature keys to the shared backend/frontend feature catalog:

- `rclone`: Pro minimum.
- `managed_agents`: Pro minimum.
- `backup_plan_mixed_sources`: Pro minimum.

The backend remains authoritative. Frontend checks use the same feature keys so
the UI can disable paid-only choices before submit while API validation rejects
direct calls or stale clients.

## Backend Behavior

### Backup Plans

Backup plan validation should inspect normalized `source_locations` instead of
only the legacy `source_type` value. A plan is considered mixed only when the
set of normalized source location types has more than one value, such as
`local + remote`, `remote + agent`, or `local + agent`.

Community users are rejected when:

- any normalized source location has `source_type: "agent"`;
- the normalized source locations contain more than one distinct source type;
- existing paid constraints, such as multiple enabled repositories or parallel
  repository run mode, still apply.

Community users are not rejected solely because a plan has multiple source
locations if every location has the same normalized source type.

Runtime backup-plan access checks should evaluate the stored source locations
the same way creation/update validation does, so downgraded paid configurations
are not runnable under Community plan access.

### Rclone

Authenticated rclone management APIs require `rclone` feature access. Repository
create/import/update paths that create, enable, browse, sync, or otherwise use
rclone-backed storage also require `rclone` feature access. Public OAuth
callback endpoints keep their existing unauthenticated behavior, because they
complete an external provider redirect and do not themselves grant Community
access to create or use an rclone remote.

### Managed Agents

Admin managed-agent APIs require `managed_agents` feature access. Repository
create/import/update paths that use a managed agent as the execution target also
require `managed_agents` feature access. Agent runtime heartbeat/job endpoints
are left alone so an already-installed agent can report in, but Community users
cannot create new managed-agent jobs or backup definitions through gated admin
surfaces.

## Frontend Behavior

- Backup plan source selection disables the managed-agent destination for
  Community users and shows paid-plan context through existing plan-gate styling.
- Backup plan source selection keeps multiple same-type locations available, but
  disables applying a selection that combines distinct source types for
  Community users.
- Repository creation disables managed-agent and rclone/cloud-storage choices
  for Community users and prevents the wizard from submitting paid-only payloads.
- The Managed Agents page shows a plan gate when the user has the admin
  permission but lacks the paid plan entitlement.
- Storybook stories cover the locked Community states for changed components.

The UI remains operational and compact: no heavy accent borders, no marketing
copy, and no replacement wizard shell.

## Acceptance Mapping

- Community users cannot select or submit rclone-based backup/repository
  sources.
- Community users cannot select or submit managed-agent backup/repository
  sources.
- Community users cannot create backup plans that mix distinct source types.
- Multiple locations of the same source type remain allowed when otherwise
  supported.
- Pro and Enterprise users retain rclone, managed-agent, and mixed-source
  workflows.
- Backend validation returns a paid-plan feature error for prohibited
  Community-tier requests.
- Affected frontend states use shared plan-gate/shared component patterns and
  have Storybook coverage plus updated snapshots.

## Validation

- Backend unit tests for backup-plan mixed source gating, same-type
  multi-location allowance, managed-agent source gating, rclone API gating, and
  repository rclone/managed-agent gating.
- Frontend tests for backup source chooser gating and repository wizard paid
  option gating.
- Storybook snapshots for changed source/repository gating stories.
- Required backend and frontend quality gates from repository policy.
- Runtime walkthrough covering a Community blocked path and a Pro allowed path.
