---
phase: 06-fix-services-layer-raw-english-paths
plan: 01
subsystem: api
tags: [python, i18n, backend, error-messages, restore-service]

# Dependency graph
requires:
  - phase: 04-backend-services-and-remaining-api-files
    provides: json.dumps key format established for error_message DB writes; format_error_message() returns json.dumps; ErrorDetailsDialog renders translateBackendKey line-by-line
  - phase: 05-locale-file-completion-and-ci-validation
    provides: restoreFailedExitCode key in en.json, es.json, de.json with real translations
provides:
  - restore_service.py line 451 always writes json.dumps key format regardless of stderr_output content (SVC-02)
  - backup_service.py confirmed clean — no raw-English error_message writes (SVC-01)
affects: [ErrorDetailsDialog.tsx, translateBackendKey utility, restore job error rendering]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "error_message DB writes always use json.dumps({key: ...}) — never raw text, even when stderr_output is non-empty"
    - "Debug info (stderr_output) goes to job.logs, not job.error_message — keeps UI errors translatable"

key-files:
  created: []
  modified:
    - app/services/restore_service.py

key-decisions:
  - "SVC-02: Raw stderr_output ternary removed from line 451 — error_message always uses restoreFailedExitCode json.dumps key format; stderr preserved in job.logs on line 453"
  - "SVC-01: backup_service.py confirmed already correct — error_msg variable (line 1405) is pre-assigned as json.dumps; error_parts (line 2022) contains only LOCK_ERROR::, format_error_message(), and json.dumps() items"

patterns-established:
  - "Services layer pattern: job.error_message = json.dumps({key, params}) for translatable UI; job.logs = raw text for debugging"

requirements-completed: [SVC-01, SVC-02]

# Metrics
duration: 5min
completed: 2026-03-04
---

# Phase 6 Plan 1: Fix Services Layer Raw-English Paths Summary

**Removed raw stderr_output ternary from restore_service.py line 451 — all error_message DB writes in both backup_service.py and restore_service.py now use json.dumps key format, ensuring ErrorDetailsDialog always renders translated text**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-04T04:35:00Z
- **Completed:** 2026-03-04T04:40:00Z
- **Tasks:** 2 (1 verification-only, 1 one-line fix)
- **Files modified:** 1

## Accomplishments

- SVC-01 confirmed satisfied: backup_service.py has zero raw-English error_message DB writes — `error_msg` variable is always `json.dumps({...})`, `error_parts` only contains LOCK_ERROR:: sentinel + `format_error_message()` + `json.dumps()` items
- SVC-02 fixed: restore_service.py line 451 ternary `stderr_output if stderr_output else json.dumps(...)` replaced with unconditional `json.dumps({"key": "backend.errors.service.restoreFailedExitCode", "params": {"exitCode": process.returncode}})`
- Debug information preserved: stderr_output still written to job.logs on line 453 — no information lost

## Task Commits

Each task was committed atomically:

1. **Task 1: Verify SVC-01 — grep backup_service.py** - no code changes (verification only, included in Task 2 commit context)
2. **Task 2: Fix SVC-02 — remove raw stderr ternary** - `1aa879e` (fix)

## Files Created/Modified

- `app/services/restore_service.py` - Line 451 ternary removed; error_message always uses json.dumps restoreFailedExitCode key format

## Verification Output

### SVC-01: backup_service.py (no raw-English error_message assignments)

```
grep -n "error_message" app/services/backup_service.py | grep -v "json.dumps\|format_error_message\|LOCK_ERROR\|#"
```

Results (all verified as non-DB-write usages):
- Line 1405: `job.error_message = error_msg` — `error_msg` is `json.dumps({...})` from line 1399. CORRECT.
- Lines 1904, 1969, 1982, 2172: Pass `job.error_message` as function arguments to notification calls. NOT DB writes.
- Line 2022: `"\n".join(error_parts)` — `error_parts` contains only LOCK_ERROR::, format_error_message(), json.dumps() items. CORRECT.

**SVC-01: SATISFIED — no raw-English DB writes**

### SVC-02: restore_service.py (fix applied)

Before:
```python
job.error_message = stderr_output if stderr_output else json.dumps({"key": "backend.errors.service.restoreFailedExitCode", "params": {"exitCode": process.returncode}})
```

After:
```python
job.error_message = json.dumps({"key": "backend.errors.service.restoreFailedExitCode", "params": {"exitCode": process.returncode}})
```

```
grep -n "error_message" app/services/restore_service.py | grep -v "json.dumps\|#"
```

Result: Line 463 only — `job.error_message` as function argument to notification call. NOT a DB write.

**SVC-02: SATISFIED — all error_message DB writes use json.dumps key format**

### Locale key verification

```
grep "restoreFailedExitCode" frontend/src/locales/en.json frontend/src/locales/es.json frontend/src/locales/de.json
```

```
frontend/src/locales/en.json:        "restoreFailedExitCode": "Restore process exited with code {{exitCode}}",
frontend/src/locales/es.json:        "restoreFailedExitCode": "El proceso de restauración terminó con el código {{exitCode}}",
frontend/src/locales/de.json:        "restoreFailedExitCode": "Der Wiederherstellungsprozess wurde mit Code {{exitCode}} beendet",
```

3 locale files, all pre-existing from Phase 4/5. No locale changes needed.

## Decisions Made

- SVC-01: backup_service.py grep returns false positives for function-argument usages (not DB writes); manual code review of each line confirms all are correct — no file changes needed
- SVC-02: Raw ternary removed entirely; stderr preserved in job.logs is sufficient for debugging; error_message surfaces to UI via ErrorDetailsDialog and must be translatable

## Deviations from Plan

None — plan executed exactly as written. Task 1 was verification-only (no code changes). Task 2 was the single one-line fix described.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Services layer is now clean: backup_service.py and restore_service.py both use json.dumps key format exclusively for error_message DB writes
- ErrorDetailsDialog will render translated text for all restore failure paths (exit code, zero files, unexpected errors)
- Phase 6 plan 1 complete — requirements SVC-01 and SVC-02 fully satisfied

---
*Phase: 06-fix-services-layer-raw-english-paths*
*Completed: 2026-03-04*
