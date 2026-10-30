# Archive sync lock retries implementation plan

> Execute inline with the test-driven-development and verification-before-completion skills. The user authorized implementation and a PR.

**Goal:** Defer temporary server archive-listing contention through the existing bounded runner backoff and retain read-only diagnostics when it persists.

**Architecture:** Preserve the Borg result's contention classification on `ArchiveListingError`, let that exception reach the runner, and reuse its existing retry budget, cancellation and dependency semantics. Capture bounded lock-owner filenames only for local cache locks under the configured cache directory; never read remote paths or delete locks. Permission errors and lost-owned-lock failures remain terminal.

**Tech stack:** Python, asyncio, SQLAlchemy, pytest, Ruff.

**Requirements:** No version bump, migration, new dependency, automatic lock breaking, host-identity change, concurrency change, or frontend change. Keep existing work in the primary checkout untouched.

## Task 1: Server contention retries

- [x] Add failing runner tests using the real archive-sync executor and mocked Borg process results: timeout followed by successful listing; persistent timeout exhausting the budget; cancellation while deferred; permission denial and Borg 2's lost-owned-lock remaining terminal. Assert archive preservation, dependent job state, backoff, and error-report suppression during deferral.
- [x] Keep a strict contention flag on `ArchiveListingError` (modern 70/71/73 only, excluding `Our lock was killed by another borg`). Classify the raw diagnostic before truncation.
- [x] In `run_archive_sync`, rethrow contention; in `repository_busy`, recognize it alongside existing admission and agent failures. Preserve failure results for other listing errors.
- [x] Update the existing server-listing regression test to expect a retryable exception only for contention.

## Task 2: Bounded read-only diagnostics

- [x] Add failing tests with temporary cache directories and owner filenames. Exercise non-cache paths, symlinks, disappearing/unreadable locks, oversized owner lists, and secret redaction.
- [x] Add `app/services/borg_lock_diagnostics.py`: extract the reported timeout path, inspect only `<cache-root>/<64-hex-repository-id>/lock.exclusive`, and list at most five bounded owner entries. Include the application hostname and configured Borg host ID without asserting owner liveness. Handle filesystem failures as diagnostic status, never as operation failures.
- [x] Attach bounded redacted context and same-repository running operation IDs/kinds to the exception note and operation log; retain the note if the runner eventually exhausts retries.
- [x] Document the retry behavior, permission distinction, and diagnostics in `docs/troubleshooting.md`.

## Verification and PR

- [x] Observe the new tests fail for the missing behavior before production edits, then pass after implementation.
- [ ] Run affected error, executor, runner, diagnostics, and redaction suites; Ruff lint/format; and the backend unit gate. Review unrelated failures separately if host dependencies prevent a clean full run.
- [x] Review the diff manually. CodeRabbit CLI 0.8.0 is installed but signed out; no CodeRabbit review can be claimed.
- [ ] Commit only this branch's scoped changes, push, and create a PR using the repository template. Attach its URL to the current chat. Do not merge or deploy.
