"""The job starters and the operations controls off the event loop.

On the loop a handler ran from its check to its insert with nothing in
between. In a worker thread the requests around it keep running, so a start
that first looks for active work decides under a lock, and gives the lock back
when it refuses.

The plan run, its retry and run-now stay coroutines: their database work runs
in a thread and the task they start is created on the loop. What the thread
committed is launched also when the request is cancelled meanwhile, and the
startup sweep leaves a run alone that is committed and not launched yet.

The races are laid out with real requests on a session each: a `Gate` stops
one request between its check and its insert while the other one runs. The
rows decide, not how long anything takes. They run on SQLite and, with
BORG_TEST_POSTGRES_URL set, on PostgreSQL.
"""

import asyncio
import inspect
import json
import threading
import time
from importlib import import_module
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import contextmanager
from datetime import datetime, timedelta

from unittest.mock import patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

import app.api.operations as operations_api
import app.api.schedule as schedule_api
import app.services.operations.maintenance_start as maintenance_start
import app.services.operations.reconcile as reconcile
from app.core.security import create_access_token
from app.database.database import get_db
from app.database.models import (
    BackupPlan,
    BackupPlanRepository,
    BackupPlanRun,
    BackupPlanRunRepository,
    LicensingState,
    Operation,
    Repository,
    ScheduledJob,
    ScheduledJobRepository,
    ScriptExecution,
    SystemSettings,
    User,
)
from app.services.backup_plan_execution_service import (
    BackupPlanExecutionService,
    backup_plan_execution_service,
)
from app.services.job_admission import lock_backup_plan_scope, lock_repository_scope
from app.utils.process_utils import (
    POST_BACKUP_HOOKS_AFTER_CANCEL,
    cleanup_orphaned_jobs,
)
from tests.unit.test_agent_endpoints_off_event_loop import (
    HOLD_SECONDS,
    POSTGRES_URL,
    Gate,
    _on_the_loop,
    _postgres_sessions,
    _while_held,
)

ADMIN = "starter-admin"
# How long the second request gets to finish while the first one is held. With
# the lock it cannot, and the test goes on after this; without it, it has.
SETTLE_SECONDS = 0.5
ARCHIVE = "nightly-1"


def _headers() -> dict:
    token = create_access_token(data={"sub": ADMIN})
    return {"X-Borg-Authorization": f"Bearer {token}"}


@pytest.fixture(
    params=[
        "sqlite",
        pytest.param(
            "postgresql",
            marks=pytest.mark.skipif(
                not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set"
            ),
        ),
    ]
)
def database(request, test_client, session_per_request):
    """The session factory of the database the requests of this test use: for
    the test's setup and assertions, one session per request for the app."""
    if request.param == "sqlite":
        yield session_per_request
        return

    from app.main import app

    with _postgres_sessions() as sessions:

        def override_get_db():
            db = sessions()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        with patch("app.database.database.SessionLocal", sessions):
            yield sessions


@pytest.fixture
def admin(database):
    """An administrator in the database of the test, with the settings row."""
    with database() as db:
        db.add(
            User(username=ADMIN, password_hash="unused", is_active=True, role="admin")
        )
        if db.query(SystemSettings).first() is None:
            db.add(SystemSettings())
        db.commit()
    return _headers()


@pytest.fixture
def plan_runs_do_nothing(monkeypatch):
    """Runs of the shared service are launched and end at once. Returns the
    ids of the launched runs."""
    launched: list[int] = []

    async def execute_run(run_id: int) -> None:
        launched.append(run_id)

    monkeypatch.setattr(backup_plan_execution_service, "execute_run", execute_run)
    yield launched
    backup_plan_execution_service.live_run_ids.clear()


def _seed_repository(sessions, name: str = "starters", **columns) -> int:
    with sessions() as db:
        repository = Repository(
            name=name,
            path=f"/repos/{name}",
            encryption="none",
            repository_type="local",
            mode="full",
            **columns,
        )
        db.add(repository)
        db.commit()
        return repository.id


def _seed_plan(sessions, repository_id: int, **columns) -> int:
    with sessions() as db:
        plan = BackupPlan(
            **{
                "name": "starters plan",
                "enabled": True,
                "source_directories": json.dumps(["/srv/project"]),
                "created_at": datetime.utcnow(),
                **columns,
            }
        )
        db.add(plan)
        db.flush()
        db.add(
            BackupPlanRepository(
                backup_plan_id=plan.id,
                repository_id=repository_id,
                enabled=True,
                execution_order=1,
                created_at=datetime.utcnow(),
            )
        )
        db.commit()
        return plan.id


def _seed_run(sessions, plan_id: int, repository_id: int, status: str) -> int:
    with sessions() as db:
        run = BackupPlanRun(
            backup_plan_id=plan_id,
            trigger="manual",
            status=status,
            created_at=datetime.utcnow(),
        )
        db.add(run)
        db.flush()
        db.add(
            BackupPlanRunRepository(
                backup_plan_run_id=run.id, repository_id=repository_id, status=status
            )
        )
        db.commit()
        return run.id


def _seed_run_with_post_hooks_to_run(
    sessions, plan_id: int, repository_id: int, status: str
) -> int:
    """A run a restart found after its pre-backup scripts ran and before its
    post-backup scripts did."""
    run_id = _seed_run(sessions, plan_id, repository_id, status)
    with sessions() as db:
        if status == "cancelled":
            db.get(BackupPlanRun, run_id).error_message = POST_BACKUP_HOOKS_AFTER_CANCEL
        db.add(
            ScriptExecution(
                backup_plan_id=plan_id,
                backup_plan_run_id=run_id,
                hook_type="pre-backup",
                status="completed",
                started_at=datetime.utcnow(),
                triggered_by="backup_plan",
            )
        )
        db.commit()
    return run_id


def _seed_schedule(sessions, repository_id: int, *, linked: bool) -> int:
    """A schedule of one repository, or with `linked` of a list of them."""
    with sessions() as db:
        job = ScheduledJob(
            name="starters schedule",
            cron_expression="0 2 * * *",
            enabled=True,
            repository_id=None if linked else repository_id,
        )
        db.add(job)
        db.flush()
        if linked:
            db.add(
                ScheduledJobRepository(
                    scheduled_job_id=job.id,
                    repository_id=repository_id,
                    execution_order=0,
                )
            )
        db.commit()
        return job.id


def _seed_operation(sessions, repository_id: int, kind: str, **columns) -> int:
    with sessions() as db:
        operation = Operation(
            repository_id=repository_id,
            kind=kind,
            category="index" if kind in ("archive_sync", "stats") else "maintenance",
            status="queued",
            trigger="manual",
            priority=10,
            run_id=f"seeded-{kind}",
            **columns,
        )
        db.add(operation)
        db.commit()
        return operation.id


def _operations(sessions, kind: str) -> list[Operation]:
    with sessions() as db:
        return db.query(Operation).filter(Operation.kind == kind).all()


def _runs(sessions, plan_id: int) -> list[tuple[str, str]]:
    with sessions() as db:
        return [
            (run.trigger, run.status)
            for run in db.query(BackupPlanRun)
            .filter(BackupPlanRun.backup_plan_id == plan_id)
            .order_by(BackupPlanRun.id)
        ]


def _hold_before(monkeypatch, owner, name: str, gate: Gate) -> None:
    original = getattr(owner, name)

    def held(*args, **kwargs):
        gate.hold()
        return original(*args, **kwargs)

    monkeypatch.setattr(owner, name, held)


def _hold_after(monkeypatch, owner, name: str, gate: Gate) -> None:
    original = getattr(owner, name)

    def held(*args, **kwargs):
        result = original(*args, **kwargs)
        gate.hold()
        return result

    monkeypatch.setattr(owner, name, held)


