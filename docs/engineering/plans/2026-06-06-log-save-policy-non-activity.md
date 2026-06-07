# Non-Activity Log Save Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align non-Activity log advertisements and direct log-returning API surfaces with `SystemSettings.log_save_policy`.

**Architecture:** Reuse `app.services.log_policy` for policy decisions and add only small adapter helpers where endpoint-specific log sources differ. Direct log reads should first check policy visibility, while running jobs keep live log access and pending jobs do not advertise logs.

**Tech Stack:** FastAPI, SQLAlchemy ORM models, pytest unit/integration tests, Ruff.

---

## Task 1: Shared Policy Adapters

**Files:**
- Modify: `app/services/log_policy.py`
- Test: covered through API serializer tests in later tasks

- [ ] Keep the existing `job_has_logs_by_policy` contract as the shared policy source.
- [ ] Add only narrowly-scoped helper functions if repeated endpoint code needs a common way to check log text/file visibility.
- [ ] Preserve the established policy semantics:
  - `pending`, `queued`, and `scheduled` return `False`.
  - `running`, `installing`, and `in_progress` retain live log visibility.
  - `failed_only` returns visible for failed or cancelled jobs.
  - `failed_and_warnings` returns visible for failed, cancelled, warning-status, or warning/error log output.
  - `all_jobs` returns visible for non-pending log-capable jobs.

## Task 2: Legacy Backup Surfaces

**Files:**
- Modify: `app/api/backup.py`
- Test: `tests/unit/test_api_backup.py`

- [ ] Write failing tests for `/api/backup/jobs`, `/api/backup/status/{job_id}`, `/api/backup/logs/{job_id}/stream`, and `/api/backup/logs/{job_id}/download`.
- [ ] Cover `failed_only` hiding successful completed logs, `failed_and_warnings` exposing warning logs, and `all_jobs` exposing successful logs.
- [ ] Include agent-backed backup logs so `AgentJobLog` rows cannot bypass policy after the linked backup completes.
- [ ] Implement policy checks through shared helpers before serializing `has_logs`, status `logs`, stream lines, or download files.

## Task 3: Dashboard and Maintenance Surfaces

**Files:**
- Modify: `app/api/dashboard.py`
- Modify: `app/api/maintenance_jobs.py`
- Modify: `app/api/repositories.py`
- Test: `tests/unit/test_api_dashboard.py`
- Test: `tests/unit/test_api_maintenance_jobs.py`
- Test: `tests/unit/test_api_repositories_routes.py`

- [ ] Write failing tests showing dashboard recent jobs do not advertise successful hidden logs under `failed_only`.
- [ ] Write failing tests showing repository maintenance status payloads hide raw `logs` and list payloads hide `has_logs` when policy hides them.
- [ ] Preserve running maintenance status live access and pending job non-advertisement.
- [ ] Ensure repository route serializers pass the current `get_log_save_policy(db)` into maintenance serialization.

## Task 4: Archive Delete and Rclone Metadata

**Files:**
- Modify: `app/api/archives.py`
- Modify: `app/api/v2/archives.py`
- Modify: `app/api/repositories.py`
- Test: `tests/unit/test_api_archives.py`
- Test: `tests/unit/test_api_v2_archives.py`
- Test: `tests/unit/test_api_rclone.py`

- [ ] Write failing tests for archive delete status payloads hiding `logs` and `has_logs` under `failed_only` for successful jobs.
- [ ] Write a failing test for rclone `latest_sync_job.has_log` using policy instead of raw `log_path`, `log_text`, or `error_text`.
- [ ] Keep failed rclone jobs visible under failure policies and successful rclone jobs visible under `all_jobs`.

## Task 5: Managed-Agent and Restore Payloads

**Files:**
- Modify: `app/api/managed_machines.py`
- Modify: `app/api/restore.py`
- Test: `tests/unit/test_api_managed_machines.py`
- Test: `tests/unit/test_api_restore.py`

- [ ] Write failing tests for managed-agent job log row reads so terminal successful logs are hidden under `failed_only`, while running jobs keep live rows.
- [ ] Hide restore job `logs` in list/status payloads when policy hides them.
- [ ] Keep `app/api/agents.py` unchanged for this change set. Its agent log ingestion endpoints are write-side transport, not user-facing log exposure; modify `app/api/agents.py` only if `OperationSummary` or another persisted operation summary is returned directly to user-facing APIs and must be filtered by policy.

## Task 6: Validation and Handoff

**Files:**
- Update Linear workpad only

- [ ] Run targeted pytest paths for changed API surfaces.
- [ ] Run `ruff check app tests` or a narrowed command justified by touched files.
- [ ] Run `ruff format --check app tests` or a narrowed command justified by touched files.
- [ ] Push branch, create PR, attach it to Linear, ensure the PR has label `symphony`, sweep PR feedback, and move BOR-152 to Human Review only after green checks.
