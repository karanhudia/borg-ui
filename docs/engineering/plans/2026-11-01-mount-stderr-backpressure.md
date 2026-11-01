# Mount stderr backpressure recovery plan

**Goal:** Prevent foreground Borg mount stderr from filling an unread pipe before mount readiness, without increasing its timeout.

**Evidence:** A child writing 2 MB of stderr cannot publish a readiness file until the pipe is drained. The mount readiness loop currently starts stderr=PIPE and reads only after process exit; waiting for exit can also block while unread bytes remain.

**Design:** Start a managed stderr drain immediately after spawning the foreground process. Retain bounded, redacted complete-line tail diagnostics and discard oversized lines rather than truncate a secret before redaction. Keep the managed process/drain referenced for its mounted lifetime. Stop and reap it on failure/cancellation/unmount; remove finished registrations. Preserve existing timeout, mount verification, FUSE classification, SSH host-key settings, and state format.

- [x] Write failing real-child regressions for readiness after large stderr, bounded/redacted exit diagnostics, cancellation cleanup, and active-mount unmount cleanup.
- [x] Confirm the failures, implement the narrow process owner and wire it into spawn/readiness/failure/unmount boundaries.
- [x] Update existing process fakes to emit actual EOF where needed, run mount/API suites and ruff, inspect lifecycle and commit without pushing.

## Verification and review repairs

- A real Python child writes 2 MB to stderr before publishing readiness; immediate drainage allows readiness and successful unmount/reaping. The original implementation failed the regression.
- Diagnostics retain at most 8,192 redacted characters. Oversized raw lines are omitted as a whole before bounding; private-key PEM blocks are suppressed across lines/chunks. Regression checks include a 20 KB secret line and split-chunk PEM body.
- Real-child tests cover mount cancellation, timeout diagnostics, shutdown cancellation with a child ignoring SIGTERM, natural exit, and read failure. Representative never-EOF tests require cancellation/await of the drainer even after shutdown deadlines.
- Independent review reproduced inherited stderr remaining open after the direct child exited. Fresh foreground mounts now own a new session; shutdown terminates that group even after its leader exits. Persisted mount PID fallback is unchanged. Exit diagnostics wait is bounded and original mount failures survive cleanup errors.
- Existing AsyncMock process fakes now emit EOF instead of returning an infinite stream of mock objects.
- Final focused/nearest gate: **83 passed, 2 existing planned-feature skips** across backpressure, mount service, mount process mocks, and mount API tests. Ruff and diff whitespace checks pass. Existing dependency deprecation warnings remain.

No timeout increase, version bump, host-key setting change, or missing-FUSE classification duplication.

## Review follow-up: real-child fixture timing

Two new cases delay the real child by 0.3 seconds; success and timeout-diagnostic checks both failed with the original two 0.05-second fixture sleeps. Simulated five-second mount polls now wait up to two real seconds for the child's readiness signal and drained diagnostic, rather than depending on process scheduling speed. Other patched sleeps retain short ordinary yields so cancellation and unmount coverage stay meaningful. All 13 backpressure cases pass, with Ruff lint/format and whitespace checks passing. Independent review found no issues.

## CI follow-up: path-confinement fixture

The first backend CI shard exposed six failures in a path-confinement fixture that creates an uninitialized service and an inert subprocess. Reproduced all six locally before changing the fixture. Mock the process owner in those path-allocation tests; their confinement assertions remain active and the dedicated real-child suite still exercises process ownership, stderr drainage and cleanup. Both suites pass 44 tests; all six mount unit suites pass 138 tests with two existing planned-feature skips. Ruff lint/format and whitespace checks pass. Independent review found no issues.
