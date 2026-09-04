# Repository operations pipeline and archive history

**Date:** 2026-09-03
**Status:** Approved for implementation
**Owner:** karanhudia
**Related docs:** `docs/architecture/job-system.md`, `docs/engineering/specs/2026-04-13-archive-table-redesign.md` (superpowers copy), `docs/plan-content.md`

> **For agentic workers:** this spec is the single source of truth for the
> feature. Each phase in section 13 names the model that should implement it
> and the model that should review it. Do not start a phase without the
> previous phase merged. Use `superpowers:writing-plans` to turn one phase
> into a task-level plan under `docs/engineering/plans/` before coding it.
> Use `superpowers:test-driven-development` inside every phase and
> `superpowers:verification-before-completion` before claiming a phase done.
> All UI work must go through the `ui-ux-pro-max` skill and ship Storybook
> stories, per `AGENTS.md`.
>
> Appendix A lists the existing code each phase touches, with file paths.
> Appendix B records decisions already made and the alternatives rejected.
> Do not re-open a decision in Appendix B; if you believe one is wrong, stop
> and ask the owner rather than implementing something different.

---

## 1. Problem

Three separate problems share one root cause.

**Archive browsing is shallow.** The Archives page is a paginated list with
four icon buttons per row. Archive contents open in a modal that runs one
`borg list` per folder click. There is no way to see what changed between two
backups, when a file was last present, or where a deleted file still exists.
Every one of those needs data that Borg UI never stores.

**Derived data is computed ad hoc and invisibly.** After an import, the HTTP
request itself runs `borg info` and `borg list` and silently logs failures.
The same stats refresh is repeated from an hourly scheduler that loops over
every repository sequentially, from the end of every backup, and from the end
of every wipe. None of it is recorded, none of it is visible, and none of it
is coordinated with running backups, so it can collide on the Borg lock.

**Job execution has no convention.** Twelve job tables share the same core
columns (`id`, `repository_id`, `status`, `started_at`, `completed_at`,
`error_message`, `logs`, `log_file_path`, `progress`, `process_pid`,
`created_at`) but each has its own status vocabulary, its own creation site,
and its own `asyncio.create_task` call. `app/api/activity.py` runs nine
queries and merges them in Python to present one list. `maintenance_jobs.py`
is a half-built shared abstraction without a shared table. Nothing owns
"what is running on this repository right now", which is why a lock error
dialog exists in the frontend at all.

There is also no `archives` table. Every archive list anywhere in the app is
a live Borg call, and only the archive count and newest timestamp are stored.

## 2. User outcome

- A user imports a repository and gets control back immediately. A visible
  pipeline shows the repository moving through connect, stats, archives,
  history index, ready. Failures are red cards with a retry, not log lines.
- A user opens a repository and sees, per category, when it was last backed
  up, checked, pruned, compacted, indexed, and mirrored.
- A user opens an archive on its own page. A Changes tab shows what that
  backup added, removed, and modified compared to the previous one, read from
  the database with no Borg call. A Files tab browses the archive with a
  details pane. Clicking a file shows every archive that contains it and lets
  the user restore any version.
- A user searches for a filename and finds it across all archives, including
  files that no longer exist anywhere except in old backups.
- Archives are shown per series as a calendar heatmap. Gaps and size
  anomalies are visible at a glance.
- Activity remains the ledger of what happened. A separate Background work
  tab shows what Borg UI is doing now.
- Backups, checks, prunes, and index work on one repository never contend
  for the Borg lock, because one runner owns the repository lane.

## 3. Scope

- A unified `operations` table and a single in-process runner with
  per-repository lanes, priorities, dependencies, cancellation, and crash
  recovery.
- New persisted tables: `archives`, `archive_changes`.
- New operation kinds: `stats`, `archive_sync`, `history_index`,
  `history_merge`.
- A follow-up convention: every exclusive operation on a repository enqueues
  the derived-data chain for that repository.
- Migration of all existing job kinds onto `operations`, in phases, with the
  Activity API unioning old and new rows until the last phase.
- Retirement of `stats_refresh_scheduler` in favour of a reconcile trigger.
- Frontend: Background work tab, repository status strip, series heatmap,
  archive route with Changes and Files tabs, file history panel, global
  archive search, Activity category and trigger filters, run chains.
- Plan gating: the history layer is a Pro feature, `archive_history`;
  browsing stays Community (section 11).
- Storybook stories, unit tests, and docs updates for all of the above.

## 4. Non-goals

- No full per-archive file index for instant folder browsing. Folder
  listings keep going through Borg and the existing archive contents cache.
  The change table is sufficient for diff, history, search, and anomalies.
- No Miller-column browser. Breadcrumbs plus a details pane. Columns can be
  a later toggle.
- No file preview, treemap, restore cart, or time-travel scrubber. Listed in
  section 16 as follow-ups that become cheap once this ships.
- No distributed queue. The runner is in-process, like the existing
  schedulers started in `app/main.py`.
- No changes to how managed agents transport backups. `AgentJob` remains the
  transport record; it gains a pointer to an operation in the last phase.
- History index for managed-agent repositories is out of scope until the
  agent protocol gains a `diff` command. Such repositories show the history
  stage as `skipped` with a reason.

## 5. Vocabulary

| Term | Meaning |
| --- | --- |
| Operation | One row in `operations`. A unit of work on (usually) one repository. |
| Kind | What the operation does. Dispatch key for the runner. |
| Category | User-facing grouping of kinds. Filter key in Activity and the status strip. |
| Trigger | Why the operation exists: who or what asked for it. |
| Run | A group of operations sharing `run_id`, created by one trigger. A backup and its follow-ups form one run. |
| Follow-up | An operation with `trigger = followup` and a `depends_on_id`. |
| Lane | The per-repository serial slot for exclusive operations. |
| Exclusive | A kind that takes the Borg repository lock for a meaningful time. |
| Series | Archives from the same source that form one timeline. Borg 2 series name, or an inferred prefix for Borg 1. |

## 6. Data model

All new tables are created by Alembic migrations under
`app/database/alembic/versions/`. Column types follow existing models in
`app/database/models.py`. Timestamps are UTC and use the existing `utc_now`
helper.

### 6.1 `operations`

```python
class Operation(Base):
    __tablename__ = "operations"
    id                   = Column(Integer, primary_key=True)
    repository_id        = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=True, index=True)
    kind                 = Column(String, nullable=False, index=True)
    category             = Column(String, nullable=False, index=True)
    status               = Column(String, nullable=False, default="queued", index=True)
    trigger              = Column(String, nullable=False, default="manual")
    priority             = Column(Integer, nullable=False, default=10)
    run_id               = Column(String(36), nullable=False, index=True)
    depends_on_id        = Column(Integer, ForeignKey("operations.id", ondelete="SET NULL"), nullable=True)
    triggered_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    scheduled_job_id     = Column(Integer, ForeignKey("scheduled_jobs.id", ondelete="SET NULL"), nullable=True)
    backup_plan_run_id   = Column(Integer, ForeignKey("backup_plan_runs.id", ondelete="SET NULL"), nullable=True)
    execution_mode       = Column(String, nullable=True)      # server | remote_ssh | agent | rclone
    process_pid          = Column(Integer, nullable=True)
    process_start_time   = Column(Float, nullable=True)
    progress_percent     = Column(Float, nullable=True)
    progress_current     = Column(Integer, nullable=True)
    progress_total       = Column(Integer, nullable=True)
    progress_message     = Column(String, nullable=True)
    error_message        = Column(Text, nullable=True)
    skip_reason          = Column(String, nullable=True)
    log_file_path        = Column(String, nullable=True)
    params               = Column(JSON, nullable=True)         # kind-specific input, small
    result               = Column(JSON, nullable=True)         # kind-specific output summary, small
    created_at           = Column(DateTime, default=utc_now, nullable=False, index=True)
    started_at           = Column(DateTime, nullable=True)
    completed_at         = Column(DateTime, nullable=True)
```

Indexes: `(repository_id, status)`, `(status, priority, created_at)`,
`(run_id)`, `(category, created_at)`.

`params` and `result` hold small kind-specific JSON. Anything large or
queried on its own gets an extension table (6.2).

### 6.2 Extension tables

Created only when a kind migrates. One-to-one with `operations.id`.

| Table | Columns moved from | Notes |
| --- | --- | --- |
| `operation_backup_details` | `BackupJob` | archive_name, original/compressed/deduplicated size, nfiles, current_file, backup_speed, total_expected_size, estimated_time_remaining, route_strategy, source_ssh_connection_id, remote_process_pid, remote_hostname, retry_* columns, maintenance_status |
| `operation_restore_details` | `RestoreJob` | archive, destination, destination_type, destination_connection_id, temp_extraction_path, destination_hostname, repository_type, restored_size, restore_speed, nfiles, current_file |
| `operation_wipe_details` | `RepositoryWipeJob` | phase, archive_count, archive_fingerprint, archive_manifest_json, dry_run_output, blocking_reason, protected_archives_json, run_compact, requested_by_user_id, confirmed_by_user_id, confirmed_at |
| `operation_rclone_details` | `RcloneSyncJob` | direction, operation, scheduled_for, bytes_transferred, files_transferred, log_text, error_text |

Check, prune, compact, restore check, delete archive, package install, and
the four index kinds need no extension table. Their kind-specific inputs
(`extra_flags`, `max_duration`, `probe_paths`, `full_archive`,
`archive_name`, `package_id`) go in `params`.

### 6.3 Enumerations

Stored as strings, validated in Python. Defined once in
`app/services/operations/vocab.py` and mirrored in
`frontend/src/types/operations.ts`.

**kind**

| kind | category | exclusive | notes |
| --- | --- | --- | --- |
| `import_connect` | import | no | `borg info` verification. Synchronous in the request, but recorded. |
| `backup` | backup | yes | |
| `restore` | restore | no | Reads only. Borg allows concurrent reads. |
| `restore_check` | restore | no | |
| `check` | maintenance | yes | |
| `prune` | maintenance | yes | |
| `compact` | maintenance | yes | |
| `delete_archive` | maintenance | yes | |
| `wipe` | maintenance | yes | |
| `rclone_sync` | mirror | no | Uses the existing `rclone` lock scope, not the lane. |
| `package_install` | system | no | `repository_id` is null. |
| `stats` | index | no | `borg info`. Uses `bypass_lock_on_list` if set. |
| `archive_sync` | index | no | `borg list` or `repo-list`. |
| `history_index` | index | yes | `borg diff` per pair. Exclusive because it can run for minutes. |
| `history_merge` | index | no | Pure SQL. |

