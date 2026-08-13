# Availability-Based Backup Scheduling Implementation Plan

> **For agentic workers:** Use `superpowers:test-driven-development` for each
> implementation task and `superpowers:verification-before-completion` before
> claiming completion, committing, or pushing.

**Goal:** Let Backup Plans and Backup Automations run at a fixed cron time or
when their source is available, with a minimum time between successful backups.

**Architecture:** Persist one explicit trigger mode and its mode-specific
settings on both scheduling models. A shared availability dispatcher evaluates
source/target readiness and the last successful run before atomically creating
a normal execution run. It records non-dispatches as neutral skipped history
events. Existing fixed-time code paths remain the default and unchanged.

**Tech Stack:** FastAPI, SQLAlchemy, asyncio scheduler, pytest, React, MUI,
Vitest, Storybook.

---

## Files to Inspect and Modify

- `app/database/models.py`
- `app/database/alembic/versions/a3d1e7b4c9f2_add_availability_schedule_modes.py`
- `app/api/backup_plans.py`
- `app/api/schedule.py`
- `app/services/backup_plan_execution_service.py`
- `app/services/availability_schedule_service.py` (new)
- scheduler startup/tick code that currently dispatches scheduled jobs
- backup notification/monitoring service(s)
- schedule and backup-plan API, execution, and scheduler tests
- `frontend/src/components/ScheduleWizard.tsx` (rename incrementally only if
  low-risk; user-visible name changes are required)
- `frontend/src/components/shared/SchedulePicker.tsx` and its stories/tests
- Backup Plan wizard schedule/review components and stories/tests
- `frontend/src/pages/Schedule.tsx`, `ScheduleByPlanTab.tsx`, translations, and
  schedule-page tests
- relevant user navigation documentation

## Task 1: Map current contracts and write failing backend tests

- [ ] Identify the exact scheduled-job dispatch loop, plan dispatch loop,
  active-run locking, current history records, and notification decision points.
- [ ] Add failing migration/model tests for trigger fields on `BackupPlan` and
  `ScheduledJob`, `skip_reason` on plan runs, and durable automation run
  history.
- [ ] Add API tests for both resources: cron remains valid/default; availability
  requires positive bounded polling and minimum intervals; incompatible fields
  are rejected; responses round-trip the selected mode.
- [ ] Add resolver tests for local, healthy/unhealthy managed-agent, reachable/
  unreachable SSH, elapsed/not-elapsed intervals, active run, and target
  readiness.
- [ ] Add concurrency tests proving two scheduler workers/ticks cannot claim
  two availability runs for the same entity.
- [ ] Add history/notification tests proving each non-dispatch reason is
  `skipped`, not failure-notified, and does not update successful-run state.

## Task 2: Persist and validate trigger settings

- [ ] Add nullable `schedule_trigger`, `availability_check_interval_minutes`,
  and `minimum_success_interval_minutes` columns to `backup_plans` and
  `scheduled_jobs` through the Alembic availability-schedule revision. Backfill trigger to
  `cron`.
- [ ] Add `ScheduledJobRun` with entity ID, trigger, status, skip reason,
  timestamps, detail/error message, and indexes for latest state/history.
- [ ] Add nullable `skip_reason` to `BackupPlanRun`; use existing status values
  where possible.
- [ ] Implement a single validation/normalization helper shared by plan and
  automation APIs. It must enforce the mode-specific contract and preserve
  legacy cron behavior.
- [ ] Serialize trigger configuration, last successful run, next poll, and run
  history data without removing existing response fields.

## Task 3: Implement safe dispatch and history

- [ ] Implement `availability_schedule_service` with an injectable clock and
  source readiness adapters. Use agent presence for managed-agent sources and a
  lightweight SSH/TCP probe for SSH sources.
- [ ] Add a common decision result type: dispatch or a named neutral skip
  reason. Do not run hooks or Borg during probing.
- [ ] Implement database-backed claim/check logic that rechecks enabled state,
  active run, target readiness, and latest *successful* run in one transaction.
- [ ] Wire availability ticks into the existing scheduler. Poll only when an
  item's interval is due, set meaningful next-poll metadata, and retain cron
  calculation exclusively for cron mode.
- [ ] Route claimed Backup Plans through `BackupPlanExecutionService`; route
  claimed Backup Automations through their existing execution path.
- [ ] Persist skipped decisions in plan and automation histories. Wire skip
  suppression into alerting/monitoring and retain normal alerts for actual
  attempted-run failures.
- [ ] Require all enabled target repositories to pass lightweight pre-dispatch
  validation before a multi-repository automation is claimed; record one
  target-specific skipped event rather than a partial run.

## Task 4: Add frontend trigger controls and terminology

- [ ] Extend shared `SchedulePicker` (and supporting schedule types) with a
  composed Run trigger control. Reuse `CronExpressionInput`,
  `CronBuilderDialog`, and the `SchedulePicker` timezone selector for cron
  mode; do not introduce ad hoc cron/timezone fields.
- [ ] Add availability-mode fields for poll interval and minimum success
  interval, including validation and detected source-signal explanation.
- [ ] Integrate the shared control into both Backup Plan and Backup Automation
  wizards, payload hydration, edit flows, and review summaries.
- [ ] Rename user-visible standalone scheduling language from Legacy Backup
  Schedules/Create legacy schedule to Backup automations/Create backup
  automation. Keep route/API/model compatibility and avoid broad risky internal
  renames unless covered by tests.
- [ ] Update run history/activity UI to render neutral skipped state and a clear
  source-unavailable, target-unavailable, minimum-interval, or active-run
  reason.
- [ ] Add localized strings and update relevant user navigation docs.
- [ ] Add/update Storybook stories for cron and availability triggers in both
  workflows, plus skipped-history display.

## Task 5: Verification

- [ ] Run targeted backend tests for migration, APIs, dispatch decisions,
  concurrency, histories, and notifications.
- [ ] Run `ruff check app tests` and `ruff format --check app tests`.
- [ ] Run `cd frontend && npm run check:locales`, `npm run typecheck`, `npm run
  lint`, and focused Vitest tests.
- [ ] Run or update Storybook tests and capture local visual proof with `cd
  frontend && npm run snapshots`; do not commit generated snapshots.
- [ ] Manually verify each workflow: cron behavior stays unchanged; an offline
  SSH source creates a neutral skip; a reachable source runs after its interval;
  a second near-boundary poll is held; failed runs do not reset the interval;
  multi-target readiness blocks partial availability runs.

## Rollout and Compatibility Checks

- [ ] Verify migration against SQLite and supported production databases, and
  ensure existing schedule rows become `cron` without a change in `next_run`.
- [ ] Verify borgmatic import/export and repository-to-plan conversion retain
  cron behavior; availability settings must not be silently represented as a
  cron expression.
- [ ] Verify dashboards/counts that distinguish plans from scheduled jobs now
  use Backup automation wording without altering their numerical semantics.
- [ ] Confirm all availability skip reasons are observable in history/logging
  and absent from failure-notification paths.
