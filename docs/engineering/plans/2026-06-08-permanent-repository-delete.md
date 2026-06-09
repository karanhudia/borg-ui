# Permanent Repository Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for implementation and superpowers:verification-before-completion before claiming completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a distinct permanent delete action that removes server-local repository files and then removes the Borg UI repository record.

**Architecture:** Keep the existing metadata-only `DELETE /repositories/{id}` endpoint. Add a separate `POST /repositories/{id}/permanent-delete` endpoint with local-path validation and typed confirmation. Add a reusable confirmation dialog in the frontend and wire it through the repository page mutation/cache update path.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, TanStack Query, MUI, lucide-react, Vitest, Storybook.

---

## Files

- Modify: `app/api/repositories.py`
- Modify: `tests/unit/test_api_repositories.py`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/services/api.test.ts`
- Modify: `frontend/src/components/RepositoryCard.tsx`
- Modify: `frontend/src/components/__tests__/RepositoryCard.test.tsx`
- Add: `frontend/src/components/PermanentDeleteRepositoryDialog.tsx`
- Add: `frontend/src/components/PermanentDeleteRepositoryDialog.stories.tsx`
- Modify: `frontend/src/pages/Repositories.tsx`
- Modify: `frontend/src/pages/__tests__/Repositories.test.tsx`
- Modify: `frontend/src/components/RepositoryCard.stories.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

## Tasks

### Task 1: Backend Tests

- [ ] Add a pytest in `tests/unit/test_api_repositories.py` that creates a temp Borg-like directory (`config` file and `data/` directory), creates a local `Repository`, calls `POST /api/repositories/{id}/permanent-delete` with matching confirmation, and asserts the directory and repository row are gone.
- [ ] Add a pytest that patches `app.api.repositories.shutil.rmtree` to raise `OSError`, calls the endpoint, and asserts the response is an error while the repository row and directory remain.
- [ ] Add a pytest that attempts permanent deletion on an SSH repository and asserts a `400` with the row preserved.
- [ ] Run the new backend tests and verify they fail because the endpoint does not exist.

### Task 2: Backend Implementation

- [ ] Add a `RepositoryPermanentDeleteRequest` Pydantic model with `confirmation_phrase` and `understood`.
- [ ] Extract the existing database cleanup body from `delete_repository` into a helper that deletes the Borg UI repository record without filesystem operations.
- [ ] Add local repository target validation before filesystem deletion.
- [ ] Add `POST /{repo_id}/permanent-delete` that checks operator access, confirmation, running operation conflicts, filesystem validation, `shutil.rmtree`, then shared repository record deletion.
- [ ] Return structured backend error keys for unsupported targets, confirmation mismatch, unsafe paths, missing paths, and filesystem delete failures.
- [ ] Run the targeted backend tests until green.

### Task 3: Frontend API and Card Tests

- [ ] Add a failing API client test for `repositoriesAPI.permanentlyDeleteRepository(7, payload)` posting to `/repositories/7/permanent-delete`.
- [ ] Add failing `RepositoryCard` tests that verify the new permanent delete button is visible for eligible repositories, invokes `onPermanentDelete`, and is hidden for non-local repositories.
- [ ] Implement the API client method and card prop/button.
- [ ] Update `RepositoryCard.stories.tsx` default args and add a story for non-local repositories without the permanent delete action.

### Task 4: Confirmation Dialog and Page Flow Tests

- [ ] Add the `PermanentDeleteRepositoryDialog` component using `ResponsiveDialog`, MUI dialog primitives, typed repository-name confirmation, and semantic buttons.
- [ ] Add a Storybook story for the dialog.
- [ ] Add failing `Repositories` page tests for opening the dialog, enabling confirm only after typing the repository name, successful API call/cache removal, and failed API call leaving the repository visible with an error toast.
- [ ] Wire the page state, mutation, query cache update, toasts, and app state refetch.

### Task 5: Locales and Validation

- [ ] Add all new frontend and backend translation keys to `en`, `de`, `es`, and `it` locale files.
- [ ] Run targeted backend tests.
- [ ] Run targeted frontend tests.
- [ ] Run required backend validation: `ruff check app tests` and `ruff format --check app tests`.
- [ ] Run required frontend validation: `npm run check:locales`, `npm run typecheck`, `npm run lint`, and `npm run build` from `frontend/`.
- [ ] Run a local app walkthrough or smoke proof for the repository list permanent delete flow.
