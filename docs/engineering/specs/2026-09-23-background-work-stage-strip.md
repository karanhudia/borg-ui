# Background work stage strip and per-stage pause

**Date:** 2026-09-23
**Status:** Design agreed with Karan 2026-09-23, not started
**Depends on:** the PR that folds `history_merge` into `archive_sync`. This
spec assumes it has merged; the stage map below has no `history_merge`.

**Why:** The Background work board shows three stage columns (Archives,
History, Stats), but the runner has more steps than that. Connect has no
column, the retention comparison (`prune_compare`) is not on the board at all
and shows up as a foreground "Compare retention running" line, and the wait
states live in small captions inside a cell. Every new stage costs a table
column, which does not scale. The only pause is global.

The change: one block per stage above the table, each with a live count of the
repositories currently in it. Clicking a block filters the table. Each block
can be paused on its own, the way Immich pauses a single job queue.

## 1. The stages

A repository moves through these stages in this order. Connect runs only on
import; import also runs Stats first, as the connection check. The strip
always shows the stages in this order regardless.

| Stage key | Label | Kinds | Runs when | Pausable |
| --- | --- | --- | --- | --- |
| `connect` | Connect | `import_connect` | Import only | No: a synchronous request, nothing is ever queued |
| `archives` | Archive list | `archive_sync` | After backup, prune, delete, wipe; import; reconcile | Yes |
| `retention` | Retention preview | `prune_compare` | After a listing that changed the archive set; the prune preview page (Compare now, or on open when missing or stale) | Yes |
| `history` | File history | `history_index` | After backup; import; reconcile. Absent for repositories that cannot build history | Yes |
| `stats` | Stats | `stats` | End of most chains; first on import; reconcile | Yes |

Wait states before a stage starts are not stages. They are the reason a
queued stage has not started and are shown on the row and counted as
"waiting" on the block: paused, waiting on a paused stage, blocked by a
foreground job (backup, prune, check...), waiting for an index worker, queued.

`prune_compare` keeps its `maintenance` category. Changing it to `index`
would hide manual comparisons from the Activity timeline (`activity.py`
filters non-follow-up index runs), count comparisons as index freshness in
reconcile and `repository_status`, and make the repository cards read them as
sync progress. The stage is a mapping of kinds, not a category.

## 2. Backend

### 2.1 Stage map

`app/services/operations/vocab.py` gains the single source of truth:

```python
STAGES: dict[str, tuple[str, ...]] = {
    "archives": ("archive_sync",),
    "retention": ("prune_compare",),
    "history": ("history_index",),
    "stats": ("stats",),
}
STAGE_FOR_KIND = {kind: stage for stage, kinds in STAGES.items() for kind in kinds}
```

Only pausable stages are in it. `connect` is a frontend-only stage.
`frontend/src/types/operations.ts` mirrors the keys as `PausableStage`, the
same way it mirrors kinds today.

### 2.2 `paused_stages` replaces `background_paused`

- `SystemSettings.paused_stages`: JSON list of stage keys, default `[]`.
- Migration: add the column; set it to every key of `STAGES` where
  `background_paused` is true; drop `background_paused`. Downgrade restores
  the boolean as true only when every stage is paused. Recompute alembic
  heads against fetched `origin/main` before writing it.
- `can_start` (`lanes.py`): the current check

  ```python
  if background_paused and op.trigger in ("followup", "reconcile"): return False
  ```

  becomes the same trigger rule scoped to the operation's stage:

  ```python
  if STAGE_FOR_KIND.get(op.kind) in paused_stages and op.trigger in ("followup", "reconcile"): return False
  ```

  Every kind a follow-up or reconcile can enqueue today is in `STAGES`, so
  "all stages paused" blocks exactly what `background_paused` blocked. Running
  work finishes; manual runs still go through, as today.

### 2.3 API

| Method | Path | Auth | Effect |
| --- | --- | --- | --- |
| POST | `/operations/stages/{stage}/pause` | admin | Add `stage` to `paused_stages`. 404 for a key not in `STAGES` |
| POST | `/operations/stages/{stage}/resume` | admin | Remove it and wake the runner |
| POST | `/operations/pause` | admin | Unchanged path; now sets every stage paused |
| POST | `/operations/resume` | admin | Unchanged path; now clears all and wakes the runner |

`GET /operations/queue` gains `paused_stages: string[]`. Its `paused` boolean
stays, derived as "every stage paused", so the tab's banner and any other
reader keep working.

## 3. Frontend

### 3.1 Stage model (`repositoryTrack.ts`)

