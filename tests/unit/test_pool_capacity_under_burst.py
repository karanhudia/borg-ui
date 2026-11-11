"""A burst of requests must not exhaust the connection pool.

Requests and the threads they run on are both limited: the connection pool
(10 + 20 in production) and the worker threads (30). A request that kept the
connection of its authentication until it ended needed a thread for its
handler while holding it, and the threads, busy authenticating further
requests, waited for connections. Nothing moved until the pool timeout.

The event loop must never wait for a pooled connection either: the requests
holding them give them back only once the loop has run their cleanup.
"""

import asyncio
import collections
import os
import threading
import time
import uuid
from contextlib import contextmanager

import anyio
import httpx
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool, QueuePool, StaticPool
from starlette.requests import Request

from app.core.agent_auth import get_current_agent
from app.database.database import Base, get_db, register_utc_session_timezone
from app.database.models import AgentMachine

POSTGRES_URL = os.getenv("BORG_TEST_POSTGRES_URL")
RAW_TOKEN = "borgui_agent_" + "c" * 43
AGENT_HEADER = {"X-Borg-Agent-Authorization": f"Bearer {RAW_TOKEN}"}
# Short enough that a burst stuck until the pool timeout fails the test
# quickly, long enough for a free connection to be handed over in time.
POOL_TIMEOUT_SECONDS = 3


def _create_agent(db) -> int:
    agent = AgentMachine(
        name="Burst Agent",
        agent_id="agt_burst",
        token_hash="checked by the test's stand-in",
        token_prefix=RAW_TOKEN[:20],
        status="online",
        capabilities=[],
    )
    db.add(agent)
    db.commit()
    return agent.id


def _queue_pool(test_db, size: int):
    """An engine on the test's database with a production-style pool."""
    return create_engine(
        test_db.get_bind().url,
        poolclass=QueuePool,
        pool_size=size,
        max_overflow=0,
        pool_timeout=POOL_TIMEOUT_SECONDS,
        connect_args={"check_same_thread": False, "timeout": 30},
    )


def _request() -> Request:
    return Request({"type": "http", "headers": [], "state": {}})


def _statements(engine) -> list:
    statements: list = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    return statements


@contextmanager
def _single_connection_engine(database, test_db):
    """A pool of one connection on SQLite (the test's database) or on
    PostgreSQL (a schema of its own: other PostgreSQL tests drop `public`)."""
    if database == "sqlite":
        engine = _queue_pool(test_db, size=1)
        try:
            yield engine
        finally:
            engine.dispose()
        return
    schema = f"pool_capacity_{uuid.uuid4().hex}"
    admin = create_engine(POSTGRES_URL)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(
        POSTGRES_URL,
        poolclass=QueuePool,
        pool_size=1,
        max_overflow=0,
        pool_timeout=POOL_TIMEOUT_SECONDS,
        connect_args={"options": f"-c search_path={schema}"},
    )
    register_utc_session_timezone(engine)
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


@pytest.mark.unit
@pytest.mark.parametrize(
    "database",
    [
        "sqlite",
        pytest.param(
            "postgresql",
            marks=pytest.mark.skipif(
                not POSTGRES_URL, reason="BORG_TEST_POSTGRES_URL is not set"
            ),
        ),
    ],
)
def test_authentication_gives_its_connection_back(test_db, monkeypatch, database):
    monkeypatch.setattr(
        "app.core.agent_auth.verify_password", lambda token, token_hash: True
    )
    with _single_connection_engine(database, test_db) as engine:
        sessions = sessionmaker(bind=engine, autoflush=False)
        with sessions() as setup:
            agent_id = _create_agent(setup)
        request = _request()
        request.scope["headers"] = [
            (b"x-borg-agent-authorization", f"Bearer {RAW_TOKEN}".encode())
        ]
        db = sessions()
        try:
            agent = get_current_agent(request, db)
            assert engine.pool.checkedout() == 0

            # What the handlers read from the agent is still loaded: no query.
            statements = _statements(engine)
            assert (agent.id, agent.agent_id, agent.status) == (
                agent_id,
                "agt_burst",
                "online",
            )
            assert statements == []
            assert request.state.current_agent is agent

            # And what they write through it is still written.
            agent.hostname = "written-after-authentication"
            db.commit()
        finally:
            db.close()

        with sessions() as check:
            assert check.get(AgentMachine, agent_id).hostname == (
                "written-after-authentication"
            )


