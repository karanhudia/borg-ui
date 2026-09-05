# Phase 4b: Operations UI redesign brief

> **For the implementing session:** run on **Fable 5.1** (owner's call,
> 2026-09-05). Same branch as phase 4 (`feat/operations-phase-4`), same PR.
> After this PR merges the Background work tab, the per-repository
> Operations view, the Archives page, and the archive route are final.
> **No subagents.** Follow `superpowers:brainstorming` for the design pass
> (present the new design in chat, get approval), then
> `superpowers:test-driven-development` for the build. Load
> `frontend-design` or `impeccable` for the visual pass. Update the
> phase 4 row of the spec progress table when done; record every decision
> below in Appendix B at G1.

**Spec:** `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`
**Phase 4 plan:** `docs/engineering/plans/2026-09-04-operations-phase-4-archive-experience.md`
**Phase 3 plan:** `docs/engineering/plans/2026-09-04-operations-phase-3-background-work-tab.md`

## Why this brief exists

The owner reviewed the phase 3 and phase 4 output on a real install on
2026-09-05 and rejected it on usability, not on correctness. All 2418
frontend tests pass, Storybook builds, and the API contract is untouched.
The problem is that the screens were built literally from the ASCII mocks
in spec section 10 and the result is not something a person can use.
The owner's words: the Background work tab is "unusable, I can't do
anything from here", the archives tab is "so damn broken", the browsing
experience is "so ugly", the pipeline is "barely anything I can
understand".

This brief lists what is wrong screen by screen, what must stay (API,
gating, tests that encode behaviour), and which spec decisions the owner
has re-opened. The implementing session owns the visual design. Do not
reproduce the ASCII mocks; they were a sketch of information, not a layout.

## Owner decisions on 2026-09-05 (record in Appendix B)

| Decision | Replaces | Reason |
| --- | --- | --- |
| The per-repository Operations view is a dedicated repository-scoped view with runs grouped by day and follow-ups nested under their parent, not the global Activity table with a pinned filter | Spec 10.5: "It is the same table, not a new component" | Landing on the global ledger with filter chips does not answer "what happened to this repository"; the mock in 10.5 shows grouping and nesting the table cannot do |
| Heatmap orientation and density are the implementer's call; the only requirement is that a year of nightly backups reads as a compact calendar with a visible time axis | Spec 10.3: "weeks as rows, days as columns" | Weeks as rows makes a year 52 rows tall with 14 px cells; the screenshot shows sparse dots separated by hundreds of pixels of nothing |
| The redesign ships in the phase 4 PR, not as a follow-on | The phase 4 branch going to G3 review as-is | The owner wants one merge that leaves the feature finished |

Everything else in Appendix B stays binding. In particular: the board is
repository-centric, Background work is a separate tab from Activity,
history is Pro under `archive_history`, browsing and heatmap stay
Community, no subagents.

## What must not change

- Every route in spec section 9 and the types in
  `frontend/src/types/operations.ts` and `frontend/src/types/archives.ts`.
  This is a frontend-only change.
- `PlanGate` on every Pro surface (spec 11.3): search field, Changes tab,
  file history panel, history rebuild option. Locked and unlocked stories
  for each.
- Keyboard behaviour in the Files tab (spec 10.6).
- `CategoryToken` as the single owner of category icon and colour.
- AGENTS.md UI rules: no left accent borders, `ResponsiveDialog` for
  dialogs, `RichSelect` for rich selects, every string through i18n with
  all four locales (en, de, es, it) in parity, a Storybook story per
  component, no em dashes anywhere.
- Tests that encode behaviour (gating, filtering, keyboard, data flow) are
  updated to the new markup, not deleted. Tests that only assert layout
  may go.

## Screen by screen

### 1. Background work tab

Files: `frontend/src/components/BackgroundWorkTab.tsx`,
`frontend/src/components/background-work/*`.

What the owner sees (screenshots, 2026-09-05):

- Empty state: a centred "Nothing is running" card, a "Pause" button, a
  "Rebuild..." menu, and a caption "Choose a repository from its card to
  rebuild." Nothing on the page leads anywhere. The caption tells the user
  to leave.
