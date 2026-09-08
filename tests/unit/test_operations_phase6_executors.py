"""Phase 6 executors: wipe, rclone sync, package install."""

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database.models import Base, Operation, Repository
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
    repo = Repository(name="nas", path="/repo/nas", borg_version=1)
    db.add(repo)
    db.commit()
    return repo


class FakeContext:
    """The slice of OperationContext a phase 6 executor uses, matching the
    shape `tests/unit/test_operations_maintenance_executors.py` established."""

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


def _operation(db, repository, kind, category, params=None, run_id="run-1"):
    op = Operation(
        repository_id=repository.id if repository is not None else None,
        kind=kind,
        category=category,
        status="running",
        trigger="manual",
        priority=0,
        run_id=run_id,
        params=params or {},
    )
    db.add(op)
    db.commit()
    return op


@pytest.mark.asyncio
async def test_run_wipe_reports_the_status_the_service_wrote(
    db, repository, monkeypatch
):
    load_default_executors()
    op = _operation(
        db,
        repository,
        "wipe",
        "maintenance",
        params={"preview_id": 1, "run_compact": True},
    )

    async def _execute_wipe(job_id, repository_id):
        target = db.get(Operation, job_id)
        target.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.services.repository_wipe_service.repository_wipe_service.execute_wipe",
        _execute_wipe,
    )

    outcome = await get_executor("wipe")(FakeContext(db, op))

    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_run_wipe_reports_a_compaction_failure_as_completed_with_warnings(
    db, repository, monkeypatch
):
    load_default_executors()
    op = _operation(
        db, repository, "wipe", "maintenance", params={"preview_id": 1}, run_id="run-2"
    )

    async def _execute_wipe(job_id, repository_id):
        from app.services.operations.wipe_facade import WipeJobFacade

        job = WipeJobFacade(db, db.get(Operation, job_id))
        job.status = "completed_compaction_failed"
        db.commit()

    monkeypatch.setattr(
        "app.services.repository_wipe_service.repository_wipe_service.execute_wipe",
        _execute_wipe,
    )

    outcome = await get_executor("wipe")(FakeContext(db, op))

    assert outcome.status == "completed_with_warnings"


@pytest.mark.asyncio
async def test_run_wipe_enqueues_the_index_chain_after_a_partial_delete(
    db, repository, monkeypatch
):
    """A partial wipe fails the row, so the runner creates no follow-ups
    (spec 7.4), but archives did disappear: the executor enqueues the chain
    itself so the archive list and stats catch up (Appendix B)."""
    from app.services.operations.wipe_facade import WipeJobFacade

    load_default_executors()
    op = _operation(
        db,
        repository,
        "wipe",
        "maintenance",
        params={"preview_id": 1, "run_compact": True},
        run_id="run-wipe-partial",
    )

    async def _execute_wipe(job_id, repository_id):
        job = WipeJobFacade(db, db.get(Operation, job_id))
        job.status = "failed_partial"
        job.error_message = "2 of 5 archives could not be deleted"
        db.commit()

    monkeypatch.setattr(
        "app.services.repository_wipe_service.repository_wipe_service.execute_wipe",
        _execute_wipe,
    )

    outcome = await get_executor("wipe")(FakeContext(db, op))

    assert outcome.status == "failed"
    followups = (
        db.query(Operation)
        .filter(Operation.run_id == "run-wipe-partial", Operation.id != op.id)
        .order_by(Operation.id.asc())
        .all()
    )
    assert [f.kind for f in followups][0] == "archive_sync"
    assert [f.kind for f in followups][-1] == "stats"
    assert {f.trigger for f in followups} == {"followup"}
    assert followups[0].depends_on_id is None
    assert all(f.status == "queued" for f in followups)


@pytest.mark.asyncio
async def test_run_wipe_fails_when_the_service_records_no_verdict(
    db, repository, monkeypatch
):
    load_default_executors()
    op = _operation(
        db, repository, "wipe", "maintenance", params={"preview_id": 1}, run_id="run-3"
    )

    async def _execute_wipe(job_id, repository_id):
        return None

    monkeypatch.setattr(
        "app.services.repository_wipe_service.repository_wipe_service.execute_wipe",
        _execute_wipe,
    )

    outcome = await get_executor("wipe")(FakeContext(db, op))

    assert outcome.status == "failed"
    assert "no result" in (outcome.error_message or "")


