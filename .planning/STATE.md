---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-03-03T14:31:49Z"
progress:
  total_phases: 5
  completed_phases: 2
  total_plans: 11
  completed_plans: 10
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** Every user-facing string — whether from the frontend or backend — must be translatable, so users can operate the UI entirely in their own language.
**Current focus:** Phase 3 - Backend API Migration: Auth and High-Traffic Domains

## Current Position

Phase: 3 of 5 (Backend API Migration: Auth and High-Traffic Domains)
Plan: 4 of N in current phase (03-04 complete — BKND-02 gap closure: 8 remaining raw strings migrated, 6 new locale keys)
Status: Phase 3 in progress
Last activity: 2026-03-03 — Plan 03-04 complete: 8 remaining raw English HTTPException.detail strings migrated; 6 new locale keys added to en/es/de; BKND-02 definitively complete

Progress: [█████████████░] 70%

## Performance Metrics

**Velocity:**
- Total plans completed: 4 (phase 3 plans: 03-01, 03-02, 03-03, 03-04)
- Average duration: 8 min
- Total execution time: 0.55 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-frontend-utility-and-hardcoded-string-cleanup | 4 | 20 min | 5 min |
| 02-locale-file-structure-and-key-skeleton | 1 | 3 min | 3 min |

**Recent Trend:**
- Last 5 plans: 8 min, 11 min, 0 min (03), 1 min (04), 3 min (02-01)
- Trend: stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Architecture: Backend sends translation keys, frontend owns all translation via i18next — no server-side translation
- Pattern: Dynamic strings use `{key, params}` object format for interpolation
- Safety: Deploy `translateBackendKey` utility and update all 69 call sites BEFORE migrating any backend endpoint (prevents `[object Object]` in production)
- Exclusion: `LOCK_ERROR::` sentinel in `error_message` must not be converted — regex in BackupJobsTable.tsx:331 depends on it
- 01-01: Use String(i18n.t(...)) to coerce i18next union return type to plain string — avoids TypeScript errors without suppressing type checking
- 01-01: es.json and de.json use English placeholder for common.errors.unexpectedError — proper translations deferred to Phase 5
- 01-02: Archives.tsx multi-line mount success toast replaced with t('archives.mountSuccess', { command }) to preserve interpolation
- 01-02: SSHConnectionsSingleKey response.data.error paths also wrapped through translateBackendKey() for consistency across all success/error code paths
- 01-02: English placeholders used in es.json and de.json for all new toast keys — Phase 5 will add proper translations
- 02-01: backend namespace added as last top-level key in all three locale files — purely additive, no existing keys removed
- 02-01: es.json and de.json use English placeholder values for backend.* keys — Phase 5 will add real translations
- 02-01: missingKeyHandler uses console.warn gated on import.meta.env.DEV — no output in production; saveMissing: true required alongside handler to fire
- 03-01: Two "Inactive user" strings in security.py (get_current_user, get_current_active_user) auto-fixed alongside the planned get_current_admin_user migration — all three now use {"key": "backend.errors.auth.inactiveUser"}
- 03-01: notEnoughPermissions locale key inserted in alphabetical order within backend.errors.auth block across all three locale files
- 03-02: Stream logs endpoint "Backup job not found" migrated despite being absent from research table — uses get_current_user (axios-authenticated), errors surface to users
- 03-02: Download endpoint auth strings intentionally left as raw English — browser navigation, not axios-intercepted
- 03-02: Cannot download logs for running backup intentionally left as raw English — browser download handler, not react-query
- 03-03: checkAlreadyRunning and compactAlreadyRunning use static key form (Job ID dropped) — cleaner UX, locale value is the simplified message
- 03-03: Conditional message variable pattern (lines 672/675) assigns key strings; return {"message": message} unchanged
- 03-03: Import endpoint "Repository path already exists in database with name ..." left as raw English — parameterized with dynamic name, outside migration table scope
- 03-04: Lines 761 and 858 both reuse existing notValidBorgRepository key (already has {{path}} param) — no new key needed for either site
- 03-04: Line 852 passphrase error uses static key encryptedPassphraseIncorrect (no params) — message is fixed regardless of input
- 03-04: es.json and de.json use English placeholder values for all 6 new keys — Phase 5 will add proper translations

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 3/4: The 656+ `detail=` site count is a grep count; actual unique keys likely 80-120. Do a domain-by-domain tally at Phase 3 start to right-size locale file work.
- Phase 4: Verify `error_message` column max length can accommodate JSON-encoded `{key, params}` strings before migrating services layer.
- Phase 5: Spanish and German translations for new backend.* keys may need a human reviewer — identify this dependency early.

## Session Continuity

Last session: 2026-03-03
Stopped at: Completed 03-04-PLAN.md — BKND-02 gap closure: 8 remaining raw English detail strings migrated, 6 new locale keys added to all 3 locale files. BKND-02 definitively complete.
Resume file: None