@contextmanager
def _held_after_its_commit(sessions, gate: Gate, model):
    """Stop the first session that commits a row of `model`, right after the
    commit."""

    def after_flush(session, _context) -> None:
        if any(isinstance(row, model) for row in (*session.new, *session.dirty)):
            session.info["commits_the_row"] = True

    def after_commit(session) -> None:
        if session.info.pop("commits_the_row", False):
            gate.hold()

    event.listen(sessions, "after_flush", after_flush)
    event.listen(sessions, "after_commit", after_commit)
    try:
        yield
    finally:
        event.remove(sessions, "after_flush", after_flush)
        event.remove(sessions, "after_commit", after_commit)


def _beside_the_held(gate: Gate, first, second):
    """Run `first`, which the gate stops between its check and its insert,
    and `second` beside it. `second` gets the time to finish while `first`
    is held. Returns both results."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        held = pool.submit(first)
        assert gate.reached.wait(HOLD_SECONDS), "the request never reached the gate"
        other = pool.submit(second)
        try:
            other.result(SETTLE_SECONDS)
        except FutureTimeout:
            pass
        gate.open()
        results = held.result(HOLD_SECONDS * 2), other.result(HOLD_SECONDS * 2)
    assert gate.opened_in_time == [True]
    return results


@contextmanager
def _sessions_left_as_the_handler_left_them(sessions):
    """Requests in the block get a session that nothing closes or rolls back
    after the handler: what the handler left open is still open. Yields the
    sessions of the requests."""
    from app.main import app

    kept = []

    def override_get_db():
        db = sessions()
        kept.append(db)
        yield db

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = override_get_db
    try:
        yield kept
    finally:
        app.dependency_overrides[get_db] = previous
        for db in kept:
            db.close()


@contextmanager
def _connections_of_requests(sessions):
    """Requests in the block get a session each, as always. Yields a function
    that says how many of them hold a connection right now. (A session that
    only has objects added to it is in a transaction without one.)"""
    from app.main import app

    requests, holding = [], set()

    def began(session, _transaction, _connection) -> None:
        holding.add(session)

    def ended(session, transaction) -> None:
        if transaction.parent is None:
            holding.discard(session)

    def override_get_db():
        db = sessions()
        requests.append(db)
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = override_get_db
    event.listen(sessions, "after_begin", began)
    event.listen(sessions, "after_transaction_end", ended)
    try:
        yield lambda: len(holding.intersection(requests))
    finally:
        event.remove(sessions, "after_begin", began)
        event.remove(sessions, "after_transaction_end", ended)
        app.dependency_overrides[get_db] = previous


def _take_at_once(sessions, lock) -> None:
    """Take a scope lock in a session of its own, without waiting for a
    session that still holds it."""
    with sessions() as db:
        if db.get_bind().dialect.name == "postgresql":
            db.execute(text("SET LOCAL lock_timeout = '300ms'"))
        else:
            db.execute(text("PRAGMA busy_timeout = 300"))
        lock(db)
        db.rollback()


# -- a check and the insert that follows it ------------------------------------


def _start_check(client, headers, repository_id: int):
    return client.post(f"/api/repositories/{repository_id}/check", headers=headers)


def _start_compact(client, headers, repository_id: int):
    return client.post(f"/api/repositories/{repository_id}/compact", headers=headers)


def _delete_archive(client, headers, repository_id: int):
    return client.delete(
        f"/api/archives/{ARCHIVE}",
        params={"repository": "/repos/starters"},
        headers=headers,
    )


def _refresh_comparison(client, headers, repository_id: int):
    return client.post(
        f"/api/repositories/{repository_id}/prune/comparison/refresh", headers=headers
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    ("start", "kind", "insert"),
    [
        pytest.param(_start_check, "check", (maintenance_start, "enqueue"), id="check"),
        pytest.param(
            _start_compact, "compact", (maintenance_start, "enqueue"), id="compact"
        ),
        pytest.param(
            _delete_archive,
            "delete_archive",
            (maintenance_start, "enqueue"),
            id="delete-archive",
        ),
        pytest.param(
            _refresh_comparison,
            "prune_compare",
            ("app.services.operations.enqueue", "enqueue"),
            id="prune-comparison",
        ),
    ],
)
def test_of_two_starts_at_once_one_is_refused(
    test_client, database, held_runner, admin, monkeypatch, start, kind, insert
):
    repository_id = _seed_repository(database)
    gate = Gate()
    owner, name = insert
    if isinstance(owner, str):
        owner = import_module(owner)
    _hold_before(monkeypatch, owner, name, gate)

    def request():
        return start(test_client, admin, repository_id)

    first, second = _beside_the_held(gate, request, request)

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert len(_operations(database, kind)) == 1


@pytest.mark.unit
def test_of_two_resyncs_at_once_one_queues_the_run(
    test_client, database, held_runner, admin, monkeypatch
):
    repository_id = _seed_repository(database)
    gate = Gate()
    _hold_before(monkeypatch, reconcile, "enqueue_chain", gate)

    def request():
        return test_client.post(
            f"/api/repositories/{repository_id}/resync", headers=admin
        )

    first, second = _beside_the_held(gate, request, request)

    assert first.status_code == second.status_code == 200
    queued = sorted([first.json()["operations"], second.json()["operations"]], key=len)
    assert queued[0] == [] and queued[1]
    with database() as db:
        assert db.query(Operation).count() == len(queued[1])


@pytest.mark.unit
def test_of_two_reconcile_requests_at_once_one_queues_the_runs(
    test_client, database, held_runner, admin, monkeypatch
):
    _seed_repository(database)
    gate = Gate()
    _hold_before(monkeypatch, reconcile, "enqueue_chain", gate)

    def request():
        return test_client.post("/api/operations/reconcile", headers=admin)

    first, second = _beside_the_held(gate, request, request)

    assert first.status_code == second.status_code == 200
    assert sorted([first.json()["repositories"], second.json()["repositories"]]) == [
        0,
        1,
    ]
    with database() as db:
        run_ids = {run_id for (run_id,) in db.query(Operation.run_id)}
    assert len(run_ids) == 1


@pytest.mark.unit
def test_of_two_reconcile_requests_without_a_settings_row_one_queues_the_runs(
    test_client, database, held_runner, admin, monkeypatch
):
    """An install that has saved no setting yet has no settings row, and
    the two take their turn without one."""
    _seed_repository(database)
    with database() as db:
        db.query(SystemSettings).delete()
        db.commit()
    gate = Gate()
    _hold_before(monkeypatch, reconcile, "enqueue_chain", gate)

    def request():
        return test_client.post("/api/operations/reconcile", headers=admin)

    first, second = _beside_the_held(gate, request, request)

    assert first.status_code == second.status_code == 200
    assert sorted([first.json()["repositories"], second.json()["repositories"]]) == [
        0,
        1,
    ]
    with database() as db:
        run_ids = {run_id for (run_id,) in db.query(Operation.run_id)}
        assert db.query(SystemSettings).count() == 0
    assert len(run_ids) == 1


@pytest.mark.unit
def test_a_reconcile_request_beside_a_resync_queues_no_second_run(
    test_client, database, held_runner, admin, monkeypatch
):
    repository_id = _seed_repository(database)
    gate = Gate()
    _hold_before(monkeypatch, reconcile, "enqueue_chain", gate)

    resync, reconciled = _beside_the_held(
        gate,
        lambda: test_client.post(
            f"/api/repositories/{repository_id}/resync", headers=admin
        ),
        lambda: test_client.post("/api/operations/reconcile", headers=admin),
    )

    assert resync.status_code == reconciled.status_code == 200
    assert resync.json()["operations"]
    assert reconciled.json() == {"repositories": 0}
    with database() as db:
        assert db.query(Operation).count() == len(resync.json()["operations"])


@pytest.mark.unit
def test_two_stages_paused_at_once_are_both_paused(
    test_client, database, held_runner, admin, monkeypatch
):
    """The request that read the list first writes it last."""
    gate = Gate()
    _hold_after(monkeypatch, operations_api, "_settings_row", gate)

    def pause(stage: str):
        return test_client.post(f"/api/operations/stages/{stage}/pause", headers=admin)

    first, second = _while_held(gate, lambda: pause("history"), lambda: pause("stats"))

    assert first.status_code == second.status_code == 200
    with database() as db:
        assert set(db.query(SystemSettings).one().paused_stages) == {
            "history",
            "stats",
        }
    assert set(first.json()["paused_stages"]) == {"history", "stats"}


def _run_plan(client, headers, plan_id: int):
    return client.post(f"/api/backup-plans/{plan_id}/run", headers=headers)


def _run_schedule(client, headers, schedule_id: int):
    return client.post(f"/api/schedule/{schedule_id}/run-now", headers=headers)


def _start_borg_2_check(client, headers, repository_id: int):
    return client.post(
        "/api/v2/backup/check", json={"repository_id": repository_id}, headers=headers
    )


def _start_borg_2_compact(client, headers, repository_id: int):
    return client.post(
        "/api/v2/backup/compact", json={"repository_id": repository_id}, headers=headers
    )


def _delete_borg_2_archive(client, headers, repository_id: int):
    return client.delete(
        f"/api/v2/archives/{ARCHIVE}",
        params={"repository": str(repository_id)},
        headers=headers,
    )


def _license_borg_2(sessions) -> None:
    with sessions() as db:
        db.add(LicensingState(instance_id="starters", plan="pro", status="active"))
        db.commit()


@pytest.mark.unit
def test_of_two_plan_runs_at_once_one_is_refused(
    test_client, database, held_runner, admin, plan_runs_do_nothing, monkeypatch
):
    plan_id = _seed_plan(database, _seed_repository(database))
    gate = Gate()
    _hold_after(monkeypatch, backup_plan_execution_service, "has_active_run", gate)

    def request():
        return _run_plan(test_client, admin, plan_id)

    first, second = _beside_the_held(gate, request, request)

    assert sorted([first.status_code, second.status_code]) == [202, 409]
    assert _runs(database, plan_id) == [("manual", "pending")]


@pytest.mark.unit
def test_of_two_retries_at_once_one_is_refused(
    test_client, database, held_runner, admin, plan_runs_do_nothing, monkeypatch
):
    repository_id = _seed_repository(database)
    plan_id = _seed_plan(database, repository_id)
    failed = _seed_run(database, plan_id, repository_id, "failed")
    gate = Gate()
    _hold_after(monkeypatch, backup_plan_execution_service, "has_active_run", gate)

    def request():
        return test_client.post(f"/api/backup-plans/runs/{failed}/retry", headers=admin)

    first, second = _beside_the_held(gate, request, request)

    assert sorted([first.status_code, second.status_code]) == [202, 409]
    assert _runs(database, plan_id) == [("manual", "failed"), ("retry", "pending")]


@pytest.mark.unit
def test_the_schedule_does_not_start_a_plan_beside_a_run_started_by_hand(
    test_client, database, held_runner, admin, plan_runs_do_nothing, monkeypatch
):
    now = datetime.utcnow()
    plan_id = _seed_plan(
        database,
        _seed_repository(database),
        schedule_enabled=True,
        cron_expression="0 3 * * *",
        next_run=now - timedelta(minutes=1),
    )
    gate = Gate()
    _hold_after(monkeypatch, backup_plan_execution_service, "has_active_run", gate)

    def dispatch():
        with database() as db:
            return asyncio.run(backup_plan_execution_service.dispatch_due_runs(db, now))

    by_hand, dispatched = _beside_the_held(
        gate, lambda: _run_plan(test_client, admin, plan_id), dispatch
    )

    assert by_hand.status_code == 202
    assert dispatched == 0
    assert _runs(database, plan_id) == [("manual", "pending")]


@pytest.mark.unit
def test_of_two_run_nows_of_a_borg_2_repository_one_is_refused(
    test_client, database, held_runner, admin, scheduled_work_does_nothing, monkeypatch
):
    """A Borg 2 backup asks for its feature between the admission and the
    insert. That lookup must not commit: the commit would give the
    admission's lock back, and the second request would be admitted too."""
    _license_borg_2(database)
    schedule_id = _seed_schedule(
        database, _seed_repository(database, borg_version=2), linked=False
    )
    gate = Gate()
    _hold_before(
        monkeypatch, import_module("app.services.operations.enqueue"), "enqueue", gate
    )

    def request():
        return _run_schedule(test_client, admin, schedule_id)

    first, second = _beside_the_held(gate, request, request)

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert len(_operations(database, "backup")) == 1


