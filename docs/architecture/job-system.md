# Job System

Borg UI runs long operations as background jobs. Jobs keep the UI responsive while Borg commands run inside the container.

Every job is a row in the `operations` table. There is one job table and one
id space.

## Job Lifecycle

An operation moves through the status words of the operations vocabulary:

```text
queued -> running -> completed
queued -> running -> completed_with_warnings
queued -> running -> failed
queued -> running -> cancelled
queued -> skipped
```

The HTTP routes answer `pending` where the row says `queued`, because that is
the word their clients have always read. Every other word is the same on both
sides.

Operation rows store status, trigger, priority, timestamps, progress, errors,
and the path of the job's log file. Kind-specific columns live on an extension
table (`operation_backup_details`, `operation_restore_details`,
`operation_wipe_details`, `operation_rclone_details`); the kinds without one
keep their inputs in `operations.params`.

## Main Job Types

| Kind | Category | Exclusive | Purpose |
| --- | --- | --- | --- |
| `import_connect` | import | no | Connect an existing repository |
| `backup` | backup | yes | Run Borg create for a repository |
| `restore` | restore | no | Extract files from an archive |
| `restore_check` | restore | no | Verify that selected paths can be restored |
| `check` | maintenance | yes | Verify repository/archive integrity |
| `prune` | maintenance | yes | Apply retention policy |
| `compact` | maintenance | yes | Free unused repository space |
| `delete_archive` | maintenance | yes | Delete an archive |
| `wipe` | maintenance | yes | Delete every archive in a repository |
| `rclone_sync` | mirror | no | Copy a repository to (or from) an rclone remote |
| `package_install` | system | no | Install an OS package on the server |
| `stats` | index | no | Refresh a repository's size and archive count |
| `archive_sync` | index | no | Refresh the persisted archive list |
| `history_index` | index | yes | Index an archive's file history |
| `history_merge` | index | no | Fold indexed history into the series |

An exclusive kind holds its repository's lane: only one of them runs against a
repository at a time.

Schedules are configuration records. When a schedule fires, it enqueues backup,
check, or restore-check operations.

A wipe preview is not a unit of work, so it is the one thing still written to
`repository_wipe_jobs`; only the confirmed wipe becomes an operation, and it
names the preview it was confirmed from in `params.preview_id`.

## Backup Jobs

A backup is a row in the `operations` table (kind `backup`, category
`backup`, exclusive) with its backup columns on `operation_backup_details`:
archive name and sizes, the live progress fields, the route strategy and
source SSH connection, the remote host, the retry lineage columns, and the
maintenance status.

Every creation site enqueues through `create_backup_operation`: `POST
/api/backup/start` and its `/run` alias, the retry route, the single and
multi repository schedules, backup plan runs, and `POST /api/v2/backups/run`.
The operations runner dispatches the row when the repository lane is free
and the concurrency limits allow, and enqueues the index follow-up chain
(`archive_sync`, `history_merge`, `history_index`, `stats`) when the backup
succeeds.

Typical flow:

0. enqueue the operation
1. the runner dispatches it and marks it running
2. run pre-backup scripts
3. run Borg backup
4. update progress and logs
5. run configured prune/compact work
6. run post-backup scripts
7. send notifications
8. update final status

Steps 5 to 7 happen inside the executor or the calling scheduler exactly as
they did before the migration.

There are two execution paths. A server backup runs
`backup_service.execute_backup`, which covers a local source, an SSHFS
source, and a remote direct backup through `remote_backup_service`. An agent
backup queues an `agent_jobs` row carrying `operation_id`; the agent's start,
progress and completion reports write to the operation, and the executor
waits on the transport job.

Cancelling depends on the state. A running backup raises the runner's cancel
flag first and then kills the process, so the cancelled verdict survives the
service's later failure write. A queued backup is cancelled by the runner
directly. An agent backup sends a cancel request to the agent.

