# Faster PR CI without reducing safety

Approved scope: parallel screenshot capture, duration-balanced backend shards,
test profiling, conservative PR routing, obsolete-run cancellation, and smaller
lint/coverage jobs. Existing checks, security gates, coverage thresholds, Borg
variants, and screenshot viewports remain intact.

## Safety boundaries

- Only PRs changing exclusively frontend source, Storybook, frontend scripts,
  or frontend public assets may omit backend-only lint, unit, integration, and
  migration jobs. Frontend dependency manifests, root/shared configuration,
  unknown paths, renames, missing/invalid diff metadata, and all non-PR events
  run everything. Backend changes continue to run frontend checks too.
- All smoke suites and both Borg variants run on every PR, including frontend
  changes. The existing scheduled core-smoke exception remains unchanged.
- Python tests that inspect frontend sources (Borg dispatch, URL-prefix parity,
  and security allowlist applicability) run in an always-required contract job.
  New cross-language invariants belong in this job as well as the unit suite.
- CI / Summary always runs and requires each selected job to succeed; only
  jobs explicitly excluded by the change classifier may be skipped. Classifier
  failures, cancellations, and accidental downstream skips fail the summary.
- Compare the complete PR merge-base diff, including both sides of renames.
  Never use a truncated file-list API response to decide that checks can skip.
- Historical durations change placement only. Every collected unit test file
  appears in exactly one shard, even with missing or corrupt timing history.
  Every shard consumes the same immutable per-run timing artifact.
- Save reusable timing history only on successful trusted main pushes. PR
  code must not write a timing cache used by other PRs.
- Screenshot concurrency is bounded and configurable, keeps each capture's
  isolated page/context, existing retries, readiness waits, names and images.
  Worker failures fail capture and remaining workers settle before teardown.

## Verification and rollout

Test classifier decisions and summary failures as executable behavior, including
unknown paths, deletions, renames, and failure injection. Test shard partition
invariants and timing ingestion; test bounded capture and error propagation.
Run actionlint, focused Python/Node tests, frontend build and local snapshots.
Record setup/call/teardown timing and JUnit reports for backend suites. Fixture
changes require profiling evidence; do not weaken database isolation or password
hashing to pursue speculative savings. Confirm real speedups with GitHub runs
after publication; local checks cannot establish hosted-runner performance.
