"""Phase 5: the maintenance executors (spec 6.3, 7.4, section 13 phase 5)."""

import asyncio
from datetime import datetime

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
@pytest.mark.parametrize(
    "kind, router_method, v1_module, v2_module, v2_singleton",
    [
        ("prune", "prune", "prune_service", "v2.prune_service", "prune_v2_service"),
        (
            "compact",
            "compact",
            "compact_service",
            "v2.compact_service",
            "compact_v2_service",
        ),
    ],
)
async def test_borg2_cancellation_terminates_the_borg2_services_process(
    db, monkeypatch, kind, router_method, v1_module, v2_module, v2_singleton
):
    """On a Borg 2 server repository the router runs the Borg 2 service,
    which tracks its own process; the Borg 1 singleton the executor used to
    hand the watcher knows nothing about it, so a cancel returned False for
    the whole run and the row never read `cancelled` for the service to
    poll. The watcher now calls the Borg 2 service's canceller there."""
    import importlib
    from unittest.mock import AsyncMock, MagicMock

    from app.services.operations.executors import maintenance

    v1 = getattr(importlib.import_module(f"app.services.{v1_module}"), v1_module)
    v2 = getattr(importlib.import_module(f"app.services.{v2_module}"), v2_singleton)
    repo = Repository(name=f"nas2-{kind}", path=f"/repo/nas2-{kind}", borg_version=2)
    db.add(repo)
    db.commit()
    op = _operation(db, repo, kind=kind)
    ctx = FakeContext(db, op)
    ctx._cancelled = True

    fake_process = MagicMock()
    fake_process.pid = 4243
    fake_process.wait = AsyncMock(return_value=None)
    v2.running_processes[op.id] = fake_process
    v1_cancel = AsyncMock(return_value=False)
    monkeypatch.setattr(v1, f"cancel_{kind}", v1_cancel)

    async def call(self, job_id, *args, **kwargs):
        await asyncio.sleep(0.05)
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "cancelled"
        db.commit()

    monkeypatch.setattr(
        f"app.core.borg_router.BorgRouter.{router_method}", call, raising=True
    )
    try:
        await getattr(maintenance, f"run_{kind}")(ctx)
        fake_process.terminate.assert_called_once()
        v1_cancel.assert_not_awaited()
    finally:
        v2.running_processes.pop(op.id, None)


@pytest.mark.asyncio
async def test_a_killed_borg2_process_ends_the_row_cancelled_not_failed(
    db, monkeypatch
):
    """The Borg 2 services record a killed process as `failed` with the
    signal's exit as the error: they poll the row for `cancelled`, which the
    runner's flag never writes. Once the service has returned the process is
    dead, so the executor turns that failure into the user's cancel, and the
    runner keeps `cancelled` because the row already says so."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.operations.executors import maintenance
    from app.services.v2.prune_service import prune_v2_service

    repo = Repository(name="nas2-killed", path="/repo/nas2-killed", borg_version=2)
    db.add(repo)
    db.commit()
    op = _operation(db, repo, kind="prune")
    ctx = FakeContext(db, op)
    ctx._cancelled = True
    fake_process = MagicMock()
    fake_process.pid = 4245
    fake_process.wait = AsyncMock(return_value=None)
    prune_v2_service.running_processes[op.id] = fake_process

    async def call(self, job_id, *args, **kwargs):
        await asyncio.sleep(0.05)
        # what the service writes after SIGTERM: not cancelled, failed
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "failed"
        job.error_message = "Terminated"
        db.commit()

    monkeypatch.setattr("app.core.borg_router.BorgRouter.prune", call, raising=True)
    try:
        outcome = await maintenance.run_prune(ctx)
    finally:
        prune_v2_service.running_processes.pop(op.id, None)
    fake_process.terminate.assert_called_once()
    assert outcome.status == "failed" and outcome.error_message == "cancelled"
    db.expire_all()
    assert db.get(Operation, op.id).status == "cancelled"


@pytest.mark.asyncio
async def test_a_failure_without_a_cancel_stays_a_failure(db, repository, monkeypatch):
    """The mapping is for the cancel case only."""
    from app.services.operations.executors import maintenance

    op = _operation(db, repository, kind="prune")
    ctx = FakeContext(db, op)
    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.prune", _completing(db, "failed", "boom")
    )
    outcome = await maintenance.run_prune(ctx)
    assert outcome.status == "failed" and outcome.error_message == "boom"
    db.expire_all()
    assert db.get(Operation, op.id).status == "failed"


@pytest.mark.asyncio
async def test_borg1_cancellation_keeps_the_borg1_canceller(
    db, repository, monkeypatch
):
    """The Borg 1 route is unchanged: its own singleton tracks the process,
    and the Borg 2 service is not consulted."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.operations.executors import maintenance
    from app.services.prune_service import prune_service
    from app.services.v2.prune_service import prune_v2_service

    op = _operation(db, repository, kind="prune")
    ctx = FakeContext(db, op)
    ctx._cancelled = True
    fake_process = MagicMock()
    fake_process.pid = 4244
    fake_process.wait = AsyncMock(return_value=None)
    prune_service.running_processes[op.id] = fake_process
    v2_cancel = AsyncMock(return_value=True)
    monkeypatch.setattr(prune_v2_service, "cancel_prune", v2_cancel)

    async def call(self, job_id, *args, **kwargs):
        await asyncio.sleep(0.05)
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "cancelled"
        db.commit()

    monkeypatch.setattr("app.core.borg_router.BorgRouter.prune", call, raising=True)
    try:
        await maintenance.run_prune(ctx)
        fake_process.terminate.assert_called_once()
        v2_cancel.assert_not_awaited()
    finally:
        prune_service.running_processes.pop(op.id, None)


