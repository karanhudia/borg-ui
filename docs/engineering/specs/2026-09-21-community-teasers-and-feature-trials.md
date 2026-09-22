# Community teasers and per-feature trials

**Date:** 2026-09-21
**Status:** Scoped with Karan 2026-09-21, phase 1 in progress
**Why:** A Community user today meets `archive_history` as four dead ends: a
blurred mock on the changes tab, a greyed-out search box, a disabled file
history panel, and an upgrade prompt where the prune preview would say which
files are about to lose their last copy. None of them shows the user a single
fact about their own repository, so none of them makes the case for Pro. The
one in the prune preview is worse than unpersuasive: it withholds a data-loss
warning from the person standing in front of an irreversible action.

The change is one sentence: **Community sees the counts, Pro sees the rows.**
Every gate stops being an advertisement and starts being a number about the
user's own data, with the file-level answer behind the plan.

That requires the history index to exist on Community installs, which today it
does not.

## 1. The cut, surface by surface

The rule, applied everywhere: a count, a total or a date is Community. A list
of paths, a per-version history or a jump to an archive is Pro.

| Surface | Community sees | Pro adds |
| --- | --- | --- |
| Prune preview, lost files | "Pruning drops the last copy of 812 files (4.2 GB)", the `incomplete` warning, and the safety wording | The largest lost files, the per-folder chips, the path filter, the link to the archive that last held each file |
| Archive changes tab | The totals strip: added / modified / removed counts for this archive against its predecessor | The file list, the path and change-type filters, compare against an older archive of the series |
| Archive search | "47 files match, across 12 archives" plus the first 3 matching paths | The full result list, present-in-latest state, opening a result's archive |
| File history panel | One line for the selected file: version count, first seen, last seen | The version list with sizes, and restore from an older version |

Three of those four numbers are already computed by code that exists
(`_totals` in `archive_index.py`, `lost_files` in `prune_preview.py`,
`matching_paths` in the search route). The work is in shaping responses and in
replacing four locked states, not in new analysis.

### 1.2 Reading a Borg 2 archive

Found while testing the above, and fixed in the same branch: the whole
`/api/v2` surface carried `dependencies=[require_feature("borg_v2")]`, so a
Community install could not browse or download from an existing Borg 2
repository. The archive browser answered "This feature is not available on
your current plan" in place of the file tree, and the restore wizard had no
tree to pick from.

Borg 2 support stays the Pro feature. Getting your own files back does not:
a backup tool that refuses to hand them over because a plan lapsed has
stopped being a backup tool, and the people who hit it are exactly those
whose trial ended. Three routes are now open on every plan:

- `GET /{archive_id}/contents`
- `GET /download`
- `GET /download-folder`

`list`, `info`, the archive delete and its job status keep the gate, as do
`v2/backups.py` and `v2/repositories.py` in full, so creating Borg 2
repositories and backing up to them is unchanged. `info` and `list` were
considered and left gated: no screen calls `info`, and the archive list is
read from the ungated index.

The gate moved from the router to each route, which means a new route in
that module defaults to open. `test_only_the_read_routes_are_open_on_
community` pins the exact open set against the running app, so adding one
without a decision fails rather than shipping.

### 1.1 What does not change

- `archive_history` stays one feature key. No new keys, no per-surface plans.
- The file browser, restore, prune itself and the heatmap stay Community, as today.
- Enterprise is untouched.

## 2. Indexing on Community

`history_enabled(db)` is `plan >= Pro` (`followups.py:237`) and is read in two
different senses that this change has to separate:

- **May the index be built** (`chain_for`, `history_capability`,
  `reconcile_kinds`, the `history_index` executor's own guard,
  `enqueue.import_connect`). These become plan independent.
- **May the reader see the rows** (the routes in `archive_index.py`, the
  `lost_files` block in `prune_preview.py`). These keep the plan gate, now with
  the teaser carved out per section 1.

