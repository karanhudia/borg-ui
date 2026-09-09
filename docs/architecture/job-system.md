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
| Repository wipe | Delete every archive in a repository |
| Cloud mirror sync | Copy a repository to (or from) an rclone remote |
| Package install | Install an OS package on the server |

Schedules are configuration records. When a schedule fires, it creates backup/check/restore-check jobs.

Repository wipe, cloud mirror sync and hydrate, and package install are
`operations` rows too (kinds `wipe`, `rclone_sync`, `package_install`).
`repository_wipe_jobs`, `rclone_sync_jobs`, and `package_install_jobs` are
legacy tables now: they hold history written before the migration and nothing
writes new rows to them, with one exception. A wipe preview is not a unit of
work, so it is still written to `repository_wipe_jobs`; only the confirmed
wipe becomes an operation, and it names the preview it was confirmed from in
`params.preview_id`. A job id resolves against `operations` first and falls
back to its legacy table, so old links keep working.

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

As of section 13 phase 7 of the operations spec, a restore is a row in the
`operations` table (kind `restore`, category `restore`) with its restore
columns on `operation_restore_details`: archive, destination, destination
type and SSH connection, repository type, and the live byte and file counts.
`POST /api/restore/start` enqueues the row; the operations runner dispatches
it. Restore is not exclusive (Borg allows concurrent reads), so it runs
beside a backup or check on the same repository rather than waiting for the
lane, exactly as it did before the migration.

The restore service keeps its three execution paths and drives the row
through a facade that presents the legacy attribute surface:

- local destination: `borg extract` in the container, progress parsed from
  `--log-json`
- SSH destination: the destination is mounted over SSHFS and extracted into
  directly
- managed-agent repository: a `repository.restore` agent job is queued and
  its progress mirrored onto the operation

Cancelling a running restore (`POST /api/restore/cancel/{id}`) raises the
runner's cancel flag, terminates the extract process (or asks the agent to
cancel), and marks the row `cancelled`; the executor keeps that verdict even
when the service records the killed process's exit afterwards.

Restore logs are the operation's log file, written once at the end from the
captured output. Rows written before phase 7 stay in `restore_jobs` and are
served by the same routes until retention drops them; the table is deleted
in phase 9.

Notifications can be sent for restore success or failure.

## Check, Prune, Compact, Archive Delete, and Restore Check

