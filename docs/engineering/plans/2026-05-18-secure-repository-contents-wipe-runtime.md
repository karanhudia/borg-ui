# Secure Repository Contents Wipe Runtime Implementation Plan

**Goal:** Implement the BOR-31 repository contents wipe runtime while preserving the Borg UI repository record.

**Architecture:** Add a version-aware repository wipe job model and service behind the existing `/api/repositories` router. The service will use BorgRouter command builders for Borg 1/Borg 2 preview, delete, and compact commands, keep destructive work behind admin authorization plus repository operator access, and expose preview/execute/status/cancel endpoints consumed by a compact MUI dialog on repository cards.

**Tech Stack:** FastAPI, SQLAlchemy, SQLite migrations, Borg/Borg2 CLI wrappers, React, TanStack Query, MUI, i18next, Storybook, Vitest.

---

## File Map

- `app/database/models.py`: add `RepositoryWipeJob` audit/job model.
- `app/database/migrations/109_add_repository_wipe_jobs.py`: create the wipe job table and indexes.
- `app/core/borg_router.py`: add version-aware wipe command builders and service dispatch helper.
- `app/services/repository_wipe_service.py`: implement archive identity normalization, fingerprinting, preview, execute, cancel, conflict checks, log persistence, cache/stat/MQTT refresh, and status serialization.
- `app/api/repositories.py`: add `/wipe-preview`, `/wipe`, `/wipe-jobs/{job_id}`, and preview-cancel route; wire background execution.
- `app/core/authorization.py`: add admin policies for wipe routes.
- `tests/unit/test_repository_wipe_service.py`: cover fingerprinting, command construction, stale preview, protected Borg 2 archive blocking, compact outcomes, and secret-safe logs.
- `tests/unit/test_api_repository_wipe.py`: cover route authorization, preview, execute, status, and cancel contracts.
- `frontend/src/services/api.ts` and `frontend/src/types/index.ts`: add wipe DTOs and API methods.
- `frontend/src/components/RepositoryWipeDialog.tsx`: add the destructive preview/confirmation/progress UI.
- `frontend/src/components/RepositoryWipeDialog.stories.tsx`: demonstrate confirmation-ready and blocked/stale states.
- `frontend/src/components/RepositoryCard.tsx`, `frontend/src/pages/Repositories.tsx`, `frontend/src/pages/repositories-page/RepositoryGroups.tsx`: add the admin-only entry point and dialog orchestration.
- `frontend/src/locales/{en,de,es,it}.json`: add the BOR-31 UI copy and backend error/success keys.
- `frontend/src/components/__tests__/RepositoryWipeDialog.test.tsx` and `frontend/src/services/api.test.ts`: cover validation and client contract.

## Tasks

- [ ] 1. Backend red tests
  - [ ] Add failing service tests for Borg 1/Borg 2 preview fingerprinting and command shape.
  - [ ] Add failing service tests for stale preview rejection, protected Borg 2 archive blocking, compact failure status, and partial delete failure status.
  - [ ] Add failing route tests for admin-only preview/execute/status/cancel and repository record preservation.
- [ ] 2. Backend implementation
  - [ ] Add `RepositoryWipeJob` model and migration.
  - [ ] Add command builders to `BorgRouter` without repository-delete command paths.
  - [ ] Add `RepositoryWipeService` with preview, execute, cancel, serialization, conflict checks, and cleanup.
  - [ ] Add routes and authorization policies.
- [ ] 3. Frontend red tests
  - [ ] Add failing dialog tests for preview gating, exact typed phrase, checkbox validation, stale/empty/protected states, and final action enablement.
  - [ ] Add failing API client tests for wipe preview/execute/status/cancel request paths.
- [ ] 4. Frontend implementation
  - [ ] Add API DTOs and methods.
  - [ ] Add `RepositoryWipeDialog` using balanced warning panels, inline validation, and ARIA-announced errors.
  - [ ] Add repository card action gated by `repositories.manage_all`.
  - [ ] Add Storybook story and snapshots.
- [ ] 5. Validation
  - [ ] Run targeted backend tests, then `ruff check app tests` and `ruff format --check app tests`.
  - [ ] Run targeted Vitest tests, locale check, typecheck, lint, build, and Storybook snapshots.
  - [ ] Run disposable Borg preview and successful wipe proofs when Borg binaries are available.
  - [ ] Launch the app and walk the repository card -> wipe dialog -> preview -> confirm -> execution path.
