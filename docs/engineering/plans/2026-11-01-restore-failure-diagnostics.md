# Restore failure diagnostics and zero-file warnings

**Goal:** Preserve actionable, bounded, secret-redacted causes for failed restores and prevent zero-file SSH destination warnings from appearing successful.

**Architecture:** Add a restore-specific formatter that extracts Borg warning/error JSON messages or plaintext, drops progress noise, redacts before bounding, and retains existing translation keys when no hint exists and selects dedicated Details variants for nonempty hints, preserving historical stored errors. Local destination and SSHFS restore failure paths use it; managed-agent failed results retain their bounded causal output. Existing mkdir, mount and subprocess cwd operations are authoritative destination checks. Do not use server access checks on remote paths.

- [x] Add failing regressions for observed exit 104/105 with zero restored files, JSON diagnostics, unterminated stderr, redaction, SSHFS warning failure, and agent causal output.
- [x] Confirm failures against unchanged code, then implement the shared formatter and apply at existing failure seams.
- [x] Preserve successful restores, warnings with files, cancellations, and agent warnings where file count is unknown.
- [x] Run restore/agent/operation suites, lint, formatting and whitespace checks; review and commit.

**Limits:** No changed permissions, remote filesystem probes, repository repair, frontend components, or version changes. Diagnostic hints supplement existing structured errors; operation logs remain available separately.

**Verification:** Nine diagnostic/SSHFS/agent regressions and a destination-redaction regression were observed failing before their fixes. Frontend rendering tests first failed 20 cases for missing diagnostic translations while all four historical-error cases passed. Final backend verification: 143 passed across restore service, agent delegation, formatter, operation executor/facade, API, v2 and agent restore suites. Frontend formatter/translation verification: 36 passed. All four locales pass key parity and translation checks. Ruff, Python formatting, frontend targeted lint/format and whitespace checks pass. Existing dependency deprecations and an existing async mock warning remain in broader tests.

**UI compatibility:** Five diagnostic-specific translation variants in all bundled locales render params.error. Existing keys remain unchanged so historical stored failures never show an unresolved error placeholder. No components or navigation changed.

## Review follow-up: notification HTML, persisted logs and success allocation

- [x] Reproduce HTML injection through the diagnostic, archive, repository name and location in restore-failure email output; verify the Markdown notification retains its original text. Escape those values only in the HTML representation of `send_restore_failure`. Also reproduce the JSON attachment bypass with an HTML transport and encode JSON at the shared HTML `<pre>` embedding sink; pure JSON webhooks and Markdown retain their literal payloads.
- [x] Reproduce secret persistence in SSHFS operation log files. Redact at `RestoreJobFacade.logs`, the common persisted-file sink for local, SSHFS and managed-agent restores. Keep diagnostic text and the existing SSHFS 100-line tail.
- [x] Reproduce an unnecessary full-output allocation on successful SSHFS restores: a synthetic 10 MB output exceeded the 17.9 MB traced-allocation limit before the fix (21.6 MB). Join the complete diagnostic only in the failure branch and write the bounded tail once. The same regression passes after the fix.
- [x] Verify all affected restore, notification, operation, API, v2 and agent suites: 193 tests passed. All 36 frontend translation/formatter tests passed; all four locales retain key parity. Ruff lint/format and diff whitespace checks passed. Existing dependency deprecations and an existing async-mock warning remain.

No real notifications were sent; tests mock transport. Existing failure verdicts, warnings with extracted files, unknown agent file counts and SSH mount cleanup remain covered. No components, translations, protocol or version changed in this follow-up.

## Review follow-up: authorization credentials

- [x] Reproduce Bearer and Basic credentials leaking through the shared redactor and into restore operation log files: eight regressions failed before the fix.
- [x] Mask Authorization credentials in the shared redactor, including case-insensitive headers and JSON/Python dict diagnostics. Preserve the scheme, surrounding diagnostics, line boundaries and repeated-redaction behavior.
- [x] Verify both `job.logs` and its stored file exclude the credentials. All 200 redaction, restore-facade, restore-service, agent-delegation, restore-error and notification tests pass. Ruff lint/format and diff whitespace checks pass; existing dependency deprecations and the async-mock warning remain.

### Key-value and escaped JSON follow-up

- [x] Reproduce ten failures for authorization fields using `=` and JSON-escaped quotes, including credentials written to restore log files.
- [x] Extend the authorization matcher to accept both field delimiters and escaped quotes without decoding or rewriting the diagnostic. Preserve header schemes, quotes, line boundaries and idempotence.
- [x] All 210 affected tests pass, including direct redaction and persisted-log regressions for Bearer and Basic credentials. Ruff lint/format and whitespace checks pass; existing warnings remain.
