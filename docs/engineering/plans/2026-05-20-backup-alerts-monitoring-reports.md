# Backup Alerts, Monitoring, and Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable stale-backup monitoring and scheduled backup health reports delivered through existing Apprise notification services.

**Architecture:** Persist global monitoring/report settings on `SystemSettings`, add Apprise trigger flags to `NotificationSettings`, and isolate stale detection/report composition in a backend service called by the shared scheduler and manual settings endpoints. Add a system-managed Settings tab for controls and update notification service UI for the new event triggers.

**Tech Stack:** Python/FastAPI/SQLAlchemy/pytest backend, React/Vite/MUI/TanStack Query/Vitest/Storybook frontend.

---

### Task 1: Backend Models, Migrations, and API Contracts

**Files:**
- Modify: `app/database/models.py`
- Create: `app/database/migrations/111_add_backup_monitoring_reports.py`
- Modify: `app/api/settings.py`
- Modify: `app/api/notifications.py`
- Test: `tests/unit/test_api_settings_routes.py`
- Test: `tests/unit/test_api_notifications.py`

- [ ] Add failing API tests that assert `/api/settings/system` includes default monitoring/report settings, `PUT /api/settings/system` persists valid values, invalid monitoring/report values are rejected, notification settings include `notify_on_stale_backup`, and notification settings include `notify_on_backup_report`.
- [ ] Run the targeted tests and confirm they fail because the fields do not exist yet.
- [ ] Add SQLAlchemy model columns and migration defaults for system monitoring/report settings and notification event flags.
- [ ] Add pydantic request/update/response handling in settings and notifications APIs.
- [ ] Run the targeted tests and confirm they pass.

### Task 2: Monitoring and Report Service

**Files:**
- Create: `app/services/backup_monitoring_service.py`
- Modify: `app/services/notification_service.py`
- Modify: `app/api/settings.py`
- Modify: `app/api/schedule.py`
- Test: `tests/unit/test_backup_monitoring_service.py`
- Test: `tests/unit/test_schedulers.py`
- Test: `tests/unit/test_api_settings_routes.py`

- [ ] Add failing service tests for stale repository selection, observe-only inclusion, alert cooldown, daily/weekly/monthly report due windows, and report content selection.
- [ ] Add failing API tests for manual monitoring run and manual report send.
- [ ] Add failing scheduler test that the shared scheduler invokes backup monitoring/report scheduling each cycle.
- [ ] Implement the monitoring/report service with deterministic helpers and Apprise dispatch methods.
- [ ] Add `NotificationService.send_stale_backup_alert` and `NotificationService.send_backup_report`.
- [ ] Wire manual settings endpoints and the shared scheduler loop.
- [ ] Run the targeted tests and confirm they pass.

### Task 3: Frontend Settings and Notification UI

**Files:**
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/components/AppSidebar.tsx`
- Modify: `frontend/src/components/AppHeader.tsx`
- Create: `frontend/src/components/MonitoringReportsTab.tsx`
- Modify: `frontend/src/components/NotificationsTab.tsx`
- Modify: `frontend/src/components/NotificationCard.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`
- Test: `frontend/src/pages/__tests__/Settings.monitoring.test.tsx`
- Test: `frontend/src/components/__tests__/NotificationsTab.test.tsx`

- [ ] Add failing Vitest tests for rendering `/settings/monitoring`, saving monitoring/report payloads, manual check/report actions, and notifications payloads containing the new event toggles.
- [ ] Implement API types and methods for manual monitoring/report actions.
- [ ] Add the Monitoring & Reports tab and navigation entries gated by `settings.system.manage`.
- [ ] Update notification form/card categories for stale-backup alerts and backup reports.
- [ ] Add locale keys across all locale files.
- [ ] Run targeted Vitest tests and locale parity check.

### Task 4: Storybook and Snapshot Coverage

**Files:**
- Create: `frontend/src/components/MonitoringReportsTab.stories.tsx`
- Modify: `frontend/storybook-snapshots/*`

- [ ] Add a story showing enabled monitoring and weekly reports.
- [ ] Run `cd frontend && npm run snapshots`.
- [ ] Commit the generated snapshot image(s).

### Task 5: Full Validation, Runtime Proof, and Handoff

**Files:**
- Modify as needed from prior tasks.

- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run targeted backend pytest suites.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run targeted frontend Vitest suites.
- [ ] Launch Borg UI locally and record Settings -> Monitoring & Reports walkthrough evidence.
- [ ] Commit, push, open PR with the template, add `symphony` label, run PR feedback sweep, and move Linear to Human Review only when checks are green.
