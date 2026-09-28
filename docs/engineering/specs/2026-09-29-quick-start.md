# Quick Start: one guided setup for a working backup

**Date:** 2026-09-29
**Status:** Design agreed with Karan 2026-09-29, implementation in stacked PRs
**Plan:** `docs/engineering/plans/2026-09-29-quick-start.md`

## Why

Borg UI has good pages for every piece of a backup (SSH connections, managed
agents, repositories, backup plans, schedules, maintenance), but a person who
has never set up server backups does not know which pieces they need or in
what order. Today they visit four or five tabs and make a dozen expert
decisions (encryption mode, compression, retention, prune/compact) before the
first backup runs. Prune, compact and check default to off in the plan
wizard, so a beginner who does finish often ends up with a repository that
grows forever.

Quick Start is a single guided dialog that asks plain-language questions and
then creates everything for a working, scheduled, self-maintaining backup. It
becomes the primary way to set up a new backup. The existing wizards stay for
advanced setups and editing.

## Scope

In v1:

| Setup | Source | Destination |
| --- | --- | --- |
| This server to a local disk | local paths on the Borg UI host | local repository on the host |
| This server to another server | local paths on the host | SSH repository |
| Pull from another computer | remote paths over an SSH connection | local repository on the host, or an SSH repository |
| Another computer via agent (Pro) | paths on a managed agent | repository on a disk of that agent |

The agent row is fixed by the route planner (`routePreview.ts`,
`plan_repository_route`): an agent source can only back up to a repository
executed by the same agent.

Out of v1: rclone and cloud destinations, database and container sources,
multiple repositories per plan, Borg 2 as the default (Pro users can pick it
under Customize), scripts. Each has a full flow on its existing page.

## User flow

Steps adapt to the answers. The indicator only shows steps that apply.

1. **What**: "Files on this server" or "Files on another computer". For
   another computer, a second choice: "This server can SSH into it" (pull)
   or "Install the Borg UI agent on it" (Pro, `PlanGate` for Community).
   A "Not sure?" note explains the difference in two sentences.
2. **Connect** (another computer only)
   - SSH: pick an existing connection (`SshConnectionSelect`) or add one
     inline with host, user, port and a one-time password. The system SSH
     key is generated if it does not exist, then deployed with the password
     (`/ssh-keys/generate`, `/ssh-keys/{id}/deploy`). The password is not
     stored in the SSH connection record or key files.
   - Agent: pick a connected agent (`ManagedAgentSelect`) or open the
     existing `AddAgentDialog` to enroll one; the new agent is selected when
     it connects.
3. **Folders**: `PathSelectorField` browsing the chosen machine. At least
   one path.
4. **Where**: "A disk on this server" or "Another server over SSH" (for an
   agent source: "A disk on that computer", the only option). SSH reuses
   the connect sub-form from step 2. A path field with a sensible default
   (`/backups/<name>` style, editable, browsable). A warning when a local
   destination path sits inside a source path.
5. **Protect**: repository name (prefilled from the source), passphrase
   typed twice with a strength hint, "Download passphrase" (client-side
   text file) and a required "I have saved my passphrase" checkbox. The
   copy says plainly that a lost passphrase means lost backups.
6. **When**: presets Daily at 02:00 (default), Every 6 hours, Weekly
   (Sunday 02:00), or Custom via `SchedulePicker` (which also owns the
   timezone). "Manual only" is not offered here; Customize can turn the
   schedule off.
