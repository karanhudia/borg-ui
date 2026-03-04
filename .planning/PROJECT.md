# borg-ui

## What This Is

A web UI for managing Borg backup operations — repositories, scheduled backups, archives, SSH connections, and restore jobs. Built with React/TypeScript frontend and FastAPI/Python backend. Full internationalization support shipped in v1.0: all user-facing strings from both frontend and backend are now translatable in English, Spanish, and German.

## Core Value

Every user-facing string — whether from the frontend or backend — is translatable, so users can operate the UI entirely in their own language.

## Requirements

### Validated

- ✓ Borg backup repository management (create, list, delete, stats) — existing
- ✓ Backup job creation, execution, and status tracking — existing
- ✓ Archive listing and browsing — existing
- ✓ Restore job management — existing
- ✓ Scheduled backup jobs with cron expressions — existing
- ✓ SSH connection management — existing
- ✓ JWT-based authentication (login, logout, user management) — existing
- ✓ i18next initialized in frontend with en/es/de locale files — existing
- ✓ Script management and borgmatic import/export — existing
- ✓ Notification support (MQTT, etc.) — existing
- ✓ `translateBackendKey` utility handles all 4 backend string shapes — v1.0
- ✓ All 70+ frontend error/success display sites use `translateBackendKey` — v1.0
- ✓ All backend API files return translation keys (not raw English strings) — v1.0
- ✓ Services layer (backup_service, restore_service, process_utils) writes json.dumps key format — v1.0
- ✓ 223 real Spanish and German translations for all backend.* locale keys — v1.0
- ✓ CI parity enforcement: `check-locale-parity.js` wired into GitHub Actions — v1.0

### Active

_(Next milestone requirements defined when /gsd:new-milestone is run)_

### Out of Scope

- Adding new languages beyond en/es/de — only completing existing coverage
- Translating log output, terminal output, or raw borg CLI output — system-level strings, not UI strings
- Backend locale files or server-side rendering of translated text — frontend owns all translation
- `LOCK_ERROR::` prefix in error_message — machine-readable sentinel, must remain untranslated
- Status enum values (running, pending, etc.) — already handled by frontend `status.*` namespace

## Context

**Current state (post v1.0):**
- Locale files: `frontend/src/locales/en.json`, `es.json`, `de.json` — 2064 keys each, exact parity enforced by CI
- `backend.*` namespace: 223 leaf keys across errors/success/messages domains covering all 16 API files + services layer
- Translation gateway: `frontend/src/utils/translateBackendKey.ts` — 4-shape dispatch via i18n singleton
- ErrorDetailsDialog: renders `error_message` DB field through `translateBackendKey` per-line (supports multi-line with LOCK_ERROR:: sentinel passthrough)
- RestoreJobCard: renders `job.error_message` through `translateBackendKey` on both Alert blocks
- CI: `scripts/check-locale-parity.js` enforces key-set parity; `npm run check:locales` exits 0 on match

**Known tech debt (v1.0):**
- `repositories.py:809` — one low-traffic raw f-string (path deduplication edge case, acknowledged deferral)
- `schedule.py` — `scheduledJobStartedMulti` key emitted without `count` param; frontend uses hardcoded key anyway
- `ssh_keys.py:1439` — raw f-string to `connection.error_message` DB field for "SSH key deleted" state
- `package_service.py:140` — raw English to `job.error_message` (out of v1.0 scope)

## Constraints

- **Stack**: React/TypeScript frontend + FastAPI/Python backend — no changes to this
- **Languages**: en (primary), es, de — all three must be kept in sync
- **Pattern**: Backend sends keys, frontend translates — no server-side translation
- **Sentinel**: `LOCK_ERROR::` in error_message must remain raw (machine-readable for BackupJobsTable.tsx regex)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Backend sends translation keys, not translated text | Keeps all translation logic in one place (frontend/i18next) | ✓ Good — clean separation; no locale knowledge in Python |
| Dynamic strings use `{key, params}` object | Preserves variable context for interpolation | ✓ Good — works with i18next `t(key, params)` natively |
| Scope limited to UI strings only | Log/terminal output is system-level, not worth translating | ✓ Good — raw borg stderr never reaches translateBackendKey |
| `translateBackendKey` uses i18n singleton (not hook) | Required for use outside React components (service layer, utils) | ✓ Good — utility callable anywhere |
| Services write `json.dumps({key})` to DB | Stored error_message must survive round-trips and multi-line joins | ✓ Good — Shape 2 in translateBackendKey handles JSON strings |
| LOCK_ERROR:: sentinel excluded from json.dumps | Machine-readable for BackupJobsTable.tsx regex extraction | ✓ Good — sentinel is Shape 4 passthrough in translateBackendKey |
| Phase 3 line 809 (repositories.py) deferred | Parameterized f-string; low-traffic edge case; clean key design requires research | ⚠️ Revisit — one user-facing 400 raw string remains |
| CI parity script committed to `scripts/` (not `frontend/`) | Script reads all three locale files; belongs at repo root | ✓ Good — `npm run check:locales` calls `node ../scripts/check-locale-parity.js` |

---
*Last updated: 2026-03-04 after v1.0 milestone*
