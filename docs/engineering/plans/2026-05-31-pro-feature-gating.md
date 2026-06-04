# Pro Feature Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:test-driven-development for implementation and
> superpowers:verification-before-completion before claiming completion. Steps
> use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate rclone, managed-agent, and mixed source-type backup capabilities
to Pro and Enterprise users while preserving Community access to same-type
multi-location backups.

**Architecture:** Add shared feature keys to the backend and frontend feature
catalogs, enforce the rules in backend validation/service policy, and surface
the same restrictions in existing backup/repository wizard UI using shared plan
gate patterns. Backup mixed-source detection is based on distinct normalized
source-location types, not the legacy `source_type: "mixed"` value.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, React, TypeScript, MUI,
TanStack Query, Vitest, Storybook snapshots.

---

## Task 1: Backend Feature Catalog and Backup Plan Policy

**Files:**

- Modify: `app/core/features.py`
- Modify: `app/services/backup_plan_policy.py`
- Modify: `app/api/backup_plans.py`
- Test: `tests/unit/test_api_backup_plans.py`

- [ ] Add failing tests for Community rejection of mixed distinct source types,
      Community allowance of multiple same-type source locations, Community
      rejection of managed-agent source locations, and Pro allowance of the paid
      backup source shapes.
- [ ] Add `rclone`, `managed_agents`, and `backup_plan_mixed_sources` as
      Pro-minimum features.
- [ ] Extend backup-plan feature decisions to inspect normalized source
      locations and return the relevant paid feature key for agent or mixed
      distinct source types.
- [ ] Pass normalized source locations from backup-plan create/update validation
      into the policy layer.
- [ ] Reuse the same policy in existing stored-plan access checks so downgraded
      paid configurations are not runnable under Community access.
- [ ] Run the targeted backup-plan pytest tests and record red/green evidence.

## Task 2: Backend Rclone and Managed-Agent Enforcement

**Files:**

- Modify: `app/api/rclone.py`
- Modify: `app/api/managed_machines.py`
- Modify: `app/api/repositories.py`
- Test: `tests/unit/test_api_rclone.py`
- Test: `tests/unit/test_api_repositories.py`
- Test existing managed-agent API tests if affected by route-level gating.

- [ ] Add failing tests proving Community users cannot create rclone remotes,
      cannot create rclone-backed repositories, and cannot create managed-agent
      repositories.
- [ ] Add Pro-plan setup to existing rclone/managed-agent tests that exercise
      paid paths so current paid behavior stays covered.
- [ ] Gate authenticated rclone management APIs with the `rclone` feature while
      leaving public OAuth callbacks unchanged.
- [ ] Gate managed-machine admin APIs and repository payloads that use managed
      agents with the `managed_agents` feature.
- [ ] Gate repository payloads and rclone operation endpoints that use
      rclone/cloud-storage storage with the `rclone` feature.
- [ ] Run targeted backend pytest tests and record red/green evidence.

## Task 3: Frontend Feature Keys, Backup Source UI, and Tests

**Files:**

- Modify: `frontend/src/core/features.ts`
- Modify: `frontend/src/pages/BackupPlans.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/types.ts`
- Modify: `frontend/src/pages/backup-plans/BackupPlanWizardStep.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceStep.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/locales/*.json`
- Test: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`
- Story: `frontend/src/pages/backup-plans/wizard-step/SourceStep.stories.tsx`
- Story: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.stories.tsx`

- [ ] Add failing Vitest coverage for a Community user seeing managed-agent
      destination locked and mixed distinct source-type application blocked.
- [ ] Add frontend feature keys matching the backend catalog.
- [ ] Pass `managed_agents` and `backup_plan_mixed_sources` entitlement checks
      from `BackupPlans` through the wizard/source-step component boundary.
- [ ] Disable managed-agent source selection when the feature is unavailable.
- [ ] Detect distinct source types in draft source locations and disable Apply
      with concise paid-plan context when Community users combine types.
- [ ] Keep same-type multi-location source selections enabled.
- [ ] Update stories and locales for the locked Community states.
- [ ] Run targeted SourceStep/SourceSelectionDialog tests and record red/green
      evidence.

## Task 4: Frontend Repository and Managed Agents UI

**Files:**

- Modify: `frontend/src/pages/Repositories.tsx`
- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/components/wizard/WizardStepLocation.tsx`
- Modify: `frontend/src/components/wizard/WizardStepCloudMirror.tsx`
- Modify: `frontend/src/pages/ManagedAgents.tsx`
- Modify: `frontend/src/locales/*.json`
- Test: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`
- Test: `frontend/src/components/wizard/__tests__/WizardStepLocation.test.tsx`
- Story: `frontend/src/components/wizard/WizardStepLocation.stories.tsx`
- Story: `frontend/src/components/wizard/WizardStepCloudMirror.stories.tsx`

- [ ] Add failing Vitest coverage for Community repository wizard rclone and
      managed-agent options being disabled and unable to submit paid payloads.
- [ ] Pass `rclone` and `managed_agents` entitlement checks from the repositories
      page into the repository wizard.
- [ ] Disable direct rclone, cloud mirror, and managed-agent repository choices
      for Community users using existing plan-gate styling.
- [ ] Prevent repository wizard submit paths from producing rclone or
      managed-agent payloads when the entitlement is unavailable.
- [ ] Show a paid-plan gate on the Managed Agents page when the user has admin
      permission but lacks `managed_agents`.
- [ ] Update stories/locales for locked repository and managed-agent states.
- [ ] Run targeted repository wizard tests and record red/green evidence.

## Task 5: Final Validation, Runtime Proof, and Handoff

**Commands:**

- `pytest tests/unit/test_api_backup_plans.py tests/unit/test_api_rclone.py tests/unit/test_api_repositories.py -q`
- `ruff check app tests`
- `ruff format --check app tests`
- `cd frontend && npm run test -- --run src/pages/backup-plans/__tests__/SourceStep.test.tsx src/components/__tests__/RepositoryWizard.test.tsx src/components/wizard/__tests__/WizardStepLocation.test.tsx`
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`
- `cd frontend && npm run snapshots`
- Runtime walkthrough via `./scripts/dev.sh`, Docker, or an available smoke
  runner that proves Community blocked and Pro allowed paths.

- [ ] Run targeted backend pytest paths.
- [ ] Run backend ruff quality and format checks.
- [ ] Run targeted frontend Vitest paths.
- [ ] Run frontend locales, typecheck, lint, build, and Storybook snapshots.
- [ ] Perform and record a runtime walkthrough for the affected backup creation
      paths.
- [ ] Commit changes.
- [ ] Push branch, create/update PR from `.github/PULL_REQUEST_TEMPLATE.md`,
      add GitHub label `symphony`, attach/link the PR to Linear, sweep PR
      feedback/checks, and move BOR-106 to Human Review only when green.
