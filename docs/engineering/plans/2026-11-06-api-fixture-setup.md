# API Fixture Setup Implementation Plan

**Goal:** Remove repeated invariant fixture work without sharing mutable test state.
**Architecture:** One closed empty SQLite template per pytest process, copied to
unique tmp_path files; existing real ORM/session/lifespan behavior stays intact.
Reuse the existing immutable production-cost credential cache for operators.
**Tech Stack:** pytest, SQLAlchemy, SQLite, bcrypt.
**Spec:** docs/engineering/specs/2026-11-06-api-fixture-setup.md

## Global constraints

Keep all test selections, isolation, constraints, real lifecycle/authentication,
coverage gates and CI parallelism. No production code or version changes.

## Task 1: Reuse the fixed operator password hash

Files: tests/fixtures/database.py, operator_user in tests/fixtures/api.py,
tests/unit/test_fixture_passwords.py.

- [x] Extend the existing real subprocess probe with operator_user/operator123
  and expect exactly one production-cost hash for each fixed password. Run it
  first: existing operator setup should hash repeatedly and fail the call count.
- [x] Add operator123 to the immutable session fixture; operator_user reads it.
  Preserve role, per-test rows and actual password verification. Run password,
  authorization and operator-path tests; compare the relevant suite before/after.

## Task 2: Clone an empty schema into per-test API files

Files: tests/fixtures/api.py; new tests/unit/test_api_fixture_database.py.

- [x] Write a real subprocess probe using the API fixture plugin. Instrument
  create_all/drop_all while delegating to the real methods. Exercise at least
  three independent fixtures, committed and pending writes, an extra table,
  foreign-key rejection, and an exceptional exit. Assert unique files/sessions,
  complete empty schemas and one create/no drops. Run RED against current setup.
- [x] Add a session-scoped template fixture using tmp_path_factory, real
  Base.metadata.create_all and an engine disposed in finally. Copy the closed
  template to each test_db file before opening the normal engine; retain its
  WAL/foreign-key listeners and current overrides. Close/dispose normally without
  dropping schemas; pytest owns the unique temporary files.
- [x] Run the new probe and test_api_fixture_shutdown.py; verify the template is
  still empty and unchanged after all child test mutations/cleanup.
- [x] Repeat the complete 220-test repository URL suite using identical commands
  before/after, including cProfile and normal wall time. Check create/drop counts
  and unchanged real bcrypt work. Revert optimization if benefit is unproven.

## Task 3: Verify and publish

- [x] Review both changes for schema/data/lifecycle/authentication regressions.
- [x] Run all affected API tests and existing CI/shard/fixture/security guards;
  Ruff lint/format and diff checks. Broaden only if failures reveal a concern.
- [x] Update docs/testing.md and this plan with actual measured results and local
  limitations.
- [ ] Commit, push the codex branch and create/attach a PR from the repository
  template. Hosted CI remains authoritative for Linux/services.

## Execution decisions

Use the subagent-driven-development workflow for the two bounded tasks with
sequential ownership of tests/fixtures/api.py and independent review. The user
has authorized implementation and the existing PR workflow; no approval pause.

## Measured results

- Password regression RED: operator123 was hashed three times instead of once.
  GREEN: exactly one real bcrypt hash per viewer/admin/operator fixed password;
  12 child user cases verify correct/wrong passwords, cost 12, roles and fresh
  rows. Authorization trio passed 69 cases both times (15.38s before, 13.96s
  after); this single small timing comparison is not a hosted speed guarantee.
- Schema regression RED: five real API schema builds instead of one. GREEN:
  five independent databases, one build, zero drops, complete empty schemas,
  real WAL/foreign keys/NullPool and isolated pending/committed/custom-table
  mutations. The intentional exceptional child body is strict-xfailed, followed
  by another empty-database test. Source hash stays unchanged; engines have no
  open connections and are disposed before copies/after teardown as appropriate.
- Same 220-test URL suite, normal command: **48.84s -> 44.27s** (~9% improvement).
  cProfile command: **57.92s -> 46.61s**. Profiled schema create calls go from
  207 to 2 (one initial application schema plus one API template), drop calls
  from 206 to zero. Real bcrypt calls go from 123 to 124 (one additional cached
  operator hash up front); hash time remains 21.55s/21.79s. Authentication work
  was not stubbed or reduced in this benchmark.
- Independent spec/quality review found no actionable issues. Its fresh schema,
  lifecycle and password checks passed 5 tests in 9.34s. CodeRabbit CLI is signed
  out; the PR can receive its normal hosted review.
- Broader validation partitions the current unit inventory into whole affected
  files and a disjoint remainder, each balanced across six local processes.
  Local timings are evidence for correctness, not a prediction of hosted queues.

## Final verification

All 8,164 collected unit cases were executed exactly once across the affected
file group (4,419 cases) and its disjoint remainder (3,745). All 12 subprocesses
exited zero: **8,139 passed, 25 skipped**, zero failures/errors. Reconstructed
JUnit node IDs from every report and compared their Counter to a fresh full
collection; the union matches exactly with no duplicate or missing cases.
PostgreSQL-only cases remain local environment skips; hosted service-backed CI
retains its existing configuration. Ruff lint/format and diff checks pass.

No production modules, non-API database fixture setup, migrations, workflow test
selection, coverage thresholds, security gates, smoke variants, visual settings
or versions changed. Expected gain is bounded API setup savings; hosted total
completion time is not guaranteed by this local benchmark.
