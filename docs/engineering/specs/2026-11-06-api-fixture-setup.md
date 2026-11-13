# Faster API fixture setup

## Evidence and goal

Successful PR run 42223069036 still takes about 12 minutes. Six unit partitions
have 322–447 seconds of testcase time. Existing historical balancing predicts
roughly 404 seconds per partition, so additional parallelism is not justified.

A local cProfile run of all 220 repository URL tests passed in 57.92 seconds.
It recorded 207 schema creations (9.17s), 206 drops (2.70s), and 123 real bcrypt
calls (21.55s). Optimize invariant fixture setup, preserving actual authentication.

## Required behavior

- Build one empty API SQLite schema from real Base.metadata per pytest process.
  Close/dispose the schema-building engine before copying its database file.
- Give each API test its own copied file, fresh engine/session and real SQLite
  foreign-key enforcement/WAL connections. No test writes reach the template,
  another test, or another process. Runtime engines still use NullPool.
- Close sessions and dispose engines at teardown; per-test files belong to
  pytest tmp_path. Avoid rebuilding and dropping the entire schema per API test.
- Keep real app startup/shutdown, service session-factory overrides, rollback,
  task cancellation/draining and runner lease cleanup unchanged.
- Extend the existing immutable fixed-password hash fixture to operator123,
  computed once at the unchanged production bcrypt cost. Rows remain per-test,
  and real correct/wrong password verification remains exercised. No production
  hashing, verification, random enrollment tokens, or agent authentication mocks.
- Leave non-API in-memory fixtures, migration/upgrade fixtures, all test selections,
  six shards, coverage thresholds, security scans and smoke/visual settings intact.
- Prove safety in fresh subprocesses: exactly one schema build and no schema drops
  across repeated API fixtures, complete empty schema, distinct files/sessions,
  enforced constraints, no committed/uncommitted/custom-table leakage, unchanged
  source template, and cleanup even when a test raises.
- Keep changes only if comparable before/after runs show useful improvement.
  Publish a new reviewable PR; no versions or generated artifacts committed.
