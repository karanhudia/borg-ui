# Rclone Repository Edit Updates Implementation Plan

> **For agentic workers:** Execute task-by-task with failing tests before production code changes. Keep the Linear workpad updated after reproduction, implementation, validation, and publish milestones.

**Goal:** Make repository wizard edits for existing cached rclone repositories update supported rclone fields instead of submitting an unsupported storage-mode conversion.

**Architecture:** Preserve the existing backend model: cached rclone repositories are `repository_type="rclone"` with `RepositoryStorage.backend="rclone"`, while cloud mirrors are non-rclone primary repositories with the same storage table. Add tests that distinguish cached rclone primary edits from cloud mirror edits, update the wizard payload generation for the cached-rclone edit case, and keep backend rollback guarantees for unsupported conversions.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, MUI, Vitest, React Testing Library.

---

### Task 1: Reproduce With Failing Tests

**Files:**
- Modify: `tests/unit/test_api_rclone.py`
- Modify: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`

- [ ] Add a backend test that creates a cached rclone repository, submits a payload containing a name change plus an unsupported conversion to `storage_backend: "local"`, and asserts the API returns `backend.errors.rclone.updateUnsupported` while the repository name and rclone storage row remain unchanged after rollback.
- [ ] Add a frontend test in `legacy edit mode` that renders a cached rclone repository with `storage_backend: "rclone"` and `rclone_storage`, walks to review, submits the wizard, and expects `onSubmit` to receive `storage_backend: "rclone"` with the existing rclone remote/path/sync fields.
- [ ] Run the two new tests before production code changes. Expected result: backend rollback test should pass if rollback already holds; frontend test should fail because the wizard currently submits `storage_backend: "local"`.

### Task 2: Fix Cached Rclone Wizard Payloads

**Files:**
- Modify: `frontend/src/components/RepositoryWizard.tsx`

- [ ] Add a derived `isCachedRcloneRepositoryEdit` boolean for `mode === "edit"` when the repository has `storage_backend: "rclone"` or `repository_type === "rclone"` plus `rclone_storage`.
- [ ] Use that boolean when building submit payloads so cached rclone edits keep `storage_backend: "rclone"`, include rclone remote/path/schedule/flags, and avoid representing the edit as a local cloud mirror conversion.
- [ ] Preserve existing direct Borg 2 rclone behavior and local/SSH/agent cloud mirror behavior.
- [ ] Run the frontend red test again. Expected result: pass.

### Task 3: Clarify Unsupported Update Copy

**Files:**
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Update `backend.errors.rclone.updateUnsupported` text to explain that Borg UI can edit the selected rclone remote, path, sync policy, and flags, but changing the repository storage mode requires creating or importing a new repository.
- [ ] Run locale parity after the locale edits.

### Task 4: Storybook Coverage

**Files:**
- Modify: `frontend/src/components/wizard/WizardStepCloudMirror.stories.tsx` or `frontend/src/components/RepositoryWizard.stories.tsx` if an existing repository-wizard story file exists.

- [ ] Add or update a story that shows the existing rclone storage edit state if the repository wizard already has component-level Storybook coverage.
- [ ] If the wizard has no full component story and the changed UI is payload-only, record that no visual Storybook story was applicable and rely on the existing cloud mirror stories plus unit coverage.
- [ ] If a story changes, run `cd frontend && npm run snapshots` and commit the generated files.

### Task 5: Validate, Commit, And Publish

**Files:**
- Modify only files touched by the implementation and generated snapshots if applicable.

- [ ] Run targeted backend and frontend tests for the changed behavior.
- [ ] Run required backend checks: `ruff check app tests`, `ruff format --check app tests`, and relevant `pytest`.
- [ ] Run required frontend checks from `frontend/`: `npm run check:locales`, `npm run typecheck`, `npm run lint`, `npm run build`, and relevant Vitest tests.
- [ ] Run a local app walkthrough or smoke path proving the repository wizard edit route for cached rclone repositories.
- [ ] Commit, push, open/link the PR, ensure the PR has label `symphony`, sweep PR feedback/checks, update the workpad handoff note, and move BOR-96 to `Human Review`.