Post-backup prune, compact and check are child operations in the backup's
run, and `maintenance_status` on the details row mirrors them
(`running_prune` while the child prune runs, and so on).

## Restore Jobs

A restore is a row in the `operations` table (kind `restore`, category
`restore`) with its restore columns on `operation_restore_details`: archive,
destination, destination type and SSH connection, repository type, and the
live byte and file counts.
`POST /api/restore/start` enqueues the row; the operations runner dispatches
it. Restore is not exclusive (Borg allows concurrent reads), so it runs
beside a backup or check on the same repository rather than waiting for the
lane, exactly as it did before the migration.

The restore service keeps its three execution paths and drives the row
through a facade that presents the attribute surface it was written against:

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
captured output.

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

The caller of an inline operation owns its terminal status. When the step
raises instead of writing one (an agent job refused by admission because
the backup's follow-up listing still holds the repository, a locked
database), the caller closes the row as `failed` with the cause
(`fail_inline_maintenance`) and the plan's or schedule's run records the
failed step; the agent path does the same for the operation itself when
its job cannot be queued. A row a live agent job is still carrying is not
closed: the caller's wait may have given up on a prune the agent is still
running (or one still queued for an offline agent, which holds the
repository through admission on its own), and the agent's report closes
it. A step that returns with the
row still `running` (a service bug) is closed by `finish_inline_maintenance`
with that reason. A `running` operation nobody
closes counts as active write work and would refuse every backup of the
repository until the next restart, so the agent job reaper also fails,
once a minute, a `running` inline maintenance operation recorded as
agent-executed (`execution_mode`, which only `start_inline_maintenance`
sets for these kinds; a runner-dispatched operation is the runner's task
and ends with it) that is older than a few minutes and has no live agent
job behind it. Server-side operations are not reaped at runtime: a prune
records no pid, so nothing there proves the row dead.