@pytest.mark.unit
def test_a_burst_larger_than_the_pool_and_the_threads_succeeds(
    test_client, test_db, monkeypatch
):
    """The production deadlock at a small scale: two worker threads, two
    connections, eight polls. The runner shares the pool, as in production,
    and is woken throughout, so that its lease renewals and ticks meet the
    burst."""
    _create_agent(test_db)
    from app.main import app
    from app.services.operations.runner import operation_runner

    engine = _queue_pool(test_db, size=2)
    factory = sessionmaker(bind=engine, autoflush=False)

    def per_request_session():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = per_request_session
    monkeypatch.setattr("app.database.database.SessionLocal", factory)

    def slow_check(token, token_hash):
        time.sleep(0.05)
        return True

    monkeypatch.setattr("app.core.agent_auth.verify_password", slow_check)
    bursting = threading.Event()
    ticks_during_the_burst: list = []
    tick = operation_runner.tick

    async def counted_tick():
        dispatched = await tick()
        if bursting.is_set():
            ticks_during_the_burst.append(dispatched)
        return dispatched

    monkeypatch.setattr(operation_runner, "tick", counted_tick)

    async def wake_the_runner():
        while bursting.is_set():
            operation_runner.wake()
            await asyncio.sleep(0.01)

    async def burst():
        limiter = anyio.to_thread.current_default_thread_limiter()
        tokens = limiter.total_tokens
        limiter.total_tokens = 2
        bursting.set()
        waker = asyncio.create_task(wake_the_runner())
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test", timeout=None
            ) as client:
                return await asyncio.gather(
                    *[
                        client.get("/api/agents/jobs/poll", headers=AGENT_HEADER)
                        for _ in range(8)
                    ],
                    return_exceptions=True,
                )
        finally:
            bursting.clear()
            await waker
            limiter.total_tokens = tokens

    try:
        results = test_client.portal.call(burst)
    finally:
        engine.dispose()

    outcomes = collections.Counter(
        getattr(result, "status_code", type(result).__name__) for result in results
    )
    assert outcomes == {200: 8}
    assert ticks_during_the_burst


def _on_the_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("method", "path", "keeps_connection"),
    [
        # a plain `def` handler, run in a worker thread
        ("GET", "/api/agents/jobs/poll", False),
        # a coroutine that queries the request's session on the loop
        ("POST", "/api/agents/jobs/{job_id}/artifact", True),
        # a coroutine that leaves the database to a worker of its own
        ("POST", "/api/agents/jobs/{job_id}/complete", False),
    ],
)
def test_authentication_keeps_its_connection_only_for_a_handler_on_the_loop(
    test_db, monkeypatch, method, path, keeps_connection
):
    from app.api.agents import router

    _create_agent(test_db)
    monkeypatch.setattr(
        "app.core.agent_auth.verify_password", lambda token, token_hash: True
    )
    (route,) = [
        route
        for route in router.routes
        if route.path == path and method in route.methods
    ]
    request = _request()
    request.scope["headers"] = [
        (b"x-borg-agent-authorization", f"Bearer {RAW_TOKEN}".encode())
    ]
    request.scope["route"] = route
    engine = _queue_pool(test_db, size=1)
    db = sessionmaker(bind=engine, autoflush=False)()
    try:
        get_current_agent(request, db)
        assert engine.pool.checkedout() == (1 if keeps_connection else 0)
    finally:
        db.close()
        engine.dispose()


