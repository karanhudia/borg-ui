---
phase: 03-backend-api-migration-auth-high-traffic-domains
plan: 01
subsystem: auth
tags: [i18n, translation-keys, fastapi, python, backend-migration]

# Dependency graph
requires:
  - phase: 02-locale-file-structure-and-key-skeleton
    provides: backend.errors.auth and backend.success.auth locale keys already scaffolded in en/es/de
provides:
  - app/api/auth.py with all 10 HTTPException.detail strings using {"key": "backend.errors.auth.*"} format
  - app/api/auth.py with all 3 success message strings using "backend.success.auth.*" dot-notation format
  - app/core/security.py with "Not enough permissions" and "Inactive user" strings migrated to translation key format
  - notEnoughPermissions key added to backend.errors.auth in en/es/de locale files
affects:
  - 03-02-PLAN and later backend migration phases (establishes the exact Shape 1 / Shape 3 patterns to follow)
  - frontend translateBackendKey utility (consumes these key strings at runtime)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shape 1 error: detail={\"key\": \"backend.errors.auth.someKey\"} — dict format for HTTPException.detail"
    - "Shape 3 success: return {\"message\": \"backend.success.auth.someKey\"} — bare dot-notation string for message fields"
    - "Preserve headers={\"WWW-Authenticate\": \"Bearer\"} on all raises that already had it"
    - "Do NOT migrate catch-all except Exception strings or internal /token OAuth2 error responses"
    - "New locale keys use English placeholder value in es.json and de.json — Phase 5 will add real translations"

key-files:
  created: []
  modified:
    - app/api/auth.py
    - app/core/security.py
    - frontend/src/locales/en.json
    - frontend/src/locales/es.json
    - frontend/src/locales/de.json

key-decisions:
  - "Two 'Inactive user' strings in security.py (get_current_user and get_current_active_user) were outside the plan's explicit scope but appeared in the end-to-end verification grep; auto-fixed under Rule 1 for correctness"
  - "notEnoughPermissions key added in alphabetical position within backend.errors.auth block across all three locales"
  - "es.json and de.json use English value 'Not enough permissions' as placeholder — Phase 5 convention"

patterns-established:
  - "Shape 1 error pattern: detail={\"key\": \"backend.errors.auth.*\"}"
  - "Shape 3 success pattern: return {\"message\": \"backend.success.auth.*\"}"

requirements-completed: [BKND-01]

# Metrics
duration: 3min
completed: 2026-03-03
---

# Phase 3 Plan 01: Auth Backend Migration Summary

**All HTTPException.detail and message strings in auth.py and security.py migrated to translation key format using Shape 1 dict and Shape 3 bare-string patterns; notEnoughPermissions locale key added to all three locale files**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-03T13:46:57Z
- **Completed:** 2026-03-03T13:49:28Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Migrated 10 HTTPException.detail strings in auth.py to `{"key": "backend.errors.auth.*"}` dict format
- Migrated 3 success message strings in auth.py to `"backend.success.auth.*"` dot-notation format
- Migrated `get_current_admin_user` "Not enough permissions" in security.py to key format
- Auto-fixed 2 additional "Inactive user" strings in security.py found during end-to-end verification
- Added `notEnoughPermissions` key to `backend.errors.auth` block in en/es/de locale files (alphabetical order)
- TypeScript compilation and JSON validity verified clean after all changes

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate auth.py detail and message strings to translation keys** - `eca8b51` (feat)
2. **Task 2: Migrate security.py and add notEnoughPermissions to all locale files** - `5c45221` (feat)
3. **Auto-fix: Remaining inactiveUser strings in security.py** - `487f5fe` (fix)

## Files Created/Modified
- `app/api/auth.py` - 10 error detail strings + 3 success message strings migrated to translation keys
- `app/core/security.py` - "Not enough permissions" and 2x "Inactive user" strings migrated to translation keys
- `frontend/src/locales/en.json` - notEnoughPermissions key added; auth block reordered alphabetically
- `frontend/src/locales/es.json` - notEnoughPermissions key added (English placeholder); auth block reordered alphabetically
- `frontend/src/locales/de.json` - notEnoughPermissions key added (English placeholder); auth block reordered alphabetically

## Decisions Made
- Two "Inactive user" strings in `security.py` (`get_current_user` and `get_current_active_user`) were outside the plan's explicit task scope but were revealed by the end-to-end verification grep; auto-fixed under deviation Rule 1 for correctness — leaving them would create inconsistency where the same "Inactive user" condition in auth.py is translated but in security.py is not
- notEnoughPermissions inserted in alphabetical order within the existing backend.errors.auth block across all three locales
- English value used as placeholder in es.json and de.json per established Phase 5 convention

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Two "Inactive user" strings in security.py missed by plan scope**
- **Found during:** End-to-end verification after Task 2
- **Issue:** `get_current_user` (line 89) and `get_current_active_user` (line 178) in security.py both contained raw "Inactive user" detail strings; the plan only explicitly called out `get_current_admin_user` for security.py migration. The plan's end-to-end verification grep included `app/core/security.py` and returned 2 hits.
- **Fix:** Replaced both `detail="Inactive user"` with `detail={"key": "backend.errors.auth.inactiveUser"}` — key already exists in all three locale files
- **Files modified:** `app/core/security.py`
- **Verification:** End-to-end grep returned 0 results after fix
- **Committed in:** `487f5fe`

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug/omission)
**Impact on plan:** Auto-fix necessary for correctness — the existing `inactiveUser` locale key was already present; leaving raw strings in security.py would create inconsistent translation coverage in the same auth subsystem.

## Issues Encountered
None — all migrations applied cleanly. TypeScript compiled without errors. All three locale files passed JSON validation.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- auth.py and security.py fully migrated; Pattern established for remaining Phase 3 plans
- Shape 1 (error dict) and Shape 3 (success bare string) patterns documented and ready for reuse
- Next plan should target the next highest-traffic backend file per Phase 3 research

---
*Phase: 03-backend-api-migration-auth-high-traffic-domains*
*Completed: 2026-03-03*
