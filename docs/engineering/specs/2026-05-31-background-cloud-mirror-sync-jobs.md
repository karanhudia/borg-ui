# Background Cloud Mirror Sync Jobs Spec

## Problem

Repository edit mode currently blocks on the initial cloud mirror sync when the
mirror policy is `after_success`. The backend commits the repository storage
configuration and then awaits `rclone_repository_service.sync_repository(...)`
before returning the save response. A slow rclone transfer keeps the wizard in
the Saving state and can make the remote repository appear before the dialog
closes.

Cloud storage sync and hydrate work is also only partly observable. The rclone
sync job table exists for manual and scheduled sync attempts, but the Activity
view does not list those jobs and hydrate operations do not create a comparable
job row.

## Desired Outcome

Repository edits should persist cloud mirror configuration immediately. When
the default `after_success` policy requires an initial sync, Borg UI should
queue that work as a background rclone job after the configuration commit and
return the save response without awaiting transfer completion. Manual and
scheduled policies should continue to save without starting an immediate sync.

Cloud storage sync and hydration jobs should be visible in the same operational
surfaces users already use for backup and restore job progress: repository card
status, Activity, log viewing, and a progress-card-style summary for active
cloud storage jobs.

## Reproduction Signal

Before implementation, an AST scan of `app/api/repositories.py` confirmed that
`update_repository` directly awaits rclone sync:

```text
update_repository await sync_repository lines: [4348]
```

That line runs after `db.commit()` and only when
`sync_cloud_mirror_after_update` is set from `storage.sync_policy ==
"after_success"`.

## Architecture

- Reuse the existing `RcloneSyncJob` table as the durable job record for cloud
  storage operations.
- Add an `operation` discriminator to `RcloneSyncJob` so Activity can label
  `rclone_sync` and `rclone_hydrate` separately while preserving existing sync
  rows as `sync`.
- For repository update with `after_success`:
  - commit the repository and mirror settings first,
  - create a pending rclone sync job with `triggered_by="initial"`,
  - mark the mirror storage row pending,
  - schedule a background coroutine that opens a fresh database session and
    executes the pending job,
  - return the repository response without awaiting the rclone transfer.
- Keep manual and scheduled policies unchanged with respect to save behavior:
  no immediate initial sync is scheduled during the edit request.
- Let manual sync and scheduled sync continue to run through
  `RcloneRepositoryService.sync_repository` so local, SSHFS, and managed-agent
  mirror strategies share one execution path.
- Record hydrate operations as `RcloneSyncJob(operation="hydrate")` rows so the
  Activity surface can show cloud storage hydration alongside sync jobs.
- Extend the Activity API to list, fetch logs for, download logs for, and delete
  rclone sync/hydrate jobs using existing Activity job endpoints.
- Extend the frontend Activity page with active cloud storage job progress cards
  and rclone job filters while keeping the existing `BackupJobsTable` and
  shared log viewer pattern.

## UI Direction

The Activity additions should follow Borg UI's dense operational dashboard
style: compact status surfaces, balanced borders, icons, chips, and readable
job metadata. Do not add heavy left accent borders. The new card should be a
top-level active-job summary above the Activity table, not a decorative nested
card.

## Acceptance Criteria

- Repository edit save persists `cloud_mirror_enabled`, `rclone_remote_id`,
  `rclone_remote_path`, and `rclone_sync_policy` without awaiting the rclone
  transfer.
- For `after_success`, the initial sync is queued as a background rclone job
  after the configuration commit succeeds.
- For `manual` and `scheduled`, saving repository edits does not queue or run an
  immediate initial sync.
- Cloud storage sync and hydration jobs appear in Activity with status, trigger,
  repository context, timestamps, errors, and logs where available.
- Active cloud storage jobs are summarized with the same progress-card-style
  used for other running work.
- Repository cards continue to reflect pending, syncing, completed, failed, and
  hydrate-related cloud mirror status.
- Existing scheduled rclone mirror behavior remains compatible.

## Validation

- Backend tests prove repository update schedules background work for
  `after_success` without awaiting `sync_repository`.
- Backend tests prove `manual` and `scheduled` policies do not queue initial
  sync work during repository update.
- Backend tests prove rclone sync and hydrate jobs appear in Activity and expose
  logs through Activity endpoints.
- Frontend tests or stories cover rclone Activity filters, active cloud storage
  progress cards, and log-viewer labels.
- Storybook snapshots cover the changed UI state.
- Required backend and frontend lint, type, build, and targeted test gates pass.
- Runtime walkthrough verifies: enable cloud mirror in repository edit mode,
  save returns promptly, dialog closes, and cloud sync progress/activity appears
  after close.

## Out Of Scope

- A new standalone rclone job viewer route separate from Activity.
- Changing scheduled mirror cadence behavior.
- Changing manual sync endpoint semantics beyond making job records visible in
  Activity.
