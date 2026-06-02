# Stale Backup Running Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix backup task cards stuck in `running_check` so cancel and startup cleanup reconcile them to terminal maintenance state.

**Architecture:** Extend the existing backup maintenance-status tables rather than adding a new endpoint or frontend state model. The backup cancel endpoint will treat `running_check` like other post-backup maintenance work, and orphan cleanup will use one running-to-failed mapping for prune, compact, and check maintenance.

**Tech Stack:** Python, FastAPI, SQLAlchemy models, pytest unit tests, Ruff.

---

## File Structure

- Modify `tests/unit/test_api_backup.py`: add cancel endpoint tests for running and orphaned `running_check`.
- Modify `tests/unit/test_utils.py`: add startup cleanup coverage for completed backups with stale, live, and dead-child `running_check`.
- Modify `app/api/backup.py`: add `CheckJob` support to maintenance cancellation.
- Modify `app/utils/backup_maintenance.py`: share backup maintenance status constants.
- Modify `app/utils/process_utils.py`: add `running_check` to stale maintenance normalization while preserving completed backup status and live child processes.

### Task 1: RED Tests for Backup Cancel

**Files:**
- Modify: `tests/unit/test_api_backup.py`

- [ ] **Step 1: Add `CheckJob` to test imports**

```python
from app.database.models import (
    AgentJob,
    AgentMachine,
    Repository,
    BackupJob,
    CheckJob,
    PruneJob,
    CompactJob,
    SSHConnection,
    SystemSettings,
)
```

- [ ] **Step 2: Add the running-check cancel tests inside `TestBackupCancel` after the compact test**

```python
    def test_cancel_backup_running_check_success(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
            borg_version=1,
        )
        job = BackupJob(
            repository=repo.path,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_check",
        )
        test_db.add_all([repo, job])
        test_db.commit()
        test_db.refresh(repo)
        test_db.refresh(job)

        check_job = CheckJob(
            repository_id=repo.id,
            repository_path=repo.path,
            status="running",
        )
        test_db.add(check_job)
        test_db.commit()
        test_db.refresh(check_job)

        response = test_client.post(
            f"/api/backup/cancel/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        test_db.refresh(job)
        test_db.refresh(check_job)
        assert job.status == "completed"
        assert job.maintenance_status == "check_failed"
        assert check_job.status == "cancelled"
        assert check_job.completed_at is not None

    def test_cancel_backup_stale_running_check_without_child_reconciles_parent(
        self, test_client: TestClient, admin_headers, test_db
    ):
        repo = Repository(
            name="Test Repo",
            path="/test/repo",
            encryption="none",
            repository_type="local",
            borg_version=1,
        )
        job = BackupJob(
            repository=repo.path,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_check",
        )
        test_db.add_all([repo, job])
        test_db.commit()
        test_db.refresh(job)

        response = test_client.post(
            f"/api/backup/cancel/{job.id}", headers=admin_headers
        )

        assert response.status_code == 200
        test_db.refresh(job)
        assert job.status == "completed"
        assert job.maintenance_status == "check_failed"
```

- [ ] **Step 3: Run the new cancel tests and verify RED**

Run:

```bash
pytest tests/unit/test_api_backup.py::TestBackupCancel::test_cancel_backup_running_check_success tests/unit/test_api_backup.py::TestBackupCancel::test_cancel_backup_stale_running_check_without_child_reconciles_parent -q
```

Expected: both tests fail because the endpoint still returns `400`.

### Task 2: RED Test for Startup Cleanup

**Files:**
- Modify: `tests/unit/test_utils.py`

- [ ] **Step 1: Add cleanup coverage inside `TestProcessUtils` near existing orphan cleanup tests**

```python
    def test_cleanup_orphaned_jobs_normalizes_completed_backup_running_check_without_child_job(
        self, db_session
    ):
        repo = Repository(
            name="Check Repo",
            path="/repos/check",
            encryption="none",
            repository_type="local",
        )
        db_session.add(repo)
        db_session.flush()

        backup_job = BackupJob(
            repository=repo.path,
            repository_id=repo.id,
            status="completed",
            started_at=datetime.now(),
            completed_at=datetime.now(),
            maintenance_status="running_check",
        )
        db_session.add(backup_job)
        db_session.commit()

        cleanup_orphaned_jobs(db_session)

        db_session.refresh(backup_job)
        assert backup_job.status == "completed"
        assert backup_job.maintenance_status == "check_failed"
```

- [ ] **Step 2: Run the cleanup test and verify RED**

Run:

```bash
pytest tests/unit/test_utils.py::TestProcessUtils::test_cleanup_orphaned_jobs_normalizes_completed_backup_running_check_without_child_job -q
```

Expected: test fails because `maintenance_status` remains `running_check`.

