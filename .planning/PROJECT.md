# borg-ui

## What This Is

A web UI for managing Borg backup operations — repositories, scheduled backups, archives, SSH connections, and restore jobs. Built with React/TypeScript frontend and FastAPI/Python backend. Currently adding full internationalization support to make the UI usable in multiple languages.

## Core Value

Every user-facing string — whether from the frontend or backend — must be translatable, so users can operate the UI entirely in their own language.

## Requirements

### Validated

- ✓ Borg backup repository management (create, list, delete, stats) — existing
- ✓ Backup job creation, execution, and status tracking — existing
- ✓ Archive listing and browsing — existing
- ✓ Restore job management — existing
- ✓ Scheduled backup jobs with cron expressions — existing
- ✓ SSH connection management — existing
- ✓ JWT-based authentication (login, logout, user management) — existing
- ✓ i18next initialized in frontend with en/es/de locale files (82 sections) — existing
- ✓ Most frontend components use `t()` for translations — existing
- ✓ Script management and borgmatic import/export — existing
- ✓ Notification support (MQTT, etc.) — existing

### Active

- [ ] All frontend components use `t()` — fix remaining hardcoded strings (WizardStepIndicator and any others found during audit)
- [ ] Backend returns translation keys instead of human-readable English strings for all error messages, success messages, and status values
- [ ] Dynamic backend strings use key + params pattern: `{key: "errors.repo_not_found", params: {name: "myrepo"}}`
- [ ] Frontend translates backend-returned keys using i18next
- [ ] All new backend keys added to en.json, es.json, and de.json locale files

### Out of Scope

- Adding new languages beyond en/es/de — only completing existing coverage
- Translating log output, terminal output, or raw borg CLI output — these are system-level, not UI strings
- Backend locale files or server-side rendering of translated text — frontend owns all translation

## Context

- Locale files: `frontend/src/locales/en.json`, `es.json`, `de.json` (2200+ lines each, 82 sections)
- i18next initialized in `frontend/src/main.tsx`
- Frontend already uses `t()` in 176 files; one confirmed gap: `frontend/src/components/wizard/WizardStepIndicator.tsx`
- Backend currently returns raw English strings in `HTTPException.detail`, response `message` fields, and `status` enum values
- Frontend currently displays raw backend strings directly (e.g. `error.response?.data?.detail`) — these bypass translation

## Constraints

- **Stack**: React/TypeScript frontend + FastAPI/Python backend — no changes to this
- **Languages**: en (primary), es, de — all three must be kept in sync
- **Pattern**: Backend sends keys, frontend translates — no server-side translation

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Backend sends translation keys, not translated text | Keeps all translation logic in one place (frontend/i18next) | — Pending |
| Dynamic strings use key + params object | Preserves variable context for interpolation | — Pending |
| Scope limited to UI strings only | Log/terminal output is system-level, not worth translating | — Pending |

---
*Last updated: 2026-03-03 after initialization*