A Borg 2 compact runs with `--stats` under `BORG_UNITS=raw` (the server
adds `--info`, the level Borg prints the lines on there). The repository
statistics Borg 2 reports only there ("Repository size is N B in M
objects." and the lines around it, exact byte counts) are stored on the
operation as `result["stats"]`. On the server the compact service parses
them from its own output. A managed agent from release 0.1.4 parses the
tail of its own output and sends them in its completion report; the server
takes `result["stats"]` from that report and otherwise parses the tail of
the job log once at completion (an agent that ran `--stats` but reported
nothing may still have those lines in flight, and then that compact records
no statistics; an older agent never sends them). A Borg warning exit
completes an agent compact with warnings, as it does on the server, and
carries the statistics the same way; the agent's other streamed
operations keep failing on any non-zero exit (a `check` that exits 1
found consistency errors). A successful compact also writes the
repository `total_size` from `repository_size`, by priority of source: a
size from the chunk index (`borg2_index`) or the Borg 1 cache statistics
(`borg1_cache_stats`) outranks it and stays; a store walk (`storage_used`)
or an older compact's figure is replaced by an exact compact figure; a
rounded one (a compact without `BORG_UNITS=raw`) replaces only an older
compact's figure or fills an empty size. The `stats` follow-up that runs
after every compact measures again and, where it can measure, replaces
the compact's figure (see `storage_usage`).

Use them carefully:

- checks can be expensive on large repositories
- prune changes retention state
- compact reclaims space after prune
- archive delete requires a per-archive lock: two different archives may be
  removed at once, the same one may not

Do not interrupt maintenance unless necessary.

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

On application startup, Borg UI checks for work left in `running` states by a
container restart or crash.

The operations runner does the recovery: it requeues index rows and fails the
rest unless their recorded process is still alive (see "Operations runner"),
including a local lock-break attempt for a repository whose lock a dead
process left behind. For a local check or compact, Borg UI attempts to break
the repository lock; for a remote repository it does not, because the remote
Borg process may still be running.

Two sweeps run beside it, for state that is not an operation:

- a backup left in a `running_prune`, `running_compact` or `running_check`
  maintenance state is marked `failed`, with the maintenance state changed to
  `prune_failed`, `compact_failed` or `check_failed`, unless its child
  operation is genuinely still running
- a backup plan run left `pending` or `running` is finalised from the states
  of its children

One mirror case is handled before recovery runs: an initial cloud mirror sync
(trigger `import`) left `running` by a restart is put back to `queued` rather
than failed. Recovery would fail it, which is right for a Borg command holding
a lock and wrong for `rclone sync`, which is itself a reconciliation and safe
to re-run. The requeue happens earlier in startup than
`OperationRunner.recover_on_startup`, so recovery sees a queued row and leaves
it alone.

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

Each of those is an operation: deleting the entry removes the `operations` row
and tries to delete the log file it names.

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
- No two of the shared index kinds (`archive_sync`, `history_merge`,
  `stats`) run on one repository at the same time, and no `history_index`
  starts next to one of them. The bypass settings do not change that: they
  read past a backup's lock, not past another index job. Two chains of one
  run (the backup's follow-ups and the prune's) otherwise started their
  stats side by side, and on an agent's repository a listing next to the
  stats' `rinfo` failed with rc 2, since Borg 1 holds the cache lock during
  `info` and `list` and only the server's own Borg calls are serialised by
  the metadata scope. A running `history_index` is governed by the lane
  and bypass as above, so an hours-long index does not hold the hourly
  listing; the metadata scope keeps its diff and the listing apart. Lane
  capacity (`index_workers`) stays global. An index row left `running` by
  a task the runner no longer has is requeued at the next tick, as at
  startup, so it holds neither the repository nor a worker; after three
  such requeues it fails instead, so a task that keeps dying ends in a
  visible failure. `GET /queue` reports the state as `index_busy` per
  repository.
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
  a backup executor (server or agent) enqueues the `backup` chain the
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
  whose key is bound to the REST server); below the index sum and the
  cache statistics, a Borg 2 compact's `--stats` figure (`compact_stats`,
  pack file bytes) fills the size and outranks a store walk when exact,
  until the next `stats` run measures again. The labels name different
  quantities: `compact --stats` counts
  pack file bytes, which include data no index entry covers, so it and
  `borg2_index` agree only on a fully indexed repository. Agent
  repositories get the same order from the agent's
  `repository.storage_usage` job (agents from 0.1.4; older agents
  keep `repository.disk_usage`, which only measures local paths). The
  agent measures local paths with du but has no `ssh://` du path; that
  one exists on the server only, where the SSH key is at hand. An
  unknown size leaves the stored value alone, never `0`. Both versions'
  `repository.last_modified` (the last manifest
  write) lands in `repositories.borg_last_modified`.
- The repository status (`GET /repositories/{id}/status`) reads
  repository evidence first: backup is the newest
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
  section 10.2. The repository card shows `Last prune` and `Last index`
  in its metadata row from the same evidence, delivered with the
  repositories list (`last_prune`, `last_index`, computed once per page
  by `repository_status.last_runs`); the status route is not polled.
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
  state, and every later archive in the series waits on it. A managed
  agent's repository never gets the stage (see the history capability
  below); should a row reach the executor anyway, it skips with
  `agent_diff_unsupported`.
- `history_merge` consumes `removed_archive_ids` from the `archive_sync`
  it depends on. A removed archive's rows are folded into its successor
  (the table in the spec, section 8.4), or the successor is reset to
  pending when the removed archive was never indexed, or the rows are
  simply dropped when there is no successor. The archive row is deleted
  afterwards.