@pytest.mark.unit
def test_a_handler_on_the_loop_keeps_the_connection_of_its_authentication(
    test_client, test_db, monkeypatch
):
    """A coroutine handler that queries its session runs on the loop. Had the
    authentication given the connection back, the handler's first query
    would wait for one there, holding every other request."""
    from app.main import app
    from app.database.models import AgentJob

    agent_id = _create_agent(test_db)
    # Not a listing or a download: with no consumer, its upload is drained.
    job = AgentJob(
        agent_machine_id=agent_id,
        job_type="backup",
        status="running",
        payload={"job_kind": "backup.create"},
    )
    test_db.add(job)
    test_db.commit()
    monkeypatch.setattr(
        "app.core.agent_auth.verify_password", lambda token, token_hash: True
    )
    # The request's own engine: the runner and the other background services
    # use the test's.
    engine = create_engine(
        test_db.get_bind().url,
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine, autoflush=False)

    def request_session():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = request_session
    events: list = []

    def record_checkout(dbapi_connection, connection_record, connection_proxy):
        events.append(("checkout on the loop", _on_the_loop()))

    def record_job_read(conn, cursor, statement, parameters, context, executemany):
        if "FROM agent_jobs" in statement:
            events.append(("job read", _on_the_loop()))

    event.listen(engine, "checkout", record_checkout)
    event.listen(engine, "before_cursor_execute", record_job_read)
    try:
        response = test_client.post(
            f"/api/agents/jobs/{job.id}/artifact", headers=AGENT_HEADER, content=b"x"
        )
    finally:
        engine.dispose()

    assert response.status_code == 200
    # The handler reads its job on the loop, on the connection the
    # authentication checked out in its worker thread.
    first_read = events.index(("job read", True))
    assert events[:first_read] == [("checkout on the loop", False)]


@pytest.mark.unit
@pytest.mark.parametrize("route", ["poll", "logs", "cancel"])
def test_a_handler_in_a_worker_gives_its_connection_back_before_the_response(
    test_client, test_db, monkeypatch, route
):
    """FastAPI validates a plain `def` handler's response in another worker
    thread, before the request's session is closed. A session still holding
    its connection there waits for a thread while holding it."""
    from app.main import app
    from app.database.models import AgentJob

    agent_id = _create_agent(test_db)
    job = AgentJob(
        agent_machine_id=agent_id,
        job_type="repository",
        status="running",
        payload={"job_kind": "repository.delete_archive"},
    )
    test_db.add(job)
    test_db.commit()
    monkeypatch.setattr(
        "app.core.agent_auth.verify_password", lambda token, token_hash: True
    )
    factory = sessionmaker(bind=test_db.get_bind(), autoflush=False)
    sessions: list = []

    def recorded_session():
        db = factory()
        sessions.append(db)
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = recorded_session
    import fastapi.routing

    serialize = fastapi.routing.serialize_response
    holding_at_validation: list = []

    async def recording_serialize(*args, **kwargs):
        holding_at_validation.append(sessions[-1].in_transaction())
        return await serialize(*args, **kwargs)

    monkeypatch.setattr(fastapi.routing, "serialize_response", recording_serialize)

    if route == "poll":
        response = test_client.get("/api/agents/jobs/poll", headers=AGENT_HEADER)
    elif route == "logs":
        # The second copy of a line is acknowledged after the read, without a
        # commit.
        for _ in range(2):
            response = test_client.post(
                f"/api/agents/jobs/{job.id}/logs",
                headers=AGENT_HEADER,
                json={"sequence": 0, "message": "a line"},
            )
        assert response.json()["duplicate"] is True
    else:
        response = test_client.post(
            f"/api/agents/jobs/{job.id}/cancel", headers=AGENT_HEADER, json={}
        )

    assert response.status_code == 200
    assert holding_at_validation[-1] is False