@contextmanager
def _waiting_pool(sessions, busy_seconds: float = 30):
    """Sessions on the same database with the pool the app has, whose
    checkouts wait: the code that keeps waits off the loop asks for it. On
    SQLite a write gives up after `busy_seconds`."""
    engine = sessions.kw["bind"]
    if isinstance(engine.pool, QueuePool):
        yield sessions
        return
    pooled = create_engine(
        engine.url,
        poolclass=QueuePool,
        connect_args={"check_same_thread": False, "timeout": busy_seconds},
    )
    try:
        yield sessionmaker(autocommit=False, autoflush=False, bind=pooled)
    finally:
        pooled.dispose()


async def _the_loop_runs_while(waiting, release) -> None:
    """`waiting` is a coroutine that needs a lock another session holds. Run
    it, and see that the loop takes a turn while it waits: `release`, which
    gives the lock back, runs only after a while, from a thread."""
    released = threading.Event()

    def give_back() -> None:
        released.set()
        release()

    timer = threading.Timer(HOLD_SECONDS / 2, give_back)
    timer.start()
    try:
        task = asyncio.ensure_future(waiting)
        await asyncio.sleep(0.05)
        assert not released.is_set(), "the wait for the lock held the loop"
        await asyncio.wait_for(task, HOLD_SECONDS * 2)
    finally:
        timer.cancel()
    assert released.is_set(), "nothing waited for the lock"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"schedule_enabled": False},
        {"enabled": False},
        {"next_run": datetime(2999, 1, 1)},
    ],
    ids=["schedule-off", "plan-off", "moved"],
)
async def test_the_plan_schedule_starts_nothing_for_a_plan_changed_meanwhile(
    database, plan_runs_do_nothing, monkeypatch, change
):
    """The due plans are read first. A plan that is switched off, or moved,
    while the schedule waits for its lock is no longer due under the lock."""
    import app.services.backup_plan_execution_service as plan_service

    now = datetime.utcnow()
    plan_id = _seed_plan(
        database,
        _seed_repository(database),
        schedule_enabled=True,
        cron_expression="0 3 * * *",
        next_run=now - timedelta(minutes=1),
    )
    real_lock = plan_service.lock_backup_plan_scope
    changed: list[int] = []

    def lock_after_the_change(db, locked_plan_id):
        if not changed:
            changed.append(locked_plan_id)
            with database() as other:
                other.query(BackupPlan).filter(BackupPlan.id == plan_id).update(change)
                other.commit()
        real_lock(db, locked_plan_id)

    monkeypatch.setattr(plan_service, "lock_backup_plan_scope", lock_after_the_change)

    with database() as db:
        assert await backup_plan_execution_service.dispatch_due_runs(db, now) == 0

    assert _runs(database, plan_id) == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_plan_schedule_waits_for_the_plan_lock_off_the_loop(
    database, plan_runs_do_nothing
):
    now = datetime.utcnow()
    plan_id = _seed_plan(
        database,
        _seed_repository(database),
        schedule_enabled=True,
        cron_expression="0 3 * * *",
        next_run=now - timedelta(minutes=1),
    )
    # the licensing row exists, as on any install: the plan's feature check
    # then reads only
    _license_borg_2(database)
    with _waiting_pool(database) as pooled, pooled() as holder, pooled() as db:
        lock_backup_plan_scope(holder, plan_id)

        await _the_loop_runs_while(
            backup_plan_execution_service.dispatch_due_runs(db, now), holder.rollback
        )

    assert _runs(database, plan_id) == [("schedule", "pending")]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_plan_schedule_keeps_no_lock_across_a_turn_of_the_loop(
    database, monkeypatch
):
    """Two plans are due. The run of the first is launched and writes on the
    loop, as a run does when it starts, while the schedule is at the second
    plan. On SQLite the plan's lock is the one write lock: were it taken in a
    thread and kept while the loop takes its turn, that write would wait on
    the loop for a lock that only the loop could give back."""
    import app.services.backup_plan_execution_service as plan_service

    now = datetime.utcnow()
    repository_id = _seed_repository(database)
    due = {
        "schedule_enabled": True,
        "cron_expression": "0 3 * * *",
        "next_run": now - timedelta(minutes=1),
    }
    plans = [
        _seed_plan(database, repository_id, name=f"due {index}", **due)
        for index in (1, 2)
    ]
    _license_borg_2(database)
    service = BackupPlanExecutionService()
    second_plan_locked = threading.Event()
    locked: list[int] = []
    writes: list[str] = []
    real_lock = plan_service.lock_backup_plan_scope

    def lock(db, plan_id):
        real_lock(db, plan_id)
        locked.append(plan_id)
        if len(locked) == 2:
            second_plan_locked.set()
            time.sleep(0.3)  # the first run writes meanwhile

    monkeypatch.setattr(plan_service, "lock_backup_plan_scope", lock)

    with _waiting_pool(database, busy_seconds=2) as pooled:

        async def execute_run(run_id: int) -> None:
            while not second_plan_locked.is_set():
                await asyncio.sleep(0.005)
            with pooled() as db:
                try:
                    db.query(BackupPlanRun).filter(BackupPlanRun.id == run_id).update(
                        {"status": "running"}, synchronize_session=False
                    )
                    db.commit()
                    writes.append("written")
                except OperationalError as error:
                    writes.append(str(error.orig))

        service.execute_run = execute_run
        with pooled() as db:
            assert await service.dispatch_due_runs(db, now) == 2
        await asyncio.wait_for(_until(lambda: not service.live_run_ids), HOLD_SECONDS)

    assert writes == ["written", "written"]
    assert [_runs(database, plan_id) for plan_id in plans] == [
        [("schedule", "running")],
        [("schedule", "running")],
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_reconcile_tick_waits_for_its_lock_off_the_loop(
    database, admin, monkeypatch
):
    _seed_repository(database)
    with _waiting_pool(database) as pooled, pooled() as holder:
        monkeypatch.setattr(reconcile, "SessionLocal", pooled)
        reconcile.lock_reconcile_scope(holder)

        await _the_loop_runs_while(
            reconcile.ReconcileScheduler()._tick_off_loop(datetime.utcnow()),
            holder.rollback,
        )

    with database() as db:
        assert db.query(Operation).count() > 0


# -- a refusal gives the lock back ---------------------------------------------


def _repository_lock(repository_id: int):
    def lock(db):
        lock_repository_scope(db, db.get(Repository, repository_id))

    return lock


@pytest.mark.unit
@pytest.mark.parametrize(
    ("start", "kind", "params"),
    [
        pytest.param(_start_check, "check", None, id="check"),
        pytest.param(
            _delete_archive,
            "delete_archive",
            {"archive_name": ARCHIVE},
            id="delete-archive",
        ),
        pytest.param(_refresh_comparison, "prune_compare", None, id="prune-comparison"),
    ],
)
def test_a_refused_start_leaves_the_repository_lock(
    test_client, database, held_runner, admin, start, kind, params
):
    repository_id = _seed_repository(database)
    _seed_operation(database, repository_id, kind, params=params)

    with _sessions_left_as_the_handler_left_them(database):
        assert start(test_client, admin, repository_id).status_code == 409
        _take_at_once(database, _repository_lock(repository_id))

    assert len(_operations(database, kind)) == 1


@pytest.mark.unit
@pytest.mark.parametrize("path", ["run", "retry"])
def test_a_refused_plan_run_leaves_the_plan_lock(
    test_client, database, held_runner, admin, plan_runs_do_nothing, path
):
    repository_id = _seed_repository(database)
    plan_id = _seed_plan(database, repository_id)
    failed = _seed_run(database, plan_id, repository_id, "failed")
    _seed_run(database, plan_id, repository_id, "running")
    url = (
        f"/api/backup-plans/{plan_id}/run"
        if path == "run"
        else f"/api/backup-plans/runs/{failed}/retry"
    )

    with _sessions_left_as_the_handler_left_them(database):
        assert test_client.post(url, headers=admin).status_code == 409
        _take_at_once(database, lambda db: lock_backup_plan_scope(db, plan_id))


@pytest.mark.unit
@pytest.mark.parametrize("start", ["maintenance", "archive-delete", "plan-run"])
def test_a_start_that_refuses_gives_the_lock_back_itself(database, start):
    """Not every caller ends the transaction for it: a prune route and the
    check schedule call start_maintenance on the loop and keep their session."""
    repository_id = _seed_repository(database)
    plan_id = _seed_plan(database, repository_id)
    _seed_operation(database, repository_id, "check")
    _seed_operation(
        database, repository_id, "delete_archive", params={"archive_name": ARCHIVE}
    )
    _seed_run(database, plan_id, repository_id, "running")

    with database() as db:
        repository = db.get(Repository, repository_id)
        with pytest.raises(HTTPException) as refused:
            if start == "maintenance":
                maintenance_start.start_maintenance(
                    db,
                    repository,
                    "check",
                    trigger="manual",
                    params={},
                    user_id=None,
                    duplicate_error_key="backend.errors.repo.checkAlreadyRunning",
                )
            elif start == "archive-delete":
                maintenance_start.start_archive_delete(
                    db, repository, ARCHIVE, user_id=None
                )
            else:
                BackupPlanExecutionService().refuse_active_run(db, plan_id)
        assert refused.value.status_code == 409

        # the refusing session is still open, and holds nothing
        if start == "plan-run":
            _take_at_once(
                database, lambda other: lock_backup_plan_scope(other, plan_id)
            )
        else:
            _take_at_once(database, _repository_lock(repository_id))


@pytest.mark.unit
def test_a_retry_with_nothing_to_retry_leaves_the_plan_lock(
    test_client, database, held_runner, admin, plan_runs_do_nothing
):
    """The retry finds out under the plan's lock that no failed repository
    is left to retry, and answers 400. The lock goes back in its thread."""
    repository_id = _seed_repository(database)
    plan_id = _seed_plan(database, repository_id)
    failed = _seed_run(database, plan_id, repository_id, "failed")
    with database() as db:
        db.query(BackupPlanRepository).update({"enabled": False})
        db.commit()

    with _sessions_left_as_the_handler_left_them(database):
        response = test_client.post(
            f"/api/backup-plans/runs/{failed}/retry", headers=admin
        )
        assert response.status_code == 400, response.text
        _take_at_once(database, lambda db: lock_backup_plan_scope(db, plan_id))

    assert _runs(database, plan_id) == [("manual", "failed")]


@pytest.mark.unit
def test_a_start_that_fails_under_its_lock_leaves_the_lock(
    test_client, database, held_runner, admin, monkeypatch
):
    repository_id = _seed_repository(database)

    def fail(*_args, **_kwargs):
        raise RuntimeError("no insert")

    monkeypatch.setattr(
        import_module("app.services.operations.enqueue"), "enqueue", fail
    )

    with _sessions_left_as_the_handler_left_them(database):
        with pytest.raises(RuntimeError):
            _refresh_comparison(test_client, admin, repository_id)
        _take_at_once(database, _repository_lock(repository_id))


@pytest.mark.unit
def test_a_run_now_that_fails_under_its_lock_leaves_the_lock(
    test_client, database, held_runner, admin, monkeypatch
):
    repository_id = _seed_repository(database)
    schedule_id = _seed_schedule(database, repository_id, linked=False)

    def fail(*_args, **_kwargs):
        raise RuntimeError("no insert")

    monkeypatch.setattr(schedule_api, "create_backup_operation", fail)

    with _sessions_left_as_the_handler_left_them(database):
        assert _run_schedule(test_client, admin, schedule_id).status_code == 500
        _take_at_once(database, _repository_lock(repository_id))


@pytest.mark.unit
def test_the_lock_probe_fails_on_a_lock_that_is_held(database):
    """What the two tests above rely on."""
    repository_id = _seed_repository(database)
    with database() as holder:
        _repository_lock(repository_id)(holder)
        with pytest.raises(OperationalError):
            _take_at_once(database, _repository_lock(repository_id))
        holder.rollback()
    _take_at_once(database, _repository_lock(repository_id))


# -- the handlers ---------------------------------------------------------------

IN_A_WORKER_THREAD = [
    "app.api.repositories:check_repository",
    "app.api.repositories:restore_check_repository",
    "app.api.repositories:compact_repository",
    "app.api.archive_index:prune_comparison_refresh",
    "app.api.archive_index:resync",
    "app.api.archives:delete_archive",
    "app.api.backup:retry_backup_job",
    "app.api.restore:start_restore",
    "app.api.operations:reconcile_now",
    "app.api.operations:pause_background",
    "app.api.operations:resume_background",
    "app.api.operations:pause_stage",
    "app.api.operations:resume_stage",
    "app.api.operations:update_limits",
    "app.api.v2.archives:delete_archive",
    "app.api.v2.backups:compact_repository",
    "app.api.v2.backups:check_repository",
]


@pytest.mark.unit
@pytest.mark.parametrize("handler", IN_A_WORKER_THREAD)
def test_the_handler_runs_in_a_worker_thread(handler):
    """FastAPI runs a plain function in a worker thread and a coroutine on
    the event loop."""
    module, name = handler.split(":")
    assert not inspect.iscoroutinefunction(getattr(import_module(module), name))


def _pause_all(client, headers, repository_id: int):
    return client.post("/api/operations/pause", headers=headers)


def _resume_all(client, headers, repository_id: int):
    return client.post("/api/operations/resume", headers=headers)


def _pause_stage(client, headers, repository_id: int):
    return client.post("/api/operations/stages/history/pause", headers=headers)


def _resume_stage(client, headers, repository_id: int):
    return client.post("/api/operations/stages/history/resume", headers=headers)


def _set_limits(client, headers, repository_id: int):
    return client.put(
        "/api/operations/limits", json={"index_workers": 3}, headers=headers
    )


def _reconcile(client, headers, repository_id: int):
    return client.post("/api/operations/reconcile", headers=headers)


def _resync(client, headers, repository_id: int):
    return client.post(f"/api/repositories/{repository_id}/resync", headers=headers)


@pytest.mark.unit
@pytest.mark.parametrize(
    "request_",
    [
        _start_check,
        _start_compact,
        _delete_archive,
        _refresh_comparison,
        _resync,
        _reconcile,
        _pause_all,
        _resume_all,
        _pause_stage,
        _resume_stage,
        _set_limits,
    ],
    ids=lambda request_: request_.__name__.strip("_"),
)
def test_the_handler_ends_its_read_when_it_returns(
    test_client, database, held_runner, admin, request_
):
    """The request no longer holds a connection while it waits for the thread
    that validates its response."""
    repository_id = _seed_repository(database)

    with _sessions_left_as_the_handler_left_them(database) as left:
        assert request_(test_client, admin, repository_id).status_code == 200
        assert [db.in_transaction() for db in left] == [False]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("request_", "borg_version"),
    [
        (_start_check, 1),
        (_delete_archive, 1),
        (_start_borg_2_check, 2),
        (_start_borg_2_compact, 2),
        (_delete_borg_2_archive, 2),
    ],
    ids=lambda value: value.__name__.strip("_") if callable(value) else str(value),
)
def test_the_request_waits_for_its_worker_threads_without_a_connection(
    test_client, database, held_runner, admin, monkeypatch, request_, borg_version
):
    """FastAPI takes a worker thread for the handler. The threads may all be
    waiting for connections, so the request holds none while it waits for
    one: not from a dependency before the handler either. The Borg 2 routes
    have one, the feature check, which reads before the user is looked up."""
    import fastapi.routing

    _license_borg_2(database)
    repository_id = _seed_repository(database, borg_version=borg_version)
    held_while_waiting: list[int] = []
    real_run_in_threadpool = fastapi.routing.run_in_threadpool

    with _connections_of_requests(database) as held:

        async def run_in_threadpool(function, /, *args, **kwargs):
            held_while_waiting.append(held())
            return await real_run_in_threadpool(function, *args, **kwargs)

        monkeypatch.setattr(fastapi.routing, "run_in_threadpool", run_in_threadpool)
        assert request_(test_client, admin, repository_id).status_code == 200

    assert held_while_waiting and not any(held_while_waiting)


