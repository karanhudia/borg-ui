# Source Selection UI Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild BOR-17 from `origin/main` with a compact source chooser,
database discovery templates, code-editor script drafts, and corrected script
selection density.

**Architecture:** Add a small backend discovery router that returns source type
metadata and database templates. Add a source-selection dialog in the backup
plan wizard that reuses existing path controls and `CodeEditor`, while keeping
the persisted backup-plan payload unchanged.

**Tech Stack:** FastAPI, Pydantic, pytest, React, TypeScript, MUI, TanStack
Query, Vitest, React Testing Library.

---

### Task 1: Backend Source Discovery Contract

**Files:**
- Create: `app/api/source_discovery.py`
- Modify: `app/main.py`
- Test: `tests/unit/test_source_discovery.py`

- [ ] **Step 1: Write backend RED tests**

Create tests that call `GET /api/source-discovery/databases` with admin auth and
assert:

- `source_types` contains enabled `paths`, enabled `database`, and disabled
  `container`.
- Templates include `postgresql`, `mysql`, `mongodb`, and `redis`.
- PostgreSQL contains source directories and both script drafts.
- Every script draft has a non-empty `name`, `description`, `content`, and
  `timeout`.

Run: `pytest tests/unit/test_source_discovery.py -q`
Expected: fail with `404 Not Found` before the router exists.

- [ ] **Step 2: Implement the router**

Create a router with Pydantic models for source types, script drafts, database
items, and the response. Generate conservative local detections by checking
well-known paths with `Path.exists()` and client availability with
`shutil.which()`. Always return templates even when detections are empty.

- [ ] **Step 3: Register the router**

Import `source_discovery` in `app/main.py` and include it at
`/api/source-discovery`.

- [ ] **Step 4: Run backend GREEN tests**

Run: `pytest tests/unit/test_source_discovery.py -q`
Expected: pass.

### Task 2: Frontend API Types

**Files:**
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: Add source discovery types**

Add exported TypeScript interfaces for source type options, script drafts,
database items, and the response.

- [ ] **Step 2: Add API wrapper**

Add `sourceDiscoveryAPI.databases()` returning
`api.get<SourceDiscoveryResponse>('/source-discovery/databases')`.

### Task 3: Script Selector Density Fix

**Files:**
- Modify: `frontend/src/components/ScriptSelectorSection.tsx`
- Modify: `frontend/src/components/__tests__/ScriptSelectorSection.test.tsx`

- [ ] **Step 1: Write frontend RED test for long labels**

Add a test with a long script name and assert the selected combobox exposes the
full script name via text/title or accessible text after selection.

Run:
`cd frontend && npm test -- --run src/components/__tests__/ScriptSelectorSection.test.tsx`
Expected: fail before selector rendering is adjusted.

- [ ] **Step 2: Implement compact long-label rendering**

Render selected values and menu items with a two-line `Box`: script name on the
first line, optional description/metadata on the second line when available.
Use `minWidth: 0`, controlled wrapping, and a `title` attribute for long names.

- [ ] **Step 3: Run selector GREEN test**

Run:
`cd frontend && npm test -- --run src/components/__tests__/ScriptSelectorSection.test.tsx`
Expected: pass.

### Task 4: Source Selection Dialog

**Files:**
- Create: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceStep.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/types.ts`
- Modify: `frontend/src/pages/BackupPlans.tsx`
- Test: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`

- [ ] **Step 1: Write frontend RED tests for the chooser**

Tests should render `SourceStep` with scripts and an `onCreateScript` stub, then
assert:

- The step initially shows a `Choose source` action instead of all path fields
  as the first visual element.
- Opening the chooser shows Files and folders, Database, and Docker containers.
- There is only one Files and folders/manual path route.
- Selecting Database shows compact templates and code-editor-backed script
  drafts.
- Applying a database source calls `updateState` with source directories and
  created/reused script ids.

Run:
`cd frontend && npm test -- --run src/pages/backup-plans/__tests__/SourceStep.test.tsx`
Expected: fail before the dialog exists.

- [ ] **Step 2: Implement dialog structure**

Use `ResponsiveDialog`, MUI outlined cards, chips, tooltips, and compact
spacing. Keep disabled container scanning visible but non-interactive.

- [ ] **Step 3: Reuse path controls**

Move `WizardStepDataSource` and `ExcludePatternInput` behind the Files and
folders route while keeping plan name/description visible in the source step.

- [ ] **Step 4: Implement database flow**

Fetch discovery data with TanStack Query or a contained `useEffect`. Show
detections first, templates second. Use chips and helper text for non-blocking
guidance, not repeated alerts.

- [ ] **Step 5: Implement script draft handling**

Use `CodeEditor` for editable pre/post script drafts. Add radio/segmented style
choices for create/reuse/skip. When creating scripts, call the `onCreateScript`
prop with `category: 'template'` and update wizard state with returned ids.

- [ ] **Step 6: Wire script creation in BackupPlans**

Add a `scriptsAPI.create` mutation and pass an async `createScript` callback to
`SourceStep`. Invalidate `['scripts']` after creation.

- [ ] **Step 7: Run source step GREEN tests**

Run:
`cd frontend && npm test -- --run src/pages/backup-plans/__tests__/SourceStep.test.tsx`
Expected: pass.

### Task 5: Locales and Required Validation

**Files:**
- Modify: `frontend/src/locales/en.json`
- Modify matching keys in `frontend/src/locales/de.json`,
  `frontend/src/locales/es.json`, and `frontend/src/locales/it.json`

- [ ] **Step 1: Add source chooser translation keys**

Add keys for chooser title, source type names, compact helper copy, database
template labels, script draft handling, and apply actions.

- [ ] **Step 2: Run targeted tests**

Run:
`pytest tests/unit/test_source_discovery.py -q`

Run:
`cd frontend && npm test -- --run src/pages/backup-plans/__tests__/SourceStep.test.tsx src/components/__tests__/ScriptSelectorSection.test.tsx src/components/wizard/__tests__/WizardStepDataSource.test.tsx`

- [ ] **Step 3: Run required backend checks**

Run: `ruff check app tests`

Run: `ruff format --check app tests`

- [ ] **Step 4: Run required frontend checks**

Run: `cd frontend && npm run check:locales`

Run: `cd frontend && npm run typecheck`

Run: `cd frontend && npm run lint`

Run: `cd frontend && npm run build`

- [ ] **Step 5: Run runtime walkthrough**

Launch with `./scripts/dev.sh` or a documented smoke runner. Verify
`/backup-plans` loads, source chooser opens, database flow displays templates,
script drafts render in code editors, and applying a source updates the wizard.
