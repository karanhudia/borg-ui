# Pro Plan Content Gating Implementation Plan

**Goal:** Gate every shipped runtime feature currently marked as Pro in plan content but not enforced in app feature maps.

**Architecture:** Treat `app/core/features.py` and `frontend/src/core/features.ts` as the enforcement maps for plan-content runtime features. Backend API routes reject Pro-only operations for Community plans; frontend surfaces use existing plan-gating behavior and disabled controls instead of new gate UI.

**Tech Stack:** FastAPI, SQLAlchemy-backed licensing state, React, MUI, Vitest, pytest.

---

## Files

- Modify `app/core/features.py` and `frontend/src/core/features.ts` to add feature IDs for `database_discovery`, `container_backups`, `backup_reports`, and `alerting_monitoring`.
- Modify `app/api/source_discovery.py` to require `database_discovery` for database discovery/scanning and `container_backups` for Docker container scanning.
- Modify `app/api/settings.py` and/or `app/services/backup_monitoring_service.py` to block Community writes/actions for `alerting_monitoring` and `backup_reports`.
- Modify `frontend/src/pages/BackupPlans.tsx`, `BackupPlanWizardStep.tsx`, `SourceStep.tsx`, and `SourceSelectionDialog.tsx` so database and container source tabs are gated from plan state.
- Modify `frontend/src/components/MonitoringReportsTab.tsx` so monitoring and report controls are gated with existing Borg UI gating primitives.
- Update `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.stories.tsx` and `frontend/src/components/MonitoringReportsTab.stories.tsx` with Community gated states.
- Add/update tests in `tests/unit/test_core_features.py`, `tests/unit/test_source_discovery.py`, `tests/unit/test_api_settings_routes.py`, `tests/unit/test_api_backup_plans.py`, `frontend/src/pages/backup-plans/__tests__/SourceStep.gating.test.tsx`, and `frontend/src/components/__tests__/MonitoringReportsTab.test.tsx`.

## Tasks

- [x] Write backend RED tests that Community cannot access database discovery/scanning, container scanning, backup monitoring actions, report actions, or enable Pro-only settings.
- [x] Write frontend RED tests that Community sees gated database/container source tabs and gated monitoring/report controls.
- [x] Add the four missing feature IDs to backend/frontend feature maps.
- [x] Add backend enforcement at source-discovery and settings/report action boundaries.
- [x] Thread plan access booleans through the backup-plan source wizard and disable/replace Pro-only source views using shared gate affordances.
- [x] Gate monitoring and report settings sections with shared `PlanGate` behavior while leaving read-only context visible.
- [x] Add Storybook stories for the new gated UI states.
- [x] Run targeted tests, frontend required checks, backend required checks, and runtime proof before handoff.

## Audit Notes

- Already gated/enforced: `borg_v2`, `backup_plan_multi_repository`, `backup_plan_mixed_sources`, `rclone`, `managed_agents`, `remote_clients`, and `extra_users`.
- Newly in scope: `database_discovery`, `container_backups`, `backup_reports`, and `alerting_monitoring`.
- Audited but not a local feature gate: `pro_server_seats`, because it is licensing entitlement policy rather than a specific UI/API operation in this repository.
