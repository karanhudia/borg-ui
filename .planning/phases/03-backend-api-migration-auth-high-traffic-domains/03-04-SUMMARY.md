---
phase: 03-backend-api-migration-auth-high-traffic-domains
plan: "04"
subsystem: api
tags: [i18n, python, fastapi, locale, repositories]

# Dependency graph
requires:
  - phase: 03-backend-api-migration-auth-high-traffic-domains
    plan: "03"
    provides: "repositories.py migration (46 sites) and 13 locale keys for BKND-02 initial pass"
provides:
  - "6 new backend.errors.repo locale keys added to en/es/de (24 total repo keys)"
  - "8 remaining raw English HTTPException.detail strings in repositories.py replaced with translation key dicts"
  - "BKND-02 fully satisfied: zero raw English strings in user-facing HTTPException.detail positions in repositories.py"
affects: [phase-05-translations, future-repo-api-changes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Static error key (no params): detail={\"key\": \"backend.errors.repo.encryptedPassphraseIncorrect\"}"
    - "Parameterized error: detail={\"key\": \"backend.errors.repo.repositoryDirNotExist\", \"params\": {\"path\": repo_path}}"

key-files:
  created: []
  modified:
    - app/api/repositories.py
    - frontend/src/locales/en.json
    - frontend/src/locales/es.json
    - frontend/src/locales/de.json

key-decisions:
  - "03-04: Gap closure plan: 8 sites missed in 03-03 now migrated — permission denied dir creation (2 sites), parent dir not writable (1), import dir not exist (1), import config missing (1), passphrase incorrect (1), import borg error (1), keyfile not required (1)"
  - "03-04: Lines 761 and 858 both reuse existing notValidBorgRepository key (already has {{path}} param) — no new key needed"
  - "03-04: Line 852 passphrase error uses static key encryptedPassphraseIncorrect (no params) — message is fixed regardless of input"
  - "03-04: es.json and de.json use English placeholder values for all 6 new keys — Phase 5 will add proper translations"

patterns-established:
  - "Reuse existing notValidBorgRepository key for all 'Not a valid Borg repository' error sites — avoids duplicate keys for same semantic error"

requirements-completed: [BKND-02]

# Metrics
duration: 2min
completed: 2026-03-03
---

# Phase 3 Plan 04: BKND-02 Gap Closure Summary

**8 remaining raw English HTTPException.detail strings in repositories.py migrated to translation keys, closing BKND-02 gap across 3 locale files with 6 new repo error keys**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-03T14:29:40Z
- **Completed:** 2026-03-03T14:31:49Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- 6 new `backend.errors.repo` locale keys added to en.json, es.json, and de.json (24 total repo error keys, exact parity across all three files)
- 8 raw English HTTPException.detail f-strings removed from repositories.py — all replaced with `{"key": "...", "params": {...}}` dicts
- BKND-02 requirement formally complete: zero user-facing raw English strings remain in repositories.py HTTPException.detail positions

## Task Commits

Each task was committed atomically:

1. **Task 1: Add 6 new locale keys to all three locale files** - `0e6a7b6` (feat)
2. **Task 2: Migrate 8 remaining raw English detail strings in repositories.py** - `0c918e0` (feat)

**Plan metadata:** (docs commit — see below)

## Files Created/Modified

- `app/api/repositories.py` - 8 raw English detail strings replaced with translation key dicts (migrations at former lines 570, 594, 613, 753, 761, 852, 858, 978)
- `frontend/src/locales/en.json` - 6 new keys added under `backend.errors.repo` (24 total)
- `frontend/src/locales/es.json` - Same 6 new keys with English placeholder values (24 total, exact parity)
- `frontend/src/locales/de.json` - Same 6 new keys with English placeholder values (24 total, exact parity)

## Decisions Made

- Lines 761 and 858 both reuse the existing `notValidBorgRepository` key (already has `{{path}}` param in locale value) — no new key needed for either site
- Line 852 passphrase error uses a static `encryptedPassphraseIncorrect` key (no params) — the message is the same regardless of input
- `es.json` and `de.json` use English placeholder values for all 6 new keys — Phase 5 will add proper Spanish and German translations

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. All 8 migration sites matched their described patterns exactly. JSON validation passed for all three locale files. Key parity confirmed (24 repo error keys in all three locale files).

## Note on BKND-02 Status

BKND-02 was marked `[x]` complete after Plan 03-03, but 8 user-facing HTTPException.detail strings had been missed in that pass. This gap closure plan (03-04) finalizes the requirement for real. The REQUIREMENTS.md marking is already `[x]` complete — no change needed — but this SUMMARY documents that 03-04 is the plan that fully satisfied the requirement.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- repositories.py is fully migrated — BKND-02 definitively complete
- Phase 3 can continue with remaining backend domain files (if any remain in scope)
- Phase 5 (translations) can now add proper Spanish and German values for all 6 new keys

---
*Phase: 03-backend-api-migration-auth-high-traffic-domains*
*Completed: 2026-03-03*
