# Multiple Backup Source Locations Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow one repository or backup plan to combine local source paths and
paths from multiple SSH source machines.

**Architecture:** Add a normalized `source_locations` contract while retaining
legacy single-source fields. Resolve grouped source locations into the existing
local/SSHFS backup path flow. Update the source chooser modal to append grouped
paths by source context instead of forcing one local/remote mode.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite migrations, pytest, React,
TypeScript, MUI, Vitest, React Testing Library.

---

### Task 1: Backend Source Location Contract

**Files:**
- Modify: `app/database/models.py`
- Add: `app/database/migrations/107_add_source_locations.py`
- Modify: `app/api/repositories.py`
- Modify: `app/api/v2/repositories.py`
- Modify: `app/api/backup_plans.py`
- Test: `tests/unit/test_api_repositories.py`
- Test: `tests/unit/test_api_v2_repositories.py`
- Test: `tests/unit/test_api_backup_plans.py`

- [ ] **Step 1: Write RED API tests**

Add tests that post `source_locations` with one local group and two SSH groups
to repository and backup-plan APIs. Assert the response includes
`source_locations`, `source_type` is `mixed`, legacy `source_directories` is
flattened, and single-source legacy payloads still serialize as one location.

Run:
`pytest tests/unit/test_api_repositories.py tests/unit/test_api_v2_repositories.py tests/unit/test_api_backup_plans.py -q`

Expected: fail because request/response models do not expose
`source_locations`.

- [ ] **Step 2: Add model and migration**

Add nullable `source_locations = Column(Text, nullable=True)` to repositories
and backup plans. Migration 107 adds the two columns if missing.

- [ ] **Step 3: Add normalization helpers**

Add helpers that validate locations, trim paths, remove empty paths, require SSH
ids for remote groups, derive legacy groups when `source_locations` is absent,
flatten paths, and calculate legacy mirrors.

- [ ] **Step 4: Wire repository and backup-plan APIs**

Accept optional `source_locations` in create/update payloads. Serialize both
`source_locations` and legacy fields. Keep legacy-only payloads working.

- [ ] **Step 5: Run API GREEN tests**

Run the same pytest command and fix failures before moving on.

### Task 2: Runtime Resolution

**Files:**
- Modify: `app/services/backup_service.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Test: `tests/unit/test_backup_service_mocks.py`
- Test: `tests/unit/test_api_backup_plans.py`

- [ ] **Step 1: Write RED runtime tests**

Add a backup-service test that passes grouped source locations with two SSH
connections and one local path. Assert `_prepare_source_paths` receives SSH URLs
for each remote connection plus the local path, and that no single source
connection id is forced for all paths.

- [ ] **Step 2: Resolve grouped locations**

Add an optional `source_locations` argument to `execute_backup`. Convert grouped
locations into source paths before the existing SSHFS preparation call. For
grouped remote sources, call `_prepare_source_paths(..., source_connection_id=None)`
so it groups by parsed SSH host/user/port.

- [ ] **Step 3: Propagate plan context**

Include `source_locations` in plan run context, script environment, and backup
job execution calls. Preserve legacy flattened env variables.

- [ ] **Step 4: Run runtime GREEN tests**

Run:
`pytest tests/unit/test_backup_service_mocks.py tests/unit/test_api_backup_plans.py -q`

### Task 3: Frontend Types and Payloads

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/utils/backupPlanPayload.ts`
- Modify: `frontend/src/pages/backup-plans/state.ts`
- Modify: `frontend/src/pages/backup-plans/types.ts`
- Modify: `frontend/src/components/RepositoryWizard.tsx`

- [ ] **Step 1: Write RED payload tests**

Add Vitest coverage showing a backup-plan state with local plus two SSH source
locations produces a payload with `source_locations`, `source_type: mixed`, and
flattened `source_directories`.

- [ ] **Step 2: Add TypeScript source location types**

Define reusable `SourceLocation` and `SourceType` types and add
`source_locations` to repository and backup-plan data.

- [ ] **Step 3: Update state conversion**

Initialize state with empty `sourceLocations`. Convert legacy plans/repos into a
single source location and keep legacy fields derived for compatibility.

- [ ] **Step 4: Run payload GREEN tests**

Run the targeted Vitest tests for payload/state conversion.

### Task 4: Grouped Source Directory Modal

**Files:**
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceStep.tsx`
- Modify: `frontend/src/components/wizard/WizardStepDataSource.tsx`
- Modify: `frontend/src/components/SourceDirectoriesInput.tsx`
- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Test: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`
- Test: `frontend/src/components/wizard/__tests__/WizardStepDataSource.test.tsx`
- Test: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`

- [ ] **Step 1: Write RED UI tests**

Tests should open the backup-plan source chooser, select local and multiple SSH
source contexts, add paths to each group, and assert the summary keeps all
groups visible. Repository wizard tests should submit grouped source locations.

- [ ] **Step 2: Implement grouped input**

Replace the one-mode source directory picker with a grouped source location
input that uses outlined surfaces, source chips, icon buttons, and labeled
manual path entry. Browsing uses the currently selected group context.

- [ ] **Step 3: Preserve database source flow**

When applying a database source, set a single local source location for the
database dump paths and keep script behavior unchanged.

- [ ] **Step 4: Update summaries and review**

Render grouped source summaries in the source step, repository wizard review,
and backup-plan review without oversized cards or heavy accent borders.

- [ ] **Step 5: Run UI GREEN tests**

Run:
`cd frontend && npm test -- --run src/pages/backup-plans/__tests__/SourceStep.test.tsx src/components/wizard/__tests__/WizardStepDataSource.test.tsx src/components/__tests__/RepositoryWizard.test.tsx`

### Task 5: Validation and Handoff

**Files:**
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`
- Modify: `.github/PULL_REQUEST_TEMPLATE.md` only as read-only template input

- [ ] **Step 1: Add locale keys**

Add labels and helper copy for source groups, local source, SSH source, selected
paths, remove group/path, and browse current source.

- [ ] **Step 2: Run required backend checks**

Run:
`ruff check app tests`

Run:
`ruff format --check app tests`

Run targeted pytest files changed by this work.

- [ ] **Step 3: Run required frontend checks**

Run:
`cd frontend && npm run check:locales`

Run:
`cd frontend && npm run typecheck`

Run:
`cd frontend && npm run lint`

Run:
`cd frontend && npm run build`

- [ ] **Step 4: Runtime walkthrough**

Launch Borg UI locally. Create or update a backup plan with one local source
group and two SSH source groups through the source directory modal. Save,
reload, and confirm all groups persist in the UI and API response.

- [ ] **Step 5: PR**

Commit only scoped files, push a fresh branch, create a PR with the repository
template, attach it to Linear, sweep feedback/checks, and move the issue to
Human Review only when the completion bar is met.
