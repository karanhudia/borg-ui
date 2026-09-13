# Combined Lane and Index Fixes Implementation Plan

**Goal:** Replace #1023 and #1024 with one PR on current main, including their maintainer feedback.

**Architecture:** Preserve runner admission and recovery from #1024 and the holder payload from #1023. Derive wait reasons in `deriveTrack` from fetched flags and current operation rows; name only the supplied holder while it is running. Remove the copied exclusive-kind set and unnamed-lane state.

**Tech stack:** Python, SQLAlchemy, FastAPI, React, TypeScript, pytest, Vitest, Storybook.

**Spec:** `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`, sections 7.2 and 10.1, and maintainer comments on #1023 and #1024.

## Constraints

Preserve upstream #1027, the accumulated deferral backoff, access-scoped index query, and both original PRs' regression coverage. Keep both SSE busy flags fetched and interpret them in the track. Use existing components and all four locales.

## Steps

- [x] Apply both diffs and reconcile overlapping payload, fixture, locale, and test changes.
- [x] Change missing/completed-holder expectations to `queued` and prove they fail. Cover a valid server holder unknown locally and lane completion revealing index contention.
- [x] Replace `LANE_KINDS` with a holder ID/status check against current operations. Preserve precedence: paused, named holder, foreign index work, worker limit, queued. Remove `lane_busy_unnamed`; use queued wording for an incomplete named stage. Update stories.
- [x] Run affected backend tests, frontend tests, typecheck, lint, formatting, locale parity, and Storybook build. Render and inspect affected stories.
- [x] Review against both source diffs; no actionable findings.

## Verification

- Affected backend suites: 186 passed.
- Full frontend suite: 231 files, 2,725 tests passed with `NODE_OPTIONS=--no-experimental-webstorage` on Node 26.
- Ruff, frontend typecheck/lint/formatting, locale parity, and Storybook build passed.
- Four affected stories rendered at desktop and mobile sizes; local screenshots are not committed.

**Delivery:** Open the replacement PR in the fork after local review. Wait for CodeRabbit approval and green non-visual CI before opening the upstream replacement; the fork's protected visual-state branch causes an accepted Storybook publication failure. Then close #1023 and #1024 and the unmerged fork validation PR with references to the upstream replacement. Never merge the fork PR.

## Review round 1 corrections

- Checkpoint history merge deletions atomically with each outcome so retrying an abandoned operation cannot delete a replacement archive whose SQLite ID was reused. Regressions use the existing migration's non-AUTOINCREMENT schema.
- Refresh authoritative queue ownership when SSE reports an operation starting.
- Treat independent index branches within one run as contenders; exclude only actual dependency ancestors from the waiting reason.
- Verification: 168 targeted backend tests and all 2,729 frontend tests passed. Typecheck, lint, formatting, and Storybook build passed; the sibling-branch story was inspected at desktop and mobile sizes.

## Review round 2 corrections

- Preserve Borg archive identities in the listing result and verify them before merging history. This also protects unvisited targets when another chain overtakes a delayed merge; legacy ID-only targets wait for a fresh listing.
- Preserve newer completion and progress updates when a queue response arrives late.
- Verification: 172 targeted backend tests and all 2,730 frontend tests passed; typecheck and lint passed.
- Original #1024 side finding: startup recovery now shares the runtime retry budget and backoff. Seven startup regressions failed before the correction; 183 targeted backend tests pass afterward.

## Review round 3 corrections

- Cover parent-triggered queue requests and newer authoritative responses without replaying older buffered events onto them.
- Both event-order regressions failed before the correction; all 37 board and parent-tab tests pass afterward.

## Review round 4 corrections

- Coalesce events received during an active shared queue request into one follow-up fetch. Keep optimistic row updates only between requests, avoiding both event/response ordering guesses and starvation under continuous progress events.
- Strengthen the completion-race test with a completed replacement snapshot and a visible `done` stage assertion.
- The progress-burst regression failed with eleven requests before the correction and passes with one initial request and one follow-up; all 38 board and parent-tab tests, typecheck, and lint pass.

## Fork validation follow-ups

- Progress received during a fetch relies on that response instead of scheduling another fetch; only status events request the coalesced follow-up. A sustained-progress regression proves that progress during the follow-up cannot start a third request.
- Preserve accepted cancellation intent when a terminal database commit fails. Recovery must commit cancellation before dropping the request, preventing an unintended retry or dependant execution.
- Give both operations in the same-run serialization regression the same run ID.

- Fork full-review finding: bind removed archive targets to their last-seen observation as well as repository, database ID, and Borg ID. Advance the existing observation timestamp monotonically on every sighting, so a delayed or retried merge cannot delete an archive rediscovered by a newer listing. Legacy results without observation identities wait for another listing. Regression coverage includes first execution and interrupted replay, with advancing, frozen, and backward wall clocks.

## Upstream review correction

- Reproduce deletion and recreation with identical repository, SQLite ID, Borg ID, and captured timestamp, both before first execution and after partial replay. Both regressions fail before the fix.
- Add a persisted UUID generation to each archive row, carry it in removal targets, and require it at merge time. A nullable additive migration preserves existing rows; each listing initializes missing generations even for absent archives. Legacy results without all required identities wait for a new listing.
- Verify upgrade and downgrade preserve archive history, plus legacy-target, replay, queue, runner, and migration suites.
