---
phase: 01-frontend-utility-and-hardcoded-string-cleanup
plan: 02
subsystem: ui
tags: [i18n, i18next, react, toast, translateBackendKey]

# Dependency graph
requires:
  - phase: 01-frontend-utility-and-hardcoded-string-cleanup
    provides: translateBackendKey utility created in Plan 01

provides:
  - All 32 hardcoded English toast strings in 5 page components replaced with t() calls
  - All 21 error.response?.data?.detail sites in those files routed through translateBackendKey()
  - backup.toasts.*, restore.toasts.*, repositories.toasts.*, archives.toasts.*, archives.mountSuccess, sshConnections.toasts.* keys in en/es/de locales

affects:
  - Phase 5 (Spanish/German translations for placeholder keys added)

# Tech tracking
tech-stack:
  added: []
  patterns: [translateBackendKey wraps every error.response?.data?.detail site, t() replaces all hardcoded English toast strings]

key-files:
  created: []
  modified:
    - frontend/src/pages/Backup.tsx
    - frontend/src/pages/Restore.tsx
    - frontend/src/pages/Repositories.tsx
    - frontend/src/pages/Archives.tsx
    - frontend/src/pages/SSHConnectionsSingleKey.tsx
    - frontend/src/locales/en.json
    - frontend/src/locales/es.json
    - frontend/src/locales/de.json

key-decisions:
  - "Archives.tsx multi-line mount success toast replaced with t('archives.mountSuccess', { command: accessCommand }) to preserve interpolation"
  - "Repositories.tsx check/compact error handlers: detail variable reassigned from raw to translateBackendKey() before branching on status 409"
  - "SSHConnectionsSingleKey.tsx testExistingConnectionMutation and redeployKeyMutation: response.data.error paths also wrapped through translateBackendKey()"
  - "es.json and de.json use English placeholders for all new toast keys — proper translations deferred to Phase 5"

patterns-established:
  - "All toast error calls with backend detail: translateBackendKey(error.response?.data?.detail) || t('section.toasts.key')"
  - "All toast success calls: t('section.toasts.key')"
  - "No template literals containing detail strings in toast calls"

requirements-completed: [FRONT-01, FRONT-02, FRONT-03, FRONT-04, FRONT-05, UTIL-02]

# Metrics
duration: 11min
completed: 2026-03-03
---

# Phase 1 Plan 02: Replace Hardcoded Toast Strings in 5 Page Components Summary

**32 hardcoded English toast strings replaced and 21 backend detail sites wired through translateBackendKey() across Backup, Restore, Repositories, Archives, and SSHConnectionsSingleKey pages**

## Performance

- **Duration:** 11 min
- **Started:** 2026-03-03T07:27:00Z
- **Completed:** 2026-03-03T07:38:09Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- All 32 hardcoded English toast strings in the 5 page components replaced with `t()` calls
- All 21 `error.response?.data?.detail` sites in those files routed through `translateBackendKey()`
- 43 new locale keys added to en.json, es.json, and de.json (backup: 5, restore: 3, repositories: 14, archives: 4 + mountSuccess, sshConnections: 17)
- TypeScript compiles without errors

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace hardcoded toasts and wire detail sites in all 5 page components** - `8de3c34` (feat)
2. **Task 2: Add all new toast locale keys to en.json, es.json, and de.json** - `499246d` (feat)

## Files Created/Modified
- `frontend/src/pages/Backup.tsx` - Added translateBackendKey import; 5 toast strings replaced, 2 detail sites wired
- `frontend/src/pages/Restore.tsx` - Added translateBackendKey import; 3 toast strings replaced, 1 detail site wired
- `frontend/src/pages/Repositories.tsx` - Added translateBackendKey import; 9 toast strings replaced, 5 detail sites wired
- `frontend/src/pages/Archives.tsx` - Added translateBackendKey import; 4 toast strings replaced (including multi-line mountSuccess), 3 detail sites wired
- `frontend/src/pages/SSHConnectionsSingleKey.tsx` - Added translateBackendKey import; 12 toast strings replaced, 10 detail sites wired
- `frontend/src/locales/en.json` - Added backup.toasts.* (5), restore.toasts.* (3), repositories.toasts.* (14), archives.mountSuccess + archives.toasts.* (4), sshConnections.toasts.* (17) keys
- `frontend/src/locales/es.json` - Same keys added with English placeholders
- `frontend/src/locales/de.json` - Same keys added with English placeholders

## Decisions Made
- Archives.tsx multi-line mount success toast replaced with `t('archives.mountSuccess', { command: accessCommand })` to preserve command interpolation while removing hardcoded English
- Repositories.tsx check/compact error handlers: detail variable reassigned from raw string to `translateBackendKey()` result before 409 status branching — no behavioral change, correct wrapping
- SSHConnectionsSingleKey.tsx `testExistingConnectionMutation` and `redeployKeyMutation` success paths: `response.data.error` fields also wrapped through `translateBackendKey()` for consistency
- English placeholders used in es.json and de.json (consistent with Plan 01 decision) — Phase 5 will add proper translations

## Deviations from Plan

None - plan executed exactly as written. Actual line numbers differed slightly from research (expected line ~153 for Archives errorDetail was accurate; SSHConnections line ~384 for publicKeyCopied was at ~384). All changes applied correctly.

## Issues Encountered

None. TypeScript compiled cleanly after all changes. The transient tsc error seen mid-execution resolved on re-run (caching artifact).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- FRONT-01 through FRONT-05 requirements fulfilled: all 5 page components are free of hardcoded English toasts
- UTIL-02 page-component portion complete: all 21 detail sites in these 5 pages routed through translateBackendKey()
- Ready for Plan 03 (remaining utility/component cleanup for UTIL-02 completion across remaining files)

---
*Phase: 01-frontend-utility-and-hardcoded-string-cleanup*
*Completed: 2026-03-03*
