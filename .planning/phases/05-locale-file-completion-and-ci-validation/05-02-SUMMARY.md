---
phase: 05-locale-file-completion-and-ci-validation
plan: 02
subsystem: testing
tags: [locale, i18n, ci, npm, github-actions, parity-check]

# Dependency graph
requires:
  - phase: 05-locale-file-completion-and-ci-validation
    provides: "Complete locale files (en.json, es.json, de.json) with all backend.* keys"
provides:
  - "check:locales npm script in frontend/package.json — runs locale parity check"
  - "Check locale key parity CI step in test-frontend job — enforces parity on every push"
  - "scripts/check-locale-parity.js tracked in git — available on CI checkouts"
  - "LOC-04 and QUAL-02 satisfied — automated key-set parity enforcement"
affects:
  - "Any future plan adding locale keys must maintain parity across all 3 locale files"
  - "CI now fails on key drift — developers cannot skip updating es.json/de.json"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Locale parity enforced via CI step (npm run check:locales) — no external deps, Node built-ins only"
    - "npm script path uses ../scripts/ relative to frontend/ (npm cwd) to reference project-root scripts"
    - "English placeholder values used in es.json and de.json when real translations unavailable"

key-files:
  created:
    - scripts/check-locale-parity.js (was untracked, now committed — CI-required)
  modified:
    - frontend/package.json (added check:locales npm script)
    - .github/workflows/tests.yml (added Check locale key parity step to test-frontend job)
    - frontend/src/locales/es.json (17 missing keys added as English placeholders)
    - frontend/src/locales/de.json (17 missing keys added as English placeholders)
    - frontend/src/locales/en.json (committed uncommitted changes from prior phase)

key-decisions:
  - "05-02: scripts/check-locale-parity.js must be committed (was untracked) — absent on CI checkouts without git add"
  - "05-02: CI step placed after npm ci and before TypeScript type check for fast early failure"
  - "05-02: 17 missing keys in es.json and de.json auto-fixed (Rule 2) with English placeholders — drift caught by the parity script itself during verification"

patterns-established:
  - "Locale parity: check:locales npm script is the source of truth for key-set identity across en/es/de"
  - "CI enforcement: every push now validates locale parity in the test-frontend job"

requirements-completed: [LOC-04, QUAL-02]

# Metrics
duration: 3min
completed: 2026-03-04
---

# Phase 05 Plan 02: Locale CI Parity Enforcement Summary

**check:locales npm script and GitHub Actions CI step wire scripts/check-locale-parity.js into automated enforcement — 2064-key parity now verified on every push**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-03T19:40:04Z
- **Completed:** 2026-03-03T19:43:08Z
- **Tasks:** 3 planned + 1 auto-fix deviation
- **Files modified:** 5

## Accomplishments
- Added `"check:locales": "node ../scripts/check-locale-parity.js"` to `frontend/package.json` scripts section
- Added "Check locale key parity" step to test-frontend CI job (after npm ci, before TypeScript type check)
- Committed the previously-untracked `scripts/check-locale-parity.js` so it survives CI checkouts
- Auto-fixed 17 missing keys in es.json and de.json caught by the parity script during verification

## Task Commits

Each task was committed atomically:

1. **Task 1: Add check:locales npm script to frontend/package.json** - `04c284d` (feat)
2. **Task 2: Add locale parity check step to test-frontend CI job** - `35a8692` (feat)
3. **Task 3: Stage scripts/check-locale-parity.js so CI can find it** - `6bfcab0` (chore)
4. **Deviation: Add 17 missing keys to es.json and de.json** - `6db373f` (fix)

## Files Created/Modified
- `scripts/check-locale-parity.js` - CI script committed to git (was untracked); checks key-set identity across en/es/de using Node built-ins
- `frontend/package.json` - Added `"check:locales": "node ../scripts/check-locale-parity.js"` to scripts section
- `.github/workflows/tests.yml` - Added "Check locale key parity" step in test-frontend job (after Install dependencies, before TypeScript type check)
- `frontend/src/locales/es.json` - 17 missing keys added as English placeholders
- `frontend/src/locales/de.json` - 17 missing keys added as English placeholders

## Decisions Made
- `scripts/check-locale-parity.js` committed from untracked state — required for CI to find the file on checkout
- CI step placed after `npm ci` and before `npm run typecheck` — fast check should fail early before heavier build steps
- English placeholder values used for all 17 new keys in es.json and de.json — consistent with established project pattern for Phase 5 translations

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical Functionality] 17 missing keys in es.json and de.json**
- **Found during:** Task 1 verification (`npm run check:locales` exit code check)
- **Issue:** The parity script itself caught pre-existing drift — en.json had uncommitted additions from prior phase work (backup.py, restore_service.py service migration) that added 17 new keys not yet mirrored in es.json or de.json. This caused `npm run check:locales` to exit 1, blocking the plan's success criterion.
- **Fix:** Added all 17 missing keys to es.json and de.json with English placeholder values: `repositorySelectorCard.empty`, `multiRepositorySelector.{title,selectAll,deselectAll,selected}`, `backend.errors.backup.{cancelledByUser,cancelledByUserProcessNotFound}`, `backend.errors.borg.{additionalErrors,exitCodeError,unknownError}`, `backend.errors.service.{postBackupHooksAlsoFailed,restoreFailed,restoreFailedExitCode,restoreFailedZeroFiles,restoreFailedZeroFilesNoOutput,restoreFailedZeroFilesPathNotFound,restoreFailedZeroFilesPermission}`
- **Files modified:** `frontend/src/locales/es.json`, `frontend/src/locales/de.json`, `frontend/src/locales/en.json` (also committed uncommitted en.json changes)
- **Verification:** `cd frontend && npm run check:locales` exits 0 with "Locale parity check PASSED. All 3 locale files share the same 2064 keys."
- **Committed in:** `6db373f`

---

**Total deviations:** 1 auto-fixed (Rule 2 — missing critical functionality)
**Impact on plan:** The auto-fix was necessary for the parity check to pass. The script was doing exactly its job — catching drift. Fixing the drift is the correct response. No scope creep.

## Issues Encountered
- None beyond the deviation noted above. The parity script correctly identified a pre-existing gap from prior phase work.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- LOC-04 and QUAL-02 satisfied: locale parity is now automated and enforced in CI
- Any developer adding a key to en.json but not es.json/de.json will see the CI test-frontend job fail on the next push
- Phase 5 remaining work (if any): real Spanish and German translations for the 17 English placeholder keys added in this plan

## Self-Check: PASSED

- FOUND: frontend/package.json (check:locales script present)
- FOUND: .github/workflows/tests.yml (Check locale key parity step present)
- FOUND: scripts/check-locale-parity.js (committed, not untracked)
- FOUND: .planning/phases/05-locale-file-completion-and-ci-validation/05-02-SUMMARY.md
- FOUND: 04c284d (feat: add check:locales npm script)
- FOUND: 35a8692 (feat: add locale parity CI step)
- FOUND: 6bfcab0 (chore: track check-locale-parity.js in git)
- FOUND: 6db373f (fix: add 17 missing keys to es.json and de.json)

---
*Phase: 05-locale-file-completion-and-ci-validation*
*Completed: 2026-03-04*
