# Direct Borg 2 Rclone Repository Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development for implementation and
> superpowers:verification-before-completion before claiming completion. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add explicit advanced support for Borg 2 direct `rclone:` repository
URLs without replacing the normal primary-location plus optional Cloud Mirror
flow.

**Architecture:** Keep `storage_backend: "rclone"` as the existing cached
rclone repository contract. Add `storage_backend: "rclone_direct"` as a Borg
2-only repository URL mode that stores no `RepositoryStorage` row and uses Borg
2 command routing directly against the `rclone:` URL.

**Tech Stack:** FastAPI, SQLAlchemy, BorgRouter, pytest, React, Vite, MUI,
Vitest, Storybook screenshots.

---

## Task 1: Backend Direct Rclone Contract

**Files:**

- Modify: `app/api/repositories.py`
- Test: `tests/unit/test_api_rclone.py`
- Test: `tests/unit/test_api_repositories.py`

- [ ] Add failing create tests for `storage_backend: "rclone_direct"` with Borg
      2, asserting no storage row/cache path and Borg 2 initialization routing.
- [ ] Add failing import tests for direct rclone URLs, asserting Borg 2
      verification routing and no hydrate/sync.
- [ ] Add failing validation tests for Borg 1, cloud mirror fields, cached
      rclone fields, SSH connection, managed-agent execution, invalid URL, and
      update switching.
- [ ] Implement helpers for direct rclone payload detection, URL normalization,
      incompatible field rejection, and direct repository serialization.
- [ ] Implement create/import record paths that preserve existing cached rclone
      and Cloud Mirror behavior.
- [ ] Run targeted API tests.

## Task 2: Borg 2 Command Routing

**Files:**

- Modify: `app/services/v2/backup_service.py`
- Test: `tests/unit/test_v2_backup_service.py`
- Test: `tests/unit/test_borg_router.py` or focused existing command tests

- [ ] Add failing tests proving Borg 2 local repository validation skips
      `rclone:` and `rclone://` URLs.
- [ ] Add failing tests proving Borg 2 backup command construction uses
      `-r <rclone-url>` and does not rewrite the URL.
- [ ] Implement the minimal URL detection in the Borg 2 backup service.
- [ ] Run targeted routing tests.

## Task 3: Frontend Advanced Mode

**Files:**

- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/components/wizard/WizardStepLocation.tsx`
- Modify: `frontend/src/components/wizard/WizardStepReview.tsx`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/locales/*.json`
- Test: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`
- Test: `frontend/src/components/wizard/__tests__/WizardStepLocation.test.tsx`
- Test: `frontend/src/components/wizard/__tests__/WizardStepReview.test.tsx`

- [ ] Add failing tests for advanced direct rclone visibility/gating, selecting
      the mode, Cloud Mirror step omission, and `rclone_direct` payload shape.
- [ ] Add failing tests for edit population of existing direct rclone
      repositories and Review tradeoff copy.
- [ ] Implement an advanced Location control that sets Borg 2, clears SSH/agent
      and mirror state, disables browse, and relabels the path input.
- [ ] Omit the Cloud Mirror step while direct rclone is selected and clamp the
      active step when the step list changes.
- [ ] Update payload and repository type handling for `rclone_direct`.
- [ ] Update locales with the new labels, warnings, and tradeoff text.
- [ ] Run targeted Vitest tests.

## Task 4: Docs, Stories, And Snapshots

**Files:**

- Modify: user docs under `docs/`
- Modify: `frontend/src/components/wizard/WizardStepLocation.stories.tsx`
- Modify: `frontend/src/components/wizard/WizardStepReview.stories.tsx`
- Snapshot: `frontend/storybook-snapshots/`

- [ ] Update repository/cloud storage docs so users can distinguish Cloud Mirror
      from advanced direct Borg 2 rclone URLs.
- [ ] Add or update Storybook stories for Location and Review direct rclone
      states.
- [ ] Run `cd frontend && npm run snapshots` and keep generated snapshots.

## Task 5: Final Validation And Handoff

**Files:**

- Modify as required by validation fixes only.

- [ ] Run targeted backend pytest paths.
- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run targeted frontend Vitest tests.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run `cd frontend && npm run snapshots`.
- [ ] Launch Borg UI or a smoke runner and record a walkthrough for the default
      repository flow and the advanced direct rclone path.
- [ ] Commit, push, create/update PR using `.github/PULL_REQUEST_TEMPLATE.md`,
      add the `symphony` label, attach the PR to Linear, sweep PR feedback and
      checks, then move BOR-74 to Human Review only when green.