@pytest.fixture
def scheduled_work_does_nothing(monkeypatch):
    """The tasks run-now starts end at once. Returns what was started."""
    started: list[tuple] = []

    async def backup_with_maintenance(backup_job_id, repository_path, job_id, **_):
        started.append(("backup", backup_job_id, _on_the_loop()))

    async def multi_repo(job_id):
        started.append(("multi", job_id, _on_the_loop()))

    monkeypatch.setattr(
        schedule_api,
        "execute_scheduled_backup_with_maintenance",
        backup_with_maintenance,
    )
    monkeypatch.setattr(schedule_api, "execute_multi_repo_schedule_by_id", multi_repo)
    return started


def _wait_for(test_client, condition) -> bool:
    """Give the tasks on the app's loop their turns until `condition` holds."""

    async def wait() -> bool:
        for _ in range(int(HOLD_SECONDS / 0.01)):
            if condition():
                return True
            await asyncio.sleep(0.01)
        return condition()

    return test_client.portal.call(wait)


@pytest.fixture
def request_database_work(session_per_request):
    """Where the database work of the requests ran: True for each step on
    the event loop."""
    seen: list[bool] = []

    def record(*_args) -> None:
        seen.append(_on_the_loop())

    names = ("do_orm_execute", "after_begin", "after_commit", "after_soft_rollback")
    for name in names:
        event.listen(session_per_request, name, record)
    yield seen
    for name in names:
        event.remove(session_per_request, name, record)


