"""Phase 8: the backup executor is a thin shell around backup_service."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
from app.services.operations.backup_facade import (
    CANCELLED_BY_USER,
    BackupJobFacade,
)
from app.services.operations.executors import get_executor, load_default_executors


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


class FakeContext:
    """The slice of OperationContext an executor uses, matching the shape
    `tests/unit/test_operations_phase6_executors.py` established."""

    def __init__(self, db, operation):
        self.db = db
        self.operation = operation
        self.operation_id = operation.id
        self.repository_id = operation.repository_id
        self.kind = operation.kind
        self.params = dict(operation.params or {})
        self.lines = []
        self._cancelled = False

    def cancelled(self):
        return self._cancelled

    def log(self, line):
        self.lines.append(line)

    async def progress(self, **kwargs):
        return None


def _operation(db, repository, params=None, status="running"):
    op = Operation(
        repository_id=repository.id if repository is not None else None,
        kind="backup",
        category="backup",
        status=status,
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params
        or {"executor": "server", "archive_name": "nas-1", "skip_hooks": True},
    )
    db.add(op)
    db.commit()
    return op


@pytest.mark.asyncio
async def test_run_backup_passes_params_to_the_service(db, repository, monkeypatch):
    load_default_executors()
    op = _operation(db, repository)
    seen = {}

    async def _execute_backup(job_id, repository_path, session, **kw):
        seen.update(
            job_id=job_id, repository_path=repository_path, session=session, **kw
        )
        job = BackupJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        job.archive_name = kw["archive_name"]
        job.original_size = 12
        db.commit()

    monkeypatch.setattr(
        "app.services.backup_service.backup_service.execute_backup", _execute_backup
    )
    outcome = await get_executor("backup")(FakeContext(db, op))

    assert seen == {
        "job_id": op.id,
        "repository_path": "/repo/nas",
        "session": None,
        "archive_name": "nas-1",
        "skip_hooks": True,
    }
    assert outcome.status == "completed"
    assert outcome.result == {
        "archive_name": "nas-1",
        "original_size": 12,
        "compressed_size": 0,
        "deduplicated_size": 0,
        "nfiles": 0,
    }


@pytest.mark.asyncio
async def test_run_backup_keeps_the_cancelled_verdict(db, repository, monkeypatch):
    load_default_executors()
    op = _operation(db, repository)
    ctx = FakeContext(db, op)

    async def _execute_backup(job_id, repository_path, session, **kw):
        ctx._cancelled = True
        job = BackupJobFacade(db, db.get(Operation, job_id))
        job.status = "failed"
        job.error_message = "borg died"
        db.commit()

    monkeypatch.setattr(
        "app.services.backup_service.backup_service.execute_backup", _execute_backup
    )
    outcome = await get_executor("backup")(ctx)

    assert outcome.status == "failed"
    assert db.get(Operation, op.id).status == "cancelled"
    assert db.get(Operation, op.id).error_message == CANCELLED_BY_USER


@pytest.mark.asyncio
async def test_post_hook_failure_still_enqueues_the_index_chain(
    db, repository, monkeypatch
):
    load_default_executors()
    op = _operation(db, repository)

    async def _execute_backup(job_id, repository_path, session, **kw):
        job = BackupJobFacade(db, db.get(Operation, job_id))
        job.status = "failed"
        job.error_message = json.dumps(
            {"key": "backend.errors.service.postBackupHooksFailed", "params": {}}
        )
        db.commit()

    monkeypatch.setattr(
        "app.services.backup_service.backup_service.execute_backup", _execute_backup
    )
    monkeypatch.setattr(
        "app.services.operations.followups.history_enabled", lambda db: False
    )
    outcome = await get_executor("backup")(FakeContext(db, op))

    assert outcome.status == "failed"
    chain = (
        db.query(Operation)
        .filter(Operation.run_id == "run-1", Operation.kind != "backup")
        .order_by(Operation.id)
        .all()
    )
    assert [c.kind for c in chain] == ["archive_sync", "history_merge", "stats"]
    assert chain[0].depends_on_id is None
    assert chain[0].trigger == "followup"


@pytest.mark.asyncio
async def test_run_backup_agent_path_queues_and_waits(db, repository, monkeypatch):
    load_default_executors()
    repository.executor_type = "agent"
    db.commit()
    op = _operation(
        db,
        repository,
        params={
            "executor": "agent",
            "archive_name": "nas-1",
            "compression_override": "zstd",
        },
    )
    seen = {}

    def _queue(session, backup_job, repo, **kw):
        seen["queue"] = kw
        backup_job.execution_mode = "agent"
        return SimpleNamespace(id=77, payload={})

    async def _dispatch(session, agent_job, **context):
        seen["dispatch"] = agent_job.id
        return True

    async def _wait(session, agent_job_id, backup_job_id, is_cancelled, **kw):
        job = BackupJobFacade(db, db.get(Operation, backup_job_id))
        job.status = "completed_with_warnings"
        job.archive_name = "nas-1"
        db.commit()
        return "completed_with_warnings"

    monkeypatch.setattr(
        "app.services.operations.executors.backup.queue_agent_backup_job", _queue
    )
    monkeypatch.setattr(
        "app.services.operations.executors.backup.dispatch_agent_job_best_effort",
        _dispatch,
    )
    monkeypatch.setattr(
        "app.services.operations.executors.backup.wait_for_agent_backup_job", _wait
    )
    outcome = await get_executor("backup")(FakeContext(db, op))

    assert seen["queue"] == {"archive_name": "nas-1", "compression": "zstd"}
    assert seen["dispatch"] == 77
    assert outcome.status == "completed_with_warnings"
    assert db.get(Operation, op.id).execution_mode == "agent"


@pytest.mark.asyncio
async def test_run_backup_without_a_repository_is_skipped(db):
    load_default_executors()
    op = _operation(db, None)
    outcome = await get_executor("backup")(FakeContext(db, op))
    assert outcome.status == "skipped"
    assert outcome.skip_reason == "repository_missing"


@pytest.mark.asyncio
async def test_run_backup_reports_a_graceful_skip_as_skipped(
    db, repository, monkeypatch
):
    """A pre-backup script standing the backup down writes `skipped`; the
    runner must record that, not a failure."""
    load_default_executors()
    op = _operation(db, repository)

    async def _execute_backup(job_id, repository_path, session, **kw):
        job = BackupJobFacade(db, db.get(Operation, job_id))
        job.status = "skipped"
        job.error_message = "Skipped by 'leader-check'"
        db.commit()

    monkeypatch.setattr(
        "app.services.backup_service.backup_service.execute_backup", _execute_backup
    )
    outcome = await get_executor("backup")(FakeContext(db, op))

    assert outcome.status == "skipped"
    assert outcome.skip_reason == "Skipped by 'leader-check'"
    assert outcome.error_message is None
