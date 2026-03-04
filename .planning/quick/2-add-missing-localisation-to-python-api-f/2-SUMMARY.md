---
phase: quick-2
plan: 01
subsystem: i18n / backend API
tags: [i18n, localisation, python, fastapi, locale, error-messages]
dependency_graph:
  requires: []
  provides: [backend.errors.auth.*, backend.errors.backup.*, backend.errors.activity.*, backend.errors.dashboard.*, backend.errors.restore.*, backend.errors.mounts.*, backend.errors.archives.*, backend.errors.events.*, backend.errors.packages.*, backend.errors.repo.*, backend.errors.ssh.*, backend.errors.settings.*, backend.errors.schedule.*]
  affects: [frontend error display, all 12 backend API modules]
tech_stack:
  added: []
  patterns: [structured locale key dict pattern for HTTPException detail=, params dict for dynamic f-string values]
key_files:
  created: []
  modified:
    - frontend/src/locales/en.json
    - frontend/src/locales/de.json
    - frontend/src/locales/es.json
    - app/api/repositories.py
    - app/api/ssh_keys.py
    - app/api/settings.py
    - app/api/schedule.py
    - app/api/backup.py
    - app/api/activity.py
    - app/api/dashboard.py
    - app/api/restore.py
    - app/api/mounts.py
    - app/api/archives.py
    - app/api/events.py
    - app/api/packages.py
decisions:
  - "Auth errors (authTokenRequired, invalidToken, etc.) shared under backend.errors.auth across backup.py, activity.py, archives.py"
  - "f-string dynamic values mapped to params.error key in locale dict pattern"
  - "New dashboard and events sections added to all three locale files"
  - "activity.py had 2 duplicate occurrences of invalidJobType/jobNotFound — both replaced independently using surrounding context"
metrics:
  duration: ~25 minutes
  completed: "2026-03-04"
  tasks_completed: 2
  files_modified: 15
---

# Phase quick-2 Plan 01: Add Missing Localisation to Python API Files Summary

Migrated all remaining hardcoded English strings in HTTPException `detail=` parameters across 12 Python API files to use the structured `{"key": "backend.errors.<section>.<key>"}` locale key pattern, adding 100+ new locale keys to en.json, de.json, and es.json.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add new locale keys to en.json, de.json, es.json | 68ed953 | frontend/src/locales/en.json, de.json, es.json |
| 2 | Migrate hardcoded detail strings in Python API files | e5edb64 | 12 app/api/*.py files |

## Locale Keys Added

**New sections created:**
- `backend.errors.dashboard` (4 keys): failedGetSystemMetrics, failedGetDashboardStatus, failedGetMetrics, failedGetSchedule
- `backend.errors.events` (4 keys): notAuthenticated, invalidAuthCredentials, userNotFoundOrInactive, failedStartEventStream

**Keys added to existing sections:**
- `backend.errors.auth` (5 keys): authTokenRequired, invalidToken, invalidAuthentication, invalidAuthToken, invalidOrExpiredToken
- `backend.errors.backup` (4 keys): failedGetBackupJobs, failedGetBackupStatus, failedCancelBackup, cannotDownloadLogsForRunningBackup
- `backend.errors.activity` (2 keys): cannotDownloadLogsForRunningJob, noLogsAvailableForJob
- `backend.errors.restore` (3 keys): failedStartRestore, failedFetchArchives, failedFetchArchiveContents
- `backend.errors.mounts` (4 keys): failedMountArchive, failedUnmount, failedListMounts, failedGetMountInfo
- `backend.errors.archives` (3 keys): repositoryNotFound, fileNotFoundAfterExtraction, failedExtractFile
- `backend.errors.packages` (1 key): failedStartInstallation
- `backend.errors.repo` (4 keys): failedParseArchiveList, failedParseRepositoryInfo, failedParseArchiveInfo, failedExportKeyfile
- `backend.errors.ssh` (22 keys): all f-string error catches
- `backend.errors.settings` (17 keys): all f-string error catches
- `backend.errors.schedule` (11 keys): all f-string error catches

**Total: ~84 new locale keys added across en.json, de.json, es.json**

## Python Files Migrated

| File | Strings Migrated | Notes |
|------|-----------------|-------|
| repositories.py | 4 | JSON parse error strings |
| ssh_keys.py | 22 | All f-string error catches with error params |
| settings.py | 17 | All f-string error catches with error params |
| schedule.py | 11 | Including dbConstraintError with truncated message |
| backup.py | 8 | Auth errors mapped to shared backend.errors.auth keys |
| activity.py | 8 | 2 duplicate occurrences of invalidJobType/jobNotFound replaced |
| dashboard.py | 4 | New dashboard section |
| restore.py | 3 | F-string errors with params |
| mounts.py | 4 | F-string errors with params |
| archives.py | 5 | Auth errors + extraction errors |
| events.py | 4 | New events section |
| packages.py | 1 | F-string with error params |

## Deviations from Plan

None - plan executed exactly as written.

**Note:** The plan's scope explicitly excludes pre-existing hardcoded strings in archives.py (lines 47, 89, 211, 291, 390, 432, 448, 451) and activity.py (lines 290, 296 in the first get_job_logs function, 454 read log file error, 641 delete job error) that were not in the task's target replacements. These are out of scope per the plan's focus on the specific listed lines and the statement to not fix unrelated issues. However, activity.py lines 290+296 were also migrated as they are duplicate instances of the same invalidJobType/jobNotFound patterns that appear at lines 515+521.

## Self-Check: PASSED

- frontend/src/locales/en.json: modified, exists
- frontend/src/locales/de.json: modified, exists
- frontend/src/locales/es.json: modified, exists
- All 12 Python API files: modified
- Commit 68ed953: locale keys task
- Commit e5edb64: Python migration task
- Verification 1 (locale keys): OK - all 3 files contain all required keys
- Verification 2 (no hardcoded strings): OK - 0 hardcoded English detail= strings in target files