@pytest.mark.unit
@pytest.mark.parametrize("path", ["run", "retry", "run-now", "run-now-list", "stats"])
def test_a_starter_that_stays_a_coroutine_does_its_database_work_in_a_thread(
    test_client,
    session_per_request,
    held_runner,
    plan_runs_do_nothing,
    scheduled_work_does_nothing,
    request_database_work,
    monkeypatch,
    path,
):
    sessions = session_per_request
    with sessions() as db:
        db.add(
            User(username=ADMIN, password_hash="unused", is_active=True, role="admin")
        )
        db.commit()
    repository_id = _seed_repository(sessions)
    plan_id = _seed_plan(sessions, repository_id)
    enqueued_on_the_loop: list[bool] = []
    import app.services.operations.enqueue as enqueue_module

    original_chain = enqueue_module.enqueue_chain

    def chain(*args, **kwargs):
        try:
            return original_chain(*args, **kwargs)
        finally:
            enqueued_on_the_loop.append(_on_the_loop())

    monkeypatch.setattr(enqueue_module, "enqueue_chain", chain)
    if path == "run":
        url, expected = f"/api/backup-plans/{plan_id}/run", 202
    elif path == "retry":
        failed = _seed_run(sessions, plan_id, repository_id, "failed")
        url, expected = f"/api/backup-plans/runs/{failed}/retry", 202
    elif path == "stats":
        url, expected = "/api/settings/refresh-stats", 200
    else:
        schedule_id = _seed_schedule(
            sessions, repository_id, linked=path == "run-now-list"
        )
        url, expected = f"/api/schedule/{schedule_id}/run-now", 200
    request_database_work.clear()

    response = test_client.post(url, headers=_headers())

    assert response.status_code == expected, response.text
    assert request_database_work and not any(request_database_work)
    # and what it starts is started on the loop
    if path in ("run", "retry"):
        assert _wait_for(test_client, lambda: plan_runs_do_nothing)
        assert plan_runs_do_nothing == [response.json()["id"]]
    elif path == "stats":
        assert _wait_for(test_client, lambda: enqueued_on_the_loop)
        assert enqueued_on_the_loop == [False]
    else:
        assert _wait_for(test_client, lambda: scheduled_work_does_nothing)
        kind = "multi" if path == "run-now-list" else "backup"
        assert [
            (what, on_loop) for what, _id, on_loop in scheduled_work_does_nothing
        ] == [(kind, True)]


