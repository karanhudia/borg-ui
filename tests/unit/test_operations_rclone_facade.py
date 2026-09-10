"""Phase 6: an `operations` row wearing the legacy rclone-sync-job surface."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
from app.services.operations.details import rclone_details
from app.services.operations.rclone_facade import (
    RcloneSyncFacade,
    rclone_activity_type,
    resolve_rclone_job,
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


def _rclone_operation(
    db,
    repository,
    *,
    status="queued",
    trigger="manual",
    operation="sync",
    run_id="run-1",
):
    op = Operation(
        repository_id=repository.id,
        kind="rclone_sync",
        category="mirror",
        status=status,
        trigger=trigger,
        priority=0,
        run_id=run_id,
    )
    db.add(op)
    db.commit()
    rclone_details(db, op).operation = operation
    db.commit()
    return op


def test_initial_trigger_round_trips_as_triggered_by(db, repository):
    op = _rclone_operation(db, repository, trigger="import")

    job = RcloneSyncFacade(db, op)
    assert job.triggered_by == "initial"
    assert job.status == "pending"

    job.triggered_by = "schedule"
    db.commit()
    assert op.trigger == "schedule"
    assert RcloneSyncFacade(db, op).triggered_by == "schedule"


def test_status_maps_pending_to_queued_in_both_directions(db, repository):
    op = _rclone_operation(db, repository, status="running")
    job = RcloneSyncFacade(db, op)

    job.status = "pending"
    db.commit()
    assert op.status == "queued"
    assert RcloneSyncFacade(db, op).status == "pending"

    job.status = "completed"
    db.commit()
    assert op.status == "completed"
    assert RcloneSyncFacade(db, op).status == "completed"


def test_details_columns_read_and_write_through_the_facade(db, repository):
    op = _rclone_operation(db, repository)
    job = RcloneSyncFacade(db, op)

    job.direction = "cache_to_remote"
    job.log_text = "transferred 3 files"
    job.error_text = None
    job.bytes_transferred = 4096
    db.commit()

    reread = RcloneSyncFacade(db, db.get(Operation, op.id))
    assert reread.direction == "cache_to_remote"
    assert reread.log_text == "transferred 3 files"
    assert reread.bytes_transferred == 4096


def test_log_path_is_the_operations_log_file_path(db, repository):
    op = _rclone_operation(db, repository)
    job = RcloneSyncFacade(db, op)

    job.log_path = "/data/logs/operation_1.log"
    db.commit()

    assert op.log_file_path == "/data/logs/operation_1.log"
    assert RcloneSyncFacade(db, op).log_path == "/data/logs/operation_1.log"


def test_hydrate_reads_as_the_hydrate_activity_type(db, repository):
    op = _rclone_operation(db, repository, operation="hydrate", status="running")

    assert rclone_activity_type(RcloneSyncFacade(db, op)) == "rclone_hydrate"


def test_sync_reads_as_the_sync_activity_type(db, repository):
    op = _rclone_operation(db, repository)

    assert rclone_activity_type(RcloneSyncFacade(db, op)) == "rclone_sync"


def test_resolve_filters_on_the_details_operation(db, repository):
    op = _rclone_operation(db, repository, status="completed")

    assert resolve_rclone_job(db, op.id, operation="sync") is not None
    assert resolve_rclone_job(db, op.id, operation="hydrate") is None
    assert resolve_rclone_job(db, 9999) is None