@pytest.mark.asyncio
async def test_cancel_watcher_retries_until_the_process_is_registered(
    db, repository, monkeypatch
):
    """A cancel request can land before the service has registered its
    process (still resolving the repository, listing archives, etc.).
    `cancel_watcher` used to call the canceller exactly once and give up for
    good on a `False` result, so a cancel that arrived during that setup
    window was silently dropped and the Borg process ran to completion
    untouched. It must keep retrying each poll interval until something
    actually terminates."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.check_service import check_service
    from app.services.operations.executors import maintenance

    monkeypatch.setattr(maintenance, "_CANCEL_POLL_SECONDS", 0.02)

    op = _operation(db, repository)
    ctx = FakeContext(db, op)
    ctx._cancelled = True

    fake_process = MagicMock()
    fake_process.pid = 4242
    fake_process.wait = AsyncMock(return_value=None)
    # Not registered yet: the first cancel_watcher attempt must see no
    # tracked process and retry instead of giving up.

    async def call(self, job_id, *args, **kwargs):
        # Simulate setup time (resolving the repository) before the process
        # is actually tracked, well past the first poll interval.
        await asyncio.sleep(0.06)
        check_service.running_processes[job_id] = fake_process
        await asyncio.sleep(0.06)
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


_RUNNER_CLAIMED_AT = datetime(2026, 1, 1, 12, 0, 0)


def _runner_claimed(db, repository, kind="compact", params=None):
    """A row the way `runner.tick` leaves it: queued, then claimed."""
    op = _operation(db, repository, kind=kind, params=params)
    op.status = "queued"
    db.commit()
    claimed = (
        db.query(Operation)
        .filter(Operation.id == op.id, Operation.status == "queued")
        .update(
            # a fixed past instant: the service's own stamp must differ from it
            # on any clock resolution
            {"status": "running", "started_at": _RUNNER_CLAIMED_AT},
            synchronize_session=False,
        )
    )
    assert claimed == 1
    db.commit()
    db.refresh(op)
    assert op.started_at is not None
    return op


def _other_session(db):
    """A second identity map on the test engine (the in-memory SQLite engine
    shares one connection, so this is what `claim_running` in the service's
    own session sees, not a second transaction)."""
    return sessionmaker(bind=db.get_bind())()


@pytest.fixture()
def borg2_repository(db):
    repo = Repository(name="nas2", path="/repo/nas2", borg_version=2)
    db.add(repo)
    db.commit()
    return repo


# kind -> (executor, router method, params)
_CLAIMING = {
    "check": ("run_check", "check", None),
    "prune": ("run_prune", "prune", None),
    "compact": ("run_compact", "compact", None),
    "delete_archive": ("run_delete_archive", "delete_archive", {"archive_name": "a1"}),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", sorted(_CLAIMING))
async def test_run_hands_the_runner_claimed_row_to_a_claiming_service(
    db, borg2_repository, monkeypatch, kind
):
    """The runner claims a row as `running` with a `started_at`; the Borg 2
    server services claim it again through `claim_running`, which takes a
    `running` row only without a start. The executor hands the row over in
    that shape before the call, so the service's claim succeeds and the
    stored start is the service's, not the runner's (#1005)."""
    from app.services.operations.executors import maintenance
    from app.services.operations.job_facade import claim_running

    executor_name, router_method, params = _CLAIMING[kind]
    op = _runner_claimed(db, borg2_repository, kind=kind, params=params)
    runner_started_at = op.started_at
    seen = {}

    async def fake_service(self, job_id, *args, **kwargs):
        other = _other_session(db)
        try:
            seen["started_at"] = datetime.utcnow()
            seen["claimed"] = claim_running(other, job_id, kind, seen["started_at"])
            other.commit()
            job = MaintenanceJobFacade(other, other.get(Operation, job_id))
            job.status = "completed"
            other.commit()
        finally:
            other.close()

    monkeypatch.setattr(
        f"app.core.borg_router.BorgRouter.{router_method}", fake_service, raising=True
    )

    outcome = await getattr(maintenance, executor_name)(FakeContext(db, op))

    assert outcome.status == "completed"
    assert seen["claimed"] == 1
    db.expire_all()
    stored = db.get(Operation, op.id).started_at
    assert stored == seen["started_at"]
    assert stored != runner_started_at


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "borg_version, executor_type",
    [(1, "server"), (2, "agent")],
    ids=["borg1-server", "borg2-agent"],
)
async def test_run_keeps_the_runner_start_where_no_service_claims(
    db, monkeypatch, borg_version, executor_type
):
    """A Borg 1 service writes its own start over the runner's and the agent
    path stamps it from the agent's report; neither claims through
    `claim_running`, so the runner's start is left in place (an agent that
    never reports would otherwise end the run with no start at all)."""
    from app.services.operations.executors import maintenance

    repo = Repository(
        name=f"r-{borg_version}-{executor_type}",
        path=f"/repo/{executor_type}",
        borg_version=borg_version,
        executor_type=executor_type,
    )
    db.add(repo)
    db.commit()
    op = _runner_claimed(db, repo)
    runner_started_at = op.started_at

    async def fake_compact(self, job_id):
        other = _other_session(db)
        try:
            assert other.get(Operation, job_id).started_at == runner_started_at
            job = MaintenanceJobFacade(other, other.get(Operation, job_id))
            job.status = "completed"
            other.commit()
        finally:
            other.close()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    outcome = await maintenance.run_compact(FakeContext(db, op))

    assert outcome.status == "completed"
    db.expire_all()
    assert db.get(Operation, op.id).started_at == runner_started_at


