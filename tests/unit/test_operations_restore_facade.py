"""Phase 7: an `operations` row wearing the legacy restore-job surface."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
from app.services.operations.details import restore_details
from app.services.operations.restore_facade import (
    RestoreJobFacade,
    list_restore_jobs,
    resolve_restore_job,
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


@pytest.fixture()
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    return tmp_path / "logs"


def _restore_operation(db, repository, status="queued", params=None):
    op = Operation(
        repository_id=repository.id,
        kind="restore",
        category="restore",
        status=status,
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params or {"archive_name": "nas-2026-09-08", "paths": []},
    )
    db.add(op)
    db.flush()
    restore_details(db, op).archive = op.params["archive_name"]
    db.commit()
    return op


def test_queued_operation_reads_as_pending_and_pending_writes_queued(db, repository):
    job = RestoreJobFacade(db, _restore_operation(db, repository))
    assert job.status == "pending"

    job.status = "running"
    assert job.operation.status == "running"
    job.status = "pending"
    assert job.operation.status == "queued"


def test_repository_is_the_path_of_the_operations_repository(db, repository):
    job = RestoreJobFacade(db, _restore_operation(db, repository))
    assert job.repository == "/repo/nas"
    assert job.repository_id == repository.id


def test_details_columns_round_trip_through_the_extension_row(db, repository):
    from app.database.models import OperationRestoreDetails

    op = _restore_operation(db, repository)
    job = RestoreJobFacade(db, op)
    job.archive = "nas-2026-09-08"
    job.destination = "/restore/here"
    job.destination_type = "ssh"
    job.destination_hostname = "backup.example"
    job.repository_type = "local"
    job.restored_size = 512
    job.restore_speed = 2.5
    job.nfiles = 3
    db.commit()

    row = db.get(OperationRestoreDetails, op.id)
    assert row.archive == "nas-2026-09-08"
    assert row.destination == "/restore/here"
    assert row.destination_type == "ssh"
    assert row.destination_hostname == "backup.example"
    assert row.restored_size == 512
    assert row.restore_speed == 2.5
    assert row.nfiles == 3
    assert RestoreJobFacade(db, op).nfiles == 3


def test_progress_int_and_percent_share_one_column(db, repository):
    job = RestoreJobFacade(db, _restore_operation(db, repository))
    job.progress_percent = 42.6
    assert job.progress == 42
    job.progress = 100
    assert job.operation.progress_percent == 100.0


def test_original_size_and_eta_follow_the_legacy_arithmetic(db, repository):
    job = RestoreJobFacade(db, _restore_operation(db, repository))
    job.original_size = 10 * 1024 * 1024
    job.restored_size = 4 * 1024 * 1024
    job.restore_speed = 2.0  # MB/s

    assert job.original_size == 10 * 1024 * 1024
    assert job.estimated_time_remaining == 3

    job.restore_speed = 0.0
    assert job.estimated_time_remaining == 0
    job.restore_speed = 2.0
    job.restored_size = job.original_size
    assert job.estimated_time_remaining == 0

    # The service also assigns the ETA it computed; the facade accepts and
    # drops the write because the value is derived.
    job.estimated_time_remaining = 999
    assert job.estimated_time_remaining == 0


def test_current_file_is_mirrored_into_progress_message(db, repository):
    job = RestoreJobFacade(db, _restore_operation(db, repository))
    job.current_file = "docs/report.txt"
    assert job.current_file == "docs/report.txt"
    assert job.operation.progress_message == "docs/report.txt"


def test_logs_are_written_to_and_read_from_the_operation_log_file(
    db, repository, log_dir
):
    op = _restore_operation(db, repository)
    job = RestoreJobFacade(db, op)
    assert job.logs == ""

    job.logs = "STDOUT:\nrestored\n\nSTDERR:\n(no output)"
    db.commit()

    assert op.log_file_path == str(log_dir / f"operation_{op.id}.log")
    assert (log_dir / f"operation_{op.id}.log").read_text() == (
        "STDOUT:\nrestored\n\nSTDERR:\n(no output)"
    )
    assert RestoreJobFacade(db, op).logs.startswith("STDOUT:")


def test_unknown_attributes_raise(db, repository):
    job = RestoreJobFacade(db, _restore_operation(db, repository))
    with pytest.raises(AttributeError):
        job.no_such_column


def test_resolve_returns_none_for_an_unknown_id(db, repository):
    op = _restore_operation(db, repository)

    assert isinstance(resolve_restore_job(db, op.id), RestoreJobFacade)
    assert resolve_restore_job(db, 9999) is None


def test_list_restore_jobs_newest_first(db, repository):
    from datetime import datetime, timedelta

    base = datetime(2026, 9, 8, 12, 0, 0)
    old = _restore_operation(db, repository, params={"archive_name": "a", "paths": []})
    old.created_at = base
    newer = _restore_operation(
        db, repository, params={"archive_name": "b", "paths": []}
    )
    newer.created_at = base + timedelta(minutes=10)
    middle = _restore_operation(db, repository)
    middle.created_at = base + timedelta(minutes=5)
    db.commit()

    jobs = list_restore_jobs(db, limit=2)

    assert [j.archive for j in jobs] == ["b", "nas-2026-09-08"]
    assert isinstance(jobs[1], RestoreJobFacade)
    assert len(list_restore_jobs(db, limit=10)) == 3


def test_list_restore_jobs_limits_each_source_by_created_at_not_id(db, repository):
    """The list ranks by created_at, so the cut has to use created_at too.
    Cutting by id drops the newer row whenever id order and created_at order
    disagree."""
    from datetime import datetime, timedelta

    base = datetime(2026, 9, 8, 12, 0, 0)
    newer_but_lower_id = _restore_operation(
        db, repository, params={"archive_name": "fresh", "paths": []}
    )
    older_but_higher_id = _restore_operation(
        db, repository, params={"archive_name": "stale", "paths": []}
    )
    newer_but_lower_id.created_at = base + timedelta(minutes=10)
    older_but_higher_id.created_at = base
    db.commit()
    assert newer_but_lower_id.id < older_but_higher_id.id

    jobs = list_restore_jobs(db, limit=1)

    assert [j.archive for j in jobs] == ["fresh"]
