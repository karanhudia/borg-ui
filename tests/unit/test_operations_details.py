"""Phase 6: the two extension tables spec 6.2 names for wipe and rclone."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Base,
    Operation,
    OperationRcloneDetails,
    OperationWipeDetails,
    Repository,
)
from app.services.operations.details import rclone_details, wipe_details


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


def _operation(db, repository, kind):
    op = Operation(
        repository_id=repository.id,
        kind=kind,
        category={"wipe": "maintenance", "restore": "restore", "backup": "backup"}.get(
            kind, "mirror"
        ),
        status="queued",
        trigger="manual",
        priority=0,
        run_id="run-1",
    )
    db.add(op)
    db.commit()
    return op


def test_wipe_details_is_created_once_per_operation(db, repository):
    op = _operation(db, repository, "wipe")

    first = wipe_details(db, op)
    first.archive_count = 3
    second = wipe_details(db, op)

    assert first.operation_id == op.id
    assert second is first
    assert second.archive_count == 3
    assert db.query(OperationWipeDetails).count() == 1


def test_rclone_details_is_created_once_per_operation(db, repository):
    op = _operation(db, repository, "rclone_sync")

    first = rclone_details(db, op)
    first.direction = "cache_to_remote"
    first.operation = "sync"
    db.commit()

    assert rclone_details(db, op).direction == "cache_to_remote"
    assert db.query(OperationRcloneDetails).count() == 1


def test_details_rows_are_deleted_with_their_operation(db, repository):
    wipe_op = _operation(db, repository, "wipe")
    rclone_op = _operation(db, repository, "rclone_sync")
    wipe_details(db, wipe_op)
    rclone_details(db, rclone_op)
    db.commit()

    db.delete(wipe_op)
    db.delete(rclone_op)
    db.commit()

    assert db.query(OperationWipeDetails).count() == 0
    assert db.query(OperationRcloneDetails).count() == 0


def test_restore_details_is_created_once_per_operation(db, repository):
    from app.database.models import OperationRestoreDetails
    from app.services.operations.details import restore_details

    op = _operation(db, repository, "restore")

    first = restore_details(db, op)
    first.archive = "nas-2026-09-08"
    first.original_size = 3 * 1024**3
    second = restore_details(db, op)

    assert first.operation_id == op.id
    assert second is first
    assert second.archive == "nas-2026-09-08"
    assert second.original_size == 3 * 1024**3
    assert db.query(OperationRestoreDetails).count() == 1


def test_restore_details_row_is_deleted_with_its_operation(db, repository):
    from app.database.models import OperationRestoreDetails
    from app.services.operations.details import restore_details

    op = _operation(db, repository, "restore")
    restore_details(db, op)
    db.commit()

    db.delete(op)
    db.commit()

    assert db.query(OperationRestoreDetails).count() == 0


def test_backup_details_is_created_once_per_operation(db, repository):
    from app.database.models import OperationBackupDetails
    from app.services.operations.details import backup_details

    op = _operation(db, repository, "backup")

    first = backup_details(db, op)
    first.archive_name = "nas-2026-09-09"
    first.original_size = 3 * 1024**3
    first.maintenance_status = "running_prune"
    second = backup_details(db, op)

    assert first.operation_id == op.id
    assert second is first
    assert second.archive_name == "nas-2026-09-09"
    assert second.original_size == 3 * 1024**3
    assert second.retry_attempt == 1
    assert db.query(OperationBackupDetails).count() == 1


def test_backup_details_row_is_deleted_with_its_operation(db, repository):
    from app.database.models import OperationBackupDetails
    from app.services.operations.details import backup_details

    op = _operation(db, repository, "backup")
    backup_details(db, op)
    db.commit()

    db.delete(op)
    db.commit()

    assert db.query(OperationBackupDetails).count() == 0


def test_agent_job_and_script_execution_link_to_an_operation(db, repository):
    from app.database.models import AgentJob, AgentMachine, ScriptExecution

    op = _operation(db, repository, "backup")
    machine = AgentMachine(
        agent_id="agent-1",
        name="agent",
        token_hash="hash",
        token_prefix="prefix",
        status="online",
    )
    db.add(machine)
    db.flush()
    db.add(
        AgentJob(
            agent_machine_id=machine.id,
            operation_id=op.id,
            job_type="backup",
            status="queued",
            payload={},
        )
    )
    db.add(
        ScriptExecution(
            operation_id=op.id,
            hook_type="pre-backup",
            status="completed",
            triggered_by="backup",
        )
    )
    db.commit()

    db.delete(op)
    db.commit()

    assert db.query(ScriptExecution).count() == 0
    assert db.query(AgentJob).one().operation_id is None