@pytest.mark.unit
@pytest.mark.parametrize("path", ["run", "retry", "run-now"])
def test_a_starter_that_stays_a_coroutine_ends_its_read_too(
    test_client,
    database,
    held_runner,
    admin,
    plan_runs_do_nothing,
    scheduled_work_does_nothing,
    path,
):
    repository_id = _seed_repository(database)
    plan_id = _seed_plan(database, repository_id)
    if path == "run":
        url = f"/api/backup-plans/{plan_id}/run"
    elif path == "retry":
        failed = _seed_run(database, plan_id, repository_id, "failed")
        url = f"/api/backup-plans/runs/{failed}/retry"
    else:
        schedule_id = _seed_schedule(database, repository_id, linked=False)
        url = f"/api/schedule/{schedule_id}/run-now"

    with _sessions_left_as_the_handler_left_them(database) as left:
        assert test_client.post(url, headers=admin).status_code in (200, 202)
        assert [db.in_transaction() for db in left] == [False]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("path", "owner"),
    [
        ("run", "app.services.backup_plan_execution_service"),
        ("retry", "app.services.backup_plan_execution_service"),
        ("run-now", "app.api.schedule"),
        ("stats", "app.api.settings"),
    ],
)
def test_a_starter_that_stays_a_coroutine_waits_for_its_thread_without_a_connection(
    test_client,
    database,
    held_runner,
    admin,
    plan_runs_do_nothing,
    scheduled_work_does_nothing,
    monkeypatch,
    path,
    owner,
):
    """The threads it waits for may be waiting for a connection themselves,
    after their commit: a request that held one meanwhile would keep it from
    them."""
    repository_id = _seed_repository(database)
    plan_id = _seed_plan(database, repository_id)
    if path == "run":
        url = f"/api/backup-plans/{plan_id}/run"
    elif path == "retry":
        failed = _seed_run(database, plan_id, repository_id, "failed")
        url = f"/api/backup-plans/runs/{failed}/retry"
    elif path == "stats":
        url = "/api/settings/refresh-stats"

        async def no_background_work(*_args) -> None:
            """It would outlive the test and its database."""

        monkeypatch.setattr(
            "app.api.settings._run_stats_refresh_background", no_background_work
        )
    else:
        schedule_id = _seed_schedule(database, repository_id, linked=False)
        url = f"/api/schedule/{schedule_id}/run-now"
    module = import_module(owner)
    real_run_off_loop = module.run_off_loop
    held_while_waiting: list[int] = []

    with _connections_of_requests(database) as held:

        async def run_off_loop(function, *args):
            held_while_waiting.append(held())
            return await real_run_off_loop(function, *args)

        monkeypatch.setattr(module, "run_off_loop", run_off_loop)
        assert test_client.post(url, headers=admin).status_code in (200, 202)

    assert held_while_waiting and not any(held_while_waiting)


# -- committed, and the request is cancelled ------------------------------------


def _cancel_while_held(test_client, gate: Gate, url: str, headers, meanwhile=None):
    """Send the request on the app's loop and cancel it while the gate holds
    its thread. `meanwhile` runs on the loop before the gate opens."""
    from app.main import app

    async def cancelled_request() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test", timeout=None
        ) as client:
            request = asyncio.ensure_future(client.post(url, headers=headers))
            for _ in range(int(HOLD_SECONDS / 0.01)):
                if gate.reached.is_set():
                    break
                await asyncio.sleep(0.01)
            assert gate.reached.is_set(), "the request never reached the gate"
            request.cancel()
            await asyncio.sleep(0.05)  # the handler has the cancellation now
            assert not request.done(), "the request did not wait for its thread"
            if meanwhile is not None:
                meanwhile()
            gate.open()
            with pytest.raises(asyncio.CancelledError):
                await request

    test_client.portal.call(cancelled_request)
    assert gate.opened_in_time == [True]


def _startup_sweep() -> None:
    """The sweep of a runner that gets its lease now, as it calls it: on the
    loop, with the runs the service executes."""
    from app.database.database import SessionLocal

    db = SessionLocal()
    try:
        cleanup_orphaned_jobs(db, backup_plan_execution_service.live_run_ids)
    finally:
        db.close()


@pytest.mark.unit
@pytest.mark.parametrize("path", ["run", "retry"])
@pytest.mark.parametrize(
    "sweep", [False, True], ids=["cancelled", "cancelled-and-swept"]
)
def test_a_plan_run_committed_by_a_cancelled_request_is_launched(
    test_client, database, held_runner, admin, plan_runs_do_nothing, path, sweep
):
    """With `sweep`, the startup sweep runs between the commit and the launch
    as well: the runner got its lease just then. It fails the run a restart
    left behind and leaves the new one."""
    repository_id = _seed_repository(database)
    plan_id = _seed_plan(database, repository_id)
    if path == "run":
        url = f"/api/backup-plans/{plan_id}/run"
        before = []
    else:
        failed = _seed_run(database, plan_id, repository_id, "failed")
        url = f"/api/backup-plans/runs/{failed}/retry"
        before = [("manual", "failed")]
    other_plan = _seed_plan(database, repository_id, name="left behind")
    left_behind = _seed_run(database, other_plan, repository_id, "pending")
    gate = Gate()

    with _held_after_its_commit(database, gate, BackupPlanRun):
        _cancel_while_held(
            test_client, gate, url, admin, meanwhile=_startup_sweep if sweep else None
        )

    assert _wait_for(test_client, lambda: plan_runs_do_nothing)
    with database() as db:
        new_run = (
            db.query(BackupPlanRun)
            .filter(BackupPlanRun.backup_plan_id == plan_id)
            .order_by(BackupPlanRun.id.desc())
            .first()
        )
        assert plan_runs_do_nothing == [new_run.id]
        assert db.get(BackupPlanRun, left_behind).status == (
            "failed" if sweep else "pending"
        )
    assert _runs(database, plan_id) == before + [
        ("retry" if path == "retry" else "manual", "pending")
    ]
    assert not backup_plan_execution_service.live_run_ids