- `StageKey` becomes `'connect' | 'archives' | 'retention' | 'history' | 'stats'`;
  `STAGE_FOR_KIND` adds `prune_compare: 'retention'` and loses `history_merge`.
- The foreground check skips kinds that have a stage, so a running comparison
  fills the Retention preview block and is not also shown as foreground. A
  real prune or check still is.
- `WaitReason`: `paused` now means "this stage is paused" (read from
  `paused_stages`). New `upstream_paused`: an operation this one depends on
  (walking `depends_on_id`, as the index-holder check already does) is queued
  in a paused stage. Order: `paused`, `upstream_paused`, `lane_busy`,
  `index_busy`, `workers`, `queued`.
- New `currentStage(track): StageState | null`: the running stage, else the
  first waiting one in stage order, else a failed one from the chosen run,
  else `null` (at rest). The strip and the row both read it.

### 3.2 Stage strip (`StageStrip.tsx`, new)

Placed between `HubSummary` and `HubToolbar`.

- One block per stage, always rendered. An empty stage is muted and reads
  "Idle", so every stage is visible even when nothing runs.
- Block content: stage label, count of repositories whose `currentStage` is
  this stage (large, tabular), and a line splitting it into running, waiting,
  failed. The system lane is not counted.
- Click toggles a filter. `HubToolbarState` gains `stage: StageKey | null`,
  applied in `applyToolbar` with search and attention; changing it resets the
  row window like the other toolbar fields. The selected block has the accent
  outline; no left accent borders.
- Pause: admins get an icon button per pausable block (pause or resume, with
  a tooltip naming the stage). A paused block shows a "Paused" chip; its
  waiting count keeps growing, which is the signal of what the pause holds
  back. Operators see the chip but no button.
- The index worker stepper moves from the History column header onto the File
  history block.
- Layout: `repeat(auto-fit, minmax(128px, 1fr))`, so blocks wrap on narrow
  screens instead of scrolling sideways.

### 3.3 Table

- New "Current stage" column right after the repository name. Running: stage
  label, progress bar, elapsed and `current/total` when known. Waiting: stage
  label and a pill with the wait reason. Failed: "Failed" and the retry
  action (the existing `handleRetry`). At rest: empty.
- The Archives, History and Stats columns stay as at-rest data only (sync
  state and archive count, history coverage, stats refreshed). Their headers
  no longer carry stage controls. A new stage adds a block, not a column.
- The shaded `StageTrack` band under active rows is removed, and
  `StageTrack.tsx` with it (the row is its only user). Per-stage detail stays
  in `RepositoryTrackDialog`.

### 3.4 Tab header

`BackgroundWorkTab`'s Pause button becomes "Pause all" (calls
`/operations/pause`). The warning banner shows only when every stage is
paused, with "Resume all". A partial pause is shown on the blocks alone.

## 4. Known limits

- The queue keeps finished operations for about a minute, so a failure leaves
  the block's failed count after that. It is still caught by the attention
  filter's existing chips. Keeping failures on the strip longer needs a
  backend change and is out of scope.
- Pausing does not stop a stage's manual runs (rebuild, Compare now), same as
  today's global pause.

## 5. Tests

Backend:
- `can_start` refuses a `followup`/`reconcile` op of a paused stage, admits
  one of an unpaused stage, admits a manual op of a paused stage.
- Stage pause and resume routes: admin only, 404 on unknown stage, resume
  wakes the runner; `/pause` and `/resume` set and clear every stage.
- Queue response carries `paused_stages` and the derived `paused`.
- Migration up and down with `background_paused` true and false.
- A `prune_compare` follow-up carries its parent's `run_id`.

Frontend:
- `repositoryTrack`: `prune_compare` maps to `retention` and is not
  foreground; `currentStage` precedence; `paused` and `upstream_paused`
  reasons.
- `hubRows`: the stage filter combined with search and attention.
- `PipelineBoard`: strip counts for a mixed queue, block click filters the
  table, pause button calls the stage route, stepper on the File history block.

Storybook: `StageStrip` stories for a backup wave, all idle, a failure, one
stage paused, and all paused; `RepositoryHubRow` story updated for the
Current stage cell in each state. Verify light and dark before pushing.

## 6. Docs

- `docs/navigation.md`, Background work row: stage blocks, per-stage pause,
  Pause all.
- `docs/configuration.md`: `background_paused` becomes `paused_stages`.
- i18n: new keys in every locale (stage labels, reasons, pause and resume
  tooltips, Pause all, Resume all). No partial localization.