def _checkouts_on_the_loop(engine) -> list:
    on_the_loop: list = []

    def record(dbapi_connection, connection_record, connection_proxy):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            on_the_loop.append(False)
        else:
            on_the_loop.append(True)

    event.listen(engine, "checkout", record)
    return on_the_loop


async def _until(condition, seconds: float = 5) -> None:
    deadline = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < deadline, "the runner never got there"
        await asyncio.sleep(0.01)


def _runner(engine, ticks: int, poll_interval: float = 0.01):
    """A runner on `engine` that stops after `ticks` ticks. Startup recovery
    is left out: it runs once, on the loop, before the app serves requests."""
    from app.services.operations.runner import OperationRunner

    runner = OperationRunner(
        session_factory=sessionmaker(bind=engine, autoflush=False),
        registry={},
        poll_interval=poll_interval,
    )
    runner._recover = lambda before_recovery: None
    ticked: list = []
    tick = runner.tick

    async def counted_tick():
        dispatched = await tick()
        ticked.append(dispatched)
        if len(ticked) >= ticks:
            runner.stop()
            runner.wake()
        return dispatched

    runner.tick = counted_tick
    return runner, ticked


@pytest.mark.unit
def test_the_runner_takes_its_connections_off_the_loop(test_db):
    """After its recovery the runner renews its lease and ticks every few
    seconds, each starting with a pool checkout. On the loop, with every
    connection held by a request waiting for the loop, that checkout stood
    until the pool timeout."""
    engine = _queue_pool(test_db, size=2)
    runner, ticked = _runner(engine, ticks=2)
    on_the_loop = _checkouts_on_the_loop(engine)
    try:
        asyncio.run(asyncio.wait_for(runner.start(), timeout=10))
    finally:
        engine.dispose()

    assert len(ticked) == 2
    # the first lease (on the loop, as recovery needs), then tick, lease,
    # tick; the release at shutdown follows
    assert on_the_loop[:4] == [True, False, False, False]


@pytest.mark.unit
def test_a_runner_on_a_pool_that_never_waits_stays_on_the_loop():
    """A pool that shares one connection (or keeps one per thread) never makes
    a checkout wait, and its connection must not move to another thread."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    runner, ticked = _runner(engine, ticks=2)
    on_the_loop = _checkouts_on_the_loop(engine)
    try:
        asyncio.run(asyncio.wait_for(runner.start(), timeout=10))
    finally:
        engine.dispose()

    assert len(ticked) == 2
    assert on_the_loop[:4] == [True, True, True, True]


@pytest.mark.unit
def test_the_runner_takes_no_shared_worker_thread(test_db):
    """The requests holding the connections can hold every shared worker
    thread too; the runner's checkouts must not wait for one."""
    engine = _queue_pool(test_db, size=2)
    runner, ticked = _runner(engine, ticks=2)

    async def run():
        anyio.to_thread.current_default_thread_limiter().total_tokens = 1
        release = threading.Event()
        taken = threading.Event()

        def hold_the_only_thread():
            taken.set()
            release.wait(10)

        holder = asyncio.create_task(anyio.to_thread.run_sync(hold_the_only_thread))
        await asyncio.to_thread(taken.wait, 10)
        try:
            await asyncio.wait_for(runner.start(), timeout=5)
        finally:
            release.set()
            await holder

    try:
        asyncio.run(run())
    finally:
        engine.dispose()

    assert len(ticked) == 2


def _connections(engine) -> list:
    """Every connection opened on `engine`, kept alive here so that one left
    open is not quietly given back by the garbage collector."""
    connections: list = []
    event.listen(engine, "engine_connect", connections.append)
    return connections


class _ThreadGate:
    """Holds the first worker thread that reaches it until the test opens it."""

    def __init__(self):
        self.armed = False
        self.reached = threading.Event()
        self.opened = threading.Event()

    def hold(self):
        if self.armed and not _on_the_loop() and not self.reached.is_set():
            self.reached.set()
            self.opened.wait(10)


