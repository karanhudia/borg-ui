# Storage failure recovery implementation plan

**Goal:** Keep storage failures actionable and visible, and stop persistent background archive failures from repeating at full frequency.

**Architecture:** Detect only explicit storage exhaustion and I/O signals through exception causes, SQLAlchemy originals and bounded diagnostic text. Reuse the existing API exception handlers, telemetry and reconcile scheduler; preserve failed operation state and repository metadata. No schema migration, repository repair, lock breaking, version bump or automatic data deletion.

**Evidence:** Five-day production reports contain 555 I/O-error occurrences on five installs and SQLite FULL failures on cancellation and prune comparison refresh. Current main already defers archive lock contention and retains bounded diagnostic tails; preserve those fixes.

## Tasks

- [x] Add failing API regressions for SQLite FULL, wrapped FULL, ENOSPC, EDQUOT and EIO; verify unrelated errors remain 500 and response bodies never expose SQL, paths or secrets.
- [x] Add a shared storage-failure classifier and translatable safe recovery details. Use it for unhandled and wrapped HTTP 5xx responses, preserving original exceptions in telemetry.
- [x] Add failing telemetry regressions for handled Borg I/O/storage exhaustion. Mark these actionable failures as unhandled for severity classification, retain bounded redacted details and preserve ordinary handled failures.
- [x] Add failing reconcile tests for repeated terminal archive-sync failures, increasing cooldown with a six-hour cap, manual/forced bypass and successful recovery reset. Preserve lock deferral and failed history.
- [x] Implement bounded cooldown from persisted operation history without new tables or background timers; document manual refresh and recovery.
- [x] Run affected tests, formatting, locale parity and diff checks; review and open a dedicated PR.

## Constraints and remaining cases

Storage remediation on private user hosts requires their operators. No claim of repairing host disks or restoring backups follows from these code changes. Source preparation, announcements and operation-specific recovery have separate branches and PRs. Existing fixed-version reports receive upgrade guidance rather than duplicate patches.

## Verification

The 13 API/telemetry regressions and five cooldown regressions failed before implementation. The affected main, reporter, reconcile, runner and index suites pass 308 tests. Ruff lint/format, locale key and placeholder parity, and whitespace checks pass. Independent review exercised extended SQLite I/O codes and cyclic causes and found no issues. Existing deprecation/resource warnings remain.

Follow-up validation: a short refresh interval regression proved four stored failures were insufficient to reach the six-hour cap. Inspect ten bounded verdicts instead; the five-minute interval now reaches the cap and intervals longer than six hours remain preserved. The reconcile/runner/index suites pass 230 tests, and independent reconcile verification passes 38 tests.

## Review follow-up

SQLAlchemy renders the failed statement and bound values in its wrapper text. Ten regressions reproduced false storage classification from query data, the resulting incorrect HTTP status, and a misleading telemetry key. The classifier now inspects original and causal exceptions without scanning copied wrapper text; exception reporting classifies the exception object before converting it to text. String-only handled Borg diagnostics retain their storage classification.

The storage-full copy in all four locales now says Borg UI does not delete data to recover from the error; it makes no assertion about earlier prune/deletion work. Reporter, main and Borg-error suites pass 143 tests. Ruff lint/format, JSON formatting, locale parity, personal-path scan and whitespace checks pass.

Independent review also reproduced copied SQL text inside outer HTTPException/RuntimeError messages. Four added regressions cover both wrappers with misleading full/I/O phrases; authoritative cause/context traversal prevents those false matches while genuine wrapped FULL/EIO failures still classify correctly. Final independent review found no remaining issues.

## Tar-stream exception-context follow-up

Both tar download helpers raise their HTTP error while catching normal stream exhaustion. Seven end-to-end regressions reproduced lost FULL/EIO recovery responses or telemetry reporting incidental `StopAsyncIteration` instead of Borg's diagnostic. The helpers now suppress only that incidental context, and the HTTP handler respects explicit context suppression when selecting the exception to report. Explicit causes and ordinary unsuppressed wrappers retain their existing handling.

Regression coverage invokes both actual stream helpers through the HTTP handler and reporter for ENOSPC, EIO and unrelated permission errors, plus an explicitly suppressed-context case. Full reporter, download, both archive API and main suites pass 163 tests. Ruff lint/format and whitespace checks pass; existing dependency/resource warnings remain. Independent review found no remaining issues.
