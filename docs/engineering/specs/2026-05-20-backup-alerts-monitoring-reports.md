# Backup Alerts, Monitoring, and Reports Spec

## Context

BOR-43 extends the GitHub issue asking for server-side detection when repositories stop receiving new backups. Borg UI already has repository freshness signals on the dashboard and Apprise-backed notification services for backup, restore, check, restore-check, and schedule failures. The missing piece is an automated server-side loop that evaluates those freshness signals, alerts through the existing Apprise destinations, and sends configurable summary reports.

This is an unattended implementation, so the Linear ticket and linked GitHub issue are treated as the approval source for the design.

## Goals

- Detect stale repositories, including observe-only/imported repositories, using the persisted newest archive timestamp in `Repository.last_backup`.
- Let admins configure monitoring enablement, stale age, evaluation interval, alert cooldown, and observe-only inclusion from Settings.
- Send stale-backup alerts through existing Apprise notification services without adding a second provider model.
- Let admins configure periodic backup health reports by cadence and content sections.
- Let notification services opt in or out of stale alerts and reports alongside existing backup/check/restore event triggers.
- Add settings UI, tests, Storybook coverage, and snapshots for the new controls.

## Non-Goals

- Replacing external uptime monitoring or healthchecks. If Borg UI itself is down, it cannot send alerts.
- Per-repository monitoring thresholds. The first version is system-wide to match existing dashboard threshold settings.
- A full report templating engine. Reports use fixed, configurable sections.
- Adding email-specific settings outside Apprise.

## Backend Design

Add fields to `SystemSettings` for two related capabilities:

- Stale-backup monitoring:
  - `backup_monitoring_enabled`
  - `backup_monitoring_stale_after_days`
  - `backup_monitoring_interval_hours`
  - `backup_monitoring_alert_cooldown_hours`
  - `backup_monitoring_include_observe_repos`
  - `backup_monitoring_last_checked_at`
  - `backup_monitoring_last_alert_sent_at`
- Backup reports:
  - `backup_reports_enabled`
  - `backup_reports_frequency` (`daily`, `weekly`, `monthly`)
  - `backup_reports_hour_utc`
  - `backup_reports_weekday`
  - `backup_reports_monthday`
  - `backup_reports_include_summary`
  - `backup_reports_include_stale_repositories`
  - `backup_reports_include_recent_activity`
  - `backup_reports_last_sent_at`

Add notification-service trigger fields:

- `notify_on_stale_backup`
- `notify_on_backup_report`

Both default to enabled so existing Apprise services can receive these new system events once the system-level capability is enabled.

Create `app/services/backup_monitoring_service.py` as the boundary for:

- finding stale repositories from persisted repository freshness data,
- applying evaluation interval and alert cooldown gates,
- composing stale-backup alert bodies,
- deciding when a report cadence is due,
- composing report content from repository health and recent backup jobs,
- sending via new `NotificationService` methods.

Wire the service into the existing shared scheduler loop in `app/api/schedule.py` so it runs every scheduler tick but only performs work when the configured interval/cadence is due. Add manual admin endpoints under `/api/settings` for deterministic validation:

- `POST /api/settings/backup-monitoring/run`
- `POST /api/settings/backup-reports/send`

## Frontend Design

Add a system-managed Settings tab at `/settings/monitoring` named "Monitoring & Reports". It is visible to users with `settings.system.manage`.

The tab uses existing MUI settings patterns:

- contained page title and save button,
- compact full-outline cards/sections,
- controlled form inputs,
- switches for enablement and report content sections,
- numeric inputs for day/hour/cadence values,
- action buttons for "Run check now" and "Send report now",
- no heavy left accent borders.

Update the Notifications tab/card to expose the two new Apprise event toggles under a system/reporting category so admins can target alert/report destinations.

## Validation

Backend validation:

- Unit tests for stale repository selection, alert cooldown, report due calculation, and report dispatch.
- API tests for reading/updating new system settings and manual run/send endpoints.
- Existing policy checks: `ruff check app tests`, `ruff format --check app tests`.

Frontend validation:

- Settings tab test that edits monitoring/report controls and saves the expected payload.
- Notifications test coverage for new event fields.
- Storybook story for the Monitoring & Reports settings tab.
- `npm run check:locales`, `npm run typecheck`, `npm run lint`, `npm run build`, targeted Vitest tests, and `npm run snapshots`.

Runtime validation:

- Launch Borg UI locally, open Settings -> Monitoring & Reports, save monitoring/report settings, run a manual check/report, and record the outcome.
