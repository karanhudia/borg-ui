# Source Selection Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a guided backup-plan source-selection flow with database discovery and explicit generated-script handling.

**Architecture:** Add a small backend source-discovery endpoint that returns detected local databases plus templates and script drafts. Add a focused frontend source-selection dialog that applies its output to the existing backup-plan wizard state without changing the backup-plan persistence model.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy auth dependency, React, TypeScript, MUI, React Query, Vitest.

---

## Files

- Create: `app/api/source_discovery.py`
- Modify: `app/main.py`
- Create: `tests/unit/test_source_discovery.py`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/pages/backup-plans/types.ts`
- Modify: `frontend/src/pages/backup-plans/wizard-step/types.ts`
- Modify: `frontend/src/pages/backup-plans/BackupPlanWizardStep.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceStep.tsx`
- Create: `frontend/src/pages/backup-plans/source-discovery/types.ts`
- Create: `frontend/src/pages/backup-plans/source-discovery/SourceSelectionDialog.tsx`
- Create: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

## Task 1: Backend Source Discovery Contract

- [ ] Step 1: Add failing API tests in `tests/unit/test_source_discovery.py`.
  - Assert `GET /api/source-discovery/databases` requires auth.
  - Assert the response includes source type entries for `paths`, `database`, and disabled `container`.
  - Patch scanner helpers so PostgreSQL is detected and assert script drafts plus source directories are returned.
  - Assert templates include PostgreSQL, MySQL, MongoDB, and Redis when no database is detected.

- [ ] Step 2: Run the focused test and confirm it fails because the route does not exist.
  - Command: `pytest tests/unit/test_source_discovery.py -q`
  - Expected: 404 or import failure for the missing endpoint.

- [ ] Step 3: Implement `app/api/source_discovery.py`.
  - Define Pydantic models for source types and database targets.
  - Implement conservative helpers for common data-directory existence, socket existence, and local port checks.
  - Return generated stop/start pre/post script drafts with editable service names.

- [ ] Step 4: Register the router in `app/main.py`.
  - Prefix: `/api/source-discovery`
  - Tags: `Source Discovery`

- [ ] Step 5: Run the focused backend test and keep it green.
  - Command: `pytest tests/unit/test_source_discovery.py -q`

## Task 2: Frontend Source Selection Dialog

- [ ] Step 1: Add failing UI tests in `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`.
  - Render `SourceStep` with minimal wizard state and mocked `sourceDiscoveryAPI.scanDatabases`.
  - Assert initial source directories are not exposed as the first control path until the user opens the chooser.
  - Assert "Choose source" opens the source-selection dialog.
  - Assert choosing database scan displays returned detected/template database choices.
  - Assert applying a database with "create scripts" calls `scriptsAPI.create` with user-editable names and updates source directories plus plan script IDs.
  - Assert files/folders path keeps the existing local/remote path controls available.

- [ ] Step 2: Run the focused frontend test and confirm it fails on missing UI.
  - Command: `cd frontend && npm test -- --run src/pages/backup-plans/__tests__/SourceStep.test.tsx`

- [ ] Step 3: Add frontend source-discovery types and API helper.
  - Add `sourceDiscoveryAPI.scanDatabases()` to `frontend/src/services/api.ts`.
  - Keep response types in `frontend/src/pages/backup-plans/source-discovery/types.ts`.

- [ ] Step 4: Create `SourceSelectionDialog.tsx`.
  - Use `ResponsiveDialog`.
  - Render source type choices with lucide icons.
  - Render database scan results/templates and generated script preview.
  - Render script mode controls: create new scripts, use existing scripts, skip for now.
  - Disable apply when required script names or existing script IDs are missing.

- [ ] Step 5: Rework `SourceStep.tsx`.
  - Keep plan name and description.
  - Replace initial inline source controls with a compact source summary plus "Choose source".
  - Render `WizardStepDataSource` and `ExcludePatternInput` only after path/manual selection or after a database selection has populated paths.
  - On database apply, update `sourceType`, `sourceDirectories`, `preBackupScriptId`, `postBackupScriptId`, and script parameters.

- [ ] Step 6: Pass scripts into `SourceStep`.
  - Extend `BackupPlanWizardStepProps` and `BackupPlanWizardStep.tsx` so `SourceStep` receives `scripts` and `loadingScripts`.

- [ ] Step 7: Add locale keys to English, Spanish, and Italian locale files.
  - Keep translations aligned so `npm run check:locales` passes.

- [ ] Step 8: Run focused frontend tests.
  - Command: `cd frontend && npm test -- --run src/pages/backup-plans/__tests__/SourceStep.test.tsx src/components/wizard/__tests__/WizardStepDataSource.test.tsx`

## Task 3: Validation and Handoff

- [ ] Step 1: Run backend validation.
  - `ruff check app tests`
  - `ruff format --check app tests`
  - `pytest tests/unit/test_source_discovery.py -q`

- [ ] Step 2: Run frontend validation.
  - `cd frontend && npm run check:locales`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run lint`
  - `cd frontend && npm run build`
  - Focused Vitest command from Task 2.

- [ ] Step 3: Run app walkthrough.
  - Launch with `./scripts/dev.sh`.
  - Visit `/backup-plans`.
  - Open create backup plan.
  - Open source chooser.
  - Choose database scan, choose detected database or template, create/reuse scripts, verify source summary and scripts are populated.

- [ ] Step 4: Commit, push, create PR, attach PR, apply `symphony` label, run PR feedback sweep, and move Linear to Human Review only after checks are green.
