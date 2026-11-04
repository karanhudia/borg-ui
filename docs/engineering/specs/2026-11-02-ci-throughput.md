# CI throughput and safe parallelism

The approved follow-up addresses runner contention, repeated API teardown waits,
visual throughput, six backend shards, and isolated migration parallelism.

## Required behavior

- Preserve every test, coverage threshold, security gate, Borg smoke variant,
  screenshot, viewport, retry and readiness condition.
- Keep conservative PR routing and fail-closed summary behavior. Merge scope,
  runtime-image resolution, backend lint and Python frontend contract guards into
  the existing preparation runner so one queued runner serves these small tasks.
  Expose the same scope and image outputs; required contracts run for every PR.
- Upload backend Codecov data in the coverage-combination job and frontend data
  in its producing Vitest job, eliminating two extra queued runner allocations.
- Consolidate security scans and their summary into one runner while retaining
  separate mandatory scan steps, failure reporting, artifacts, SARIF publication,
  and existing non-PR Docker scan behavior/PR-only cancellation.
- Use six duration-balanced backend shards. Every collected file must occur in
  exactly one shard; all six reports are required before combining coverage.
- Use two migration shards partitioned by whole test files. Each runs on its own
  GitHub runner with its own Postgres service, database and temp directories.
  Both dialects and every migration/harness test remain selected across shards.
- Diagnose the five-second API teardown delays with a measured regression. Keep
  real cleanup and test isolation; avoid global mocks, shorter safety timeouts,
  or suppressing genuine background task failures. Prefer a narrow lifecycle
  correctness fix with explicit tests for stop/wake and cancellation behavior.
- Benchmark two versus four visual workers on identical immutable Storybook
  assets. Adopt four for CI only if throughput improves and screenshot inventory
  and output remain equivalent; preserve the configurable local default of two.
- No release/version changes, committed generated images, or production safety
  reductions. Real hosted queue and completion times require post-push evidence.
