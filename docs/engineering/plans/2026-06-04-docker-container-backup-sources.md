# Docker Container Backup Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for implementation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable Docker container backup sources in the backup-plan source chooser with typed metadata and source-level export scripts.

**Architecture:** Docker remains a metadata block on a normal `SourceLocation`; Borg still reads from local, remote, or agent paths. The frontend queues an export staging path plus generated scripts, and the backend normalizes/preserves the `container` block and executes container source scripts through the existing source hook phase.

**Tech Stack:** React, TypeScript, MUI, lucide-react, i18next, Vitest, FastAPI/Pydantic, pytest.

---

## Task 1: Backend Contract

**Files:**

- Modify: `app/utils/source_locations.py`
- Modify: `app/api/source_discovery.py`
- Modify: `tests/unit/test_source_discovery.py`
- Modify: `tests/unit/test_api_backup_plans.py`

- [ ] Write a failing backend normalization/API test that posts a backup plan with `source_locations[0].container` and expects the response and stored JSON to preserve normalized container metadata.
- [ ] Update the source-discovery test to expect Docker containers to be `enabled` and not disabled.
- [ ] Add `normalize_container_config()` beside `normalize_database_config()` with required `container_name`, `backup_mode="export"`, `export_path`, `script_execution_target`, optional script IDs, script parameters, image/display fields, and script order.
- [ ] Call `normalize_container_config()` from `normalize_source_locations()` and preserve the `container` block in normalized locations.
- [ ] Update `_source_types()` so the container option is enabled with precise copy.
- [ ] Run the targeted backend tests and verify they fail before implementation, then pass after implementation.

## Task 2: Source-Level Container Script Execution

**Files:**

- Modify: `app/services/backup_plan_execution_service.py`
- Modify: `tests/unit/test_api_backup_plans.py`

- [ ] Write a failing async execution test that creates a source location with container pre/post script IDs and asserts `source-pre-backup`, backup, then `source-post-backup` order.
- [ ] Add container source-location discovery helpers mirroring the database helpers.
- [ ] Add `_container_script_env_for_location()` with `BORG_UI_CONTAINER_NAME`, `BORG_UI_CONTAINER_DISPLAY_NAME`, `BORG_UI_CONTAINER_IMAGE`, `BORG_UI_CONTAINER_BACKUP_MODE`, `BORG_UI_CONTAINER_EXPORT_DIR`, `BORG_UI_CONTAINER_BACKUP_PATHS`, `BORG_UI_CONTAINER_SCRIPT_EXECUTION_TARGET`, and `BORG_UI_CONTAINER_SOURCE_INDEX`.
- [ ] Extend `_execute_source_scripts()` to merge database and container assignments sorted by execution order and source index.
- [ ] Extend source script remote routing so remote Docker container scripts with `script_execution_target="source"` run on the remote source connection.
- [ ] Run the targeted execution test red/green.

## Task 3: Frontend Types And Payload

**Files:**

- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/utils/backupPlanPayload.ts`
- Modify: `frontend/src/pages/backup-plans/state.ts`
- Modify: `frontend/src/pages/__tests__/BackupPlans.test.tsx`

- [ ] Write a failing payload test that builds a backup plan with `sourceLocations[0].container` and expects trimmed container metadata, source script parameters, and unchanged plan-level script fields.
- [ ] Add `SourceContainerSelection` and optional `container` to `SourceLocation`.
- [ ] Normalize container metadata in `backupPlanPayload.ts`.
- [ ] Normalize container metadata in `state.ts` for edit hydration.
- [ ] Run the payload test red/green.

## Task 4: Source Dialog UI

**Files:**

- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceStep.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/ReviewStep.tsx`
- Modify: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`
- Modify: `frontend/src/pages/backup-plans/__tests__/ReviewStep.test.tsx`

- [ ] Replace the old disabled-container test with a failing test that opens Container, enters a container name, applies, and expects `updateState.sourceLocations[0].container`.
- [ ] Add `container` and `container-detail` view state as needed, or render the container form directly from the Container tab if one screen is sufficient.
- [ ] Enable the Container pivot segment and add count chip support.
- [ ] Add Docker source form controls: source target, SSH/agent picker reuse, container name or ID, optional image label, export staging path, generated script mode.
- [ ] Generate pre/post Docker scripts through existing `onCreateScript` and store resulting IDs/parameters in the container metadata.
- [ ] Show queued Docker sources alongside selected files/databases with a Container icon and remove actions.
- [ ] Update SourceStep summary to show Docker container source kind when all source locations are container sources, and mixed source label when combined.
- [ ] Update ReviewStep to surface container name and export path.
- [ ] Run the SourceStep and ReviewStep targeted tests red/green.

## Task 5: Storybook And Locales

**Files:**

- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.stories.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceStep.stories.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Add or update Storybook state showing a configured Docker container source.
- [ ] Add English source chooser strings for container tab, fields, warnings, script names, and summary/review labels.
- [ ] Add matching locale keys in de/es/it, using clear fallback translations.
- [ ] Run `cd frontend && npm run check:locales`.

## Task 6: Validation And Handoff

**Files:**

- Modify: Linear workpad only after validation results are known.

- [ ] Run targeted backend tests:
  - `pytest tests/unit/test_source_discovery.py::TestSourceDiscovery::test_database_discovery_returns_extensible_source_types -q`
  - `pytest tests/unit/test_api_backup_plans.py -k "container_source" -q`
- [ ] Run targeted frontend tests:
  - `cd frontend && npm test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx -t "configures a Docker container source" --run`
  - `cd frontend && npm test -- src/pages/__tests__/BackupPlans.test.tsx -t "preserves Docker container source metadata" --run`
- [ ] Run required frontend gates:
  - `cd frontend && npm run check:locales`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build`
- [ ] Run required backend gates:
  - `ruff check app tests`
  - `ruff format --check app tests`
- [ ] Run local UI walkthrough using the available dev/smoke path and record evidence in Linear.
- [ ] Commit, push, create/link PR, add `symphony` label, sweep PR feedback/checks, then move Linear to Human Review only when green.
