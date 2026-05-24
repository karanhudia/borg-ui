# Rclone Storage Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Implement server-owned rclone-backed repositories using a local Borg
cache that Borg UI mirrors to an rclone remote.

**Architecture:** Keep Borg operations on a normal local repository path and
add an rclone storage layer that owns remote configuration, cache hydration,
post-Borg mirror jobs, status reporting, and UI setup. Existing SSH and managed
agent repository routes remain unchanged.

**Tech Stack:** FastAPI, SQLAlchemy migrations, pytest, Borg CLI wrappers,
rclone CLI wrappers, React/Vite/MUI, Vitest, Storybook screenshots.

---

## Task 1: Rclone Settings And Availability

**Files:**

- Modify: `app/config.py`
- Modify: `docs/configuration.md`
- Modify: `Dockerfile.runtime-base`
- Modify: `.github/workflows/docker-runtime-base.yml`
- Test: `tests/unit/test_config.py`
- Test: `tests/unit/test_dockerfile_borg2_fuse.py`

- [ ] Write config tests for `RCLONE_CONFIG_ROOT`, `RCLONE_CACHE_ROOT`,
      `RCLONE_SYNC_TIMEOUT`, `RCLONE_HYDRATE_TIMEOUT`,
      `RCLONE_DEFAULT_TRANSFERS`, and `RCLONE_DEFAULT_CHECKERS`.
- [ ] Add settings with defaults:
  - `RCLONE_CONFIG_ROOT=/data/rclone`
  - `RCLONE_CACHE_ROOT=/data/rclone-cache`
  - `RCLONE_SYNC_TIMEOUT=14400`
  - `RCLONE_HYDRATE_TIMEOUT=14400`
  - `RCLONE_DEFAULT_TRANSFERS=4`
  - `RCLONE_DEFAULT_CHECKERS=8`
- [ ] Add rclone to the runtime base image and smoke it with
      `docker run --rm borg-ui-runtime-base:smoke-test rclone version`.
- [ ] Document the settings in `docs/configuration.md`.
- [ ] Run
      `pytest tests/unit/test_config.py tests/unit/test_dockerfile_borg2_fuse.py -q`.

## Task 2: Database Model

**Files:**

- Modify: `app/database/models.py`
- Create: `app/database/migrations/113_add_rclone_storage.py`
- Test: `tests/unit/test_database_operations.py`

- [ ] Add migration tests or model-shape checks for the new tables.
- [ ] Create `rclone_remotes` with fields for name, provider, config source,
      config path, redacted config, test status, timestamps, and error text.
- [ ] Create `repository_storage` with fields for repository id, backend,
      rclone remote id, relative remote path, cache path, sync policy, sync
      status, last sync/hydrate/check timestamps, last error, and extra flags.
- [ ] Store `rclone_remote_path` as a relative path only and expose any full
      `<remote_name>:<relative_path>` value as a derived read-only preview.
- [ ] Create `rclone_sync_jobs` with repository id, direction, status,
      started/completed timestamps, bytes/files counters, log path, and error text.
- [ ] Add SQLAlchemy relationships from `Repository` to storage metadata.
- [ ] Run `pytest tests/unit/test_database_operations.py -q`.

## Task 3: Rclone Command Wrapper

**Files:**

- Create: `app/services/rclone_service.py`
- Test: `tests/unit/test_rclone_service.py`

- [ ] Write command-builder tests for `version`, `listremotes`, `lsjson`,
      `about`, `sync`, and `check`.
- [ ] Write tests proving commands are argv lists and never shell strings.
- [ ] Write redaction tests for config paths, tokens, secrets, access keys,
      secret keys, and remote paths in logs.
- [ ] Implement `RcloneService` with subprocess execution, timeout handling,
      JSON parsing, structured result objects, and log redaction.
- [ ] Add a typed `RcloneUnavailable` error for missing binaries.
- [ ] Run `pytest tests/unit/test_rclone_service.py -q`.

## Task 4: Remote Management API

**Files:**

