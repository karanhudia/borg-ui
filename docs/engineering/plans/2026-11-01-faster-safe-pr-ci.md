# Faster Safe PR CI Implementation Plan

**Goal:** Reduce PR latency while preserving coverage and failing closed.

**Architecture:** A narrow classifier controls backend-only lanes; an executable
summary validates selected results. One timing manifest per run feeds all four
backend shards. A bounded browser worker pool captures all stories/viewports.

**Tech Stack:** GitHub Actions, Python/pytest, Node/Vitest, Playwright.

**Spec:** `docs/engineering/specs/2026-11-01-faster-safe-pr-ci.md`

## Global constraints

Preserve every security check, coverage threshold, smoke suite and Borg variant.
Unknown paths and shared configuration require full checks. Main, manual and
scheduled test runs remain full. No version bumps or generated PNG commits.

## Task 1: Conservative routing and summary

Files: `scripts/ci/pr_scope.py`, `scripts/ci/check_results.py`,
`tests/unit/test_ci_pr_scope.py`, `.github/workflows/tests.yml`.

- [x] Write tests for frontend-only classification, mixed/unknown/deleted paths,
  rename handling, and the summary rejecting unexpected skipped/failed jobs.
- [x] Run focused pytest and confirm missing behavior fails.
- [x] Implement GitHub-output classifier over a NUL-delimited git name-status diff;
  use literal allowlisted frontend directories only, unknowns imply full.
- [x] Wire a lightweight preparation job and guarded backend lanes. Smoke and
  frontend jobs remain unconditional. Summary consumes `toJSON(needs)` via env.
- [x] Re-run tests and validate workflow expressions with actionlint.

## Task 2: Duration-aware sharding and profiling

Files: `scripts/ci/select_pytest_shard.py`, timing reader/merger and associated
unit tests, `.github/workflows/tests.yml`.

- [x] Test duration weighting, conservative missing-data fallback, corrupt input,
  complete disjoint assignment, and setup/call/teardown JUnit totals.
- [x] Watch new tests fail, then implement measured file weights with test-count
  fallback calibrated from known seconds per test.
- [x] Restore history once in preparation and publish an immutable timing
  manifest. Generate JUnit and `--durations=50` reports from all backend suites.
- [x] Merge reports and save fresh history on successful main pushes only.
- [x] Verify with focused tests, shard coverage invariants, and actionlint.

## Task 3: Bounded visual capture

Files: frontend snapshot worker module/tests and capture script;
`.github/workflows/visual-snapshot-capture.yml`, `visual-regression.yml`.

- [x] Test complete exactly-once capture, bounded workers, invalid limits,
  cancellation/error propagation and worker teardown before browser shutdown.
- [x] Run tests red, add a small configurable worker pool, keep all capture
  semantics and serial mode for comparison.
- [x] Run Node tests and compare serial/parallel output using real Storybook.
- [x] Cancel obsolete PR capture runs; keep trusted report publication isolated.
  Avoid installing Chromium in report-only runs that consume PNG artifacts.

## Task 4: Small job cleanup and final proof

Files: `.github/workflows/security.yml`, `.github/workflows/tests.yml`, CI docs.

- [x] Add PR-scoped security concurrency, retaining scheduled/manual work.
- [x] Install only the requirements-pinned Ruff for backend lint; align coverage
  combine tooling with the pinned producer version. Remove unrelated Codecov
  dependencies without weakening required results.
- [x] Review slow-fixture evidence and retain isolation/hashing unless a measured
  optimization can be proven equivalent.
- [x] Finish the full fresh Storybook snapshot run and record its result.
- [x] Run actionlint, focused pytest, frontend script tests and lint/build. Review
  the complete diff for accidental bypasses and document verification results.

## Verification record

- 268 focused Python tests passed, including auth/security, routing, summary
  failure injection, fixture isolation, JUnit ingestion and shard invariants.
  Local auth tests use `PUBLIC_BASE_URL=http://testserver` to override the
  developer machine's configured URL; the initial 14 OIDC failures reproduced
  before implementation and disappeared with that setting.
- All 7,856 collected unit tests across 347 files form complete, disjoint four-way
  partitions both with cold history and with partial measured timing history.
- 77 frontend script tests and 7 Node worker tests passed. Production frontend and
  Storybook builds, frontend lint, changed-script Prettier, and Python Ruff
  lint/format passed. Existing build chunk warnings remain unchanged.
- Actionlint workflow/expression validation passed. Full ShellCheck reports the
  same pre-existing SC2012/SC2086/SC2129 diagnostics as the original workflows;
  no new structural or expression errors were introduced.
- An independent review found and verified a timing-output-directory fix, then
  found no further actionable issues in selection, mandatory contract/smoke
  jobs, timing-cache scope, shard consistency, or fixture credential caching.
- Real fixed-fixture hashing benchmark: 9 full-cost hashes in 1.637s before;
  2 full-cost hashes in 0.368s after. Production bcrypt and per-test database/user
  construction are unchanged.
- Full fresh Storybook capture passed: 625 stories, both viewports, all 1,250
  expected PNGs, exit 0, 378.63s, zero retries. Exact inventory checked against
  the built Storybook index; no missing or unexpected screenshots.
- Fresh original-serial vs 2-worker capture: 32.69s vs 19.35s for 30 stories across
  both viewports (about 41% less local capture time). All 60 PNGs were byte-for-byte
  and pixel-identical between modes and to the same subset of the full run.
  Both representative runs had zero retries. These local timings do not predict
  the exact hosted-runner improvement.
- No security-permission changes, version bumps, or generated PNGs are included.
  Hosted CI wall-clock speedups require a run after these changes are published.