- Populated state: five column headers (Connect, Stats, Archives, History
  index, Ready) each with a count badge, three small grey cards reading
  "Remote Repo / waiting", "Remote Repo / Running for 2 sec", "Remote Repo
  / waiting", and a stray caption "workers: index 2" under one column.
  The same repository appears in three columns at once, which contradicts
  the "card moves across stages" model in Appendix B. There is no
  indication of what is waiting on what, no way to change the worker
  count, no link to the operation's log, and the `ForegroundLaneRow` is
  invisible when there is no foreground work so the user never learns
  what a lane is.

What it needs to do:

- Answer "what is Borg UI doing to my repositories right now" in one
  glance, per repository. One row or card per repository, showing the
  whole chain (connect, stats, archives, history index) as a single
  progress track with the current stage highlighted, elapsed time, and
  the reason when a stage is waiting (lane held by a foreground backup,
  worker limit reached, paused).
- Keep the existing `RepositoryTrackDialog` behaviour reachable from that
  row (per-stage timing, "Rebuild from").
- Put the controls where they act: worker count next to the stage it
  limits, pause as a clear global state with a banner when paused, retry
  on the failed stage.
- The empty state must say when the last reconcile ran and offer the
  rebuild action inline, not tell the user to go somewhere else.
- The board must be understandable with zero prior knowledge of lanes,
  stages, or workers. If a term needs a tooltip to make sense, the layout
  is wrong.

Whether stage columns survive is the implementer's call. The Appendix B
decision is "repository-centric", not "kanban".

### 2. Per-repository Operations view

Files: `frontend/src/pages/Activity.tsx`, `frontend/src/pages/activity/*`,
`frontend/src/components/activity/RunChainRow.tsx`,
`frontend/src/components/RepositoryCard*` (the Operations action).

What the owner sees: clicking "Operations" on a repository card opens the
global Activity page with the repository filter set. The page shows two
`Select`s ("All Types", "All Status"), a row of seven pale category chips
(Import, Backup, Restore, Maintenance, Index, Mirror, System) each with an
icon, and a "Trigger" `RichSelect`, above the global jobs table. The chips
are low-contrast, wrap awkwardly against the select, and the table columns
(Job ID, Repository, Type, Trigger, Status, Started, Duration, Actions)
repeat the repository on every row even though it is pinned.

What it needs to do (per the re-opened decision above):

- A repository-scoped view titled with the repository name, reached from
  the card's Operations action and from the Background work row. URL still
  carries `repository_id` so it is linkable.
- Runs grouped by day (Today, Yesterday, date), each run one line: status,
  category token, kind, trigger, size or archive delta, duration. Follow-up
  chain nested under the run, collapsed by default when all succeeded,
  expanded when any is running or failed. The 10.5 mock has the right
  content.
- Category filter as a segmented control or toggle group, not seven
  chips; trigger filter stays.
- Log and detail actions per run reuse the existing Activity dialogs.
- The global Activity page keeps its table. Category and trigger filters
  on the global page should use the same control the repository view uses
  so the two do not drift.

### 3. Archives page

Files: `frontend/src/pages/Archives.tsx`,
`frontend/src/components/archives/ArchiveSeriesHeatmap.tsx`,
`HeatmapLegend.tsx`, `SyncStateChip.tsx`, `ArchiveSearchField.tsx`.

What the owner sees: four stat cards, a "No recent restores" strip, then
a row with a "Sync is out of date" chip, a "Rebuild" link, a search field,
and a Heatmap/List toggle. Below, four series headings ("Downloads backup",
"Downloads-Backup-(Onsite-and-Offsite)", "Downloads-backup",
"manual-backup") each followed by a tall column of mostly empty space with
a handful of 14 px blue squares and a few orange-ringed ones. There is no
axis, no month labels, no legend near the cells, and the three
"Downloads" series are the same backup under three names.

Root causes in code:

