"""Phase 5: the maintenance executors (spec 6.3, 7.4, section 13 phase 5)."""

import asyncio

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
from app.services.operations.executors import get_executor, load_default_executors
from app.services.operations.job_facade import MaintenanceJobFacade


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


class FakeContext:
    """The slice of OperationContext a maintenance executor uses."""

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


def _operation(db, repository, kind="check", params=None, category="maintenance"):
    op = Operation(
        repository_id=repository.id,
        kind=kind,
        category=category,
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params or {},
    )
    db.add(op)
    db.commit()
    return op


def _completing(db, status="completed", error=None):
    """A router stand-in that records the verdict the way a real service does."""

    async def call(self, job_id, *args, **kwargs):
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = status
        if error is not None:
            job.error_message = error
        db.commit()

    return call


def test_every_maintenance_kind_has_an_executor():
    load_default_executors()
    for kind in ("check", "prune", "compact", "delete_archive", "restore_check"):
        assert get_executor(kind) is not None


@pytest.mark.asyncio
async def test_check_reports_the_status_the_service_wrote(db, repository, monkeypatch):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository, params={"max_duration": 3600})
    ctx = FakeContext(db, op)
    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.check", _completing(db), raising=True
    )

    outcome = await maintenance.run_check(ctx)

    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_check_reports_failure_with_the_services_message(
    db, repository, monkeypatch
):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository)
    ctx = FakeContext(db, op)
    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.check",
        _completing(db, status="failed", error="borg exited 2"),
        raising=True,
    )

    outcome = await maintenance.run_check(ctx)

    assert outcome.status == "failed"
    assert outcome.error_message == "borg exited 2"


@pytest.mark.asyncio
async def test_check_fails_when_the_service_records_no_verdict(
    db, repository, monkeypatch
):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository)
    ctx = FakeContext(db, op)

    async def silent(self, job_id, *args, **kwargs):
        return None

    monkeypatch.setattr("app.core.borg_router.BorgRouter.check", silent, raising=True)

    outcome = await maintenance.run_check(ctx)

    assert outcome.status == "failed"


@pytest.mark.asyncio
async def test_check_skips_when_the_repository_is_gone(db, repository):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository)
    op.repository_id = None
    db.commit()
    ctx = FakeContext(db, op)

    outcome = await maintenance.run_check(ctx)

    assert outcome.status == "skipped"
    assert outcome.skip_reason == "repository_missing"


@pytest.mark.asyncio
async def test_check_stamps_last_check_on_success(db, repository, monkeypatch):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository)
    ctx = FakeContext(db, op)
    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.check", _completing(db), raising=True
    )

    await maintenance.run_check(ctx)

    db.refresh(repository)
    assert repository.last_check is not None


@pytest.mark.asyncio
async def test_check_does_not_stamp_last_check_on_failure(db, repository, monkeypatch):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository)
    ctx = FakeContext(db, op)
    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.check",
        _completing(db, status="failed"),
        raising=True,
    )

    await maintenance.run_check(ctx)

    db.refresh(repository)
    assert repository.last_check is None