@pytest.mark.asyncio
async def test_run_leaves_a_row_a_cancel_made_terminal_alone(tmp_path, monkeypatch):
    """A cancel that landed between the runner's claim and the hand-over
    (committed by a request's session on its own connection, after the
    runner's session loaded the row) made the row terminal; the guarded
    UPDATE reads the table, not the runner session's copy, so its start
    stays for the history. A file-backed database, so the two sessions
    really are two connections."""
    from app.services.operations.executors import maintenance

    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    runner_db = factory()
    repo = Repository(name="nas2", path="/repo/nas2", borg_version=2)
    runner_db.add(repo)
    runner_db.commit()
    op = _runner_claimed(runner_db, repo)
    started_at = op.started_at
    ctx = FakeContext(runner_db, op)  # holds the row as `running`

    request_db = factory()
    request_db.query(Operation).filter(Operation.id == op.id).update(
        {"status": "cancelled"}, synchronize_session=False
    )
    request_db.commit()
    request_db.close()

    async def fake_compact(self, job_id):
        return None

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    try:
        await maintenance.run_compact(ctx)
        runner_db.expire_all()
        row = runner_db.get(Operation, op.id)
        assert row.status == "cancelled"
        assert row.started_at == started_at
    finally:
        runner_db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_run_restores_the_runner_start_when_the_service_never_claimed(
    db, borg2_repository, monkeypatch
):
    """A service that ends the run before it claims (a missing repository, a
    lock it gave up on) writes a terminal status with no start; the runner's
    start is put back so the run keeps its place in the history."""
    from app.services.operations.executors import maintenance

    op = _runner_claimed(db, borg2_repository)
    runner_started_at = op.started_at

    async def fake_compact(self, job_id):
        other = _other_session(db)
        try:
            assert other.get(Operation, job_id).started_at is None
            job = MaintenanceJobFacade(other, other.get(Operation, job_id))
            job.status = "failed"
            job.error_message = "Repository not found"
            other.commit()
        finally:
            other.close()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    outcome = await maintenance.run_compact(FakeContext(db, op))

    assert outcome.status == "failed"
    db.expire_all()
    assert db.get(Operation, op.id).started_at == runner_started_at


