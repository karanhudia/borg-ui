---
phase: 17-add-cli-password-reset-script-for-issue-350
plan: 01
subsystem: infra
tags: [python, sqlite3, bcrypt, cli, admin-tools]

# Dependency graph
requires: []
provides:
  - Standalone CLI script to reset any user password directly in SQLite
affects: [operations, deployment, admin-tooling]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Standalone admin scripts use raw sqlite3 with no app bootstrap dependency"
    - "DB path configurable via BORG_DB_PATH env var with /data/borg.db default"

key-files:
  created:
    - app/scripts/reset_password.py
  modified: []

key-decisions:
  - "Inline bcrypt.hashpw directly rather than importing from app.core.security to avoid full app init"
  - "Set must_change_password = 0 on reset (admin-initiated resets should not force another change)"
  - "Wrap sys.exit in except block re-raise to prevent rollback swallowing the intended exit"

patterns-established:
  - "Standalone scripts: shebang + stdlib + single third-party import, no app package imports"

requirements-completed: [QUICK-17]

# Metrics
duration: 1min
completed: 2026-03-21
---

# Quick Task 17: Add CLI Password Reset Script Summary

**Self-contained `app/scripts/reset_password.py` using raw sqlite3 and inline bcrypt to let admins reset locked-out user passwords from the container shell**

## Performance

- **Duration:** ~1 min
- **Started:** 2026-03-21T15:19:52Z
- **Completed:** 2026-03-21T15:20:59Z
- **Tasks:** 1 of 1
- **Files modified:** 1

## Accomplishments

- Created `app/scripts/reset_password.py` — a zero-dependency admin recovery tool (issue #350)
- Script hashes the new password with bcrypt inline (no app.core.security import)
- Sets `must_change_password = 0` so admin-initiated resets don't force an immediate re-change
- Full error handling: wrong arg count, empty password, unknown user, DB exceptions — all exit 1 with clear stderr messages
- DB path overridable via `BORG_DB_PATH` env var, consistent with existing script conventions

## Task Commits

1. **Task 1: Create reset_password.py CLI script** - `8b2ca45` (feat)

**Plan metadata:** (docs commit below)

## Files Created/Modified

- `app/scripts/reset_password.py` - Standalone CLI tool: `python -m app.scripts.reset_password <username> <password>`

## Decisions Made

- Inlined bcrypt hashing rather than importing `get_password_hash` from `app.core.security` — avoids pulling in the full FastAPI app initialisation chain
- Set `must_change_password = 0` (not 1): admin-initiated resets should grant immediate access, not prompt another forced change
- Re-raise `SystemExit` in the `except` block so it isn't caught and swallowed by the generic exception handler

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Tool is ready for immediate use in production containers
- Usage: `docker exec -it borg-ui python -m app.scripts.reset_password <username> <new_password>`

---
*Phase: quick-17*
*Completed: 2026-03-21*

## Self-Check: PASSED

- app/scripts/reset_password.py: FOUND
- Commit 8b2ca45: FOUND
