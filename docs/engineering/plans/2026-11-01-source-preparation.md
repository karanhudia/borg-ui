# Fail closed when preparing backup sources

**Goal:** A backup must never silently omit configured SSH sources that could not be prepared.

**Architecture:** Keep the existing source preparation and backup failure epilogue. Raise actionable errors for invalid URLs, missing connections, failed mounts and incomplete mount results. Release previously successful SSH mounts before propagating preparation failure; keep the original mount failure as the exception cause. Preserve the existing successful local, remote and restore-canary path behavior.

- [x] Add regression tests for mixed local/failed remote sources, all-failed remote sources, invalid/missing connections, incomplete mount results and cleanup after an earlier connection mounted.
- [x] Run new tests against unchanged production code and confirm failures expose silently dropped sources.
- [x] Implement validation and failure cleanup at `_prepare_source_paths` in `app/services/backup_service.py`.
- [x] Run backup service, restore-canary and mount unit coverage, Ruff and whitespace checks; inspect the final diff and commit only this scope.

**Limits:** No permission changes, SSH key repair, automatic retries, repository mutations or version bumps. The mount service already cleans its own partially failed connection; preparation owns successful earlier connections. Local source accessibility remains Borg's responsibility.

**Verification:** All seven new regressions failed before production changes (the preparation method returned silently). After the fix, the backup/mount/restore suites passed: 158 passed, 8 existing skips. The final preparation-only run, including an added valid mixed-source preservation case, passed 17 tests. Ruff lint/format and diff whitespace checks passed. Existing dependency deprecations and async mock warnings remain in the broader suites.
