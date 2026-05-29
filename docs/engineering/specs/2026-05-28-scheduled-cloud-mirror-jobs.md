# Scheduled Cloud Mirror Jobs Spec

## Problem

BOR-67 added optional rclone cloud mirrors for repositories and the UI already
offers a `scheduled` sync policy label. That policy is only a stored enum today:
there is no schedule cadence, next-run metadata, scheduler dispatch, or job log
record for cloud mirror syncs. Repository cards can show the last mirror sync
status, but they cannot show whether a scheduled mirror is configured, when it
will run next, or whether the last scheduled run failed.

## Desired Outcome

Users can configure a scheduled cloud mirror sync for a repository without
removing the manual mirror sync action. Borg UI records each scheduled mirror
attempt as a rclone sync job, advances next-run metadata after due schedules,
and surfaces scheduled mirror health in repository settings and cards. Failed
or missed runs remain observable and do not rewrite the repository's primary
metadata.

## Architecture

- Store mirror schedule configuration on the existing `RepositoryStorage`
  rclone row:
  - `sync_policy="scheduled"` activates scheduled dispatch.
  - `sync_cron_expression` stores the cron cadence.
  - `sync_timezone` stores the IANA timezone used for next-run calculation.
  - `last_scheduled_sync_at` and `next_scheduled_sync_at` store run metadata.
- Keep manual sync independent: `/api/repositories/{id}/rclone/sync` remains
  available for any mirrored repository even when `sync_policy` is `scheduled`.
- Record attempts in `RcloneSyncJob` with `triggered_by`, `scheduled_for`,
  `status`, timestamps, `error_text`, and `log_text`.
- Add `run_due_scheduled_rclone_mirrors(db, now)` to the existing minute-based
  scheduler loop after backup/check dispatch.
- Run scheduled mirrors through `RcloneRepositoryService.sync_repository` so
  local, SSHFS, and managed-agent mirror strategies keep a single execution
  path.
- On dispatch failure, advance `next_scheduled_sync_at`, set mirror
  `sync_status="failed"`, store `last_sync_error`, and mark the job failed. Do
  not mutate `Repository.path`, repository identity fields, or mirror target
  configuration.

## API Behavior

- Repository create, import, and update accept:
  - `rclone_sync_cron_expression`
  - `rclone_sync_timezone`
- If `rclone_sync_policy` is `scheduled`, a cron expression is required and
  `next_scheduled_sync_at` is calculated at save time.
- If `rclone_sync_policy` is not `scheduled`, `next_scheduled_sync_at` is null.
- Rclone status serialization includes schedule fields and the latest sync job
  summary.
- The existing manual sync endpoint records a manual `RcloneSyncJob` but does
  not alter scheduled next-run metadata.

## UI Behavior

- The existing Cloud Mirror wizard/settings step shows cron and timezone inputs
  only when the sync policy is Scheduled.
- Edit mode pre-populates the scheduled policy, cron, timezone, and next-run
  data from `repository.rclone_storage`.
- Repository cards show a compact scheduled mirror chip when a schedule is
  configured, including paused/missing-next-run/failure states.
- The rclone status chip still shows the mirror execution result; the schedule
  chip focuses on cadence and next run.
- Storybook covers repository card scheduled mirror states and the Cloud Mirror
  scheduled settings state.

## Acceptance Criteria

- Users can configure a scheduled cloud mirror sync policy independently of
  manual sync.
- Scheduler records job status, logs, and next-run information.
- Repository cards and settings show scheduled mirror state and failures.
- Missed and failed runs are observable and do not corrupt repository metadata.
- Tests cover schedule creation, execution, failure handling, and UI state.

## Validation

- Backend targeted tests cover schedule persistence, next-run calculation,
  manual sync independence, scheduled dispatch, failure handling, job logging,
  and metadata isolation.
- Frontend targeted tests cover scheduled Cloud Mirror settings and repository
  card state.
- Storybook snapshots cover the changed card/settings states.
- Required backend and frontend lint/build gates pass.
- Runtime walkthrough confirms scheduled mirror configuration and failure
  visibility from repository UI.

## Notes

The schedule belongs to the mirror row rather than the backup schedule table.
Backup schedules create Borg archives and may run prune/compact; cloud mirror
schedules only sync an existing repository to an rclone target.
