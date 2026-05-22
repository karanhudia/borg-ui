# Btrfs and ZFS Snapshot Sources Implementation Plan

**Goal:** Build local btrfs/zfs snapshot source support for backup plans and repository source locations.

**Architecture:** Preserve snapshot metadata in existing `source_locations`, validate it centrally, prepare runtime snapshot staging in `BackupService`, and keep UI changes inside the existing backup-plan source dialog. Runtime cleanup is best-effort and owned by the backup service `finally` path.

**Tech Stack:** Python/FastAPI/SQLAlchemy backend, pytest, React/Vite/MUI frontend, Vitest, Storybook snapshots.

---

### Task 1: Snapshot Source Model And Templates

**Files:**
- Modify: `app/utils/source_locations.py`
- Create: `app/services/filesystem_snapshot_service.py`
- Modify: `tests/unit/test_source_locations.py`
- Create: `tests/unit/test_filesystem_snapshot_service.py`

- [ ] **Step 1: Write failing normalization tests**

Add tests that assert local btrfs/zfs snapshot metadata is preserved and remote/agent snapshot metadata is rejected.

- [ ] **Step 2: Run red test**

Run: `pytest tests/unit/test_source_locations.py -q`
Expected: the new snapshot-preservation test fails because `snapshot` is currently dropped.

- [ ] **Step 3: Implement snapshot normalization**

Add a small validator that keeps only `provider`, `staging_path`, `dataset`, `mountpoint`, and `recursive`, rejects unsupported providers, and rejects snapshots on non-local locations.

- [ ] **Step 4: Write failing command template tests**

Cover btrfs create/delete command generation and zfs snapshot-path/delete command generation without invoking host tools.

- [ ] **Step 5: Implement command template service**

Create dataclasses for prepared snapshot records and command builders that quote only at subprocess boundary by returning argv lists.

- [ ] **Step 6: Run green tests**

Run: `pytest tests/unit/test_source_locations.py tests/unit/test_filesystem_snapshot_service.py -q`
Expected: all tests pass.

### Task 2: Backup Runtime Staging And Cleanup

**Files:**
- Modify: `app/services/backup_service.py`
- Modify: `tests/unit/test_backup_service.py`

- [ ] **Step 1: Write failing backup-service tests**

Add tests for:
- snapshot source paths replacing live paths before `_prepare_source_paths()`
- cleanup called after successful backup
- cleanup called when borg returns warning/failure
- cleanup called after cancellation where the process reaches service cleanup

- [ ] **Step 2: Run red tests**

Run: `pytest tests/unit/test_backup_service.py -q`
Expected: the new tests fail because no snapshot preparation/cleanup hook exists.

- [ ] **Step 3: Implement snapshot preparation**

Decode repository-level `source_locations` when present, prepare snapshots after local/remote source resolution and before source-size calculation, and pass staging paths into size calculation, SSH preparation, and Borg command construction.

- [ ] **Step 4: Implement cleanup**

Track prepared snapshots by job id and call cleanup from the existing `finally` block. Log cleanup failures without overriding the job’s terminal status.

- [ ] **Step 5: Run green tests**

Run: `pytest tests/unit/test_backup_service.py tests/unit/test_source_locations.py tests/unit/test_filesystem_snapshot_service.py -q`
Expected: all tests pass.

### Task 3: API Capability Surface

**Files:**
- Modify: `app/api/source_discovery.py`
- Modify: `frontend/src/services/api.ts`
- Add or modify targeted backend tests if an existing source-discovery API test covers this module.

- [ ] **Step 1: Add backend capability response**

Return whether `btrfs` and `zfs` commands are available on the Borg UI server, plus static support notes that snapshots are local-server only.

- [ ] **Step 2: Add frontend API typing**

Expose `sourceDiscoveryAPI.filesystemSnapshots()` and response types.

- [ ] **Step 3: Run targeted tests**

Run the smallest relevant source-discovery test path or `pytest tests/unit/test_api_filesystem.py -q` if no dedicated source-discovery test exists.

### Task 4: Source Picker UI

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/utils/backupPlanPayload.ts`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceStep.tsx`
- Modify: relevant `frontend/src/pages/**/__tests__/*.test.tsx`

- [ ] **Step 1: Write failing frontend test**

Use the existing source-dialog/payload test pattern to verify btrfs snapshot metadata is included in `source_locations` for a local path and remote/agent controls show disabled requirements copy.

- [ ] **Step 2: Run red frontend test**

Run the targeted Vitest command for the changed test file.

- [ ] **Step 3: Implement UI state and payload preservation**

Extend `SourceLocation` with optional `snapshot`; preserve it through wizard state, payload building, and local dialog draft state.

- [ ] **Step 4: Implement controls**

Add local-only snapshot controls with labeled fields, provider chips, and host/tool requirements copy. Do not use heavy left accent borders.

- [ ] **Step 5: Run green frontend test**

Run the targeted Vitest command for the changed test file.

### Task 5: Storybook And Snapshots

**Files:**
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.stories.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceStep.stories.tsx`
- Update generated files under `frontend/storybook-snapshots/`

- [ ] **Step 1: Add stories**

Add a story for local btrfs/zfs snapshot configuration and a summary story showing snapshot chips.

- [ ] **Step 2: Generate snapshots**

Run: `cd frontend && npm run snapshots`
Expected: updated screenshot files under `frontend/storybook-snapshots/`.

### Task 6: Required Validation And Handoff

**Files:**
- `.github/PULL_REQUEST_TEMPLATE.md` for PR body reference only.

- [ ] **Step 1: Backend validation**

Run:
- `ruff check app tests`
- `ruff format --check app tests`
- targeted `pytest` for changed backend tests

- [ ] **Step 2: Frontend validation**

Run from `frontend/`:
- `npm run check:locales`
- `npm run typecheck`
- `npm run lint`
- `npm run build`
- targeted Vitest tests

- [ ] **Step 3: Runtime walkthrough**

Launch the app with the repo’s available local runner or smoke path, open the backup plan source flow, confirm local snapshot controls and remote/agent guardrails render, and record evidence in the workpad.

- [ ] **Step 4: Commit, push, PR, feedback sweep**

Commit intentional changes, push the BOR-60 branch, create/update a PR from the repo template, attach it to Linear, apply the `symphony` label, run the full PR feedback sweep, and move Linear to Human Review only after checks are green.

## Plan Self-Review

- Spec coverage: every acceptance criterion maps to Tasks 1, 2, 4, and 5.
- Placeholder scan: no implementation step is left without file targets or a validation command.
- Type consistency: `snapshot` is consistently an optional object on `SourceLocation` in backend JSON and frontend TypeScript.
