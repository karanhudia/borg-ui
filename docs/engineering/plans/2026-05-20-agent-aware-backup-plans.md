# Agent-Aware Backup Plans Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Backup Plans understand server, SSH, and managed-agent ownership
so source selection, repository operations, browsing, and execution routing are
correct and explicit.

**Architecture:** Preserve existing server/SSH behavior, add normalized agent
source endpoints, and centralize topology decisions in a backend route planner.
Agent-owned repositories are always local paths on the selected agent; the
server queues structured agent jobs and never runs local Borg commands for
agent-owned repositories.

**Tech Stack:** FastAPI, SQLAlchemy, pytest, React, MUI, Vitest, Storybook,
`borg-ui-agent`.

---

### Task 1: Source Endpoint Model

**Files:**
- Modify: `app/utils/source_locations.py`
- Modify: `app/api/backup_plans.py`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/pages/backup-plans/types.ts`
- Test: `tests/unit/test_source_locations.py`
- Test: `tests/unit/test_api_backup_plans.py`

- [ ] Write failing tests showing `source_type: "agent"` is preserved with
  `agent_machine_id`.
- [ ] Write failing tests for invalid combinations: remote without SSH id,
  agent without agent id, local with SSH id, and local with agent id.
- [ ] Extend normalization, decoding, flattening, and legacy field derivation.
- [ ] Update API payload models and frontend types to include
  `agent_machine_id`.
- [ ] Run
  `pytest tests/unit/test_source_locations.py tests/unit/test_api_backup_plans.py -q`.

### Task 2: Agent-Owned Repository Constraints

**Files:**
- Modify: `app/api/repositories.py`
- Modify: `app/services/repository_executor.py`
- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/components/wizard/WizardStepLocation.tsx`
- Modify: `frontend/src/components/wizard/WizardStepReview.tsx`
- Test: `tests/unit/test_api_repositories.py`
- Test: `frontend/src/components/__tests__/RepositoryWizard.test.tsx`
- Story: `frontend/src/components/wizard/WizardStepLocation.stories.tsx`

- [ ] Replace the existing accepting test for agent SSH targets with failing
  rejection coverage.
- [ ] Reject `executor_type: "agent"` and legacy
  `execution_target: "agent"` payloads when `connection_id` is set or the
  repository location is SSH.
- [ ] Keep agent repository creation without source paths supported.
- [ ] Hide or disable SSH repository location in the wizard when managed-agent
  ownership is selected and force submitted `connection_id` to `null`.
- [ ] Update review copy to "Repository path on selected agent".
- [ ] Run `pytest tests/unit/test_api_repositories.py -q`.
- [ ] Run
  `cd frontend && npm test -- --run src/components/__tests__/RepositoryWizard.test.tsx`.

### Task 3: Backup Route Planner

**Files:**
- Create: `app/services/backup_route_planner.py`
- Test: `tests/unit/test_backup_route_planner.py`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Write route planner tests for every supported matrix row.
- [ ] Write route planner tests for every unsupported matrix row and reason
  key.
- [ ] Implement `plan_repository_route(repository, source_locations)`.
- [ ] Add localized backend/UI reason keys for unsupported routes and route
  labels.
- [ ] Run `pytest tests/unit/test_backup_route_planner.py -q`.

### Task 4: Agent Filesystem Browse

**Files:**
- Create: `agent/borg_ui_agent/filesystem.py`
- Modify: `agent/borg_ui_agent/runtime.py`
- Modify: `agent/README.md`
- Create: `app/services/agent_filesystem_service.py`
- Modify: `app/api/managed_machines.py`
- Modify: `frontend/src/services/api.ts`
- Test: `tests/unit/agent/test_filesystem.py`
- Test: `tests/unit/agent/test_runtime.py`
- Test: `tests/unit/test_api_managed_machines.py`

- [ ] Write agent filesystem tests for normal browse, hidden filtering,
  missing path, file path, and unreadable path.
- [ ] Add `filesystem.browse` capability and runtime handler using Python
  filesystem APIs only.
- [ ] Write server endpoint tests for missing agent, non-queueable agent,
  missing capability, timeout, failed browse, and successful browse.
- [ ] Add
  `GET /api/managed-machines/agents/{agent_machine_id}/filesystem/browse`.
- [ ] Add frontend API method for agent browse.
- [ ] Run `pytest tests/unit/agent tests/unit/test_api_managed_machines.py -q`.

### Task 5: Backup Plan UX

