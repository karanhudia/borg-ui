# DB-Backed Job Admission Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development while implementing this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enforce durable admission checks before backup, scheduled backup, maintenance, and agent-backed repository work is queued or dispatched.

**Architecture:** Add a focused backend admission service that derives active repository work from persisted job rows and classifies it by operation class. Manual and scheduled capacity use DB counts instead of process-local task state, while route helpers call the admission service before creating new job or `AgentJob` rows.

**Tech Stack:** FastAPI, SQLAlchemy ORM, SQLite-compatible queries, pytest, ruff.

---

## Files

- Add: `app/services/job_admission.py`
- Modify: `app/api/backup.py`
- Modify: `app/api/maintenance_jobs.py`
- Modify: `app/api/repositories.py`
- Modify: `app/api/schedule.py`
- Modify: `app/services/backup_plan_execution_service.py`
- Modify: `app/services/repository_executor.py`
- Test: `tests/unit/test_job_admission.py`
- Test: `tests/unit/test_api_backup.py`
- Test: `tests/unit/test_api_maintenance_jobs.py`
- Test: `tests/unit/test_schedulers.py`

## Admission Contract

- Active states are `pending`, `queued`, `claimed`, `cancel_requested`, and `running` where those states exist on the backing job table.
- Repository write operations include backup, prune, compact, archive delete, and repository wipe.
- Repository read/check operations include check, restore check, archive listing, info, and archive file extraction.
- A duplicate operation on the same repository is rejected while an active same-type row exists.
- A repository write is rejected while any active repository work exists for that repository.
- A repository read/check operation is rejected while an active repository write exists for that repository, but different read/check operation classes may run together.
- Manual backup admission enforces `SystemSettings.max_concurrent_backups` against active manual `BackupJob` rows.
- Scheduled backup capacity uses active scheduled `BackupJob` rows and keeps
  `_active_scheduled_backup_runs` only as a same-process guard for multi-repo
  schedules before their first `BackupJob` row exists.

## Implementation Tasks

- [x] Write failing unit tests for duplicate pending/running maintenance admission.
- [x] Write failing unit tests for cross-operation repository conflicts.
- [x] Write failing API tests for manual backup capacity and agent backup pre-`AgentJob` admission.
- [x] Write failing scheduler tests proving active scheduled `BackupJob` rows consume capacity.
- [x] Add `app/services/job_admission.py` with active status constants, operation classification, active work listing, repository admission, manual capacity, and scheduled capacity helpers.
- [x] Update maintenance helpers to use repository admission before creating jobs.
- [x] Update manual backup creation to enforce manual capacity and repository admission before `BackupJob` creation; keep legacy unknown-repository behavior.
- [x] Update agent repository operation queueing to reject conflicting work before `AgentJob` creation.
- [x] Update scheduled backup dispatch and run-now/multi-repo row creation to use DB-backed capacity and repository admission.
- [x] Update backup plan repository execution to check repository admission before creating each child backup job.
- [x] Run targeted pytest paths, then `ruff check app tests` and `ruff format --check app tests`.

## Self-Review

- The plan does not add frontend scope because the ticket only requires enforcing an existing backend setting.
- The plan avoids a new lock table for this slice because every covered active job already has a persisted row with status and repository identity; this keeps release semantics tied to existing job completion updates.
- The plan still creates a centralized admission layer so future retry work can reuse one contract instead of duplicating route-local guards.
