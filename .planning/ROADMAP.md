# Roadmap: borg-ui i18n Completion

## Overview

This milestone completes full internationalization coverage for the borg-ui application. i18next is already initialized and most of the frontend uses `t()`. The remaining work is: (1) fix the last hardcoded frontend strings and build the translation utility that gates all subsequent work, (2) establish the locale file structure so keys are never missing on first use, (3) migrate the high-traffic backend API domains (auth, repositories, backup), (4) migrate the remaining API files and the services layer that writes stored error messages, and (5) finalize Spanish and German translations and lock in CI enforcement to prevent future drift.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Frontend Utility and Hardcoded String Cleanup** - Build translateBackendKey utility and remove all hardcoded English strings from frontend page components
- [x] **Phase 2: Locale File Structure and Key Skeleton** - Establish backend.* namespace in all three locale files and enable dev-mode missing-key detection (completed 2026-03-03)
- [x] **Phase 3: Backend API Migration (Auth + High-Traffic Domains)** - Convert all HTTPException.detail and message fields in auth.py, repositories.py, and backup.py to translation keys (completed 2026-03-03)
- [x] **Phase 4: Backend Services and Remaining API Files** - Migrate restore.py, schedule.py, and all remaining API files plus the services layer that writes stored error_message fields (gap closure in progress) (completed 2026-03-03)
- [ ] **Phase 5: Locale File Completion and CI Validation** - Complete Spanish and German translations for all new backend.* keys and add automated key-sync enforcement

## Phase Details

### Phase 1: Frontend Utility and Hardcoded String Cleanup
**Goal**: The frontend can safely receive and display translated backend messages — whether from the legacy string format or the new key/params format — and all hardcoded English toast strings in page components are gone
**Depends on**: Nothing (first phase)
**Requirements**: FRONT-01, FRONT-02, FRONT-03, FRONT-04, FRONT-05, UTIL-01, UTIL-02, UTIL-03
**Success Criteria** (what must be TRUE):
  1. All toast notifications in Backup.tsx, Restore.tsx, Repositories.tsx, Archives.tsx, and SSHConnectionsSingleKey.tsx display translated text in Spanish and German when the language is switched
  2. A `translateBackendKey` utility exists in `frontend/src/utils/` and correctly handles all four input shapes: plain English string, plain key string, `{key, params}` object, and JSON-encoded object
  3. All 69 `error.response?.data?.detail` call sites in the frontend display translated text through the utility instead of raw backend strings or `[object Object]`
  4. All frontend `data.message` success field call sites display translated text via i18next rather than passing the raw string to toast
**Plans**: 4 plans

### Phase 2: Locale File Structure and Key Skeleton
**Goal**: A `backend` namespace exists in all three locale files with the correct sub-structure, and the development environment warns immediately when a translation key is missing
**Depends on**: Phase 1
**Requirements**: LOC-01, QUAL-01
**Success Criteria** (what must be TRUE):
  1. `en.json`, `es.json`, and `de.json` each contain a top-level `backend` key with sub-sections for `errors`, `success`, and `messages` (with domain groupings: auth, repo, backup, restore, schedule, borg)
  2. The browser console shows a warning when a translation key is missing during development, rather than silently displaying the raw key string
  3. All three locale files have matching key structure within the `backend` namespace (no file has keys absent in another)
**Plans**: 1 plan

Plans:
- [ ] 02-01-PLAN.md — Populate backend namespace in locale files and enable missingKeyHandler

### Phase 3: Backend API Migration (Auth + High-Traffic Domains)
**Goal**: The three highest-traffic backend domains — authentication, repositories, and backup — return translation keys instead of raw English strings, with all new keys present in all three locale files
**Depends on**: Phase 2
**Requirements**: BKND-01, BKND-02, BKND-03
**Success Criteria** (what must be TRUE):
  1. Auth errors (wrong password, user not found, token expired) display translated text in the frontend rather than raw English detail strings
  2. Repository errors and success messages (not found, already exists, created, deleted) display translated text in the frontend
  3. Backup errors and success messages display translated text in the frontend
  4. Dynamic error messages containing variable data (e.g., repository name, file path) use the `{key, params}` pattern and render with the correct interpolated values in all three languages
  5. All new keys introduced in this phase are present in `en.json`, `es.json`, and `de.json` in the same commits (no missing-key warnings in dev console after this phase)