@pytest.mark.unit
@pytest.mark.parametrize("linked", [False, True], ids=["one-repository", "list"])
def test_what_run_now_committed_is_started_when_the_request_is_cancelled(
    test_client, database, held_runner, admin, scheduled_work_does_nothing, linked
):
    schedule_id = _seed_schedule(database, _seed_repository(database), linked=linked)
    gate = Gate()

    with _held_after_its_commit(database, gate, ScheduledJob if linked else Operation):
        _cancel_while_held(
            test_client, gate, f"/api/schedule/{schedule_id}/run-now", admin
        )

    assert _wait_for(test_client, lambda: scheduled_work_does_nothing)
    if linked:
        assert scheduled_work_does_nothing == [("multi", schedule_id, True)]
    else:
        (backup,) = _operations(database, "backup")
        assert scheduled_work_does_nothing == [("backup", backup.id, True)]


# -- the service ---------------------------------------------------------------


@pytest.fixture
def service():
    service = BackupPlanExecutionService()
    service.launched = []

    async def execute_run(run_id: int) -> None:
        service.launched.append(run_id)

    service.execute_run = execute_run
    return service


def _create_run(service, sessions, plan_id: int) -> int:
    with sessions() as db:
        return service.create_run(db, db.get(BackupPlan, plan_id), trigger="manual")


@pytest.mark.unit
def test_a_committed_run_is_live_before_it_is_launched(database, service):
    plan_id = _seed_plan(database, _seed_repository(database))

    run_id = _create_run(service, database, plan_id)

    assert service.live_run_ids == {run_id}
    assert service.launched == []


@pytest.mark.unit
def test_a_run_whose_commit_failed_is_not_live(database, service, monkeypatch):
    plan_id = _seed_plan(database, _seed_repository(database))

    with database() as db:
        monkeypatch.setattr(db, "commit", lambda: 1 / 0)
        with pytest.raises(ZeroDivisionError):
            service.create_run(db, db.get(BackupPlan, plan_id), trigger="manual")

    assert service.live_run_ids == set()
    assert _runs(database, plan_id) == []


