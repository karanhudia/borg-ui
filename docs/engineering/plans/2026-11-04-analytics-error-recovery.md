# Analytics Error Recovery Implementation Plan

> Execute using Superpowers test-driven development and task review. The user authorized implementation and PR publication.

**Goal:** Fix reproducible application defects from the 3 November error investigation and document remaining operational recovery.

**Architecture:** Keep repairs in the existing database upgrade, operation/session ownership and SSH tempfile helpers. Use the target database schema as the transfer authority and preserve rollback files. No speculative pool-size or DOM changes.

**Tech Stack:** Python, SQLAlchemy/Alembic, pytest; existing frontend diagnostic tests if investigation reaches the reporter.

**Spec:** `docs/engineering/specs/2026-11-04-analytics-error-recovery.md`.

## Global constraints

No version bump or new dependencies. Preserve data and existing operation contracts. Run red/green regression tests, affected suites, Ruff and whole-branch review before push. Preserve the original checkout.

### Task 1: Migration resilience

Files: `app/database/db_upgrade.py`, `tests/unit/test_db_upgrade.py`, `docs/troubleshooting.md`.

- [x] Reproduce source reflection failing on a foreign key to absent `users`, using real SQLite schemas. Prove both optional and required orphan handling on the target.
- [x] Reflect source columns without resolving foreign keys (`reflected.reflect(bind=source, resolve_fks=False)`); continue deriving FK semantics from the target. When a parent table is absent, classify all non-null references as orphans.
- [x] Reproduce interrupted schema initialization from the exact `agent_machines already exists` traceback. Recover only disposable staging databases; refuse unsafe repair of durable databases with clear recovery guidance rather than stamping unverified schemas.
- [x] Simulate ENOSPC during SQLite snapshot and prove original exception, source bytes, connection closure and staging cleanup. Make the smallest resource ownership fix.
- [x] Run migration/ensure-schema suites; document verified recovery and disk-space requirements.

### Task 2: Pool exhaustion investigation and repair

Files: operation runner/executors and matching tests, as narrowed by evidence.

- [x] Trace database session lifetime during long-running external operations and reproduce pool-slot retention with a small real QueuePool.
- [x] Release idle read transactions at the responsible ownership boundaries without losing loaded state, cancellation or terminal writes. Use regression proof for progress while work is blocked.
- [x] Run runner/executor suites; state clearly that this fixes a demonstrated exhaustion mechanism, not a proven cause for every observed timeout.

### Task 3: SSH secret tempfile cleanup

Files: `app/utils/ssh_utils.py`, `tests/unit/test_ssh_utils.py`.

- [x] Simulate write/close/chmod failures around real tempfiles; observe root failure masking and leftover files.
- [x] Transfer descriptor ownership once to the stream; close only still-owned descriptors and unlink the partial key on failure, preserving the primary exception.
- [x] Verify success mode 0600, contents, descriptor lifecycle, and failure cleanup.

### Task 4: Verification and publication

- [x] Investigate frontend render evidence; document any unresolved reproduction requirement rather than applying broad speculative DOM changes.
- [x] Review each task and the final diff, run relevant backend gates and unit suite; run frontend gates only if frontend files change.
- [ ] Commit, push `codex/analytics-error-recovery`, fill the repository PR template with exact validation and scope limits, create and attach the PR.

## Verification evidence

- Baseline migration/SSH suites: 38 passed, 3 PostgreSQL skips.
- Final focused suites: 44 migration/startup tests, 308 polling/runner/executor tests, and 21 SSH tests passed (373 total); 3 PostgreSQL-only tests skipped locally.
- Each changed behavior has failing-before/passing-after regression proof. Independent task reviews and whole-branch review approved the final fixes, including preflight-before-DDL preservation and combined write/close failures.
- Repository-wide Ruff lint/format and whitespace checks passed. Full backend unit-suite results are recorded in the PR after completion; installer/API tests run in the same disjoint file sharding used by CI.
- No frontend code changed. Release source-map investigation is recorded in the spec; the isolated render crash remains unresolved.

Full backend unit run: 8,020 passed, 25 skipped, one 100 ms cancellation timing failure under parallel load. The unchanged failing test file passed in isolation (18 tests), and the individual test passed again. This is recorded explicitly in the PR rather than reported as a clean full run. Final migration follow-ups passed the fresh 44-test suite after collection of the broad run.
