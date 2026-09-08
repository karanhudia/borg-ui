"""Phase 7: the restore executor is a thin shell around restore_service."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
from app.services.operations.details import restore_details
from app.services.operations.executors import get_executor, load_default_executors
from app.services.operations.restore_facade import (
    CANCELLED_BY_USER,
    RestoreJobFacade,
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


def _operation(db, repository, params=None):
    op = Operation(
        repository_id=repository.id if repository is not None else None,
        kind="restore",
        category="restore",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-1",
        params=params
        or {
            "archive_name": "nas-2026-09-08",
            "paths": ["docs/"],
            "restore_layout": "contents_only",
            "path_metadata": [{"path": "docs/", "type": "directory"}],
        },
    )
    db.add(op)
    db.flush()
    details = restore_details(db, op)
    details.archive = "nas-2026-09-08"
    details.destination = "/restore/target"
    details.destination_type = "local"
    details.repository_type = "local"
    db.commit()
    return op


@pytest.mark.asyncio
async def test_run_restore_passes_the_details_and_params_to_the_service(
    db, repository, monkeypatch
):
    load_default_executors()
    op = _operation(db, repository)
    seen = {}

    async def _execute_restore(
        job_id, repository_path, archive, destination, paths, **kw
    ):
        seen.update(
            job_id=job_id,
            repository_path=repository_path,
            archive=archive,
            destination=destination,
            paths=paths,
            **kw,
        )
        job = RestoreJobFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        job.nfiles = 4
        job.restored_size = 2048
        db.commit()

    monkeypatch.setattr(
        "app.services.restore_service.restore_service.execute_restore",
        _execute_restore,
    )

    outcome = await get_executor("restore")(FakeContext(db, op))

    assert outcome.status == "completed"
    assert outcome.result == {"nfiles": 4, "restored_size": 2048}
    assert seen == {
        "job_id": op.id,
        "repository_path": "/repo/nas",
        "archive": "nas-2026-09-08",
        "destination": "/restore/target",
        "paths": ["docs/"],
        "repository_type": "local",
        "destination_type": "local",
        "destination_connection_id": None,
        "ssh_connection_id": None,
        "restore_layout": "contents_only",
        "path_metadata": [{"path": "docs/", "type": "directory"}],
    }


@pytest.mark.asyncio
async def test_run_restore_skips_when_the_repository_is_gone(db, repository):
    load_default_executors()
    op = _operation(db, repository)
    op.repository_id = None
    db.commit()

    outcome = await get_executor("restore")(FakeContext(db, op))

    assert outcome.status == "skipped"
    assert outcome.skip_reason == "repository_missing"


@pytest.mark.asyncio
async def test_run_restore_reports_a_failure_the_service_wrote(
    db, repository, monkeypatch
):
    load_default_executors()
    op = _operation(db, repository)

    async def _execute_restore(job_id, *args, **kw):
        job = RestoreJobFacade(db, db.get(Operation, job_id))
        job.status = "failed"
        job.error_message = '{"key": "backend.errors.service.restoreFailed"}'
        db.commit()

    monkeypatch.setattr(
        "app.services.restore_service.restore_service.execute_restore",
        _execute_restore,
    )

    outcome = await get_executor("restore")(FakeContext(db, op))

    assert outcome.status == "failed"
    assert outcome.error_message == '{"key": "backend.errors.service.restoreFailed"}'


@pytest.mark.asyncio
async def test_run_restore_fails_when_the_service_returns_without_a_verdict(
    db, repository, monkeypatch
):
    load_default_executors()
    op = _operation(db, repository)

    async def _execute_restore(*args, **kw):
        return None

    monkeypatch.setattr(
        "app.services.restore_service.restore_service.execute_restore",
        _execute_restore,
    )

    outcome = await get_executor("restore")(FakeContext(db, op))

    assert outcome.status == "failed"
    assert outcome.error_message == "restore returned no result"


@pytest.mark.asyncio
async def test_run_restore_keeps_cancelled_over_the_killed_process_failure(
    db, repository, monkeypatch
):
    """The cancel route raises the runner's flag, kills the process, and
    writes `cancelled`; the service's read loop then sees the non-zero exit
    and writes `failed`. Whichever lands last, the executor answers for the
    flag (spec 7.7)."""
    load_default_executors()
    op = _operation(db, repository)
    ctx = FakeContext(db, op)

    async def _execute_restore(job_id, *args, **kw):
        ctx._cancelled = True
        job = RestoreJobFacade(db, db.get(Operation, job_id))
        job.status = "failed"
        job.error_message = '{"key": "backend.errors.service.restoreFailedExitCode"}'
        db.commit()

    monkeypatch.setattr(
        "app.services.restore_service.restore_service.execute_restore",
        _execute_restore,
    )

    outcome = await get_executor("restore")(ctx)

    assert db.get(Operation, op.id).status == "cancelled"
    assert outcome.status == "failed"
    assert outcome.error_message == CANCELLED_BY_USER


@pytest.mark.asyncio
async def test_run_restore_keeps_the_cancel_message_the_route_wrote(
    db, repository, monkeypatch
):
    from app.services.operations.restore_facade import CANCELLED_PROCESS_NOT_FOUND

    load_default_executors()
    op = _operation(db, repository)
    ctx = FakeContext(db, op)

    async def _execute_restore(job_id, *args, **kw):
        ctx._cancelled = True
        job = RestoreJobFacade(db, db.get(Operation, job_id))
        job.status = "cancelled"
        job.error_message = CANCELLED_PROCESS_NOT_FOUND
        db.commit()

    monkeypatch.setattr(
        "app.services.restore_service.restore_service.execute_restore",
        _execute_restore,
    )

    outcome = await get_executor("restore")(ctx)

    assert outcome.error_message == CANCELLED_PROCESS_NOT_FOUND
