"""Phase 5: the maintenance executors (spec 6.3, 7.4, section 13 phase 5)."""

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


@pytest.mark.xfail(
    reason="prune, compact, delete_archive, restore_check land in tasks 3 to 6"
)
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
