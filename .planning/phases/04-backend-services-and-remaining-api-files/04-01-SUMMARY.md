---
phase: 04-backend-services-and-remaining-api-files
plan: 01
subsystem: api
tags: [i18n, fastapi, python, locale, translation-keys]

requires:
  - phase: 03-backend-api-migration-auth-and-high-traffic-domains
    provides: Established migration pattern (key dict format, json.dumps for DB writes, reuse existing keys)

provides:
  - restore.py fully migrated — zero raw English strings in HTTPException.detail or message fields
  - schedule.py fully migrated — zero raw English strings in HTTPException.detail or message fields
  - 11 new locale keys in en.json, es.json, and de.json (alphabetically ordered)

affects:
  - 05-translations
  - frontend translation call sites for restore/schedule error/success messages

tech-stack:
  added: []
  patterns:
    - "HTTPException.detail uses dict format: {\"key\": \"backend.errors.domain.keyName\"}"
    - "Parameterized errors: {\"key\": \"backend.errors.domain.keyName\", \"params\": {\"field\": value}}"
    - "DB error_message writes use json.dumps({\"key\": \"...\"})"
    - "Success message fields return bare key strings: \"backend.success.domain.keyName\""
    - "Conditional message uses variable: message = key_a if cond else key_b; return {\"message\": message}"

key-files:
  created: []
  modified:
    - app/api/restore.py
    - app/api/schedule.py
    - frontend/src/locales/en.json
    - frontend/src/locales/es.json
    - frontend/src/locales/de.json

key-decisions:
  - "Conditional toggle message (enabled/disabled) uses a message variable pre-assigned to key string, then returned in dict — avoids f-string in message field"
  - "Multi-repo run-now message drops count param — scheduledJobStartedMulti key uses {{count}} but Phase 5 will wire params; for now bare key returned (frontend shows key string or fallback)"
  - "cancel_restore DB error_message writes use json.dumps() with key dict — consistent with established pattern from Phase 3"
  - "schedule.py line 266 (path-based repo observability) uses static key form (no name param) — path-based repos don't have a name field available in that branch"

patterns-established:
  - "Parameterized invalidCronExpression: {\"key\": \"backend.errors.schedule.invalidCronExpression\", \"params\": {\"error\": str(e)}}"
  - "Parameterized repositoryNotFound with id: {\"key\": \"backend.errors.schedule.repositoryNotFound\", \"params\": {\"id\": repo_id}}"
  - "observabilityOnlyRepo used both statically (path-based) and with params (ID-based: {\"name\": repo.name})"

requirements-completed: [BKND-04, BKND-05]

duration: 7min
completed: 2026-03-03
---

# Phase 04 Plan 01: Restore and Schedule API Migration Summary

**restore.py and schedule.py fully migrated to translation key dict format — 15 restore sites and 25+ schedule sites, plus 11 new locale keys across en/es/de**

## Performance

- **Duration:** 7 min
- **Started:** 2026-03-03T15:35:33Z
- **Completed:** 2026-03-03T15:41:55Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- All user-facing HTTPException.detail strings in restore.py replaced with `{"key": "backend.errors.restore.*"}` dicts
- All user-facing HTTPException.detail strings in schedule.py replaced with `{"key": "backend.errors.schedule.*"}` dicts
- cancel_restore DB error_message writes now use `json.dumps({"key": "..."})` — translatable end-to-end
- 11 new locale keys added alphabetically to en.json, es.json, and de.json (7 restore errors, 3 schedule errors, 1 schedule success)
- BKND-04 and BKND-05 requirements satisfied

## Task Commits

Each task was committed atomically:

1. **Task 1: Add new restore and schedule locale keys to all three locale files** - `85cf8d3` (feat)
2. **Task 2: Migrate restore.py and schedule.py HTTPException.detail strings to translation keys** - `9300689` (feat)

## Files Created/Modified

- `app/api/restore.py` - 15 migration sites: preview/start/repositories/contents/jobs/status/cancel endpoints
- `app/api/schedule.py` - 25+ migration sites across all CRUD and run-now endpoints
- `frontend/src/locales/en.json` - 11 new keys in backend.errors.restore, backend.errors.schedule, backend.success.schedule
- `frontend/src/locales/es.json` - Same 11 new keys with English placeholder values
- `frontend/src/locales/de.json` - Same 11 new keys with English placeholder values

## Decisions Made

- Conditional toggle message (enabled vs disabled) uses a message variable pre-assigned to the appropriate key string, then returned in the response dict. This avoids an f-string in the message field.
- Multi-repo run-now message returns the `scheduledJobStartedMulti` key without a count param for now. The locale value contains `{{count}}` but the frontend will show the key/fallback until Phase 5 wires params.
- `cancel_restore` DB writes use `json.dumps({"key": "..."})` to store translatable error messages in the `error_message` column — consistent with the Phase 3 established pattern.
- The path-based single-repo observability check (legacy by path) uses the static key form without a `name` param — the name is not reliably available in that branch.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- BKND-04 and BKND-05 complete — restore and schedule APIs are fully migrated
- Phase 04-02 can proceed with remaining backend service files (services layer)
- Phase 5 (translations) can now add proper Spanish/German values for the 11 new keys added here

## Self-Check: PASSED

- FOUND: .planning/phases/04-backend-services-and-remaining-api-files/04-01-SUMMARY.md
- FOUND: app/api/restore.py
- FOUND: app/api/schedule.py
- FOUND commit: 85cf8d3 (Task 1)
- FOUND commit: 9300689 (Task 2)

---
*Phase: 04-backend-services-and-remaining-api-files*
*Completed: 2026-03-03*
