"""Phase 8: an `operations` row wearing the legacy backup-job surface."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    BackupJob,
    BackupPlan,
    BackupPlanRun,
    Base,
    Operation,
    Repository,
)
from app.services.operations.backup_facade import (
    BackupJobFacade,
    backup_jobs_for_archive_names,
    backup_jobs_started_since,
    create_backup_operation,
    latest_backup_jobs_by_repository,
    list_backup_jobs,
    newest_backup_job,
    resolve_backup_job,
    wait_for_backup_operation,
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
    repo = Repository(
        name="nas", path="/repo/nas", borg_version=1, repository_type="local"
    )
    db.add(repo)
    db.commit()
    return repo


@pytest.fixture()
def log_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("app.config.settings.data_dir", str(tmp_path))
    return tmp_path / "logs"


def _backup_operation(db, repository, status="queued", trigger="manual", **kw):
    op = Operation(
        repository_id=repository.id if repository is not None else None,
        kind="backup",
        category="backup",
        status=status,
        trigger=trigger,
        priority=0,
        run_id="run-1",
        params={"executor": "server"},
        **kw,
    )
    db.add(op)
    db.commit()
    return op


def test_facade_maps_status_words_and_progress(db, repository):
    op = _backup_operation(db, repository)
    job = BackupJobFacade(db, op)

    assert job.status == "pending"
    assert job.repository == "/repo/nas"
    assert job.execution_mode == "local"
    assert job.triggered_by == "manual"
    assert job.retry_attempt == 1

    job.status = "running"
    job.progress = 42
    job.progress_percent = 42.5
    job.current_file = "/home/k/docs"
    job.execution_mode = "local"
    db.commit()

    assert op.status == "running"
    assert op.progress_percent == 42.5
    assert job.progress == 42
    assert op.progress_message == "/home/k/docs"
    assert op.execution_mode == "server"


def test_detail_columns_land_on_the_details_row(db, repository):
    op = _backup_operation(db, repository)
    job = BackupJobFacade(db, op)
    job.archive_name = "nas-2026-09-09"
    job.original_size = 5
    job.maintenance_status = "running_prune"
    job.remote_hostname = "box"
    db.commit()

    again = BackupJobFacade(db, db.get(Operation, op.id))
    assert again.archive_name == "nas-2026-09-09"
    assert again.original_size == 5
    assert again.maintenance_status == "running_prune"
    assert again.remote_hostname == "box"
    with pytest.raises(AttributeError):
        again.no_such_column


def test_backup_plan_id_is_derived_from_the_run(db, repository):
    plan = BackupPlan(name="nightly", source_directories='["/data"]')
    db.add(plan)
    db.flush()
    run = BackupPlanRun(backup_plan_id=plan.id, trigger="manual", status="running")
    db.add(run)
    db.flush()
    op = _backup_operation(db, repository, trigger="plan", backup_plan_run_id=run.id)
    job = BackupJobFacade(db, op)

    assert job.backup_plan_id == plan.id
    assert job.triggered_by == "backup_plan"


def test_logs_go_to_the_operation_log_file(db, repository, log_dir):
    op = _backup_operation(db, repository)
    job = BackupJobFacade(db, op)

    job.logs = "line one\nline two"
    db.commit()

    assert op.log_file_path == str(log_dir / f"operation_{op.id}.log")
    assert job.logs == "line one\nline two"

    job.logs = "Logs saved to: something.log"
    assert job.logs == "line one\nline two"


def test_resolve_prefers_the_operation_and_falls_back_to_legacy(db, repository):
    # The two tables number their rows independently, and an operation wins a
    # shared id (Appendix B). The legacy row therefore takes an explicit id
    # past the operation's, so the fallback branch is exercised every run
    # rather than only when the two sequences happen to diverge.
    op = _backup_operation(db, repository)
    legacy = BackupJob(id=op.id + 500, repository="/repo/nas", status="completed")
    db.add(legacy)
    db.commit()

    assert isinstance(resolve_backup_job(db, op.id), BackupJobFacade)
    assert resolve_backup_job(db, legacy.id + 1000) is None
    assert resolve_backup_job(db, legacy.id) is legacy


def test_create_backup_operation_records_route_and_params(db, repository):
    repository.source_ssh_connection_id = None
    job = create_backup_operation(
        db,
        repository,
        trigger="schedule",
        executor="server",
        params={"archive_name": "nas-{now}", "skip_hooks": None},
        scheduled_job_id=None,
    )

    op = db.get(Operation, job.id)
    assert op.kind == "backup"
    assert op.trigger == "schedule"
    assert op.priority == 5
    assert op.params == {"archive_name": "nas-{now}", "executor": "server"}
    assert op.execution_mode == "server"
    assert job.route_strategy is not None


def test_create_backup_operation_without_a_repository_keeps_the_path(db):
    job = create_backup_operation(
        db,
        None,
        trigger="manual",
        executor="server",
        repository_path="/nowhere",
        commit=False,
    )
    job.status = "failed"
    db.commit()

    assert job.repository == "/nowhere"
    assert job.repository_id is None
    assert db.get(Operation, job.id).status == "failed"


@pytest.mark.asyncio
async def test_wait_for_backup_operation_returns_the_legacy_word(db, repository):
    op = _backup_operation(db, repository, status="running")

    async def _finish():
        op.status = "completed_with_warnings"
        db.commit()

    import asyncio

    asyncio.get_running_loop().call_later(
        0.05, lambda: asyncio.ensure_future(_finish())
    )
    assert (
        await wait_for_backup_operation(db, op.id, poll_interval_seconds=0.01)
        == "completed_with_warnings"
    )


def test_list_backup_jobs_unions_both_tables_newest_first(db, repository):
    old = BackupJob(
        repository="/repo/nas",
        status="completed",
        created_at=datetime(2026, 9, 1),
    )
    db.add(old)
    db.commit()
    op = _backup_operation(db, repository, status="completed")
    op.created_at = datetime(2026, 9, 9)
    db.commit()

    jobs = list_backup_jobs(db, 10)
    assert [j.id for j in jobs] == [op.id, old.id]
    assert list_backup_jobs(db, 10, manual_only=True)[0].id == op.id
    assert list_backup_jobs(db, 10, scheduled_only=True) == []
    assert list_backup_jobs(db, 10, repository_path="/other") == []


def test_started_since_archive_names_and_per_repository_helpers(db, repository):
    now = datetime.utcnow()
    legacy = BackupJob(
        repository="/repo/nas",
        repository_id=repository.id,
        status="completed",
        archive_name="nas-old",
        started_at=now - timedelta(days=3),
        created_at=now - timedelta(days=3),
    )
    db.add(legacy)
    db.commit()
    op = _backup_operation(db, repository, status="running")
    op.started_at = now - timedelta(hours=1)
    job = BackupJobFacade(db, op)
    job.archive_name = "nas-new"
    db.commit()

    recent = backup_jobs_started_since(db, now - timedelta(days=7))
    assert [j.id for j in recent] == [op.id, legacy.id]
    assert backup_jobs_started_since(db, now - timedelta(days=1))[0].id == op.id

    by_name = backup_jobs_for_archive_names(db, repository, {"nas-old", "nas-new"})
    assert {j.archive_name for j in by_name} == {"nas-old", "nas-new"}

    latest = latest_backup_jobs_by_repository(db)
    assert latest["/repo/nas"].id == op.id
    assert latest_backup_jobs_by_repository(db, running=True)["/repo/nas"].id == op.id
    assert newest_backup_job(db, running=True).id == op.id
    assert newest_backup_job(db, terminal=True).id == legacy.id