@pytest.mark.asyncio
async def test_run_restores_the_runner_start_when_the_service_raises(
    db, borg2_repository, monkeypatch
):
    """A service that raises out of the call (a cancel arriving while it
    retries a lock, before it claimed) leaves the row with no start; the
    restore runs in the executor's `finally`, so the runner's verdict that
    follows lands on a row that still has one."""
    from app.services.operations.executors import maintenance

    op = _runner_claimed(db, borg2_repository)
    runner_started_at = op.started_at

    async def fake_compact(self, job_id):
        other = _other_session(db)
        try:
            assert other.get(Operation, job_id).started_at is None
        finally:
            other.close()
        raise RuntimeError("database is locked")

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    with pytest.raises(RuntimeError):
        await maintenance.run_compact(FakeContext(db, op))

    db.expire_all()
    row = db.get(Operation, op.id)
    assert row.status == "running"  # the runner writes the verdict
    assert row.started_at == runner_started_at


@pytest.mark.asyncio
async def test_run_restores_the_runner_start_when_the_service_gave_no_verdict(
    db, borg2_repository, monkeypatch
):
    """A service that returns with the row still `running` (its own failure
    write lost to a lock) never claimed it; the start comes back before the
    executor reports the missing verdict."""
    from app.services.operations.executors import maintenance

    op = _runner_claimed(db, borg2_repository)
    runner_started_at = op.started_at

    async def fake_compact(self, job_id):
        return None

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    outcome = await maintenance.run_compact(FakeContext(db, op))

    assert outcome.status == "failed"
    assert outcome.error_message == "service returned no result"
    db.expire_all()
    assert db.get(Operation, op.id).started_at == runner_started_at