**Plans**: 3 plans

Plans:
- [ ] 03-01-PLAN.md — Migrate auth.py and security.py to translation keys (BKND-01)
- [ ] 03-02-PLAN.md — Migrate backup.py to translation keys (BKND-03)
- [ ] 03-03-PLAN.md — Add 13 new locale keys and migrate repositories.py to translation keys (BKND-02)

### Phase 4: Backend Services and Remaining API Files
**Goal**: All remaining backend API files and the services layer that writes stored `error_message` fields to the database return translation keys, with the `LOCK_ERROR::` sentinel explicitly preserved
**Depends on**: Phase 3
**Requirements**: BKND-04, BKND-05, BKND-06, SVC-01, SVC-02, SVC-03
**Success Criteria** (what must be TRUE):
  1. Restore, schedule, SSH, settings, users, scripts, and activity API errors display translated text in the frontend
  2. Stored `error_message` values written by backup and restore services are key strings (or JSON-encoded `{key, params}` for parameterized messages) and display translated text in ErrorDetailsDialog when rendered
  3. The `LOCK_ERROR::` sentinel in `error_message` continues to be parsed correctly by the regex in `BackupJobsTable.tsx` — the lock path extraction still works
  4. No backend API file returns a raw hardcoded English string in `HTTPException.detail` or `message` fields
**Plans**: 6 plans

Plans:
- [ ] 04-01-PLAN.md — Migrate restore.py and schedule.py to translation keys (BKND-04, BKND-05)
- [ ] 04-02-PLAN.md — Migrate ssh_keys.py and settings.py; establish settings locale domain (BKND-06 partial)
- [ ] 04-03-PLAN.md — Migrate remaining API files (archives, mounts, activity, filesystem, browse, packages, notifications, scripts) (BKND-06 complete)
- [ ] 04-04-PLAN.md — Migrate services layer (backup_service, restore_service, process_utils) and update ErrorDetailsDialog (SVC-01, SVC-02, SVC-03)
- [ ] 04-05-PLAN.md — Gap closure: migrate 13 unmigrated ssh_keys.py message response fields; add 7 new backend.success.ssh keys (BKND-06)
- [ ] 04-06-PLAN.md — Gap closure: fix settings.py key corruption; migrate filesystem.py and scripts_library.py success messages; add filesystem and scripts success locale domains (BKND-06)

### Phase 5: Locale File Completion and CI Validation
**Goal**: All new `backend.*` keys have complete Spanish and German translations (not just English placeholders), and a CI script enforces key-set parity across all three locale files going forward
**Depends on**: Phase 4
**Requirements**: LOC-02, LOC-03, LOC-04, QUAL-02
**Success Criteria** (what must be TRUE):
  1. Switching the UI to Spanish shows proper Spanish translations for all backend-originating error and success messages (no English fallthrough or raw key strings)
  2. Switching the UI to German shows proper German translations for all backend-originating error and success messages
  3. `en.json`, `es.json`, and `de.json` contain identical key sets — verified by running the CI script locally, which exits 0
  4. The CI script fails (non-zero exit) when a key exists in `en.json` but is absent from `es.json` or `de.json`, preventing future divergence
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Frontend Utility and Hardcoded String Cleanup | 4/4 | Complete | 2026-03-03 |
| 2. Locale File Structure and Key Skeleton | 0/1 | Complete    | 2026-03-03 |
| 3. Backend API Migration (Auth + High-Traffic Domains) | 4/4 | Complete   | 2026-03-03 |
| 4. Backend Services and Remaining API Files | 6/6 | Complete   | 2026-03-03 |
| 5. Locale File Completion and CI Validation | 0/? | Not started | - |
