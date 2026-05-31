# Database Source Multi-Scripts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or equivalent task-by-task execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let each selected database source carry its own reusable pre/post script assignment and per-source parameter values, instead of forcing database capture into the backup plan's single plan-level script slots.

**Architecture:** Extend the existing `source_locations[].database` JSON contract with `pre_backup_script_id`, `post_backup_script_id`, `pre_backup_script_parameters`, `post_backup_script_parameters`, and `script_execution_order`. Keep global `pre_backup_script_id` and `post_backup_script_id` as plan-level hooks. During execution, run database source pre-scripts in source order before repository work, then run plan-level pre-script, repositories, database source post-scripts, and plan-level post-script.

**Tech Stack:** FastAPI, SQLAlchemy models using existing JSON columns, React/MUI source wizard, Vitest, pytest.

---

### Task 1: Backend Contract And Execution

**Files:**
- Modify: `app/utils/source_locations.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Test: `tests/unit/test_source_locations.py`
- Test: `tests/unit/test_api_backup_plans.py`

- [ ] Add failing tests that `normalize_source_locations()` preserves database script assignment ids and parameters.
- [ ] Add failing tests that a backup plan with two database source locations runs the same generic pre-script twice with different parameter values before repository backup.
- [ ] Normalize database script assignment fields inside `normalize_database_config()`.
- [ ] Add execution helpers that iterate database source locations with script assignments.
- [ ] Refactor plan script execution enough to share one script runner for plan-level and database-source script hooks.
- [ ] Keep failure behavior: any failing database pre-script aborts the plan before repositories; database post-script failure marks the completed run with warning, matching plan-level post-script behavior.

### Task 2: Frontend Payload And Source Selection

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/utils/backupPlanPayload.ts`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Test: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`

- [ ] Add TypeScript fields for database script assignment metadata.
- [ ] Preserve script assignment fields during `buildBackupPlanPayload()`.
- [ ] When adding a database, store selected pre/post script ids and auto-filled parameters on that database source item.
- [ ] For "create scripts", create or reuse generic engine scripts and assign their ids to the database source instead of assigning them to the plan-level script slots.
- [ ] For "reuse scripts", attach the selected scripts to the database source item with auto-filled parameters.
- [ ] Leave plan-level Scripts step fields untouched when database sources are added.

### Task 3: UI Clarity

**Files:**
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/ScriptsStep.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.stories.tsx`

- [ ] Show per-database script assignment summary under selected databases.
- [ ] In the Scripts step, show a compact "Database source scripts" section above plan-level scripts when database sources have assignments.
- [ ] Use compact rows/chips, not nested cards, and keep plan scripts labeled as "Plan scripts".
- [ ] Add/update Storybook states for selected multiple databases with source scripts and the Scripts step database-source summary.
- [ ] Run `cd frontend && npm run snapshots` after story updates.

### Task 4: Verification

**Commands:**
- `.venv311/bin/pytest tests/unit/test_source_locations.py tests/unit/test_api_backup_plans.py -q`
- `cd frontend && eval "$(fnm env --use-on-cd)" && fnm use v22.21.1 && npm test -- SourceStep.test.tsx --run`
- `cd frontend && eval "$(fnm env --use-on-cd)" && fnm use v22.21.1 && npm run typecheck`
- `cd frontend && eval "$(fnm env --use-on-cd)" && fnm use v22.21.1 && npm run check:locales`
- `cd frontend && eval "$(fnm env --use-on-cd)" && fnm use v22.21.1 && npm run snapshots`
- `git diff --check`
