# Pro roadmap: universal search, space family, empty-source guard

**Date:** 2026-09-16
**Status:** Agreed with Karan, not yet planned in detail
**Why:** Archive history and restore checks are the features users love. Both answer "what is in my backups and would they save me", which no competitor (borgmatic, Vorta, Zerobyte, Borg Backup Server, restic front-ends) builds on. These three continue that line. All reuse the archive index (`archives` table: nfiles, duration_seconds, original_size, compressed_size, deduplicated_size per archive) and the existing changes endpoint.

Karan's original note (Google Keep "Borg features"): universal search; per archive size; prune preview, files that will be lost; prune preview, contribution of each archive; how to save space. Items 2 to 5 are one feature family.

## 1. Universal search (Pro)

Filename search exists per repository (`GET /api/repositories/{id}/search?q=`, `archive_history` feature). Universal means:
- One search box across all repositories the user can see, results grouped by repository and series.
- Content peek for small text files: first lines extracted from the archive on demand.
- Later: across remote clients.

## 2. Space family (Pro), build in this order

### 2a. Archive view stats header
The archive detail view (opened from the heatmap and from the list view; shows the changes against the predecessor) gets a stats header:
- Added to the repository: deduplicated_size. Headline number.
- Files changed: added / modified / removed from the changes endpoint (already computed by `_totals`).
- Data backed up: original_size, with delta against the predecessor.
- Files (nfiles) and duration, each with delta against the predecessor.
- Compression ratio: compressed_size / original_size.
- "Measured at" timestamp (see caveat).

### 2b. Repository growth graph
One chart on the repository view, x = archive start:
- Bars: each archive's deduplicated_size (what that backup added).
- Line: running total of the bars (repository footprint over time).
- Optional line: original_size (source growth vs disk growth, "is dedup working").
- Filter by series when a repository holds several plans.

