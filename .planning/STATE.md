---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-03-03T15:57:11.892Z"
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 13
  completed_plans: 11
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** Every user-facing string — whether from the frontend or backend — must be translatable, so users can operate the UI entirely in their own language.
**Current focus:** Phase 4 - Backend Services and Remaining API Files

## Current Position

Phase: 4 of 5 (Backend Services and Remaining API Files)
Plan: 2 of 4 in current phase (04-02 complete — ssh_keys.py and settings.py migrated; 29 new locale keys; BKND-06 SSH+settings portion satisfied)
Status: Phase 4 in progress
Last activity: 2026-03-03 — Plan 04-02 complete: ssh_keys.py and settings.py fully migrated to translation key dict format; 29 new locale keys added to en/es/de; new backend.errors.settings and backend.success.settings domains established

Progress: [██████████████░] 75%

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
| Phase 04-backend-services-and-remaining-api-files P01 | 7 | 2 tasks | 5 files |
| Phase 04-backend-services-and-remaining-api-files P02 | 9 | 2 tasks | 5 files |

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
- [Phase 04-01]: Conditional toggle message uses a message variable pre-assigned to the key string — avoids f-string in message field
- [Phase 04-01]: Multi-repo run-now message returns scheduledJobStartedMulti key without count param — Phase 5 will wire params
- [Phase 04-01]: cancel_restore DB writes use json.dumps({key: ...}) for translatable error messages in error_message column
- [Phase 04-02]: Cross-domain key reuse: settings.py change_password uses auth.currentPasswordIncorrect; cache clear uses repo.repositoryNotFound — avoids duplicating semantically identical keys
- [Phase 04-02]: Parameterized message fields in settings.py use bare key strings — params not passed to frontend at this phase, Phase 5 will wire params

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 3/4: The 656+ `detail=` site count is a grep count; actual unique keys likely 80-120. Do a domain-by-domain tally at Phase 3 start to right-size locale file work.
- Phase 4: Verify `error_message` column max length can accommodate JSON-encoded `{key, params}` strings before migrating services layer.
- Phase 5: Spanish and German translations for new backend.* keys may need a human reviewer — identify this dependency early.

## Session Continuity

Last session: 2026-03-03
Stopped at: Completed 04-02-PLAN.md — ssh_keys.py and settings.py fully migrated to translation key dict format; 29 new locale keys added to en/es/de; new backend.errors.settings and backend.success.settings domains established; BKND-06 (SSH + settings portion) satisfied.
Resume file: None
