# Fail closed when preparing backup sources

**Goal:** A backup must never silently omit configured SSH sources that could not be prepared.

**Architecture:** Keep the existing source preparation and backup failure epilogue. Raise actionable errors for invalid URLs, missing connections, failed mounts and incomplete mount results. Release previously successful SSH mounts before propagating preparation failure; keep the original mount failure as the exception cause. Preserve the existing successful local, remote and restore-canary path behavior.

- [x] Add regression tests for mixed local/failed remote sources, all-failed remote sources, invalid/missing connections, incomplete mount results and cleanup after an earlier connection mounted.
- [x] Run new tests against unchanged production code and confirm failures expose silently dropped sources.
- [x] Implement validation and failure cleanup at `_prepare_source_paths` in `app/services/backup_service.py`.
- [x] Run backup service, restore-canary and mount unit coverage, Ruff and whitespace checks; inspect the final diff and commit only this scope.

**Limits:** No permission changes, SSH key repair, automatic retries, repository mutations or version bumps. The mount service already cleans its own partially failed connection; preparation owns successful earlier connections. Local source accessibility remains Borg's responsibility.

**Verification:** All seven new regressions failed before production changes (the preparation method returned silently). After the fix, the backup/mount/restore suites passed: 158 passed, 8 existing skips. The final preparation-only run, including an added valid mixed-source preservation case, passed 17 tests. Ruff lint/format and diff whitespace checks passed. Existing dependency deprecations and async mock warnings remain in the broader suites.

## Recorded source-preparation causes

Code review identified that the backup failure epilogue preserves keyed JSON exceptions but replaces plaintext exceptions with its generic unknown-error key. Add end-to-end tests using the real preparation method and backup epilogue for a missing SSH connection and a permission-denied SSHFS mount. Preserve source causes through keyed JSON exceptions, redacted before bounding to 1000 characters. Add a diagnostic-specific locale key in all four locales so new errors display the cause while historical errors remain readable. Keep the generic exception handler unchanged and retain chained mount exceptions.

- [x] End-to-end regressions observed the unknown-error key before the fix.
- [x] Four frontend cause-rendering tests failed before locale support; four historical-error cases passed.
- [x] Verify complete affected suites, lint/format and locale parity, then commit.

**Follow-up verification:** Full backup suite: 82 passed, 6 existing skips. Four end-to-end scenarios cover inferred missing connection, explicitly selected missing connection, SSHFS permission failure and an oversized diagnostic with a quoted secret and a final causal hint. Original mount exceptions remain chained. Eight frontend tests pass across all four languages, including historical-error compatibility. Locale parity, targeted Python/frontend lint and formatting, and whitespace checks pass. Existing dependency and async-mock warnings remain.

## Authorization credential redaction review fix

- [x] Reproduce credential persistence in four end-to-end mount-error scenarios: Bearer, Basic, key-value authorization and JSON-escaped authorization fields.
- [x] Reuse the shared authorization redactor and its regression cases from PR #1506, retaining the existing diagnostic bounds and failure handling.
- [x] Verify backup/redaction coverage: 166 passed, 6 existing skips. Mount and path-confinement coverage: 115 passed, 2 existing skips. Ruff lint/format and whitespace checks pass. Existing dependency warnings remain.

No mount behavior, retry policy, translation or version changed.
