"""Phase 5: maintenance work is enqueued, not dispatched."""

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
from app.services.operations.maintenance_start import (
    active_maintenance_operation,
    start_maintenance,
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


def test_start_enqueues_a_queued_operation(db, repository):
    op = start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={"max_duration": 3600, "extra_flags": None},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert op.status == "queued"
    assert op.kind == "check"
    assert op.category == "maintenance"
    assert op.trigger == "manual"
    assert op.repository_id == repository.id
    assert op.params["max_duration"] == 3600


def test_start_rejects_a_second_check_on_the_same_repository(db, repository):
    start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    with pytest.raises(HTTPException) as excinfo:
        start_maintenance(
            db,
            repository,
            "check",
            trigger="manual",
            params={},
            user_id=None,
            duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["key"] == "backend.errors.repo.checkAlreadyRunning"


def test_start_rejects_a_second_check_when_a_legacy_row_is_still_running(
    db, repository
):
    """A pre-phase-5 install can restart mid-check, leaving a `running`
    `CheckJob` row. `active_maintenance_operation` only sees `Operation`
    rows, so without this check a second check would queue right alongside
    it instead of getting the usual 409."""
    from app.database.models import CheckJob

    db.add(CheckJob(repository_id=repository.id, status="running"))
    db.commit()

    with pytest.raises(HTTPException) as excinfo:
        start_maintenance(
            db,
            repository,
            "check",
            trigger="manual",
            params={},
            user_id=None,
            duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail["key"] == "backend.errors.repo.checkAlreadyRunning"


def test_start_allows_a_different_kind_to_queue_alongside(db, repository):
    start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    prune = start_maintenance(
        db,
        repository,
        "prune",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.pruneAlreadyRunning",
    )

    assert prune.status == "queued"


def test_start_allows_a_new_run_once_the_last_one_finished(db, repository):
    first = start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )
    first.status = "completed"
    db.commit()

    second = start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert second.id != first.id


def test_active_maintenance_operation_finds_queued_and_running(db, repository):
    op = start_maintenance(
        db,
        repository,
        "check",
        trigger="schedule",
        params={},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert active_maintenance_operation(db, repository.id, "check").id == op.id

    op.status = "running"
    db.commit()
    assert active_maintenance_operation(db, repository.id, "check").id == op.id

    op.status = "failed"
    db.commit()
    assert active_maintenance_operation(db, repository.id, "check") is None


def test_params_drop_none_values(db, repository):
    op = start_maintenance(
        db,
        repository,
        "check",
        trigger="manual",
        params={"max_duration": None, "extra_flags": "--verify-data"},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert "max_duration" not in op.params
    assert op.params["extra_flags"] == "--verify-data"


def test_a_scheduled_check_carries_the_schedule_trigger(db, repository):
    op = start_maintenance(
        db,
        repository,
        "check",
        trigger="schedule",
        params={"scheduled_check": True},
        user_id=None,
        duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
    )

    assert op.trigger == "schedule"
    # Spec 6.3: schedule runs at priority 5, behind manual work.
    assert op.priority == 5


def test_start_refuses_a_kind_that_is_not_maintenance(db, repository):
    with pytest.raises(ValueError):
        start_maintenance(
            db,
            repository,
            "backup",
            trigger="manual",
            params={},
            user_id=None,
            duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
        )


def test_inline_maintenance_starts_running_so_the_runner_leaves_it_alone(
    db, repository
):
    from app.services.operations.maintenance_start import start_inline_maintenance

    op = start_inline_maintenance(
        db, repository, "prune", params={"dry_run": True}, user_id=None
    )

    # Spec 7.1 dispatches queued rows only, so an inline row is never picked up.
    assert op.status == "running"
    assert op.started_at is not None


def test_finish_inline_enqueues_the_followup_chain(db, repository):
    from app.services.operations.executors import load_default_executors
    from app.services.operations.maintenance_start import (
        finish_inline_maintenance,
        start_inline_maintenance,
    )

    load_default_executors()

    op = start_inline_maintenance(
        db, repository, "prune", params={"keep_daily": 7}, user_id=None
    )
    op.status = "completed"
    db.commit()

    finish_inline_maintenance(db, op)

    followups = (
        db.query(Operation)
        .filter(Operation.depends_on_id.isnot(None), Operation.run_id == op.run_id)
        .order_by(Operation.id.asc())
        .all()
    )
    # Spec 7.4: prune is followed by archive_sync, history_merge, stats.
    # history_merge is not plan gated (only history_index is), so the chain is
    # the same on Community.
    assert [f.kind for f in followups] == ["archive_sync", "history_merge", "stats"]
    assert all(f.trigger == "followup" for f in followups)


def test_finish_inline_enqueues_nothing_after_a_failure(db, repository):
    from app.services.operations.maintenance_start import (
        finish_inline_maintenance,
        start_inline_maintenance,
    )

    op = start_inline_maintenance(db, repository, "prune", params={}, user_id=None)
    op.status = "failed"
    db.commit()

    finish_inline_maintenance(db, op)

    assert db.query(Operation).count() == 1


def test_finish_inline_skips_the_chain_when_asked(db, repository):
    from app.services.operations.maintenance_start import (
        finish_inline_maintenance,
        start_inline_maintenance,
    )

    op = start_inline_maintenance(
        db, repository, "prune", params={"dry_run": True}, user_id=None
    )
    op.status = "completed"
    db.commit()

    finish_inline_maintenance(db, op, enqueue_followups=False)

    assert db.query(Operation).count() == 1


def test_active_delete_is_scoped_to_one_archive(db, repository):
    from app.services.operations.enqueue import enqueue
    from app.services.operations.maintenance_start import active_delete_for_archive

    enqueue(
        db,
        "delete_archive",
        repository_id=repository.id,
        trigger="manual",
        params={"archive_name": "nightly-1"},
    )

    assert active_delete_for_archive(db, repository.id, "nightly-1") is not None
    assert active_delete_for_archive(db, repository.id, "nightly-2") is None


def test_active_delete_sees_a_legacy_row_for_the_same_archive(db, repository):
    from app.database.models import DeleteArchiveJob
    from app.services.operations.maintenance_start import active_delete_for_archive

    db.add(
        DeleteArchiveJob(
            repository_id=repository.id,
            repository_path=repository.path,
            archive_name="nightly-1",
            status="running",
        )
    )
    db.commit()

    assert active_delete_for_archive(db, repository.id, "nightly-1") is not None
    assert active_delete_for_archive(db, repository.id, "nightly-2") is None
