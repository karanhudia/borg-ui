# Upload Bandwidth Limits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development for the implementation and
> superpowers:verification-before-completion before handoff. Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Add repository default upload bandwidth limits that backup runs inherit
unless a backup plan supplies a more specific cap.

**Architecture:** Store optional KiB/s limits on repositories, resolve effective
limits at backup dispatch time, and keep command generation on the existing Borg
1/Borg 2 `--upload-ratelimit` paths. Frontend uses MB/s for humans and converts
to KiB/s at API boundaries, matching the existing backup-plan control.

**Tech Stack:** FastAPI, SQLAlchemy models/migrations, pytest, React, MUI, Vite,
Vitest, Storybook.

---

### Task 1: Backend RED tests

**Files:**
- Modify: `tests/unit/test_api_repositories.py`
- Modify: `tests/unit/test_api_backup_plans.py`
- Modify: `tests/unit/test_backup_service.py`
- Modify: `tests/unit/test_agent_runtime.py`

- [x] Add failing repository API tests for create/update serialization of
  `upload_ratelimit_kib` and rejection of `0`.
- [x] Add failing backup plan execution tests proving effective limit order:
  link override, plan value, repository default, unlimited.
- [x] Add failing backup service tests proving repository backups inherit the
  repository default when no explicit plan value is supplied.
- [x] Add failing agent payload/runtime tests proving agent backups receive the
  effective limit for Borg 2 command construction.
- [x] Run the targeted pytest commands and confirm failures are caused by the
  missing repository-level default behavior.

### Task 2: Backend implementation

**Files:**
- Modify: `app/database/models.py`
- Create: `app/database/migrations/123_add_repository_upload_ratelimit.py`
- Modify: `app/api/repositories.py`
- Modify: `app/api/v2/repositories.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Modify: `app/services/backup_service.py`
- Modify: `app/services/repository_executor.py`

- [x] Add nullable `repositories.upload_ratelimit_kib`.
- [x] Accept and validate repository upload limits on v1 and v2 repository
  create/import/update payloads.
- [x] Serialize repository upload limits in list/detail responses.
- [x] Resolve effective backup-plan limits from link override, plan value,
  repository default, then `None`.
- [x] Make manual, scheduled, remote, and agent repository backup paths
  pass the repository default when no explicit plan value is supplied.
- [x] Re-run targeted backend tests and keep the RED tests green.

### Task 3: Frontend RED tests

**Files:**
- Modify: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`
- Modify: `frontend/src/components/__tests__/AdvancedRepositoryOptions.test.tsx`
- Modify: `frontend/src/components/__tests__/RepositoryCard.test.tsx`
- Modify: `frontend/src/components/wizard/__tests__/WizardStepBackupConfig.test.tsx`

- [x] Add failing repository wizard tests for hydrating and submitting upload
  limits.
- [x] Add failing component tests for the advanced upload-limit field and
  repository card metadata.
- [x] Keep existing backup plan upload-limit tests intact.
- [x] Run targeted Vitest commands and confirm failures before UI changes.

### Task 4: Frontend implementation

**Files:**
- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/components/wizard/WizardStepRepositoryAdvanced.tsx`
- Modify: `frontend/src/components/wizard/WizardStepBackupConfig.tsx`
- Modify: `frontend/src/components/AdvancedRepositoryOptions.tsx`
- Modify: `frontend/src/components/RepositoryCard.tsx`
- Modify: `frontend/src/components/RepositoryCard.stories.tsx`
- Create: `frontend/src/components/AdvancedRepositoryOptions.stories.tsx`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/utils/uploadRatelimit.ts`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [x] Add `uploadRatelimitMb` to repository wizard state and hydrate it from
  `upload_ratelimit_kib`.
- [x] Add an optional numeric upload-limit field to advanced backup settings.
- [x] Convert MB/s to KiB/s in create/edit payloads; send `null` when the
  field is empty.
- [x] Display repository default upload limit on repository cards or review
  surfaces without introducing a new visual pattern.
- [x] Update Storybook story data to demonstrate a repository with an upload
  limit.
- [x] Re-run targeted frontend tests and keep them green.

### Task 5: Required validation and handoff

**Commands:**
- `pytest tests/unit/test_api_repositories.py::TestRepositoriesCreate::test_create_local_repository_persists_upload_ratelimit_default tests/unit/test_api_repositories.py::TestRepositoriesCreate::test_create_repository_rejects_non_positive_upload_ratelimit tests/unit/test_api_repositories.py::TestRepositoriesUpdate::test_update_repository_upload_ratelimit_default tests/unit/test_api_repositories.py::TestRepositoriesUpdate::test_update_repository_rejects_non_positive_upload_ratelimit tests/unit/test_api_backup_plans.py::TestBackupPlanRoutes::test_execute_plan_run_uses_repository_upload_ratelimit_default tests/unit/test_api_backup_plans.py::TestBackupPlanRoutes::test_execute_plan_run_prefers_plan_upload_ratelimit_over_repository_default tests/unit/test_api_backup_plans.py::TestBackupPlanRoutes::test_execute_plan_run_prefers_link_upload_ratelimit_override tests/unit/test_backup_service.py::TestBackupService::test_execute_backup_delegates_remote_direct_route_strategy tests/unit/test_agent_runtime.py::test_backup_create_payload_builds_borg2_command_from_flat_payload -q`
- `ruff check app tests`
- `ruff format --check app tests`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- focused Vitest runs for repository advanced options, repository wizard,
  repository card, and backup configuration components
- app/runtime smoke using a live FastAPI server for Borg 1 and Borg 2 repository
  create plus backup execution

- [x] Run targeted backend and frontend tests.
- [x] Run required backend and frontend checks.
- [x] Capture app/runtime evidence for repository default and backup-plan
  override flows.
- [ ] Commit, push, open/update PR with the Borg UI template, add `symphony`,
  attach the PR to Linear, sweep feedback/checks, and move to Human Review only
  when green.

### Self-review

- The plan covers Borg 1, Borg 2, remote SSH, scheduled, manual, and managed
  agent backup paths.
- It preserves the existing backup-plan upload cap and uses repository defaults
  only as fallback.
- It does not implement time-window upload policies; that is an explicit
  follow-up candidate if requested.