Only `history_index` is gated on the plan including `archive_history`; on
Community installs the follow-up chains and the reconcile run omit it, and
activating a Pro licence enqueues a reconcile run for every repository.
The same gate applies per repository through its history capability
(`history_capability` in `app/services/operations/followups.py`): a
repository executed by a managed agent cannot be diffed by the server, so
it is `agent_unsupported` and gets no `history_index` from any chain.
`chain_for_repository` and the reconcile run read the three gates in one
place, the plan, the repository's index mode (below) and its executor, so
no follow-up site decides on its own. The rebuild route refuses
`from = history` for such a repository (409) and drops the kind for
`from = archives`. The capability is derived from the plan and the
executor when read, not stored. `archive_sync` marks such a repository's
`pending` and `failed` archives `skipped`, the state the history run used
to write for them (nothing there could retry a failure), and
`history_merge` resets a successor to `skipped` rather than `pending`
there; moving the repository back to the server puts them back to
`pending` with a fresh retry budget and queues an index run (a server's
listing reopens rows an older release left `skipped` the same way). The
archive list, detail and changes responses, the hub rows and the
path-history `coverage` carry it, so the
UI says "not available" where the stage does not exist rather than "not
yet"; the file history panel reads `coverage` (indexed archives out of
all) before it calls a repository unindexed or a path absent, and the
series' own archive states before it counts older archives without the
path.
`history_merge` runs on every plan, because it is what deletes the rows of
archives that have left the repository: `archive_sync` reports them and
deliberately leaves the deletion to it.
`POST /api/repositories/{id}/rebuild` with `from = history` resets the
index; `from = archives` refetches per-archive info; `from = stats`
re-measures the repository.

### Per-repository index mode

`repositories.index_mode` says how much derived data a repository keeps up
to date, and is the second gate beside the plan:

| Mode | Archive listing | File history | Size and health |
| --- | --- | --- | --- |
| `full` (default) | yes | yes (Pro) | yes |
| `archives` | yes | no | yes |
| `off` | no | no | no |

The mode is applied in two functions and nowhere else,
`followups.chain_for()` and `reconcile.reconcile_kinds()`, so a stage a
mode excludes is never created and then skipped, exactly as a Community
install never gets a `history_index` row. The reconcile tick skips an `off`
repository outright rather than enqueueing an empty run.

Manual work overrides the mode once and never repeats:
`POST /api/repositories/{id}/rebuild` and `POST /api/repositories/{id}/resync`
run for an `off` repository, and both answer with `index_mode` and a
`repeats` flag. The flag is a warning: it reads the stages that were asked
for, not the ones that survived the mode filter, so it is false as soon as
any of them will not be kept fresh. A `from = stats` rebuild on an
`archives` repository does repeat, since that mode still refreshes the
listing and the size; a `from = history` rebuild on the same repository
does not. Neither re-enables file history
behind a mode that excludes it, since the mode is a standing instruction
not to diff this repository. Clearing history stays explicit and works in
every mode: `rebuild` with `from = history` deletes the change rows
whatever the mode is.

Changing the mode away from `full` cancels the repository's queued index
work; a running index is left to finish, because the lane time is already
spent and its rows are kept in every mode. Changing back to `full` enqueues
one reconcile run so the repository catches up without waiting for the
tick. Rows already stored are never deleted by a mode change: they go
stale, and every surface says so rather than reporting the repository as a
problem.

## Notifications

Job-related notifications are handled by the notification service.

Current notification event groups include:

- backup start/success/warning/failure
- restore success/failure
- check success/failure
- schedule failure

See [Notifications](../notifications).

## Upgrading from a release before the operations runner

The first start after the upgrade copies every legacy job row into
`operations`: backups, restores, checks, restore checks, compacts, prunes,
archive deletes, executed wipes, mirror syncs, and package installs, with
their extension rows and the retry lineage. Copied rows get new ids, and the
`agent_jobs`, `script_executions` and `backup_plan_run_repositories` links are
rewritten to them. Log text a legacy row kept inline becomes the operation's
log file. A row whose repository had already been deleted is not copied, since
an operation's repository is a real foreign key. Nine of the ten job tables
are then dropped; `repository_wipe_jobs` stays behind as the preview store,
its executed rows having moved to `operations` and only its previews left.
