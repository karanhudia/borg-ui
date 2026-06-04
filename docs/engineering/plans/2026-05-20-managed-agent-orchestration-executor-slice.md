# Managed Agent Orchestration Executor Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development or superpowers:executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for
> tracking.

**Goal:** Add Borg UI's first-class repository executor choice and route manual
and backup-plan backups through server or managed-agent execution.

**Architecture:** Keep the server as orchestrator. Store executor choice in
`Repository.executor_type`, keep `execution_target` as a compatibility field,
and use a shared routing helper for manual backups and plan execution. Agent
execution remains structured `backup.create` payloads linked to normal
`BackupJob` and plan history surfaces.

**Tech Stack:** FastAPI, SQLAlchemy/SQLite migrations, pytest, Python agent,
React/Vite, MUI, Storybook.

---

### Task 1: Data Model And Compatibility

**Files:**
- Modify: `app/database/models.py`
- Create: `app/database/migrations/110_add_repository_executor_type.py`
- Modify: `app/api/repositories.py`
- Test: `tests/unit/test_api_repositories.py`

- [ ] Add `executor_type` to `Repository`, defaulting to `server`.
- [ ] Add a migration that backfills `executor_type = 'agent'` where
  `execution_target = 'agent'`, otherwise `server`.
- [ ] Preserve `execution_target` responses for compatibility, but include
  `executor_type` in create/import/list/detail/update payloads.
- [ ] Make explicit `executor_type` win over legacy `execution_target`.
- [ ] Keep repository location (`connection_id`, `path`) independent from
  executor choice, including agent-executed SSH repository targets as stored
  configuration.

### Task 2: Shared Agent Backup Routing

**Files:**
- Create: `app/services/repository_executor.py`
- Modify: `app/api/backup.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Modify: `app/api/backup_plans.py`
- Test: `tests/unit/test_api_backup.py`
- Test: `tests/unit/test_api_backup_plans.py`

- [ ] Write failing tests showing manual backup routes by `executor_type`.
- [ ] Write failing tests showing backup-plan repository execution queues an
  `AgentJob` when the repository executor is `agent`.
- [ ] Extract structured `backup.create` payload creation, agent validation,
  job queueing, waiting, and cancellation helpers.
- [ ] Use the shared helper from manual backups and backup-plan execution.
- [ ] Include `execution_mode` in backup job and plan run API responses so UI
  history can show server/agent transport.

### Task 3: Agent Reliability Hardening

**Files:**
- Modify: `app/api/agents.py`
- Modify: `agent/borg_ui_agent/client.py`
- Modify: `agent/borg_ui_agent/runtime.py`
- Modify: `agent/borg_ui_agent/backup.py`
- Test: `tests/unit/test_api_agents.py`
- Test: `tests/unit/test_agent_runtime.py`

- [ ] Write failing tests for repeated terminal status reports returning OK.
- [ ] Write failing tests for heartbeat reconciliation of stale claimed/running
  work not reported by an online agent.
- [ ] Add idempotent terminal report handling that does not overwrite an
  already-final job.
- [ ] Add simple retry around agent control-plane reports.
- [ ] Add a handler registry for structured agent job kinds.
- [ ] Start Borg in its own process group where supported and cancel the
  process tree on agent cancellation.

### Task 4: Repository Wizard And History UI

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/types/jobs.ts`
- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/components/RepositoryWizard.tsx`
- Modify: `frontend/src/components/wizard/WizardStepLocation.tsx`
- Modify: `frontend/src/components/wizard/WizardStepDataSource.tsx`
- Modify: `frontend/src/components/BackupJobsTable.tsx`
- Modify: `frontend/src/components/BackupPlanRunsPanel.tsx`
- Add/modify: Storybook story under `frontend/src/components/**/*.stories.tsx`
- Test: relevant Vitest component tests

- [ ] Write failing component tests for agent executor preserving SSH repository
  target choice and for visible transport chips.
- [ ] Send `executor_type` from the wizard and keep legacy
  `execution_target = 'agent'` for agent executor compatibility.
- [ ] Do not silently clear SSH repository target when switching executor to
  agent.
- [ ] Keep remote source disabled for this slice and explain that source paths
  are interpreted on the agent filesystem.
- [ ] Show compact server/agent transport chips in manual backup history and
  plan run repository rows.
- [ ] Add/update Storybook coverage and run snapshots.

### Task 5: Validation And Handoff

**Files:**
- Modify: `.github` PR metadata only when creating the PR.

- [ ] Run focused backend and agent pytest paths for touched behavior.
- [ ] Run `ruff check app tests`.
- [ ] Run `ruff format --check app tests`.
- [ ] Run frontend locale, typecheck, lint, build, relevant Vitest tests, and
  Storybook snapshots.
- [ ] Capture runtime proof with a fake or real enrolled agent that polls,
  claims, reports progress/logs, completes, and updates manual or plan history.
- [ ] Commit, push, create PR from template, attach PR to Linear, label
  `symphony`, run the PR feedback sweep, and move BOR-39 to Human Review only
  after checks and workpad acceptance are complete.

### Out Of Scope For This Slice

- Silent Host/Endpoint linking.
- Arbitrary agent commands, agent-side hooks, self-update, or signed update
  flows.
- Full remote-to-remote data-plane proof beyond preserving agent-to-SSH target
  configuration and keeping server proxying out of the default route.
