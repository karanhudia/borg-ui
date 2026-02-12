"""
Tests for repository deletion with foreign key constraints

These tests verify that repositories can be deleted even when they have
related records in job tables (RestoreJob, CheckJob, PruneJob, CompactJob).
"""

import pytest
from sqlalchemy.orm import Session
from app.database.models import (
    Repository, RestoreJob, CheckJob, PruneJob, CompactJob,
    BackupJob, ScheduledJob, ScheduledJobRepository, User
)
from app.database.database import SessionLocal, engine, Base
from datetime import datetime


@pytest.fixture(scope="function")
def db_session():
    """Create a fresh database session for each test"""
    # Create all tables
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    yield session

    # Cleanup
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def admin_user(db_session: Session):
    """Create an admin user for testing"""
    user = User(
        username="admin",
        email="admin@test.com",
        hashed_password="fake_hash",
        is_admin=True
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_repository(db_session: Session):
    """Create a test repository"""
    repo = Repository(
        name="Test Repo",
        path="/test/repo",
        encryption="repokey",
        mode="full"
    )
    db_session.add(repo)
    db_session.commit()
    db_session.refresh(repo)
    return repo


def test_delete_repository_with_restore_jobs(db_session: Session, test_repository: Repository):
    """Test: Repository deletion should work even with RestoreJob records"""

    # Create a RestoreJob for this repository
    # Note: RestoreJob stores repository path (string), not repository_id (int)
    restore_job = RestoreJob(
        repository=test_repository.path,  # Uses path, not ID
        archive="test-archive",
        destination="/restore/path",
        status="completed",
        started_at=datetime.utcnow()
    )
    db_session.add(restore_job)
    db_session.commit()

    # Verify RestoreJob exists
    assert db_session.query(RestoreJob).filter(
        RestoreJob.repository == test_repository.path
    ).count() == 1

    # Simulate deletion logic from repositories.py
    restore_jobs = db_session.query(RestoreJob).filter(
        RestoreJob.repository == test_repository.path
    ).all()
    for job in restore_jobs:
        db_session.delete(job)

    # Delete repository
    db_session.delete(test_repository)
    db_session.commit()

    # Verify both are deleted
    assert db_session.query(Repository).filter(Repository.id == test_repository.id).count() == 0
    assert db_session.query(RestoreJob).count() == 0


def test_delete_repository_with_check_jobs(db_session: Session, test_repository: Repository):
    """Test: Repository deletion should work even with CheckJob records"""

    # Create a CheckJob for this repository
    check_job = CheckJob(
        repository_id=test_repository.id,
        status="completed",
        started_at=datetime.utcnow()
    )
    db_session.add(check_job)
    db_session.commit()

    # Verify CheckJob exists
    assert db_session.query(CheckJob).filter(
        CheckJob.repository_id == test_repository.id
    ).count() == 1

    # Simulate deletion logic
    check_jobs = db_session.query(CheckJob).filter(
        CheckJob.repository_id == test_repository.id
    ).all()
    for job in check_jobs:
        db_session.delete(job)

    # Delete repository
    db_session.delete(test_repository)
    db_session.commit()

    # Verify both are deleted
    assert db_session.query(Repository).filter(Repository.id == test_repository.id).count() == 0
    assert db_session.query(CheckJob).count() == 0


def test_delete_repository_with_prune_jobs(db_session: Session, test_repository: Repository):
    """Test: Repository deletion should work even with PruneJob records"""

    # Create a PruneJob for this repository
    prune_job = PruneJob(
        repository_id=test_repository.id,
        keep_daily=7,
        status="completed",
        started_at=datetime.utcnow()
    )
    db_session.add(prune_job)
    db_session.commit()

    # Verify PruneJob exists
    assert db_session.query(PruneJob).filter(
        PruneJob.repository_id == test_repository.id
    ).count() == 1

    # Simulate deletion logic
    prune_jobs = db_session.query(PruneJob).filter(
        PruneJob.repository_id == test_repository.id
    ).all()
    for job in prune_jobs:
        db_session.delete(job)

    # Delete repository
    db_session.delete(test_repository)
    db_session.commit()

    # Verify both are deleted
    assert db_session.query(Repository).filter(Repository.id == test_repository.id).count() == 0
    assert db_session.query(PruneJob).count() == 0


def test_delete_repository_with_compact_jobs(db_session: Session, test_repository: Repository):
    """Test: Repository deletion should work even with CompactJob records"""

    # Create a CompactJob for this repository
    compact_job = CompactJob(
        repository_id=test_repository.id,
        status="completed",
        started_at=datetime.utcnow()
    )
    db_session.add(compact_job)
    db_session.commit()

    # Verify CompactJob exists
    assert db_session.query(CompactJob).filter(
        CompactJob.repository_id == test_repository.id
    ).count() == 1

    # Simulate deletion logic
    compact_jobs = db_session.query(CompactJob).filter(
        CompactJob.repository_id == test_repository.id
    ).all()
    for job in compact_jobs:
        db_session.delete(job)

    # Delete repository
    db_session.delete(test_repository)
    db_session.commit()

    # Verify both are deleted
    assert db_session.query(Repository).filter(Repository.id == test_repository.id).count() == 0
    assert db_session.query(CompactJob).count() == 0


def test_delete_repository_with_all_job_types(db_session: Session, test_repository: Repository):
    """Test: Repository deletion should work with ALL job types at once"""

    # Create one of each job type
    restore_job = RestoreJob(
        repository=test_repository.path,  # Uses path, not ID
        archive="test-archive",
        destination="/restore/path",
        status="completed",
        started_at=datetime.utcnow()
    )
    check_job = CheckJob(
        repository_id=test_repository.id,
        status="completed",
        started_at=datetime.utcnow()
    )
    prune_job = PruneJob(
        repository_id=test_repository.id,
        keep_daily=7,
        status="completed",
        started_at=datetime.utcnow()
    )
    compact_job = CompactJob(
        repository_id=test_repository.id,
        status="completed",
        started_at=datetime.utcnow()
    )

    db_session.add_all([restore_job, check_job, prune_job, compact_job])
    db_session.commit()

    # Verify all jobs exist
    assert db_session.query(RestoreJob).filter(RestoreJob.repository == test_repository.path).count() == 1
    assert db_session.query(CheckJob).filter(CheckJob.repository_id == test_repository.id).count() == 1
    assert db_session.query(PruneJob).filter(PruneJob.repository_id == test_repository.id).count() == 1
    assert db_session.query(CompactJob).filter(CompactJob.repository_id == test_repository.id).count() == 1

    # Simulate full deletion logic from repositories.py
    for job in db_session.query(RestoreJob).filter(RestoreJob.repository == test_repository.path).all():
        db_session.delete(job)
    for job in db_session.query(CheckJob).filter(CheckJob.repository_id == test_repository.id).all():
        db_session.delete(job)
    for job in db_session.query(PruneJob).filter(PruneJob.repository_id == test_repository.id).all():
        db_session.delete(job)
    for job in db_session.query(CompactJob).filter(CompactJob.repository_id == test_repository.id).all():
        db_session.delete(job)

    # Delete repository
    db_session.delete(test_repository)
    db_session.commit()

    # Verify everything is deleted
    assert db_session.query(Repository).filter(Repository.id == test_repository.id).count() == 0
    assert db_session.query(RestoreJob).count() == 0
    assert db_session.query(CheckJob).count() == 0
    assert db_session.query(PruneJob).count() == 0
    assert db_session.query(CompactJob).count() == 0


def test_delete_repository_preserves_backup_job_history(db_session: Session, test_repository: Repository):
    """Test: BackupJob records should be unlinked, not deleted (preserve history)"""

    # Create a BackupJob for this repository
    # Note: BackupJob stores repository path (string), not repository_id (int)
    backup_job = BackupJob(
        repository=test_repository.path,  # Uses path, not ID
        status="completed",
        started_at=datetime.utcnow()
    )
    db_session.add(backup_job)
    db_session.commit()

    backup_job_id = backup_job.id

    # Verify BackupJob exists
    assert db_session.query(BackupJob).filter(BackupJob.id == backup_job_id).count() == 1
    assert backup_job.repository == test_repository.path

    # Simulate deletion logic - unlink BackupJobs (set path to NULL)
    backup_jobs = db_session.query(BackupJob).filter(
        BackupJob.repository == test_repository.path
    ).all()
    for job in backup_jobs:
        job.repository = None

    # Delete repository
    db_session.delete(test_repository)
    db_session.commit()

    # Verify repository is deleted but BackupJob remains (unlinked)
    assert db_session.query(Repository).filter(Repository.id == test_repository.id).count() == 0

    backup_job_after = db_session.query(BackupJob).filter(BackupJob.id == backup_job_id).first()
    assert backup_job_after is not None  # Job still exists
    assert backup_job_after.repository is None  # But path is NULL


def test_delete_repository_with_scheduled_job_link(db_session: Session, test_repository: Repository):
    """Test: ScheduledJobRepository junction entries should be deleted"""

    # Create a scheduled job
    scheduled_job = ScheduledJob(
        name="Test Schedule",
        cron_expression="0 2 * * *",
        enabled=True
    )
    db_session.add(scheduled_job)
    db_session.commit()
    db_session.refresh(scheduled_job)

    # Link repository to scheduled job via junction table
    junction = ScheduledJobRepository(
        scheduled_job_id=scheduled_job.id,
        repository_id=test_repository.id,
        execution_order=0
    )
    db_session.add(junction)
    db_session.commit()

    # Verify junction entry exists
    assert db_session.query(ScheduledJobRepository).filter(
        ScheduledJobRepository.repository_id == test_repository.id
    ).count() == 1

    # Simulate deletion logic - delete junction entries
    junction_entries = db_session.query(ScheduledJobRepository).filter(
        ScheduledJobRepository.repository_id == test_repository.id
    ).all()
    for entry in junction_entries:
        db_session.delete(entry)

    # Delete repository
    db_session.delete(test_repository)
    db_session.commit()

    # Verify repository and junction are deleted, but schedule remains
    assert db_session.query(Repository).filter(Repository.id == test_repository.id).count() == 0
    assert db_session.query(ScheduledJobRepository).count() == 0
    assert db_session.query(ScheduledJob).filter(ScheduledJob.id == scheduled_job.id).count() == 1


def test_delete_repository_without_cleanup_fails(db_session: Session, test_repository: Repository):
    """
    Test: WITHOUT cleanup, deletion should fail with FK constraint
    This demonstrates the bug that was fixed
    """

    # Create a CheckJob for this repository (CheckJob has repository_id FK)
    check_job = CheckJob(
        repository_id=test_repository.id,
        status="completed",
        started_at=datetime.utcnow()
    )
    db_session.add(check_job)
    db_session.commit()

    # Try to delete repository WITHOUT cleaning up CheckJob first
    with pytest.raises(Exception) as exc_info:
        db_session.delete(test_repository)
        db_session.commit()

    # Verify we got a foreign key constraint error
    assert "FOREIGN KEY constraint failed" in str(exc_info.value) or \
           "IntegrityError" in str(exc_info.value.__class__.__name__)

    # Rollback the failed transaction
    db_session.rollback()

    # Verify repository still exists (deletion failed)
    assert db_session.query(Repository).filter(Repository.id == test_repository.id).count() == 1
    assert db_session.query(CheckJob).filter(CheckJob.repository_id == test_repository.id).count() == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