Decision, as built: `history_enabled` keeps its name and its meaning (the plan
includes `archive_history`) and stays the read gate. No replacement function is
added for the build path, because there is nothing left to ask: the build sites
simply stop calling it. `chain_for_repository`, `history_possible`,
`history_possible_for`, `enqueue_backup_followups`, `enqueue_reconcile_run` and
`enqueue_reconcile_runs` lose their `history` parameter, which existed only to
carry the plan answer past a savepoint.

`history_capability` keeps `plan_locked`, but only for readers. Its `history`
argument now means "this reader's plan includes the feature", the read routes
keep passing it, and the build path passes `history=True`. A repository that
cannot have history built still answers `agent_unsupported`, which is what the
chain builders act on.

`_on_plan_changed` in the licensing service is deleted. It existed to enqueue a
catch-up index when an install went Pro; with the index built on every plan
there is nothing to catch up.

### 2.1 Cost, and the opt-out that already exists

Every Community install that upgrades to this release starts indexing every
archive of every repository in `full` index mode, which is the default. That is
real CPU, real borg calls and real rows in `archive_changes`.

What bounds it, all of it already built:
- Per-repository `index_mode` (`full` / `archives` / `off`) is the user's
  switch, and `archives` or `off` stops history indexing without touching the
  rows already there.