@pytest.mark.asyncio
async def test_run_wipe_skips_when_the_repository_is_gone(db):
    load_default_executors()
    op = Operation(
        repository_id=None,
        kind="wipe",
        category="maintenance",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-4",
        params={},
    )
    db.add(op)
    db.commit()

    outcome = await get_executor("wipe")(FakeContext(db, op))

    assert outcome.status == "skipped"
    assert outcome.skip_reason == "repository_missing"


@pytest.mark.asyncio
async def test_run_rclone_sync_calls_the_service_with_its_own_operation_id(
    db, repository, monkeypatch
):
    from app.services.operations.details import rclone_details

    load_default_executors()
    op = _operation(db, repository, "rclone_sync", "mirror", run_id="run-5")
    op.trigger = "schedule"
    rclone_details(db, op).operation = "sync"
    db.commit()

    seen = {}

    async def _sync(
        session,
        repo,
        *,
        timeout=None,
        triggered_by="manual",
        scheduled_for=None,
        job_id=None,
    ):
        seen["job_id"] = job_id
        seen["triggered_by"] = triggered_by
        target = session.get(Operation, job_id)
        target.status = "completed"
        session.commit()
        return {}

    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_repository_service"
        ".sync_repository",
        _sync,
    )

    outcome = await get_executor("rclone_sync")(FakeContext(db, op))

    assert seen["job_id"] == op.id
    assert seen["triggered_by"] == "schedule"
    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_run_rclone_sync_dispatches_a_hydrate_to_hydrate_repository(
    db, repository, monkeypatch
):
    from app.services.operations.details import rclone_details

    load_default_executors()
    op = _operation(db, repository, "rclone_sync", "mirror", run_id="run-6")
    rclone_details(db, op).operation = "hydrate"
    db.commit()

    called = {}

    async def _hydrate(session, repo, *, timeout=None, job_id=None):
        called["job_id"] = job_id
        target = session.get(Operation, job_id)
        target.status = "completed"
        session.commit()
        return {}

    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_repository_service"
        ".hydrate_repository",
        _hydrate,
    )

    outcome = await get_executor("rclone_sync")(FakeContext(db, op))

    assert called["job_id"] == op.id
    assert outcome.status == "completed"


@pytest.mark.asyncio
async def test_run_rclone_sync_reports_a_failed_row_with_its_error_text(
    db, repository, monkeypatch
):
    from app.services.operations.details import rclone_details

    load_default_executors()
    op = _operation(db, repository, "rclone_sync", "mirror", run_id="run-7")
    rclone_details(db, op).operation = "sync"
    db.commit()

    async def _sync(session, repo, **kwargs):
        target = session.get(Operation, kwargs["job_id"])
        target.status = "failed"
        rclone_details(session, target).error_text = "remote refused"
        session.commit()
        return {}

    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_repository_service"
        ".sync_repository",
        _sync,
    )

    outcome = await get_executor("rclone_sync")(FakeContext(db, op))

    assert outcome.status == "failed"
    assert outcome.error_message == "remote refused"


@pytest.mark.asyncio
async def test_run_rclone_sync_marks_storage_failed_when_the_row_never_finishes(
    db, repository, monkeypatch
):
    """The deleted `_mark_background_rclone_sync_failed` used to keep a cloud
    repository from being stuck on "syncing" forever."""
    from app.database.models import RepositoryStorage
    from app.services.operations.details import rclone_details

    load_default_executors()
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        cache_path="/cache/nas",
        sync_status="syncing",
    )
    db.add(storage)
    op = _operation(db, repository, "rclone_sync", "mirror", run_id="run-8")
    rclone_details(db, op).operation = "sync"
    db.commit()

    async def _sync(session, repo, **kwargs):
        return {}

    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_repository_service"
        ".sync_repository",
        _sync,
    )

    outcome = await get_executor("rclone_sync")(FakeContext(db, op))

    db.refresh(storage)
    assert outcome.status == "failed"
    assert storage.sync_status == "failed"


