# Dashboard error fixes implementation plan

**Goal:** Fix the empty dashboard schedule response and make archive-sync failures actionable without changing archive data on failure.

**Architecture:** Keep the existing best-effort listing API by default; opt archive sync into explicit listing failures. Preserve redacted, bounded failure details in the operation outcome. Classify background HTTP 4xx refusals as handled failures at the operations reporting boundary.

**Tech stack:** Python, FastAPI, Pydantic, SQLAlchemy, pytest.

## Constraints

- No version bumps, UI changes, compatibility-floor changes, or changes to archive retention.
- Never treat a failed listing as an empty repository.
- Never include raw credentials in stored listing diagnostics.
- Keep unhandled exceptions and HTTP 5xx failures reported as bugs.

## Steps

- [x] Add an API regression test for no scheduled jobs; observe HTTP 500, make `next_execution` optional, and verify HTTP 200 with an empty list and null next execution.
- [x] Add listing regression coverage for Borg 1, Borg 2, and agent results. Observe lost failure reasons; add an explicit listing exception and an opt-in `raise_on_error` keyword for `BorgRouter.list_archives_checked`. Archive sync catches only that expected failure and returns a failed outcome with its redacted stderr/exit code. Keep best-effort callers unchanged and verify stored archives/count/last-backup remain intact.
- [x] Add reporting regressions for background HTTP 400 and HTTP 500 failures. Treat only HTTP 4xx as handled operation failures, preserving the refusal reason. Keep HTTP 5xx and unexpected exceptions on the exception-reporting path.
- [x] Run the affected dashboard, router, index, runner, error reporter, archive-index and history-merge suites; inspect the final diff and formatting.

## Baseline

349 tests passed in `test_api_dashboard.py`, `test_operations_index_executors.py`, `test_borg_router.py`, `test_error_reporter.py`, and `test_operations_runner.py` before changes. Existing dependency/deprecation warnings and sandbox cache-write warnings were emitted.

## Verification

- The new empty-schedule, server/agent failure-reason, and HTTP 4xx classification regressions failed against the original code before implementation. The HTTP 500 control continued reporting an unhandled exception.
- Final run: 526 tests passed across the five baseline suites plus `test_borg_errors.py`, `test_history_merge.py`, and `test_api_archive_index.py`; 163 existing dependency/deprecation/OpenAPI warnings were emitted.
- Added cases cover Borg 1 and Borg 2, exit-code fallback, agent stderr, unchanged archive state, credential redaction, and bounded diagnostics.
- `ruff check --no-cache app tests`, `ruff format --no-cache --check app tests` (800 files), and `git diff --check` passed.
- Local diff review completed. CodeRabbit review was unavailable because its CLI is signed out.
- Deployment is still required before new reports expose the underlying causes of the existing archive-sync failures. These patches do not establish or repair those installation-specific causes.

## Review follow-up

The agent waiter raises HTTP 502 for a terminal failed job before returning a result. Map that path to `ArchiveListingError` only when the job is actually failed, using the existing failure-message extractor. Preserve canceled-job HTTP errors, marked lock contention (the runner must defer it), and HTTP 504 cleanup. A regression using the real queue and database waiter reproduced this missing path; all 91 index-executor tests passed after the fix.

The review follow-up also passed all 529 tests across the original eight affected suites and the full backend Ruff lint/format checks.