**category:** `import`, `backup`, `restore`, `maintenance`, `index`, `mirror`, `system`.

**status:** `queued`, `running`, `completed`, `completed_with_warnings`,
`failed`, `cancelled`, `skipped`.

Mapping from existing vocabularies during migration:

| old | new |
| --- | --- |
| `pending` | `queued` |
| `needs_backup` (BackupJob) | `skipped` with `skip_reason = "needs_backup"` |
| `running_prune`, `running_compact` (BackupJob maintenance) | `running` on the child prune or compact operation; backup itself is `completed` |
| `prune_failed`, `compact_failed` | `failed` on the child operation |

**trigger:** `manual`, `schedule`, `plan`, `import`, `followup`, `reconcile`, `retry`.

**priority:** lower runs first. `0` manual and plan, `5` schedule, `10`
followup, `20` reconcile and manual rebuild.

### 6.4 `archives`

```python
class Archive(Base):
    __tablename__ = "archives"
    id                 = Column(Integer, primary_key=True)
    repository_id      = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False, index=True)
    borg_id            = Column(String(64), nullable=False)    # archive id hex
    name               = Column(String, nullable=False)
    series             = Column(String, nullable=False, index=True)
    start              = Column(DateTime, nullable=False, index=True)
    end                = Column(DateTime, nullable=True)
    duration_seconds   = Column(Float, nullable=True)
    nfiles             = Column(Integer, nullable=True)
    original_size      = Column(BigInteger, nullable=True)
    compressed_size    = Column(BigInteger, nullable=True)
    deduplicated_size  = Column(BigInteger, nullable=True)
    hostname           = Column(String, nullable=True)
    username           = Column(String, nullable=True)
    comment            = Column(Text, nullable=True)
    backup_operation_id = Column(Integer, ForeignKey("operations.id", ondelete="SET NULL"), nullable=True)
    history_state      = Column(String, nullable=False, default="pending")  # pending | indexed | skipped | failed
    history_indexed_at = Column(DateTime, nullable=True)
    history_rows       = Column(Integer, nullable=True)
    history_truncated  = Column(Boolean, nullable=False, default=False)
    first_seen_at      = Column(DateTime, default=utc_now, nullable=False)
    last_seen_at       = Column(DateTime, default=utc_now, nullable=False)
    __table_args__ = (UniqueConstraint("repository_id", "borg_id"),)
```

