"""Repository deletion with related job rows.

Deleting a repository that still has CheckJob, PruneJob or CompactJob rows
used to fail on their repository_id foreign key. These tests replay the
cleanup steps of the delete route against the models: dependent job rows go
first (RestoreJob rows are linked by repository path, not by a foreign key,
and are removed for tidiness), BackupJob history is unlinked rather than
deleted, schedule links are removed while the schedule itself survives, and a
delete without cleanup is refused by the database. They do not call the
route itself.
"""

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    BackupJob,
    CheckJob,
    CompactJob,
    PruneJob,
    Repository,
    RestoreJob,
    ScheduledJob,
    ScheduledJobRepository,
    utc_now,
)


@pytest.fixture(autouse=True)
def enforce_foreign_keys(test_db: Session):
    """Turn on SQLite foreign key enforcement for this module.

    The shared test database leaves the pragma at SQLite's default (off), so
    the "delete without cleanup fails" case would pass silently. The engine
    uses NullPool, so every checkout is a fresh connection and the listener
    covers all of them.
    """
    engine = test_db.get_bind()

    def _enable(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    event.listen(engine, "connect", _enable)
    # Drop the connection the session may already hold so it reconnects
    # through the listener.
    test_db.rollback()
    try:
        yield
    finally:
        event.remove(engine, "connect", _enable)


@pytest.fixture
def test_repository(test_db: Session):
    """Create a test repository"""
    repo = Repository(
        name="Test Repo", path="/test/repo", encryption="repokey", mode="full"
    )
    test_db.add(repo)
    test_db.commit()
    test_db.refresh(repo)
    return repo


def test_delete_repository_with_restore_jobs(
    test_db: Session, test_repository: Repository
):
    """Test: Repository deletion should work even with RestoreJob records"""

    # Create a RestoreJob for this repository
    # Note: RestoreJob stores repository path (string), not repository_id (int)
    restore_job = RestoreJob(
        repository=test_repository.path,  # Uses path, not ID
        archive="test-archive",
        destination="/restore/path",
        status="completed",
        started_at=utc_now(),
    )
    test_db.add(restore_job)
    test_db.commit()

    # Verify RestoreJob exists
    assert (
        test_db.query(RestoreJob)
        .filter(RestoreJob.repository == test_repository.path)
        .count()
        == 1
    )

    # Simulate deletion logic from repositories.py
    restore_jobs = (
        test_db.query(RestoreJob)
        .filter(RestoreJob.repository == test_repository.path)
        .all()
    )
    for job in restore_jobs:
        test_db.delete(job)

    # Delete repository
    test_db.delete(test_repository)
    test_db.commit()

    # Verify both are deleted
    assert (
        test_db.query(Repository).filter(Repository.id == test_repository.id).count()
        == 0
    )
    assert test_db.query(RestoreJob).count() == 0


def test_delete_repository_with_check_jobs(
    test_db: Session, test_repository: Repository
):
    """Test: Repository deletion should work even with CheckJob records"""

    # Create a CheckJob for this repository
    check_job = CheckJob(
        repository_id=test_repository.id,
        status="completed",
        started_at=utc_now(),
    )
    test_db.add(check_job)
    test_db.commit()

    # Verify CheckJob exists
    assert (
        test_db.query(CheckJob)
        .filter(CheckJob.repository_id == test_repository.id)
        .count()
        == 1
    )

    # Simulate deletion logic
    check_jobs = (
        test_db.query(CheckJob)
        .filter(CheckJob.repository_id == test_repository.id)
        .all()
    )
    for job in check_jobs:
        test_db.delete(job)

    # Delete repository
    test_db.delete(test_repository)
    test_db.commit()

    # Verify both are deleted
    assert (
        test_db.query(Repository).filter(Repository.id == test_repository.id).count()
        == 0
    )
    assert test_db.query(CheckJob).count() == 0


def test_delete_repository_with_prune_jobs(
    test_db: Session, test_repository: Repository
):
    """Test: Repository deletion should work even with PruneJob records"""

    # Create a PruneJob for this repository
    prune_job = PruneJob(
        repository_id=test_repository.id,
        status="completed",
        started_at=utc_now(),
    )
    test_db.add(prune_job)
    test_db.commit()

    # Verify PruneJob exists
    assert (
        test_db.query(PruneJob)
        .filter(PruneJob.repository_id == test_repository.id)
        .count()
        == 1
    )

    # Simulate deletion logic
    prune_jobs = (
        test_db.query(PruneJob)
        .filter(PruneJob.repository_id == test_repository.id)
        .all()
    )
    for job in prune_jobs:
        test_db.delete(job)

    # Delete repository
    test_db.delete(test_repository)
    test_db.commit()

    # Verify both are deleted
    assert (
        test_db.query(Repository).filter(Repository.id == test_repository.id).count()
        == 0
    )
    assert test_db.query(PruneJob).count() == 0


def test_delete_repository_with_compact_jobs(
    test_db: Session, test_repository: Repository
):
    """Test: Repository deletion should work even with CompactJob records"""

    # Create a CompactJob for this repository
    compact_job = CompactJob(
        repository_id=test_repository.id,
        status="completed",
        started_at=utc_now(),
    )
    test_db.add(compact_job)
    test_db.commit()

    # Verify CompactJob exists
    assert (
        test_db.query(CompactJob)
        .filter(CompactJob.repository_id == test_repository.id)
        .count()
        == 1
    )

    # Simulate deletion logic
    compact_jobs = (
        test_db.query(CompactJob)
        .filter(CompactJob.repository_id == test_repository.id)
        .all()
    )
    for job in compact_jobs:
        test_db.delete(job)

    # Delete repository
    test_db.delete(test_repository)
    test_db.commit()

    # Verify both are deleted
    assert (
        test_db.query(Repository).filter(Repository.id == test_repository.id).count()
        == 0
    )
    assert test_db.query(CompactJob).count() == 0


def test_delete_repository_with_all_job_types(
    test_db: Session, test_repository: Repository
):
    """Test: Repository deletion should work with ALL job types at once"""

    # Create one of each job type
    restore_job = RestoreJob(
        repository=test_repository.path,  # Uses path, not ID
        archive="test-archive",
        destination="/restore/path",
        status="completed",
        started_at=utc_now(),
    )
    check_job = CheckJob(
        repository_id=test_repository.id,
        status="completed",
        started_at=utc_now(),
    )
    prune_job = PruneJob(
        repository_id=test_repository.id,
        status="completed",
        started_at=utc_now(),
    )
    compact_job = CompactJob(
        repository_id=test_repository.id,
        status="completed",
        started_at=utc_now(),
    )

    test_db.add_all([restore_job, check_job, prune_job, compact_job])
    test_db.commit()

    # Verify all jobs exist
    assert (
        test_db.query(RestoreJob)
        .filter(RestoreJob.repository == test_repository.path)
        .count()
        == 1
    )
    assert (
        test_db.query(CheckJob)
        .filter(CheckJob.repository_id == test_repository.id)
        .count()
        == 1
    )
    assert (
        test_db.query(PruneJob)
        .filter(PruneJob.repository_id == test_repository.id)
        .count()
        == 1
    )
    assert (
        test_db.query(CompactJob)
        .filter(CompactJob.repository_id == test_repository.id)
        .count()
        == 1
    )

    # Simulate full deletion logic from repositories.py
    for job in (
        test_db.query(RestoreJob)
        .filter(RestoreJob.repository == test_repository.path)
        .all()
    ):
        test_db.delete(job)
    for job in (
        test_db.query(CheckJob)
        .filter(CheckJob.repository_id == test_repository.id)
        .all()
    ):
        test_db.delete(job)
    for job in (
        test_db.query(PruneJob)
        .filter(PruneJob.repository_id == test_repository.id)
        .all()
    ):
        test_db.delete(job)
    for job in (
        test_db.query(CompactJob)
        .filter(CompactJob.repository_id == test_repository.id)
        .all()
    ):
        test_db.delete(job)

    # Delete repository
    test_db.delete(test_repository)
    test_db.commit()

    # Verify everything is deleted
    assert (
        test_db.query(Repository).filter(Repository.id == test_repository.id).count()
        == 0
    )
    assert test_db.query(RestoreJob).count() == 0
    assert test_db.query(CheckJob).count() == 0
    assert test_db.query(PruneJob).count() == 0
    assert test_db.query(CompactJob).count() == 0


def test_delete_repository_preserves_backup_job_history(
    test_db: Session, test_repository: Repository
):
    """Test: BackupJob records should be unlinked, not deleted (preserve history)"""

    # A BackupJob carries the repository path and, since the column exists,
    # the repository_id foreign key (ondelete="SET NULL").
    backup_job = BackupJob(
        repository=test_repository.path,
        repository_id=test_repository.id,
        status="completed",
        started_at=utc_now(),
    )
    test_db.add(backup_job)
    test_db.commit()

    backup_job_id = backup_job.id

    # Verify BackupJob exists
    assert test_db.query(BackupJob).filter(BackupJob.id == backup_job_id).count() == 1
    assert backup_job.repository == test_repository.path

    # Simulate deletion logic - unlink BackupJobs (set path to NULL)
    backup_jobs = (
        test_db.query(BackupJob)
        .filter(BackupJob.repository == test_repository.path)
        .all()
    )
    for job in backup_jobs:
        job.repository = None

    # Delete repository
    test_db.delete(test_repository)
    test_db.commit()

    # Verify repository is deleted but BackupJob remains (unlinked)
    assert (
        test_db.query(Repository).filter(Repository.id == test_repository.id).count()
        == 0
    )

    backup_job_after = (
        test_db.query(BackupJob).filter(BackupJob.id == backup_job_id).first()
    )
    assert backup_job_after is not None  # Job still exists
    assert backup_job_after.repository is None  # But path is NULL
    assert backup_job_after.repository_id is None  # FK cleared by ondelete


def test_delete_repository_with_scheduled_job_link(
    test_db: Session, test_repository: Repository
):
    """Test: ScheduledJobRepository junction entries should be deleted"""

    # Create a scheduled job
    scheduled_job = ScheduledJob(
        name="Test Schedule", cron_expression="0 2 * * *", enabled=True
    )
    test_db.add(scheduled_job)
    test_db.commit()
    test_db.refresh(scheduled_job)

    # Link repository to scheduled job via junction table
    junction = ScheduledJobRepository(
        scheduled_job_id=scheduled_job.id,
        repository_id=test_repository.id,
        execution_order=0,
    )
    test_db.add(junction)
    test_db.commit()

    # Verify junction entry exists
    assert (
        test_db.query(ScheduledJobRepository)
        .filter(ScheduledJobRepository.repository_id == test_repository.id)
        .count()
        == 1
    )

    # Simulate deletion logic - delete junction entries
    junction_entries = (
        test_db.query(ScheduledJobRepository)
        .filter(ScheduledJobRepository.repository_id == test_repository.id)
        .all()
    )
    for entry in junction_entries:
        test_db.delete(entry)

    # Delete repository
    test_db.delete(test_repository)
    test_db.commit()

    # Verify repository and junction are deleted, but schedule remains
    assert (
        test_db.query(Repository).filter(Repository.id == test_repository.id).count()
        == 0
    )
    assert test_db.query(ScheduledJobRepository).count() == 0
    assert (
        test_db.query(ScheduledJob).filter(ScheduledJob.id == scheduled_job.id).count()
        == 1
    )


def test_delete_repository_unlinks_single_repository_schedule(
    test_db: Session, test_repository: Repository
):
    """Test: a legacy single-repository ScheduledJob keeps its row, loses the link

    ScheduledJob.repository_id has no ondelete action, so the route nulls it
    before the delete.
    """

    scheduled_job = ScheduledJob(
        name="Legacy Schedule",
        cron_expression="0 3 * * *",
        enabled=True,
        repository_id=test_repository.id,
    )
    test_db.add(scheduled_job)
    test_db.commit()
    test_db.refresh(scheduled_job)

    # Simulate deletion logic - unlink single-repository schedules
    for job in (
        test_db.query(ScheduledJob)
        .filter(ScheduledJob.repository_id == test_repository.id)
        .all()
    ):
        job.repository_id = None

    # Delete repository
    test_db.delete(test_repository)
    test_db.commit()

    # Verify repository is gone and the schedule survives unlinked
    assert (
        test_db.query(Repository).filter(Repository.id == test_repository.id).count()
        == 0
    )
    schedule_after = (
        test_db.query(ScheduledJob).filter(ScheduledJob.id == scheduled_job.id).first()
    )
    assert schedule_after is not None
    assert schedule_after.repository_id is None


def test_delete_repository_without_cleanup_fails(
    test_db: Session, test_repository: Repository
):
    """
    Test: WITHOUT cleanup, deletion should fail with FK constraint
    This demonstrates the bug that was fixed
    """

    # Create a CheckJob for this repository (CheckJob has repository_id FK)
    check_job = CheckJob(
        repository_id=test_repository.id,
        status="completed",
        started_at=utc_now(),
    )
    test_db.add(check_job)
    test_db.commit()

    # Try to delete repository WITHOUT cleaning up CheckJob first
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        test_db.delete(test_repository)
        test_db.commit()

    # Rollback the failed transaction
    test_db.rollback()

    # Verify repository still exists (deletion failed)
    assert (
        test_db.query(Repository).filter(Repository.id == test_repository.id).count()
        == 1
    )
    assert (
        test_db.query(CheckJob)
        .filter(CheckJob.repository_id == test_repository.id)
        .count()
        == 1
    )
