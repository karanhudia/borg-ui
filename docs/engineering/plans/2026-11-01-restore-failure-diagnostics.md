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
