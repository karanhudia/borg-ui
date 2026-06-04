# Backup Report Period Windows Spec

## Context

BOR-49 links GitHub issue #294, which asks for periodic backup reports that act as a vital sign when users only notify on backup failures. The broad feature already exists on `origin/main`: admins can configure backup monitoring and reports, send reports manually, schedule them through the shared scheduler, and route them through Apprise notification services.

The remaining gap is report period accuracy. `build_backup_report()` currently includes backup activity from the last seven days regardless of whether the report cadence is daily, weekly, or monthly. GitHub issue #294 specifically describes reports for the last configured period, so daily and monthly reports should not use a fixed weekly activity window.

## Goals

- Keep the existing Settings UI, scheduler integration, manual send endpoint, and Apprise routing.
- Make recent backup activity use a period derived from `backup_reports_frequency`.
- Include the activity period in the report body so recipients can tell what interval the report covers.
- Make report delivery scheduling match the existing schedule UI pattern: cron expression plus explicit IANA timezone, with the cron builder available from the reports settings.
- Add focused regression tests for the period window behavior.

## Non-Goals

- Add report templates or HTML formatting.
- Add per-notification-service report cadence.
- Replace external uptime monitoring for Borg UI process failure.

## Design

Add a small helper in `app/services/backup_monitoring_service.py` that derives the activity period start from the configured report frequency:

- `daily`: one day before the report timestamp.
- `weekly`: seven days before the report timestamp.
- `monthly`: one calendar month before the report timestamp, clamping the day when the previous month is shorter.

`build_backup_report()` will query `BackupJob.started_at >= period_start` instead of the current fixed seven-day cutoff. The "Recent backup activity" heading will include serialized start and end timestamps. This keeps the generated report plain text and Apprise-provider neutral.

For report delivery scheduling, add `backup_reports_cron_expression` and `backup_reports_timezone` settings. The backend will evaluate the latest due report window with the same timezone helpers used by recurring schedules. New report settings should default to the container timezone from `TZ`, `/etc/timezone`, or `/etc/localtime`, falling back to UTC only when no valid IANA timezone is available. The existing `backup_reports_frequency` field remains as report content cadence, not as the delivery scheduler. The Monitoring & Reports tab will replace the separate frequency/hour UTC/week/month controls with a clearer "Report cadence" selector plus the shared `SchedulePicker` cron/timezone control.

## Validation

- Add a unit test proving daily reports exclude backup jobs older than one day while including recent jobs.
- Add a unit test proving monthly reports include jobs within the previous monthly period and exclude older jobs.
- Add API and service tests proving report cron/timezone settings are persisted, validated, and used to determine when reports are due.
- Add frontend test and Storybook snapshot coverage for the shared schedule picker in the report settings.
- Run the focused monitoring service unit tests.
- Run backend lint and format checks for `app` and `tests`.
- Run frontend locale, typecheck, lint, build, focused Vitest, and Storybook snapshot validation for the UI change.
- Exercise report generation through a runtime or API-level proof before handoff.
