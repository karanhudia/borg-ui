---
phase: 04-backend-services-and-remaining-api-files
plan: 03
subsystem: api
tags: [i18n, localization, fastapi, python, json, translation-keys, backend]

# Dependency graph
requires:
  - phase: 04-02
    provides: "ssh_keys.py and settings.py migrated; backend.errors.settings and backend.success.settings domains established"
  - phase: 03-04
    provides: "repositories.py migration complete, migration pattern established"
provides:
  - "9 remaining API files fully migrated to translation key dict format"
  - "8 new locale error domains: activity, archives, browse, filesystem, mounts, notifications, packages, scripts"
  - "3 new locale success domains: activity, archives, packages"
  - "BKND-06 requirement satisfied — zero user-facing raw English strings in HTTPException.detail or message fields across all backend API files"
affects: [phase-05-translations, frontend-error-display, translateBackendKey-utility]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Static error: raise HTTPException(status_code=N, detail={key: 'backend.errors.domain.keyName'})"
    - "Parameterized error: raise HTTPException(..., detail={key: '...keyName', params: {param: value}})"
    - "Success message: return {message: 'backend.success.domain.keyName'}"
    - "Cross-domain key reuse: restore.repositoryNotFound reused in archives, browse, scripts_library"
    - "Cross-domain key reuse: settings.adminAccessRequired reused in packages"
    - "Cross-domain key reuse: ssh.sshKeyNotFound reused in filesystem"
    - "Download endpoints (FileResponse/token-auth) excluded from migration"
    - "str(e) catch-all exception strings excluded from migration"
    - "Raw OS/SSH error strings (stderr content) excluded from migration"

key-files:
  created: []
  modified:
    - "app/api/archives.py"
    - "app/api/mounts.py"
    - "app/api/activity.py"
    - "app/api/filesystem.py"
    - "app/api/browse.py"
    - "app/api/packages.py"
    - "app/api/notifications.py"
    - "app/api/scripts.py"
    - "app/api/scripts_library.py"
    - "frontend/src/locales/en.json"
    - "frontend/src/locales/es.json"
    - "frontend/src/locales/de.json"

key-decisions:
  - "browse.py archiveMemoryTooHigh uses round(estimated_memory_mb) for integer params — avoids float format issues in i18next interpolation"
  - "scripts.py and scripts_library.py have user-facing HTTPException.detail strings — migrated to backend.errors.scripts domain with 10 keys"
  - "scripts_library.py scriptInUse uses params {count, places, repos} — preserves original dynamic message data while using key format"
  - "browse.py archiveTooLarge and archiveMemoryTooHigh use actual variable names (lines_read, max_items, estimated_memory_mb, max_memory_mb) as params"
  - "activity.py delete_job endpoint message uses bare key string 'backend.success.activity.jobDeleted' — jobType param not passed at this phase, Phase 5 will wire params"
  - "packages.py installationInProgress/installationStarted use bare key strings — name param not passed at this phase, Phase 5 will wire params"

patterns-established:
  - "Download endpoint exclusion: FileResponse endpoints with token query-param auth are never migrated — browser-navigated, not axios-intercepted"
  - "Cross-domain key reuse: prefer reusing existing semantically-identical keys over creating duplicates (restore.repositoryNotFound, settings.adminAccessRequired, ssh.sshKeyNotFound)"

requirements-completed: [BKND-06]

# Metrics
duration: 10min
completed: 2026-03-03
---

# Phase 04 Plan 03: Remaining API Files Migration Summary

**9 remaining API files migrated to translation key dict format with 8 new error domains and 3 new success domains — BKND-06 fully satisfied**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-03-03T16:00:00Z
- **Completed:** 2026-03-03T16:09:36Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments

- Added 204 lines of new locale keys across en.json, es.json, de.json covering 8 new error domains and 3 new success domains
- Migrated all user-facing HTTPException.detail and message fields in 9 API files to translation key dict format
- Confirmed download endpoints (archives.py download_file_from_archive, activity.py download_job_logs) are correctly excluded
- BKND-06 fully satisfied: zero raw English strings in HTTPException.detail or message response fields across all backend API files