These five kinds are rows in the `operations` table (see "Operations
runner" below), not per-kind tables. Check, prune, compact, and archive
delete are exclusive: they take the repository lane, so they queue behind a
running backup instead of being rejected outright, and the runner starts
them when the lane is free. Restore check is category `restore`: it only
reads, so it does not take the lane and keeps its own cron scheduler.

Prune's dry run and every post-backup prune/compact/check are the
exceptions: they run inline (`start_inline_maintenance` /
`finish_inline_maintenance`), because a queued child would deadlock
against the backup row holding the lane in `running_prune`. An inline
operation still gets a real row and the same follow-up chain a
runner-dispatched one would get, just without the runner's queueing.

Use them carefully:

- checks can be expensive on large repositories
- prune changes retention state
- compact reclaims space after prune
- archive delete requires a per-archive lock: two different archives may be
  removed at once, the same one may not

Do not interrupt maintenance unless necessary.

Pre-phase-5 installs still have history in `check_jobs`, `prune_jobs`,
`compact_jobs`, `delete_archive_jobs`, and `restore_check_jobs`. The status
and list routes serve operations first and fall back to those tables by id,
so old links and activity rows keep resolving. The tables themselves are
deleted in a later phase.

## Logs

Job logs are written to disk and referenced from the database.

System settings control:

- log retention days
- log save policy
- total log size cap
- cleanup on startup

## Repository Wipe, Cloud Mirror Sync, and Package Install

**Repository wipe** is exclusive, so a confirmed wipe queues behind whatever
holds the repository lane instead of being rejected with a 409. The preview
stays in `repository_wipe_jobs`: it is not a unit of work, it holds no lock,
and it blocks nothing. Confirming the preview creates the `wipe` operation and
copies the preview snapshot (fingerprint, manifest, dry-run output, protected
archives) into `operation_wipe_details`; a preview is spent once an
operation's `params.preview_id` names it. Two wipe statuses the UI shows,
`completed_compaction_failed` and `failed_partial`, are not operation
statuses: they are stored as `completed_with_warnings` and `failed` and
reconstructed from the details row's `phase`.

**Cloud mirror sync** is one kind, `rclone_sync`, for both the mirror sync and
the cache hydrate; `operation_rclone_details.operation` says which. It does not
take the repository lane. It serialises on the `rclone` lock scope instead, as
it always has, and the executor is what takes that lock now, so the mirror
scheduler gets it too (it did not before). The scheduler and the initial sync
queued when a cloud repository is created both only enqueue; the runner starts
them. The scheduler skips a repository whose scheduled run is still queued or
running and leaves the slot due, so a sync that outlasts its interval is
followed by one run, not a backlog. The legacy `triggered_by` word `initial`
is stored as the trigger `import` and mapped back on read.

**Package install** has no repository and no lane. Its `package_id` lives in
`operations.params`, its exit code in `operations.result`, and its captured
output in the operation's log file. That file opens with one header line
giving the length of each stream, so the split never depends on what apt
printed, and `GET /api/packages/jobs/{id}` still returns `stdout` and `stderr`
apart.

## Restart Cleanup

On application startup, Borg UI checks for jobs that were left in `running` states by a container restart or crash.

Startup cleanup currently covers:

- backup jobs
- restore rows in their legacy table, written by an install that has not
  restarted since upgrading to phase 7
- check, restore-check, prune, and compact rows in their legacy tables,
  written by an install that has not restarted since upgrading to phase 5

Check, prune, compact, restore-check, and restore now run as operations, and new
work in that shape is recovered by the operations runner on startup
(requeue index rows, fail the rest unless their process is still alive; see
"Operations runner"), including a local lock-break attempt equivalent to
the one this sweep makes. The five legacy-table branches below stay only to
resolve a running row a pre-upgrade process left behind; each query is
empty on any install that has restarted since the upgrade, and the branches
are deleted with the tables in a later phase.

What happens:

- running backup jobs are marked `failed`
- running legacy restore rows are marked `failed`
- running legacy prune rows are marked `failed`
- running legacy check, restore-check, and compact rows are marked `failed` when their recorded process is no longer alive
- backup rows left in `running_prune` or `running_compact` maintenance states are marked `failed`, with maintenance state changed to `prune_failed` or `compact_failed`
- orphaned legacy prune and compact rows update the related backup maintenance state when possible

For local check and compact jobs, Borg UI attempts to break the repository lock after detecting an orphaned process. For remote repositories, it does not automatically break the lock because the remote Borg process may still be running.

Archive-delete and package-install jobs are not part of this startup orphan-job
cleanup path.

One mirror case is handled before recovery runs: an initial cloud mirror sync
(trigger `import`) left `running` by a restart is put back to `queued` rather
than failed. Recovery would fail it, which is right for a Borg command holding
a lock and wrong for `rclone sync`, which is itself a reconciliation and safe
to re-run. The requeue happens earlier in startup than
`OperationRunner.recover_on_startup`, so recovery sees a queued row and leaves
it alone.

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
- A failed or cancelled operation skips everything that depends on it with
  `skip_reason = dependency_failed`, including every subsequent dependant
  of that skip. An intentional skip means the stage had nothing to do, so
  dependants (`stats` after an unsupported `history_index`) still run.
- An operation the repository admission refuses (409, another job holds
  the repository) goes back to the queue instead of failing, with
  `params.deferrals` counting the attempts and `params.deferred_until`
  holding the next attempt's not-before time as epoch seconds (5 s,
  doubling to 5 min).
  After 20 deferrals it fails with "repository still busy".
- Follow-ups are created automatically when an operation succeeds. An
  import enqueues stats and archive listing. A backup that completes through
  the legacy backup paths (server or agent) enqueues the `backup` chain the
  same way, so the archive index and `last_backup` follow within a runner
  tick instead of waiting for the next reconcile run. Only a queued
  `archive_sync` with no dependency or an already satisfied dependency
  suppresses a duplicate listing. `history_merge` follows the listing on
  every plan so removed archives leave the database as well.
- `stats` measures the repository read-only through the best source Borg
  offers and records it in `repositories.total_size_source`: Borg 1
  `cache.stats.unique_csize` (`borg1_cache_stats`, deduplicated); Borg 2 the
  chunk-index sum through Borg's Python API next to the configured binary
  (`borg2_index`, the bytes of every indexed object), else a store-level
  measurement per URL scheme (`storage_used`, file bytes including index and
  pack headers: rclone for `sftp://` and `rclone:` paths with the prepared
  environment, du for local
  paths and `ssh://`, a REST listing for http; none for `rest://user@host`,
  whose key is bound to the REST server). The labels name different
  quantities: `compact --stats` counts pack file bytes, which include data
  no index entry covers, so it and `borg2_index` agree only on a fully
  indexed repository. Agent repositories get the same order from the
  agent's `repository.storage_usage` job (agents from 0.1.4; older agents
  keep `repository.disk_usage`, which only measures local paths). The
  agent measures local paths with du but has no `ssh://` du path; that
  one exists on the server only, where the SSH key is at hand. An
  unknown size leaves the stored value alone, never `0`. Both versions'
  `repository.last_modified` (the last manifest
  write) lands in `repositories.borg_last_modified`.
