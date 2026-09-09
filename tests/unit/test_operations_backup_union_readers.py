"""Phase 8: every reader of the backup history sees both tables."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    BackupJob,
    Base,
    Operation,
    OperationBackupDetails,
    OperationBackupRetryLineage,
    Repository,
    SSHConnection,
)
from app.services.operations.details import backup_details


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
    repo = Repository(
        name="nas", path="/repo/nas", borg_version=1, repository_type="local"
    )
    db.add(repo)
    db.commit()
    return repo


def _pair(db, repository, *, archive="nas-new", legacy_archive="nas-old"):
    """One legacy row and one operation, the operation the newer of the two."""
    now = datetime.utcnow()
    legacy = BackupJob(
        repository=repository.path,
        repository_id=repository.id,
        status="completed",
        archive_name=legacy_archive,
        original_size=1,
        deduplicated_size=1,
        started_at=now - timedelta(days=2),
        completed_at=now - timedelta(days=2),
        created_at=now - timedelta(days=2),
    )
    db.add(legacy)
    operation = Operation(
        repository_id=repository.id,
        kind="backup",
        category="backup",
        status="completed",
        trigger="manual",
        priority=0,
        run_id="run-1",
        params={"executor": "server"},
        started_at=now - timedelta(hours=1),
        completed_at=now - timedelta(minutes=30),
        created_at=now - timedelta(hours=1),
    )
    db.add(operation)
    db.flush()
    details = backup_details(db, operation)
    details.archive_name = archive
    details.original_size = 10
    details.deduplicated_size = 5
    db.commit()
    return legacy, operation


def test_mqtt_reads_both_tables(db, repository):
    from app.services.mqtt_service import BackupJobQueryService

    legacy, operation = _pair(db, repository)
    operation.status = "running"
    db.commit()

    service = BackupJobQueryService()
    assert (
        service.fetch_latest_backup_jobs_by_repository(db)[repository.path].id
        == operation.id
    )
    assert (
        service.fetch_running_backup_jobs_by_repository(db)[repository.path].id
        == operation.id
    )

    operation.status = "failed"
    db.commit()
    assert service.fetch_failed_repositories(db, {repository.path: repository.id}) == {
        repository.id
    }


def test_metrics_read_the_newer_operation(db, repository):
    from app.services.operations.backup_facade import latest_backup_job_for_repository

    legacy, operation = _pair(db, repository)

    assert latest_backup_job_for_repository(db, repository).id == operation.id
    assert (
        latest_backup_job_for_repository(
            db,
            repository,
            statuses=("completed", "completed_with_warnings"),
            order="completed",
        ).original_size
        == 10
    )


def test_started_since_covers_dashboard_and_monitoring(db, repository):
    from app.services.operations.backup_facade import backup_jobs_started_since

    legacy, operation = _pair(db, repository)

    jobs = backup_jobs_started_since(db, datetime.utcnow() - timedelta(days=7))
    assert [job.id for job in jobs] == [operation.id, legacy.id]
    assert [job.archive_name for job in jobs] == ["nas-new", "nas-old"]


def test_archive_metadata_enriches_from_both_tables(db, repository):
    from app.utils.archive_job_metadata import enrich_archives_with_backup_metadata

    _pair(db, repository)

    enriched = enrich_archives_with_backup_metadata(
        [{"name": "nas-new"}, {"name": "nas-old"}], repository, db
    )
    assert {item["name"]: item.get("triggered_by") for item in enriched} == {
        "nas-new": "manual",
        "nas-old": "manual",
    }


def test_retention_marks_and_purges_operation_rows(db, repository):
    from app.services.job_history_retention import (
        mark_jobs_of_pruned_archives,
        purge_job_rows,
    )

    legacy, operation = _pair(db, repository)

    assert mark_jobs_of_pruned_archives(db, repository.id, ["nas-new", "nas-old"]) == 2
    db.expire_all()
    assert db.get(OperationBackupDetails, operation.id).archive_pruned_at is not None
    assert db.get(BackupJob, legacy.id).archive_pruned_at is not None

    db.add(
        OperationBackupRetryLineage(
            attempt_number=2,
            requested_at=datetime.utcnow() - timedelta(days=400),
            created_operation_id=operation.id,
            request_snapshot={},
        )
    )
    db.commit()

    purge_job_rows(db, datetime.utcnow() - timedelta(days=30))
    assert db.query(OperationBackupRetryLineage).count() == 0


def test_deleting_an_operation_takes_its_details_row(db, repository):
    _legacy, operation = _pair(db, repository)

    db.delete(operation)
    db.commit()

    assert db.query(OperationBackupDetails).count() == 0


def test_connection_deletion_nulls_the_details_row(db, repository):
    connection = SSHConnection(host="box", username="backup", port=22)
    db.add(connection)
    db.flush()
    _legacy, operation = _pair(db, repository)
    details = db.get(OperationBackupDetails, operation.id)
    details.source_ssh_connection_id = connection.id
    db.commit()

    db.delete(connection)
    db.commit()
    db.expire_all()

    assert db.get(OperationBackupDetails, operation.id).source_ssh_connection_id is None


def test_stale_maintenance_sweep_covers_details_rows(db, repository):
    from app.utils.process_utils import _mark_stale_backup_maintenance_failed

    _legacy, operation = _pair(db, repository)
    details = db.get(OperationBackupDetails, operation.id)
    details.maintenance_status = "running_compact"
    db.commit()

    assert _mark_stale_backup_maintenance_failed(db, datetime.utcnow()) == 1
    db.expire_all()
    assert db.get(OperationBackupDetails, operation.id).maintenance_status == (
        "compact_failed"
    )


def test_latest_by_repository_loads_only_the_newest_row_per_table(db, repository):
    """The newest row per repository is picked in SQL, so a long history is
    not materialized on every MQTT sync."""
    from app.services.operations.backup_facade import latest_backup_jobs_by_repository

    now = datetime.utcnow()
    for index in range(5):
        db.add(
            BackupJob(
                repository=repository.path,
                repository_id=repository.id,
                status="completed",
                archive_name=f"legacy-{index}",
                created_at=now - timedelta(days=10 + index),
            )
        )
        operation = Operation(
            repository_id=repository.id,
            kind="backup",
            category="backup",
            status="completed",
            trigger="manual",
            priority=0,
            run_id=f"run-{index}",
            params={"executor": "server"},
            created_at=now - timedelta(days=index),
        )
        db.add(operation)
        db.flush()
        backup_details(db, operation).archive_name = f"op-{index}"
    db.commit()

    loaded: list[str] = []

    @event.listens_for(db.get_bind(), "before_cursor_execute")
    def _record(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            loaded.append(statement)

    try:
        latest = latest_backup_jobs_by_repository(db)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _record)

    assert latest[repository.path].archive_name == "op-0"
    # Two ranked reads (one per table), neither a plain scan of the history.
    ranked = [statement for statement in loaded if "row_number" in statement.lower()]
    assert len(ranked) == 2


def test_mqtt_last_backup_ignores_a_skipped_operation(db, repository):
    """`skipped` is terminal in the operations vocabulary but was never a
    backup outcome, so the Home Assistant sensor keeps reporting the real
    last run."""
    from app.services.mqtt_service import TERMINAL_JOB_STATUSES
    from app.services.operations.backup_facade import newest_backup_job

    _legacy, operation = _pair(db, repository)
    now = datetime.utcnow()
    skipped = Operation(
        repository_id=repository.id,
        kind="backup",
        category="backup",
        status="skipped",
        trigger="manual",
        priority=0,
        run_id="run-skipped",
        params={"executor": "server"},
        created_at=now,
        completed_at=now,
    )
    db.add(skipped)
    db.commit()

    latest_terminal = newest_backup_job(
        db, terminal=True, terminal_statuses=TERMINAL_JOB_STATUSES
    )
    assert latest_terminal.id == operation.id
    # The unnarrowed call is the one that would surface the skipped run.
    assert newest_backup_job(db, terminal=True).id == skipped.id