- `buildWeeks` in `ArchiveSeriesHeatmap.tsx` renders one row per week from
  the first archive to the last with fixed 14 px cells and 4 px gaps. A
  series spanning May to September is 18 rows of mostly empty cells. A
  year is 52.
- The same function keys days by `date.toISOString().slice(0, 10)` (UTC)
  while `parseISO` returns local time, so cells shift a day for anyone
  east of UTC.
- Series inference (spec 6.6) splits on case and hyphen variants, so one
  plan yields three series. That is a phase 2 backend concern; the page
  must at least survive it visually (collapse tiny series, or show them
  as one group with a note) and the implementer should file the inference
  fix as a follow-up in the spec's section 16, not fix it here.

What it needs to do:

- A calendar people recognise: horizontal time axis with month labels,
  compact cells, one row (or a short band) per series, so ten series fit
  on a screen. Density and orientation are the implementer's call.
- Legend adjacent to the cells explaining count colour, anomaly ring,
  and missed-day marker.
- Hover shows date, count, size, duration. Click opens the archive route
  (existing `onSelectDay` contract).
- The sync state, search, and view toggle belong in one toolbar with
  clear grouping, not three unrelated items on a line.
- Stat cards and the restores strip can stay if they earn their space;
  if not, fold them into the toolbar.

### 4. Archive route

Files: `frontend/src/pages/ArchiveDetail.tsx`,
`frontend/src/components/archives/ArchiveFilesTab.tsx`,
`ArchiveFileDetailsPane.tsx`, `FileHistoryPanel.tsx`,
`ArchiveChangesTab.tsx`, `ArchiveInfoTab.tsx`.

What the owner sees on the Files tab: breadcrumb "Archive Browser /
Downloads Backup", archive name and timestamp, Restore/Mount/Delete
buttons top right, tabs, then a left column with its own heading
("Select files to restore"), its own subtitle, its own breadcrumb (Root >
local > Users > ...), a "1 item selected / Clear all" bar, the file list,
a helper caption, and a divider, then a footer "1 selected (0 B) [Restore
selection]". The right column repeats "Restore" and "Download" for the
selected file and shows "Size: 0 B" for a 9.4 KB file, then a History
list with two "Restore this" links. Four competing surfaces, three
restore buttons, two breadcrumbs, and the size is wrong.

What it needs to do:

- One header owns the archive identity and the archive-level actions.
- The Files tab has one breadcrumb (the path inside the archive), one
  list, one details pane, one footer. The wrapped `ArchivePathSelector`
  chrome (its heading, subtitle, helper caption) is suppressed or the
  selector gains a `variant="embedded"` prop.
- The details pane shows the selected file's real size and metadata
  (the 0 B bug: the pane reads a field the list row does not carry;
  trace it through `ArchiveFilesTab.tsx` and fix the data path).
- Restore lives in exactly two places: the footer for the selection, and
  "Restore this" in history for a specific archive. The per-file Restore
  and Download in the pane are the same action as the footer when one
  file is selected; keep Download, drop the duplicate Restore or make
  the footer the only restore.
- Changes tab and Info tab follow the same header and spacing so the
  three tabs feel like one page.

### 5. "Open full page" in `ArchiveContentsDialog`

File: `frontend/src/components/ArchiveContentsDialog.tsx` line ~170,
rendered through `StorageBrowserDialog`'s `titleAction` slot.

The link sits misaligned with the dialog title (baseline and vertical
centre do not match the title row). Fix the alignment in
`StorageBrowserDialog`'s title row so any `titleAction` aligns, and add a
story showing the slot populated.

## Definition of done

- Owner has approved the proposed design in chat before code is written
  (brainstorming gate).
- Every screen above is rebuilt; the owner walks through all five on a
  real install and accepts each.
- `npm run test`, `npm run lint`, `npm run typecheck`, Storybook build,
  and the four-locale parity check pass.
- Argos snapshots regenerated for changed stories.
- Spec progress table row for phase 4 updated; Appendix B carries the
  three decisions above; section 16 carries the series inference
  follow-up.
- Branch pushed; phase 4 PR ready for G3 on Opus 5.