### 2c. Prune preview
Given a retention policy (the plan's current one or an edited one), before applying:
- Which archives would be deleted.
- Contribution of each archive (deduplicated_size), sorted, so the user sees the best bet for freeing space.
- Files that would be lost: files whose last surviving copy lives in a to-be-deleted archive. Needs the index complete for the window; reuse the `incomplete` / `unindexed_archive_ids` flag from the changes endpoint as a "preview incomplete" warning.
- Space actually freed, not the sum of deleted archives' deduplicated sizes (see caveat).

### 2d. How to save space
Summary tab over 2b and 2c: growth per series, paths that grew most between archives, suggested retention per plan.

### Caveat that shapes all of 2
deduplicated_size is relative to the archives that exist at listing time. Pruning an old archive moves its unique chunks to the neighbour, whose number then grows. So: refresh archive stats after prune, show "measured at", and compute prune preview's freed space from chunk-level data (borg prune --dry-run --list plus a stats refresh, or Borg 2 equivalents), never by summing per-archive deduplicated sizes.

## 3. Empty-source guard (Pro, possibly Community as trust)

Before a scheduled backup runs, refuse and alert if a source path:
- is empty,
- is not a mountpoint when it was one at plan creation (record `is_mountpoint` per source at save time),
- shrank by more than a threshold against the last indexed archive (nfiles or original_size).

Reason: unmounted NAS share or external disk, borg backs up an empty directory for months, prune deletes the real data. Most quotable failure story in this space. Per-source override to skip the guard. Nothing like this exists in app/ today (checked 2026-09-16: no mount guard, no source preflight).

## Not in this round (from the same discussion, keep for later)
- Missed-run catch-up (anacron-style) and silent-stagnation alert: strongest companions to the guard; "your schedule cannot fail silently" story.
- Unprotected-data finder, time scrubber, what-would-I-lose-now, restore drills with proof report, deleted-file recycle bin, mass-change guard, schedule advisor, quiet windows, pause with resume date.

---

## 4. Space family: detailed design

Agreed with Karan 2026-09-16 in the design conversation that produced this
section. Section 2 above is the outline; this section is what gets built.
Universal search (section 1) and the empty-source guard (section 3) are not
designed yet and get their own sections when they are.

Mockup of the three screens (example data, private artifact):
https://claude.ai/artifact/LsvMba2GFJLzgXytxZumbP

### 4.1 What the numbers mean, and which ones move

Borg reports four figures per archive. `original_size`, `compressed_size`
and `nfiles` describe the archive's own contents and never change after the
backup. `deduplicated_size` is the size of the chunks that only this
archive references, and it moves with the repository:

- Prune or delete of a neighbour: chunks the two shared become unique to the
  survivor. Its number grows.
- A new backup: chunks the new archive shares with an older one stop being
  unique to the older one. The older number shrinks.
- Compact: no change. It reclaims disk for chunks nothing references.

So the stored `deduplicated_size` is a measurement with a date, and the UI
must say when. Re-measuring every archive after every backup is out (365
daily archives means 365 `borg info` calls a day). The rule:

- `archives.stats_measured_at` records when `fill_archive_info` last wrote
  the four figures for that row. NULL means never measured or stale.
- A listing that observes removed archives (`run_archive_sync` with a
  non-empty `removed_ids`, which is every prune, delete and wipe, including
  ones run outside Borg UI) sets `stats_measured_at = NULL` on every
  surviving archive of that repository, before the same run's info fill.
- `archives_needing_info` selects `stats_measured_at IS NULL`, oldest first,
  under the existing per-run cap (`index_archive_info_per_run`, default 20),
  so survivors are re-measured by the loop that already exists, spread over
  the following runs. Values stay in place while stale; the UI shows them
  with a "re-measuring" state (`original_size` set, `stats_measured_at`
  null).
- After a backup nothing is marked stale. The header shows "measured
  <when>" and that is the honest answer.
- The prune preview (4.4) re-measures its deletion candidates synchronously
  before answering, so the freed-space figure is fresh at that moment.

The migration backfills `stats_measured_at = first_seen_at` for rows that
already carry sizes (the info fill runs in the listing run that creates the
row, so the two are within a run of each other); rows without sizes stay
NULL and are picked up as before.

### 4.2 Phase 1: stats freshness and the archive stats header (2a)

Data: the column and rule in 4.1. Alembic revision on head `f2a3b4c5d6e7`,
plain `add_column` / `drop_column` (a batch rebuild of `archives` on SQLite
cascades into `archive_changes`), with a migration test in the pattern of
`tests/unit/test_repository_index_mode_migration.py`.

API: `serialize_archive` adds `stats_measured_at`. `GET
/repositories/{id}/archives/{archive_id}` adds `predecessor_stats`, either
null or `{id, nfiles, original_size, deduplicated_size, duration_seconds}`
of `predecessor_of(archive)`, so the header draws deltas from one request.
No new endpoint.

Frontend: a new `ArchiveStatsHeader` component replaces the chip row in the
archive detail header (`frontend/src/pages/ArchiveDetail.tsx`). Tiles, in
this order:

1. Added to the repository: `deduplicated_size`, the headline. Sub-line:
   "measured <relative time>", or "re-measuring" when stale, or "not
   measured yet" when never measured.
2. Files changed: `+added −removed ~modified` from the changes totals the
   page already fetches (Pro, `archive_history`). On Community, or while the
   archive is not indexed, the tile says why in one line instead of numbers.
3. Data backed up: `original_size`, delta against the predecessor.
4. Files: `nfiles`, delta against the predecessor.
5. Duration: `duration_seconds`, delta against the predecessor.
6. Compression: `original_size / compressed_size` as a ratio ("1.5:1"), or
   "not reported by this Borg version" when `compressed_size` is null (Borg 2).

A delta is shown only when the predecessor has the figure. The series chip
stays. No plan gate on the header itself: Community sees these numbers
today. Storybook story with light and dark screenshots before push, per the
repository's UI rule.

### 4.3 Phase 2: repository growth graph (2b)

Ungated. Per repository, on the Archives page, as a third view next to
Heatmap and List.

API: `GET /repositories/{id}/archives/growth?series=` returns
`{points: [{archive_id, name, series, start, deduplicated_size,
original_size, running_total, stale}], series: [...], stale_count}` sorted
by `start`. `running_total` is the cumulative `deduplicated_size` over the
returned points (per series when filtered, over the repository otherwise).
Archives without sizes are skipped and counted in `unmeasured_count`.

UI: `ArchiveGrowthChart` (Recharts `ComposedChart`): bars for
`deduplicated_size`, line for `running_total`, a toggle that adds the
`original_size` line ("is dedup working"), a series `RichSelect` when the
repository has more than one series, stale points drawn lighter with a
legend note, click on a bar opens the archive. Empty state when fewer than
two measured archives.

### 4.4 Phase 3: prune preview (2c)

Community for the preview; "files lost forever" is Pro under the existing
`archive_history` key, since it is computed from the history index and is
meaningless without it.

API: `POST /repositories/{id}/prune/preview` with the retention fields of
the existing prune route (`keep_*`, `keep_within`). It:

1. Runs the existing inline dry run (`start_inline_maintenance` with
   `dry_run=True`, the path the prune route takes today).
2. Parses the `--list` output: `Would prune: <name>` and `Keeping archive
   (rule: <period> #<n>): <name>` (Borg 1.2+ and Borg 2 print the rule).
   Each name is joined to its `archives` row. Borg 2 series share a name;
   how its dry-run output identifies the archive (name, id, both) is
   verified with the `borg-live-debug` skill when phase 3 is planned, and
   recorded here.
3. Re-measures the deletion candidates (`fill_archive_info` on those rows,
   cap 50; beyond the cap the stored values are used and `partial_measure`
   is true).
4. Computes freed space as a lower bound: the sum of the candidates'
   `deduplicated_size`. Chunks shared only among deleted archives are in
   nobody's number, so the true figure is at least this. The response
   calls it `freed_at_least` and the UI says "at least".
5. Computes files lost forever (Pro), per series: candidates are paths with
   a `removed` change row in any archive of the series; a candidate is
   lost when, at every surviving archive of the series, its last change at
   or before that archive is `removed` or absent. Borg always keeps the
   newest archive when any keep rule matches, so a path never removed is
   never lost. The result carries `total_count`, `total_size` (from
   `size_before` of the removing row), the largest N (200) with the archive
   that last held each, and a per-top-level-folder rollup. `incomplete`
   and `unindexed_archive_ids` follow the changes endpoint's rule for the
   series' archives. Cross-series survival of the same path is not checked
   and the UI states this.

Response: `{archives: [{id, name, series, start, verdict: "kept"|"deleted",
rule, deduplicated_size, stats_measured_at}], freed_at_least,
partial_measure, footprint_before, footprint_after_at_most, lost_files:
{available, incomplete, unindexed_archive_ids, total_count, total_size,
top: [...], by_folder: [...]}, log}`. `footprint_before` is the
repository's stored storage size (the `storage` payload from #1030);
`footprint_after_at_most` is `footprint_before - freed_at_least`.

UI: a page, not a dialog: `/repositories/{id}/prune-preview`, reached from
the prune dialog's dry-run button (renamed "Preview") and from the
repository card. Layout: retention editor prefilled from the plan or the
last manual prune; the series heatmap re-used with a verdict per block
(kept green with the rule in the tooltip, deleted red, size-weighted
intensity), a numbers row (archives deleted, freed at least, footprint
before and after at most), deleted archives ranked by contribution with
bars, the lost-files panel behind `PlanGate` with the folder rollup and the
top list, warnings (index incomplete, partial measure, cross-series
limitation), the raw Borg log behind a disclosure, and "Run prune now" which
posts to the existing prune route with the same fields and then navigates
to the operation.

### 4.5 Phase 4: how to save space (2d)

Deferred. Designed after phases 2 and 3 ship, because "suggested retention"
needs real prune-preview usage to be honest. Not planned until this
section is written.

### 4.6 Plan gating

No new feature key. `archive_history` (Pro) gates the files-changed tile's
numbers and the lost-files panel, as it gates the history index they come
from. Everything else in this family is Community.

### 4.7 Testing

Backend: pytest unit tests in the existing files (`tests/unit/
test_operations_index_executors.py`, `tests/unit/test_api_archive_index.py`)
plus one migration test per migration. Prune output parsing uses fixtures
captured from real Borg 1.4 and Borg 2 through `borg-live-debug`. Frontend:
Vitest per component and page, a Storybook story per component, light and
dark screenshots before push.

### 4.8 Phases, models and reviewers

| Phase | Scope | Implement | Review |
| --- | --- | --- | --- |
| 1 Stats freshness and archive header | 4.1, 4.2 | Fable 5.1 (touches the index executor) | Fable 5.1 |
| 2 Growth graph | 4.3 | Sonnet 5 | Fable 5.1 |
| 3 Prune preview | 4.4 | Sonnet 5 (Fable 5.1 for the lost-files algorithm if the implementer asks) | Fable 5.1 |
| 4 How to save space | 4.5 | not planned | |

Plans are written on Fable 5.1.

## 5. Working this spec

This section is the only state the feature carries between sessions. Say
`/continue-spec` with this file's path in any session and the agent follows
5.2 from wherever the table in 5.1 says we are. No subagents.

### 5.1 Progress

Statuses: `not started`, `plan drafted`, `plan approved`, `in progress`,
`in review`, `done`, `blocked`.

| Phase | Status | Plan file | Branch | Notes |
| --- | --- | --- | --- | --- |
| 1 Stats freshness and archive header | done | `docs/engineering/plans/2026-09-16-space-family-phase-1-stats-header.md` | `feat/space-family-phase-1` | Plan drafted 2026-09-16 on Fable 5.1, the model 4.8 names; approved at G1 the same day; implemented on Fable 5.1 2026-09-16 in worktree `../borg-ui-space-family`, all seven tasks, TDD throughout. One deviation from the plan: staling survivors is keyed on removals the newest recorded listing did not already report (`pending_removed_ids`), because archive_sync never deletes rows and the `archives` index mode never runs the merge that would; without that guard every listing would re-stale the repository. Backend unit suite and frontend typecheck, lint, tests, locale parity and format all green; Storybook renders light only, dark checked by token reuse. Committed 9876ad88 at G2. Reviewed 2026-09-17 on Fable 5.1 (CodeRabbit high, plus 4.1, 4.2 and Appendix B by hand): two findings, both fixed in 28e8c207 (removed rows stay out of the stale reset; ratio for a zero-byte archive), re-review clean. Merged to main via PR #1080 on 2026-09-17 after the PR review (removed rows kept out of the info selector, no 0 B for a missing dedup size, doc corrections). Open wording question: headline label "Added to the repository" vs "Unique to this archive". |
| 2 Growth graph | not started | | `feat/space-family-phase-2` | |
| 3 Prune preview | not started | | `feat/space-family-phase-3` | Verify Borg 2 dry-run output naming with `borg-live-debug` before planning. |
| 4 How to save space | blocked | | | Design pending (4.5). |

### 5.2 Continuation protocol

Same as section 19.2 of
`docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`,
with these substitutions: the model table is 4.8; plan files are
`docs/engineering/plans/<date>-space-family-phase-<n>-<slug>.md`; branches
are `feat/space-family-phase-<n>` from `main`, always in a worktree; the
review step checks against the sections in 5.3 and Appendix B below.

### 5.3 Review focus per phase

Phase 1: 4.1, 4.2. Phase 2: 4.3. Phase 3: 4.1 (the re-measure of
candidates), 4.4, 4.6. Every phase: Appendix B.

### 5.4 Gates

Same as 19.4 of the operations spec: G0 model, G1 plan review, G2
verification and commit, G3 review findings, G4 blocked, G5 spec conflict.
Nothing is committed or pushed without the gate answer.

## Appendix B. Decisions and rejected alternatives

- **Freed space is a lower bound, not chunk-level math.** Borg 1.4 and Borg
  2 refuse `--stats` with `--dry-run`, and there is no CLI that reports the
  unique size of a set of archives. Chunk-level computation through
  `borg debug` commands was rejected: slow, version-specific, not available
  through agents. The sum of the candidates' fresh `deduplicated_size` is
  shown as "at least"; the exact figure is what the post-prune re-measure
  and the repository size measurement report.
- **Re-measure scope after a removal is the whole repository**, not the
  series, because chunks are shared across series. Cost is bounded by the
  existing per-run cap.
- **Nothing is re-measured after a backup.** The measurement date is shown
  instead. Re-measuring the predecessor only is a possible later refinement.
- **Staleness is detected from the listing**, not hooked into the prune,
  delete and wipe services, so an external prune stales the numbers too and
  there is one code path.
- **No new feature key.** The growth graph and the prune preview are
  Community; only history-derived parts are Pro under `archive_history`.
  Karan's call 2026-09-16.
- **Growth graph is per repository**, on the Archives page, ungated. An
  all-repositories overview is not in this round.
- **Lost files are computed per series from the history index only.** The
  UI states the cross-series limitation. Reading surviving archives from
  Borg to check was rejected on cost.
- **Prune preview is a page**, not a dialog, because the heatmap and the
  lost-files panel need the room. The existing dialog keeps its retention
  form and gains a "Preview" button that opens the page.
- **Phase 4 is deferred** until phases 2 and 3 have shipped.
