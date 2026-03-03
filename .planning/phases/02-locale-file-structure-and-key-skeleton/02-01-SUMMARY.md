---
phase: 02-locale-file-structure-and-key-skeleton
plan: 01
subsystem: i18n
tags: [i18next, react-i18next, json, locale, translation, typescript]

# Dependency graph
requires:
  - phase: 01-frontend-utility-and-hardcoded-string-cleanup
    provides: translateBackendKey utility deployed at all call sites; English placeholder pattern for es/de locale files established
provides:
  - backend translation namespace with full key skeleton (errors, success, messages) in en/es/de locale files
  - missingKeyHandler in i18n.ts for development-time key gap detection
affects:
  - 03-backend-key-emission (needs backend namespace keys to already exist before backend routes emit them)
  - 04-frontend-translation-wiring (needs backend keys present to wire translateBackendKey calls)
  - 05-translations (needs English placeholders in es/de to replace with real translations)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "backend namespace: all backend-originating strings live under the top-level backend key in locale files"
    - "English placeholders in es/de: newer keys use English text as placeholder; Phase 5 replaces with real translations"
    - "missingKeyHandler: saveMissing: true + console.warn gated on import.meta.env.DEV for development-only key gap warnings"

key-files:
  created: []
  modified:
    - frontend/src/locales/en.json
    - frontend/src/locales/es.json
    - frontend/src/locales/de.json
    - frontend/src/i18n.ts

key-decisions:
  - "backend namespace added as last top-level key in all three locale files — purely additive, no existing keys removed"
  - "es.json and de.json use identical English placeholder values as en.json for backend keys — Phase 5 will add real translations"
  - "missingKeyHandler uses console.warn (not console.error) gated on import.meta.env.DEV — no spurious output in production or test"
  - "saveMissing: true is required alongside missingKeyHandler for the handler to fire — both added together"

patterns-established:
  - "backend.errors.{domain}.{camelCaseKey}: error strings from backend HTTP exceptions"
  - "backend.success.{domain}.{camelCaseKey}: success message strings from backend responses"
  - "backend.messages.{domain}.{camelCaseKey}: informational/status strings from backend"
  - "Parameterized values use {{variableName}} syntax (i18next interpolation), e.g. {{path}}, {{mode}}, {{id}}, {{filename}}, {{error}}"

requirements-completed: [LOC-01, QUAL-01]

# Metrics
duration: 3min
completed: 2026-03-03
---

# Phase 2 Plan 1: Locale File Structure and Key Skeleton Summary

**backend namespace with 60+ translation keys across auth/repo/backup/restore/schedule/ssh/borg domains added to en/es/de locale files, plus i18next missingKeyHandler for development-time key gap detection**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-03T12:59:19Z
- **Completed:** 2026-03-03T13:01:38Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added `backend` namespace with `errors`, `success`, and `messages` sub-sections to en.json, es.json, and de.json
- Covered all 7 error domains: auth, repo, backup, restore, schedule, ssh, borg with real English values in en.json and English placeholders in es/de
- Enabled `saveMissing: true` + `missingKeyHandler` in i18n.ts — development console warns immediately on any missing translation key
- All 1362 existing tests pass; TypeScript compiles without errors; all three JSON files are valid

## Task Commits

Each task was committed atomically:

1. **Task 1: Populate backend namespace in all three locale files** - `69015fe` (feat)
2. **Task 2: Enable missingKeyHandler in i18n.ts** - `06624ba` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `frontend/src/locales/en.json` - Added `backend` block (108 lines) with real English values for all 7 error domains and 6 success domains
- `frontend/src/locales/es.json` - Added identical `backend` block with English placeholders
- `frontend/src/locales/de.json` - Added identical `backend` block with English placeholders
- `frontend/src/i18n.ts` - Added `saveMissing: true` and `missingKeyHandler` with `import.meta.env.DEV` guard

## Decisions Made

- English placeholders used in es.json and de.json for `backend.*` keys — consistent with the established pattern from Phase 1; Phase 5 will add proper Spanish and German translations
- `missingKeyHandler` warns on all namespaces (no `if (ns === 'translation')` guard) — simpler and catches any key gap regardless of namespace
- No `import.meta.env.MODE !== 'test'` guard added to handler — research notes the spurious Vitest output is cosmetic and won't fail tests; handler stays simple

## Deviations from Plan

None - plan executed exactly as written. Backend source file audit confirmed the key set in the plan covers all `detail=` strings that are user-facing and belong in the backend namespace.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 3 can now emit translation keys from backend endpoints — all keys exist in the locale files
- Phase 4 can wire `translateBackendKey` calls to the backend namespace keys — skeleton is complete
- Phase 5 dependency identified: Spanish and German translations for `backend.*` keys will need human review

---
*Phase: 02-locale-file-structure-and-key-skeleton*
*Completed: 2026-03-03*
