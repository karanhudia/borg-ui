"""Phase 6: an `operations` row wearing the legacy wipe-job surface."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository, RepositoryWipeJob
from app.services.operations.wipe_facade import (
    WipeJobFacade,
    active_wipe_operation,
    resolve_wipe_job,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, record):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def repository(db):
    repo = Repository(name="nas", path="/repo/nas", borg_version=1)
    db.add(repo)
    db.commit()
    return repo


def _wipe_operation(db, repository, status="queued", params=None):
    op = Operation(
        repository_id=repository.id,
        kind="wipe",
        category="maintenance",
        status=status,
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params or {"preview_id": 7, "run_compact": True},
    )
    db.add(op)
    db.commit()
    return op


def test_queued_operation_reads_as_pending(db, repository):
    job = WipeJobFacade(db, _wipe_operation(db, repository))
    assert job.status == "pending"


def test_compaction_failure_round_trips_through_the_phase(db, repository):
    op = _wipe_operation(db, repository, status="running")
    job = WipeJobFacade(db, op)

    job.phase = "compact_failed"
    job.status = "completed_compaction_failed"
    db.commit()

    assert op.status == "completed_with_warnings"
    assert job.status == "completed_compaction_failed"
    assert WipeJobFacade(db, op).phase == "compact_failed"


def test_partial_delete_failure_round_trips(db, repository):
    op = _wipe_operation(db, repository, status="running")
    job = WipeJobFacade(db, op)

    job.status = "failed_partial"
    db.commit()

    assert op.status == "failed"
    assert job.status == "failed_partial"


def test_compact_skipped_stays_completed_with_warnings(db, repository):
    op = _wipe_operation(db, repository, status="running")
    job = WipeJobFacade(db, op)

    job.phase = "compact_skipped"
    job.status = "completed_with_warnings"
    db.commit()

    assert op.status == "completed_with_warnings"
    assert job.status == "completed_with_warnings"


def test_preview_snapshot_reads_from_the_details_row(db, repository):
    op = _wipe_operation(db, repository)
    job = WipeJobFacade(db, op)

    job.archive_count = 4
    job.archive_fingerprint = "sha256:abc"
    job.run_compact = False
    db.commit()

    reread = WipeJobFacade(db, db.get(Operation, op.id))
    assert reread.archive_count == 4
    assert reread.archive_fingerprint == "sha256:abc"
    assert reread.run_compact is False


def test_resolve_prefers_operations_then_falls_back_to_the_legacy_row(db, repository):
    op = _wipe_operation(db, repository)
    # Distinct ids on purpose: on a fresh database both tables start at 1, and
    # a shared id would resolve to the operation and never exercise the legacy
    # branch this test is about.
    legacy = RepositoryWipeJob(
        id=op.id + 1000, repository_id=repository.id, status="previewed"
    )
    db.add(legacy)
    db.commit()

    assert isinstance(resolve_wipe_job(db, op.id), WipeJobFacade)
    assert resolve_wipe_job(db, legacy.id) is legacy
    assert resolve_wipe_job(db, 9999) is None


def test_active_wipe_operation_sees_queued_work_and_legacy_running_rows(db, repository):
    assert active_wipe_operation(db, repository.id) is None

    op = _wipe_operation(db, repository)
    assert active_wipe_operation(db, repository.id) is op

    op.status = "completed"
    db.commit()
    legacy = RepositoryWipeJob(repository_id=repository.id, status="running")
    db.add(legacy)
    db.commit()
    assert active_wipe_operation(db, repository.id) is legacy
