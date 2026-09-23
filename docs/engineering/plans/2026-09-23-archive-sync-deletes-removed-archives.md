# archive_sync deletes removed archives (#1141)

## Problem

`archive_sync` reports archive rows the listing no longer saw and leaves them
in place; `history_merge` deletes them later. The `archives` index mode runs no
`history_merge`, so there the rows are never deleted: the archive list and the
heatmap show every archive the repository ever had, each with browse, restore,
mount and delete actions (#1141).

Even in `full` mode the delay between the two stages is why a set of readers
carries `pending_removed_ids` exclusions, and why the listing passes
borg ID, generation and last-seen identities to a later stage that has to
guard against SQLite reusing a row ID in between.

## Decision

Delete in the stage that finds the removal. `archive_sync` runs
`merge_removed_archive` (unchanged: fold, reset or drop, one transaction per
archive, spec 8.4) for each row its listing did not see, inside the run that
already holds the repository's metadata lane. `history_merge` leaves every
chain.

- Every index mode gets the same chain; `archives` needs no special case.
- A removed row never outlives the run that found it, so `pending_removed_ids`
  and the exclusions built on it go.
- A run that dies halfway leaves rows the next listing finds again, so the
  identity hand-off and the per-target checkpoint go with the stage.
- Rows left by the old behaviour (every `archives` repository today) are
  reported again by the next listing and deleted then. No migration.

## Scope

Backend:

1. `executors/index.py` `run_archive_sync`: after `apply_listing`, mark the
   neighbours of the removed rows stale (Borg 1, #1137), then fold and delete
   each removed row with `merge_removed_archive`. `reset_state` is `skipped`
   for an agent that cannot produce the change listing, as today. The result
   keeps `removed_archive_ids` (prune_compare trigger, prune evidence) and
   adds the fold outcome counts; the identity maps go. `newly_removed`,
   `exclude_ids` on the info fill and on the column write go.
2. `_neighbours_of_removed` loses its `gone_ids` argument (no lingering rows).
3. `apply_listing` stops seeding `generation_id` (only the merge read it);
   docstring and the `last_seen_at` comment updated. The column stays;
   dropping it is a follow-up migration.
4. `executors/history.py`: `run_history_merge` becomes a drain that returns
   `skipped` for rows queued before the upgrade (the next listing deletes
   their targets); `removed_archive_targets_from_dependency` and
   `_checkpoint_merge` go. `merge_removed_archive` keeps its `operation`-free
   form.
5. Chains: `followups.FOLLOWUPS`, `reconcile.RECONCILE_CHAIN`, the rebuild
   `archives` stage, `index_mode.MODE_KINDS` / `INDEX_KINDS`,
   `followups.HISTORY_KINDS` and its comment, `HISTORY_WRITE_KINDS`,
   `CANCELLABLE_WHILE_RUNNING`. The kind stays in `vocab` so old rows render.
6. Readers: `pending_removed_ids` and its callers in the growth route,
   `prune_preview` (two), `prune_compare`, `repository_status`.
7. Comments that describe the old gap: `repository_status` (`_current_archives`,
   storage summary), `repository_wipe_service`, `index_pending_kinds`,
   resync docstring, `frontend/src/pages/Archives.tsx`.

Unchanged on purpose: `repository_info_sync` still only reports removals (it
runs from an HTTP request without the metadata lane); the next listing deletes
them, and `_current_archives` already keeps those rows out of the sums.
The Background work board keeps mapping old `history_merge` rows to the
history stage.

Docs: spec sections 6.4 step 3, 6.8 table, 7.4, 7.5 and 8.4;
`docs/architecture/job-system.md` where it lists the chain.

## Tests (first, then code)

- `archive_sync` on a listing without an archive deletes its row in the same
  run, in `full` and `archives` mode, and the archive list and heatmap routes
  no longer return it and match `archive_count`.
- Fold outcomes through `archive_sync`: both indexed (folded), successor
  indexed only (reset, `pending` / agent without diff `skipped`), no
  successor (dropped).
- Rows lingering from the old behaviour are deleted by the next listing.
- Neighbour re-measure (#1137) still stales exactly the adjacent survivors.
- Chains for backup, prune, delete_archive, wipe, reconcile and rebuild carry
  no `history_merge` in any mode.
- A queued `history_merge` left from before the upgrade finishes `skipped`
  and frees its dependent `stats`.

Existing tests that assert the old chains, the identity maps or
`pending_removed_ids` are updated or deleted with the code they cover.

## Verification

Full unit suite (known: 14 OIDC failures in the main checkout come from its
`.env`, not this change), `ruff check`, `ruff format --check`, frontend lint
and the touched frontend tests.