@pytest.mark.asyncio
async def test_check_cancellation_terminates_the_tracked_borg_process(
    db, repository, monkeypatch
):
    """`run_check`'s canceller is `getattr(check_service, "cancel_check",
    None)`; before `cancel_check` existed, `cancel_watcher` saw the flag but
    had nothing to call, so a cancelled check operation left its Borg
    process running untouched."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.check_service import check_service
    from app.services.operations.executors import maintenance

    op = _operation(db, repository)
    ctx = FakeContext(db, op)
    ctx._cancelled = True

    fake_process = MagicMock()
    fake_process.pid = 4242
    fake_process.wait = AsyncMock(return_value=None)
    check_service.running_processes[op.id] = fake_process

    async def call(self, job_id, *args, **kwargs):
        # Give the cancel watcher a scheduling turn before completing, the
        # way a real Borg subprocess wait would.
        await asyncio.sleep(0.05)
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "cancelled"
        db.commit()

    monkeypatch.setattr("app.core.borg_router.BorgRouter.check", call, raising=True)

    try:
        await maintenance.run_check(ctx)
        fake_process.terminate.assert_called_once()
    finally:
        check_service.running_processes.pop(op.id, None)


@pytest.mark.asyncio
async def test_prune_passes_the_retention_policy_from_params(
    db, repository, monkeypatch
):
    from app.services.operations.executors import maintenance

    op = _operation(
        db,
        repository,
        kind="prune",
        params={
            "keep_hourly": 0,
            "keep_daily": 7,
            "keep_weekly": 4,
            "keep_monthly": 6,
            "keep_quarterly": 0,
            "keep_yearly": 1,
            "keep_within": "2d",
        },
    )
    ctx = FakeContext(db, op)
    seen = {}

    async def fake_prune(self, job_id, *args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.prune", fake_prune, raising=True
    )

    outcome = await maintenance.run_prune(ctx)

    assert outcome.status == "completed"
    assert seen["args"] == (0, 7, 4, 6, 0, 1, False)
    assert seen["kwargs"]["keep_within"] == "2d"


@pytest.mark.asyncio
async def test_prune_omits_keep_within_when_it_is_not_set(db, repository, monkeypatch):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository, kind="prune", params={"keep_daily": 7})
    ctx = FakeContext(db, op)
    seen = {}

    async def fake_prune(self, job_id, *args, **kwargs):
        seen["kwargs"] = kwargs
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.prune", fake_prune, raising=True
    )

    await maintenance.run_prune(ctx)

    assert "keep_within" not in seen["kwargs"]


@pytest.mark.asyncio
async def test_compact_stamps_last_compact_on_success(db, repository, monkeypatch):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository, kind="compact")
    ctx = FakeContext(db, op)

    async def fake_compact(self, job_id):
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    outcome = await maintenance.run_compact(ctx)

    assert outcome.status == "completed"
    db.refresh(repository)
    assert repository.last_compact is not None


@pytest.mark.asyncio
async def test_delete_archive_passes_the_archive_name(db, repository, monkeypatch):
    from app.services.operations.executors import maintenance

    op = _operation(
        db,
        repository,
        kind="delete_archive",
        params={"archive_name": "aid:deadbeef"},
    )
    ctx = FakeContext(db, op)
    seen = {}

    async def fake_delete(self, job_id, archive_name):
        seen["archive"] = archive_name
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.delete_archive", fake_delete, raising=True
    )

    outcome = await maintenance.run_delete_archive(ctx)

    assert outcome.status == "completed"
    assert seen["archive"] == "aid:deadbeef"


@pytest.mark.asyncio
async def test_delete_archive_fails_without_an_archive_name(db, repository):
    from app.services.operations.executors import maintenance

    op = _operation(db, repository, kind="delete_archive", params={})
    ctx = FakeContext(db, op)

    outcome = await maintenance.run_delete_archive(ctx)

    assert outcome.status == "failed"


@pytest.mark.asyncio
async def test_restore_check_runs_the_service_with_the_operation_id(
    db, repository, monkeypatch
):
    from app.services.operations.executors import maintenance

    op = _operation(
        db,
        repository,
        kind="restore_check",
        params={"probe_paths": "[]", "full_archive": True},
    )
    op.category = "restore"
    db.commit()
    ctx = FakeContext(db, op)
    seen = {}

    async def fake_execute(job_id, repository_id):
        seen["job_id"] = job_id
        seen["repository_id"] = repository_id
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.services.restore_check_service.restore_check_service.execute_restore_check",
        fake_execute,
        raising=True,
    )

    outcome = await maintenance.run_restore_check(ctx)

    assert outcome.status == "completed"
    assert seen["job_id"] == op.id
    assert seen["repository_id"] == repository.id
