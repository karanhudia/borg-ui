---
phase: 03-backend-api-migration-auth-high-traffic-domains
plan: 02
subsystem: api
tags: [fastapi, i18n, translation-keys, backup, python]

# Dependency graph
requires:
  - phase: 02-locale-file-structure-and-key-skeleton
    provides: backend.errors.backup.* and backend.success.backup.* keys in en/es/de locale files
  - phase: 03-backend-api-migration-auth-high-traffic-domains
    provides: translateBackendKey utility and Shape 1/2/3 patterns established in 03-01 (auth.py)
provides:
  - backup.py with all user-facing HTTPException.detail strings migrated to {key} dict format
  - First parameterized error using {key, params} shape in backup domain
  - Cancel success message using dot-notation key string
affects:
  - frontend consumption of backup errors (translateBackendKey parses these shapes)
  - Phase 4 services layer migration (same patterns)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shape 1 static: detail={\"key\": \"backend.errors.backup.someKey\"}"
    - "Shape 1 parameterized: detail={\"key\": \"...\", \"params\": {\"filename\": var}}"
    - "Shape 3 success: return {\"message\": \"backend.success.backup.backupCancelled\"}"

key-files:
  created: []
  modified:
    - app/api/backup.py

key-decisions:
  - "Stream logs endpoint 'Backup job not found' migrated despite being absent from research table — verify command confirmed 0 remaining raw strings, stream endpoint uses axios (not browser nav), migration correct"
  - "Download endpoint auth strings (Authentication token required, Invalid token, etc.) intentionally left as raw English — browser navigation, not axios-intercepted"
  - "Cannot download logs for running backup intentionally left as raw English — browser download handler, not axios"

patterns-established:
  - "Parameterized backup error: {key: backend.errors.backup.logFileNotFound, params: {filename: log_filename}}"
  - "Success message as plain dot-notation string, not dict: return {message: backend.success.backup.backupCancelled}"

requirements-completed: [BKND-03]

# Metrics
duration: 2min
completed: 2026-03-03
---

# Phase 3 Plan 02: Backup API Translation Key Migration Summary

**backup.py fully migrated — 4 backupJobNotFound, 1 canOnlyCancelRunningJobs, 1 noLogsAvailable, 1 logFileNotFound (parameterized), 1 backupCancelled success key; download endpoint auth strings intentionally preserved**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-03T13:46:48Z
- **Completed:** 2026-03-03T13:49:00Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Replaced all user-facing `detail=` raw English strings in backup.py with `{"key": "backend.errors.backup.*"}` dict format
- Established first parameterized error in backup domain: `{"key": "backend.errors.backup.logFileNotFound", "params": {"filename": log_filename}}`
- Cancel success message converted to `"backend.success.backup.backupCancelled"` dot-notation string format
- Python syntax verified clean; all 5 locale keys confirmed present in en.json
- Download endpoint auth strings (`Authentication token required`, `Invalid token`, `User not found or inactive`, `Invalid authentication`) correctly left as raw English (browser navigation, not axios)

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate backup.py user-facing strings to translation keys** - `07b0138` (feat)
2. **Task 2: Verify backup.py migration correctness and run type checks** - `07b0138` (no code changes — audit only)

**Plan metadata:** (docs commit — see final commit)

## Files Created/Modified
- `app/api/backup.py` - All 7 user-facing detail/message strings migrated to translation key format

## Decisions Made
- Stream logs endpoint `Backup job not found` was not in the research migration table but was correctly identified as needing migration: it uses `get_current_user` (authenticated via axios), so errors surface to users via `translateBackendKey`. The verify command confirmed 0 remaining raw strings, validating this decision.
- `Cannot download logs for running backup` left as raw English: the download endpoint uses `<a>` click / browser navigation, so HTTP 400 goes to the browser download handler and is NOT intercepted by axios/react-query error handling.
- Download endpoint auth strings left as raw English for the same browser-navigation reason.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Migration] stream_backup_logs endpoint "Backup job not found" migrated**
- **Found during:** Task 1 verification (grep returned 1 instead of 0)
- **Issue:** Research table listed 3 "Backup job not found" sites (~145, ~190, ~274) but a 4th existed at ~344 in `stream_backup_logs` endpoint. This endpoint uses `get_current_user` Depends (axios-authenticated), so its errors ARE surfaced to users via `translateBackendKey`. The plan's verify command expected count 0, confirming the intent was to migrate all user-facing instances.
- **Fix:** Replaced `detail="Backup job not found"` at line 345 with `detail={"key": "backend.errors.backup.backupJobNotFound"}`
- **Files modified:** app/api/backup.py
- **Verification:** `grep -n '"Backup job not found"...' | wc -l` returns 0
- **Committed in:** `07b0138` (part of Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 2 — missing migration)
**Impact on plan:** Necessary for correctness. Stream endpoint errors now properly translated. No scope creep — same key, same pattern, same endpoint category.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- backup.py fully migrated; all backup error/success keys in translation key format
- Pattern for parameterized errors (`{key, params}`) now established in Phase 3
- Ready for next high-traffic domain (Phase 3 remaining plans)
- BKND-03 requirement satisfied

---
*Phase: 03-backend-api-migration-auth-high-traffic-domains*
*Completed: 2026-03-03*