- The repository status (`GET /repositories/{id}/status`, also served as
  `/status-strip`) reads repository evidence first: backup is the newest
  archive, whatever created it, unless a failed or cancelled Borg UI
  attempt is newer, and with no archives at all the newest job row; prune
  is the newest successful `archive_sync` that reported removed archives
  unless a prune run through Borg UI is newer; check and compact keep
  their job rows. Overdue is judged per series against its own cadence (the
  repository is overdue when one series is), against the check schedule
  or a scheduled plan that checks after backups, and against the plans or
  scheduled jobs that run prune or compact (a plan counts only when
  enabled, scheduled, dispatchable and linked through an enabled
  association); it is
  null where nothing is expected. Details and the `source` field: spec
  section 10.2.
- The reconcile scheduler replaces the old stats refresh loop. Every
  `stats_refresh_interval_minutes` it enqueues an index run for each
  repository that has none queued or running. `0` disables it.
- On startup, running index operations are requeued; other running
  operations are marked failed unless their recorded process is still
  alive.
- Operations write their logs to files under `data/logs/`. Retention deletes
  those files at `log_retention_days` and again with the row itself at
  `cleanup_retention_days`.
- A backup job outlives its archive. When a prune or an archive deletion
  removes the archive a job created, the job row is marked
  (`archive_pruned_at`) and kept as the record that the backup ran; it falls
  with `cleanup_retention_days` like every other job row.
- A failed listing is never written as derived state: if borg or the agent
  fails, `archive_sync` fails rather than recording the repository as empty.
- Cancelling a running operation is cooperative: the executor observes the
  request through `ctx.cancelled()` and stops at its next check. Cancelling
  a queued operation is immediate.

The `/api/operations` routes expose the list, a live queue view, cancel,
pause and resume of background triggers, and the `index_workers` limit.
Activity includes operations rows; index-category rows are hidden unless
the Index category filter is on.

### History index

Two more index kinds fill and maintain `archive_changes`:

- `history_index` (exclusive, takes the lane) walks every series of a
  repository by archive start. The first archive of a series stores its
  full listing as `added` rows from `borg list --json-lines`; every later
  archive stores the output of `borg diff --json-lines` against its
  predecessor. Paths matching `repository.history_index_excludes` are
  dropped. Modified files get absolute sizes from the last known size of
  the path in the series, since `borg diff` only reports byte deltas. Past
  `INDEX_HISTORY_MAX_ROWS` the rest is collapsed into `summary` rows keyed
  by the first three path segments and the archive is marked truncated.
  Each archive is written in one transaction; a crash leaves it either
  fully indexed or pending. An archive whose predecessor is not indexed
  yet stays pending for the next run, and the run reports
  `completed_with_warnings` so a stalled series is visible. An archive that
  failed is retried on the next run: nothing else moves it out of that
  state, and every later archive in the series waits on it. Managed-agent
  repositories skip the stage with `agent_diff_unsupported`.
- `history_merge` consumes `removed_archive_ids` from the `archive_sync`
  it depends on. A removed archive's rows are folded into its successor
  (the table in the spec, section 8.4), or the successor is reset to
  pending when the removed archive was never indexed, or the rows are
  simply dropped when there is no successor. The archive row is deleted
  afterwards.

Only `history_index` is gated on the plan including `archive_history`; on
Community installs the follow-up chains and the reconcile run omit it, and
activating a Pro licence enqueues a reconcile run for every repository.
`history_merge` runs on every plan, because it is what deletes the rows of
archives that have left the repository: `archive_sync` reports them and
deliberately leaves the deletion to it.
`POST /api/repositories/{id}/rebuild` with `from = history` resets the
index; `from = archives` refetches per-archive info; `from = stats`
re-measures the repository.

## Notifications

Job-related notifications are handled by the notification service.

Current notification event groups include:

- backup start/success/warning/failure
- restore success/failure
- check success/failure
- schedule failure

See [Notifications](../notifications).