@pytest.mark.asyncio
async def test_run_rclone_sync_marks_storage_failed_when_the_service_raises(
    db, repository, monkeypatch
):
    """An exception escaping the service reaches the runner, which fails the
    row; the storage must not be left on "syncing" on the way out."""
    from app.database.models import RepositoryStorage
    from app.services.operations.details import rclone_details

    load_default_executors()
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        cache_path="/cache/nas",
        sync_status="syncing",
    )
    db.add(storage)
    op = _operation(db, repository, "rclone_sync", "mirror", run_id="run-8b")
    rclone_details(db, op).operation = "sync"
    db.commit()

    async def _sync(session, repo, **kwargs):
        raise RuntimeError("rclone binary missing")

    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_repository_service"
        ".sync_repository",
        _sync,
    )

    with pytest.raises(RuntimeError, match="rclone binary missing"):
        await get_executor("rclone_sync")(FakeContext(db, op))

    db.refresh(storage)
    assert storage.sync_status == "failed"
    assert storage.last_sync_error == "rclone binary missing"


@pytest.mark.asyncio
async def test_run_rclone_sync_stamps_the_scheduled_run_on_the_storage(
    db, repository, monkeypatch
):
    from app.database.models import RepositoryStorage
    from app.services.operations.details import rclone_details

    load_default_executors()
    storage = RepositoryStorage(
        repository_id=repository.id,
        backend="rclone",
        cache_path="/cache/nas",
        sync_status="syncing",
    )
    db.add(storage)
    op = _operation(db, repository, "rclone_sync", "mirror", run_id="run-9")
    op.trigger = "schedule"
    rclone_details(db, op).operation = "sync"
    db.commit()

    async def _sync(session, repo, **kwargs):
        target = session.get(Operation, kwargs["job_id"])
        target.status = "completed"
        session.commit()
        return {}

    monkeypatch.setattr(
        "app.services.rclone_repository_service.rclone_repository_service"
        ".sync_repository",
        _sync,
    )

    outcome = await get_executor("rclone_sync")(FakeContext(db, op))

    db.refresh(storage)
    assert outcome.status == "completed"
    assert storage.last_scheduled_sync_at is not None


@pytest.mark.asyncio
async def test_run_package_install_reports_the_exit_code_it_recorded(
    db, monkeypatch, tmp_path
):
    from app.services.operations.package_facade import PackageInstallFacade

    load_default_executors()
    op = Operation(
        repository_id=None,
        kind="package_install",
        category="system",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-10",
        params={"package_id": 3},
    )
    db.add(op)
    db.commit()

    async def _run_install_job(job_id):
        job = PackageInstallFacade(db, db.get(Operation, job_id))
        job.status = "completed"
        job.exit_code = 0
        db.commit()

    monkeypatch.setattr(
        "app.services.package_service.package_service.run_install_job",
        _run_install_job,
    )

    outcome = await get_executor("package_install")(FakeContext(db, op))

    assert outcome.status == "completed"
    assert outcome.result == {"exit_code": 0}


@pytest.mark.asyncio
async def test_run_package_install_reports_a_failure(db, monkeypatch):
    from app.services.operations.package_facade import PackageInstallFacade

    load_default_executors()
    op = Operation(
        repository_id=None,
        kind="package_install",
        category="system",
        status="running",
        trigger="manual",
        priority=0,
        run_id="run-11",
        params={"package_id": 3},
    )
    db.add(op)
    db.commit()

    async def _run_install_job(job_id):
        job = PackageInstallFacade(db, db.get(Operation, job_id))
        job.status = "failed"
        job.exit_code = 100
        job.error_message = "Installation failed with exit code 100"
        db.commit()

    monkeypatch.setattr(
        "app.services.package_service.package_service.run_install_job",
        _run_install_job,
    )

    outcome = await get_executor("package_install")(FakeContext(db, op))

    assert outcome.status == "failed"
    assert outcome.error_message == "Installation failed with exit code 100"
    # The runner replaces `result` with the outcome's, so the exit code the
    # service recorded has to ride along or the failed job loses it.
    assert outcome.result == {"exit_code": 100}
