---
phase: 04-backend-services-and-remaining-api-files
plan: 02
subsystem: api
tags: [i18n, translation-keys, python, fastapi, locale]

# Dependency graph
requires:
  - phase: 04-01
    provides: restore.py and schedule.py migrated; migration pattern established
provides:
  - ssh_keys.py fully migrated to translation key dict format for all HTTPException.detail and message fields
  - settings.py fully migrated to translation key dict format for all HTTPException.detail and message fields
  - backend.errors.settings domain established in all 3 locale files (10 keys)
  - backend.success.settings domain established in all 3 locale files (15 keys)
  - 13 new backend.errors.ssh keys + 1 new backend.success.ssh key added to all 3 locale files
affects: [phase-05-translations, frontend-error-handling]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SSH errors use backend.errors.ssh.* keys"
    - "Settings/user management errors use backend.errors.settings.* keys"
    - "Settings success messages use backend.success.settings.* bare key strings"
    - "Cross-domain key reuse: auth.currentPasswordIncorrect for password change, repo.repositoryNotFound for cache-clear repo lookup"

key-files:
  created: []
  modified:
    - app/api/ssh_keys.py
    - app/api/settings.py
    - frontend/src/locales/en.json
    - frontend/src/locales/es.json
    - frontend/src/locales/de.json

key-decisions:
  - "Cross-domain key reuse: settings.py change_password uses backend.errors.auth.currentPasswordIncorrect (already exists); cache clear endpoint uses backend.errors.repo.repositoryNotFound (already exists)"
  - "Parameterized message fields (statsRefreshStarted, logCleanupCompleted, cacheCleared, allCacheCleared) use bare key strings — params lost at this phase, Phase 5 will wire properly"
  - "failedCollectStorage in refresh-storage success=False response uses bare error key string (not HTTPException) — non-fatal path consistent with other message fields"

patterns-established:
  - "All HTTPException.detail strings: {key: 'backend.errors.domain.keyName'} or {key: '...', params: {...}}"
  - "All message response fields: bare key string 'backend.success.domain.keyName'"

requirements-completed: [BKND-06]

# Metrics
duration: 9min
completed: 2026-03-03
---

# Phase 4 Plan 2: SSH Keys and Settings API Migration Summary

**ssh_keys.py and settings.py fully migrated to translation key dict format; new backend.errors.settings and backend.success.settings locale domains established across en/es/de**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-03T15:46:30Z
- **Completed:** 2026-03-03T15:55:30Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added 13 new backend.errors.ssh keys + 1 backend.success.ssh key to all 3 locale files, plus full backend.errors.settings (10 keys) and backend.success.settings (15 keys) new domains
- Migrated all user-facing HTTPException.detail strings in ssh_keys.py to {"key": "backend.errors.ssh.*"} dict format across 15+ endpoints
- Migrated all user-facing HTTPException.detail and message fields in settings.py to translation key format, covering system settings, user management, cache, logs, and profile endpoints

## Task Commits

Each task was committed atomically:

1. **Task 1: Add new SSH and settings locale keys to all three locale files** - `33d3378` (feat)
2. **Task 2: Migrate ssh_keys.py and settings.py HTTPException.detail strings to translation keys** - `17badfc` (feat)

## Files Created/Modified

- `app/api/ssh_keys.py` - All user-facing HTTPException.detail and message fields migrated to translation key format
- `app/api/settings.py` - All user-facing HTTPException.detail and message fields migrated to translation key format
- `frontend/src/locales/en.json` - Added 13 new backend.errors.ssh keys, 1 backend.success.ssh key, new backend.errors.settings domain (10 keys), new backend.success.settings domain (15 keys)
- `frontend/src/locales/es.json` - Same additions with English placeholder values
- `frontend/src/locales/de.json` - Same additions with English placeholder values

## Decisions Made

- Cross-domain key reuse applied: settings.py `change_password` uses `backend.errors.auth.currentPasswordIncorrect` (existing); cache-clear repo lookup uses `backend.errors.repo.repositoryNotFound` (existing) — avoids duplicating semantically identical keys across domains
- Parameterized message fields (statsRefreshStarted, logCleanupCompleted, cacheCleared, allCacheCleared) use bare key strings — params not passed to frontend at this phase; Phase 5 will wire params properly
- `failedCollectStorage` in non-exception response path (success=False message field) uses bare error key string — consistent with other message field treatment

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- BKND-06 (SSH + settings portion) satisfied: ssh_keys.py and settings.py have zero raw English strings in HTTPException.detail or message response fields
- New backend.errors.settings and backend.success.settings domains fully established in all 3 locale files
- Ready to proceed with remaining Phase 4 plans (remaining API files)

---
*Phase: 04-backend-services-and-remaining-api-files*
*Completed: 2026-03-03*

## Self-Check: PASSED

- FOUND: app/api/ssh_keys.py
- FOUND: app/api/settings.py
- FOUND: frontend/src/locales/en.json
- FOUND: .planning/phases/04-backend-services-and-remaining-api-files/04-02-SUMMARY.md
- FOUND: commit 33d3378 (Task 1: locale keys)
- FOUND: commit 17badfc (Task 2: Python migration)
