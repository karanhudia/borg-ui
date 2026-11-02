# CI Throughput Implementation Plan

**Goal:** Reduce queue hops and execution latency without excluding checks.
**Spec:** docs/engineering/specs/2026-11-02-ci-throughput.md
**Architecture:** Consolidate lightweight work onto existing runners, retain
explicit fail-closed validation, and parallelize complete independent workloads.
**Tech stack:** GitHub Actions, pytest, Playwright, Python and Node.

## Global constraints

All tests, coverage gates, security scans, Borg variants, screenshot viewports,
readiness checks, retries, and per-test/per-shard database isolation are retained.
No version bumps or generated PNGs. User has authorized implementation and PR.

## Task 1: Lifecycle delay investigation

- [x] Profile representative API activity tests with --durations and trace the
  teardown owner in app/main.py, operation runner, and scheduler lifecycle code.
- [x] Add a failing regression for the observed delay/correctness mechanism.
- [x] Implement the narrow fix; prove shutdown still waits for real work,
  cancellation cleans up tasks, and independent TestClient sessions stay isolated.
- [x] Run affected lifecycle and API suites and report measured before/after.

## Task 2: Migration and backend sharding proof

- [x] Add executable partition tests for the actual collected migration suite
  using scripts/ci/select_pytest_shard.py; run red before extending behavior if
  needed. Every collected file and node remains in the union exactly once.
- [x] Wire two migration jobs with separate services and six backend unit jobs.
  Require exact report counts before coverage combination; retain full suites.
- [x] Run focused shard tests, migration partition proof and available real DB
  migration checks. Hosted CI proves both service-backed migration shards.

## Task 3: Visual benchmark

- [x] Build one current Storybook and capture the full inventory with two and
  four workers on the same assets into separate ignored/temporary directories.
- [x] Compare names and pixels, retries and wall time. Preserve readiness/retry
  behavior; choose CI workers based on measured evidence and inspect differences.
- [x] Test capture pool and visual workflow wiring; commit no generated PNGs.

## Task 4: Runner consolidation and summary

- [x] Write regression tests for the consolidated job graph, mandatory checks,
  backend scope, missing/cancelled/failed jobs and exact shard artifacts.
- [x] Merge preparation, image resolution, backend lint and contract checks;
  move Codecov uploads to their producers and consolidate security scan steps.
- [x] Update summary and documentation to require all remaining selected jobs.
- [x] Run focused Python and Node tests, actionlint, Ruff, builds and visual proof;
  review the whole diff for bypasses, commit, push and create/attach the PR.

## Verification evidence

- The delay came from the shared test SQLite session retaining a write lock while
  real shutdown tried to release its runner lease. The fixture now rolls back
  before exiting TestClient; no production lifecycle changes or timeout changes.
- Regression failed before the fixture change and passes afterward, including
  an exceptional test body, real task cancellation/cleanup, lease release,
  preservation of committed rows, and rollback of pending rows.
- All 260 affected activity/lifecycle tests passed. The same activity suite went
  from 56.58s to 33.41s (116 tests); two representative teardowns went from about
  5.2s to 0.02–0.03s. These are local measurements under concurrent host load.
- 127 focused CI/lifecycle regressions passed. Actual collection proves every
  unit/migration node belongs to exactly one complete-file shard. Migration file
  weights ignore release parameter counts/history, so tags arriving between
  checkouts cannot change file assignments.
- Workflow syntax validation and Ruff pass. Frontend locale parity, typecheck,
  lint and production build pass; seven capture-pool tests and 19 visual tooling
  tests pass. Existing framework deprecations/build chunk warnings remain.
- Test workflow allocations decrease from 23 to 21 including expanded matrices;
  security allocations decrease from six to two (one on PRs). Coverage uploads
  stay on producing runners and all security work runs after previous failures,
  while cancellation can stop obsolete PR work.
- Independent review fixed failure/cancellation ordering and found no remaining
  test, coverage, smoke variant, or security bypass. Hosted queue/completion
  improvements still require a real PR run.

## Final validation

- Complete local unit run across all six count-balanced partitions before the
  final audit-hook regression: **7,934
  passed, 25 skipped** (7,959 collected), with every subprocess exiting zero.
  These local runs used Python 3.11; hosted CI uses Python 3.12 and services.
- Final path-stable migration partitions: **56 passed + 4 expected skips** and
  **77 passed**. Both JUnit inventories match all **137 collected node IDs**
  exactly once, including SQLite and PostgreSQL parameters. Four skips cover
  missing backup-plan tables in legacy v2.0.9/v2.1.0 releases. Separate temporary
  PostgreSQL 14 clusters were confirmed shut down; CI retains PostgreSQL 16.
- Full visual benchmark on unchanged 625-story assets: two workers **461.39s**,
  four workers **697.50s**, each **1,250 images**, zero retries, exact filenames,
  no missing/extra files. **1,216 images matched exactly; 34 differed** in small
  edges, lazy editor rendering/tokenization and copy feedback. Rechecking the
  31 affected stories at both viewports showed same-worker variability in 27
  cases and left residual differences. Changing concurrent host load confounds
  timing comparisons. Four workers do not have sufficient speed/equivalence
  evidence, so **CI and local default remain two**. Readiness and retries stay
  intact; no generated images are committed.
- PR: https://github.com/karanhudia/borg-ui/pull/1509. Initial hosted preparation,
  security, both migration shards, integration, and all six smoke variants have
  passed. Full hosted CI remains the final Linux/service/coverage proof.

- A final isolation review found that dependency lifecycle hooks could modify
  inputs to subsequent consolidated scans. Both audit-only npm installation
  commands now use `--ignore-scripts`. Offline tarball/root-hook regressions
  reproduced mutations of requirements, an allowlist, and the final gate before
  the fix, then verified all three stay unchanged while installation, lockfile
  validation and executable links remain functional. Audit commands and policies
  stay unchanged. Final-tip focused verification: **129 passed**, plus Ruff,
  workflow syntax validation and diff checks. Full unit execution was not
  repeated for this workflow-only delta; the two new cases passed directly.