def _cancel(task, cancelled: str) -> None:
    """Cancel the task, or every task but the test's own, as an event loop
    shutting down does."""
    if cancelled == "the task":
        task.cancel()
        return
    for other in asyncio.all_tasks():
        if other is not asyncio.current_task():
            other.cancel()


_CANCELLED = pytest.mark.parametrize("cancelled", ["the task", "every task"])


@pytest.mark.unit
@_CANCELLED
def test_a_cancelled_runner_releases_its_lease_after_its_renewal(test_db, cancelled):
    """Shutdown stops and drains the runner, then cancels its task. A renewal
    still running in its thread must not take the lease back after the
    cancelled runner has released it: the next process would wait for it to
    expire."""
    from app.database.models import OperationsRunnerLease

    engine = _queue_pool(test_db, size=2)
    runner, ticked = _runner(engine, ticks=1000)
    gate = _ThreadGate()

    def hold_the_renewal(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE operations_runner_lease"):
            gate.hold()

    renewed = threading.Event()

    def record_the_renewal(conn):
        if gate.reached.is_set() and not _on_the_loop():
            renewed.set()

    event.listen(engine, "before_cursor_execute", hold_the_renewal)
    event.listen(engine, "commit", record_the_renewal)

    async def run():
        task = asyncio.create_task(runner.start())
        await _until(lambda: ticked)
        gate.armed = True
        runner.wake()
        assert await asyncio.to_thread(gate.reached.wait, 5)
        # app shutdown: stop, wake, drain, then cancel the background task
        runner.stop()
        runner.wake()
        await runner.drain()
        _cancel(task, cancelled)
        asyncio.get_running_loop().call_later(0.2, gate.opened.set)
        with pytest.raises(asyncio.CancelledError):
            await task
        gate.opened.set()
        assert await asyncio.to_thread(renewed.wait, 5)

    try:
        asyncio.run(run())
    finally:
        engine.dispose()

    test_db.expire_all()
    assert test_db.get(OperationsRunnerLease, 1).holder is None


@pytest.mark.unit
@_CANCELLED
def test_a_cancelled_tick_gives_its_connection_back(test_db, cancelled):
    engine = _queue_pool(test_db, size=2)
    runner, _ = _runner(engine, ticks=1)
    gate = _ThreadGate()
    gate.armed = True
    event.listen(engine, "checkout", lambda *args: gate.hold())
    connections = _connections(engine)

    async def run():
        task = asyncio.create_task(runner.tick())
        assert await asyncio.to_thread(gate.reached.wait, 5)
        _cancel(task, cancelled)
        asyncio.get_running_loop().call_later(0.2, gate.opened.set)
        with pytest.raises(asyncio.CancelledError):
            await task

    try:
        asyncio.run(run())
        assert len(connections) == 1
        assert connections[0].closed
        assert engine.pool.checkedout() == 0
    finally:
        engine.dispose()


@pytest.mark.unit
def test_a_tick_that_claims_work_takes_no_connection_on_the_loop(test_db):
    """A claim commits, and the tick reads the claimed row again before it
    starts the task. Its connection outlives that commit, so the read does
    not wait for a checkout on the loop."""
    from app.database.models import Repository, SystemSettings
    from app.services.operations.enqueue import enqueue
    from app.services.operations.runner import OperationRunner, Outcome

    repository = Repository(name="burst", path="/burst")
    test_db.add(repository)
    if test_db.query(SystemSettings).first() is None:
        test_db.add(SystemSettings())
    test_db.commit()
    enqueue(test_db, "stats", repository_id=repository.id)

    ran: list = []

    async def stats(ctx):
        ran.append(ctx.operation_id)
        return Outcome()

    engine = _queue_pool(test_db, size=2)
    runner = OperationRunner(
        session_factory=sessionmaker(bind=engine, autoflush=False),
        registry={"stats": stats},
    )
    on_the_loop = _checkouts_on_the_loop(engine)
    connections = _connections(engine)

    async def run():
        dispatched = await runner.tick()
        during_the_tick = list(on_the_loop)
        # the tick's connection goes back when the tick ends
        assert len(connections) == 1
        assert connections[0].closed
        await asyncio.gather(*runner.running_tasks.values())
        return dispatched, during_the_tick

    try:
        dispatched, during_the_tick = asyncio.run(run())
    finally:
        engine.dispose()

    assert dispatched == 1
    assert len(ran) == 1
    assert during_the_tick == [False]


@pytest.mark.unit
def test_a_standby_runner_retries_off_the_loop(test_db):
    """While another process holds the lease, the runner retries at every
    poll, the app serving requests meanwhile. Only the first attempt runs on
    the loop."""
    from datetime import timedelta

    from app.database.models import OperationsRunnerLease, utc_now

    test_db.add(
        OperationsRunnerLease(
            id=1, holder="another process", expires_at=utc_now() + timedelta(hours=1)
        )
    )
    test_db.commit()
    engine = _queue_pool(test_db, size=2)
    runner, ticked = _runner(engine, ticks=1)
    attempts: list = []
    renew = runner._renew_lease

    def counted_renewal():
        held = renew()
        attempts.append(held)
        if len(attempts) >= 3:
            runner.stop()
        return held

    runner._renew_lease = counted_renewal
    on_the_loop = _checkouts_on_the_loop(engine)
    try:
        asyncio.run(asyncio.wait_for(runner.start(), timeout=10))
    finally:
        engine.dispose()

    assert attempts == [False, False, False]
    assert not ticked
    assert on_the_loop[:3] == [True, False, False]


@pytest.mark.unit
def test_the_runner_recovers_before_the_loop_moves_on(test_db):
    """The app starts the runner as a task and goes on to serve requests.
    The first lease and the recovery happen at the task's first step, before
    the loop runs anything else, as before."""
    engine = _queue_pool(test_db, size=2)
    runner, _ = _runner(engine, ticks=1)
    steps: list = []
    runner._recover = lambda before_recovery: steps.append("recovered")

    async def run():
        task = asyncio.create_task(runner.start())
        await asyncio.sleep(0)
        steps.append("loop moved on")
        await asyncio.wait_for(task, timeout=10)

    try:
        asyncio.run(run())
    finally:
        engine.dispose()

    assert steps == ["recovered", "loop moved on"]


@pytest.mark.unit
def test_the_loop_runs_while_the_runner_waits_for_a_connection(test_db):
    engine = _queue_pool(test_db, size=1)
    # A poll long enough that the runner renews only when woken.
    runner, ticked = _runner(engine, ticks=2, poll_interval=30)
    renewals = {"started": 0, "finished": 0}
    renew = runner._renew_lease

    def counted_renewal():
        renewals["started"] += 1
        try:
            return renew()
        finally:
            renewals["finished"] += 1

    runner._renew_lease = counted_renewal

    async def run():
        task = asyncio.create_task(runner.start())
        await _until(lambda: ticked)
        # The only connection is taken; the renewal it is woken for waits
        # for it.
        held = await asyncio.to_thread(engine.connect)
        runner.wake()
        await _until(lambda: renewals["started"] == 2)
        beats = 0
        deadline = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            await asyncio.sleep(0.01)
            beats += 1
        still_waiting = renewals["finished"] == 1
        await asyncio.to_thread(held.close)
        await asyncio.wait_for(task, timeout=10)
        return beats, still_waiting

    try:
        beats, still_waiting = asyncio.run(run())
    finally:
        engine.dispose()

    assert still_waiting
    assert len(ticked) == 2
    # The loop went on while the runner waited for the held connection.
    assert beats >= 20