@pytest.mark.unit
@pytest.mark.parametrize("path", ["run", "retry"])
def test_a_new_run_is_handed_on_without_a_query_after_its_commit(
    database, service, path
):
    """The id is what gets the run launched. Read after the commit it is a
    query, and one that fails would leave the run committed, live and never
    launched."""
    repository_id = _seed_repository(database)
    plan_id = _seed_plan(database, repository_id)
    failed = _seed_run(database, plan_id, repository_id, "failed")
    with database() as db:
        plan, source = db.get(BackupPlan, plan_id), db.get(BackupPlanRun, failed)

        def no_query_after_the_commit(session) -> None:
            def refuse(_state):
                raise AssertionError("a query after the commit")

            event.listen(session, "do_orm_execute", refuse)

        event.listen(db, "after_commit", no_query_after_the_commit)
        if path == "run":
            run_id = service.create_run(db, plan, trigger="manual")
        else:
            run_id = service.create_retry_run(db, source, requested_by_user_id=None)

    assert service.live_run_ids == {run_id}
    assert _runs(database, plan_id)[-1] == (
        "manual" if path == "run" else "retry",
        "pending",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_run_cancelled_before_its_launch_does_not_start(
    test_client, session_per_request, monkeypatch
):
    """The run is committed in a thread and launched afterwards. A cancel
    that comes in between stays: the launch does not turn the run back to
    running or run anything for it."""
    sessions = session_per_request
    service = BackupPlanExecutionService()
    plan_id = _seed_plan(sessions, _seed_repository(sessions))
    run_id = _create_run(service, sessions, plan_id)
    executed: list[str] = []

    async def execute_series(*_args) -> None:
        executed.append("backups")

    monkeypatch.setattr(service, "_execute_series", execute_series)
    with sessions() as db:
        cancelled = await service.cancel_run(db, run_id)
    assert cancelled["already_terminal"] is False

    service._launch(run_id)
    await asyncio.wait_for(_until(lambda: not service.live_run_ids), HOLD_SECONDS)

    with sessions() as db:
        run = db.get(BackupPlanRun, run_id)
        assert (run.status, run.started_at) == ("cancelled", None)
    assert executed == []


async def _until(condition) -> None:
    while not condition():
        await asyncio.sleep(0.01)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_launched_run_is_live_until_its_task_ends(database, service):
    plan_id = _seed_plan(database, _seed_repository(database))
    finish = asyncio.Event()

    async def execute_run(run_id: int) -> None:
        await finish.wait()

    service.execute_run = execute_run

    with database() as db:
        run_id = service.start_run(db, db.get(BackupPlan, plan_id), trigger="manual")
    await asyncio.sleep(0)

    assert service.live_run_ids == {run_id}
    finish.set()
    await asyncio.sleep(0.01)
    assert service.live_run_ids == set()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_run_that_could_not_be_launched_is_not_left_live(
    database, service, monkeypatch
):
    plan_id = _seed_plan(database, _seed_repository(database))
    run_id = _create_run(service, database, plan_id)

    def no_task(coroutine):
        coroutine.close()
        raise RuntimeError("no running event loop")

    monkeypatch.setattr(
        "app.services.backup_plan_execution_service.asyncio.create_task", no_task
    )
    with pytest.raises(RuntimeError):
        service._launch(run_id)

    assert service.live_run_ids == set()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_run_a_stand_in_task_never_runs_is_not_left_live(
    database, service, monkeypatch
):
    """Tests replace `create_task`: nothing ends such a run, and it would
    keep its plan busy for every test after it."""
    plan_id = _seed_plan(database, _seed_repository(database))
    run_id = _create_run(service, database, plan_id)

    def stand_in(coroutine):
        coroutine.close()

    monkeypatch.setattr(
        "app.services.backup_plan_execution_service.asyncio.create_task", stand_in
    )
    service._launch(run_id)

    assert service.live_run_ids == set()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_work_that_fails_after_its_commit_still_has_its_run_launched(
    database, service
):
    plan_id = _seed_plan(database, _seed_repository(database))

    def work(created: list[int]) -> None:
        created.append(_create_run(service, database, plan_id))
        raise ZeroDivisionError

    with pytest.raises(ZeroDivisionError):
        with database() as db:
            await service.launch_after(db, work)
    await asyncio.sleep(0.01)

    assert len(service.launched) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_work_that_fails_under_the_plan_lock_gives_it_back_in_its_thread(
    database, service
):
    """Not on the loop, a turn later: on SQLite the lock is the one write
    lock, and a write on the loop in that turn would wait for it there."""
    plan_id = _seed_plan(database, _seed_repository(database))
    ended_on_the_loop: list[bool] = []

    with database() as db:
        event.listen(
            db,
            "after_transaction_end",
            lambda *_args: ended_on_the_loop.append(_on_the_loop()),
        )

        def work(created: list[int]) -> None:
            lock_backup_plan_scope(db, plan_id)
            raise ValueError("nothing to start")

        with pytest.raises(ValueError):
            await service.launch_after(db, work)

        assert ended_on_the_loop == [False]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_work_that_commits_nothing_launches_nothing(database, service):
    def work(created: list[int]) -> str:
        return "refused"

    with database() as db:
        assert await service.launch_after(db, work) == "refused"
    await asyncio.sleep(0.01)

    assert service.launched == []
    assert service.live_run_ids == set()


@pytest.mark.unit
def test_the_sweep_fails_a_run_whose_process_ended_before_the_launch(database, service):
    """The restart: the run is committed, nothing launched it, and the next
    process knows no live run. Its sweep fails the run, and the plan can run
    again."""
    plan_id = _seed_plan(database, _seed_repository(database))
    run_id = _create_run(service, database, plan_id)
    after_restart = BackupPlanExecutionService()

    with database() as db:
        assert after_restart.has_active_run(db, plan_id)
        cleanup_orphaned_jobs(db, after_restart.live_run_ids)

    with database() as db:
        assert db.get(BackupPlanRun, run_id).status == "failed"
        assert not after_restart.has_active_run(db, plan_id)


@pytest.mark.unit
def test_the_sweep_leaves_a_run_committed_while_it_reads(session_per_request, service):
    """A thread commits a run between the sweep's look at the live runs and
    its read of the rows. The run is live before its row shows, so the sweep
    has to read the rows first."""
    sessions = session_per_request
    plan_id = _seed_plan(sessions, _seed_repository(sessions))
    committed: list[int] = []

    def commit_a_run(conn, cursor, statement, *_args) -> None:
        if "FROM backup_plan_runs" in statement and not committed:
            committed.append(0)  # not for the statements of the commit below
            committed[0] = _create_run(service, sessions, plan_id)

    engine = sessions.kw["bind"]
    event.listen(engine, "before_cursor_execute", commit_a_run)
    try:
        with sessions() as db:
            cleanup_orphaned_jobs(db, service.live_run_ids)
    finally:
        event.remove(engine, "before_cursor_execute", commit_a_run)

    assert committed and committed[0]
    assert _runs(sessions, plan_id) == [("manual", "pending")]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_run_the_startup_sweep_ends_keeps_its_plan_busy_for_its_post_hooks(
    database, monkeypatch
):
    """A restart left a run whose post-backup scripts are still to run. The
    sweep shows it as failed and the scripts are launched after that: a start
    in a worker thread that reads in between must not find the plan free."""
    import app.database.database as app_database
    import app.main as main

    service = backup_plan_execution_service
    repository_id = _seed_repository(database)
    plan_id = _seed_plan(database, repository_id)
    run_id = _seed_run_with_post_hooks_to_run(
        database, plan_id, repository_id, "running"
    )
    scripts_may_end = asyncio.Event()

    async def post_hooks(_run_id: int) -> None:
        await scripts_may_end.wait()

    monkeypatch.setattr(service, "_run_post_hooks_after_restart", post_hooks)
    monkeypatch.setattr(app_database, "SessionLocal", database)
    monkeypatch.setattr(
        import_module("app.api.repositories"),
        "resume_pending_initial_cloud_mirror_sync_operations",
        lambda: 0,
    )
    seen: list[tuple[str, bool]] = []

    def a_start_reads(_session) -> None:
        with database() as other:
            seen.append(
                (
                    other.get(BackupPlanRun, run_id).status,
                    service.has_active_run(other, plan_id),
                )
            )

    event.listen(database, "after_commit", a_start_reads)
    try:
        main._recover_interrupted_work()
    finally:
        event.remove(database, "after_commit", a_start_reads)

    try:
        assert seen and seen[-1] == ("failed", True)
        assert all(busy for _status, busy in seen)
        with database() as db:
            assert service.has_active_run(db, plan_id)
    finally:
        scripts_may_end.set()
    await asyncio.wait_for(_until(lambda: not service.live_run_ids), HOLD_SECONDS)
    with database() as db:
        assert not service.has_active_run(db, plan_id)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_run_held_for_post_hooks_that_are_not_launched_is_not_left_live(
    service, monkeypatch
):
    launched: list[int] = []

    def one_task(coroutine):
        coroutine.close()
        if launched:
            raise RuntimeError("no running event loop")
        launched.append(1)

    monkeypatch.setattr(
        "app.services.backup_plan_execution_service.asyncio.create_task", one_task
    )
    with service.holding_for_post_hooks() as hold:
        hold([7, 8, 9])
    assert service.live_run_ids == {7, 8, 9}

    with pytest.raises(RuntimeError):
        service.recover_post_hooks_after_restart([7, 8, 9])

    assert service.live_run_ids == set()


@pytest.mark.unit
def test_a_start_that_reads_while_the_sweep_ends_a_run_finds_the_plan_busy(
    database, service
):
    """The start looks for an active run of the plan, and the sweep shows the
    interrupted run as failed between two steps of that look. The sweep holds
    the run before its commit, so the look reads the rows first and who is
    live after: the other way round it finds neither."""
    repository_id = _seed_repository(database)
    plan_id = _seed_plan(database, repository_id)
    run_id = _seed_run_with_post_hooks_to_run(
        database, plan_id, repository_id, "running"
    )
    swept: list[list[int]] = []

    def sweep(conn, cursor, statement, *_args) -> None:
        if "FROM backup_plan_runs" in statement and not swept:
            swept.append([])  # not for the statements of the sweep below
            with service.holding_for_post_hooks() as hold, database() as other:
                swept[0] = cleanup_orphaned_jobs(
                    other, service.live_run_ids, hold_for_post_hooks=hold
                )

    engine = database.kw["bind"]
    with database() as db:
        event.listen(engine, "before_cursor_execute", sweep)
        try:
            busy = service.has_active_run(db, plan_id)
        finally:
            event.remove(engine, "before_cursor_execute", sweep)

    assert swept == [[run_id]]
    with database() as db:
        assert db.get(BackupPlanRun, run_id).status == "failed"
    assert busy


@pytest.mark.unit
def test_a_finished_run_with_post_hooks_to_run_keeps_its_plan_busy_from_the_sweep_on(
    database, service
):
    """A run cancelled before the restart is finished already, so the sweep
    has nothing to end and commits nothing. Its post-backup scripts are
    launched after the sweep, and a start in a worker thread reads in
    between."""
    repository_id = _seed_repository(database)
    plan_id = _seed_plan(database, repository_id)
    run_id = _seed_run_with_post_hooks_to_run(
        database, plan_id, repository_id, "cancelled"
    )

    with service.holding_for_post_hooks() as hold, database() as db:
        assert not service.has_active_run(db, plan_id)
        pending = cleanup_orphaned_jobs(
            db, service.live_run_ids, hold_for_post_hooks=hold
        )

    assert pending == [run_id]
    with database() as db:
        assert service.has_active_run(db, plan_id)


@pytest.mark.unit
def test_a_sweep_that_fails_gives_up_the_runs_it_held(database, monkeypatch):
    """The sweep holds the runs and its commit fails: no post-backup scripts
    are launched, and a run that stayed live would keep its plan busy until
    the next restart."""
    import app.database.database as app_database
    import app.main as main

    service = backup_plan_execution_service
    repository_id = _seed_repository(database)
    plan_id = _seed_plan(database, repository_id)
    interrupted = _seed_run_with_post_hooks_to_run(
        database, plan_id, repository_id, "running"
    )
    other_plan_id = _seed_plan(database, repository_id, name="other plan")
    cancelled = _seed_run_with_post_hooks_to_run(
        database, other_plan_id, repository_id, "cancelled"
    )
    held_at_the_commit: list[set[int]] = []

    def sessions_whose_commit_fails():
        db = database()

        def commit() -> None:
            held_at_the_commit.append(set(service.live_run_ids))
            raise OperationalError("COMMIT", {}, Exception("database is locked"))

        db.commit = commit
        return db

    monkeypatch.setattr(
        import_module("app.api.repositories"),
        "resume_pending_initial_cloud_mirror_sync_operations",
        lambda: 0,
    )
    try:
        with patch.object(app_database, "SessionLocal", sessions_whose_commit_fails):
            main._recover_interrupted_work()

        assert held_at_the_commit[-1] == {interrupted, cancelled}
        assert service.live_run_ids == set()
        with database() as db:
            assert not service.has_active_run(db, other_plan_id)
    finally:
        service.live_run_ids.clear()
