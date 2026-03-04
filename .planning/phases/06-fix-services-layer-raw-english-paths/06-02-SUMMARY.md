---
phase: 06-fix-services-layer-raw-english-paths
plan: 02
subsystem: ui
tags: [react, i18next, translateBackendKey, RestoreJobCard, TDD]

# Dependency graph
requires:
  - phase: 06-fix-services-layer-raw-english-paths
    provides: translateBackendKey utility and backend JSON key format established in plan 06-01
provides:
  - Translated inline error display in RestoreJobCard for failed and completed_with_warnings jobs
  - Test coverage for JSON key string error_message rendering in RestoreJobCard
affects: [restore-job-display, error-message-rendering]

# Tech tracking
tech-stack:
  added: []
  patterns: [translateBackendKey called on each line of split('\n') error_message, sx whiteSpace pre-wrap for multi-line display]

key-files:
  created: []
  modified:
    - frontend/src/components/RestoreJobCard.tsx
    - frontend/src/components/__tests__/RestoreJobCard.test.tsx

key-decisions:
  - "RestoreJobCard: translateBackendKey wraps each split('\n') line — consistent with ErrorDetailsDialog.tsx pattern"
  - "sx={{ whiteSpace: 'pre-wrap' }} on Typography enables multi-line translated messages to render as separate lines"
  - "No mock needed for translateBackendKey in tests — i18n is initialized via setup.ts import of ../i18n which loads real en.json translations"

patterns-established:
  - "split('\n').map(line => translateBackendKey(line)).join('\n') — per-line translation preserving multi-line structure"

requirements-completed: [SVC-02]

# Metrics
duration: 8min
completed: 2026-03-04
---

# Phase 6 Plan 2: RestoreJobCard JSON Error Translation Summary

**translateBackendKey wrapping added to both RestoreJobCard Alert blocks — failed and completed_with_warnings jobs now render translated error messages instead of raw JSON key strings**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-04T10:16:00Z
- **Completed:** 2026-03-04T10:24:00Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments
- Added two new failing tests (RED phase) covering JSON key string error_message for both `failed` and `completed_with_warnings` status
- Fixed RestoreJobCard.tsx by importing `translateBackendKey` and wrapping both Alert block error_message displays
- All 28 RestoreJobCard tests pass and full frontend suite (1364 tests across 66 files) passes with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): Add failing tests for JSON key string error_message** - `70f6104` (test)
2. **Task 2 (GREEN): Fix RestoreJobCard.tsx to render translated error_message** - `1d224aa` (feat)

_Note: TDD tasks have two commits: test (RED) → feat (GREEN)_

## Files Created/Modified
- `frontend/src/components/RestoreJobCard.tsx` - Added `translateBackendKey` import; updated both Alert blocks to split on `\n` and translate each line; added `sx={{ whiteSpace: 'pre-wrap' }}` to Typography in both blocks
- `frontend/src/components/__tests__/RestoreJobCard.test.tsx` - Added 2 new test cases: JSON key string for `failed` status and for `completed_with_warnings` status

## Decisions Made
- No mock needed for `translateBackendKey` in tests: `setup.ts` already imports `../i18n` which loads the real locale files — `translateBackendKey` calls `i18n.t()` directly and returns actual translated strings in the test environment.
- `split('\n').map(line => translateBackendKey(line)).join('\n')` pattern mirrors `ErrorDetailsDialog.tsx` per-line translation, ensuring consistent behavior for multi-line error messages.
- `sx={{ whiteSpace: 'pre-wrap' }}` on Typography renders joined `\n`-separated translated lines as separate visual lines.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## Verification

grep output confirming translateBackendKey appears in 3+ lines of RestoreJobCard.tsx:
```
5:import { translateBackendKey } from '../utils/translateBackendKey'
188:            {job.error_message.split('\n').map(line => translateBackendKey(line)).join('\n')}
196:            {job.error_message.split('\n').map(line => translateBackendKey(line)).join('\n')}
```

Full frontend test suite: 1364 tests passed across 66 files (0 failures).

TypeScript compilation: no errors.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- SVC-02 fully closed: RestoreJobCard now translates JSON key string error_message values from the backend
- No blockers for subsequent plans

---
*Phase: 06-fix-services-layer-raw-english-paths*
*Completed: 2026-03-04*