- Create: `app/api/rclone.py`
- Modify: `app/main.py`
- Modify: `app/services/rclone_service.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Write API tests for unauthenticated access, list remotes, create managed
      remote, test remote, browse remote, rclone unavailable, and redacted output.
- [ ] Add `GET /api/rclone/status`.
- [ ] Add `GET /api/rclone/remotes`.
- [ ] Add `POST /api/rclone/remotes`.
- [ ] Add `POST /api/rclone/remotes/{id}/test`.
- [ ] Add `GET /api/rclone/remotes/{id}/browse`.
- [ ] Persist managed configs under `RCLONE_CONFIG_ROOT` with restrictive file
      permissions.
- [ ] Run `pytest tests/unit/test_api_rclone.py -q`.

## Task 5: Repository Storage Service

**Files:**

- Create: `app/services/rclone_repository_service.py`
- Modify: `app/services/repository_command_lock.py`
- Test: `tests/unit/test_rclone_repository_service.py`

- [ ] Write tests for cache path derivation under `RCLONE_CACHE_ROOT`.
- [ ] Write tests that reject non-empty remote paths unless they are verified
      Borg repositories or Borg UI-owned paths.
- [ ] Write tests that command builders compose the full rclone target from
      `rclone_remote_id` plus relative `rclone_remote_path`.
- [ ] Write create-flow tests: local Borg init succeeds, initial sync succeeds,
      storage status becomes `current`.
- [ ] Write import-flow tests: remote Borg repository hydrates into a temp cache,
      Borg verification succeeds, temp cache promotes atomically.
- [ ] Write failure tests: sync failure leaves repository usable locally but
      marks storage status `failed`; hydration failure does not replace old cache.
- [ ] Implement create, import, sync, hydrate, and status helpers.
- [ ] Ensure all mutable Borg and rclone operations use the repository command
      lock.
- [ ] Run `pytest tests/unit/test_rclone_repository_service.py -q`.

## Task 6: Repository API Integration

**Files:**

- Modify: `app/api/repositories.py`
- Modify: `app/api/v2/repositories.py`
- Modify: `app/services/repository_service.py`
- Modify: `app/services/v2/repository_service.py`
- Test: `tests/unit/test_api_repositories.py`
- Test: `tests/unit/test_api_v2_repositories.py`

- [ ] Add request fields for `storage_backend`, `rclone_remote_id`,
      `rclone_remote_path`, `rclone_cache_path`, `rclone_sync_policy`, and
      `rclone_extra_flags`.
- [ ] Add response serialization for rclone storage metadata, including a
      derived `rclone_target` preview while keeping submitted
      `rclone_remote_path` relative.
- [ ] Route create/import payloads with `storage_backend: "rclone"` through
      `RcloneRepositoryService`.
- [ ] Preserve existing local, SSH, and agent repository behavior.
- [ ] Reject rclone storage for managed-agent repositories in this slice.
- [ ] Add manual endpoints:
  - `POST /api/repositories/{id}/rclone/sync`
  - `POST /api/repositories/{id}/rclone/hydrate`
  - `GET /api/repositories/{id}/rclone/status`
- [ ] Run
      `pytest tests/unit/test_api_repositories.py tests/unit/test_api_v2_repositories.py -q`.

## Task 7: Backup And Maintenance Mirror Hooks

**Files:**

- Modify: `app/services/backup_service.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Modify: `app/services/check_service.py`
- Modify: `app/services/prune_service.py`
- Modify: `app/services/compact_service.py`
- Modify: `app/services/delete_archive_service.py`
- Modify: `app/services/repository_wipe_service.py`
- Test: `tests/unit/test_backup_service.py`
- Test: `tests/unit/test_api_backup_plans.py`
- Test: relevant maintenance service tests

- [ ] Write backup tests proving rclone repositories hydrate before Borg when
      cache is missing or stale.
- [ ] Write backup tests proving sync runs after successful Borg writes.
- [ ] Write tests proving Borg success plus sync failure becomes a warning and
      storage status `failed`.
- [ ] Add post-mutation mirror hooks to check/prune/compact/delete/wipe paths
      where the Borg operation mutates repository files.
- [ ] Keep read-only list/info/browse operations from triggering sync unless
      hydration occurred.
- [ ] Run
      `pytest tests/unit/test_backup_service.py tests/unit/test_api_backup_plans.py -q`.

## Task 8: Frontend Types And API Client

**Files:**

- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/pages/repositories-page/types.ts`
- Test: existing API client tests if available

- [ ] Add `RcloneRemote`, `RcloneStorage`, `RcloneStatus`, and rclone request
      types.
- [ ] Add `rcloneAPI` methods for status, remotes, test, browse, repository
      sync, repository hydrate, and repository status.
- [ ] Extend repository types with rclone storage fields.
- [ ] Run `cd frontend && npm run typecheck`.

## Task 9: Repository Wizard UI

**Files:**

- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/components/wizard/WizardStepLocation.tsx`
- Modify: `frontend/src/components/wizard/WizardStepReview.tsx`
- Modify: `frontend/src/components/wizard/WizardStepLocation.stories.tsx`
- Modify: `frontend/src/components/wizard/WizardStepReview.stories.tsx`
- Test: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`

- [ ] Write failing tests for selecting rclone location and submitting rclone
      storage fields.
- [ ] Add the "Cloud storage (rclone)" location option beside Borg UI server,
      SSH remote, and managed agent.
- [ ] Add remote selector, relative remote path field, browse action, derived
      target preview, local cache path preview, sync policy selector, and
      advanced flags section.
- [ ] Show unavailable state when `GET /api/rclone/status` reports missing
      binary.
- [ ] Update review to show route:
      `Sources -> Borg UI server -> local cache -> rclone sync -> remote`.
- [ ] Add Storybook stories for configured rclone, unavailable rclone, and
      remote path warning states.
- [ ] Run
      `cd frontend && npm test -- --run src/components/__tests__/RepositoryWizard.test.tsx`.

## Task 10: Repository Card And Status UX

**Files:**

- Modify: `frontend/src/components/RepositoryCard.tsx`
- Modify: `frontend/src/components/RepositoryCard.stories.tsx`
- Modify: `frontend/src/pages/repositories-page/RepositoryGroups.tsx`
- Test: relevant repository-card tests if present

- [ ] Add chips for `Rclone mirror`, `Synced`, `Sync pending`,
      `Sync failed`, and `Hydration required`.
- [ ] Add repository actions for `Run sync now` and `Hydrate cache` when the
      current status permits them.
- [ ] Keep cards compact and use balanced outline/background emphasis rather
      than heavy left accent borders.
- [ ] Add stories for current, pending, failed, and hydration-required states.
- [ ] Run targeted frontend tests for repository card behavior.

## Task 11: Documentation

**Files:**

- Create: `docs/rclone-storage.md`
- Modify: `docs/usage-guide.md`
- Modify: `docs/disaster-recovery.md`
- Modify: `docs/configuration.md`
- Modify: `docs/plan-content.json` only if feature availability copy changes

- [ ] Document the local-cache-plus-remote-mirror model.
- [ ] Document disk sizing requirements for `RCLONE_CACHE_ROOT`.
- [ ] Document disaster recovery: install rclone, configure remote, sync remote
      path to local directory, then use Borg/Borg UI.
- [ ] Document sync failure states and safe retry behavior.
- [ ] Document why direct rclone mount is not the supported default.

## Task 12: Storybook Snapshots And Runtime Validation

**Files:**

- Update: `frontend/storybook-snapshots/**`
- Add or update smoke tests under `tests/smoke/` if a local rclone binary is
  available in CI.

- [ ] Run `cd frontend && npm run snapshots`.
- [ ] Add a smoke test using an rclone local filesystem remote:
  - configure local remote rooted at a temp directory
  - create rclone repository
  - run one backup
  - assert remote has Borg repository files
  - remove cache
  - hydrate cache
  - list archives
- [ ] If CI cannot guarantee rclone, skip the smoke test with a clear
      `shutil.which("rclone")` guard and keep unit coverage mandatory.

## Task 13: Required Validation And Handoff

**Files:**

- Use `.github/PULL_REQUEST_TEMPLATE.md` when opening the PR.

- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run all targeted backend pytest commands from earlier tasks.
- [ ] Run the rclone smoke test when rclone is available.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run all targeted Vitest commands from earlier tasks.
- [ ] Run `cd frontend && npm run snapshots`.
- [ ] Launch Borg UI and capture walkthrough evidence for:
  - repository wizard rclone location
  - remote test/browse
  - review route preview
  - repository card sync status
  - manual sync or hydrate action
- [ ] Commit scoped changes, push the branch, create/update PR from the repo
      template, apply `symphony`, complete PR feedback sweep, and move Linear to
      Human Review only after checks are green.

## Plan Self-Review

- Spec coverage: tasks cover packaging, data model, command wrapper, APIs,
  repository runtime, backup/maintenance hooks, frontend wizard, status cards,
  docs, smoke validation, and handoff.
- Placeholder scan: no task relies on undefined files or open-ended "handle
  errors" steps without tests.
- Type consistency: `storage_backend`, rclone remote metadata, relative remote
  path, derived target preview, cache path, sync policy, and sync status are
  used consistently across backend, frontend, and docs.
