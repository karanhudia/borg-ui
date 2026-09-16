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
