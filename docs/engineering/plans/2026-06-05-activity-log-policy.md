# Activity Log Policy Implementation Plan

> **For agentic workers:** Use the repository execution workflow and keep the
> Linear workpad checklist in sync while implementing this plan.

**Goal:** Make Activity and backup-plan run `has_logs` serialization honor
`SystemSettings.log_save_policy` consistently across supported job types.

**Architecture:** Add a small shared policy service that reads the configured
policy once and exposes one helper for job log visibility. Serializers pass each
job's status, exit code, output text, and file-backed log source into that helper
instead of duplicating boolean checks.

**Tech Stack:** FastAPI, SQLAlchemy models, pytest, Ruff.

---

## File Map

- Create: `app/services/log_policy.py`
  - Owns `get_log_save_policy(db)` and `job_has_logs_by_policy(...)`.
  - Encodes `all_jobs`, `failed_only`, and `failed_and_warnings` behavior.
- Modify: `app/api/activity.py`
  - Imports the shared helpers.
  - Reads `log_save_policy` once in `list_recent_activity`.
  - Replaces `has_logs` checks for backup, restore, check, restore_check,
    compact, prune, package, script_execution, rclone_sync, and rclone_hydrate.
- Modify: `app/api/backup_plans.py`
  - Imports the shared helpers.
  - Applies the helper to serialized backup jobs and script executions in plan
    run detail responses.
- Modify: `tests/unit/test_api_activity.py`
  - Adds policy matrix coverage for persisted-log, file-backed, script, and
    rclone representative rows.
- Modify: `tests/unit/test_api_backup_plans.py`
  - Adds/updates plan-run coverage for backup job and script execution rows.

## Tasks

### Task 1: Reproduce Current Policy Mismatch

- [ ] Add failing tests in `tests/unit/test_api_activity.py` that seed
      `SystemSettings.log_save_policy` and assert:
  - quiet successful backup with DB `logs` is hidden under `failed_only`;
  - quiet successful file-backed check is hidden under `failed_and_warnings`;
  - quiet successful file-backed check is visible under `all_jobs`;
  - failed restore/rclone/script examples are visible under all policies;
  - warning/error output is visible under `failed_and_warnings`.
- [ ] Add failing tests in `tests/unit/test_api_backup_plans.py` for plan-run
      backup/script `has_logs` serialization under the same policy helper.
- [ ] Run the narrow failing tests and record the output in the Linear workpad.

### Task 2: Add Shared Log Policy Helper

- [ ] Create `app/services/log_policy.py`.
- [ ] Implement `get_log_save_policy(db)` using `SystemSettings`, defaulting to
      `failed_and_warnings` when the row or value is absent.
- [ ] Implement `job_has_logs_by_policy(job, log_save_policy, output_text=None,
      file_path=None, status=None, exit_code=None)` with these rules:
  - pending jobs return `False`;
  - running jobs return `True` when a log source exists or the job type is
    log-capable;
  - `all_jobs` returns `True` for non-pending jobs with a source or a
    log-capable job object;
  - `failed_only` returns `True` only for failed, cancelled, or non-zero jobs;
  - `failed_and_warnings` returns `True` for failed/cancelled/non-zero jobs or
    output/error text containing warning/error signals.

### Task 3: Wire Activity Serialization

- [ ] Import `get_log_save_policy` and `job_has_logs_by_policy` in
      `app/api/activity.py`.
- [ ] Fetch `log_save_policy = get_log_save_policy(db)` once near the top of
      `list_recent_activity`.
- [ ] For each job type, pass the ticket-specified sources:
  - backup: `job.log_file_path`, `job.logs`, `job.error_message`;
  - restore: `job.logs`, `job.error_message`;
  - check/restore_check/compact/prune: `job.log_file_path`, `job.logs`,
    `job.error_message`;
  - package: `job.log_file_path`, `job.stdout`, `job.stderr`,
    `job.error_message`;
  - script_execution: `stdout`, `stderr`, `error_message`, `exit_code`;
  - rclone: `log_path`, `log_text`, `error_text`.

### Task 4: Wire Backup-Plan Run Serialization

- [ ] Import the shared helpers in `app/api/backup_plans.py`.
- [ ] Add a private serializer helper or optional argument so the plan-run
      response can pass a single `log_save_policy` through backup job and script
      execution serialization.
- [ ] Keep response shape unchanged except for policy-correct `has_logs`.

### Task 5: Validate and Handoff

- [ ] Run:
      `python -m pytest tests/unit/test_api_activity.py tests/unit/test_api_backup_plans.py -q`
- [ ] Run:
      `python -m pytest tests/unit/test_source_discovery.py -q`
- [ ] Run:
      `ruff check app/services/log_policy.py app/api/activity.py app/api/backup_plans.py tests/unit/test_api_activity.py tests/unit/test_api_backup_plans.py`
- [ ] Run:
      `ruff format --check app/services/log_policy.py app/api/activity.py app/api/backup_plans.py tests/unit/test_api_activity.py tests/unit/test_api_backup_plans.py`
- [ ] Skip frontend checks unless the backend response shape or UI behavior
      contract changes.
- [ ] Record validation evidence in the Linear workpad, commit, push, create or
      update the PR, attach it to Linear, apply the `symphony` PR label, run the
      PR feedback sweep, and move the issue to `Human Review` only after checks
      are green.

## Self-Review

- Spec coverage: all requested job types, policy modes, backup-plan run
  serialization, running/pending behavior, and validation commands are covered.
- Placeholder scan: no implementation placeholders remain in this plan.
- Type consistency: the planned helper arguments match the existing model fields
  found in `app/api/activity.py` and `app/api/backup_plans.py`.
