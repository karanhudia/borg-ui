from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    Archive,
    ArchiveChange,
    Base,
    Operation,
    Repository,
    SystemSettings,
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


def _repo(db):
    repo = Repository(name="r1", path="/tmp/r1", encryption="none", compression="lz4")
    db.add(repo)
    db.commit()
    return repo


@pytest.mark.unit
def test_operation_defaults(db):
    repo = _repo(db)
    op = Operation(
        repository_id=repo.id, kind="stats", category="index", run_id="run-1"
    )
    db.add(op)
    db.commit()
    db.refresh(op)
    assert op.status == "queued"
    assert op.trigger == "manual"
    assert op.priority == 10
    assert op.created_at is not None
    assert op.started_at is None


@pytest.mark.unit
def test_operation_columns_match_spec():
    cols = {c.name for c in Operation.__table__.columns}
    assert cols == {
        "id",
        "repository_id",
        "kind",
        "category",
        "status",
        "trigger",
        "priority",
        "run_id",
        "depends_on_id",
        "triggered_by_user_id",
        "scheduled_job_id",
        "backup_plan_run_id",
        "execution_mode",
        "process_pid",
        "process_start_time",
        "progress_percent",
        "progress_current",
        "progress_total",
        "progress_message",
        "error_message",
        "skip_reason",
        "log_file_path",
        "params",
        "result",
        "created_at",
        "started_at",
        "completed_at",
    }
    index_columns = {
        tuple(c.name for c in ix.columns) for ix in Operation.__table__.indexes
    }
    assert ("repository_id", "status") in index_columns
    assert ("status", "priority", "created_at") in index_columns
    assert ("category", "created_at") in index_columns


@pytest.mark.unit
def test_archive_unique_per_repository_and_cascade(db):
    repo = _repo(db)
    a = Archive(
        repository_id=repo.id,
        borg_id="abc",
        name="n",
        series="default",
        start=datetime(2026, 9, 1),
    )
    db.add(a)
    db.commit()
    db.add(ArchiveChange(archive_id=a.id, path="/x", change="added", size_after=1))
    db.commit()
    assert a.history_state == "pending"
    assert a.history_truncated is False
    dup = Archive(
        repository_id=repo.id,
        borg_id="abc",
        name="n2",
        series="default",
        start=datetime(2026, 9, 2),
    )
    db.add(dup)
    with pytest.raises(Exception):
        db.commit()
    db.rollback()
    db.delete(db.get(Repository, repo.id))
    db.commit()
    assert db.query(Archive).count() == 0
    assert db.query(ArchiveChange).count() == 0


@pytest.mark.unit
def test_system_settings_new_columns(db):
    s = SystemSettings()
    db.add(s)
    db.commit()
    db.refresh(s)
    assert s.index_workers == 2
    assert s.background_paused is False


@pytest.mark.unit
def test_config_has_index_archive_info_per_run():
    from app.config import settings

    assert settings.index_archive_info_per_run == 20


@pytest.mark.unit
def test_serialize_operation_shape(db):
    from app.services.operations.models import (
        is_success,
        is_terminal,
        serialize_operation,
    )

    repo = _repo(db)
    op = Operation(
        repository_id=repo.id,
        kind="archive_sync",
        category="index",
        run_id="run-9",
        trigger="schedule",
        priority=5,
        params={"archive_name": "a1"},
        status="completed",
        result={"count": 3},
    )
    db.add(op)
    db.commit()
    item = serialize_operation(op, repository_name=repo.name, repository_path=repo.path)
    assert item["id"] == op.id
    assert item["type"] == "archive_sync"
    assert item["kind"] == "archive_sync"
    assert item["category"] == "index"
    assert item["triggered_by"] == "schedule"
    assert item["trigger"] == "schedule"
    assert item["repository"] == "r1"
    assert item["repository_path"] == "/tmp/r1"
    assert item["archive_name"] == "a1"
    assert item["activity_key"] == f"operation:{op.id}"
    assert item["followups"] == []
    assert item["has_logs"] is False
    assert is_terminal(op) and is_success(op)
    op.status = "running"
    assert not is_terminal(op)
