---
phase: 04-backend-services-and-remaining-api-files
plan: "04"
subsystem: backend-services-i18n
tags: [i18n, services, backend, error-messages, locale]
dependency_graph:
  requires: [04-03]
  provides: [SVC-01, SVC-02, SVC-03]
  affects: [ErrorDetailsDialog, backup_service, restore_service, process_utils]
tech_stack:
  added: []
  patterns:
    - json.dumps key format for DB error_message writes
    - line-by-line translateBackendKey rendering in ErrorDetailsDialog
key_files:
  created: []
  modified:
    - frontend/src/locales/en.json
    - frontend/src/locales/es.json
    - frontend/src/locales/de.json
    - app/services/backup_service.py
    - app/services/restore_service.py
    - app/utils/process_utils.py
    - frontend/src/components/ErrorDetailsDialog.tsx
decisions:
  - Error messages in DB use json.dumps key format; ErrorDetailsDialog renders them line-by-line through translateBackendKey for mixed content support
  - Warning appends use newline + json.dumps so LOCK_ERROR:: and borg output lines fall through to raw (Shape 4) rendering
  - LOCK_ERROR:: sentinel in error_parts.append() remains as raw f-string — BackupJobsTable regex depends on it
metrics:
  duration: 3 min
  completed_date: "2026-03-03"
  tasks_completed: 2
  files_modified: 7
---

# Phase 04 Plan 04: Services Layer i18n Migration Summary

Service layer error_message writes migrated from raw English strings to json.dumps key format; ErrorDetailsDialog updated to render via translateBackendKey line-by-line for full i18n chain from DB through frontend.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Add backend.errors.service locale domain (13 keys) to en/es/de | c284c4c | frontend/src/locales/{en,es,de}.json |
| 2 | Migrate service layer + update ErrorDetailsDialog | bd9e3dd | backup_service.py, restore_service.py, process_utils.py, ErrorDetailsDialog.tsx |

## What Was Built

### New Locale Domain

Added `backend.errors.service` domain with 13 keys to all three locale files (en.json, es.json, de.json). Keys cover:
- Backup hook failures (preBackupHooksFailed, postBackupHooksFailed, backupWarningPostHooksFailed)
- Backup/restore with warnings (backupCompletedWithWarning, restoreCompletedWithWarnings)
- Source path failures (failedPrepareSourcePaths, failedCreateDestinationDir)
- Container restart scenarios (containerRestartedDuringBackup, containerRestartedDuringRestore, containerRestartedDuringOperation)
- Warning appends (warningFailedBreakLock, warningRemoteProcessMayBeRunning)
- Execution mode error (unsupportedExecutionMode)

### Service Layer Migration

**backup_service.py (SVC-01):** 5 error_message write sites migrated:
- `preBackupHooksFailed` (with failed/total params)
- `failedPrepareSourcePaths` (static key)
- `postBackupHooksFailed` (with failed/total params)
- `backupCompletedWithWarning` (with exitCode param)
- `backupWarningPostHooksFailed` (with failed/total params)

**restore_service.py (SVC-02):** 4 error_message write sites migrated:
- `unsupportedExecutionMode` (with mode param)
- `failedCreateDestinationDir` (with error param)
- `restoreCompletedWithWarnings` at line 422 (with process.returncode param)
- `restoreCompletedWithWarnings` at line 818 (with literal exitCode: 1 param)

**process_utils.py (SVC-03):** 7 error_message write sites migrated + `import json` added:
- `containerRestartedDuringBackup` (static key)
- `containerRestartedDuringRestore` (static key)
- `containerRestartedDuringOperation` (2 sites, check + compact jobs)
- `warningFailedBreakLock` append (2 sites, newline + json.dumps pattern)
- `warningRemoteProcessMayBeRunning` append (2 sites, newline + json.dumps pattern)

### ErrorDetailsDialog.tsx

Added `import { translateBackendKey } from '../utils/translateBackendKey'` and changed `{job.error_message}` to `.split('\n').map(line => translateBackendKey(line)).join('\n')`. This enables:
- JSON-encoded key lines: translated via translateBackendKey (Shape 2)
- `LOCK_ERROR::` lines: pass through as raw text (Shape 4)
- Borg output lines: pass through as raw text (Shape 4)

## Deviations from Plan

None - plan executed exactly as written.

## Success Criteria Verification

- [x] SVC-01: backup_service.py error_message writes use json.dumps key format
- [x] SVC-02: restore_service.py error_message writes use json.dumps key format
- [x] SVC-03: process_utils.py container restart strings use json.dumps; warning appends use newline + json.dumps pattern
- [x] LOCK_ERROR:: sentinel preserved as raw string (error_parts.append(f"LOCK_ERROR::{repository}") unchanged)
- [x] ErrorDetailsDialog.tsx renders job.error_message through translateBackendKey line-by-line
- [x] backend.errors.service domain with 13 keys in all 3 locale files
- [x] Python syntax check passes for all 3 service files (py_compile verified)
- [x] TypeScript compiles without errors

## Self-Check: PASSED

Files verified:
- FOUND: frontend/src/locales/en.json (service domain present)
- FOUND: frontend/src/locales/es.json (service domain present)
- FOUND: frontend/src/locales/de.json (service domain present)
- FOUND: app/services/backup_service.py (syntax OK, json import present)
- FOUND: app/services/restore_service.py (syntax OK, json import present)
- FOUND: app/utils/process_utils.py (syntax OK, json import present)
- FOUND: frontend/src/components/ErrorDetailsDialog.tsx (translateBackendKey imported and used)

Commits verified:
- FOUND: c284c4c (Task 1 - locale keys)
- FOUND: bd9e3dd (Task 2 - service migration + ErrorDetailsDialog)