## Task Commits

Each task was committed atomically:

1. **Task 1: Add new locale keys for all remaining API domains** - `849f8e6` (feat)
2. **Task 2: Migrate remaining API files to translation key format** - `a19001b` (feat)

## Files Created/Modified

- `frontend/src/locales/en.json` - Added 8 new backend.errors domains (activity, archives, browse, filesystem, mounts, notifications, packages, scripts) and 3 new backend.success domains (activity, archives, packages)
- `frontend/src/locales/es.json` - Same domains added with English placeholder values
- `frontend/src/locales/de.json` - Same domains added with English placeholder values
- `app/api/archives.py` - 9 HTTPException.detail / message fields migrated; download_file_from_archive() excluded
- `app/api/mounts.py` - 5 HTTPException.detail fields migrated
- `app/api/activity.py` - 5 HTTPException.detail / message fields in delete_job endpoint migrated; download_job_logs() excluded
- `app/api/filesystem.py` - 12 HTTPException.detail fields migrated across browse, validate-path, and create-folder endpoints; raw OS/SSH error strings excluded
- `app/api/browse.py` - 3 HTTPException.detail fields migrated (repositoryNotFound reuse + 2 archive size limits with params)
- `app/api/packages.py` - All admin, packageNotFound, packageAlreadyExists, jobNotFound, and message fields migrated across 6 endpoints
- `app/api/notifications.py` - 3 instances of settingNotFound migrated
- `app/api/scripts.py` - 3 HTTPException.detail fields migrated (adminAccessRequired, scriptCannotBeEmpty, scriptExecutionTimedOut)
- `app/api/scripts_library.py` - 14 HTTPException.detail fields migrated across all CRUD endpoints and repository assignment endpoints

## Decisions Made

- browse.py archiveMemoryTooHigh uses round(estimated_memory_mb) for integer params — avoids float format issues in i18next interpolation
- scripts.py and scripts_library.py have user-facing HTTPException.detail strings — migrated to backend.errors.scripts domain with 10 keys (discovered during Task 1 file review per plan instructions)
- scripts_library.py scriptInUse uses params {count, places, repos} — preserves original dynamic message data while using key format
- activity.py and packages.py success message fields use bare key strings — jobType/name params not passed at this phase, Phase 5 will wire params
- Cross-domain key reuse: restore.repositoryNotFound reused in archives, browse, scripts_library (5 sites); settings.adminAccessRequired reused in packages (6 sites); ssh.sshKeyNotFound reused in filesystem (3 sites)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Migrated scripts.py and scripts_library.py user-facing strings**
- **Found during:** Task 1 (reading scripts.py and scripts_library.py per plan instructions)
- **Issue:** Plan directed executor to read both files and add keys if user-facing strings existed; scripts.py had 3 user-facing strings and scripts_library.py had 14
- **Fix:** Added 10 keys under backend.errors.scripts domain; migrated all user-facing strings in both files
- **Files modified:** frontend/src/locales/en.json, es.json, de.json, app/api/scripts.py, app/api/scripts_library.py
- **Verification:** Python syntax check passes; JSON valid
- **Committed in:** 849f8e6 (Task 1), a19001b (Task 2)

---

**Total deviations:** 1 auto-handled (per plan's explicit instructions to check scripts files)
**Impact on plan:** scripts.py and scripts_library.py migration was explicitly part of plan scope — executor discovered and handled as instructed. No scope creep.

## Issues Encountered

None - all migrations applied cleanly. All 9 files pass syntax check. JSON valid in all 3 locale files.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- BKND-06 fully satisfied: all backend API files (auth, repositories, backup, restore, check, compact, prune, ssh_keys, settings, archives, mounts, activity, filesystem, browse, packages, notifications, scripts, scripts_library) now use translation key dict format
- Phase 5 will add proper Spanish and German translations for all backend.* keys (currently using English placeholders)
- Phase 5 will wire jobType/name params into success message responses for activity and packages endpoints

---
*Phase: 04-backend-services-and-remaining-api-files*
*Completed: 2026-03-03*
