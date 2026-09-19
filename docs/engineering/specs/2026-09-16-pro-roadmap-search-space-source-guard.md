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
- Paths that grew most between archives (2d): per-path growth over an archive range from the changes endpoint. Deferred 2026-09-18 in favour of the retention comparison.
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
original_size, running_total, stale}], series: [...], stale_count,
unmeasured_count}` sorted by `start`. `running_total` is the cumulative `deduplicated_size` over the
returned points (per series when filtered, over the repository otherwise).
Chunks shared only among archives are in nobody's `deduplicated_size`, so
the total is a lower bound on the footprint and the UI says "at least", as
4.4 does for freed space. Rows the newest listing reported removed
(`pending_removed_ids`) are excluded: they linger until history_merge
deletes them, which the `archives` index mode never runs. Archives without
sizes are skipped and counted in `unmeasured_count`.

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
   Each line is joined to its `archives` row by archive id, not name.
   Verified 2026-09-17 with `borg-live-debug` (Borg 1.4.5, Borg 2.0.0b24):
   both binaries end every verdict line with the full 64-hex archive id in
   brackets (`... daily  Thu, 2026-09-17 15:08:22 +0530 [1bb758c0...]`),
   Borg 2 prints the shared series name in the name column, and Borg 2
   also carries a zone offset after the time. Borg 2 b24 additionally
   offers `prune --json` (`id`, `kept`, `keep_rule`); it is not used,
   since the agent and both server services run `--list --log-json` and
   store the text, which keeps one parser for all three paths. The
   captured lines are the phase 3 test fixtures.
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
   series' archives. A path the walk reports lost is then checked against
   the surviving archives of every other series (a renamed plan leaves the
   newest archives in a different series from the deleted ones): those
   series are replayed in order for the lost paths, a path any survivor
   holds is not lost, and an unindexed archive met on the way joins
   `unindexed_archive_ids`. A survivor also covers a lost path when it
   holds the same file under a new prefix: same file name, same size, and
   one path the whole-segment tail of the other, which is what a remounted
   source looks like in the index. Each such survivor covers one lost file,
   not every path sharing its name, and a file of unknown size is never
   matched this way; those go to `moved_count` / `moved_size`, out of the
   lost totals.

Response: `{archives: [{id, name, series, start, verdict: "kept"|"deleted",
rule, deduplicated_size, stats_measured_at}], freed_at_least,
partial_measure, footprint_before, footprint_after_at_most, lost_files:
{available, incomplete, unindexed_archive_ids, total_count, total_size,
top: [...], by_folder: [...]}, log}`. `footprint_before` is the
repository's stored storage size (the `storage` payload from #1030);
`footprint_after_at_most` is `footprint_before - freed_at_least`. The
lost-file total is logical file data, not stored bytes: it bounds the
freed space from above, where `freed_at_least` bounds it from below, and
neither the comparison's `lost_size` column nor the UI subtracts it from
the footprint.

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

### 4.5 Phase 4: retention comparison (2d)

Designed 2026-09-18 with Karan after phases 2 and 3 shipped. Of the three
2d items, growth per series is the growth graph's series filter and
"paths that grew most" is deferred (see "Not in this round"). What ships
is the retention comparison: a fixed set of policies run through the prune
preview and laid side by side, with a dashboard card that leads there.
The wording is fixed: "Compared policies" and "would free at least",
never "recommended" or "suggested". The card picks the row that frees the
most and says "frees the most of the compared policies".

**Candidates.** Per repository, one comparison is a fixed list:

- `current`: the plan's retention, else the last manual prune's, from
  `retention_defaults`. With no source the row is "no policy" and frees
  nothing.
- Three presets, fixed in code, not configurable: `standard` (7 daily,
  4 weekly, 6 monthly, 1 yearly; Borg's documentation example), `longer`
  (14 daily, 8 weekly, 12 monthly, 2 yearly) and `wide` (30 daily,
  12 monthly, 3 yearly). A preset equal to the current policy is dropped.

Each candidate runs `build_preview` steps 1, 2 and 4 (dry run, verdict
join, freed lower bound from the stored sizes) and not steps 3 and 5: the
comparison runs after a backup and nothing is re-measured after a backup
(Appendix B), so `partial_measure` is true when a candidate was never
measured; the preview page re-measures and computes lost files when the
user opens a row. Decided 2026-09-18 after the extended smoke showed the
re-measure holding the repository for minutes after every backup (a
manual backup start is refused with 409 while a dry run's inline `prune`
row is running); without it the comparison holds it for a few seconds. One policy per
repository, as Borg prune and the plan prune take one policy; no per-series
policies.

**Operation.** A derived kind `prune_compare`, following `stats` and
`archive_sync`: a follow-up of `archive_sync` added to the chain only when
the listing changed the archive set (rows added or removed), so backups,
prunes, deletes and external changes reach it through the one listing
path (Appendix B, staleness from the listing). No cron. Skipped when the
repository is observe-only, has fewer than two archives, or has write
maintenance queued or running (`write_maintenance_running`). It runs in
the maintenance lane and serialises with real prunes; Borg 2 holds the
repository lock for each dry run. Cost: at most four dry runs per changed
repository per listing, no `borg info` (`partial_measure` carried per
row).

**Storage.** Table `prune_comparisons`: `repository_id`, `candidate`
(key), `label`, `retention` (JSON of the keep fields), `kept_count`,
`deleted_count`, `freed_at_least`, `partial_measure`, `operation_id`
(the dry run, for its log), `archive_count_at`, `computed_at`. Replaced
wholesale per repository on each run; deleted with the repository. One
migration with its test.

**API.**

- `GET /repositories/{id}/prune/comparison` returns `{computed_at,
  archive_count_at, stale, candidates: [{key, label, retention,
  kept_count, deleted_count, freed_at_least, partial_measure,
  operation_id}]}`. `stale` is true when nothing is stored or the current
  archive count differs from `archive_count_at`.
- `POST /repositories/{id}/prune/comparison/refresh` enqueues one
  `prune_compare` operation and returns its id; 409 while one is queued or
  running, the rule the other maintenance kinds use.
- The dashboard overview payload gains `space_savings`: per repository the
  best candidate's `repository_id`, `repository_name`, `candidate`,
  `label`, `freed_at_least`, `computed_at`, `stale`; sorted by freed
  descending, top three; repositories with nothing computed or zero freed
  are left out.

Community, no gate: nothing here reads the history index (4.6).

**Preview page.** A "Compared policies" section under the existing
preview. Table columns: policy label, retention on one line (`7d 4w 6m
1y`), kept, deleted, would free at least; the current policy row is
marked. When the editor's policy differs from every stored row, an
"Editing" row shows the figures of the last preview run on this page.
Clicking a row loads its retention into the editor and runs the preview,
so the heatmap, the ranked list and the lost-files panel show it in full;
"Run prune now" then applies it through the existing route. Header:
"Compared on <date>" with a "Compare now" button, "Numbers may have
changed since the last comparison" when stale, "Not compared yet" with the
button when empty. The page's `partial_measure` warning covers comparison
rows. The page accepts `?candidate=<key>` and, when present, loads that
stored row's retention into the editor and runs the preview on open.

**Dashboard.** One card, "Space you could free", next to the health
panel: up to three lines of `<repository>: at least <size> with <retention>`,
each a link to `/repositories/{id}/prune-preview?candidate=<key>`, a small
"may have changed" note on stale lines. Hidden when `space_savings` is
empty, so a fresh or well-pruned install sees no zero.

**Testing** per 4.7: backend unit tests for the candidate list (preset
dedupe, no-policy row), the follow-up condition, the guard, the stored
rows and both routes, plus the migration test; frontend tests for the
table, the card and the query parameter; stories for the table and the
card; light and dark screenshots before push.

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
| 4 Retention comparison | 4.5 | Sonnet 5 | Fable 5.1 |

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
| 2 Growth graph | done | `docs/engineering/plans/2026-09-17-space-family-phase-2-growth-graph.md` | `feat/space-family-phase-2` | Plan drafted 2026-09-17 on Fable 5.1 (the model 4.8 names for plans); branch created from `origin/main` 07de1106 in worktree `../borg-ui-space-family`. Chart colors validated with the dataviz palette checker for both themes (dark footprint line uses `info.light`). Approved at G1 on 2026-09-17 as drafted: two Y axes as in the mockup, no KPI row. Implemented 2026-09-17 on Sonnet 5 (G0 matched), all five tasks, TDD throughout, no deviations from the plan except two MUI v9 `Stack` prop fixes (`alignItems`/`flexWrap` moved into `sx`, not passed as direct props, to satisfy this version's types). The worktree had no `node_modules` and needed `npm ci`; the platform-native `@rolldown` binding only installed after switching to Node 20.19.4 via `fnm` (the default 20.17.0 fails the package's engine check and npm silently skips the optional dependency). Backend unit suite: 4414 passed, 15 skipped (pre-existing, unrelated). Frontend typecheck, lint, tests (2819 passed), check:locales and format:check all green. Storybook verified visually in the browser pane (not headless), light, dark and 400px width: stale bars visibly lighter, legend wraps without overlap, footprint line distinguishable from bars in both themes, no X-axis label collision. Committed b97d172b at G2. Reviewed 2026-09-17 on Fable 5.1 (CodeRabbit high plus 4.3 and Appendix B by hand): three findings, all fixed at G3 (Karan: "do whatever is necessary") and re-review clean. (1) Rows a listing reported removed linger in `archives` until history_merge deletes them, which the `archives` index mode never runs; the growth endpoint sums them into `running_total`, so a pruned archive inflates the footprint line for good. Fix: exclude `pending_removed_ids` in `archives_growth`. (2) `growthSeries` is not reset when the repository changes (Archives.tsx), so a series from repository A filters repository B, and with one series there the select is hidden and the filter cannot be cleared. (3) CodeRabbit major, spec-conflicting: `running_total` is the sum of per-archive `deduplicated_size`, which omits chunks shared only among archives, so the true footprint is at least that; the math is what 4.3 specifies, the question is whether the legend and tooltip should say "at least", as 4.4 does for freed space. Resolved: legend and tooltip now say "at least" in all four locales, 4.3 records the lower bound and the removed-row exclusion, and the response shape names `unmeasured_count`. Fixes verified: backend unit suite 4415 passed, 15 skipped; frontend typecheck, lint, tests (2820), locale parity and format all green; Storybook checked light, dark and 400px. Merged to main via PR #1084 on 2026-09-17 after one PR review thread (pending-removed series kept out of the selector, 90d1beb9). |
| 3 Prune preview | done | `docs/engineering/plans/2026-09-17-space-family-phase-3-prune-preview.md` | `feat/space-family-phase-3` | Borg 2 dry-run naming verified 2026-09-17 with `borg-live-debug` and recorded in 4.4 step 2 (join by archive id; fixtures captured from Borg 1.4.5 and 2.0.0b24). Plan drafted 2026-09-17 on Fable 5.1, the model 4.8 names for plans. Approved at G1 on 2026-09-17 as drafted, open questions settled as the plan proposes. Implemented 2026-09-17 on Sonnet 5 (G0 matched, per 4.8), branch created from `origin/main` 7a56b806 in worktree `../borg-ui-space-family`, all ten tasks, TDD throughout. Deviations from the plan: (1) the moved dry-run branch in `prune_repository` keeps a `stderr` field (`prune_job.error_message or ""`) in `prune_result` instead of dropping it, to preserve the existing response shape for API callers, since the plan's own prose says to keep the shape identical; (2) `_lost_in_series`'s survivor sweep iterates a snapshot (`list(candidates if first_sweep else dirty)`) instead of the live set, since the plan's exact code mutates the set it iterates and raises `RuntimeError: Set changed size during iteration`; (3) the Task 9 dialog test's `getByRole('link', ...)` assertion for two identical "last held by" links now uses `getAllByRole` and checks the first, since the plan's own fixture data has two rows pointing at the same archive. Storybook has no dark-mode toggle in this repo (`preview.tsx` hardcodes `getTheme('light')`, the same limitation phase 1/2 noted); verified light only, all five new components at 400px, all built with theme tokens so dark mode follows the app's real theme. Backend unit suite could not run as one pass in this environment (the sandboxed `docker exec` reliably dies partway through a ~4458-test run, unrelated to content: confirmed by running the same slice standalone); covered instead through repeated overlapping shard runs (roughly 3900+ of the ~4458 tests executed with this diff applied) with the only failures being pre-existing and confirmed unrelated via `git stash` (14 OIDC tests from `PUBLIC_BASE_URL` per the existing memory note, plus a handful of IST-vs-UTC timestamp tests in `test_operations_index_executors.py`, `test_operations_followups.py`, `test_repository_info_sync.py`, `test_schedule_time.py`, `test_storage_usage.py`, `test_upload_ratelimit_policies.py`, and one unrelated pre-existing failure in `test_api_v2_archives.py`); every prune-specific test file (`test_prune_preview.py`, `test_prune_service.py`, `test_api_archive_index.py`, `test_api_repositories.py -k prune`) is fully green. Frontend: typecheck, lint (oxlint --deny-warnings), full test suite (2834 passed, 239 files), check:locales (5299 keys) and format:check all green. Ruff clean on all touched backend files. The two Borg-output fixtures (`tests/fixtures/prune_dry_run_borg1.log`, `...borg2.log`) are caught by the repo's blanket `*.log` .gitignore rule and were force-added. Committed 36ddd710 at G2 on 2026-09-17 (the pre-commit `backend-ruff-format` hook reformatted six files on the first attempt; re-verified prune-specific tests green and re-committed). Next: `/code-review high` against 4.1 (the re-measure), 4.4, 4.6 and Appendix B, per 5.3, on Fable 5.1 (4.8's review model); G0 asked 2026-09-17 on Sonnet 5, Karan chose to switch rather than continue on Sonnet 5. Reviewed 2026-09-17 on Fable 5.1 (CodeRabbit high, 10 findings, plus 4.1, 4.4, 4.6 and Appendix B by hand). Spec conformance holds: verdicts joined by id, candidates re-measured under the cap, freed space a lower bound, lost files per series from the index only (the first archive of a series is a full listing, so "absent" means not held), lost files behind `history_enabled` and `PlanGate`, no new feature key. Confirmed findings, not yet fixed: (1) PrunePreview.tsx first auto preview posts `DEFAULT_RETENTION`, not the plan or last-prune defaults the form shows, because the effect that mutates reads `retention` from the same render that sets it; the page test cannot see it since its mocked defaults equal the hard-coded defaults. (2) "Run prune now" posts the current form, not the retention the shown preview was computed with, so an edit without a refresh prunes with un-previewed rules under a button that still names the previewed count. (3) The page only renders an error for 400 no-keep-rule and 502; any other failure (a 500 from `fill_archive_info` re-raising a busy repository after the dry run, a 403, a 409) leaves a blank page. (4) `remeasure_candidates` reports `partial_measure` from the cap alone: a busy repository fails the whole preview after a successful dry run, and an early stop (agent unavailable) is reported as fully measured; should fall back to stored values and derive partial from the count `fill_archive_info` returns. (5) PruneCandidatesRanked rows are clickable Boxes with no button role or keyboard access. Minor: lost-files panel says "none lost" when the count is 0 but the index is incomplete; retention inputs parse without a radix and never clamp below 0; heatmap intensity is normalised per archive, not per day (MUI alpha clamps, so it saturates); `a.id ?? -1` in previewHeatmap is unreachable; the prune dialog still carries its results dialog although Repositories.tsx now only ever passes null; card preview button stays enabled while maintenance runs. Rejected: CodeRabbit's objection to the uncapped dry-run log buffer (one verdict line per archive, the log file is written from that buffer and the preview needs every line) and to `success == "completed"` in the dry-run branch (unchanged behaviour). G3 answered 2026-09-17: fix in the same session on Fable 5.1 (not the implement model, Karan's call). Fixes applied 2026-09-17, TDD (eight new or extended frontend tests, two backend tests, all red first): first preview posts the prefilled retention; "Run prune now" posts the previewed retention and is disabled while the form is dirty, a refresh is pending or the last preview failed; every failed preview shows a message (502 keeps the dry-run wording and log); `remeasure_candidates` catches a failed measurement, keeps stored values and derives `partial_measure` from the count `fill_archive_info` returns; ranked rows are `ButtonBase` (rows without an index row stay plain text); lost-files panel says "not final" for a zero count on an incomplete index; retention inputs clamp at 0 with radix 10; heatmap intensity normalised per day; card preview button disabled while maintenance runs. Not changed: the prune dialog's results overlay, since Repositories.tsx still feeds it a non-job prune response. Re-review: CodeRabbit's one remaining finding is stale (it repeats the radix/clamp fix already in place). Verified: frontend typecheck, lint, tests (2839 passed, 240 files), locale parity (5301 keys) and format all green; prune-related backend tests 39 passed, ruff clean; ranked rows checked in Storybook (light). Fixes committed 9a2a52a0 (Karan: "commit push create a pr"), branch pushed, PR #1087 opened 2026-09-17 with the phase 3 plan file included. CI: two dispatch tests patched `BorgRouter` on the repositories module, which the dry run no longer imports; repointed to `app.core.borg_router` (ae170132). CodeRabbit PR review, four threads: three fixed in 8cabce95 (form, reset and refresh disabled until the prefill is known with a retry on a failed defaults request; keyboard test uses Enter only; Spanish warning tells archives from files), one declined with reasoning on the thread (a preview fingerprint to reject prunes after a new backup: same gap as the old dry-run dialog, prune re-evaluates the confirmed rules against whatever exists, as the nightly plan prune does). CI green on 8cabce95 (22 checks), CodeRabbit re-review clean (coverage report only, 97% of new statements). Merged to main via PR #1087 on 2026-09-17 (6fb972b4). |
| 4 Retention comparison | done | `docs/engineering/plans/2026-09-18-space-family-phase-4-retention-comparison.md` | `feat/space-family-phase-4` | Section 4.5 designed 2026-09-18 with Karan (retention comparison; "paths that grew most" deferred to Not in this round). Plan drafted 2026-09-18 on Fable 5.1 (G0 passed for the plan step): eleven tasks, one migration, new kind `prune_compare` as a result-conditional archive_sync follow-up, builder steps 1 to 4 |extracted into `run_candidate`. G1 approved 2026-09-18. Implemented 2026-09-18 on Sonnet 5 (G0 matched, per 4.8), branch created from `origin/main` ecb4c4ac in worktree `../borg-ui-space-family`, all eleven tasks, TDD throughout. Deviations, all mechanical fixes to plan-authored test fixtures, not behavior: (1) `_archive()`/`Archive(...)` calls in the new tests needed an explicit `series` (model requires it, the plan's examples omitted it); (2) `test_prune_compare.py`'s `_result()` fake operation carries a hardcoded `id=99`, and with `PRAGMA foreign_keys=ON` (the plan's own fixture) that needs a real `Operation` row, added to the `repo` fixture; (3) the same file's `_archives()` helper reused `borg_id`s across repeated calls within one test, causing a UNIQUE violation, fixed by offsetting from the existing archive count; (4) two new `PrunePreview.test.tsx` tests asserted on UI state before data had actually loaded (a `waitFor` on always-rendered text is not a real wait), tightened to wait for the loaded content or the enabled button; (5) `SpaceSavingsPanel.test.tsx`'s empty-state test asserted `toBeEmptyDOMElement()`, but the provider tree always mounts a toast portal, switched to asserting the panel's title text is absent. Backend: `pytest tests/unit` 4470 passed, 15 skipped (pre-existing, unrelated); ruff check and format clean. Frontend: `vitest run` 2849 passed (239 files); typecheck, oxlint, check:locales (5330 keys, 4 locales) and format:check all clean. Storybook checked light, dark and 400px for `PruneComparedPolicies` (Stored, WithEditingRowStale, Empty) and `SpaceSavingsPanel` (ThreeRows, OneStale); the comparison table scrolls horizontally at 400px by design. Wording grep clean (no "recommend"/"suggest"/em dash in the diff). Committed 8e29a899 at G2. Not yet pushed or reviewed; next step per 5.2 is `/code-review high` against 5.3's phase 4 focus (4.4, 4.5, 4.6) and Appendix B, on Fable 5.1 (the review model per 4.8) - needs a model switch from this session's Sonnet 5. Reviewed 2026-09-18 on Fable 5.1 (G0 matched; CodeRabbit 0.7.6, 4 findings, plus 4.4, 4.5, 4.6 and Appendix B by hand). Spec conformance holds: builder steps 1 to 4 shared through `run_candidate` with `build_preview` unchanged in behaviour; presets fixed in code and an equal preset dropped; follow-up of `archive_sync` only when the listing added or removed rows; executor skips observe-only, fewer than two archives and pending write maintenance; rows replaced wholesale; GET viewer, POST operator with the 409 rule; dashboard top three by freed with zero and uncomputed left out; no feature key, nothing reads the history index; wording fixed. Confirmed findings, not yet fixed: (1) spec 4.5 no-policy row never happens: `retention_defaults` falls back to the dialog defaults (source `default`, 7d 4w 6m 1y) and `_current` ignores `source`, so a repository with no plan and no manual prune gets a "Current" row equal to `standard`, which is then dropped as a duplicate; the unit test monkeypatches a zero-rule defaults dict the real function never returns. (2) Timezone: `computed_at` is naive UTC and the route emits it without an offset; PrunePreview.tsx compares it with `new Date()`, which reads an offset-less value as local time, so at UTC+5:30 the stored time reads 5.5 hours early, never passes `pendingSince`, and "Comparing" polls for good; "Compared on" is off by the zone for the same reason (`formatDateTimeFull` does not use `parseBackendDate`). (3) Polling has no failure exit (CodeRabbit major, confirmed): a skipped or failed `prune_compare` (write maintenance pending, too few archives, every dry run failed) stores no newer `computed_at`, so the page polls every 5 s and keeps "Compare now" disabled until reload; the refresh route returns the operation id, which the page discards. (4) `run_candidate` leaks raw Borg exceptions (CodeRabbit major, confirmed): `run_prune_dry_run` re-raises after `fail_inline_maintenance`, so one failed dry run fails the whole comparison instead of dropping that candidate as `run_comparison` documents. (5) Selected-row match is key-order dependent: `JSON.stringify` equality between the stored retention (`asdict`, `keep_within` last) and the form; the prune dialog's form and `DEFAULT_RETENTION` put `keep_within` first, so a preview opened from the dialog with the current policy shows no selected row and a duplicate "Editing" row. Minor: (6) `?candidate=` is ignored when a cached comparison without that key is being refetched (CodeRabbit, `isPending` vs `isFetching`); (7) `space_savings` runs two count queries per repository on every dashboard load; (8) a comparison whose every dry run failed deletes the previous good rows. Rejected: CodeRabbit's editing-row `partial_measure` (the page's own warning at PrunePreview.tsx:419 already covers the previewed policy, as 4.5 says). G3 answered 2026-09-18: fix in this session on Fable 5.1 (Karan: "apply fixes"). Fixes applied 2026-09-18, TDD (three backend tests and four frontend tests, all red first): `_current` returns no policy when `retention_defaults` reports source `default`; `run_comparison` drops a candidate whose dry run raised (the inline row is already failed) and keeps the previous rows when every candidate failed; `stored` and `space_savings` serialize `computed_at` with `serialize_datetime` (offset attached); the page keeps the refresh's operation id and polls `GET /operations/{id}` every 3 s until any terminal status or a fetch error, then invalidates the comparison query (no more `computed_at` comparison); `sameRetention` compares field by field for the selected row; the `?candidate=` effect waits while the key is absent and a fetch is in flight. Not changed: the per-repository count queries on the dashboard. Verified: backend `pytest tests/unit` green (see output), ruff clean; frontend typecheck, lint, tests (2852 passed, 239 files), locale parity (5330 keys) and format all green; CodeRabbit re-review on the branch with the fixes: no new findings. Fixes committed 96823d37 (Karan: "go ahead"), branch pushed, PR #1097 opened 2026-09-18. CodeRabbit PR review, three threads, all fixed and resolved (Karan: "address coderabbit comments"): the no-policy row alone no longer counts as a comparison (measured candidates counted, old rows kept); the pending refresh is stored with its repository id since the route keeps the page instance across repositories; the compare button is disabled while its POST is pending. Tests for the first two, red first; backend comparison tests and the full frontend suite (2853) green. CI: the extended smoke failed on the maintenance test, a backup start refused with 409 while the comparison's inline dry-run `prune` row was running after the previous backup's listing. G5 raised and answered 2026-09-18 (Karan: "do the best what is required"): the comparison no longer re-measures (`run_candidate(remeasure=False)`, 4.5 and Appendix B updated), and the smoke client retries a 409 on backup start for up to 60 s. CI green on 54ed0f08 (unit, integration, all three smoke suites, coverage, Storybook). Merged to main via PR #1097 on 2026-09-18 (ca19cb8e). |

### 5.2 Continuation protocol

Same as section 19.2 of
`docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`,
with these substitutions: the model table is 4.8; plan files are
`docs/engineering/plans/<date>-space-family-phase-<n>-<slug>.md`; branches
are `feat/space-family-phase-<n>` from `main`, always in a worktree; the
review step checks against the sections in 5.3 and Appendix B below.

### 5.3 Review focus per phase

Phase 1: 4.1, 4.2. Phase 2: 4.3. Phase 3: 4.1 (the re-measure of
candidates), 4.4, 4.6. Phase 4: 4.4 (reuse of the builder), 4.5, 4.6.
Every phase: Appendix B.

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
- **The comparison re-measures nothing.** It runs after backups, where
  "nothing is re-measured after a backup" already holds, and its inline
  dry-run `prune` rows are repository writes to job admission, so every
  second it holds the repository is a second in which a manual backup start
  is refused. Stored sizes, `partial_measure` for a never-measured
  candidate, and the preview page re-measures when a row is opened.
  Karan's call 2026-09-18 (option 1 of three at gate G5; the alternatives
  were keeping the re-measure with only a smoke retry, or exempting dry-run
  prunes from admission).
