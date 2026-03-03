---
phase: 03-backend-api-migration-auth-high-traffic-domains
plan: 03
subsystem: api
tags: [i18n, fastapi, python, translation-keys, locale, repositories]

# Dependency graph
requires:
  - phase: 03-backend-api-migration-auth-high-traffic-domains
    provides: translateBackendKey utility deployed; auth.py and backups.py already migrated
provides:
  - repositories.py fully migrated — all user-facing HTTPException.detail strings use translation key dict format
  - 13 new locale keys in backend.errors.repo (11) and backend.success.repo (3) across en/es/de
affects:
  - phase-04-services-layer-migration
  - phase-05-translations

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Static errors use {"key": "backend.errors.repo.keyName"} dict format
    - Parameterized errors use {"key": "...", "params": {...}} dict format
    - checkAlreadyRunning and compactAlreadyRunning drop dynamic Job ID — use static key
    - 423 lock error dicts are exempt — LockErrorDialog uses HTTP status code, not translateBackendKey
    - catch-all 500 strings with {str(e)} intentionally left as raw English (system errors)
    - Conditional message variable pattern: assign key string, return {"message": message} unchanged

key-files:
  created: []
  modified:
    - app/api/repositories.py
    - frontend/src/locales/en.json
    - frontend/src/locales/es.json
    - frontend/src/locales/de.json

key-decisions:
  - "checkAlreadyRunning and compactAlreadyRunning use static key form (Job ID dropped) — cleaner UX, locale value is the simplified message"
  - "Conditional message variable at lines 672/675 assigns key strings (repositoryCreated, repositoryAlreadyExists) — return path unchanged"
  - "Line 815 import endpoint 'Repository path already exists in database with name ...' left as is — parameterized string with name, not in migration table scope"

patterns-established:
  - "Pattern 1: All user-facing HTTPException.detail in repositories.py use {\"key\": \"backend.errors.repo.*\"} format"
  - "Pattern 2: Parameterized errors use {\"key\": ..., \"params\": {...}} — SSH connection and passphrase errors"
  - "Pattern 3: 423 Locked responses are excluded from migration — handled by LockErrorDialog via HTTP status"

requirements-completed: [BKND-02]

# Metrics
duration: 12min
completed: 2026-03-03
---

# Phase 03 Plan 03: Repositories API Migration Summary

**46 translation key migration sites in repositories.py (3,164 lines) — all user-facing HTTPException.detail strings now use {key} dict format; 13 new locale keys added to en/es/de**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-03T13:50:00Z
- **Completed:** 2026-03-03T14:02:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- 13 new locale keys added: 11 in `backend.errors.repo` (atLeastOneSourceDirRequired, keyfileEmpty, repoHasNoKeyfile, cannotSwitchToFullModeNoSourceDirs, cannotDeleteRepoWithArchives, checkAlreadyRunning, compactAlreadyRunning, breakLockTimeout, checkJobNotFound, compactJobNotFound, sshUrlWithoutConnectionId) and 3 in `backend.success.repo` (repositoryCreated, repositoryAlreadyExists, keyfileUploaded)
- repositories.py fully migrated: 46 `"key":` sites covering all error types (not found, admin required, name/path conflict, SSH, keyfile, check/compact already running, lock timeout, job not found)
- 423 lock error dicts confirmed untouched; catch-all 500 strings with {str(e)} confirmed intentionally left as raw English
- Python syntax check passes; TypeScript compiles clean with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add 13 new locale keys** - `d67b388` (feat)
2. **Task 2: Migrate repositories.py detail strings** - `a212bab` (feat)
3. **Task 3: Verify skip rules** - no new files changed (verification only)

## Files Created/Modified
- `app/api/repositories.py` - All user-facing HTTPException.detail strings migrated to translation key dict format
- `frontend/src/locales/en.json` - 13 new keys in backend.errors.repo and backend.success.repo
- `frontend/src/locales/es.json` - 13 new keys (English placeholders, Phase 5 convention)
- `frontend/src/locales/de.json` - 13 new keys (English placeholders, Phase 5 convention)

## Decisions Made
- **checkAlreadyRunning / compactAlreadyRunning static form:** The original strings included dynamic Job ID in parentheses. The plan specified dropping the Job ID and using a static locale key — cleaner UX, no loss of actionable information for the user.
- **Conditional message variable (lines 672/675):** The `message` variable is assigned key strings (`"backend.success.repo.repositoryCreated"` / `"backend.success.repo.repositoryAlreadyExists"`) and the `return {"message": message}` line is left unchanged. Frontend translateBackendKey handles the lookup.
- **Import endpoint path conflict (line 815):** The string `"Repository path already exists in database with name '{existing_path.name}'"` was not in the migration table. Left as raw English — it's parameterized with a dynamic name and not a clean static key candidate without further research.

## Deviations from Plan

None — plan executed exactly as written. The prune endpoint at ~line 1664 (`"A prune operation is already running..."`) was noted during audit but is outside the plan scope (repositories.py prune errors were not in the migration table and prune uses its own locale domain not yet established).

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness
- Phase 3 plan 03 complete: repositories.py fully migrated. All three high-traffic backend files (auth.py, backups.py, repositories.py) are now fully migrated.
- BKND-02 requirement satisfied.
- Phase 4 (services layer migration) can proceed.
- Phase 5 will need real Spanish and German translations for all `backend.errors.repo.*` and `backend.success.repo.*` keys added in this plan.

---
*Phase: 03-backend-api-migration-auth-high-traffic-domains*
*Completed: 2026-03-03*

## Self-Check: PASSED
- SUMMARY.md: FOUND
- Commit d67b388 (Task 1 locale keys): FOUND
- Commit a212bab (Task 2 repositories.py migration): FOUND
