# Job System

Borg UI runs long operations as background jobs. Jobs keep the UI responsive while Borg commands run inside the container.

## Job Lifecycle

Most jobs follow the same lifecycle:

```text
pending -> running -> completed
pending -> running -> failed
pending -> running -> cancelled
```

Job records store status, timestamps, progress, errors, and log file references.

## Main Job Types

| Job type | Purpose |
| --- | --- |
| Backup | Run Borg create for a repository |
| Restore | Extract files from an archive |
| Check | Verify repository/archive integrity |
| Compact | Free unused repository space |
| Prune | Apply retention policy |
| Archive delete | Delete an archive |
| Restore check | Verify that selected paths can be restored |

Schedules are configuration records. When a schedule fires, it creates backup/check/restore-check jobs.

## Backup Jobs

Backup jobs can be started manually or by schedule.

Typical flow:

1. create job record
2. run pre-backup scripts
3. run Borg backup
4. update progress and logs
5. run configured prune/compact work
6. run post-backup scripts
7. send notifications
8. update final status

## Restore Jobs

Restore jobs extract archive contents to a destination path visible inside the container.

Restores can target:

- local mounted paths
- remote destinations supported by the restore flow

Notifications can be sent for restore success or failure.

## Check, Prune, and Compact

Maintenance jobs run Borg maintenance commands and record job history.

Use them carefully:

- checks can be expensive on large repositories
- prune changes retention state
- compact reclaims space after prune

Do not interrupt maintenance unless necessary.

## Logs

Job logs are written to disk and referenced from the database.

System settings control:

- log retention days
- log save policy
- total log size cap
- cleanup on startup

## Restart Cleanup

On application startup, Borg UI checks for jobs that were left in `running` states by a container restart or crash.

Startup cleanup currently covers:

- backup jobs
- restore jobs
- check jobs
- restore-check jobs
- prune jobs
- compact jobs

What happens:

- running backup jobs are marked `failed`
- running restore jobs are marked `failed`
- running prune jobs are marked `failed`
- running check, restore-check, and compact jobs are marked `failed` when their recorded process is no longer alive
- backup rows left in `running_prune` or `running_compact` maintenance states are marked `failed`, with maintenance state changed to `prune_failed` or `compact_failed`
- orphaned prune and compact jobs update the related backup maintenance state when possible

For local check and compact jobs, Borg UI attempts to break the repository lock after detecting an orphaned process. For remote repositories, it does not automatically break the lock because the remote Borg process may still be running.

Archive-delete and package-install jobs are not part of this startup orphan-job cleanup path.

## Stale Scheduled Checks

Scheduled check jobs have an additional stale-job cleanup in the scheduled-check dispatcher.

The dispatcher marks these scheduled checks as `failed`:

- `pending` scheduled checks older than 15 minutes
- `running` scheduled checks older than 15 minutes when the recorded process is no longer alive

This prevents stale scheduled checks from permanently consuming scheduled-check concurrency slots.

## Deleting Job Entries

Admins can delete job history entries from the activity/job views.

The delete endpoint supports these job types:

- backup
- restore
- check
- restore check
- compact
- prune
- package install

Deleting a job entry removes the database row and tries to delete the associated log file when the job has a `log_file_path`.

It does not delete Borg repositories, backup archives, or restored files. Archive deletion is a separate archive operation.

Running jobs cannot be deleted. Pending jobs can be deleted, which is useful for cleaning up stuck pending rows.

## Concurrency

System settings control concurrent work:

- max concurrent manual backups
- max concurrent scheduled backups
- max concurrent scheduled checks

Avoid running multiple write operations against the same repository at the same time.

## Operations runner

Derived-data work (repository stats, archive listing, and in later phases
history indexing) runs through a single in-process runner backed by the
`operations` table. Each row has a kind, a category, a trigger, a priority,
and an optional dependency on another row. Rows that share a `run_id` form
a run, for example an import followed by its stats and archive listing.

Rules:

- One exclusive operation per repository at a time (the repository lane).
  While a backup, check, prune, compact, wipe, or archive delete is running,
  exclusive operations wait. Index operations wait too unless
  `bypass_lock_on_list` or the repository's bypass setting allows them to
  run alongside.
- Lower priority number runs first: manual and plan work at 0, scheduled at
  5, follow-ups at 10, reconcile at 20.
- A failed, cancelled, or skipped operation skips everything that depends on
  it with `skip_reason = dependency_failed`.
- Follow-ups are created automatically when an operation succeeds. An
  import enqueues stats and archive listing.
- The reconcile scheduler replaces the old stats refresh loop. Every
  `stats_refresh_interval_minutes` it enqueues an index run for each
  repository that has none queued or running. `0` disables it.
- On startup, running index operations are requeued; other running
  operations are marked failed unless their recorded process is still
  alive.
- Operations write their logs to files under `data/logs/`. Retention deletes
  those files at `log_retention_days` and again with the row itself at
  `cleanup_retention_days`.
- A failed listing is never written as derived state: if borg or the agent
  fails, `archive_sync` fails rather than recording the repository as empty.
- Cancelling a running operation is cooperative: the executor observes the
  request through `ctx.cancelled()` and stops at its next check. Cancelling
  a queued operation is immediate.

The `/api/operations` routes expose the list, a live queue view, cancel,
pause and resume of background triggers, and the `index_workers` limit.
Activity includes operations rows; index-category rows are hidden unless
the Index category filter is on.

## Notifications

Job-related notifications are handled by the notification service.

Current notification event groups include:

- backup start/success/warning/failure
- restore success/failure
- check success/failure
- schedule failure

See [Notifications](../notifications).
