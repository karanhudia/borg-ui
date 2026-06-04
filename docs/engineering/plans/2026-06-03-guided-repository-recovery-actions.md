# Guided Repository Recovery Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for app behavior changes. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a safe guided diagnosis action to the failed repository info recovery panel while leaving repair and reinitialization as copyable command templates.

**Architecture:** Keep backend execution on the existing repository check maintenance route. `RepositoryInfoDialog` renders the action affordance and invokes a parent callback; `Repositories.tsx` supplies the existing check confirmation flow and permission gate. Backend changes are limited to tests that document the check route/job path used by the recovery action.

**Tech Stack:** React, TypeScript, MUI, TanStack Query, Vitest, React Testing Library, FastAPI, pytest.

---

## File Structure

- `frontend/src/components/RepositoryInfoDialog.tsx`: add guided-check props and render the safe action in the failed-info recovery panel.
- `frontend/src/pages/Repositories.tsx`: pass the recovery-check callback, permission state, and pending state into the dialog.
- `frontend/src/components/__tests__/RepositoryInfoDialog.test.tsx`: cover guided-check button, unavailable permission state, and command fallback preservation.
- `frontend/src/pages/__tests__/Repositories.test.tsx`: cover clicking the recovery action from failed info state opens the existing Check confirmation dialog.
- `frontend/src/components/RepositoryInfoDialog.stories.tsx`: add/update Storybook stories for action available and action unavailable states.
- `frontend/src/locales/*.json`: add new recovery action strings.
- `tests/unit/test_api_repositories_dispatch.py`: document the backend check route/job payload used by guided diagnosis.

## Implementation Tasks

### Task 1: Frontend Red Tests

- [x] Add a `RepositoryInfoDialog` test that renders failed info with `onRunRecoveryCheck`, clicks "Run guided check", and expects the callback to receive the repository.
- [x] Add a `RepositoryInfoDialog` test that renders failed info with `canRunRecoveryCheck={false}` and verifies the action is disabled while all three copyable commands remain visible.
- [x] Add a `Repositories` page test that renders a failed info state, clicks "Run guided check", and verifies `CheckWarningDialog` opens for the same repository.
- [x] Run `cd frontend && npm run test -- src/components/__tests__/RepositoryInfoDialog.test.tsx src/pages/__tests__/Repositories.test.tsx` and confirm the new tests fail because the action does not exist yet.

### Task 2: Frontend Implementation

- [x] Add optional props to `RepositoryInfoDialog`: `onRunRecoveryCheck?: (repository: Repository) => void`, `canRunRecoveryCheck?: boolean`, and `isRecoveryCheckStarting?: boolean`.
- [x] Render a compact recovery action row above the command templates when `onRunRecoveryCheck` is supplied.
- [x] Use a MUI `Button` with an icon and stable dimensions; disable it when `canRunRecoveryCheck` is false or `isRecoveryCheckStarting` is true.
- [x] Keep the check, repair, and init command boxes unchanged and always visible in the failed-info state.
- [x] In `Repositories.tsx`, pass `onRunRecoveryCheck={handleCheckRepository}`, `canRunRecoveryCheck={viewingInfoRepository ? permissions.canDo(viewingInfoRepository.id, 'maintenance') : false}`, and `isRecoveryCheckStarting={checkRepositoryMutation.isPending}`.
- [x] Run the targeted frontend tests and confirm they pass.

### Task 3: Backend Coverage

- [x] Add a backend unit test to `tests/unit/test_api_repositories_dispatch.py` that posts to `/api/repositories/{id}/check` with `max_duration: 0`, patches `start_background_maintenance_job`, and asserts the created job uses `CheckJob` with `extra_fields.max_duration == 0` and no repair flags.
- [x] Run `pytest tests/unit/test_api_repositories_dispatch.py -q` and confirm the backend check route coverage passes.

### Task 4: Storybook and Locale Coverage

- [x] Add locale keys for guided-check title/description/button and disabled helper copy in every frontend locale file.
- [x] Update `RepositoryInfoDialog.stories.tsx` to show the action-available failed-info state.
- [x] Add a second story where the action is unavailable but command fallback remains visible.
- [x] Run `cd frontend && npm run check:locales` and fix missing or extra keys.

### Task 5: Required Validation and Handoff

- [x] Run targeted frontend tests: `cd frontend && npm run test -- src/components/__tests__/RepositoryInfoDialog.test.tsx src/pages/__tests__/Repositories.test.tsx`.
- [x] Run targeted backend tests: `pytest tests/unit/test_api_repositories_dispatch.py -q`.
- [x] Run backend validation: `ruff check app tests` and `ruff format --check app tests`.
- [x] Run frontend validation: `cd frontend && npm run check:locales`, `npm run typecheck`, `npm run lint`, and `npm run build`.
- [x] Run local app/runtime validation for the failed-info recovery state and guided-check confirmation path.
- [x] Update the Linear workpad with completed checklist and validation evidence.
- [x] Commit, push, create/link PR, add the `symphony` PR label, sweep PR feedback/checks, and move Linear to Human Review only when the completion bar is satisfied.
