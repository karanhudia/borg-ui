# Database Source Preservation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Use superpowers:test-driven-development for every behavior change and superpowers:verification-before-completion before claiming completion.

**Goal:** Make database source selections behave like durable source picks in the backup-plan source chooser, including preserved tab state, source-machine-aware dump paths, source-aware plan scripts, advanced original-path mode, and less prominent templates.

**Architecture:** Preserve database metadata on `source_locations`, while keeping `database_template_id` as a compatibility field. The frontend queues database sources in the Database tab and applies all queued sources through the same final dialog action as file paths. The backend preserves database metadata, injects `BORG_UI_DB_*` script variables, and executes database plan scripts on the selected source machine for remote SSH database sources. When multiple generated database templates are queued, the frontend creates one plan-level pre/post script pair with one environment-scoped block per database.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic-style dict validation, pytest, React, TypeScript, MUI, Vitest, Storybook snapshots, i18next locale files.

---

## Design Specs and Embedded Mockups

Design source of truth:

- `impeccable`: follow Borg UI product register, restrained MUI surfaces, `ResponsiveDialog`, shared selectors, balanced borders, no heavy left accents, factual copy.
- `ui-ux-pro-max`: apply active tab visibility, accessible alert/error messaging, contrast, color-plus-text selected states, and stable React state structure. Ignore the generated funnel/dark-mode palette because this is an existing Borg UI product surface.

### Mockup 1: Database Tab After Scan

```text
Choose backup source

[ Files 2 ] [ Database ] [ Container soon ]

Scan target
  (o) Borg UI server     ( ) Remote machine

Paths to scan                         [Re-scan]
  [/var/lib/postgresql x] [/var/lib/mysql x] [/srv/db x]

Detected databases
  +-------------------+  +-------------------+
  | PostgreSQL        |  | SQLite            |
  | /var/lib/post...  |  | /srv/db/app.db    |
  | [Detected]        |  | [Detected]        |
  +-------------------+  +-------------------+

[Show templates]

Footer: [Cancel] [Use these paths]
```

Notes:

- Templates are collapsed by default because detections are the primary path.
- The selected tab chip appears only after a source has actually been queued.
- `Use these paths` remains the only dialog-closing apply action.

### Mockup 2: Database Detail, Dump Mode

```text
< Back    PostgreSQL database

[PostgreSQL] [logical dump] [Detected]

Source and backup path
  Source machine       backup-a@server-a.example
  Live database path   /var/lib/postgresql
  Dump path            /var/tmp/borg-ui/database-dumps/postgresql
  Borg will back up    /var/tmp/borg-ui/database-dumps/postgresql

Capture mode
  (o) Dump to staging path, recommended
      Generate or reuse plan scripts that write a safe dump before Borg runs.
  ( ) Back up original path, advanced

Dump path
  [/var/tmp/borg-ui/database-dumps/postgresql               Browse]

Scripts
  (o) Create generated scripts   ( ) Reuse scripts   ( ) Skip scripts
  Pre-backup script name   [Prepare PostgreSQL dump]
  [CodeEditor: pg_dump writes to "$BORG_UI_DB_DUMP_DIR"]
  Post-backup script name  [Clean PostgreSQL dump]
  [CodeEditor: rm -rf "$BORG_UI_DB_DUMP_DIR"]

Footer: [Cancel] [Add database]
```

Notes:

- The detail panel explicitly separates live source path, dump path, and final
  Borg path.
- `Add database` queues the selection and returns to the Database tab.
- The path is on the scan target machine. For remote scan targets, the dump path
  is a remote path.

### Mockup 3: Database Detail, Original Path Mode

```text
Capture mode
  ( ) Dump to staging path, recommended
  (o) Back up original path, advanced

Warning
  Borg will read the live database path directly. Use this only when the
  database is stopped, snapshotted, or you have an existing hook that makes the
  files consistent.

Source and backup path
  Source machine       backup-a@server-a.example
  Live database path   /var/lib/postgresql
  Borg will back up    /var/lib/postgresql

Scripts
  ( ) Create generated scripts   (o) Reuse scripts   ( ) Skip scripts
```

Notes:

- Original-path mode is intentionally behind the advanced choice.
- Generated dump scripts are not default in original mode because Borg reads the
  original path.

### Mockup 4: Reopened Dialog With Selection