`archive_sync` populates `borg_id`, `name`, `series`, `start`, `end`,
`hostname`, `username`, `comment` from the list output, which is cheap for
both Borg versions. Sizes and `nfiles` come from per-archive `borg info`,
which is expensive (see #854). Rule: `archive_sync` fetches info only for
archives it has not seen before, capped at `INDEX_ARCHIVE_INFO_PER_RUN`
(default 20) per run, oldest first. The remaining ones are picked up by the
next reconcile. The existing info-dialog sync
(`sync_archive_stats_from_info`) keeps writing into this table instead of
the repository row.

`repository.archive_count`, `repository.last_backup`, and
`repository.total_size` stay as columns for backward compatibility but are
written by `stats` and `archive_sync` from this table and `borg info`.

### 6.5 `archive_changes`

```python
class ArchiveChange(Base):
    __tablename__ = "archive_changes"
    id            = Column(Integer, primary_key=True)
    archive_id    = Column(Integer, ForeignKey("archives.id", ondelete="CASCADE"), nullable=False, index=True)
    path          = Column(Text, nullable=False)
    change        = Column(String(8), nullable=False)   # added | removed | modified | summary
    size_before   = Column(BigInteger, nullable=True)
    size_after    = Column(BigInteger, nullable=True)
    mode_changed  = Column(Boolean, nullable=False, default=False)
    owner_changed = Column(Boolean, nullable=False, default=False)
    summary_count = Column(Integer, nullable=True)      # only for change = summary
```

Indexes: `(archive_id, path)`, and `(path)` for history and search. SQLite
gets a plain index on `path`. Search uses `LIKE` on `path` with the filename
segment; a later phase may add FTS5 if measurements justify it.

One row per changed path per archive. `summary` rows collapse a subtree past
the cap (6.7). The first archive in a series stores its full listing as
`added` rows, which is the only time a full `borg list --json-lines` runs.

### 6.6 Series inference

- Borg 2: `series` is the archive `name` from `repo-list`, which Borg 2
  already defines as a series.
- Borg 1: `series` is derived by `infer_series(name, repository)`:
  1. If a backup plan or schedule targets this repository with an archive
     name template, strip the template's timestamp placeholders and use the
     literal prefix.
  2. Else strip a trailing ISO-like timestamp (`-YYYY-MM-DD[T_]HH[:-]MM[:-]SS`
     and common variants) from the name.
  3. Else `"default"`.
- Series is recomputed on every `archive_sync`; a changed series moves the
  archive to the new series and marks it `history_state = pending`.

### 6.7 History index caps and exclusions

- `repository.history_index_excludes` (new JSON column, list of glob
  patterns). Default seeded on repository creation and import:
  `["**/.cache/**", "**/Library/Caches/**", "**/node_modules/**",
  "**/__pycache__/**", "**/.git/objects/**"]`. Editable in repository
  settings.
- `INDEX_HISTORY_MAX_ROWS` setting, default 200000 per archive. When a diff
  exceeds it, remaining changes are grouped by their first three path
  segments into `summary` rows with `summary_count`, and
  `archives.history_truncated = true`.
- Diff output is streamed line by line; rows are inserted in batches of 5000
  inside one transaction per archive so a crash leaves either a fully indexed
  archive or none.

## 7. Runner

Location: `app/services/operations/`.

```
operations/
  vocab.py          kinds, categories, statuses, triggers, exclusivity table
  models.py         re-exports and typed helpers over Operation rows
  enqueue.py        enqueue(kind, repository, trigger, ...) -> Operation
  followups.py      chain_for(kind) -> list of follow-up kinds
  runner.py         OperationRunner: loop, lane rules, dispatch, recovery
  lanes.py          repository lane state, exclusivity checks
  executors/
    __init__.py     registry: kind -> executor coroutine
    index.py        stats, archive_sync, history_index, history_merge
    maintenance.py  check, prune, compact, delete_archive   (phase 5)
    wipe.py         (phase 6)
    rclone.py       (phase 6)
    package.py      (phase 6)
    restore.py      (phase 7)
    backup.py       (phase 8)
  events.py         broadcast operation.updated / operation.progress
```

### 7.1 Loop

`OperationRunner.start()` is launched from `app/main.py` alongside the other
schedulers. It waits on an `asyncio.Event` that `enqueue()` sets, with a
fallback poll every 5 seconds. Each tick:

1. Load `queued` operations whose `depends_on_id` is null or points at a
   `completed` or `completed_with_warnings` operation. If the dependency is
   `failed`, `cancelled`, or `skipped`, mark the dependant `skipped` with
   `skip_reason = "dependency_failed"` and continue down the chain.
2. Order by `priority`, then `created_at`.
3. For each candidate, check the lane and the global limits (7.3). Dispatch
   the first that fits, then re-evaluate. Stop when nothing fits.
4. Dispatch means: set `running`, `started_at`, spawn
   `asyncio.create_task(executor(operation))`, keep the task handle in
   memory for cancellation.

Executors receive an `OperationContext` with the row, a `progress()`
callback that throttles writes to at most one per second and broadcasts an
SSE event, a `log()` sink writing to `log_file_path`, and a
`cancelled()` check.

### 7.2 Lane rules

`lanes.py` answers `can_start(operation) -> bool`:

- If the kind is exclusive, the repository must have no other `running`
  exclusive operation. During migration, "running exclusive" also consults
  the legacy tables (`BackupJob`, `CheckJob`, `PruneJob`, `CompactJob`,
  `RepositoryWipeJob`, `DeleteArchiveJob`) via one helper,
  `legacy_running_exclusive(repository_id)`, which is deleted in phase 9.
- Non-exclusive index kinds may run alongside an exclusive operation only if
  `bypass_lock_on_list` is enabled; otherwise they wait too.
- `rclone_sync` uses `run_serialized_repository_command(scope="rclone")` as
  it does today and ignores the lane.
- Executors also wrap Borg calls in
  `run_serialized_repository_command(scope="metadata")`. The lane prevents
  scheduling collisions; the lock prevents accidental ones.

### 7.3 Global limits

Existing settings keep their meaning and move behind one function,
`global_slot_available(operation)`:

- `max_concurrent_manual_backups`, `max_concurrent_scheduled_backups`,
  `max_concurrent_scheduled_checks` apply to the corresponding kinds and
  triggers.
- New `index_workers` (default 2) caps concurrently running index kinds
  across all repositories. Exposed on the Background work tab.
- New `background_paused` flag (default false) stops dispatch of `followup`
  and `reconcile` triggers. Manual and scheduled work is never paused by it.

### 7.4 Follow-ups

`followups.chain_for(kind)`:

| after | chain (in order, each depends on the previous) |
| --- | --- |
| `import_connect` | `stats`, `archive_sync`, `history_index` |
| `backup` | `archive_sync`, `history_index`, `stats` |
| `prune` | `archive_sync`, `history_merge`, `stats` |
| `delete_archive` | `archive_sync`, `history_merge`, `stats` |
| `compact` | `stats` |
| `check` | none |
| `wipe` | `archive_sync`, `history_merge`, `stats` |
| `restore`, `restore_check`, `rclone_sync`, `package_install` | none |

Follow-ups are created by the runner when the parent reaches a terminal
success state, with the parent's `run_id`, `trigger = followup`,
`priority = 10`. They are not created when the parent fails.

`archive_sync` runs before `history_merge` so the merge knows which archives
disappeared. `history_index` skips pairs whose predecessor is not yet
indexed and leaves them `pending`; the next run picks them up.

### 7.5 Reconcile

Replaces `stats_refresh_scheduler`. Same setting
(`stats_refresh_interval_minutes`, `0` disables). On each tick, for every
repository without a queued or running index operation, enqueue one run:
`archive_sync`, `history_merge`, `history_index`, `stats`, with
`trigger = reconcile`, `priority = 20`. This catches archives created or
pruned outside Borg UI.

### 7.6 Crash recovery

On startup, before the runner starts:

- `running` operations of exclusive Borg kinds: if `process_pid` is alive
  with the recorded `process_start_time`, leave them and let the executor
  reattach where supported (check, compact, as today); otherwise mark
  `failed` with `error_message = "interrupted by restart"`. Local
  repositories get the existing lock-break attempt; remote ones do not, as
  documented in `job-system.md`.
- `running` index operations: set back to `queued`. They are idempotent.
- `queued` operations are left alone.

This replaces the per-table startup cleanup for each kind as it migrates.

### 7.7 Cancellation

`POST /api/operations/{id}/cancel` sets `cancelled` on a `queued` row
directly. For a `running` row it sets a cancel flag the executor observes
via `ctx.cancelled()`; Borg executors also terminate the child process, as
the existing cancel paths do. Dependants become `skipped`.

### 7.8 Retention

`job_history_retention.py` gains `operations` and the extension tables in
its table list. Rows follow `cleanup_retention_days`; log files follow
`log_retention_days`. `archives` and `archive_changes` are not job history
and are never purged by it.

## 8. Index executors

### 8.1 `stats`

Runs `borg info` via `BorgRouter`. Writes `repository.total_size` and
`result = {"unique_csize": n}`. Uses the stats env with `bypass_lock_on_list`
as today. Replaces the size half of `update_repository_stats`.

### 8.2 `archive_sync`

1. `BorgRouter.list_archives()`.
2. Upsert rows into `archives` by `(repository_id, borg_id)`. Update
   `last_seen_at`. Compute `series`.
3. Rows in `archives` not present in the list are collected as
   `result["removed_archive_ids"]` and left in place; `history_merge`
   consumes and deletes them.
4. For up to `INDEX_ARCHIVE_INFO_PER_RUN` never-seen archives, run
   per-archive `borg info` and fill sizes.
5. Write `repository.archive_count` and `repository.last_backup`.

### 8.3 `history_index`

For each series in the repository, ordered by `start`:

- For each archive with `history_state = pending`:
  - If it has no predecessor in the series, run
    `borg list --json-lines` (Borg 1) or `borg -r R list --json-lines aid:X`
    (Borg 2) and store `added` rows.
  - Else if the predecessor is `indexed`, run
    `borg diff R::prev R::cur --json-lines` (Borg 1) or
    `borg -r R diff aid:prev aid:cur --json-lines` (Borg 2), apply excludes,
    store rows, apply the cap.
  - Else leave `pending`.
- Progress: `progress_current` is the pair index, `progress_total` the
  pending count, `progress_message` is `"<prev> → <cur>"`.
- Managed-agent repositories: set `history_state = skipped` on all pending
  archives and `skip_reason = "agent_diff_unsupported"` on the operation.

New wrapper methods: `Borg.diff_archives(...)` in `app/core/borg.py`,
`Borg2.diff_archives(...)` in `app/core/borg2.py`,
`BorgRouter.diff_archives(...)`. Both parse `--json-lines` output into a
normalised `ChangeRecord(path, change, size_before, size_after,
mode_changed, owner_changed)`. Fixtures come from real Borg output captured
with the `borg-live-debug` skill.

### 8.4 `history_merge`

Input: archives that `archive_sync` reported removed. For each removed
archive `R`, find its successor `S` in the same series by `start`.

If `S` exists, fold `R`'s rows into `S`:

| R | S has | result on S |
| --- | --- | --- |
| added | nothing | copy R row |
| added | modified | `added`, `size_before = null` |
| added | removed | delete S row (file never existed in a surviving archive) |
| modified | nothing | copy R row |
| modified | modified | `size_before = R.size_before` |
| modified | removed | `size_before = R.size_before` |
| removed | nothing | copy R row |
| removed | added | `modified`, `size_before = R.size_before`, `size_after = S.size_after` |
| summary | any | keep S, add `summary_count` |

If `S` does not exist (the newest archive was removed), `R`'s rows are
simply deleted.

Then delete the `archives` row for `R`, which cascades to its remaining
rows. All of this is SQL inside one transaction per removed archive. No
Borg call, no lane.

The visible effect is honest: a change that happened in a pruned archive now
shows at the next surviving archive, which is the earliest place the user can
restore that version from.

## 9. API

All routes under `/api`. Authorization uses the existing
`require_repository_access_by_path` and role helpers: `viewer` for reads,
`operator` for cancel and rebuild, `admin` for pause and worker limits.

### 9.1 Operations

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/operations` | List. Filters: `repository_id`, `category[]`, `kind[]`, `status[]`, `trigger[]`, `run_id`, `since`, `limit`, `cursor`. Returns `OperationItem[]` plus `next_cursor`. |
| GET | `/operations/{id}` | One row with extension details and the rest of its run. |
| GET | `/operations/queue` | Live view: all `queued` and `running` rows, plus rows completed in the last 60 seconds, grouped by repository, with lane state and global limits. |
| POST | `/operations/{id}/cancel` | See 7.7. |
| POST | `/operations/pause` and `/operations/resume` | Toggle `background_paused`. |
| PUT | `/operations/limits` | `{"index_workers": n}`. |
| GET | `/operations/{id}/logs` and `/logs/download` | Same contract as `/activity/{job_type}/{job_id}/logs`. |

`OperationItem` is a superset of today's `ActivityItem` so the frontend
table can render either. New fields: `kind`, `category`, `trigger`,
`priority`, `run_id`, `depends_on_id`, `progress_current`, `progress_total`,
`progress_message`, `skip_reason`, `followups: OperationItem[]` (only in
list responses when `collapse_runs=true`).

### 9.2 Repository derived data

| Method | Route | Purpose |
| --- | --- | --- |
| POST | `/repositories/{id}/rebuild` | Body `{"from": "stats" \| "archives" \| "history"}`. Invalidates that stage and later ones, enqueues a manual run at priority 20. `history` sets all archives `pending` and deletes their change rows. |
| GET | `/repositories/{id}/status-strip` | Latest terminal operation per category for this repository, plus age thresholds. |
| GET | `/repositories/{id}/archives` | From `archives`. Query: `series`, `since`, `until`. Includes `sync_state` (`fresh`, `syncing`, `stale`, `never`). |
| GET | `/repositories/{id}/archives/heatmap` | Per series, per day: count, total deduplicated size, anomaly flags. |
| GET | `/repositories/{id}/archives/{archive_id}` | One archive with history state. |
| GET | `/repositories/{id}/archives/{archive_id}/changes` | Query: `compare_to` (archive id, default predecessor), `path_prefix`, `change[]`, `limit`, `cursor`. Folds intermediate deltas when `compare_to` is not the predecessor. |
| GET | `/repositories/{id}/history` | Query: `path`. Returns every archive that touched the path with change and sizes, plus computed "present" ranges. |
| GET | `/repositories/{id}/search` | Query: `q`, `limit`. Filename search over `archive_changes.path`, grouped by path with first seen, last seen, archive count, and whether it is present in the newest archive. |

The existing `/archives/list` route remains for one release and gains a
deprecation header; the Archives page switches to the DB route in phase 4.

### 9.3 Activity

`GET /activity/recent` gains `category[]` and `trigger[]` filters and
`collapse_runs` (default true). During migration it unions legacy tables with
`operations`. Index-category rows are excluded unless `category` includes
`index`. Follow-ups are nested under their parent when `collapse_runs` is
true.

### 9.4 Events

`event_manager.broadcast_event` gains two event types:

- `operation.updated` with the full `OperationItem` on every status change.
- `operation.progress` with `{id, progress_percent, progress_current,
  progress_total, progress_message}` throttled to once per second per
  operation.

The Background work tab, the repository status strip, and the Archives page
subscribe through the existing SSE hook.

### 9.5 Anomaly rules

Computed in `app/services/operations/anomalies.py`, returned by the heatmap
and status-strip routes. Pure functions with unit tests.

- `missed_run`: a day inside a series' expected cadence with no archive.
  Cadence is the schedule or plan cron when known, else the median gap of
  the last 14 archives.
- `size_outlier`: `deduplicated_size` or `nfiles` below 60 percent of the
  median of the previous 7 archives in the series.
- `duration_outlier`: `duration_seconds` above 250 percent of the median of
  the previous 7.
- `overdue_<category>`: last terminal operation in a category older than
  the category's threshold. Defaults: backup 2 days, check 30 days, prune
  14 days, compact 30 days, index 2 days, mirror 1 day.

## 10. Frontend

All new components ship a Storybook story. Dialogs use `ResponsiveDialog`.
Selects that need rich rows use `RichSelect`. No left accent borders. Every
string goes through `react-i18next` with keys added to
`frontend/src/locales/*.json`. Types live in
`frontend/src/types/operations.ts` and `frontend/src/types/archives.ts`.

### 10.1 Background work tab

Route `/settings/background-work`, tab id `background-work`, admin and
operator visible, wired in `frontend/src/pages/Settings.tsx` and the
settings nav. `docs/navigation.md` is updated in the same change.

```
Settings ▸ Background work                              [⏸ Pause] [Rebuild… ▾]

  Connect        Stats          Archives        History index     Ready
  ──────────     ──────────     ──────────      ──────────        ──────────
  ┌──────────┐   ┌──────────┐   ┌──────────┐    ┌──────────┐      ┌──────────┐
  │ offsite  │   │ nas ●    │   │          │    │ photos ● │      │ laptop ✓ │
  │ waiting  │   │ 00:41    │   │          │    │ 14/38    │      │ docs   ✓ │
  └──────────┘   └──────────┘   └──────────┘    │ ████░░░░ │      │ media  ✓ │
                                                └──────────┘      └──────────┘
  1 waiting      1 running      0               1 running         3 done

  Foreground: nas ● backup (plan: nightly) 41 min   → holds the lane
  workers: index 2                                     [Activity ▸]
```

Components under `frontend/src/components/background-work/`:

- `PipelineBoard` renders stage columns from `/operations/queue`.
- `PipelineStageColumn` with count and worker control.
- `PipelineRepositoryCard` with status, elapsed time, progress bar, retry.
  Moves between columns with a short slide transition when its stage
  changes.
- `ForegroundLaneRow` shows a running exclusive foreground operation holding
  the lane, with a link to Activity and no controls.
- `RepositoryTrackDialog` (`ResponsiveDialog`) shows one repository's run
  as a vertical track with per-stage timing and a "Rebuild from" `RichSelect`.
- `RebuildMenu` for the header action.

Empty state: an `EmptyStateCard` saying nothing is running, with the last
reconcile time.

### 10.2 Repository status strip

`OperationStatusStrip` inside `RepositoryCard`, fed by
`/repositories/{id}/status-strip`.

```
nas-backup                                     41.2 GB · 38 archives
  Backup   ✓ 2h ago     Check    ✓ 3d ago     Prune   ✓ 2h ago
  Compact  ⚠ 41d ago    Index    ● syncing    Mirror  ✓ 6h ago
```

Cells render only for categories that apply (no Mirror cell without rclone
storage). One `CategoryToken` component owns icon and colour per category
and is reused by Activity, the pipeline board, and the archive page. The
warning state comes from `overdue_<category>` anomalies.

### 10.3 Archives page

- `RepositorySelectorCard` stays.
- `ArchiveSeriesHeatmap` replaces the top of the list: one block per
  series, weeks as rows, days as columns, cells coloured by count and
  outlined for anomalies, hover shows size and duration, click opens the
  archive route. A "List" toggle keeps the existing `ArchivesList` for
  people who prefer it; the preference persists in `localStorage` like the
  existing list settings.
- A `sync_state` chip near the selector: "Synced 2 min ago", "Syncing",
  or "Not indexed yet" with a rebuild link.
- The list and heatmap read from `/repositories/{id}/archives`.
- `ArchiveSearchField` above the heatmap, hitting
  `/repositories/{id}/search`, results in a `ResponsiveDialog` list with
  "present in latest" and "last seen" columns.

### 10.4 Archive route

`/archives/:repositoryId/:archiveId` rendered by
`frontend/src/pages/ArchiveDetail.tsx`. Header: name, series, start, duration,
sizes, `[Restore] [Mount] [Delete]` using the existing dialogs. Tabs:

**Changes**

```
[ Changes (+12 −3 ~41) ]  [ Files ]  [ Info ]

Compared with  nas-2026-09-01T02:00 (previous) ▾        net +184 MB
  ~ home/karan/docs/invoices.xlsx        374 KB → 412 KB
  + home/karan/photos/IMG_2291.heic       4.1 MB
  − home/karan/docs/draft.txt             3 KB
  ▸ 38 more modified in home/karan/Library/…
```

`ArchiveChangesTab` with a `RichSelect` compare picker, change-type filter
chips, virtualised rows grouped by top-level directory, and a truncated
banner when `history_truncated`. When `history_state` is `pending` or
`skipped` it shows an explanatory empty state with a rebuild link.

**Files**

`ArchiveFilesTab` wraps the existing `ArchivePathSelector` browsing on the
left and a new `ArchiveFileDetailsPane` on the right: metadata, `[Restore]`,
`[Download]`, and a `FileHistoryPanel`. On screens narrower than the `md`
breakpoint the details pane becomes a `ResponsiveDialog` bottom sheet.

```
home / karan / docs                                   [🔍 search in archive]
┌───────────────────────────────────────┬───────────────────────────────────────┐
│   Name              Size    Modified  │  invoices.xlsx                        │
│ ▸ 📁 contracts      1.2 GB  Sep 01    │  ────────────────────────────────     │
│ ▸ 📁 photos         8.4 GB  Aug 30    │  Size      412 KB                     │
│ ☐ 📄 invoices.xlsx  412 KB  Sep 01 ◀  │  Modified  Sep 01, 23:14              │
│ ☐ 📄 notes.md        12 KB  Aug 28    │  Owner     karan:staff  rw-r--r--     │
│ ☐ 📄 taxes.pdf      2.1 MB  Jul 15    │                                       │
│                                       │  [Restore]  [Download]                │
│                                       │                                       │
│                                       │  History                              │
│                                       │  Sep 02 02:00  412 KB  unchanged      │
│                                       │  Sep 01 02:00  412 KB  changed ▲38 KB │
│                                       │  Aug 24 02:00  372 KB  first seen     │
├───────────────────────────────────────┴───────────────────────────────────────┤
│ 2 selected (2.5 MB)                                            [Restore… ]    │
└───────────────────────────────────────────────────────────────────────────────┘
```

Nothing is selected on open; the pane shows folder metadata for the current
path. Selecting a file fills the pane and loads its history. Multi-select
keeps the pane on the last clicked file and the footer shows the selection
count with a restore action that opens `RestoreWizard` preselected.

```
invoices.xlsx  ▸ History
  Sep 02 02:00   412 KB   unchanged
  Sep 01 02:00   412 KB   changed   ▲ +38 KB   [Restore this]
  Aug 31 02:00   374 KB   changed   ▲ +2 KB    [Restore this]
  Aug 24 02:00   372 KB   first seen
  Not present in 6 older archives
```

`FileHistoryPanel` reads `/repositories/{id}/history?path=`. "Restore this"
opens the existing `RestoreWizard` preselected to that archive and path.

**Info** reuses `RepositoryInfo` style metadata for the archive.

`ArchiveContentsDialog` remains for one release as the entry point from the
list view and gains an "Open full page" action.

### 10.5 Activity

- `ActivityFilters` gains category chips and a trigger select. Category
  chips use `CategoryToken`.
- `BackupJobsTable` rows for a parent operation render a `RunChainRow`
  beneath: follow-up kinds with status ticks and progress, expandable.
- Index-category rows appear only when the Index chip is on.
- No action buttons for index work in Activity.

**Per-repository operations view.** `RepositoryCard` gains an "Operations"
action that opens Activity with the repository filter pinned and the URL
carrying `?repository_id=`. It is the same table, not a new component. Runs
render as chains:

```
nas-backup ▸ Operations            [Backup] [Maintenance] [Index] [Mirror]

Today
  02:00  ● backup   plan: nightly                       41.2 GB   2h 11m
         └ archive_sync ✓ · history_index ● 14/38 · stats ○
  01:30  ✓ prune    schedule: weekly                    −3 archives
         └ history_merge ✓ · archive_sync ✓ · stats ✓
Yesterday
  02:00  ✓ backup   plan: nightly                       41.0 GB   2h 04m
         └ 3 follow-ups ✓
```

Category chips filter parent operations only. Follow-ups always ride with
their parent, so filtering by Backup still shows the index work that backup
caused. A nightly plan across ten repositories is ten rows in global
Activity, not forty.

**Boundary between Activity and Background work.** Activity answers "what
did Borg UI do". Background work answers "what is Borg UI doing". Activity
is read-only history with logs. Background work holds every control: pause,
worker limits, rebuild, retry. A running foreground operation appears in
both: as a row in Activity and as the lane holder on the board. Finished
operations leave the board after a 60 second hold and remain in Activity.

### 10.6 Keyboard

In the Files tab: arrow keys move selection, Enter opens a folder,
Backspace goes up, `/` focuses search, `r` opens restore for the selection.

## 11. Plan gating

Archive browsing stays a Community feature. The history layer is Pro. The
split is one feature key, `archive_history`, added to both registries:
`app/core/features.py` `FEATURES` and `frontend/src/core/features.ts`
`FEATURES`, with value `pro`. `docs/plan-content.json` gains a Pro entry
`archive_history` with localized label and description; the existing
Community entry `archive_browsing` is unchanged.

### 11.1 What each plan gets

| Capability | Community | Pro |
| --- | --- | --- |
| Operations table, runner, lanes, follow-ups, Background work tab | yes | yes |
| Repository status strip | yes | yes |
| `archives` table, `stats`, `archive_sync`, DB-backed archive list | yes | yes |
| Series heatmap with counts and sizes | yes | yes |
| Missed-run flag on the heatmap | yes | yes |
| Archive route with Files tab, details pane, keyboard navigation | yes | yes |
| Size and duration outlier flags, overdue category warnings | no | yes |
| `history_index` and `history_merge` stages, `archive_changes` rows | no | yes |
| Changes tab, compare picker | no | yes |
| File history panel and "Restore this" per version | no | yes |
| Global archive search including deleted files | no | yes |
| Rebuild from `history` | no | yes |

The rule of thumb: anything that reads `archive_changes` or computes an
insight from more than one archive is Pro. Anything that shows what Borg
already knows about one archive is Community.

### 11.2 Backend enforcement

- Routes `/repositories/{id}/archives/{archive_id}/changes`,
  `/repositories/{id}/history`, `/repositories/{id}/search`, and
  `POST /repositories/{id}/rebuild` with `from = history` use
  `Depends(require_feature("archive_history"))`, which returns the same
  403 payload other gated routes use.
- The heatmap route always returns counts, sizes, and `missed_run`; it
  includes outlier and overdue flags only when the plan includes the
  feature. The status-strip route does the same for overdue warnings.
- `followups.chain_for()` omits `history_index` and `history_merge` when
  `plan_includes(get_current_plan(db), Plan.PRO)` is false. Reconcile does
  the same. No operation is created and then skipped; the stage simply does
  not exist for Community, so the Background work board shows four columns
  instead of five.
- When a Pro licence is activated, the licensing service's activation path
  enqueues a reconcile run for every repository so history builds in the
  background. When a licence lapses, existing `archive_changes` rows are
  kept but unreadable through the gated routes; the next reconcile after
  re-activation resumes from `history_state = pending` archives.
- `archives.history_state` for Community installs stays `pending`, which
  the frontend reads as "not available on this plan" when the feature is
  locked, and as "not indexed yet" when it is unlocked.

### 11.3 Frontend enforcement

All gates use the shared `PlanGate` with `feature="archive_history"` and the
analytics `surface` and `operation` props, so blocked interactions are
tracked like other Pro features.

- Changes tab: `PlanGate` with `preview` set to a static, inert sample
  `ArchiveChangesTab` rendered from fixture data, so a Community user sees
  what the tab looks like behind the upgrade prompt. `surface="archive_detail"`,
  `operation="view_changes"`.
- File history panel: `PlanGate` with `disabled` so the panel's header row
  shows with a lock and the upgrade message, without a large prompt inside
  the details pane. `surface="archive_files"`, `operation="view_history"`.
- Search field on the Archives page: `PlanGate` with `disabled`, tooltip
  from the gate message. `surface="archives"`, `operation="search"`.
- Heatmap outlier and overdue flags: not gated in the UI; the API omits them
  and the legend shows a small "Pro" chip next to the outlier entries using
  `PLAN_LABEL` and `PLAN_COLOR`.
- Rebuild menu: the `history` option is rendered through `PlanGate` with
  `disabled`.
- Background work board: renders the columns the API reports; no gate
  needed.

Storybook stories for each gated surface show both the locked and unlocked
state, following `PlanGate.stories.tsx`.

### 11.4 Tests

- `tests/unit/test_core_features.py`: `archive_history` is Pro on the
  backend; the frontend features test asserts the same key and plan.
- `test_operations_followups.py`: chain with and without the feature.
- Route tests: 403 for Community on each gated route, 200 for Pro.
- Heatmap and status-strip tests: flags present only for Pro.
- Vitest for each `PlanGate` usage: locked renders the prompt or disabled
  state, unlocked renders the feature.

## 12. Testing

Backend, `tests/unit/`:

- `test_operations_vocab.py`: every kind has a category and an exclusivity
  entry; status mapping table.
- `test_operations_runner.py`: dispatch order by priority then age;
  dependency gating; dependency failure skips the chain; lane blocks a second
  exclusive kind; index kinds wait without bypass and run with bypass;
  global limits; pause only affects followup and reconcile; crash recovery
  for both exclusive and index kinds; cancellation of queued and running.
- `test_operations_followups.py`: chain table.
- `test_series_inference.py`: template prefix, timestamp stripping, default.
- `test_borg_diff_parsing.py`: fixtures from real `borg diff --json-lines`
  output for Borg 1 and Borg 2, captured with `borg-live-debug`.
- `test_history_index.py`: first archive full listing, pair diff, excludes,
  cap and summary rows, agent skip.
- `test_history_merge.py`: every row of the fold table in 8.4, successor
  missing, transaction atomicity.
- `test_changes_fold.py`: folding across three archives equals a direct diff
  of the endpoints on fixture data.
- `test_anomalies.py`: each rule with boundary values.
- `test_activity_union.py`: legacy and new rows merge, ordering, category
  filter hides index rows by default, `collapse_runs` nesting.
- Per migration phase: the old creation sites now produce `operations`
  rows; the old table receives no new rows; the logs endpoint still resolves
  by kind and id.

Integration, `tests/integration/`: import a fixture repository, assert the
pipeline reaches `Ready`, prune one archive outside Borg UI, run reconcile,
assert the merge outcome.

Frontend, Vitest under `__tests__` next to each component and Storybook
stories for every component listed in section 10. Snapshot coverage through
`npm run snapshots` locally and Argos in CI.

## 13. Phases, models, and reviewers

Model names use the current Claude 5 family. "Implement" is the model the
user selects with `/model` for the session that writes the code. "Review" is
a different model, selected the same way in a later session, that reads the
diff before merge. No subagents are used. Every phase gets its own plan file
under `docs/engineering/plans/` and its own branch.

| # | Phase | Implement | Review | Why this split |
| --- | --- | --- | --- | --- |
| 1 | Foundation: `operations`, `archives`, `archive_changes` tables and migrations; vocab; runner with lanes, limits, dependencies, recovery, cancellation; `stats` and `archive_sync` executors; queue API; SSE events; Activity union; reconcile replacing `stats_refresh_scheduler`; import returns after connect | Fable 5.1 | Opus 5 | The runner and lane rules are small but subtle and everything later depends on them. |
| 2 | History: `diff_archives` wrappers for Borg 1 and 2 with real fixtures; series inference; `history_index` with excludes and cap; `history_merge` fold; changes, history, search, heatmap, status-strip, rebuild routes; anomaly rules; `archive_history` feature key, route guards, plan-aware follow-up chain, licence activation hook (11.2) | Fable 5.1 for merge fold, index executor, and fold-across-archives; Sonnet 5 for wrappers, fixtures, routes, and anomaly rules once the first executor exists | Opus 5 | Correctness of the fold and the index is the feature. Wrappers and routes are pattern work. |
| 3 | Background work tab, status strip, `CategoryToken`, settings nav, docs | Sonnet 5 with `ui-ux-pro-max` | Opus 5 | The mocks are specific; the reviewer checks against AGENTS.md UI rules and the mocks. |
| 4 | Archive experience: DB-backed list, heatmap, search, archive route, Changes tab, Files tab with details pane and history panel, keyboard, Activity filters and run chains; `PlanGate` on every Pro surface with locked and unlocked stories, `plan-content.json` entry (11.3) | Sonnet 5 with `ui-ux-pro-max`; Opus 5 for the Files tab integration with `ArchivePathSelector` and `RestoreWizard` | Opus 5 | Most of this is new components against a fixed API. The Files tab touches the most existing code. |
| 5 | Migrate check, prune, compact, restore check, delete archive; follow-up convention replaces the four scattered stats calls; retire their startup cleanup and `maintenance_jobs.py` table helpers | Opus 5 for the first kind and the follow-up wiring; Sonnet 5 for the remaining four kinds by pattern | Fable 5.1 | The first migration sets the pattern; the reviewer must catch behavioural drift in scheduled checks and prune-after-backup. |
| 6 | Migrate wipe, rclone sync, package install with extension tables | Sonnet 5 | Opus 5 | Contained kinds with their own services. Wipe's confirm workflow needs care but is well tested today. |
| 7 | Migrate restore and restore's missing `repository_id` | Opus 5 | Opus 5 | Restore has remote destinations and agent execution paths. |
| 8 | Migrate backup: v1 and v2 routes, plan execution service, retry lineage, `AgentJob.operation_id`, maintenance states as child operations, notifications, MQTT | Fable 5.1 | Fable 5.1 (fresh session) | Thirty five columns, three creation sites, and every integration hangs off it. |
| 9 | Collapse: Activity reads only `operations`; delete legacy job tables and `legacy_running_exclusive`; update `docs/architecture/job-system.md`, `docs/api.md`, `docs/navigation.md`; Postman collection | Opus 5 | Sonnet 5 | Deletion and documentation with a full test suite behind it. |

Rules that apply to every phase:

- The implementing session reads this spec and the phase plan only, plus
  files the plan names. It does not have the conversation that produced this
  spec.
- Tests are written before the migration in each phase.
- The Activity union must pass its tests at the end of every phase, since it
  is what keeps the UI honest while two worlds coexist.
- Phase 1 through 4 can ship to users. Phases 5 through 9 are internal
  refactors with no visible change except fewer lock errors.
- Phases 3 and 4 may run in parallel with phase 2 against the API contract
  in section 9, using Storybook mocks, but merge only after phase 2.

## 14. Migration and rollout

- Each migration is one Alembic revision. Legacy rows are not copied; they
  are read through the union until retention drops them. Phase 9 deletes the
  tables only after `cleanup_retention_days` has elapsed since phase 8
  shipped, or after an explicit one-off copy if the user wants old history
  kept.
- New settings (`index_workers`, `background_paused`,
  `INDEX_ARCHIVE_INFO_PER_RUN`, `INDEX_HISTORY_MAX_ROWS`) are added to
  `app/config.py` and `docs/configuration.md` in phase 1 and 2.
- `repository.history_index_excludes` is added in phase 2 with the default
  list backfilled for existing repositories.
- On first startup after phase 2, a reconcile run is enqueued for every
  repository at priority 20. Large installs index in the background over
  hours; nothing blocks.
- Feature flag: `background_work_tab` in `BetaFeaturesTab` for phase 3 and
  `archive_history` for phase 4, both default on, removable in phase 9.

## 15. Risks

- **SQLite write contention.** `archive_changes` inserts in batches of 5000
  can hold the write lock. Keep batches inside the existing chunked write
  pattern from `job_history_retention.py` and yield between batches.
- **First-archive full listing on huge archives.** A series' first archive
  stores its whole tree. The cap in 6.7 bounds rows; the listing itself
  streams. If measurements show this is still too slow, store the first
  archive as a single `summary` row and start deltas from the second.
- **Borg 1 series inference is heuristic.** A wrong split produces two
  series with a spurious "first archive" each. Mitigation: recompute on each
  sync, show the series name on the archive page, allow a manual series
  override on the repository in a follow-up.
- **Lock bypass semantics differ between Borg 1 and 2.** The lane rule in
  7.2 treats index kinds as blocked unless bypass is on; phase 1 tests must
  cover both versions with `borg-live-debug`.
- **Backup migration scope.** Phase 8 is the one place a big-bang rewrite is
  tempting. The extension table exists precisely so backup columns move, not
  change. Behavioural changes to backups are out of scope for that phase.
- **Frontend size.** The archive route pulls in the path selector, restore
  wizard, and a virtualised list. Lazy-load the route.

## 16. Follow-ups this enables

Not in scope, listed so nobody re-derives them.

- Time-travel scrubber on the Files tab, walking `archives` in a series.
- Inline preview for text, images, and PDFs via the download route.
- Size treemap per archive from a full listing on demand.
- Restore cart across archives.
- Miller-column browser toggle.
- FTS5 search if `LIKE` proves slow.
- Agent protocol `diff` command to unblock history for managed agents.
- Manual series override per repository.
- Merging `BackupPlanRun` into `run_id` semantics.
- Moving the Background work tab into the sidebar if usage justifies it.

## 17. Open questions

- Should `check` get an `archive_sync` follow-up? A check with `--repair`
  can change archives; a plain check cannot. Default no, revisit if repair is
  exposed in the UI.
- Should summary rows carry the largest individual paths inside the subtree
  for display? Default no; the cap is a safety valve, not a feature.
- Should the heatmap replace the list by default or sit above it? Default
  replace, with the toggle persisted; validate in phase 4 review.

## 18. Documentation updates

Done in the phase that changes behaviour:

- `docs/architecture/job-system.md`: rewrite around operations, lanes,
  follow-ups, recovery (phase 1, then phase 9).
- `docs/configuration.md`: new settings (phases 1 and 2).
- `docs/navigation.md`: Background work tab, archive route (phases 3 and 4).
- `docs/api.md` and the Postman collection: new routes (phases 2 and 9).
- `docs/cache.md`: clarify that the archive contents cache is separate from
  the persisted index (phase 2).

## 19. Working this spec

This section is the only state the feature carries between sessions. Say
`/continue-spec` (or "continue the spec") in any session and the agent
follows 19.2 from wherever the table in 19.1 says we are. No subagents are
used: the session you are talking to does the step itself, on the model you
selected with `/model`.

### 19.1 Progress

Agents update this table and nothing else as work advances. Statuses:
`not started`, `plan drafted`, `plan approved`, `in progress`, `in review`,
`done`, `blocked`.

| Phase | Status | Plan file | Branch | Notes |
| --- | --- | --- | --- | --- |
| 1 Foundation | done | `docs/engineering/plans/2026-09-03-operations-phase-1-foundation.md` | `feat/operations-phase-1` | Implemented on Fable 5.1; reviewed on Opus 5 at G3 against 6.1, 6.3, 6.4, 7, 8.1, 8.2, 9.1, 9.3, 9.4 and Appendix B; ten findings raised, 1-8 fixed on Opus 5 in 751bd7ac (owner chose to fix on the review model rather than switch to Fable 5.1); findings 9 (deleting a queued mid-chain operation frees its dependents, activity.py) and 10 (collapse_runs nesting on /api/operations) deferred to the phases that own them; merged to main 2026-09-03 as bd4ba893 via PR #888 with CI green; no release, per section 13 phases 1-4 ship together; `run_stats` now delegates agent repositories to `_update_agent_repository_stats`, which also writes archive_count and last_backup - a second writer to columns archive_sync owns, to be resolved when the agent kinds migrate in phase 5; index executors keep the retired scheduler's MQTT state publish; plan step 15.5 live check not run; job_history_retention.py review thread left open on #888 as the marker for issue #895 |
| 2 History | in progress | `docs/engineering/plans/2026-09-04-operations-phase-2-history.md` | `feat/operations-phase-2` | Tasks 1-3 done on Sonnet 5 2026-09-04 (settings/feature key/migration, series inference, real Borg 1.4.5/2.0.0b21 diff and list fixtures captured via borg-live-debug plus diff_archives/list_archive_lines wrappers); full unit suite green except the 14 pre-existing OIDC failures; real fixtures diverged from the plan's assumed JSON shapes (Borg 2 presence entries use added/removed ints not size, mode change is "changed mode" not "mode", diff entries carry no type field so a directory's own mtime-only change is indistinguishable from a file's, borg2 subcommands are repo-create/repo-list not rcreate/rlist), parser and tests written against the captured fixtures with findings recorded in tests/fixtures/borg_output/README.md; Tasks 4-6 done on Fable 5.1 2026-09-04 (history_fold.py with the 8.4 fold table and fold_sequence, history.py with history_index and history_merge executors, history_enabled() in followups.py, excludes as anchored regexes, cap into per-three-segment summary rows, modified sizes resolved from the last known size in the series, one transaction per archive, merge folds/resets/drops per successor state); plan deviations: run_history_merge captures the removed archive's name before the delete commits (the plan read it after, which raises on an expired instance), _load_repository is imported from index.py rather than duplicated; two plan test bugs fixed (Borg 2 test needed distinct borg_ids, a class-level FakeRouter patch leaked between tests); six Task 1-3 files reformatted with ruff format (CI enforces it); full unit suite after Task 6: 2998 passed, 17 failed = the 14 pre-existing OIDC failures plus 3 in test_api_repositories_import_operations.py that assert the phase 1 import chain without history_index; these are transitional, since registering the executor puts history_index into the chain and Task 7's history=history_enabled(db) removes it again for Community installs (the plan runs that file at Task 7's end); work still uncommitted pending G2 at Task 12; Task 7 done on Sonnet 5 2026-09-04 (HISTORY_KINDS and history-aware chain_for in followups.py, runner and record_import_connect pass history_enabled(db) into chain_for, reconcile.enqueue_reconcile_runs gained a history kwarg defaulting to "ask the plan" plus bootstrap_history_once gated on SystemSettings.history_bootstrap_at, licensing_service._on_plan_changed enqueues a Pro-activation reconcile run from _apply_entitlement, main.py runs bootstrap_history_once after the reconcile scheduler starts); two plan test bugs fixed (get_or_create_licensing_state always returns the first LicensingState row, so the followups and reconcile plan-awareness tests flip that row's plan instead of inserting a second one; the reconcile test also had to mark the first run's operations completed before re-enqueuing, since has_active_index_work would otherwise skip the repository); full unit suite: 3009 passed, 14 failed (the pre-existing OIDC failures only), ruff clean; stopped at G0 before Task 8, which the spec's index-executor bucket assigns to Fable 5.1; owner chose to continue on Sonnet 5, deviation recorded here; Task 8 done on Sonnet 5 2026-09-04 (write_repository_archive_columns extracted from run_archive_sync in index.py, repository_info_sync upserts the archives table via apply_listing when info entries carry ids and falls back to columns-only otherwise); one plan test bug fixed (the plan's new test used naive timestamps with no timezone_name, which resolve in the test server's own local zone rather than UTC - switched to offset-carrying ISO strings matching the file's existing convention); Task 9 done on Sonnet 5 2026-09-04 (app/services/operations/anomalies.py: median, size/duration outlier, cadence and missed-run-day detection, overdue thresholds, series_flags, all pure functions per spec 9.5); one plan bug fixed (expected_days_from_gap used an inclusive `current <= until` bound, which double-counted the boundary day for a sub-daily gap spanning exactly the window; changed to `<`, matching the "capped at one expected day per day" contract and leaving the cron/gap-based missed_run_days cases unaffected); Task 10 done on Sonnet 5 2026-09-04 (app/api/archive_index.py: GET /{repo_id}/archives, /archives/heatmap, /archives/{archive_id}, /status-strip, POST /rebuild; app/services/operations/legacy_status.py; live listing moved to GET /{repo_id}/archives/live; RepositoryUpdate.history_index_excludes plus PUT assignment and both the list and single-repository GET serializers; /api/archives/list now sends Deprecation and Link headers); several plan bugs fixed: (1) utc_now() is tz-aware but Operation.completed_at and Archive.start round-trip as naive UTC through SQLite, so comparing them directly raised TypeError - now compares against utc_now().replace(tzinfo=None) in sync_state_for, the heatmap's until default, and status_strip's now; (2) the plan's mirror-cell check read repository.cloud_mirror_enabled and .storage_backend, neither of which is a Repository column (cloud_mirror_enabled is a create-time request field only) - changed to repository.repository_type == "rclone", matching _primary_storage_backend's own check, and updated the test fixture to set repository_type instead; (3) the rebuild-from-history test's _pro() helper inserted a second LicensingState row, which get_or_create_licensing_state never sees (it always returns the first row) - changed to flip the existing row's plan, same class of bug as Task 7's; (4) the settings round-trip test read history_index_excludes off the top-level GET response, but GET /{repo_id} nests its payload under "repository" - fixed the test and added the field to that endpoint's serializer (the plan named a different, list-endpoint serializer at line 3087, which was also updated but is not what the test exercises); rebuild's operator check uses get_repository_with_access(..., role="operator") rather than the plan's Depends(require_any_role(...)), since require_any_role takes a resolved user positionally and is not a dependency factory - matches the convention in app/api/operations.py's cancel route; full unit suite through Task 10: 3034 passed, 14 failed (pre-existing OIDC only), 12 skipped, ruff clean, frontend Archives.delete.test.tsx passes; Task 11 done on Sonnet 5 2026-09-04 (appended to archive_index.py: GET /archives/{archive_id}/changes comparing against the predecessor or an older compare_to with intermediate deltas folded via fold_sequence, present_ranges plus GET /history for per-path history and open/closed present ranges, GET /search grouping archive_changes by path with LIKE, all three gated by require_feature("archive_history")); no plan bugs, all 24 new/existing tests in test_api_archive_index.py passed on the first run; full unit suite: 3044 passed (Task 9's anomalies and Task 11's routes both landed), 14 failed (pre-existing OIDC only), 12 skipped, ruff clean; Task 12 done on Sonnet 5 2026-09-04 (History index section added to docs/architecture/job-system.md before Notifications; docs/cache.md notes the archive index is not a cache; docs/api.md gained the Archive index and history route table; Borg_UI_API.postman_collection.json gained folder 24 "Archive index and history" with 8 requests, inserted as a pure addition after folder 23 rather than round-tripped through json.dump, which would have reformatted the whole 7111-line file from 2-space to the json module's default indent); phase verification per plan step 5 all green: full unit suite 3044 passed / 14 failed (pre-existing OIDC only) / 12 skipped, ruff check and ruff format --check clean, frontend src/core + planContent.test.ts + Archives.delete.test.tsx (5 tests) and npm run lint clean, `alembic upgrade head` applies all six revisions including this phase's c2d3e4f5a6b7 cleanly against a fresh DATA_DIR, docs/plan-content.json and frontend/src/data/plan-content.json identical, no em dashes in the touched modules or this plan file; live end-to-end check against borg-live-debug not run this session (no live container reachability confirmed) - recorded per phase 1's precedent; committed on `feat/operations-phase-2` as f01aa18b, not pushed; awaiting G3 code review on Opus 5 against spec sections 6.5, 6.6, 6.7, 8.3, 8.4, 9.2, 9.5, 11.2 and Appendix B G0 answered 2026-09-04: owner confirmed the session was on Opus 5, the reviewer section 13 names. G3 code review run on Opus 5 against 6.5, 6.6, 6.7, 8.3, 8.4, 9.2, 9.5, 11.2 and Appendix B; nine findings raised: (1) HIGH BorgApiClient.listArchives still requests /repositories/{id}/archives, which Task 10 repointed at the DB-backed index route, so Archives.tsx and ScheduledRestoreChecksSection receive index rows whose id is a DB row id and which carry no archive/time/triggered_by; (2) HIGH history_merge is in HISTORY_KINDS, so Community installs strip it and nothing ever deletes the archives rows apply_listing reports as removed; (3) MED a failed history_state is never returned to pending, so one transient error stalls the whole series while runs still report completed; (4) MED anomalies cron branch mixes local and UTC dates, flagging almost every day as a missed run for a non-UTC schedule; (5) MED tz-aware since/until query params reach naive comparisons and 500 the heatmap; (6) MED /search has no SQL LIMIT and the changes route folds N x cap rows in memory; (7) MED the changes fold ignores non-indexed intermediates and reports no changes for files that changed; (8) LOW an empty history_index_excludes list reads back as the defaults while excluding nothing; (9) LOW repository_info_sync drops the removed ids apply_listing returns and can no longer roll its write back. Owner chose at G3 to fix findings 1-7 in this session on Opus 5 and to leave 8 and 9 for a follow-up; status returned to in progress for the fix pass, which ends at a fresh G2 before anything is committed. G3 fix pass done on Opus 5 2026-09-04: findings 1-7 fixed with a test first for each. (1) BorgApiClient.listArchives now calls /archives/live, and the v2 router serves that path as a second decorator on its own list_archives, so one client method reaches the live listing on both borg versions; (2) PLAN_GATED_KINDS = {history_index} split out of HISTORY_KINDS, so history_merge runs on Community too and pruned archives leave the table, and the rebuild archives stage gained history_merge; (3) history_index retries archives in the failed state and reports completed_with_warnings when any archive is left pending; (4) expected_days_from_cron converts the base into the schedule's zone and every firing back to UTC, so cron days and archive days share a frame; (5) since/until query params are normalised through _naive_utc; (6) /search bounds the path page in SQL (matching_paths + rows_for_paths) and the changes fold reads its whole window in one query instead of one per archive; (7) the changes response carries incomplete and unindexed_archive_ids when the fold window contains an archive that was never indexed. CI on PR #897 was red on three jobs, all fixed: the alembic backfill of history_index_excludes bound a plain string, which Postgres refuses to assign to a json column (now sa.bindparam with type_=sa.JSON), verified against a real Postgres 16 with BORG_TEST_POSTGRES_URL; the integration archive-listing test still called /archives (now /archives/live); and test_live_listing_moved read route.path on an included router that has none. CodeRabbit raised eight review comments, seven fixed: the empty history_index_excludes list is preserved by both serializers and compile_excludes treats None as the defaults (this was review finding 8); expected_days_from_gap is passed until directly, since it already stops at the last expected time before it; CommandLineStream bounds the whole command with one deadline rather than per read and kills the process on expiry; merge_removed_archive applies the row cap and summary rollup to the folded result via the new capped_rows helper; bootstrap_history_once claims history_bootstrap_at with a conditional UPDATE and commits before enqueueing, releasing the claim if the enqueue raises; repository_info_sync requires every field archive_fields_from_listing needs before it uses apply_listing's removal result (this was review finding 9); docs/cache.md states that the index has no TTL but follows archive lifecycle operations. The one comment declined is CodeRabbit's request that the rebuild archives stage also reset history_state and delete archive_changes: the spec gives from=history its own stage for exactly that, and refetching per-archive sizes does not invalidate the stored deltas. Verification: full unit suite 3062 passed / 14 failed (the pre-existing OIDC failures only) / 12 skipped, ruff check and format clean, tests/unit/test_db_upgrade.py 23 passed against a real Postgres 16, the previously failing integration test passes (three other integration failures reproduce on the branch head without these changes and are local-environment only), frontend borgApi + Archives + ScheduledRestoreChecks 23 passed, npm run lint clean. Awaiting G2 for the fix-pass commit and push. Second G3 review on Opus 5 2026-09-04 over the fix pass itself (the first attempt was scoped f01aa18b..19b26b95 by mistake, which excludes the fix commit and covered only two test commits; rerun over f01aa18b..ac8af705). It confirmed the v1 live route is not shadowed, PLAN_GATED_KINDS replaced HISTORY_KINDS at every gating site, the bootstrap claim is correct under SQLite and Postgres, capped_rows handles pre-existing summary rows, and the [] versus None excludes fix is consistent across all six sites. Four findings, all fixed in 137f2c19: (1) the whole-command deadline was a hard 1 hour ceiling that would kill a legitimately long borg list or a diff over a slow remote, so timeout is the idle bound again and max_duration (24h) bounds the run; (2) retrying failed archives had no bound, costing a full diff under the metadata lock on every reconcile run, so a history_attempts column (migration d3e4f5a6b7c8) caps it at MAX_HISTORY_ATTEMPTS=3, resets on success, and reports an exhausted count; (3) the compare-window in_() is chunked at SIZE_LOOKUP_CHUNK for older SQLite builds -- note the test does not reproduce the 999 limit locally, since modern SQLite allows 32766; (4) expected_days_from_gap is anchored on the newest archive rather than the oldest, which resolves the disagreement between CodeRabbit (a due run was hidden) and this review (a moved schedule flagged every day): the defect was the phase anchor, not the - gap. Also fixed in ac8af705: the v2 live alias had no request-level coverage, and the OpenAPI assertion is a declaration check that cannot see shadowing, which was verified by flipping the include order in main.py (the pre-existing agent listing test catches it; my openapi tests did not). Verification: 3071 passed, 14 failed (pre-existing OIDC only), 12 skipped, ruff clean, migration upgrade/downgrade/upgrade round-trips. Awaiting the G3 decision on merge. |
| 3 Background work tab | not started | | | May run in parallel with 2 once 2's plan is approved |
| 4 Archive experience | not started | | | May run in parallel with 2 once 2's plan is approved |
| 5 Migrate maintenance kinds | not started | | | |
| 6 Migrate wipe, rclone, package | not started | | | |
| 7 Migrate restore | not started | | | |
| 8 Migrate backup | not started | | | |
| 9 Collapse and cleanup | not started | | | |

### 19.2 Continuation protocol

1. Read this spec in full. Find the first phase in 19.1 whose status is not
   `done`. If several phases are eligible in parallel and one is already
   `in progress`, prefer advancing the one furthest along.
2. Determine the step from the status, and the model the step wants from
   the section 13 table: plan writing and implementation use the phase's
   implement model, review uses its review model.
3. Model check. Compare the model the session is running on (stated in the
   system prompt) with the model the step wants. If they differ, stop and
   ask: "This step wants <wanted>; this session runs <current>. Switch with
   `/model` and run `/continue-spec` again, or continue on <current>?" Do
   not proceed until the user answers. Continuing on a different model is
   allowed; record it in the Notes column.
4. Act on the status, in this session, with no subagents:
   - `not started`: run `superpowers:writing-plans` for the phase, writing
     `docs/engineering/plans/<date>-operations-phase-<n>-<slug>.md` in the
     format of `docs/engineering/plans/2026-05-24-rclone-storage-integration.md`.
     Reference spec sections and mocks by number instead of copying them.
     End the plan with an `Open questions` heading. Write no application
     code. Set `plan drafted`, fill the plan column, stop at gate G1.
   - `plan drafted`: stop at gate G1.
   - `plan approved`: create the branch named in the table (default
     `feat/operations-phase-<n>`) from `main`, set `in progress`, then run
     `superpowers:executing-plans` on the plan with
     `superpowers:test-driven-development` for every task. The spec wins if
     the plan and the code disagree. UI tasks use the `ui-ux-pro-max` skill
     and add Storybook stories per AGENTS.md. When the plan's tasks are done,
     run `superpowers:verification-before-completion`. If it passes, set
     `in review` and stop at gate G2. If it fails, make one fix attempt; on a
     second failure set `blocked` with the failure in Notes and stop at gate
     G4.
   - `in progress` (resuming an interrupted session): read the plan's
     checkboxes, continue from the first unchecked task, same rules.
   - `in review`: run `/code-review high` on the branch against `main`,
     checking against the spec sections listed in 19.3 and Appendix B.
     Report findings only, change nothing, stop at gate G3.
   - `blocked`: present the Notes and stop at gate G4.
5. After any gate where the user answers, update 19.1 before doing anything
   else, so an interrupted session can resume from the table.

### 19.3 Review focus per phase

Phase 1: sections 6.1, 6.3, 6.4, 7, 8.1, 8.2, 9.1, 9.3, 9.4. Phase 2: 6.5,
6.6, 6.7, 8.3, 8.4, 9.2, 9.5, 11.2. Phase 3: 10.1, 10.2. Phase 4: 10.3 to
10.6, 11.3. Phases 5 to 8: 6.2, 6.3, 7.4, 7.6 and the kind's own service.
Phase 9: 9.3, 14, 18. Every phase: Appendix B.

### 19.4 Gates

The session stops and asks the user with a clear question at each gate. It
never proceeds past a gate on its own.

- G0 model: the check in 19.2 step 3.
- G1 plan review: "Plan for phase <n> is at <file>. Approve, request
  changes, or stop?" Approve sets `plan approved`. Changes are applied to
  the plan in this session with the user's notes, then G1 again.
- G2 verification and commit: show the verification output, then ask
  whether to commit. Per `.claude/instructions.md`, nothing is committed or
  pushed without this answer. Commit messages follow the repository
  convention and name the phase.
- G3 review findings: present the findings and ask whether to apply fixes
  (in this session, ideally after switching to the implement model), merge
  (run `superpowers:finishing-a-development-branch`, then set `done`), or
  stop.
- G4 blocked: present what failed and ask how to proceed.
- G5 spec conflict: if the spec and reality disagree in a way Appendix B
  does not settle, present the conflict and ask before anything is changed.
  Record the answer in Appendix B.

### 19.5 Cost notes

Each step runs in one context. Plan writing and review are cheap on any
model. Implementation is where the model choice matters, so the table in
section 13 puts Sonnet on pattern work and reserves Fable for the runner,
the merge logic, and the backup migration. Starting a fresh session per step
keeps the context small; `/continue-spec` re-derives everything it needs
from this file.

---

## Appendix A. Current state inventory

Line numbers are as of 2026-09-03 on branch `fix/remote-direct-plan-flow`
and will drift; use them as search anchors, not truths.

### A.1 Where derived stats are computed today

All of these are replaced by `enqueue()` calls in phase 1 or phase 5.

| Site | What it does | Replaced by |
| --- | --- | --- |
| `app/api/repositories.py:3736` inside `import_repository` | Calls `BorgRouter(repository).update_stats(db)` inline in the HTTP request, swallowing errors | `import_connect` recorded, then `stats` and `archive_sync` follow-ups (phase 1) |
| `app/api/repositories.py:914` `update_repository_stats` | `borg list` for count and last backup, `borg info` for size; not wrapped in the repository command lock | `stats` and `archive_sync` executors (phase 1) |
| `app/api/repositories.py:813` `_update_agent_repository_stats` | Agent variant of the above | Same executors, routed through `BorgRouter` |
| `app/services/stats_refresh_scheduler.py:26-160` | Hourly sequential loop over all repositories calling `update_stats` | Reconcile trigger, section 7.5 (phase 1) |
| `app/services/backup_service.py:2643` and `:2759` | Stats after a backup | `backup` follow-up chain (phase 8; until then, a one-line `enqueue` replaces the call in phase 5) |
| `app/services/repository_wipe_service.py:465` | Stats after a wipe | `wipe` follow-up chain (phase 6) |
| `app/services/repository_info_sync.py:47` `sync_archive_stats_from_info` | Writes archive stats when the info dialog opens; called from `app/api/repositories.py:6089`, `:6139`, `app/api/v2/repositories.py:569`, `:634` | Keeps running, writes into `archives` (phase 2) |
| `app/core/borg_router.py:434` `BorgRouter.update_stats` | Router entry for the above | Kept as a thin call into the executors, then removed in phase 9 |

### A.2 Existing job machinery

| File | Role | Fate |
| --- | --- | --- |
| `app/database/models.py` classes `AgentJob` (125), `RcloneSyncJob` (568), `BackupJob` (608), `RestoreJob` (724), `ScheduledJob` (771), `BackupPlanRun` (1062), `CheckJob` (1173), `RestoreCheckJob` (1210), `CompactJob` (1256), `PruneJob` (1289), `DeleteArchiveJob` (1314), `RepositoryWipeJob` (1345), `PackageInstallJob` (1798) | Per-kind job tables | Migrated per section 13; `AgentJob`, `ScheduledJob`, `BackupPlanRun` remain |
| `app/api/maintenance_jobs.py:50-160` | Shared helpers for check, prune, compact, restore check, delete archive (`ensure_no_running_job`, `create_maintenance_job`, `schedule_background_job`, `start_background_maintenance_job`) | Replaced by `enqueue()` and the runner in phase 5 |
| `app/api/activity.py:312` `list_recent_activity` | Nine per-table queries merged in Python; `ActivityItem` at line 66 | Union with `operations` in phase 1, single query in phase 9 |
| `app/api/activity.py:868`, `:1193`, `:1364` | Logs, log download, delete by `job_type` and `job_id` | Contract kept; resolves `operations` by kind and id from phase 1 |
| `app/services/repository_command_lock.py:37` `run_serialized_repository_command` | Per-repository asyncio lock with `metadata` and `rclone` scopes | Kept; lane rules in 7.2 sit above it |
| `app/utils/process_utils.py` `cleanup_orphaned_jobs`, called from `app/main.py:357` | Startup cleanup per legacy table | Replaced per kind as each migrates; see 7.6 |
| `app/services/job_history_retention.py` | Row and log retention across job tables | Gains `operations` and extension tables (phase 1) |
| `app/main.py:396-460` | Startup of schedulers (stats refresh, MQTT sync, agent job reaper, job history retention) | Runner started here; stats refresh removed |
| `app/api/events.py:18` `EventManager`, `:55` `broadcast_event`, `:136` `/events/stream` | Server-sent events | Gains `operation.updated` and `operation.progress` |
| `app/services/cache_service.py:484` `ArchiveCacheService`, used by `app/api/browse.py` | Redis or in-memory cache of folder listings | Untouched; distinct from the persisted index |
| `app/core/borg.py`, `app/core/borg2.py`, `app/core/borg_router.py:398` and `:731` | Borg wrappers; `list_archive_contents`, `list_archives` | Gain `diff_archives` (phase 2) |
| `app/database/alembic/versions/` | Migrations | New revisions per phase |

### A.3 Frontend surfaces touched

| File | Role today | Fate |
| --- | --- | --- |
| `frontend/src/pages/Archives.tsx` (698 lines) | Repository selector, stats grid, list, dialogs, restore wizard wiring | Gains heatmap, search, sync chip; list becomes DB-backed (phase 4) |
| `frontend/src/components/ArchivesList.tsx` (735 lines) | Paginated, grouped, filtered rows; persists `archives-list-*` keys in `localStorage` | Kept behind the list toggle |
| `frontend/src/components/ArchiveCard.tsx` | Row with MAN/SCH chip and four icon buttons | Kept for the list view |
| `frontend/src/components/ArchiveContentsDialog.tsx` and `ArchivePathSelector.tsx` (`getArchiveContents` at `:106`) | Modal folder browser, one request per folder via `frontend/src/services/borgApi/client.ts:154` | Reused inside the Files tab; dialog gains "Open full page" |
| `frontend/src/components/RestoreWizard.tsx`, `MountArchiveDialog.tsx`, `DeleteArchiveDialog.tsx` | Existing archive actions | Reused unchanged by the archive route |
| `frontend/src/pages/Activity.tsx`, `pages/activity/ActivityFilters.tsx`, `components/BackupJobsTable.tsx` | Activity page and table | Gain category and trigger filters and `RunChainRow` (phase 4) |
| `frontend/src/components/RepositoryCard.tsx` | Repository card | Gains `OperationStatusStrip` and Operations action (phase 3) |
| `frontend/src/pages/Settings.tsx` (`tabOrder`, `currentTabId` around `:103-132`) | Settings tab wiring | Gains `background-work` (phase 3) |
| `frontend/src/locales/{en,de,es,it}.json` | Translations | Every new key added to all four |
| `frontend/src/services/api.ts:682` | `/archives/{repo}/{archive}/contents` client | Unchanged; new clients added beside it |
| SSE consumer | No shared hook was found by searching for `EventSource` in `frontend/src`; verify before phase 3 and add `frontend/src/hooks/useOperationEvents.ts` if none exists | Phase 3 |

## Appendix B. Decisions and rejected alternatives

Recorded so later sessions do not re-derive or re-litigate them.

| Decision | Rejected alternative | Reason |
| --- | --- | --- |
| Store per-archive change deltas from `borg diff` at backup time | Compute diffs at view time | `borg diff` on demand takes minutes on large archives and needs the lock; stored deltas make diff, history, search, and anomalies a database read |
| Store deltas, not a full per-archive file index | Full listing per archive in SQLite | Tens of millions of rows for a normal install; the delta table gives every feature in scope except instant folder browsing, which stays on Borg plus the existing cache |
| Merge a pruned archive's rows into its successor | Rebuild the index after every prune | Rebuild costs one Borg call per surviving pair on every nightly prune; the merge is one SQL transaction and yields an honest history |
| One generic `operations` table with small extension tables | Keep one table per kind and add a queue table on the side | The twelve tables already share the same core columns; a queue on the side would be a thirteenth shape and Activity would stay nine queries |
| Migrate kinds in phases, backup last, with Activity unioning both worlds | Big-bang migration | Backup has thirty five columns, three creation sites, agents, retry lineage, and plan runs; a phased union keeps every release shippable |
| Category and trigger are separate axes | A "scheduled" category | A scheduled backup and a scheduled check are different work with the same trigger; Activity already models `type` and `triggered_by` separately |
| Background work is a separate tab, not part of Activity | One page with a live section | Activity is a read-only ledger; controls and lane state belong to a live view. Same table underneath |
| Foreground operations appear on the board as the lane holder | Board shows only index work | Without it the board cannot explain why a repository's index work is waiting |
| The board is repository-centric (a card moves across stage columns) | Immich-style per-job-type cards with counts | Per-type counts cannot answer "what is happening to my NAS repo right now" |
| Import stays synchronous through connect only | Fully asynchronous import | A wrong path or passphrase must fail the request; everything after connect is derived data |
| Breadcrumbs plus a details pane in the Files tab | Persistent folder tree on the left | A tree costs one Borg call per expanded node and adds little over breadcrumbs; Miller columns are a possible later toggle |
| Heatmap per series is the default Archives view, list behind a toggle | Keep the paginated list as the only view | The list cannot show gaps or anomalies; existing users keep the list via a persisted preference |
| Restore is non-exclusive | Restore takes the lane | Borg permits concurrent reads; blocking restores behind a backup would be a regression |
| Borg 1 series inferred from plan template prefix, then timestamp stripping, then `default` | Require users to define series | Inference covers the common cases; a manual override is a listed follow-up |
| Managed-agent repositories skip history until the agent gains `diff` | Block the feature on the agent protocol | The rest of the feature ships; the skip is visible and explained |
| Reconcile replaces the hourly stats scheduler rather than running beside it | Keep both | Two writers to the same columns with no coordination is the current bug |
| Codex is not used; all phases are implemented and reviewed by Claude models named in section 13 | Mixed vendors | Owner's decision |
| Hidden rows above the cap collapse to per-subtree summary rows | Drop rows silently or refuse to index | The user sees that truncation happened and where |
| History layer (diff, file history, search, outlier flags) is Pro under one key `archive_history`; browsing, heatmap, status strip, and the Background work tab stay Community | Gate everything new, or gate nothing | The insight layer is the value that justifies Pro; the operational layer fixes bugs every user has and must not be withheld |
| Community installs never create history stages, rather than creating and skipping them | Create the operation and mark it skipped with a reason | A permanently skipped column on the board reads as broken, not as locked |
| Phase 1 plan defaults accepted at G1 (2026-09-03): `index_workers` and `background_paused` are `SystemSettings` columns and only `INDEX_ARCHIVE_INFO_PER_RUN` is an env setting; only the Borg 1 server import route changes in phase 1; Activity shows operations rows to any authenticated user, matching legacy rows; `update_repository_stats` stays untouched apart from the import route; running-operation cancel is cooperative through `ctx.cancelled()` with no hard task cancel | The alternatives listed under the plan's Open questions | Owner approved the plan without changes |
| No subagents in the workflow; each step runs in the session the user opened, on the model the user selected, with the spec telling the user which model the step wants | Orchestrator dispatching subagents with model overrides | Owner's decision on cost; the gates and the progress table give the same control without a second context per step |
| Phase 2 plan defaults accepted at G1 (2026-09-04): the live `borg list` route moves from `GET /repositories/{id}/archives` to `/repositories/{id}/archives/live` (one `api.ts` line changes) so the spec 9.2 path serves the database; modified-file sizes are resolved from the last known size of the path in the series, with no new column, because `borg diff` reports only byte deltas; directories are not stored as change rows, links are stored without sizes; the status strip consults the legacy job tables through `legacy_status.py` until phases 5 to 8 migrate them (deleted in phase 9); `overdue` with no record is true; the spec 14 startup bootstrap is recorded on `SystemSettings.history_bootstrap_at` and runs once per install; `history_index_excludes` is editable through `PUT /repositories/{id}` with the settings UI left to phase 4; fixtures must be real Borg output or Task 3 stops at G4; tasks split Sonnet 5 (1-3, 7-12) and Fable 5.1 (4-6); search is case-insensitive `LIKE` | The alternatives listed under the plan's Open questions | Owner approved the plan without changes |
