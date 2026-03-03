# Requirements: borg-ui i18n Completion

**Defined:** 2026-03-03
**Core Value:** Every user-facing string — whether from the frontend or backend — must be translatable, so users can operate the UI entirely in their own language.

## v1 Requirements

### Frontend Hardcoded String Cleanup

- [x] **FRONT-01**: User sees all toast notifications from Backup.tsx translated (no hardcoded English strings)
- [x] **FRONT-02**: User sees all toast notifications from Restore.tsx translated
- [x] **FRONT-03**: User sees all toast notifications from Repositories.tsx translated
- [x] **FRONT-04**: User sees all toast notifications from Archives.tsx translated
- [x] **FRONT-05**: User sees all toast notifications from SSHConnectionsSingleKey.tsx translated

### Translation Utility

- [x] **UTIL-01**: A `translateBackendKey(error)` utility exists in `frontend/src/utils/` that handles plain-string `detail`, `{key}` object, and `{key, params}` object shapes (backward-compatible during migration)
- [x] **UTIL-02**: All 69 frontend sites using `error.response?.data?.detail` display translated text via the utility instead of raw backend strings
- [x] **UTIL-03**: All frontend sites displaying `data.message` success fields translate the returned key via i18next

### Locale File Structure

- [x] **LOC-01**: A `backend` namespace exists in `en.json` with sub-sections for `errors`, `success`, and `messages` covering all backend-originating strings
- [x] **LOC-02**: All new `backend.*` keys present in `es.json` with Spanish translations
- [x] **LOC-03**: All new `backend.*` keys present in `de.json` with German translations
- [ ] **LOC-04**: en.json, es.json, and de.json contain identical key sets (no drift)

### Backend API Layer Migration

- [x] **BKND-01**: All `HTTPException.detail` strings and `message` response fields in `app/api/auth.py` return translation keys in `{key}` or `{key, params}` format
- [x] **BKND-02**: All `HTTPException.detail` strings and `message` response fields in `app/api/repositories.py` return translation keys
- [x] **BKND-03**: All `HTTPException.detail` strings and `message` response fields in `app/api/backup.py` return translation keys
- [x] **BKND-04**: All `HTTPException.detail` strings and `message` response fields in `app/api/restore.py` return translation keys
- [x] **BKND-05**: All `HTTPException.detail` strings and `message` response fields in `app/api/schedule.py` return translation keys
- [x] **BKND-06**: All `HTTPException.detail` strings and `message` response fields in all remaining API files (settings, users, scripts, ssh, activity, etc.) return translation keys

### Backend Service Layer Migration

- [ ] **SVC-01**: `error_message` fields written by `app/services/backup_service.py` use `{key}` or `{key, params}` format (excluding the `LOCK_ERROR::` sentinel which must remain as-is)
- [ ] **SVC-02**: `error_message` fields written by `app/services/restore_service.py` use `{key}` or `{key, params}` format
- [x] **SVC-03**: `error_message` fields written by `app/utils/process_utils.py` and other services use `{key}` or `{key, params}` format

### Quality and Validation

- [x] **QUAL-01**: i18next `missingKeyHandler` enabled in development mode to log warnings when a key is missing from locale files
- [ ] **QUAL-02**: A CI/local script validates that en.json, es.json, and de.json contain the same key set

## v2 Requirements

### Future Languages

- **LANG-01**: French locale file added (fr.json) with all existing keys
- **LANG-02**: Italian locale file added (it.json) with all existing keys

### Developer Experience

- **DX-01**: Locale files lazy-loaded by language (reduces initial bundle size if it becomes a concern)
- **DX-02**: TypeScript type generation from en.json key structure (type-safe `t()` calls)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Server-side translation (backend returns pre-translated text) | Violates architecture decision: frontend owns all translation. Would require backend to know user locale. |
| Translating log/terminal output | Raw Borg CLI output — system-level strings the backend doesn't own. Explicitly excluded. |
| Adding new languages beyond en/es/de | Stabilize existing three first. New languages multiply any missed keys. |
| `LOCK_ERROR::` prefix in error_message | Machine-readable sentinel used by regex in BackupJobsTable.tsx:331. Must not be translated. |
| Status enum values (running, pending, etc.) | Already handled by frontend `status.*` translation namespace. StatusBadge.tsx is correct. |
| WizardStepIndicator.tsx changes | False positive — renders `step.label` which callers already pass through `t()`. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| FRONT-01 | Phase 1 | Complete |
| FRONT-02 | Phase 1 | Complete |
| FRONT-03 | Phase 1 | Complete |
| FRONT-04 | Phase 1 | Complete |
| FRONT-05 | Phase 1 | Complete |
| UTIL-01 | Phase 1 | Complete |
| UTIL-02 | Phase 1 | Complete |
| UTIL-03 | Phase 1 | Complete |
| LOC-01 | Phase 2 | Complete |
| LOC-02 | Phase 5 | Complete |
| LOC-03 | Phase 5 | Complete |
| LOC-04 | Phase 5 | Pending |
| BKND-01 | Phase 3 | Complete |
| BKND-02 | Phase 3 | Complete |
| BKND-03 | Phase 3 | Complete |
| BKND-04 | Phase 4 | Complete |
| BKND-05 | Phase 4 | Complete |
| BKND-06 | Phase 4 | Complete |
| SVC-01 | Phase 6 | Pending |
| SVC-02 | Phase 6 | Pending |
| SVC-03 | Phase 4 | Complete |
| QUAL-01 | Phase 2 | Complete |
| QUAL-02 | Phase 5 | Pending |

**Coverage:**
- v1 requirements: 22 total
- Mapped to phases: 22
- Unmapped: 0 ✓
- Pending (gap closure): SVC-01 (Phase 6), SVC-02 (Phase 6), LOC-02 (Phase 5), LOC-03 (Phase 5), LOC-04 (Phase 5), QUAL-02 (Phase 5)

---
*Requirements defined: 2026-03-03*
*Last updated: 2026-03-03 after roadmap creation*
