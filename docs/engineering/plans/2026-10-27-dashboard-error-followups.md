# Dashboard error follow-ups

**Goal:** Address the four confirmed findings from the dashboard investigation without changing repository data, app versions, or unrelated local work.

**Approach:** Keep bounded, redacted diagnostic context and its final exception; normalize Python memory addresses consistently in both reporters; resolve the server's background listing bypass setting through the existing resolver; classify HTTP 423 as expected in the analytics warehouse view.

## Acceptance and execution

- [x] Add failing backend tests for a long Borg diagnostic with a final exception, secret redaction, and delivery of long handled failures with inspectable diagnostic detail.
- [x] Bound the archive-listing diagnostic with head and tail context; attach long handled failure messages to the existing bounded analytics stack field. Preserve short-message behaviour and archive state on failures.
- [x] Add failing Python/TypeScript tests showing that changing only a `0x` memory address preserves the error identity; add the same normalization rule in both reporters.
- [x] Add failing listing tests using real routing and a mocked external Borg invocation for global, repository, and disabled bypass settings. Add an optional router override and resolve it through `_resolve_bypass_lock` for server background listings. Borg 2 must continue to omit the unsupported flag; agent payloads stay on their existing protocol.
- [x] In the separate analytics checkout, exercise the actual warehouse SQL against temporary tables with HTTP 423, 409, 500, and startup failures. Observe the 423 regression before adding it to the expected-status list.
- [x] Run affected backend suites, frontend reporter tests and checks, analytics tests/build, and the warehouse integration test. Review the final diff for bounded redaction, preserved failure state, and unrelated changes.

## Files

- `app/core/borg_errors.py`, `app/services/error_reporter.py`, `frontend/src/utils/errorReporting.ts`: diagnostics and error identity.
- `app/core/borg_router.py`, `app/services/operations/executors/index.py`: server background bypass propagation.
- `tests/unit/test_borg_errors.py`, `tests/unit/test_error_reporter.py`, `tests/unit/test_operations_index_executors.py`, `frontend/src/utils/__tests__/errorReporting.test.ts`: regression coverage.
- Analytics repository: `sql/views/13_v_errors.sql`, `test/error-view.it.test.ts`.

## Limits

This change does not break locks, repair repositories, disable Borg self-tests, alter scheduling concurrency, deploy services, or backfill fingerprints from incomplete historical messages. The affected installations' exit-2 root causes still require their complete operation logs. Warehouse integration uses temporary tables only.

## Verification

- Red phase: four backend regressions, frontend normalization, and actual warehouse HTTP 423 classification failed as expected before implementation.
- Green phase: 280 affected backend tests plus 180 Borg 2/redaction tests; 41 frontend error-reporting tests; 88 analytics collector tests; both BigQuery integration tests using temporary tables.
- Ruff lint/format, frontend typecheck/lint/format, analytics collector build, and diff whitespace checks pass.
- Optional broader analytics dashboard test run stalled without results and was stopped; no dashboard rendering code changed. CodeRabbit is signed out, so the diff was reviewed manually.
- No deployment, production-view mutation, repository repair, app-version bump, or historical fingerprint backfill was performed.

## PR validation on latest main

After applying the scoped patch over the merged structured-fingerprint fix, 464 affected backend tests and 45 frontend reporter tests pass. Full frontend locale parity, typecheck, lint, and production build pass; Ruff lint/format and diff whitespace checks pass.

## Review follow-up

URL userinfo in handled rclone failures is now redacted before deriving the analytics message, fingerprint, or long diagnostic detail. Six short/long plain, bare-token, and percent-encoded URL regressions failed before the fix; all 204 affected reporter, redaction, and archive-index tests pass afterward, with Ruff checks clean.

A second review identified bare Basic-auth values without an Authorization header. The backend scrubber now masks these before fingerprinting and transmission; two summary/detail regressions failed before the fix and all 206 affected tests pass afterward.

A further review caught valid four-character Basic-auth credentials (for example, the Base64 encoding of `a:b`). Removed the scrubber length threshold and extended both summary/detail regressions with a short credential. Both regressions failed first; all 206 affected tests and Ruff checks pass after the fix.