```text
Choose backup source

[ Files 1 ] [ Database 2 ] [ Container soon ]

Selected databases
  PostgreSQL database
  Source machine: backup-a@server-a.example
  Live path:      /var/lib/postgresql
  Borg path:      /var/tmp/borg-ui/database-dumps/postgresql
  Capture mode:   Dump to staging path
  [Edit database] [Remove]

  MySQL database
  Source machine: backup-a@server-a.example
  Borg path:      /var/tmp/borg-ui/database-dumps/mysql
  Capture mode:   Dump to staging path
  [Edit database] [Remove]

Detected databases
  PostgreSQL    selected
  MySQL         available

[Show templates]
```

Notes:

- The user sees the same model they selected before, not a plain file path.
- Removing a database decrements the Database tab count and removes only that
  database's metadata.

---

## File Map

- Modify: `frontend/src/types/index.ts`
  - Add database metadata types on `SourceLocation`.
- Modify: `frontend/src/utils/backupPlanPayload.ts`
  - Preserve database metadata through payload normalization.
- Modify: `frontend/src/pages/backup-plans/state.ts`
  - Preserve database metadata when hydrating plans into wizard state.
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
  - Queue database selections, add capture mode UI, collapse templates, restore saved state.
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceStep.tsx`
  - Use database metadata for summary and expanded rows instead of path-prefix inference.
- Modify: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`
  - Cover queueing, tab counts, remote source target, original mode, reopening, and clearing metadata.
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.stories.tsx`
  - Add selected database, original-path mode, and collapsed-template stories.
- Modify: `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`
  - Add source chooser copy.
- Modify: `app/utils/source_locations.py`
  - Preserve and validate database metadata in source locations.
- Modify: `app/api/backup_plans.py`
  - Store and serialize database metadata in source locations and keep `database_template_id`.
- Modify: `app/services/backup_plan_execution_service.py`
  - Inject database env vars and route remote database plan scripts to SSH execution.
- Modify: `app/api/source_discovery.py`
  - Ensure generated script drafts use `BORG_UI_DB_*` variables.
- Modify: `tests/unit/test_source_locations.py`
  - Cover database metadata preservation and invalid shape rejection.
- Modify: `tests/unit/test_api_backup_plans.py`
  - Cover create/read/update with database source metadata and remote source target.
- Modify: `tests/unit/test_source_discovery.py`
  - Cover generated script variable usage.
- Modify: `docs/usage-guide.md`
  - Document database source selection, dump mode, original mode.
- Modify: `docs/script-parameters.md`
  - Document new `BORG_UI_DB_*` variables.
- Generated: `frontend/storybook-snapshots/*source-selection-dialog*.png`
  - Required after story updates.

---

## Task 1: Preserve Database Metadata in Source Locations

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/utils/backupPlanPayload.ts`
- Modify: `frontend/src/pages/backup-plans/state.ts`
- Modify: `app/utils/source_locations.py`
- Modify: `app/api/backup_plans.py`
- Test: `tests/unit/test_source_locations.py`
- Test: `tests/unit/test_api_backup_plans.py`

- [ ] **Step 1: Write failing backend metadata tests**

  Add tests to `tests/unit/test_source_locations.py`:

  ```python
  def test_preserves_database_source_metadata():
      location = {
          "source_type": "remote",
          "source_ssh_connection_id": 11,
          "paths": ["/var/tmp/borg-ui/database-dumps/postgresql"],
          "database": {
              "template_id": "postgresql",
              "engine": "PostgreSQL",
              "display_name": "PostgreSQL database",
              "backup_strategy": "logical_dump",
              "detected_source_path": "/var/lib/postgresql",
              "detection_label": "backup-a@server-a.example",
              "capture_mode": "dump",
              "dump_path": "/var/tmp/borg-ui/database-dumps/postgresql",
              "backup_paths": ["/var/tmp/borg-ui/database-dumps/postgresql"],
              "script_execution_target": "source",
          },
      }

      assert normalize_source_locations([location])[0]["database"] == location["database"]
  ```

  Add an invalid capture-mode test that expects `ValueError`.

- [ ] **Step 2: Run backend tests and confirm RED**

  Run:

  ```bash
  DATA_DIR=/tmp/borg-ui-test .venv/bin/pytest tests/unit/test_source_locations.py -q
  ```

  Expected: metadata test fails because `normalize_source_locations()` drops the
  `database` field.

- [ ] **Step 3: Add frontend type contract**

  In `frontend/src/types/index.ts`, add:

  ```ts
  export type DatabaseCaptureMode = 'dump' | 'original'

  export interface SourceDatabaseSelection {
    template_id: string
    engine: string
    display_name: string
    backup_strategy: string
    detected_source_path: string | null
    detection_label: string | null
    capture_mode: DatabaseCaptureMode
    dump_path: string | null
    backup_paths: string[]
    script_execution_target: 'source' | 'server'
  }
  ```

  Add `database?: SourceDatabaseSelection` to `SourceLocation`.

- [ ] **Step 4: Preserve metadata in backend normalization**

  In `app/utils/source_locations.py`, add a helper that validates only the
  expected `database` fields and returns a cleaned object. Preserve it on the
  normalized location when present.

- [ ] **Step 5: Preserve metadata in frontend normalization**

  Update `normalizeSourceLocations()` in `frontend/src/utils/backupPlanPayload.ts`
  and `normalizePlanSourceLocations()` in `frontend/src/pages/backup-plans/state.ts`
  so `database` metadata is copied when present.

- [ ] **Step 6: Run metadata tests and confirm GREEN**

  Run:

  ```bash
  DATA_DIR=/tmp/borg-ui-test .venv/bin/pytest tests/unit/test_source_locations.py tests/unit/test_api_backup_plans.py -q
  cd frontend && npm run test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx
  ```

---

## Task 2: Queue Database Selection Without Closing the Dialog

**Files:**
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`
- Modify: `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`

- [ ] **Step 1: Write failing UI tests**

  Add tests proving:

  - Clicking a detected database opens detail.
  - Clicking `Add database` does not close the dialog.
  - The Database tab has a selected count.
  - `updateState` is not called until `Use these paths`.
  - A remote scan target produces a remote `sourceLocation`.

  Use assertions like:

  ```ts
  fireEvent.click(screen.getByRole('button', { name: /add database/i }))

  expect(screen.getByRole('dialog')).toBeInTheDocument()
  expect(screen.getByRole('tab', { name: /database.*1/i })).toHaveAttribute(
    'aria-selected',
    'true'
  )
  expect(updateState).not.toHaveBeenCalled()
  ```

- [ ] **Step 2: Run UI tests and confirm RED**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx
  ```

  Expected: the test fails because `applyDatabase()` closes the dialog and
  calls `updateState`.

- [ ] **Step 3: Replace terminal apply with queued selection**

  In `SourceSelectionDialog.tsx`:

  - Replace `databasePickCount` and `databaseQuickPickTemplateId` with a derived
    selected database draft object.
  - Add a function that converts `selectedDatabase`, `scanTarget`, capture mode,
    detected source, and dump path into a `SourceLocation`.
  - `Add database` updates `draftSourceLocations`, stores database metadata, and
    sets `view` back to `database`.
  - `Add database` does not call `updateState` and does not call `onClose`.
  - `applyPaths()` includes `databaseTemplateId` from selected database metadata.

- [ ] **Step 4: Keep tab counts derived**

  Derive tab counts from `draftSourceLocations`:

  - `database`: count locations with `location.database`.
  - `files`: count paths in locations without `location.database`.

  This avoids stale count state when a path is removed.

- [ ] **Step 5: Run UI tests and confirm GREEN**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx
  ```

---

## Task 3: Add Capture Mode and Path Clarity UI

**Files:**
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`
- Modify: `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`

- [ ] **Step 1: Write failing tests for capture mode**

  Add tests proving:

  - Dump mode is selected by default.
  - Dump mode stores the dump path as `paths[0]`.
  - Original mode stores `detected_source_path` as `paths[0]`.
  - Original mode shows a warning.

  Use assertions like:

  ```ts
  expect(screen.getByRole('radio', { name: /dump to staging path/i })).toBeChecked()
  fireEvent.click(screen.getByRole('radio', { name: /back up original path/i }))
  expect(screen.getByText(/Borg will read the live database path directly/i)).toBeInTheDocument()
  ```

- [ ] **Step 2: Run tests and confirm RED**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx
  ```

- [ ] **Step 3: Implement capture mode state**

  Add local detail state:

  ```ts
  const [databaseCaptureMode, setDatabaseCaptureMode] =
    useState<DatabaseCaptureMode>('dump')
  const [databaseDumpPath, setDatabaseDumpPath] = useState('')
  ```

  On `chooseDatabase()`, set dump path from `database.source_directories[0]` and
  default capture mode to `dump`.

- [ ] **Step 4: Render the path clarity block**

  In database detail, render source machine, live database path, dump path, and
  final Borg backup path. Use existing MUI `Box`, `Stack`, `Typography`, `Chip`,
  `Alert`, and `PathSelectorField`; avoid nested cards and heavy accent borders.

- [ ] **Step 5: Add advanced original mode warning**

  Show an MUI warning `Alert` only when `capture_mode === 'original'`. The copy
  should be factual and short.

- [ ] **Step 6: Run tests and confirm GREEN**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx
  ```

---

## Task 4: Make Database Plan Scripts Source-Aware

**Files:**
- Modify: `app/api/source_discovery.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Modify: `tests/unit/test_source_discovery.py`
- Modify: `tests/unit/test_api_backup_plans.py`
- Modify: `docs/script-parameters.md`

- [ ] **Step 1: Write failing source-discovery script draft tests**

  In `tests/unit/test_source_discovery.py`, assert generated scripts use
  `BORG_UI_DB_DUMP_DIR` and do not hardcode their dump directory except as a
  fallback default.

- [ ] **Step 2: Write failing plan-script env tests**

  In `tests/unit/test_api_backup_plans.py`, add a plan run with a database
  source location and monkeypatch `execute_script`. Assert the env contains:

  ```python
  assert env["BORG_UI_DB_TEMPLATE_ID"] == "postgresql"
  assert env["BORG_UI_DB_CAPTURE_MODE"] == "dump"
  assert env["BORG_UI_DB_SOURCE_PATH"] == "/var/lib/postgresql"
  assert env["BORG_UI_DB_DUMP_DIR"] == "/var/tmp/borg-ui/database-dumps/postgresql"
  assert json.loads(env["BORG_UI_DB_BACKUP_PATHS"]) == [
      "/var/tmp/borg-ui/database-dumps/postgresql"
  ]
  ```

- [ ] **Step 3: Write failing remote script target test**

  Add a test with `source_type="remote"` and database metadata where
  `_execute_plan_script()` should call a new remote execution helper instead of
  local `execute_script`.

- [ ] **Step 4: Run backend tests and confirm RED**

  Run:

  ```bash
  DATA_DIR=/tmp/borg-ui-test .venv/bin/pytest tests/unit/test_source_discovery.py tests/unit/test_api_backup_plans.py -q
  ```

- [ ] **Step 5: Update generated scripts**

  In `app/api/source_discovery.py`, update template drafts to use:

  ```bash
  DUMP_DIR="${BORG_UI_DB_DUMP_DIR:-/var/tmp/borg-ui/database-dumps/postgresql}"
  ```

  Keep engine-specific database name variables such as `POSTGRES_DB`,
  `MYSQL_DATABASE`, `MONGODB_URI`, `REDIS_CLI_ARGS`, and
  `SQLITE_DATABASE_PATH`.

- [ ] **Step 6: Inject database environment variables**

  In `backup_plan_execution_service._execute_plan_script()`, read the first
  source location with `database` metadata and update `script_env` with
  `BORG_UI_DB_*` variables before script parameters are injected.

- [ ] **Step 7: Execute remote database scripts on the source host**

  Add a focused helper in `backup_plan_execution_service.py` that:

  - Resolves the source `SSHConnection` and `SSHKey`.
  - Writes the temporary key with existing SSH utilities.
  - Executes the script with `ssh user@host bash -s`, passing environment values
    safely.
  - Captures stdout, stderr, and exit code into the same `ScriptExecution`
    record flow as local scripts.

- [ ] **Step 8: Run backend tests and confirm GREEN**

  Run:

  ```bash
  DATA_DIR=/tmp/borg-ui-test .venv/bin/pytest tests/unit/test_source_discovery.py tests/unit/test_api_backup_plans.py -q
  ```

---

## Task 5: Restore Dialog State and Summary From Metadata

**Files:**
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceStep.tsx`
- Modify: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`

- [ ] **Step 1: Write failing reopen tests**

  Add tests proving a saved database source opens the dialog on the Database tab
  with the selected database details, source target, capture mode, and paths
  restored from metadata.

- [ ] **Step 2: Write failing summary tests**

  Add tests proving:

  - Database summary uses `location.database`, not `/var/tmp` path inference.
  - Original-path mode still shows `Database scan` in the summary.
  - Replacing the source with files clears database metadata and summary.

- [ ] **Step 3: Run tests and confirm RED**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx
  ```

- [ ] **Step 4: Hydrate selected database state from metadata**

  On dialog open:

  - Find the first `sourceLocation.database`.
  - Set `view` to `database`.
  - Set scan target from the source location.
  - Populate selected database display values from metadata.
  - Restore capture mode and dump path.

- [ ] **Step 5: Update SourceStep summary**

  In `SourceStep.tsx`, set `isDatabaseSource` from
  `sourceLocations.some((location) => location.database)` and display database
  source details in expanded rows when metadata exists.

- [ ] **Step 6: Run tests and confirm GREEN**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx
  ```

---

## Task 6: Collapse Templates and Update Stories

**Files:**
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.stories.tsx`
- Modify: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`
- Generated: `frontend/storybook-snapshots/*source-selection-dialog*.png`

- [ ] **Step 1: Write failing collapsed-template test**

  Add a test proving templates are hidden while detections are visible, then
  appear after clicking `Show templates`.

- [ ] **Step 2: Run test and confirm RED**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx
  ```

- [ ] **Step 3: Implement template collapse state**

  Add local `showDatabaseTemplates` state. Default it to false when detections
  exist. Reset it on scan target changes and dialog open.

- [ ] **Step 4: Update Storybook stories**

  Add stories for:

  - `DatabaseDetectedWithTemplatesCollapsed`
  - `DatabaseSelectedQueued`
  - `DatabaseOriginalPathAdvanced`
  - `DatabaseReopenedWithSelection`

- [ ] **Step 5: Run snapshots**

  Run:

  ```bash
  cd frontend && npm run snapshots
  ```

  Commit the resulting files under `frontend/storybook-snapshots/`.

---

## Task 7: User Documentation and Final Verification

**Files:**
- Modify: `docs/usage-guide.md`
- Modify: `docs/script-parameters.md`
- Verify: all files touched above

- [ ] **Step 1: Update usage docs**

  Document:

  - Scanning for databases from local or remote machines.
  - Adding a database without closing the source chooser.
  - Dump mode as the recommended default.
  - Original-path mode as advanced.
  - How final Borg paths are shown.

- [ ] **Step 2: Update script parameter docs**

  Add the new reserved variables:

  ```text
  BORG_UI_DB_TEMPLATE_ID
  BORG_UI_DB_ENGINE
  BORG_UI_DB_CAPTURE_MODE
  BORG_UI_DB_SOURCE_PATH
  BORG_UI_DB_DUMP_DIR
  BORG_UI_DB_BACKUP_PATHS
  ```

- [ ] **Step 3: Run backend validation**

  Run:

  ```bash
  DATA_DIR=/tmp/borg-ui-test .venv/bin/pytest tests/unit/test_source_locations.py tests/unit/test_source_discovery.py tests/unit/test_api_backup_plans.py -q
  .venv/bin/python -m ruff check app tests
  .venv/bin/python -m ruff format --check app tests
  ```

- [ ] **Step 4: Run frontend validation**

  Run:

  ```bash
  cd frontend && npm run test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx
  cd frontend && npm run check:locales
  cd frontend && npm run typecheck
  cd frontend && npm run lint
  cd frontend && npm run build
  cd frontend && npm run snapshots
  ```

- [ ] **Step 5: Manual walkthrough**

  Start the app with the normal dev workflow and verify:

  - Select Database tab.
  - Pick a detected database.
  - Click `Add database`, confirm the modal stays open.
  - Confirm Database tab count is visible.
  - Click `Use these paths`, reopen the source chooser, and confirm the same
    database state is restored.
  - Repeat with original-path mode.

## Self-Review

- Spec coverage: The plan covers non-closing database add, selected tab state,
  source machine preservation, dump/original mode, script environment, remote
  script execution, collapsed templates, stories, snapshots, and user docs.
- Placeholder scan: No placeholder task remains. Every task names files,
  tests, commands, and expected red/green behavior.
- Type consistency: `SourceDatabaseSelection`, `DatabaseCaptureMode`,
  `databaseTemplateId`, `database_template_id`, and `BORG_UI_DB_*` names match
  the spec.
