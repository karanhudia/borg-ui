"""Phase 5: an `operations` row wearing the legacy maintenance-job surface."""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, CheckJob, Operation, Repository
from app.services.operations.job_facade import (
    MAINTENANCE_KINDS,
    MaintenanceJobFacade,
    claim_running,
    legacy_status,
    operation_status,
    resolve_maintenance_job,
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


def _operation(db, repository, *, kind="check", params=None, status="running"):
    op = Operation(
        repository_id=repository.id,
        kind=kind,
        category="maintenance",
        status=status,
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params or {},
    )
    db.add(op)
    db.commit()
    return op


def test_every_maintenance_kind_is_a_known_kind():
    from app.services.operations.vocab import KINDS

    for kind in MAINTENANCE_KINDS:
        assert kind in KINDS


def test_status_words_map_both_ways():
    assert operation_status("pending") == "queued"
    assert operation_status("running") == "running"
    assert operation_status("completed") == "completed"
    assert legacy_status("queued") == "pending"
    assert legacy_status("completed_with_warnings") == "completed_with_warnings"


def test_facade_writes_status_through_to_the_operation(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    job.status = "completed"
    db.commit()

    assert op.status == "completed"
    assert job.status == "completed"


def test_facade_maps_pending_to_queued(db, repository):
    op = _operation(db, repository, status="queued")
    job = MaintenanceJobFacade(db, op)

    assert job.status == "pending"

    job.status = "pending"
    assert op.status == "queued"


def test_facade_progress_is_an_integer_percent(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    job.progress = 40
    db.commit()

    assert op.progress_percent == 40.0
    assert job.progress == 40


def test_facade_reads_inputs_from_params(db, repository):
    op = _operation(
        db,
        repository,
        params={"max_duration": 3600, "extra_flags": "--verify-data"},
    )
    job = MaintenanceJobFacade(db, op)

    assert job.max_duration == 3600
    assert job.extra_flags == "--verify-data"
    assert job.scheduled_check is False


def test_facade_rejects_an_input_the_kind_does_not_have(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    with pytest.raises(AttributeError):
        job.keep_daily


def test_facade_writes_a_kind_specific_input_through_to_params(db, repository):
    op = _operation(
        db,
        repository,
        kind="restore_check",
        params={"probe_paths": "[]", "full_archive": False},
    )
    job = MaintenanceJobFacade(db, op)

    job.archive_name = "nightly-2026-09-01"
    db.commit()

    assert op.params["archive_name"] == "nightly-2026-09-01"
    assert job.archive_name == "nightly-2026-09-01"


def test_facade_logs_round_trip_through_the_log_file(db, repository, tmp_path):
    op = _operation(db, repository)
    # Write to a path this test owns. Letting the facade resolve one from
    # `settings.data_dir` puts `operation_<id>.log` in a directory other
    # suites read, and a monkeypatch of that setting is not reliable once an
    # earlier test has replaced the settings object.
    op.log_file_path = str(tmp_path / "operation.log")
    job = MaintenanceJobFacade(db, op)

    job.logs = "line one\nline two\n"
    db.commit()

    assert job.logs == "line one\nline two\n"
    assert job.has_logs is True


def test_facade_logs_setter_does_not_clobber_an_already_written_file(
    db, repository, tmp_path
):
    """The five migrated maintenance services (spec section 13 phase 5) write
    the real captured output straight to the log file, set
    `log_file_path`, and then assign `job.logs = "Logs saved to: X"` as a
    backwards-compatible marker for callers that still read the legacy
    `logs` column. For a legacy row those are two independent columns, so
    that marker write is harmless there; for a facade, `.logs` reads and
    writes through the same file `log_file_path` already points at, so the
    marker write silently overwrote the real content it was written next
    to. The setter must leave a file that already has content alone."""
    op = _operation(db, repository)
    log_path = tmp_path / "operation.log"
    log_path.write_text("real captured borg output\n", encoding="utf-8")
    op.log_file_path = str(log_path)
    job = MaintenanceJobFacade(db, op)

    job.logs = "Logs saved to: operation.log"
    db.commit()

    assert job.logs == "real captured borg output\n"


def test_facade_allocates_a_log_path_when_the_operation_has_none(
    db, repository, tmp_path, monkeypatch
):
    op = _operation(db, repository)
    target = tmp_path / "allocated.log"
    monkeypatch.setattr(
        "app.services.operations.runner.operation_log_path", lambda _id: target
    )
    job = MaintenanceJobFacade(db, op)

    job.logs = "allocated\n"
    db.commit()

    assert op.log_file_path == str(target)
    assert target.read_text() == "allocated\n"


def test_facade_has_no_logs_before_anything_is_written(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    assert job.logs == ""
    assert job.has_logs is False


def test_facade_identity_matches_the_operation(db, repository):
    op = _operation(db, repository)
    job = MaintenanceJobFacade(db, op)

    assert job.id == op.id
    assert job.repository_id == repository.id
    assert job.repository_path == repository.path


def test_resolve_prefers_an_operation_of_the_right_kind(db, repository):
    op = _operation(db, repository, kind="check")

    resolved = resolve_maintenance_job(db, op.id, "check")

    assert isinstance(resolved, MaintenanceJobFacade)
    assert resolved.id == op.id


def test_resolve_ignores_an_operation_of_another_kind(db, repository):
    op = _operation(db, repository, kind="prune")
    legacy = CheckJob(id=op.id, repository_id=repository.id, status="completed")
    db.add(legacy)
    db.commit()

    resolved = resolve_maintenance_job(db, op.id, "check")

    assert isinstance(resolved, CheckJob)


def test_resolve_falls_back_to_the_legacy_row(db, repository):
    legacy = CheckJob(repository_id=repository.id, status="completed")
    db.add(legacy)
    db.commit()

    resolved = resolve_maintenance_job(db, legacy.id, "check")

    assert isinstance(resolved, CheckJob)


def test_resolve_returns_none_when_nothing_matches(db):
    assert resolve_maintenance_job(db, 4242, "check") is None


def test_claim_running_claims_a_queued_operation_once(db, repository):
    op = _operation(db, repository, status="queued")
    started = datetime(2026, 9, 6, 12, 0, 0)

    assert claim_running(db, op.id, "check", started) == 1
    db.commit()
    db.refresh(op)
    assert op.status == "running"
    assert op.started_at == started

    op.status = "completed"
    db.commit()
    assert claim_running(db, op.id, "check", started) == 0


def test_claim_running_still_claims_a_legacy_row(db, repository):
    legacy = CheckJob(repository_id=repository.id, status="pending")
    db.add(legacy)
    db.commit()
    started = datetime(2026, 9, 6, 12, 0, 0)

    assert claim_running(db, legacy.id, "check", started) == 1
    db.commit()
    db.refresh(legacy)
    assert legacy.status == "running"