**Files:**
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceStep.tsx`
- Modify: `frontend/src/pages/backup-plans/state.ts`
- Create: `frontend/src/pages/backup-plans/routePreview.ts`
- Modify: `frontend/src/pages/BackupPlans.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/RepositoriesStep.tsx`
- Modify: `frontend/src/pages/backup-plans/wizard-step/ReviewStep.tsx`
- Test: `frontend/src/pages/__tests__/BackupPlans.test.tsx`
- Test: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`
- Story: `frontend/src/pages/backup-plans/wizard-step/SourceStep.stories.tsx`
- Story: `frontend/src/pages/backup-plans/wizard-step/ReviewStep.stories.tsx`

- [ ] Write failing tests for Managed agent source selection and defaulting to
  the selected agent-owned repository.
- [ ] Rename "Local source" copy to "Borg UI server".
- [ ] Add agent browse button behavior while keeping manual path entry.
- [ ] Show source endpoint labels for server, SSH, and agent groups.
- [ ] Write failing tests for route preview and unsupported save blocking.
- [ ] Implement route preview labels: Borg UI server, SSH host, managed agent.
- [ ] Add/update stories for the five required supported/unsupported states.
- [ ] Run
  `cd frontend && npm test -- --run src/pages/__tests__/BackupPlans.test.tsx src/pages/backup-plans/__tests__/SourceStep.test.tsx`.

### Task 6: Backup Execution

**Files:**
- Modify: `app/api/backup_plans.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Modify: `app/services/backup_service.py`
- Modify: `app/services/remote_backup_service.py`
- Modify: `app/services/repository_executor.py`
- Test: `tests/unit/test_api_backup_plans.py`
- Test: `tests/unit/test_backup_service_mocks.py`

- [ ] Write failing tests that create/update reject unsupported routes.
- [ ] Write failing tests that run-time validation rejects unsupported routes
  before Borg starts.
- [ ] Queue `backup.create` on the owning agent for `agent_direct`.
- [ ] Preserve existing server direct, Borg-over-SSH, SSHFS pull, and remote
  direct behaviors.
- [ ] Persist selected route strategy in backup job or run repository metadata.
- [ ] Run
  `pytest tests/unit/test_api_backup_plans.py tests/unit/test_backup_service_mocks.py -q`.

### Task 7: Agent-Owned Repository Operations

**Files:**
- Create: `agent/borg_ui_agent/repository_ops.py`
- Modify: `agent/borg_ui_agent/runtime.py`
- Modify: `app/services/repository_executor.py`
- Modify: relevant archive/info/check/prune/compact API routes
- Test: existing repository operation tests plus new agent-specific tests

- [ ] Write agent runtime tests for `repository.info`,
  `repository.list_archives`, `repository.check`, `repository.prune`, and
  `repository.compact`.
- [ ] Add structured repository operation payloads and result normalization.
- [ ] Route server API calls for agent-owned repositories to agent jobs.
- [ ] Fail unsupported or unimplemented operations explicitly instead of
  falling back to server Borg.
- [ ] Run repository operation test paths touched by these changes.

### Task 8: Required Verification And Handoff

**Files:**
- Update: `frontend/storybook-snapshots/**`
- Update: `.github` PR metadata only when creating/updating PR.

- [ ] Run `ruff check app tests agent`.
- [ ] Run `ruff format --check app tests agent`.
- [ ] Run `pytest tests/unit/test_source_locations.py`.
- [ ] Run `pytest tests/unit/test_backup_route_planner.py`.
- [ ] Run `pytest tests/unit/test_api_repositories.py`.
- [ ] Run `pytest tests/unit/test_api_backup.py`.
- [ ] Run `pytest tests/unit/test_api_backup_plans.py`.
- [ ] Run `pytest tests/unit/test_api_managed_machines.py`.
- [ ] Run `pytest tests/unit/agent`.
- [ ] Run
  `cd frontend && npm test -- --run src/components/__tests__/RepositoryWizard.test.tsx src/pages/__tests__/BackupPlans.test.tsx src/pages/backup-plans/__tests__/SourceStep.test.tsx`.
- [ ] Run `cd frontend && npm run check:locales`.
- [ ] Run `cd frontend && npm run typecheck`.
- [ ] Run `cd frontend && npm run lint`.
- [ ] Run `cd frontend && npm run build`.
- [ ] Run `cd frontend && npm run snapshots`.
- [ ] Launch the app and record walkthrough evidence for agent repository
  creation, agent source browse, route preview, save blocking, and agent job
  queuing.
- [ ] Commit, push, create/update PR from template, attach it to Linear, add
  `symphony`, run PR feedback/check sweep, and move the issue to Human Review
  only when all validation is green.