### Task 3: GREEN Implementation

**Files:**
- Modify: `app/api/backup.py`
- Modify: `app/utils/process_utils.py`

- [ ] **Step 1: Add `CheckJob` and a running-maintenance map in `app/api/backup.py`**

```python
from app.database.models import (
    AgentJobLog,
    User,
    BackupJob,
    BackupPlan,
    Repository,
    CheckJob,
    PruneJob,
    CompactJob,
)

RUNNING_BACKUP_MAINTENANCE_FAILURES = {
    "running_prune": "prune_failed",
    "running_compact": "compact_failed",
    "running_check": "check_failed",
}
```

- [ ] **Step 2: Extend `_get_running_maintenance_job`**

```python
    if maintenance_status == "running_prune":
        job_model = PruneJob
    elif maintenance_status == "running_compact":
        job_model = CompactJob
    elif maintenance_status == "running_check":
        job_model = CheckJob
    else:
        return None
```

- [ ] **Step 3: Update `_cancel_running_maintenance_job`**

```python
async def _cancel_running_maintenance_job(db: Session, backup_job: BackupJob):
    failure_status = RUNNING_BACKUP_MAINTENANCE_FAILURES.get(
        backup_job.maintenance_status or ""
    )
    if not failure_status:
        return None

    maintenance_job = _get_running_maintenance_job(
        db, backup_job, backup_job.maintenance_status
    )
    backup_job.maintenance_status = failure_status

    if not maintenance_job:
        return SimpleNamespace(job=None, process_killed=False)

    repo = _get_job_repository(db, backup_job.repository)

    if backup_job.maintenance_status == "prune_failed":
        if repo and getattr(repo, "borg_version", 1) == 2:
            from app.services.v2.prune_service import prune_v2_service

            process_killed = await prune_v2_service.cancel_prune(maintenance_job.id)
        else:
            from app.services.prune_service import prune_service

            process_killed = await prune_service.cancel_prune(maintenance_job.id)
    elif backup_job.maintenance_status == "compact_failed":
        if repo and getattr(repo, "borg_version", 1) == 2:
            from app.services.v2.compact_service import compact_v2_service

            process_killed = await compact_v2_service.cancel_compact(maintenance_job.id)
        else:
            from app.services.compact_service import compact_service

            process_killed = await compact_service.cancel_compact(maintenance_job.id)
    elif backup_job.maintenance_status == "check_failed":
        process_killed = False
    else:
        return None

    maintenance_job.status = "cancelled"
    maintenance_job.completed_at = datetime.utcnow()
    return SimpleNamespace(job=maintenance_job, process_killed=process_killed)
```

- [ ] **Step 4: Use the map in `cancel_backup`**

```python
        elif job.maintenance_status in RUNNING_BACKUP_MAINTENANCE_FAILURES:
            maintenance_result = await _cancel_running_maintenance_job(db, job)
```

- [ ] **Step 5: Update stale cleanup mapping in `app/utils/process_utils.py`**

```python
RUNNING_BACKUP_MAINTENANCE_FAILURES = {
    "running_prune": "prune_failed",
    "running_compact": "compact_failed",
    "running_check": "check_failed",
}
COMPLETED_BACKUP_STATUSES = {"completed", "completed_with_warnings"}
```

```python
            BackupJob.maintenance_status.in_(
                list(RUNNING_BACKUP_MAINTENANCE_FAILURES)
            ),
```

```python
        backup_job.completed_at = backup_job.completed_at or datetime.utcnow()
        if backup_job.status not in COMPLETED_BACKUP_STATUSES:
            backup_job.status = "failed"
            backup_job.error_message = (
                backup_job.error_message or CONTAINER_RESTARTED_DURING_OPERATION
            )
        backup_job.maintenance_status = RUNNING_BACKUP_MAINTENANCE_FAILURES[
            previous_state
        ]
```

- [ ] **Step 6: Run the focused tests and verify GREEN**

Run:

```bash
pytest tests/unit/test_api_backup.py::TestBackupCancel::test_cancel_backup_running_check_success tests/unit/test_api_backup.py::TestBackupCancel::test_cancel_backup_stale_running_check_without_child_reconciles_parent tests/unit/test_utils.py::TestProcessUtils::test_cleanup_orphaned_jobs_normalizes_completed_backup_running_check_without_child_job -q
```

Expected: all three tests pass.

### Task 4: Validation

**Files:**
- No new files.

- [ ] **Step 1: Run nearby existing tests**

Run:

```bash
pytest tests/unit/test_api_backup.py::TestBackupCancel tests/unit/test_utils.py::TestProcessUtils -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run backend lint and format checks**

Run:

```bash
ruff check app tests
ruff format --check app tests
```

Expected: both commands exit `0`.

- [ ] **Step 3: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no output and exit `0`.
