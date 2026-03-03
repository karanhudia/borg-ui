---
phase: 05-locale-file-completion-and-ci-validation
plan: 01
subsystem: ui
tags: [i18n, locale, translations, spanish, german, json]

# Dependency graph
requires:
  - phase: 04-backend-services-and-remaining-api-files
    provides: "211 backend.* locale keys with English placeholder values in es.json and de.json"
  - phase: 02-locale-file-structure-and-key-skeleton
    provides: "backend.* key namespace structure with 211 keys in all three locale files"
provides:
  - "es.json: 2047 keys matching committed en.json, all 211 backend.* keys with real Spanish translations"
  - "de.json: 2047 keys matching committed en.json, all 211 backend.* keys with real German translations"
  - "Both files have 17 Phase 6 keys stripped (12 backend + 5 UI), ensuring parity with committed en.json"
  - "archiveBrowser.failedToLoadContents parity fix: German translation now present in de.json"
affects:
  - 05-locale-file-completion-and-ci-validation

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "filter_keys pattern: walk committed en.json as reference, populate values from working tree file, Phase 6 keys excluded by construction"

key-files:
  created: []
  modified:
    - frontend/src/locales/es.json
    - frontend/src/locales/de.json

key-decisions:
  - "05-01: Phase 6 keys excluded by construction — filter_keys walks committed en.json as reference so any key not in committed en.json is automatically absent from output"
  - "05-01: English fallback preserved for any key in committed en.json missing from working tree source — in practice no keys required fallback since working tree had all 2047"
  - "05-01: archiveBrowser.failedToLoadContents parity fix handled automatically — key is in committed en.json and working tree de.json had German value, so filter_keys used it"

patterns-established:
  - "Locale parity enforcement: use committed en.json as the single source of truth for key set; source values from working tree translations; Phase N+1 keys excluded by construction"

requirements-completed: [LOC-02, LOC-03]

# Metrics
duration: 5min
completed: 2026-03-03
---

# Phase 5 Plan 01: Locale File Completion Summary

**Replaced 211 English placeholder values in es.json and de.json with real Spanish/German translations, stripped 17 Phase 6 keys, achieving full parity with committed en.json (2047 keys)**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-03T19:40:05Z
- **Completed:** 2026-03-03T19:45:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- es.json: 2047 keys exactly matching committed en.json; all 211 backend.* keys now have real Spanish translations (zero English placeholders)
- de.json: 2047 keys exactly matching committed en.json; all 211 backend.* keys now have real German translations; archiveBrowser.failedToLoadContents parity gap closed
- 17 Phase 6 keys (12 backend + 5 UI) absent from both files, keeping them aligned with current committed en.json
- LOC-02 and LOC-03 requirements satisfied: Spanish and German users see translated backend messages instead of English fallthrough

## Task Commits

Each task was committed atomically:

1. **Task 1: Produce Phase-5-only es.json using committed en.json as key reference** - `edc1876` (feat)
2. **Task 2: Produce Phase-5-only de.json using committed en.json as key reference** - `58c7020` (feat)

## Files Created/Modified
- `frontend/src/locales/es.json` - 211 English placeholders replaced with real Spanish translations; 17 Phase 6 keys stripped; 2047 keys total
- `frontend/src/locales/de.json` - 211 English placeholders replaced with real German translations; 17 Phase 6 keys stripped; archiveBrowser.failedToLoadContents gap closed; 2047 keys total

## Decisions Made
- Phase 6 keys excluded by construction: the filter_keys function walks committed en.json as reference, so any key absent from committed en.json (the 17 Phase 6 keys) is never written to the output file
- English fallback logic preserved in filter_keys for robustness: if a key is in committed en.json but absent from working tree source, the English value is used as fallback — in practice all 2047 keys were present in both working tree files
- archiveBrowser.failedToLoadContents handled automatically: the key exists in committed en.json and the working tree de.json already had the German translation ("Archivinhalt konnte nicht geladen werden"), so no manual intervention was needed

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- es.json and de.json are now at 2047-key parity with committed en.json
- All 211 backend.* translation keys have real translations in both Spanish and German
- Ready for Phase 5 Plan 02 (CI validation / locale parity check script)
- Phase 6 backend keys (cancelledByUser, borg.*, service.restoreFailed*) and UI keys (multiRepositorySelector.*, repositorySelectorCard.empty) remain excluded until Phase 6 backend code changes land

---
*Phase: 05-locale-file-completion-and-ci-validation*
*Completed: 2026-03-03*
