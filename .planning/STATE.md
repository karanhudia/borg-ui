---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-03-04T04:47:38.825Z"
progress:
  total_phases: 6
  completed_phases: 5
  total_plans: 20
  completed_plans: 19
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-03)

**Core value:** Every user-facing string — whether from the frontend or backend — must be translatable, so users can operate the UI entirely in their own language.
**Current focus:** Phase 6 - Fix Services Layer Raw-English Paths

## Current Position

Phase: 6 of 6 (Fix Services Layer Raw-English Paths)
Plan: 1 of 2 in current phase (06-01 complete — SVC-01 confirmed satisfied in backup_service.py; SVC-02 fixed in restore_service.py line 451; raw-stderr ternary removed; error_message always uses json.dumps key format)
Status: Phase 6 in progress (1 of 2 plans complete)
Last activity: 2026-03-04 — Plan 06-01 complete: removed raw-stderr ternary from restore_service.py line 451; SVC-01 and SVC-02 both satisfied; services layer error_message writes are fully clean

Progress: [████████████████] 95%

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
| Phase 04-backend-services-and-remaining-api-files P03 | 10 | 2 tasks | 12 files |
| Phase 04-backend-services-and-remaining-api-files P04 | 3 | 2 tasks | 7 files |
| Phase 04-backend-services-and-remaining-api-files P04 | 3 | 2 tasks | 7 files |
| Phase 04-backend-services-and-remaining-api-files P06 | 2 | 2 tasks | 6 files |
| Phase 04-backend-services-and-remaining-api-files P05 | 3 | 2 tasks | 4 files |
| Phase 05-locale-file-completion-and-ci-validation P01 | 5 | 2 tasks | 2 files |
| Phase 05-locale-file-completion-and-ci-validation P02 | 3 | 4 tasks | 5 files |
| Phase 05-locale-file-completion-and-ci-validation P03 | 2 | 2 tasks | 2 files |
| Phase 06-fix-services-layer-raw-english-paths P01 | 5 | 2 tasks | 1 files |

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
- [Phase 04-03]: browse.py archiveMemoryTooHigh uses round(estimated_memory_mb) for integer params to avoid float format issues in i18next interpolation
- [Phase 04-03]: scripts.py and scripts_library.py have user-facing HTTPException.detail strings — migrated to backend.errors.scripts domain with 10 keys
- [Phase 04-03]: activity.py and packages.py success message fields use bare key strings — params not passed at this phase, Phase 5 will wire params
- [Phase 04-03]: Cross-domain key reuse: restore.repositoryNotFound reused in archives/browse/scripts_library; settings.adminAccessRequired reused in packages; ssh.sshKeyNotFound reused in filesystem
- [Phase 04-04]: Service layer error_message writes use json.dumps key format; ErrorDetailsDialog renders line-by-line through translateBackendKey for mixed content (JSON keys, LOCK_ERROR:: sentinel, borg output)
- [Phase 04-backend-services-and-remaining-api-files]: [Phase 04-06]: settings.py message key corruption removed — response[message] += lines were redundant since CacheManagementTab.tsx handles connection_info separately
- [Phase 04-backend-services-and-remaining-api-files]: [Phase 04-06]: scripts_library.py cleanup response adds count field mirroring cleaned_up for i18next {{count}} interpolation
- [Phase 04-backend-services-and-remaining-api-files]: [Phase 04-06]: es.json and de.json use English placeholder values for new filesystem and scripts success domains — Phase 5 adds real translations
- [Phase 04-backend-services-and-remaining-api-files]: 04-05: msg_parts dynamic join at delete endpoint dropped — static sshKeyDeleted key used; connection/repository counts logged, not user-facing
- [Phase 04-backend-services-and-remaining-api-files]: 04-05: Internal test_ssh_key_connection helper returns locale key string — caller uses conditional success/failure key selection instead of propagating raw message
- [Phase 05-01]: Phase 6 keys excluded by construction — filter_keys walks committed en.json as reference so keys absent from committed en.json are automatically excluded from output
- [Phase 05-01]: archiveBrowser.failedToLoadContents parity fix handled automatically — key is in committed en.json and working tree de.json had the German value
- [Phase 05-02]: 05-02: scripts/check-locale-parity.js committed from untracked — CI requires it in git; 17 missing keys auto-fixed in es.json and de.json with English placeholders after parity script caught pre-existing drift
- [Phase 05-locale-file-completion-and-ci-validation]: 05-03: Real Spanish and German translations added for all 12 placeholder backend.* keys — LOC-02 and LOC-03 fully satisfied; no English placeholders remain in any backend.* key
- [Phase 06-01]: SVC-02: Raw stderr_output ternary removed from restore_service.py line 451 — error_message always uses restoreFailedExitCode json.dumps key format; debug info preserved in job.logs
- [Phase 06-01]: SVC-01: backup_service.py confirmed already correct — error_msg pre-assigned as json.dumps; error_parts contains only LOCK_ERROR::, format_error_message(), and json.dumps() items

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 3/4: The 656+ `detail=` site count is a grep count; actual unique keys likely 80-120. Do a domain-by-domain tally at Phase 3 start to right-size locale file work.
- Phase 4: Verify `error_message` column max length can accommodate JSON-encoded `{key, params}` strings before migrating services layer.
- Phase 5: Spanish and German translations for new backend.* keys may need a human reviewer — identify this dependency early.

## Session Continuity

Last session: 2026-03-04
Stopped at: Completed 06-01-PLAN.md — removed raw-stderr ternary from restore_service.py line 451; SVC-01 (backup_service.py confirmed clean) and SVC-02 (restore_service.py line 451 fixed) both satisfied; 1 file modified; requirements SVC-01 and SVC-02 marked complete.
Resume file: None
