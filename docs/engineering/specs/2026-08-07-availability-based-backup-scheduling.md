# Availability-Based Backup Scheduling Spec

## Problem

Fixed cron times work for always-on machines, but a client that is sleeping or
offline at its scheduled time creates a misleading failed backup and misses its
backup window. Increasing cron frequency is not a safe workaround: it creates
duplicate archives and can run again immediately across a day boundary.

Issue [#714](https://github.com/karanhudia/borg-ui/issues/714) requests an
unattended, availability-gated backup that runs at the first safe opportunity.

## Desired Outcome

Both Backup Plans and standalone Backup Automations can be triggered either at
a fixed time or when their source becomes available. Availability-triggered
items are checked at a configured cadence and start one run only when the
source is reachable and the configured minimum interval since the last
successful run has elapsed.

The existing user-facing term **Legacy Backup Schedules** is replaced with
**Backup automations**. This is a terminology and presentation change, not an
API or database identity change: existing `ScheduledJob` records, endpoints,
URLs, and imported borgmatic schedules remain compatible.

## Scope

- Add a shared trigger model to `BackupPlan` and `ScheduledJob` (the backing
  model for Backup Automations).
- Keep the existing fixed-time cron behavior as the default for all existing
  records.
- Add availability checks for managed-agent and SSH sources.
- Add a configurable polling cadence and minimum-success interval.
- Record a neutral, explainable skipped event whenever an availability polling
  decision does not dispatch a backup.
- Suppress failure notifications for those intentional skips.
- Rename UI copy, navigation, help, accessibility labels, and documentation
  from legacy schedules/backups to Backup automations where the reference means
  a `ScheduledJob` workflow.

## Non-Goals

- Altering manual **Run now** behavior. A manual run bypasses the availability
  trigger and minimum-success interval, while retaining normal execution
  validation.
- Replacing cron syntax or changing the behavior of existing fixed-time jobs.
- Per-repository independent availability triggers in one multi-repository
  automation. That can be considered later as an explicit partial-run feature.
- Treating a failed backup, cancelled backup, or a warning-complete backup as a
  successful interval reset.

## Trigger Model

Each scheduled entity has these settings:

| Field | Fixed time | When available |
| --- | --- | --- |
| `schedule_trigger` | `cron` (default) | `availability` |
| `cron_expression` | required | `NULL` |
| `timezone` | required, current behavior | retained for display/API consistency; not used to evaluate elapsed intervals |
| `availability_check_interval_minutes` | `NULL` | required positive bounded integer |
| `minimum_success_interval_minutes` | `NULL` | required positive bounded integer |

The initial bounds are 5 minutes through 7 days for the poll interval and 1
hour through 30 days for the minimum interval. Defaults for a newly selected
availability trigger are 30 minutes and 20 hours. These are product defaults,
not an implicit migration of existing cron schedules.

Elapsed time is calculated from UTC timestamps, never local clock dates. A
successful run at 23:55 therefore cannot be followed by an availability run at
00:05 unless the full configured interval has elapsed.

## Availability Semantics

At each due availability poll, in one decision transaction:

1. Re-read the enabled item and ensure it has no active run.
2. Resolve the source's availability signal.
   - A managed-agent source is available only when its current connected/presence
     state is healthy.
   - An SSH source is available only when the lightweight existing SSH/TCP
     reachability probe succeeds. The probe must not execute backup hooks,
     unlock repositories, or start Borg.
   - A local source is always available; its mode remains useful as an
     interval-gated automatic backup.
3. Require all enabled target repositories in a multi-repository item to pass
   the existing lightweight pre-dispatch availability/credential validation.
   This **all targets** policy prevents silently turning one configured backup
   into a partial success. A failed target check produces one skipped item-wide
   event that identifies the target; it does not run the other targets.
4. Find the entity's latest completed `success` run. If `now - successful_at`
   is less than the configured minimum interval, do not dispatch.
5. Atomically claim a run only after all gates pass, then use the current normal
   execution path. Concurrent scheduler ticks or web workers must not create
   duplicate runs.

Availability does not guarantee that a subsequent Borg invocation will succeed.
Once a run has been claimed, ordinary connection, Borg, hook, repository, and
notification failure behavior remains unchanged.

## Skips, History, and Notifications

Every availability poll that does not dispatch creates an event with status
`skipped`, a machine-readable reason, timestamp, and human-readable detail.
Initial reason values are:

- `source_unavailable`
- `target_unavailable`
- `minimum_interval_not_elapsed`
- `run_already_active`
- `disabled_or_reconfigured` (only when a claimed poll becomes invalid before
  dispatch; normally not shown as a user-visible issue)

Backup Plan skips use `BackupPlanRun` records with an availability-specific
trigger and `skip_reason`. Backup Automation skips use durable
`AvailabilityScheduleSkip` records rather than relying only on logs, so their
history is equally inspectable. Existing `last_run` remains supported for
compatibility and display.

Skipped records are neutral: they do not increment failed-backup counters,
produce failure alerts, invoke failure notification channels, or reset the
minimum-success interval. They are visible in run history and activity with a
"Skipped" state and reason. A future notification preference may opt in to
availability summaries, but none is sent initially.

## API and Persistence Contract

`POST`/`PUT` Backup Plan and Backup Automation payloads accept and return the
trigger fields above. Validation requires exactly the fields appropriate to the
selected trigger; it rejects cron in availability mode and availability fields
in cron mode rather than retaining ambiguous hidden configuration.

The Alembic availability-schedule revision adds trigger fields to `backup_plans` and
`scheduled_jobs`, plus an indexed `availability_schedule_skips` table and
`skip_reason` on `backup_plan_runs`. Existing rows receive `schedule_mode = 'cron'`
and retain their existing cron expression, timezone, next run, and behavior.

All API route names and persisted `ScheduledJob` identifiers remain unchanged.
Responses may add `trigger_display`/next-poll metadata for presentation but
must retain current schedule response fields until a separately versioned API
cleanup.

## UI and Content

The Schedule controls in both the Backup Plan wizard and Backup Automation
wizard use the shared `SchedulePicker` family. Add a **Run trigger** choice:

- **At a fixed time** shows the existing cron expression builder and timezone
  selector.
- **When source is available** hides cron controls and shows check interval,
  minimum interval after a successful run, and a read-only explanation of the
  detected availability signal (managed agent connected, SSH reachable, or
  local source).

Review screens summarize the chosen trigger. The Schedule page calls the
standalone section **Backup automations** and uses "Create backup automation",
"Edit backup automation", and "Run backup automation". Internal component and
type renames may be incremental, but user-visible legacy terminology should be
removed in this feature. Existing routes and stored data are not renamed.

Changed components require Storybook stories covering cron and availability
states, including an unavailable/interval-held history example. Navigation
guidance in user documentation must use Backup automations.

## Acceptance Criteria

- A user can configure either trigger type on a Backup Plan and a Backup
  Automation.
- Existing cron records run unchanged after migration.
- An availability-triggered SSH or managed-agent backup runs on the first
  successful poll after its minimum interval expires.
- A polling decision that cannot run is persisted as a neutral skipped event
  with a specific reason and sends no failure notification.
- No two availability polls can start duplicate runs for the same item.
- A multi-repository item does not silently run only a subset of its configured
  enabled targets.
- UI and user documentation say Backup automations, not Legacy Backup
  Schedules, for standalone scheduled jobs.