- `index_history_seconds_per_run` (900s) bounds one run (#1103).
- `index_history_max_rows` (200000) bounds one archive's listing.
- `history_index_excludes` per repository.

Not built, and needed: the release note has to say this plainly, and the
repository settings need a line saying what `full` now costs on Community.

### 2.2 Existing installs

The index builds for existing Community installs on upgrade, through the normal
reconcile path, not only for repositories created afterwards. Anything else
would leave the teasers empty for exactly the users this is aimed at. The
budget above is what keeps that from being a thundering herd.

## 3. Per-feature trials

The mechanism exists end to end and needs no new gating code: a signed
entitlement carrying `feature_overrides` is applied by `_apply_entitlement`,
read by `get_feature_access`, and honoured by `usePlan` through
`system_info.feature_access`. A 14-day trial of one feature on a Community
install is an entitlement with `plan: "community"`, one override, and an
`expires_at`.

- **Contract (agreed 2026-09-21):** reuse `POST /v1/trials/activate` on the
  activation service with the existing payload plus
  `requested_feature: "archive_history"`. Same `denied` / `entitlement`
  response shape, same signature validation, so borg-ui parses nothing new.
  A server that does not know the field answers `denied` and the UI says the
  trial is unavailable.
- **borg-ui route:** `POST /api/system/licensing/feature-trial` with
  `{"feature": "<key>"}`, admin only, reusing `_post_activation`,
  `_validate_entitlement_document` and `_apply_entitlement`.
- **Summary fields:** `get_entitlement_summary` gains `trial_features`
  (feature plus `expires_at`, from the overrides of an active entitlement) and
  `expired_trial_features` (the same from an entitlement that has lapsed), so
  the UI can show a countdown and an end-of-trial state without new local state.
- **Policy lives on the server.** One trial per feature per instance, the
  length, and whether a new release re-opens one are the activation service's
  call, not a local ledger. This is self-hosted software: a local ledger is
  both more code and trivially editable.
- **14 days, not 7.** Value here appears on backup and prune cadence. A weekly
  plan plus a monthly prune shows a 7-day trial almost nothing.

### 3.1 UI

- `UpgradePrompt` gains a "Try free for 14 days" action when the feature has no
  trial recorded. A `denied` answer replaces it inline with the reason; nothing
  is pre-checked, so no extra round trip on every render.
- A countdown next to the plan badge while a feature trial is active: "Pro
  trial: archive history, 9 days left".
- When it lapses, the locked states return on their own (that is what the
  `get_feature_access` fix below guarantees) and the upgrade prompt says the
  trial ended rather than offering it again.

### 3.2 Prerequisite, already done

`get_feature_access` applied `payload_json.feature_overrides` regardless of
entitlement status, while `refresh_status_if_expired` only flips `status` and
`plan` and leaves `payload_json` in place. An expired feature trial would have
granted its feature for good. Fixed 2026-09-21 in `licensing_service.py`,
covered by `test_feature_override_stops_granting_once_expired`.

## 4. Phases

| Phase | Scope | Notes |
| --- | --- | --- |
| 1 Indexing for everyone | Section 2 | Backend only. No visible change on Community except that the index starts building. |
| 2 Free teasers | Section 1 | Response shaping plus the four locked states. Depends on phase 1 for data. |
| 3 Per-feature trials | Section 3 | Independent of 1 and 2, shippable alone. |

Phase 2 is the only one with UI. Storybook light and dark before push, per the
repo rule. All new copy lands in all four locales (en, de, es, it); a
half-translated screen is the failure mode, not the extra strings.

## 4.1 Progress

| Phase | Status | Notes |
| --- | --- | --- |
| 1 Indexing for everyone | done, not committed | `history_enabled` stays the read gate; the build path stops calling it (`chain_for_repository`, `history_possible`, `history_possible_for`, `enqueue_backup_followups`, `enqueue_reconcile_run(s)`, `reconcile_kinds` lose their `history` parameter, the `history_index` executor loses its `plan_locked` skip, and the `rebuild` route resolves its chain with `history=True`). `_on_plan_changed` deleted. |
| 2 Free teasers | done, not committed | `/changes`, `/history` and `/search` lose their `ARCHIVE_HISTORY` dependency and shape their own responses with `detail_locked`; `lost_files` is computed on every plan and stripped of `top` and `by_folder` for Community. Four locked states replaced: the lost-files panel keeps its count, the changes tab shows a totals strip, search runs with a match count, the file history panel shows a version count. `ArchiveChangesPreview` (the blurred mock) deleted. |
| 3 Per-feature trials | done, not committed | `request_feature_trial` posts `requested_feature` to `/v1/trials/activate`; `POST /api/system/licensing/feature-trial` (admin); `trial_features` and `expired_trial_features` on the entitlement summary; a "Try free for 14 days" action on `UpgradePrompt` at every lock, and a countdown on `PlanBadge`. The activation service does not implement `requested_feature` yet, so today every request comes back `denied` and the UI says the trial is unavailable. |

Verified 2026-09-21: backend unit suite, frontend typecheck, lint, 2878 tests,
locale parity (4 locales) and format all green. Storybook checked in light and
dark for the locked changes tab, lost-files panel and file history panel.

Not done, and needed before this ships: the release note about Community
installs starting to index (2.1), and a line in the repository settings saying
what `full` costs on Community.

## 5. Tests

- Phase 1: the chain builds the history stage on Community
  (`test_operations_followups.py`, `test_operations_reconcile.py`), the
  executor no longer skips with `plan_locked` (`test_history_index.py`), and
  the read routes still 403 on Community and still report `plan_locked` to the
  reader (`test_api_archive_index.py`, `test_api_operations.py`).
- Phase 2: one test per surface for both plans, asserting the teaser is present
  and the rows are absent on Community. Frontend: a test per locked state.
- Phase 3: trial activation applies the override, a denial leaves the plan
  alone, and the summary reports the countdown and the lapsed state.

## Appendix A. Decisions and rejected alternatives

- **Index on Community rather than on demand.** An on-demand one-shot index
  ("show me what I would lose", pay the cost once, at the moment of intent) was
  the cheaper option and was rejected 2026-09-21: it puts a cost warning in
  front of the exact moment the product should be proving itself, and it leaves
  the changes tab and search with nothing to show until the user opts in.
- **Counts free, rows Pro, rather than freeing a whole surface.** Freeing
  search outright removes the strongest reason to pay. Freeing none of it is
  the status quo that this spec exists to fix. The count is the hook, the rows
  are the tool.
- **The lost-file count is a safety number first.** Even if it converted
  nobody, it would move to Community: it is the last warning before an
  irreversible delete.
- **No local trial ledger.** Server-side policy only, see 3.
- **No per-surface feature keys.** `archive_history` stays one key; the teaser
  and the rows are one feature at two depths, and two keys would double the
  gating surface for no product gain.