@pytest.mark.asyncio
async def test_run_does_not_clear_a_start_another_claim_wrote(tmp_path, monkeypatch):
    """Between this dispatch loading the row and the hand-over, another
    session rewrote the start (a service claiming the row through its own
    path); the guarded UPDATE matches only the start this dispatch's claim
    wrote, so that start stays. Two connections on a file-backed database."""
    from app.services.operations.executors import maintenance

    engine = create_engine(f"sqlite:///{tmp_path / 'ops.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    runner_db = factory()
    repo = Repository(name="nas2", path="/repo/nas2", borg_version=2)
    runner_db.add(repo)
    runner_db.commit()
    op = _runner_claimed(runner_db, repo)
    ctx = FakeContext(runner_db, op)  # holds the runner's start

    other_start = datetime(2026, 1, 2, 8, 30, 0)
    other = factory()
    other.query(Operation).filter(Operation.id == op.id).update(
        {"started_at": other_start}, synchronize_session=False
    )
    other.commit()
    other.close()

    async def fake_compact(self, job_id):
        service = factory()
        try:
            assert service.get(Operation, job_id).started_at == other_start
            job = MaintenanceJobFacade(service, service.get(Operation, job_id))
            job.status = "completed"
            service.commit()
        finally:
            service.close()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    try:
        outcome = await maintenance.run_compact(ctx)
        assert outcome.status == "completed"
        runner_db.expire_all()
        assert runner_db.get(Operation, op.id).started_at == other_start
    finally:
        runner_db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_run_does_not_touch_a_row_dispatched_without_a_start(
    db, borg2_repository, monkeypatch
):
    """A row dispatched without a runner start (the inline shape) is not
    the executor's to touch; the start the service writes stays."""
    from app.services.operations.executors import maintenance
    from app.services.operations.job_facade import claim_running

    op = _operation(db, borg2_repository, kind="compact")  # running, no start
    assert op.started_at is None
    seen = {}

    async def fake_compact(self, job_id):
        other = _other_session(db)
        try:
            seen["started_at"] = datetime.utcnow()
            assert claim_running(other, job_id, "compact", seen["started_at"]) == 1
            other.commit()
            job = MaintenanceJobFacade(other, other.get(Operation, job_id))
            job.status = "completed"
            other.commit()
        finally:
            other.close()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    outcome = await maintenance.run_compact(FakeContext(db, op))

    assert outcome.status == "completed"
    db.expire_all()
    assert db.get(Operation, op.id).started_at == seen["started_at"]


@pytest.mark.asyncio
async def test_hand_over_commit_failure_propagates_before_the_service_runs(
    db, borg2_repository, monkeypatch
):
    """A hand-over whose commit exhausts its retries raises out of `_run`
    before the service is called; the row keeps the runner's start."""
    from sqlalchemy.exc import OperationalError

    from app.services.operations.executors import maintenance

    op = _runner_claimed(db, borg2_repository)
    started_at = op.started_at
    called = []

    async def failing_commit(session, **kwargs):
        session.rollback()
        raise OperationalError("UPDATE operations", {}, Exception("database is locked"))

    monkeypatch.setattr(maintenance, "commit_with_retry", failing_commit)

    async def fake_compact(self, job_id):
        called.append(job_id)

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    with pytest.raises(OperationalError):
        await maintenance.run_compact(FakeContext(db, op))

    assert called == []
    db.expire_all()
    assert db.get(Operation, op.id).started_at == started_at


@pytest.mark.asyncio
async def test_restore_failure_does_not_replace_the_services_error(
    db, borg2_repository, monkeypatch
):
    """The restore runs in the executor's `finally`; when its own commit
    fails, the service's failure is what reaches the runner."""
    from sqlalchemy.exc import OperationalError

    from app.services.operations.executors import maintenance

    op = _runner_claimed(db, borg2_repository)
    real = maintenance.commit_with_retry

    async def commit(session, **kwargs):
        if kwargs.get("action") == "maintenance_restore_start":
            session.rollback()
            raise OperationalError("UPDATE operations", {}, Exception("locked"))
        return await real(session, **kwargs)

    monkeypatch.setattr(maintenance, "commit_with_retry", commit)

    async def fake_compact(self, job_id):
        raise RuntimeError("borg2 compact failed")

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    with pytest.raises(RuntimeError, match="borg2 compact failed"):
        await maintenance.run_compact(FakeContext(db, op))


@pytest.mark.parametrize(
    "kind, borg_version, executor_type, handed_over",
    [
        ("check", 2, "server", True),
        ("prune", 2, "server", True),
        ("compact", 2, "server", True),
        ("delete_archive", 2, "server", True),
        ("restore_check", 2, "server", False),
        ("compact", 1, "server", False),
        ("compact", 2, "agent", False),
    ],
)
def test_hands_over_only_to_a_claiming_borg2_server_service(
    db, kind, borg_version, executor_type, handed_over
):
    """The hand-over is for the four kinds whose Borg 2 server service claims
    through `claim_running`; restore_check runs its own service without a
    claim, Borg 1 services and the agent path write or report their own
    start."""
    from app.services.operations.executors import maintenance

    repo = Repository(
        name=f"{kind}-{borg_version}-{executor_type}",
        path=f"/repo/{kind}",
        borg_version=borg_version,
        executor_type=executor_type,
    )
    db.add(repo)
    db.commit()
    op = _operation(db, repo, kind=kind, params={"archive_name": "a"})
    assert maintenance._hands_over(FakeContext(db, op), repo) is handed_over


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
async def test_compact_returns_the_statistics_the_service_filed(
    db, repository, monkeypatch
):
    """The runner writes the row's result from the outcome, so the `--stats`
    output the service filed under `result["stats"]` has to come back
    through it, or the runner's own write would drop it."""
    from app.services.operations.executors import maintenance

    op = _operation(db, repository, kind="compact")
    ctx = FakeContext(db, op)
    stats = {"repository_size": 502_000, "size_precision": "exact"}

    async def fake_compact(self, job_id):
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.stats = stats
        job.status = "completed"
        db.commit()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    outcome = await maintenance.run_compact(ctx)

    assert outcome.status == "completed"
    assert outcome.result == {"logs": False, "stats": stats}


@pytest.mark.asyncio
async def test_compact_reads_statistics_another_session_committed(
    db, repository, monkeypatch
):
    """An agent compact is finished from the completion request's session,
    not the runner's, whose identity map already holds the row: the
    executor must read the row back after the service returns (the
    in-memory SQLite engine shares one connection, so this exercises the
    stale-copy half, not transaction isolation), or the statistics filed
    there are missing from the outcome and the runner's result write drops
    them."""
    from app.services.operations.executors import maintenance

    op = _operation(db, repository, kind="compact")
    ctx = FakeContext(db, op)
    stats = {"repository_size": 502_000, "size_precision": "exact"}

    async def fake_compact(self, job_id):
        # the runner's session already holds the row (FakeContext loaded it)
        other = sessionmaker(bind=db.get_bind())()
        try:
            job = MaintenanceJobFacade(other, other.get(Operation, job_id))
            job.stats = stats
            job.status = "completed"
            other.commit()
        finally:
            other.close()

    monkeypatch.setattr(
        "app.core.borg_router.BorgRouter.compact", fake_compact, raising=True
    )

    outcome = await maintenance.run_compact(ctx)

    assert outcome.status == "completed"
    assert outcome.result == {"logs": False, "stats": stats}


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


@pytest.mark.asyncio
async def test_restore_check_cancellation_terminates_the_tracked_borg_process(
    db, repository, monkeypatch
):
    """`run_restore_check` previously passed no canceller at all, the same
    gap `run_check` had before it gained `cancel_check`; `execute_restore_check`
    already tracks `running_processes[job_id]` the same way, so this is the
    same fix applied to the same pattern."""
    from unittest.mock import AsyncMock, MagicMock

    from app.services.operations.executors import maintenance
    from app.services.restore_check_service import restore_check_service

    op = _operation(db, repository, kind="restore_check")
    op.category = "restore"
    db.commit()
    ctx = FakeContext(db, op)
    ctx._cancelled = True

    fake_process = MagicMock()
    fake_process.pid = 4242
    fake_process.wait = AsyncMock(return_value=None)
    restore_check_service.running_processes[op.id] = fake_process

    async def fake_execute(job_id, repository_id):
        await asyncio.sleep(0.05)
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "cancelled"
        db.commit()

    monkeypatch.setattr(
        "app.services.restore_check_service.restore_check_service.execute_restore_check",
        fake_execute,
        raising=True,
    )

    try:
        await maintenance.run_restore_check(ctx)
        fake_process.terminate.assert_called_once()
    finally:
        restore_check_service.running_processes.pop(op.id, None)


@pytest.mark.asyncio
async def test_restore_check_needs_backup_is_a_skip_with_that_reason(
    db, repository, monkeypatch
):
    from app.services.operations.executors import maintenance
    from app.services.restore_check_service import restore_check_service

    op = _operation(db, repository, kind="restore_check", category="restore")
    ctx = FakeContext(db, op)

    async def needs_backup(job_id, repository_id):
        job = MaintenanceJobFacade(db, db.get(Operation, job_id))
        job.status = "needs_backup"
        job.error_message = "Run a backup, then run this restore check again"
        db.commit()

    monkeypatch.setattr(restore_check_service, "execute_restore_check", needs_backup)

    outcome = await maintenance.run_restore_check(ctx)

    assert outcome.status == "skipped"
    assert outcome.skip_reason == "needs_backup"
    assert outcome.error_message == "Run a backup, then run this restore check again"
    db.refresh(op)
    assert (op.status, op.skip_reason) == ("skipped", "needs_backup")
    assert MaintenanceJobFacade(db, op).status == "needs_backup"