7. **Review**: a plain sentence summary of what will be created, a list of
   the objects ("SSH connection nas-01, repository Home backups, backup
   plan Home backups"), and a collapsed **Customize** section: encryption,
   compression, retention counts, prune/compact after each run, periodic
   check, schedule on/off, Borg version (Pro). Primary button: **Create
   backup**.

After Create the dialog switches to a progress view listing each action
with pending/running/done/failed. On failure it shows the backend error and
**Retry**, which resumes from the failed action and never recreates what
already exists. On success: **Run first backup now** (starts the plan) and
**Open backup plan**.

## Defaults

| Setting | Default | Why |
| --- | --- | --- |
| Encryption | `getDefaultRepositoryEncryption(1)` (repokey) | same as the repository wizard |
| Compression | `zstd,3` | better ratio than lz4 at similar speed for typical data |
| Retention | 7 daily, 4 weekly, 6 monthly, 1 yearly | existing plan defaults |
| After each backup | prune and compact on | keeps the repository bounded |
| Check | on, with the existing default max duration | catches corruption early |
| Schedule | enabled, daily 02:00, browser timezone | a backup nobody schedules is not a backup |
| Borg version | 1 | Borg 2 is Pro and still new |

## Architecture

Frontend only. No new backend endpoint and no migration.

- `frontend/src/components/quick-start/` holds the feature.
  - `quickStartState.ts`: the answer model, initial state, per-step
    validity, which steps apply.
  - `quickStartActions.ts`: a pure function from answers to an ordered list
    of actions (`generate_key`, `deploy_key`, `create_repository`,
    `create_plan`), and the payload builders. The plan payload goes through
    the existing `buildBackupPlanPayload` from `createInitialState()` with
    Quick Start overrides, so plan shape stays in one place.
  - `useQuickStartRunner.ts`: runs the actions in order with the existing
    API clients (`sshKeysAPI`, `BorgApiClient.createRepository`,
    `backupPlansAPI`). Results (key id, connection id, repository id, plan
    id) are kept so Retry resumes at the first action that has not
    finished.
  - `QuickStartDialog.tsx` plus one small component per step, rendered in
    the shared `WizardDialog`.
- Why not a backend `/quick-start` endpoint: SSH key deployment and
  repository init have remote side effects that a database transaction
  cannot roll back, so one endpoint would not be atomic anyway. It would
  duplicate the SSH, repository and plan logic and need its own Borg 1/2
  routing. The resumable runner gives the user a clear partial state
  instead, and every created object is valid on its own.
- Borg 1/2 routing stays in `BorgApiClient`; nothing in v1 files branches on
  version.

## Entry points

- A **New backup** button at the top of the sidebar navigation (visible to
  users who can create repositories, `repositories.manage_all`). Opens the dialog anywhere in the app.
- First run: when the user has `repositories.manage_all` and there are zero repositories
  and zero backup plans, the dialog opens once on the dashboard. Closing it
  records `borg-ui.quickStart.autoOpenDismissed` in localStorage so it does
  not reopen in that browser. Per browser is deliberate; it needs no
  migration and the sidebar button is always there.
- The Backup Plans and Repositories empty states get a **Quick start**
  action next to their existing create actions.

## Permissions and plans

- The dialog creates a repository, so it needs `repositories.manage_all`,
  the permission the Repositories page uses for its create button. The SSH connect sub-form needs SSH management permission;
  without it, only existing connections can be picked.
- Managed agents and Borg 2 are behind the existing feature gates
  (`managed_agents`, `borg_v2`). Community users see the agent option with
  `PlanGate`, not hidden.

## Error handling

- Deploy returns `success: false` with 200 on a bad password or refused
  connection; the runner treats that as a failed action and shows the
  message.
- Every API error goes through the existing `translateBackendKey` /
  `getApiErrorDetail` helpers.
- Closing the dialog mid-run is blocked while an action is in flight.
  Closing after a failure keeps the created objects; the progress view
  says which exist.

## Testing

- Unit: `quickStartActions` (every branch produces the right actions and
  payloads), `quickStartState` (step visibility and validity).
- Runner: resumes after a failure without repeating finished actions; treats
  deploy `success: false` as failure.
- Component: the dialog walks a local-to-local setup end to end with mocked
  APIs.
- Storybook: one story per step and the progress view (running, failed,
  done), light and dark.

## Docs

`docs/` user guide gets a Quick Start page and the navigation guidance
mentions the sidebar **New backup** button.
